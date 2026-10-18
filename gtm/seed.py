"""Synthetic demo seed for the V2 workspace, built from the V1 demo CSVs through an explicit import mapping.

  * Every original V1 column is preserved verbatim in each row's `orig_json`; mapped columns are also exposed as V2 fields.
  * V1 sales owners are renamed to the V2 SDR team (OWNER_MAP). Nothing is read from, or written to, the V1 database.
  * New V2-only facts (lead temperature, channels, follow-ups, modality, KYC) are generated DETERMINISTICALLY (seeded random),
    so the demo is reproducible. Everything is fictional.
"""
import json
import random
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

import metrics
from gtm import kyc, schema
from gtm import validation as v

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
OWNER_MAP = {"Jon": "Mini", "Sara": "Sue", "Alex": "Harry", "Ryan": "Dips", "Emma": "Emma"}

# V1 CSV column -> V2 field (columns not listed are still kept in orig_json)
ACCOUNT_MAPPING = {"account_id": "account_id", "account_name": "account_name", "industry": "industry", "customer_segment": "customer_segment",
                   "region": "hq_region", "company_size": "company_size", "icp_score": "icp_score", "decision_maker_persona": "decision_maker_persona",
                   "owner": "owner (renamed)", "prospecting_status": "status", "research_rationale": "notes", "source_tool": "source"}
PROSPECT_MAPPING = {"contact_id": "prospect_id (CON- -> PRO-)", "account_id": "account_id", "contact_name": "full_name", "title": "title",
                    "email": "email", "contact_status": "response_status + lead_temperature (derived)"}
OPPORTUNITY_MAPPING = {"opportunity_id": "opportunity_id", "account_id": "account_id", "service_offering": "service_capability", "stage": "stage",
                       "deal_value": "deal_value", "close_probability": "close_probability", "expected_revenue": "expected_revenue",
                       "expected_delivery_cost": "expected_delivery_cost", "expected_gross_profit": "expected_gross_profit",
                       "expected_close_date": "expected_close_date", "last_activity_date": "last_activity_date", "next_action": "next_action",
                       "outcome_reason": "outcome_reason", "lead_id": "prospect_id (via the lead's contact)", "sales_owner": "owner (renamed)"}

MODALITY_WEIGHTS = {
    "Managed AI Programs": (.2, .7, .1), "AI Consulting": (.7, .2, .1), "Annotation and Labeling": (.2, .3, .5),
    "AI Training Data Collection": (.5, .3, .2), "Model Evaluation and Benchmarking": (.6, .2, .2),
    "Multimodal Data Services": (.3, .4, .3), "RLHF and Human-in-the-Loop": (.1, .4, .5), "Robotics and Egocentric Data": (.5, .3, .2)}
CITIES = {"US": ["Austin", "Boston", "Seattle", "Denver"], "Europe": ["Berlin", "Amsterdam", "Dublin", "Stockholm"],
          "LATAM": ["Sao Paulo", "Mexico City", "Bogota", "Santiago"], "APAC": ["Singapore", "Sydney", "Bengaluru", "Tokyo"]}
REVENUE = {"51-200": "$10M-$50M", "201-1,000": "$50M-$200M", "1,001-5,000": "$200M-$1B", "5,001-10,000": "$1B-$5B", "10,000+": "$5B+"}
FICTIONAL_COMPETITORS = ["Brightlabel Data", "Northgrid Annotation", "Quanta Crowd", "Helix Data Ops", "Meridian Labeling"]
STACKS = ["PyTorch, Kubernetes, S3-compatible storage", "JAX, GCP, Airflow", "PyTorch, AWS, Ray", "TensorFlow, Azure, Databricks"]
COMPLIANCE = ["SOC 2 expected; data stays in region", "Strict PII handling; NDA before any sample data", "GDPR; no cross-border transfer of raw data",
              "Standard MSA; security questionnaire required"]


def _insert(con, table, rows):
    if rows:
        con.executemany(f"INSERT INTO {table} VALUES ({','.join('?' * len(rows[0]))})", rows)


def _rng(key):
    return random.Random(f"kai-gtm-v2-seed:{key}")


def _clean(row):
    return {k: (None if pd.isna(x) else (x.item() if hasattr(x, "item") else x)) for k, x in row.items()}


def _dt(day, rnd):
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=rnd.randint(9, 17), minutes=rnd.randint(0, 59))


def _pick(rnd, items, weights):
    return rnd.choices(items, weights=weights, k=1)[0]


def seed_demo(store, data_dir=DATA_DIR):
    d = Path(data_dir)
    accounts, contacts, leads, opps, targets = (pd.read_csv(d / f"{t}.csv") for t in ("accounts", "contacts", "leads", "opportunities", "targets"))
    asof = metrics.AS_OF.to_pydatetime().date()
    ts = datetime.combine(asof, datetime.min.time()).strftime("%Y-%m-%d %H:%M:%S")
    owner = lambda x: OWNER_MAP.get(x, x)

    acc_rows, taken = [], set()
    for _, r in accounts.iterrows():
        row = _clean(r)
        key = v.name_key(row["account_name"])
        if key in taken:
            key = f"{key} {row['account_id']}"
        taken.add(key)
        acc_rows.append((row["account_id"], row["account_name"], key, row["industry"], row["customer_segment"], row["region"], row["company_size"],
                         int(row["icp_score"]) if row["icp_score"] is not None else None, row["decision_maker_persona"], owner(row["owner"]),
                         row["prospecting_status"], row["research_rationale"], row["source_tool"], ts, ts, json.dumps(row, default=str)))
    acct = accounts.set_index("account_id")

    # --- opportunities (needed first: closures stop sequences, KYC reads requested capabilities)
    lead_contact = dict(zip(leads.lead_id, leads.contact_id))
    opp_rows, used_names, closed_accounts = [], set(), set()
    for _, r in opps.iterrows():
        row = _clean(r)
        rnd = _rng(row["opportunity_id"])
        name = f"{row['client_name']} - {row['service_offering']}"
        key = (row["account_id"], v.name_key(name))
        if key in used_names:
            name = f"{name} ({row['opportunity_id']})"
            key = (row["account_id"], v.name_key(name))
        used_names.add(key)
        modality = _pick(rnd, schema.MODALITIES, MODALITY_WEIGHTS[row["service_offering"]])
        pid = lead_contact.get(row["lead_id"])
        closed = row["stage"] in ("Won", "Lost")
        if closed:
            closed_accounts.add(row["account_id"])
        opp_rows.append((row["opportunity_id"], row["account_id"], pid.replace("CON-", "PRO-") if pid else None, name, v.name_key(name), owner(row["sales_owner"]),
                         row["stage"], float(row["deal_value"]), float(row["close_probability"]), float(row["expected_revenue"]),
                         float(row["expected_delivery_cost"]), float(row["expected_gross_profit"]), row["service_offering"], modality,
                         acct.loc[row["account_id"], "customer_segment"], acct.loc[row["account_id"], "region"], row["expected_close_date"],
                         row["expected_close_date"] if closed else None, row["last_activity_date"], row["next_action"], row["outcome_reason"],
                         ts, ts, json.dumps(row, default=str)))

    # --- prospects from contacts (+ aggregated lead facts), then channels, follow-ups, activities
    by_contact = leads.groupby("contact_id")
    pros_rows, fu_rows, act_rows, stops = [], [], [], {}
    fu_n = act_n = 0
    contact_ids = list(contacts.contact_id)
    opt_out_ids = set(_rng("opt-out").sample(contact_ids, 4))
    reject_ids = set(_rng("reject").sample([c for c in contact_ids if c not in opt_out_ids], 5))
    for _, r in contacts.iterrows():
        row = _clean(r)
        cid, pid = row["contact_id"], row["contact_id"].replace("CON-", "PRO-")
        rnd = _rng(cid)
        grp = by_contact.get_group(cid) if cid in by_contact.groups else leads.iloc[0:0]
        qual = "Qualified" if (grp.qualification_status == "Qualified").any() else (
            "Disqualified" if len(grp) and (grp.qualification_status == "Disqualified").all() else "Unqualified")
        source = Counter(grp.lead_source).most_common(1)[0][0] if len(grp) else "Outbound SDR"
        status = row["contact_status"]
        response, temp = {"Not contacted": ("No response", "Cold"),
                          "Contacted": ("No response", _pick(rnd, ["Cold", "Warm"], (1, 1))),
                          "Replied": (_pick(rnd, ["Replied", "Interested"], (1, 1)), _pick(rnd, ["Warm", "Hot"], (3, 2))),
                          "Meeting held": ("Meeting booked", "Hot")}[status]
        if qual == "Qualified" and temp == "Cold":
            temp = "Warm"
        stop_reason = None
        if cid in opt_out_ids:
            response, stop_reason = "Opt-out", schema.STOP_OPT_OUT
        elif cid in reject_ids:
            response, stop_reason = "Not interested", schema.STOP_REJECTION
        elif row["account_id"] in closed_accounts:
            stop_reason = schema.STOP_CLOSURE
        touched = status != "Not contacted" or stop_reason in (schema.STOP_OPT_OUT, schema.STOP_REJECTION)
        owner_name = owner(acct.loc[row["account_id"], "owner"])
        email = row["email"]
        stamps = {"email_sent_at": None, "linkedin_sent_at": None, "call_made_at": None}
        anchor = None
        if touched:
            created = pd.to_datetime(grp.created_date.min()) if len(grp) else pd.to_datetime(acct.loc[row["account_id"], "last_contact_date"])
            anchor = min(created.date() if pd.notna(created) else asof - timedelta(days=30), asof - timedelta(days=2))
            chosen = [c for c, p in zip(schema.CHANNELS, (.75, .5, .3)) if rnd.random() < p] or ["Email"]
            for ch in chosen:
                moment = _dt(anchor + timedelta(days=rnd.randint(0, 1)), rnd)
                stamps[schema.CHANNEL_COLUMN[ch]] = moment.strftime("%Y-%m-%d %H:%M:%S")
                act_n += 1
                act_rows.append((f"ACT-{act_n:06d}", pid, row["account_id"], owner_name, ch, "first_touch", None,
                                 moment.strftime("%Y-%m-%d %H:%M:%S"), "Done", None, ts))
            stopped_at = None
            if stop_reason:
                stopped_at = (_dt(asof - timedelta(days=rnd.randint(1, 12)), rnd)).strftime("%Y-%m-%d %H:%M:%S")
            for seq, (days, ch) in enumerate(schema.STANDARD_FOLLOWUPS, 1):
                due = anchor + timedelta(days=days)
                fu_n += 1
                fid = f"FU-{fu_n:06d}"
                completed = due < asof and rnd.random() < .75 and not (stopped_at and due.isoformat() >= stopped_at[:10])
                if stopped_at and not completed:                                   # a stopped sequence has no pending follow-ups
                    fu_rows.append((fid, pid, seq, 1, due.isoformat(), ch, "Cancelled", "Pending",
                                    f"[Cancelled: sequence stopped - {stop_reason}]", owner_name, None, ts, ts))
                elif completed:
                    outcomes = ["No answer", "Left voicemail", "Replied - neutral"] + (["Replied - positive"] if response in ("Replied", "Interested", "Meeting booked") else [])
                    outcome = rnd.choice(outcomes)
                    when = _dt(due, rnd).strftime("%Y-%m-%d %H:%M:%S")
                    fu_rows.append((fid, pid, seq, 1, due.isoformat(), ch, "Done", outcome, None, owner_name, when, ts, ts))
                    act_n += 1
                    act_rows.append((f"ACT-{act_n:06d}", pid, row["account_id"], owner_name, ch, "follow_up", fid, when, outcome, None, ts))
                else:
                    fu_rows.append((fid, pid, seq, 1, due.isoformat(), ch, "Pending", "Pending", None, owner_name, None, ts, ts))
        else:
            stopped_at = (_dt(asof - timedelta(days=rnd.randint(1, 12)), rnd)).strftime("%Y-%m-%d %H:%M:%S") if stop_reason else None
        pros_rows.append((pid, row["account_id"], row["contact_name"], row["title"], email, v.email_key(email), None, None, None, owner_name, source,
                          temp, response, qual, schema.SEQUENCE_STOPPED if stop_reason else schema.SEQUENCE_ACTIVE, stop_reason, stopped_at,
                          stamps["email_sent_at"], stamps["linkedin_sent_at"], stamps["call_made_at"], ts, ts, json.dumps(row, default=str)))

    # --- KYC profiles (derived from the account, its contacts and its opportunities)
    capability_pattern = re.compile("|".join(re.escape(c) for c in schema.CAPABILITIES))
    opps_by_acct = opps.groupby("account_id")
    kyc_rows = []
    for _, r in accounts.iterrows():
        row = _clean(r)
        rnd = _rng("kyc-" + row["account_id"])
        slug = re.sub(r"[^a-z0-9]", "", row["account_name"].lower())
        contacts_here = contacts[contacts.account_id == row["account_id"]]
        caps = list(dict.fromkeys(capability_pattern.findall(row["research_rationale"] or "") +
                                  (list(opps_by_acct.get_group(row["account_id"]).service_offering) if row["account_id"] in opps_by_acct.groups else [])))
        deal = opps_by_acct.get_group(row["account_id"]).iloc[0] if row["account_id"] in opps_by_acct.groups else None
        full = {
            "website": f"www.{slug}.example.com", "hq_city": rnd.choice(CITIES[row["region"]]), "employee_range": row["company_size"],
            "annual_revenue_range": REVENUE[row["company_size"]], "business_model": f"{row['industry']} company (synthetic profile)",
            "primary_contact": f"{contacts_here.iloc[0].contact_name}, {contacts_here.iloc[0].title}" if len(contacts_here) else "",
            "decision_makers": row["decision_maker_persona"], "requested_capabilities": caps,
            "current_vendors": rnd.choice(["In-house team plus one vendor", "Two annotation vendors", "No dedicated vendor yet"]),
            "competitors": ", ".join(rnd.sample(FICTIONAL_COMPETITORS, 2)), "tech_stack": rnd.choice(STACKS),
            "budget_range": (f"${int(deal.deal_value * .8 / 1000)}K-${int(deal.deal_value * 1.2 / 1000)}K" if deal is not None else "Not yet discussed"),
            "buying_timeline": (f"Decision expected around {deal.expected_close_date}" if deal is not None else "Unknown"),
            "compliance_requirements": rnd.choice(COMPLIANCE), "pain_points": row["research_rationale"],
            "trigger_events": "Active programs signalling demand (see pain points)", "icp_fit_notes": f"ICP score {row['icp_score']} of 100.",
            "source": row["source_tool"], "last_reviewed": row["last_contact_date"] or ""}
        fill = 1.0 if row["account_id"] in ("ACC-101", "ACC-102") else rnd.choice([.45, .7, 1.0, 1.0])
        data = {k: (val if (k in ("requested_capabilities",) or rnd.random() < fill) else "") for k, val in full.items()}
        data = kyc.clean(data)
        kyc_rows.append((row["account_id"], json.dumps(data), kyc.completeness(data), ts))

    target_rows = [(owner(r.sales_owner), r.month, float(r.target), float(r.gp_target)) for r in targets.itertuples()]

    with store.tx() as con:
        _insert(con, "accounts", acc_rows)
        _insert(con, "prospects", pros_rows)
        _insert(con, "follow_ups", fu_rows)
        _insert(con, "outreach_activities", act_rows)
        _insert(con, "opportunities", opp_rows)
        _insert(con, "kyc_profiles", kyc_rows)
        _insert(con, "targets", target_rows)
        for key, value in (("schema_version", str(schema.SCHEMA_VERSION)), ("seeded_at", ts), ("source", "V1 demo CSVs via gtm.seed mapping (synthetic)"),
                           ("owner_map", json.dumps(OWNER_MAP))):
            con.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))
        con.execute("INSERT INTO audit_log (ts, table_name, row_id, action, changes_json, actor) VALUES (?,?,?,?,?,?)",
                    (ts, "meta", "seed", "seed", json.dumps({"accounts": len(acc_rows), "prospects": len(pros_rows), "opportunities": len(opp_rows)}), "system"))
