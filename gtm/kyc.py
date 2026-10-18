"""KYC (know-your-customer) profile fields, completeness score and the downloadable blank template.

A KYC profile is a structured research record for ONE account. Everything seeded here is fictional demo data.
Never paste real client confidential information into the demo store.
"""
import csv
import io

from gtm import schema

# (key, label, kind, help). kind: text | longtext | select:<vocab> | multi:<vocab>
FIELDS = [
    ("website", "Website", "text", "Company website (public)"),
    ("hq_city", "HQ city", "text", ""),
    ("employee_range", "Employees", f"select:{'|'.join(schema.COMPANY_SIZES)}", ""),
    ("annual_revenue_range", "Annual revenue range", "text", "e.g. $50M-$200M"),
    ("business_model", "Business model", "text", ""),
    ("primary_contact", "Primary contact", "text", "Name and title"),
    ("decision_makers", "Decision makers / buying committee", "longtext", ""),
    ("requested_capabilities", "Requested capabilities", f"multi:{'|'.join(schema.CAPABILITIES)}", "What the client has asked for or signalled"),
    ("current_vendors", "Current vendors", "text", ""),
    ("competitors", "Competitors we face here", "text", ""),
    ("tech_stack", "Relevant tech stack", "text", ""),
    ("budget_range", "Budget range", "text", ""),
    ("buying_timeline", "Buying timeline", "text", ""),
    ("compliance_requirements", "Compliance / data requirements", "longtext", ""),
    ("pain_points", "Pain points", "longtext", ""),
    ("trigger_events", "Trigger events", "longtext", "Funding, hires, launches, regulation"),
    ("icp_fit_notes", "ICP fit notes", "longtext", ""),
    ("source", "Research source", "text", "e.g. company site, press release, manual research"),
    ("last_reviewed", "Last reviewed (YYYY-MM-DD)", "text", ""),
]
KEYS = [f[0] for f in FIELDS]
LABELS = {f[0]: f[1] for f in FIELDS}
REQUIRED_FOR_COMPLETE = [k for k in KEYS if k not in ("last_reviewed",)]


def vocab(kind):
    return kind.split(":", 1)[1].split("|") if ":" in kind else []


def clean(data):
    """Keep only known keys; multi-select values become a '; '-joined string; everything trimmed."""
    out = {}
    for key, _label, kind, _help in FIELDS:
        v = data.get(key, "")
        if isinstance(v, (list, tuple)):
            v = "; ".join(str(x).strip() for x in v if str(x).strip())
        v = " ".join(str(v or "").split()) if not kind.startswith("longtext") else str(v or "").strip()
        out[key] = v[:2000]
    return out


def completeness(data):
    """Share of fields that are filled, 0..1."""
    d = clean(data)
    return round(sum(bool(d[k]) for k in REQUIRED_FOR_COMPLETE) / len(REQUIRED_FOR_COMPLETE), 3)


def template_csv(account_id="", account_name=""):
    """A blank, downloadable KYC template: one header row of labels and one empty row to fill in."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["account_id", "account_name"] + KEYS)
    w.writerow([account_id, account_name] + [""] * len(KEYS))
    return buf.getvalue().encode("utf-8")


def profile_csv(account_id, account_name, data):
    d = clean(data)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["account_id", "account_name"] + KEYS)
    w.writerow([account_id, account_name] + [d[k] for k in KEYS])
    return buf.getvalue().encode("utf-8")


def parse_template_row(row):
    """A filled-in template row (dict from csv.DictReader) -> (account_id, cleaned profile)."""
    return str(row.get("account_id", "")).strip(), clean({k: row.get(k, "") for k in KEYS})
