"""The V2 GTM demo store: SQLite, row-level writes, validation, deduplication, stop rules and an audit log.

Safety properties
  * Separate file (data/gtm_v2.db, git-ignored) - the V1 database is never touched.
  * Every write is ONE row (or the few rows a business rule requires) inside a transaction. No whole-table replacement.
  * Inputs are validated (all problems reported together) and de-duplicated (account name, prospect email / LinkedIn).
  * Every change is recorded in `audit_log`. There is no authentication: the actor is always 'demo'.
  * `reset_demo(confirm=True)` rebuilds ONLY this demo file from the synthetic seed.
"""
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pandas as pd

from gtm import clock, kyc, schema, validation as v
from gtm.validation import ValidationError

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
TS = "%Y-%m-%d %H:%M:%S"


def default_path():
    return Path(os.environ.get("GTM_V2_DB") or DATA_DIR / "gtm_v2.db")


def _ts():
    return clock.now().strftime(TS)


def _today():
    return clock.today()


def _fail(message):
    raise ValidationError(message)


class GTMStore:
    def __init__(self, path=None, seed=True):
        self.path = Path(path) if path else default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure(seed)

    # ------------------------------------------------------------------ plumbing
    @contextmanager
    def tx(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        except BaseException:
            con.rollback()
            raise
        finally:
            con.close()

    def _ensure(self, seed):
        with self.tx() as con:
            con.executescript(schema.DDL)
            seeded = con.execute("SELECT value FROM meta WHERE key='seeded_at'").fetchone()
        if not seeded and seed:
            from gtm import seed as seeding
            seeding.seed_demo(self)

    def reset_demo(self, confirm=False):
        """Drop and rebuild THIS demo database from the synthetic seed. Requires confirm=True."""
        if confirm is not True:
            raise ValidationError("Resetting the demo store requires explicit confirmation.")
        with self.tx() as con:
            con.execute("PRAGMA foreign_keys = OFF")
            tables = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for t in tables:
                con.execute(f'DROP TABLE IF EXISTS "{t}"')
        self._ensure(seed=True)

    def df(self, sql, params=()):
        con = sqlite3.connect(self.path)
        try:
            return pd.read_sql_query(sql, con, params=params)
        finally:
            con.close()

    def get(self, table, key_col, key):
        with self.tx() as con:
            row = con.execute(f'SELECT * FROM "{table}" WHERE "{key_col}" = ?', (key,)).fetchone()
            return dict(row) if row else None

    @staticmethod
    def _next_id(con, table, col, prefix, width=0, start=1):
        row = con.execute(f'SELECT MAX(CAST(SUBSTR("{col}", ?) AS INTEGER)) FROM "{table}" WHERE "{col}" LIKE ?',
                          (len(prefix) + 1, prefix + "%")).fetchone()
        n = (row[0] or (start - 1)) + 1
        return f"{prefix}{n:0{width}d}" if width else f"{prefix}{n}"

    @staticmethod
    def _audit(con, table, row_id, action, changes=None, actor="demo"):
        con.execute("INSERT INTO audit_log (ts, table_name, row_id, action, changes_json, actor) VALUES (?,?,?,?,?,?)",
                    (_ts(), table, str(row_id), action, json.dumps(changes, default=str) if changes else None, actor))

    @staticmethod
    def _need(con, table, col, key, label):
        row = con.execute(f'SELECT * FROM "{table}" WHERE "{col}" = ?', (key,)).fetchone()
        if row is None:
            raise ValidationError(f"{label} {key!r} does not exist.")
        return row

    # ------------------------------------------------------------------ reads
    def accounts(self):
        return self.df("SELECT * FROM accounts ORDER BY account_id")

    def prospects(self):
        return self.df("SELECT p.*, a.account_name, a.customer_segment, a.hq_region FROM prospects p "
                       "JOIN accounts a ON a.account_id = p.account_id ORDER BY p.prospect_id")

    def follow_ups(self, prospect_id=None):
        sql = ("SELECT f.*, p.full_name, p.account_id, p.sequence_status, a.account_name FROM follow_ups f "
               "JOIN prospects p ON p.prospect_id = f.prospect_id JOIN accounts a ON a.account_id = p.account_id")
        if prospect_id:
            return self.df(sql + " WHERE f.prospect_id = ? ORDER BY f.seq_no", (prospect_id,))
        return self.df(sql + " ORDER BY f.due_date, f.followup_id")

    def activities(self, prospect_id=None):
        sql = ("SELECT o.*, p.full_name, a.account_name FROM outreach_activities o "
               "JOIN prospects p ON p.prospect_id = o.prospect_id JOIN accounts a ON a.account_id = o.account_id")
        if prospect_id:
            return self.df(sql + " WHERE o.prospect_id = ? ORDER BY o.performed_at", (prospect_id,))
        return self.df(sql + " ORDER BY o.performed_at DESC, o.activity_id DESC")

    def opportunities(self):
        return self.df("SELECT o.*, a.account_name FROM opportunities o JOIN accounts a ON a.account_id = o.account_id ORDER BY o.opportunity_id")

    def targets(self):
        return self.df("SELECT * FROM targets ORDER BY month, owner")

    def kyc_profile(self, account_id):
        row = self.get("kyc_profiles", "account_id", account_id)
        return (kyc.clean(json.loads(row["data_json"])), row["completeness"]) if row else (kyc.clean({}), 0.0)

    def kyc_completeness(self):
        return self.df("SELECT account_id, completeness FROM kyc_profiles")

    def audit(self, limit=200):
        return self.df("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (int(limit),))

    def counts(self):
        with self.tx() as con:
            return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
                    for t in ("accounts", "prospects", "follow_ups", "outreach_activities", "opportunities", "kyc_profiles", "audit_log")}

    # ------------------------------------------------------------------ accounts
    def add_account(self, data, actor="demo"):
        name = v.text(data.get("account_name"), 200)
        checks = [lambda: _fail("Account name is required.") if not name else None]
        for field, vocab, label in (("customer_segment", schema.SEGMENTS, "Customer segment"), ("hq_region", schema.REGIONS, "HQ region"),
                                    ("owner", schema.SDRS, "Owner (SDR)"), ("company_size", schema.COMPANY_SIZES, "Company size")):
            if v.text(data.get(field)):
                checks.append(lambda f=field, vo=vocab, lb=label: v.one_of(data.get(f), vo, lb))
        status = v.text(data.get("status")) or "Not Started"
        checks.append(lambda: v.one_of(status, schema.ACCOUNT_STATUSES, "Status"))
        icp = None
        if str(data.get("icp_score", "")).strip() != "":
            checks.append(lambda: v.to_number(data.get("icp_score"), "ICP score", 0, 100))
        v.collect(checks)
        key = v.name_key(name)
        if not key:
            raise ValidationError("Account name must contain letters or numbers.")
        with self.tx() as con:
            dup = con.execute("SELECT account_id, account_name FROM accounts WHERE name_key = ?", (key,)).fetchone()
            if dup:
                raise ValidationError(f"Duplicate: an account named {dup['account_name']!r} already exists ({dup['account_id']}).")
            if str(data.get("icp_score", "")).strip() != "":
                icp = int(v.to_number(data.get("icp_score"), "ICP score", 0, 100))
            aid = self._next_id(con, "accounts", "account_id", "ACC-", start=101)
            now = _ts()
            con.execute("INSERT INTO accounts (account_id, account_name, name_key, industry, customer_segment, hq_region, company_size, icp_score,"
                        " decision_maker_persona, owner, status, notes, source, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (aid, name, key, v.text(data.get("industry"), 120) or None, v.text(data.get("customer_segment")) or None,
                         v.text(data.get("hq_region")) or None, v.text(data.get("company_size")) or None, icp,
                         v.text(data.get("decision_maker_persona"), 120) or None, v.text(data.get("owner")) or None, status,
                         v.text(data.get("notes"), 1000) or None, v.text(data.get("source"), 120) or "Manual entry", now, now))
            self._audit(con, "accounts", aid, "insert", {"account_name": name}, actor)
        return aid

    ACCOUNT_EDITABLE = ("account_name", "industry", "customer_segment", "hq_region", "company_size", "icp_score",
                        "decision_maker_persona", "owner", "status", "notes")

    def update_account(self, account_id, changes, actor="demo"):
        changes = {k: val for k, val in changes.items() if k in self.ACCOUNT_EDITABLE}
        if not changes:
            raise ValidationError("Nothing to update.")
        with self.tx() as con:
            old = dict(self._need(con, "accounts", "account_id", account_id, "Account"))
            clean, checks = {}, []
            for field, vocab, label in (("customer_segment", schema.SEGMENTS, "Customer segment"), ("hq_region", schema.REGIONS, "HQ region"),
                                        ("owner", schema.SDRS, "Owner (SDR)"), ("company_size", schema.COMPANY_SIZES, "Company size"),
                                        ("status", schema.ACCOUNT_STATUSES, "Status")):
                if field in changes:
                    if v.text(changes[field]) or field == "status":
                        checks.append(lambda f=field, vo=vocab, lb=label: clean.__setitem__(f, v.one_of(changes[f], vo, lb)))
                    else:
                        clean[field] = None
            if "icp_score" in changes:
                if str(changes["icp_score"]).strip() == "":
                    clean["icp_score"] = None
                else:
                    checks.append(lambda: clean.__setitem__("icp_score", int(v.to_number(changes["icp_score"], "ICP score", 0, 100))))
            for field, n in (("industry", 120), ("decision_maker_persona", 120), ("notes", 1000)):
                if field in changes:
                    clean[field] = v.text(changes[field], n) or None
            if "account_name" in changes:
                name = v.text(changes["account_name"], 200)
                if not name or not v.name_key(name):
                    checks.append(lambda: _fail("Account name is required."))
                else:
                    clean["account_name"], clean["name_key"] = name, v.name_key(name)
            v.collect(checks)
            if "name_key" in clean:
                dup = con.execute("SELECT account_id FROM accounts WHERE name_key = ? AND account_id <> ?", (clean["name_key"], account_id)).fetchone()
                if dup:
                    raise ValidationError(f"Duplicate: another account ({dup['account_id']}) already has that name.")
            diff = {k: [old.get(k), val] for k, val in clean.items() if old.get(k) != val and k != "name_key"}
            if not diff:
                return False
            sets = ", ".join(f'"{k}" = ?' for k in clean) + ", updated_at = ?"
            con.execute(f"UPDATE accounts SET {sets} WHERE account_id = ?", (*clean.values(), _ts(), account_id))
            for field in ("customer_segment", "hq_region"):                        # keep denormalised opportunity fields in step
                if field in clean:
                    con.execute(f"UPDATE opportunities SET {field} = ?, updated_at = ? WHERE account_id = ?", (clean[field], _ts(), account_id))
            self._audit(con, "accounts", account_id, "update", diff, actor)
        return True

    # ------------------------------------------------------------------ prospects
    def _dedupe_prospect(self, con, email, linkedin, account_id, full_name, exclude=None):
        ek, lk = v.email_key(email), v.linkedin_key(linkedin)
        for col, key, label in (("email_key", ek, "email"), ("linkedin_key", lk, "LinkedIn profile")):
            if key:
                row = con.execute(f"SELECT prospect_id, full_name FROM prospects WHERE {col} = ? AND prospect_id <> ?", (key, exclude or "")).fetchone()
                if row:
                    raise ValidationError(f"Duplicate: that {label} already belongs to {row['full_name']} ({row['prospect_id']}).")
        row = con.execute("SELECT prospect_id FROM prospects WHERE account_id = ? AND LOWER(full_name) = ? AND prospect_id <> ?",
                          (account_id, full_name.lower(), exclude or "")).fetchone()
        if row:
            raise ValidationError(f"Duplicate: a prospect named {full_name!r} already exists at this account ({row['prospect_id']}).")
        return ek, lk

    def add_prospect(self, data, actor="demo"):
        name = v.text(data.get("full_name"), 120)
        email, linkedin = v.text(data.get("email"), 200), v.text(data.get("linkedin_url"), 300)
        checks = [lambda: _fail("Full name is required.") if not name else None,
                  lambda: _fail("Account is required.") if not v.text(data.get("account_id")) else None,
                  lambda: _fail("Email is not valid.") if email and not v.valid_email(email) else None,
                  lambda: _fail("LinkedIn URL must be a linkedin.com profile link.") if linkedin and not v.linkedin_key(linkedin) else None]
        for field, vocab, label, default in (("lead_temperature", schema.TEMPERATURES, "Lead temperature", "Cold"),
                                             ("response_status", schema.RESPONSE_STATUSES, "Response status", "No response"),
                                             ("qualification_status", schema.QUALIFICATIONS, "Qualification", "Unqualified"),
                                             ("lead_source", schema.LEAD_SOURCES, "Lead source", "Outbound SDR")):
            checks.append(lambda f=field, vo=vocab, lb=label, d=default: v.one_of(data.get(f) or d, vo, lb))
        if v.text(data.get("owner")):
            checks.append(lambda: v.one_of(data.get("owner"), schema.SDRS, "Owner (SDR)"))
        v.collect(checks)
        with self.tx() as con:
            acct = self._need(con, "accounts", "account_id", v.text(data.get("account_id")), "Account")
            ek, lk = self._dedupe_prospect(con, email, linkedin, acct["account_id"], name)
            pid = self._next_id(con, "prospects", "prospect_id", "PRO-", start=3001)
            response = data.get("response_status") or "No response"
            now = _ts()
            con.execute("INSERT INTO prospects (prospect_id, account_id, full_name, title, email, email_key, linkedin_url, linkedin_key, phone, owner,"
                        " lead_source, lead_temperature, response_status, qualification_status, sequence_status, created_at, updated_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (pid, acct["account_id"], name, v.text(data.get("title"), 120) or None, email or None, ek, linkedin or None, lk,
                         v.text(data.get("phone"), 40) or None, v.text(data.get("owner")) or acct["owner"],
                         data.get("lead_source") or "Outbound SDR", data.get("lead_temperature") or "Cold", response,
                         data.get("qualification_status") or "Unqualified", schema.SEQUENCE_ACTIVE, now, now))
            self._audit(con, "prospects", pid, "insert", {"full_name": name, "account_id": acct["account_id"]}, actor)
            if response in schema.RESPONSE_STOPS:
                self._stop(con, pid, schema.RESPONSE_STOPS[response], actor)
        return pid

    PROSPECT_EDITABLE = ("full_name", "title", "email", "linkedin_url", "phone", "owner", "lead_source",
                         "lead_temperature", "response_status", "qualification_status")

    def update_prospect(self, prospect_id, changes, actor="demo"):
        changes = {k: val for k, val in changes.items() if k in self.PROSPECT_EDITABLE}
        if not changes:
            raise ValidationError("Nothing to update.")
        with self.tx() as con:
            old = dict(self._need(con, "prospects", "prospect_id", prospect_id, "Prospect"))
            clean, checks = {}, []
            for field, vocab, label in (("lead_temperature", schema.TEMPERATURES, "Lead temperature"), ("response_status", schema.RESPONSE_STATUSES, "Response status"),
                                        ("qualification_status", schema.QUALIFICATIONS, "Qualification"), ("lead_source", schema.LEAD_SOURCES, "Lead source"),
                                        ("owner", schema.SDRS, "Owner (SDR)")):
                if field in changes:
                    checks.append(lambda f=field, vo=vocab, lb=label: clean.__setitem__(f, v.one_of(changes[f], vo, lb)))
            if "full_name" in changes:
                n = v.text(changes["full_name"], 120)
                checks.append(lambda: _fail("Full name is required.") if not n else clean.__setitem__("full_name", n))
            for field, n in (("title", 120), ("phone", 40)):
                if field in changes:
                    clean[field] = v.text(changes[field], n) or None
            if "email" in changes:
                e = v.text(changes["email"], 200)
                checks.append(lambda: _fail("Email is not valid.") if e and not v.valid_email(e) else clean.__setitem__("email", e or None))
            if "linkedin_url" in changes:
                u = v.text(changes["linkedin_url"], 300)
                checks.append(lambda: _fail("LinkedIn URL must be a linkedin.com profile link.") if u and not v.linkedin_key(u) else clean.__setitem__("linkedin_url", u or None))
            v.collect(checks)
            new_response = clean.get("response_status", old["response_status"])
            if old["stop_reason"] == schema.STOP_OPT_OUT and new_response != "Opt-out":
                raise ValidationError("An opt-out is permanent and cannot be reversed here.")
            if any(k in clean for k in ("email", "linkedin_url", "full_name")):
                ek, lk = self._dedupe_prospect(con, clean.get("email", old["email"]), clean.get("linkedin_url", old["linkedin_url"]),
                                               old["account_id"], clean.get("full_name", old["full_name"]), exclude=prospect_id)
                clean["email_key"], clean["linkedin_key"] = ek, lk
            diff = {k: [old.get(k), val] for k, val in clean.items() if old.get(k) != val and k not in ("email_key", "linkedin_key")}
            if not diff:
                return False
            sets = ", ".join(f'"{k}" = ?' for k in clean) + ", updated_at = ?"
            con.execute(f"UPDATE prospects SET {sets} WHERE prospect_id = ?", (*clean.values(), _ts(), prospect_id))
            self._audit(con, "prospects", prospect_id, "update", diff, actor)
            if "response_status" in diff and new_response in schema.RESPONSE_STOPS:
                self._stop(con, prospect_id, schema.RESPONSE_STOPS[new_response], actor)
        return True

    # ------------------------------------------------------------------ sequence control (stop rules)
    def _stop(self, con, prospect_id, reason, actor="demo", detail=""):
        row = dict(self._need(con, "prospects", "prospect_id", prospect_id, "Prospect"))
        if row["sequence_status"] == schema.SEQUENCE_STOPPED and not (reason == schema.STOP_OPT_OUT and row["stop_reason"] != schema.STOP_OPT_OUT):
            return False                                                            # already stopped; opt-out may upgrade the reason
        now = _ts()
        con.execute("UPDATE prospects SET sequence_status = ?, stop_reason = ?, stopped_at = COALESCE(stopped_at, ?), updated_at = ? WHERE prospect_id = ?",
                    (schema.SEQUENCE_STOPPED, reason, now, now, prospect_id))
        cancelled = con.execute("UPDATE follow_ups SET status = 'Cancelled', notes = TRIM(COALESCE(notes, '') || ' [Cancelled: sequence stopped - ' || ? || ']'), "
                                "updated_at = ? WHERE prospect_id = ? AND status = 'Pending'", (reason, now, prospect_id)).rowcount
        self._audit(con, "prospects", prospect_id, "stop_sequence", {"reason": reason, "detail": detail, "follow_ups_cancelled": cancelled}, actor)
        return True

    def stop_sequence(self, prospect_id, reason, actor="demo"):
        v.one_of(reason, schema.STOP_REASONS, "Stop reason")
        with self.tx() as con:
            return self._stop(con, prospect_id, reason, actor)

    def restart_sequence(self, prospect_id, confirm=False, actor="demo"):
        if confirm is not True:
            raise ValidationError("Restarting a stopped sequence requires explicit confirmation.")
        with self.tx() as con:
            row = dict(self._need(con, "prospects", "prospect_id", prospect_id, "Prospect"))
            if row["sequence_status"] != schema.SEQUENCE_STOPPED:
                raise ValidationError("This sequence is not stopped.")
            if row["stop_reason"] == schema.STOP_OPT_OUT:
                raise ValidationError("An opt-out is permanent: this prospect must not be contacted again.")
            response = "Replied" if row["response_status"] == "Not interested" else row["response_status"]
            con.execute("UPDATE prospects SET sequence_status = 'Active', stop_reason = NULL, stopped_at = NULL, response_status = ?, updated_at = ? "
                        "WHERE prospect_id = ?", (response, _ts(), prospect_id))
            self._audit(con, "prospects", prospect_id, "restart_sequence", {"was": row["stop_reason"]}, actor)

    def _need_active(self, con, prospect_id):
        row = dict(self._need(con, "prospects", "prospect_id", prospect_id, "Prospect"))
        if row["sequence_status"] != schema.SEQUENCE_ACTIVE:
            raise ValidationError(f"Outreach is stopped for {row['full_name']} ({row['stop_reason']}). No new touches or follow-ups are allowed.")
        return row

    # ------------------------------------------------------------------ channels, follow-ups, activities
    def start_sequence(self, prospect_id, anchor=None, actor="demo"):
        with self.tx() as con:
            return self._start_sequence(con, prospect_id, anchor, actor, strict=True)

    def _start_sequence(self, con, prospect_id, anchor, actor, strict=False):
        row = self._need_active(con, prospect_id)
        if con.execute("SELECT 1 FROM follow_ups WHERE prospect_id = ? AND is_standard = 1", (prospect_id,)).fetchone():
            if strict:
                raise ValidationError("The standard follow-ups already exist for this prospect.")
            return []
        base = v.to_date(anchor, "Anchor date") if anchor else _today()
        ids, now = [], _ts()
        for seq, (days, channel) in enumerate(schema.STANDARD_FOLLOWUPS, 1):
            fid = self._next_id(con, "follow_ups", "followup_id", "FU-", 6)
            con.execute("INSERT INTO follow_ups (followup_id, prospect_id, seq_no, is_standard, due_date, channel, status, outcome, owner, created_at, updated_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?)", (fid, prospect_id, seq, 1, (base + timedelta(days=days)).isoformat(), channel,
                                                            "Pending", "Pending", row["owner"], now, now))
            ids.append(fid)
        self._audit(con, "follow_ups", prospect_id, "start_sequence", {"created": ids, "anchor": base.isoformat()}, actor)
        return ids

    def set_channel(self, prospect_id, channel, done, actor="demo"):
        v.one_of(channel, schema.CHANNELS, "Channel")
        col = schema.CHANNEL_COLUMN[channel]
        with self.tx() as con:
            row = dict(self._need(con, "prospects", "prospect_id", prospect_id, "Prospect"))
            if done:
                self._need_active(con, prospect_id)
                if row[col]:
                    return False
                stamp = _ts()
                con.execute(f"UPDATE prospects SET {col} = ?, updated_at = ? WHERE prospect_id = ?", (stamp, stamp, prospect_id))
                aid = self._next_id(con, "outreach_activities", "activity_id", "ACT-", 6)
                con.execute("INSERT INTO outreach_activities (activity_id, prospect_id, account_id, owner, channel, kind, performed_at, outcome, notes, created_at)"
                            " VALUES (?,?,?,?,?,?,?,?,?,?)", (aid, prospect_id, row["account_id"], row["owner"], channel, "first_touch", stamp, "Done", None, stamp))
                self._audit(con, "prospects", prospect_id, "channel_on", {"channel": channel, "at": stamp}, actor)
                self._start_sequence(con, prospect_id, v.to_date(stamp[:10]), actor)       # the first touch starts the standard sequence
            else:
                if not row[col]:
                    return False
                con.execute(f"UPDATE prospects SET {col} = NULL, updated_at = ? WHERE prospect_id = ?", (_ts(), prospect_id))
                con.execute("DELETE FROM outreach_activities WHERE activity_id = (SELECT activity_id FROM outreach_activities "
                            "WHERE prospect_id = ? AND channel = ? AND kind = 'first_touch' ORDER BY performed_at DESC LIMIT 1)", (prospect_id, channel))
                self._audit(con, "prospects", prospect_id, "channel_off", {"channel": channel, "was": row[col]}, actor)
        return True

    def add_followup(self, prospect_id, due_date, channel, notes="", owner=None, actor="demo"):
        v.collect([lambda: v.to_date(due_date, "Due date"), lambda: v.one_of(channel, schema.CHANNELS, "Channel")]
                  + ([lambda: v.one_of(owner, schema.SDRS, "Owner (SDR)")] if owner else []))
        with self.tx() as con:
            row = self._need_active(con, prospect_id)
            seq = (con.execute("SELECT MAX(seq_no) FROM follow_ups WHERE prospect_id = ?", (prospect_id,)).fetchone()[0] or 0) + 1
            fid = self._next_id(con, "follow_ups", "followup_id", "FU-", 6)
            now = _ts()
            con.execute("INSERT INTO follow_ups (followup_id, prospect_id, seq_no, is_standard, due_date, channel, status, outcome, notes, owner, created_at, updated_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", (fid, prospect_id, seq, 0, v.to_date(due_date).isoformat(), channel, "Pending", "Pending",
                                                              v.text(notes, 1000) or None, owner or row["owner"], now, now))
            self._audit(con, "follow_ups", fid, "insert", {"prospect_id": prospect_id, "extra": True}, actor)
        return fid

    FOLLOWUP_EDITABLE = ("status", "outcome", "notes", "due_date", "channel", "owner")

    def update_followup(self, followup_id, changes, actor="demo"):
        changes = {k: val for k, val in changes.items() if k in self.FOLLOWUP_EDITABLE}
        if not changes:
            raise ValidationError("Nothing to update.")
        with self.tx() as con:
            old = dict(self._need(con, "follow_ups", "followup_id", followup_id, "Follow-up"))
            pros = dict(self._need(con, "prospects", "prospect_id", old["prospect_id"], "Prospect"))
            if old["status"] != "Pending":
                if set(changes) - {"notes"}:
                    raise ValidationError(f"This follow-up is {old['status']}; only its notes can be edited.")
                con.execute("UPDATE follow_ups SET notes = ?, updated_at = ? WHERE followup_id = ?", (v.text(changes["notes"], 1000) or None, _ts(), followup_id))
                self._audit(con, "follow_ups", followup_id, "update", {"notes": [old["notes"], changes["notes"]]}, actor)
                return True
            if pros["sequence_status"] != schema.SEQUENCE_ACTIVE:
                raise ValidationError(f"Outreach is stopped for {pros['full_name']} ({pros['stop_reason']}).")
            clean, checks = {}, []
            if "status" in changes:
                checks.append(lambda: clean.__setitem__("status", v.one_of(changes["status"], schema.FOLLOWUP_STATUSES, "Status")))
            if "outcome" in changes:
                checks.append(lambda: clean.__setitem__("outcome", v.one_of(changes["outcome"], schema.FOLLOWUP_OUTCOMES, "Outcome")))
            if "channel" in changes:
                checks.append(lambda: clean.__setitem__("channel", v.one_of(changes["channel"], schema.CHANNELS, "Channel")))
            if "owner" in changes:
                checks.append(lambda: clean.__setitem__("owner", v.one_of(changes["owner"], schema.SDRS, "Owner (SDR)")))
            if "due_date" in changes:
                checks.append(lambda: clean.__setitem__("due_date", v.to_date(changes["due_date"], "Due date").isoformat()))
            if "notes" in changes:
                clean["notes"] = v.text(changes["notes"], 1000) or None
            v.collect(checks)
            status, outcome = clean.get("status", old["status"]), clean.get("outcome", old["outcome"])
            if status == "Done" and outcome == "Pending":
                raise ValidationError("Choose an outcome before marking a follow-up Done.")
            if status != "Done" and outcome != "Pending" and "outcome" in clean and status == "Pending":
                status = clean["status"] = "Done"                                     # an outcome means it happened
            now = _ts()
            if status == "Done":
                clean["completed_at"] = now
            sets = ", ".join(f'"{k}" = ?' for k in clean) + ", updated_at = ?"
            con.execute(f"UPDATE follow_ups SET {sets} WHERE followup_id = ?", (*clean.values(), now, followup_id))
            self._audit(con, "follow_ups", followup_id, "update", {k: [old.get(k), val] for k, val in clean.items() if old.get(k) != val}, actor)
            if status == "Done":
                aid = self._next_id(con, "outreach_activities", "activity_id", "ACT-", 6)
                con.execute("INSERT INTO outreach_activities (activity_id, prospect_id, account_id, owner, channel, kind, followup_id, performed_at, outcome, notes, created_at)"
                            " VALUES (?,?,?,?,?,?,?,?,?,?,?)", (aid, old["prospect_id"], pros["account_id"], clean.get("owner", old["owner"]),
                                                                clean.get("channel", old["channel"]), "follow_up", followup_id, now, outcome,
                                                                clean.get("notes", old["notes"]), now))
                self._apply_outcome(con, old["prospect_id"], outcome, actor)
        return True

    def _apply_outcome(self, con, prospect_id, outcome, actor):
        effect = schema.OUTCOME_EFFECTS.get(outcome)
        if not effect:
            return
        response, floor, stop = effect
        row = dict(self._need(con, "prospects", "prospect_id", prospect_id, "Prospect"))
        sets = {"response_status": response}
        if floor and schema.TEMPERATURES.index(row["lead_temperature"]) < schema.TEMPERATURES.index(floor):
            sets["lead_temperature"] = floor
        con.execute("UPDATE prospects SET " + ", ".join(f"{k} = ?" for k in sets) + ", updated_at = ? WHERE prospect_id = ?", (*sets.values(), _ts(), prospect_id))
        self._audit(con, "prospects", prospect_id, "outcome_effect", {"outcome": outcome, **sets}, actor)
        if stop:
            self._stop(con, prospect_id, stop, actor, detail=f"follow-up outcome: {outcome}")

    def log_activity(self, prospect_id, channel, outcome="", notes="", performed_at=None, actor="demo"):
        v.collect([lambda: v.one_of(channel, schema.CHANNELS, "Channel")] + ([lambda: v.to_date(performed_at, "Date")] if performed_at else []))
        with self.tx() as con:
            row = self._need_active(con, prospect_id)
            aid = self._next_id(con, "outreach_activities", "activity_id", "ACT-", 6)
            stamp = f"{v.to_date(performed_at).isoformat()} {_ts()[11:]}" if performed_at else _ts()
            con.execute("INSERT INTO outreach_activities (activity_id, prospect_id, account_id, owner, channel, kind, performed_at, outcome, notes, created_at)"
                        " VALUES (?,?,?,?,?,?,?,?,?,?)", (aid, prospect_id, row["account_id"], row["owner"], channel, "manual", stamp,
                                                         v.text(outcome, 120) or None, v.text(notes, 1000) or None, _ts()))
            self._audit(con, "outreach_activities", aid, "insert", {"prospect_id": prospect_id, "channel": channel}, actor)
        return aid

    # ------------------------------------------------------------------ opportunities
    @staticmethod
    def _money(deal_value, margin_pct):
        revenue = round(deal_value)
        gp = round(revenue * margin_pct / 100)
        return revenue, revenue - gp, gp

    def add_opportunity(self, data, actor="demo"):
        name = v.text(data.get("name"), 200)
        checks = [lambda: _fail("Opportunity name is required.") if not name else None,
                  lambda: _fail("Account is required.") if not v.text(data.get("account_id")) else None,
                  lambda: v.to_number(data.get("deal_value"), "Deal value", 1),
                  lambda: v.to_number(data.get("gp_margin_pct", 40), "GP margin %", 0, 100),
                  lambda: v.one_of(data.get("stage") or "Prospecting", schema.OPEN_STAGES, "Stage (new opportunities must be open)"),
                  lambda: v.one_of(data.get("service_capability"), schema.CAPABILITIES, "Service capability"),
                  lambda: v.one_of(data.get("modality"), schema.MODALITIES, "Modality")]
        if v.text(data.get("owner")):
            checks.append(lambda: v.one_of(data.get("owner"), schema.SDRS, "Owner (SDR)"))
        if v.text(data.get("expected_close_date")):
            checks.append(lambda: v.to_date(data.get("expected_close_date"), "Expected close date"))
        if str(data.get("close_probability", "")).strip() != "":
            checks.append(lambda: v.to_number(data.get("close_probability"), "Close probability", 0, 1))
        v.collect(checks)
        stage = data.get("stage") or "Prospecting"
        value = v.to_number(data.get("deal_value"), "Deal value", 1)
        prob = v.to_number(data["close_probability"], "Close probability", 0, 1) if str(data.get("close_probability", "")).strip() != "" else schema.STAGE_PROBABILITY[stage]
        revenue, cost, gp = self._money(value, v.to_number(data.get("gp_margin_pct", 40), "GP margin %", 0, 100))
        with self.tx() as con:
            acct = self._need(con, "accounts", "account_id", v.text(data.get("account_id")), "Account")
            if v.text(data.get("prospect_id")):
                pr = self._need(con, "prospects", "prospect_id", v.text(data.get("prospect_id")), "Prospect")
                if pr["account_id"] != acct["account_id"]:
                    raise ValidationError("The prospect does not belong to that account.")
            key = v.name_key(name)
            dup = con.execute("SELECT opportunity_id FROM opportunities WHERE account_id = ? AND name_key = ?", (acct["account_id"], key)).fetchone()
            if dup:
                raise ValidationError(f"Duplicate: this account already has an opportunity with that name ({dup['opportunity_id']}).")
            oid = self._next_id(con, "opportunities", "opportunity_id", "OPP-", start=1001)
            now = _ts()
            con.execute("INSERT INTO opportunities (opportunity_id, account_id, prospect_id, name, name_key, owner, stage, deal_value, close_probability, expected_revenue,"
                        " expected_delivery_cost, expected_gross_profit, service_capability, modality, customer_segment, hq_region, expected_close_date,"
                        " last_activity_date, next_action, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (oid, acct["account_id"], v.text(data.get("prospect_id")) or None, name, key, v.text(data.get("owner")) or acct["owner"], stage, value, prob,
                         revenue, cost, gp, data["service_capability"], data["modality"], acct["customer_segment"], acct["hq_region"],
                         v.to_date(data["expected_close_date"]).isoformat() if v.text(data.get("expected_close_date")) else None,
                         _today().isoformat(), v.text(data.get("next_action"), 300) or None, now, now))
            self._audit(con, "opportunities", oid, "insert", {"name": name, "deal_value": value}, actor)
        return oid

    OPP_EDITABLE = ("name", "owner", "stage", "deal_value", "close_probability", "gp_margin_pct", "service_capability", "modality",
                    "expected_close_date", "next_action", "outcome_reason", "prospect_id")

    def update_opportunity(self, opportunity_id, changes, actor="demo"):
        changes = {k: val for k, val in changes.items() if k in self.OPP_EDITABLE}
        if not changes:
            raise ValidationError("Nothing to update.")
        with self.tx() as con:
            old = dict(self._need(con, "opportunities", "opportunity_id", opportunity_id, "Opportunity"))
            clean, checks = {}, []
            for field, vocab, label in (("stage", schema.STAGES, "Stage"), ("owner", schema.SDRS, "Owner (SDR)"),
                                        ("service_capability", schema.CAPABILITIES, "Service capability"), ("modality", schema.MODALITIES, "Modality")):
                if field in changes:
                    checks.append(lambda f=field, vo=vocab, lb=label: clean.__setitem__(f, v.one_of(changes[f], vo, lb)))
            if "name" in changes:
                n = v.text(changes["name"], 200)
                checks.append(lambda: _fail("Opportunity name is required.") if not n else clean.update(name=n, name_key=v.name_key(n)))
            if "deal_value" in changes:
                checks.append(lambda: clean.__setitem__("deal_value", v.to_number(changes["deal_value"], "Deal value", 1)))
            if "close_probability" in changes and str(changes["close_probability"]).strip() != "":
                checks.append(lambda: clean.__setitem__("close_probability", v.to_number(changes["close_probability"], "Close probability", 0, 1)))
            if "gp_margin_pct" in changes:
                checks.append(lambda: clean.__setitem__("gp_margin_pct", v.to_number(changes["gp_margin_pct"], "GP margin %", 0, 100)))
            if "expected_close_date" in changes:
                checks.append(lambda: clean.__setitem__("expected_close_date", v.to_date(changes["expected_close_date"], "Expected close date").isoformat()
                                                        if v.text(changes["expected_close_date"]) else None))
            for field, n in (("next_action", 300), ("outcome_reason", 300)):
                if field in changes:
                    clean[field] = v.text(changes[field], n) or None
            if "prospect_id" in changes:
                clean["prospect_id"] = v.text(changes["prospect_id"]) or None
            v.collect(checks)
            if clean.get("prospect_id"):
                pr = self._need(con, "prospects", "prospect_id", clean["prospect_id"], "Prospect")
                if pr["account_id"] != old["account_id"]:
                    raise ValidationError("The prospect does not belong to this opportunity's account.")
            if "name_key" in clean:
                dup = con.execute("SELECT opportunity_id FROM opportunities WHERE account_id = ? AND name_key = ? AND opportunity_id <> ?",
                                  (old["account_id"], clean["name_key"], opportunity_id)).fetchone()
                if dup:
                    raise ValidationError(f"Duplicate: this account already has an opportunity with that name ({dup['opportunity_id']}).")
            new_stage = clean.get("stage", old["stage"])
            if "stage" in clean and clean["stage"] != old["stage"] and "close_probability" not in clean:
                clean["close_probability"] = schema.STAGE_PROBABILITY[new_stage]       # a new stage resets to its default probability (as in V1)
            if new_stage in ("Won", "Lost"):
                clean["close_probability"] = schema.STAGE_PROBABILITY[new_stage]       # closed deals are 100% / 0%
            closing = new_stage in ("Won", "Lost") and old["stage"] not in ("Won", "Lost")
            if closing:
                clean["closed_date"] = _today().isoformat()
                if not (clean.get("outcome_reason") or old["outcome_reason"]):
                    clean["outcome_reason"] = "Not recorded"
                clean["expected_close_date"] = clean["closed_date"] if (clean.get("expected_close_date") or old["expected_close_date"] or "9999") > clean["closed_date"] else (clean.get("expected_close_date") or old["expected_close_date"])
            if new_stage not in ("Won", "Lost") and old["stage"] in ("Won", "Lost"):
                clean["closed_date"], clean["outcome_reason"] = None, None             # re-opened
            if {"deal_value", "gp_margin_pct"} & set(changes):
                margin = clean.get("gp_margin_pct", round(100 * old["expected_gross_profit"] / old["expected_revenue"], 2) if old["expected_revenue"] else 40.0)
                value = clean.get("deal_value", old["deal_value"])
                clean["expected_revenue"], clean["expected_delivery_cost"], clean["expected_gross_profit"] = self._money(value, margin)
            clean.pop("gp_margin_pct", None)
            diff = {k: [old.get(k), val] for k, val in clean.items() if old.get(k) != val and k != "name_key"}
            if not diff:
                return False
            clean["last_activity_date"] = _today().isoformat()
            sets = ", ".join(f'"{k}" = ?' for k in clean) + ", updated_at = ?"
            con.execute(f"UPDATE opportunities SET {sets} WHERE opportunity_id = ?", (*clean.values(), _ts(), opportunity_id))
            self._audit(con, "opportunities", opportunity_id, "update", diff, actor)
            if closing:                                                                # closure stops outreach to the whole account
                for p in con.execute("SELECT prospect_id FROM prospects WHERE account_id = ? AND sequence_status = 'Active'", (old["account_id"],)).fetchall():
                    self._stop(con, p["prospect_id"], schema.STOP_CLOSURE, actor, detail=f"{opportunity_id} {new_stage}")
                if new_stage == "Won":
                    con.execute("UPDATE accounts SET status = 'Customer', updated_at = ? WHERE account_id = ?", (_ts(), old["account_id"]))
        return True

    # ------------------------------------------------------------------ KYC
    def save_kyc(self, account_id, data, actor="demo"):
        cleaned = kyc.clean(data)
        review = cleaned.get("last_reviewed")
        if review:
            v.to_date(review, "Last reviewed")
        with self.tx() as con:
            self._need(con, "accounts", "account_id", account_id, "Account")
            old = con.execute("SELECT data_json FROM kyc_profiles WHERE account_id = ?", (account_id,)).fetchone()
            before = json.loads(old["data_json"]) if old else {}
            changed = {k: [before.get(k, ""), cleaned[k]] for k in kyc.KEYS if before.get(k, "") != cleaned[k]}
            if old and not changed:
                return False
            con.execute("INSERT INTO kyc_profiles (account_id, data_json, completeness, updated_at) VALUES (?,?,?,?) "
                        "ON CONFLICT(account_id) DO UPDATE SET data_json = excluded.data_json, completeness = excluded.completeness, updated_at = excluded.updated_at",
                        (account_id, json.dumps(cleaned), kyc.completeness(cleaned), _ts()))
            self._audit(con, "kyc_profiles", account_id, "update" if old else "insert", {"fields": sorted(changed)}, actor)
        return True
