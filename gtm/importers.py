"""CSV import for prospects (planned Apollo / ZoomInfo style exports) - a LOCAL file import only, never a CRM integration.

Flow: detect column mapping -> preview (every row validated and de-duplicated with the store's own rules, nothing written)
-> import only the rows marked 'ok'. Rows whose company is not already an account are reported, not auto-created.
Limits keep a bad file harmless: at most MAX_ROWS rows and MAX_BYTES bytes.
"""
import csv
import io
import re

import pandas as pd

from gtm import validation as v
from gtm.validation import ValidationError

MAX_ROWS = 2000
MAX_BYTES = 2_000_000

# canonical field -> accepted header spellings (compared after lower-casing and removing non-alphanumerics)
ALIASES = {
    "full_name": ["fullname", "name", "contactname", "personname"],
    "first_name": ["firstname", "first", "givenname"],
    "last_name": ["lastname", "last", "surname", "familyname"],
    "title": ["title", "jobtitle", "position", "role"],
    "email": ["email", "emailaddress", "workemail", "businessemail", "primaryemail"],
    "linkedin_url": ["linkedinurl", "linkedin", "linkedinprofile", "personlinkedinurl", "linkedincontactprofileurl", "linkedinprofileurl"],
    "phone": ["phone", "directphone", "mobilephone", "workphone", "phonenumber", "directphonenumber"],
    "company": ["company", "companyname", "account", "accountname", "organization", "organisation", "employer"],
}
PRESET_HINTS = {"Apollo": ["First Name", "Last Name", "Title", "Company", "Email", "Person Linkedin Url"],
                "ZoomInfo": ["First Name", "Last Name", "Job Title", "Company Name", "Email Address", "Direct Phone Number"]}


def _norm(header):
    return re.sub(r"[^a-z0-9]", "", str(header).lower())


def detect_mapping(columns):
    """{canonical field: original column name} for every header we recognise."""
    by_norm = {}
    for c in columns:
        by_norm.setdefault(_norm(c), c)
    return {field: by_norm[a] for field, aliases in ALIASES.items() for a in aliases if a in by_norm}


def read_csv(raw):
    if not isinstance(raw, (bytes, bytearray)):
        raise ValidationError("Upload a CSV file.")
    if len(raw) > MAX_BYTES:
        raise ValidationError(f"File is too large (limit {MAX_BYTES // 1_000_000} MB).")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    rows = list(csv.DictReader(io.StringIO(text)))
    if not rows:
        raise ValidationError("The file has no data rows.")
    if len(rows) > MAX_ROWS:
        raise ValidationError(f"Too many rows ({len(rows)}; limit {MAX_ROWS}).")
    return rows


def preview(store, raw, owner=None):
    """Validate every row without writing. Returns (mapping, DataFrame[row, name, title, email, company, account_id, status, reason])."""
    rows = read_csv(raw)
    mapping = detect_mapping(rows[0].keys())
    if "company" not in mapping or not ({"full_name", "first_name"} & set(mapping)):
        raise ValidationError("Could not find the required columns: a company and a name (or first and last name). "
                              f"Detected: {', '.join(mapping) or 'none'}.")
    accounts = {r.name_key: r.account_id for r in store.df("SELECT account_id, name_key FROM accounts").itertuples()}
    seen_email, seen_li, out = set(), set(), []
    for n, row in enumerate(rows, 2):                                         # row 1 of the file is the header
        get = lambda f: v.text(row.get(mapping.get(f, ""), ""), 300)
        name = get("full_name") or " ".join(x for x in (get("first_name"), get("last_name")) if x)
        rec = {"row": n, "name": name, "title": get("title"), "email": get("email"), "company": get("company"), "account_id": "", "status": "ok", "reason": ""}
        aid = accounts.get(v.name_key(rec["company"]))
        ek, lk = v.email_key(rec["email"]), v.linkedin_key(get("linkedin_url"))
        if not aid:
            rec.update(status="unmatched account", reason=f"No account named {rec['company']!r}; create it first.")
        elif (ek and ek in seen_email) or (lk and lk in seen_li):
            rec.update(status="duplicate in file", reason="Same email or LinkedIn profile appears earlier in this file.", account_id=aid)
        else:
            rec["account_id"] = aid
            try:
                store.add_prospect(_record(rec, get, owner), dry_run=True)
            except ValidationError as exc:
                dup = any(m.startswith("Duplicate") for m in exc.messages)
                rec.update(status="duplicate" if dup else "invalid", reason="; ".join(exc.messages))
        if rec["status"] == "ok":
            seen_email.add(ek) if ek else None
            seen_li.add(lk) if lk else None
        out.append(rec)
    return mapping, pd.DataFrame(out)


def _record(rec, get, owner):
    return {"account_id": rec["account_id"], "full_name": rec["name"], "title": rec["title"], "email": rec["email"],
            "linkedin_url": get("linkedin_url"), "phone": get("phone"), "lead_source": "CSV import", **({"owner": owner} if owner else {})}


def import_rows(store, raw, owner=None):
    """Re-validate and insert only the rows that preview as 'ok'. Returns {'imported': n, 'skipped': n, 'errors': [...]}."""
    mapping, prev = preview(store, raw, owner)
    rows = {n: r for n, r in enumerate(read_csv(raw), 2)}
    imported, errors = 0, []
    for rec in prev[prev.status == "ok"].to_dict("records"):
        row = rows[rec["row"]]
        get = lambda f, row=row: v.text(row.get(mapping.get(f, ""), ""), 300)
        try:
            store.add_prospect(_record(rec, get, owner))
            imported += 1
        except ValidationError as exc:                                         # e.g. a duplicate created by an earlier row of this import
            errors.append(f"row {rec['row']}: {'; '.join(exc.messages)}")
    return {"imported": imported, "skipped": len(prev) - imported, "errors": errors}
