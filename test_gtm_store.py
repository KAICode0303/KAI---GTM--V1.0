"""Tests for the V2 GTM demo store: seed, validation, deduplication, row-level writes, stop rules, follow-ups, audit.
Every test uses a throw-away database in tmp_path; the real demo store and the V1 database are never touched."""
import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

import metrics
from gtm import kyc, schema
from gtm.seed import OWNER_MAP
from gtm.store import GTMStore
from gtm.validation import ValidationError

ROOT = Path(__file__).resolve().parent


@pytest.fixture()
def store(tmp_path):
    return GTMStore(tmp_path / "gtm.db")


def table_hash(store, table, where="1=1"):
    con = sqlite3.connect(store.path)
    try:
        rows = con.execute(f'SELECT * FROM "{table}" WHERE {where} ORDER BY 1, 2').fetchall()
    finally:
        con.close()
    return hashlib.md5(repr(rows).encode()).hexdigest()


def first(store, sql, params=()):
    df = store.df(sql, params)
    assert len(df), f"no row for: {sql}"
    return df.iloc[0]


def untouched_active_prospect(store):
    return first(store, "SELECT * FROM prospects WHERE sequence_status = 'Active' AND email_sent_at IS NULL AND linkedin_sent_at IS NULL "
                        "AND call_made_at IS NULL ORDER BY prospect_id").prospect_id


def active_prospect_with_pending(store):
    return first(store, "SELECT p.prospect_id FROM prospects p WHERE p.sequence_status = 'Active' AND EXISTS "
                        "(SELECT 1 FROM follow_ups f WHERE f.prospect_id = p.prospect_id AND f.status = 'Pending') ORDER BY 1").prospect_id


def account_without_closed_opp(store):
    return first(store, "SELECT a.account_id FROM accounts a WHERE NOT EXISTS (SELECT 1 FROM opportunities o WHERE o.account_id = a.account_id "
                        "AND o.stage IN ('Won','Lost')) AND EXISTS (SELECT 1 FROM prospects p WHERE p.account_id = a.account_id "
                        "AND p.sequence_status = 'Active') ORDER BY 1").account_id


NEW_OPP = dict(name="Atlas pilot", deal_value=250000, service_capability="Annotation and Labeling", modality="Fixed-scope project")


# ---------------------------------------------------------------- seed and import mapping
def test_seed_counts_and_sdr_team(store):
    c = store.counts()
    assert (c["accounts"], c["prospects"], c["opportunities"], c["kyc_profiles"]) == (64, 109, 50, 64)
    assert c["follow_ups"] > 100 and c["outreach_activities"] > 100
    owners = set(store.accounts().owner) | set(store.prospects().owner) | set(store.opportunities().owner) | set(store.targets().owner)
    assert owners == set(schema.SDRS) == {"Mini", "Sue", "Harry", "Dips", "Emma"}
    assert not owners & {"Jon", "Sara", "Alex", "Ryan"}


def test_original_v1_columns_are_preserved_in_orig_json(store):
    v1 = pd.read_csv(ROOT / "data" / "accounts.csv").set_index("account_id")
    for r in store.accounts().itertuples():
        orig = json.loads(r.orig_json)
        for col in v1.columns:
            expected = None if pd.isna(v1.loc[r.account_id, col]) else v1.loc[r.account_id, col]
            assert str(orig[col]) == str(expected) or orig[col] == expected, (r.account_id, col)
    opp = json.loads(store.opportunities().iloc[0].orig_json)
    assert {"sales_owner", "service_offering", "monthly_sales_target", "outcome_reason"} <= set(opp)        # even unmapped columns survive
    assert OWNER_MAP["Ryan"] == "Dips"


def test_opportunity_numbers_match_the_v1_data_exactly(store):
    v1 = pd.read_csv(ROOT / "data" / "opportunities.csv").set_index("opportunity_id")
    for r in store.opportunities().itertuples():
        row = v1.loc[r.opportunity_id]
        assert (r.deal_value, r.expected_gross_profit, r.stage, r.close_probability) == (row.deal_value, row.expected_gross_profit, row.stage, row.close_probability)


def test_seed_integrity_and_stop_rule_consistency(store):
    con = sqlite3.connect(store.path)
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    con.close()
    f = store.follow_ups()
    assert len(f[(f.sequence_status == "Stopped") & (f.status == "Pending")]) == 0          # stopped sequences hold no pending follow-ups
    p = store.prospects()
    assert set(p[p.sequence_status == "Stopped"].stop_reason) <= set(schema.STOP_REASONS)
    assert (p[p.response_status == "Opt-out"].stop_reason == "Opt-out").all()
    assert set(p.lead_temperature) <= set(schema.TEMPERATURES) and set(p.response_status) <= set(schema.RESPONSE_STATUSES)


def test_constructing_the_store_never_touches_the_v1_database():
    v1 = ROOT / "data" / "kai_gtm.db"
    before = hashlib.md5(v1.read_bytes()).hexdigest() if v1.exists() else None
    import tempfile
    GTMStore(Path(tempfile.mkdtemp()) / "x.db")
    assert (hashlib.md5(v1.read_bytes()).hexdigest() if v1.exists() else None) == before


# ---------------------------------------------------------------- accounts
def test_add_account_validates_and_returns_the_next_id(store):
    aid = store.add_account({"account_name": "Nimbus Robotics", "customer_segment": "Robotics and Physical AI Companies", "hq_region": "APAC",
                             "owner": "Mini", "icp_score": "88", "company_size": "201-1,000"})
    row = store.get("accounts", "account_id", aid)
    assert aid == "ACC-165" and row["owner"] == "Mini" and row["icp_score"] == 88 and row["status"] == "Not Started"
    assert store.counts()["accounts"] == 65 and store.audit(1).iloc[0].action == "insert"


def test_account_validation_reports_every_problem_at_once(store):
    with pytest.raises(ValidationError) as exc:
        store.add_account({"account_name": "", "customer_segment": "Nope", "hq_region": "Mars", "owner": "Jon", "icp_score": "250"})
    msgs = " | ".join(exc.value.messages)
    assert len(exc.value.messages) >= 5 and "Account name" in msgs and "Customer segment" in msgs and "HQ region" in msgs and "Owner" in msgs and "ICP" in msgs
    assert store.counts()["accounts"] == 64


@pytest.mark.parametrize("variant", ["Deepcurrent Labs", "deepcurrent labs", "  DEEPCURRENT   LABS  ", "Deepcurrent Labs, Inc.", "Deepcurrent Labs LLC"])
def test_duplicate_account_names_are_rejected_whatever_the_case_spacing_or_suffix(store, variant):
    with pytest.raises(ValidationError, match="Duplicate.*ACC-101"):
        store.add_account({"account_name": variant})
    assert store.counts()["accounts"] == 64


def test_update_account_is_row_level_and_keeps_denormalised_fields_in_step(store):
    others_before = table_hash(store, "accounts", "account_id <> 'ACC-101'")
    prospects_before = table_hash(store, "prospects")
    assert store.update_account("ACC-101", {"hq_region": "APAC", "owner": "Sue", "notes": "  new   note "}) is True
    assert table_hash(store, "accounts", "account_id <> 'ACC-101'") == others_before and table_hash(store, "prospects") == prospects_before
    row = store.get("accounts", "account_id", "ACC-101")
    assert (row["hq_region"], row["owner"], row["notes"]) == ("APAC", "Sue", "new note")
    assert set(store.opportunities().query("account_id == 'ACC-101'").hq_region) == {"APAC"}
    assert store.update_account("ACC-101", {"owner": "Sue"}) is False                        # no change, no write
    with pytest.raises(ValidationError, match="Duplicate"):
        store.update_account("ACC-101", {"account_name": "Tessera Cloud"})
    with pytest.raises(ValidationError, match="does not exist"):
        store.update_account("ACC-999", {"owner": "Sue"})


# ---------------------------------------------------------------- prospects: validation, dedupe, separate statuses
def test_add_prospect_defaults_and_inherits_the_account_owner(store):
    pid = store.add_prospect({"account_id": "ACC-101", "full_name": "Nora Whitfield", "email": "Nora.Whitfield@deepcurrentlabs.example.com"})
    row = store.get("prospects", "prospect_id", pid)
    assert pid == "PRO-3110" and row["owner"] == "Dips"
    assert (row["lead_temperature"], row["response_status"], row["qualification_status"], row["sequence_status"]) == ("Cold", "No response", "Unqualified", "Active")
    assert row["email_key"] == "nora.whitfield@deepcurrentlabs.example.com"


@pytest.mark.parametrize("data, message", [
    ({"full_name": "X Y", "email": "not-an-email"}, "Email is not valid"),
    ({"full_name": "", "email": "a@b.co"}, "Full name"),
    ({"full_name": "X Y", "linkedin_url": "https://example.com/in/x"}, "LinkedIn"),
    ({"full_name": "X Y", "lead_temperature": "Boiling"}, "Lead temperature"),
    ({"full_name": "X Y", "response_status": "Maybe"}, "Response status"),
    ({"full_name": "X Y", "owner": "Jon"}, "Owner"),
])
def test_prospect_validation(store, data, message):
    with pytest.raises(ValidationError, match=message):
        store.add_prospect({"account_id": "ACC-101", **data})
    assert store.counts()["prospects"] == 109


def test_prospect_deduplication_by_email_linkedin_and_name(store):
    existing = first(store, "SELECT * FROM prospects ORDER BY prospect_id")
    with pytest.raises(ValidationError, match="Duplicate.*email"):
        store.add_prospect({"account_id": "ACC-102", "full_name": "Someone New", "email": existing.email.upper()})
    pid = store.add_prospect({"account_id": "ACC-102", "full_name": "Lin Example", "linkedin_url": "https://www.linkedin.com/in/lin-example/?trk=x"})
    for variant in ("linkedin.com/in/lin-example", "HTTPS://LinkedIn.com/in/Lin-Example/"):
        with pytest.raises(ValidationError, match="Duplicate.*LinkedIn"):
            store.add_prospect({"account_id": "ACC-103", "full_name": "Other Person", "linkedin_url": variant})
    with pytest.raises(ValidationError, match="Duplicate.*named"):
        store.add_prospect({"account_id": "ACC-102", "full_name": "lin example"})
    assert store.counts()["prospects"] == 110 and pid


def test_temperature_response_and_qualification_are_independent(store):
    pid = untouched_active_prospect(store)
    before = store.get("prospects", "prospect_id", pid)
    store.update_prospect(pid, {"lead_temperature": "Hot"})
    store.update_prospect(pid, {"qualification_status": "Qualified"})
    store.update_prospect(pid, {"response_status": "Interested"})
    after = store.get("prospects", "prospect_id", pid)
    assert (after["lead_temperature"], after["qualification_status"], after["response_status"]) == ("Hot", "Qualified", "Interested")
    assert before["lead_temperature"] != "Hot" and after["sequence_status"] == "Active"           # none of these touch the others or the sequence
    opp_stage_hash = table_hash(store, "opportunities")
    store.update_prospect(pid, {"lead_temperature": "Warm"})
    assert table_hash(store, "opportunities") == opp_stage_hash                                    # nor the opportunity stage


# ---------------------------------------------------------------- stop rules
def test_opt_out_response_stops_the_sequence_and_cancels_pending_follow_ups(store):
    pid = active_prospect_with_pending(store)
    pending = len(store.follow_ups(pid).query("status == 'Pending'"))
    assert pending > 0
    store.update_prospect(pid, {"response_status": "Opt-out"})
    row = store.get("prospects", "prospect_id", pid)
    assert (row["sequence_status"], row["stop_reason"]) == ("Stopped", "Opt-out") and row["stopped_at"]
    fu = store.follow_ups(pid)
    assert len(fu.query("status == 'Pending'")) == 0 and len(fu.query("status == 'Cancelled'")) >= pending
    assert "stop_sequence" in set(store.audit(10).action)


def test_rejection_stops_too_and_blocks_new_outreach(store):
    pid = active_prospect_with_pending(store)
    store.update_prospect(pid, {"response_status": "Not interested"})
    assert store.get("prospects", "prospect_id", pid)["stop_reason"] == "Rejection"
    for call in (lambda: store.set_channel(pid, "Email", True), lambda: store.add_followup(pid, "2026-11-01", "Call"),
                 lambda: store.log_activity(pid, "Call", "x"), lambda: store.start_sequence(pid)):
        with pytest.raises(ValidationError, match="stopped"):
            call()


def test_opt_out_is_permanent_but_rejection_can_be_restarted_with_confirmation(store):
    pid = active_prospect_with_pending(store)
    store.update_prospect(pid, {"response_status": "Opt-out"})
    with pytest.raises(ValidationError, match="permanent"):
        store.update_prospect(pid, {"response_status": "Replied"})
    with pytest.raises(ValidationError, match="permanent"):
        store.restart_sequence(pid, confirm=True)
    other = first(store, "SELECT prospect_id FROM prospects WHERE sequence_status = 'Stopped' AND stop_reason = 'Rejection' ORDER BY 1").prospect_id
    with pytest.raises(ValidationError, match="confirmation"):
        store.restart_sequence(other)
    store.restart_sequence(other, confirm=True)
    row = store.get("prospects", "prospect_id", other)
    assert row["sequence_status"] == "Active" and row["stop_reason"] is None and row["response_status"] == "Replied"


def test_closing_an_opportunity_stops_every_active_sequence_on_the_account(store):
    aid = account_without_closed_opp(store)
    active = store.prospects().query("account_id == @aid and sequence_status == 'Active'")
    assert len(active)
    store.add_opportunity({"account_id": aid, **NEW_OPP})
    oid = store.opportunities().query("account_id == @aid").iloc[-1].opportunity_id
    store.update_opportunity(oid, {"stage": "Lost", "outcome_reason": "Budget cut"})
    after = store.prospects().query("account_id == @aid")
    assert (after.sequence_status == "Stopped").all() and (after[after.prospect_id.isin(active.prospect_id)].stop_reason == "Closure").all()
    assert len(store.follow_ups().query("account_id == @aid and status == 'Pending'")) == 0


# ---------------------------------------------------------------- channels (email / LinkedIn / call) and follow-ups
def test_ticking_a_channel_stamps_it_logs_an_activity_and_starts_the_four_standard_follow_ups(store):
    pid = untouched_active_prospect(store)
    assert store.follow_ups(pid).empty
    assert store.set_channel(pid, "LinkedIn", True) is True
    row = store.get("prospects", "prospect_id", pid)
    assert row["linkedin_sent_at"] and row["email_sent_at"] is None and row["call_made_at"] is None
    act = store.activities(pid)
    assert list(act.channel) == ["LinkedIn"] and list(act.kind) == ["first_touch"] and act.performed_at.iloc[0] == row["linkedin_sent_at"]
    fu = store.follow_ups(pid)
    assert list(fu.seq_no) == [1, 2, 3, 4] and (fu.is_standard == 1).all() and list(fu.channel) == [c for _, c in schema.STANDARD_FOLLOWUPS]
    anchor = pd.Timestamp(row["linkedin_sent_at"][:10])
    assert [(pd.Timestamp(d) - anchor).days for d in fu.due_date] == [d for d, _ in schema.STANDARD_FOLLOWUPS]
    assert (fu.status == "Pending").all() and (fu.owner == row["owner"]).all()
    assert store.set_channel(pid, "LinkedIn", True) is False                                      # already ticked: no second activity
    store.set_channel(pid, "Email", True)
    assert len(store.follow_ups(pid)) == 4 and len(store.activities(pid)) == 2                    # a second channel does not duplicate follow-ups


def test_unticking_clears_the_timestamp_and_the_first_touch_activity(store):
    pid = untouched_active_prospect(store)
    store.set_channel(pid, "Call", True)
    assert store.set_channel(pid, "Call", False) is True
    assert store.get("prospects", "prospect_id", pid)["call_made_at"] is None and store.activities(pid).empty
    assert {"channel_on", "channel_off"} <= set(store.audit(20).action)                            # but the audit trail keeps both events
    assert store.set_channel(pid, "Call", False) is False


def test_extra_follow_ups_are_numbered_after_the_standard_four(store):
    pid = active_prospect_with_pending(store)
    top = store.follow_ups(pid).seq_no.max()
    fid = store.add_followup(pid, "2026-11-15", "Email", notes="  ask about Q4  ")
    row = store.get("follow_ups", "followup_id", fid)
    assert row["seq_no"] == top + 1 and row["is_standard"] == 0 and row["notes"] == "ask about Q4" and row["status"] == "Pending"
    with pytest.raises(ValidationError) as exc:
        store.add_followup(pid, "tomorrow", "Pigeon")
    assert len(exc.value.messages) == 2


def test_completing_a_follow_up_needs_an_outcome_and_logs_an_activity(store):
    pid = active_prospect_with_pending(store)
    fid = store.follow_ups(pid).query("status == 'Pending'").iloc[0].followup_id
    with pytest.raises(ValidationError, match="outcome"):
        store.update_followup(fid, {"status": "Done"})
    before = len(store.activities(pid))
    store.update_followup(fid, {"status": "Done", "outcome": "Left voicemail", "notes": "Asked for a call back"})
    row = store.get("follow_ups", "followup_id", fid)
    assert row["status"] == "Done" and row["completed_at"] and row["outcome"] == "Left voicemail"
    last = store.activities(pid).iloc[-1]
    assert len(store.activities(pid)) == before + 1 and last.kind == "follow_up" and last.followup_id == fid and last.notes == "Asked for a call back"
    with pytest.raises(ValidationError, match="only its notes"):
        store.update_followup(fid, {"due_date": "2026-12-01"})
    assert store.update_followup(fid, {"notes": "Updated note"}) is True


@pytest.mark.parametrize("outcome, response, temperature, stopped", [
    ("Replied - positive", "Interested", "Warm", None), ("Meeting booked", "Meeting booked", "Hot", None),
    ("Replied - not interested", "Not interested", None, "Rejection"), ("Opt-out request", "Opt-out", None, "Opt-out")])
def test_follow_up_outcomes_update_the_prospect_and_apply_stop_rules(store, outcome, response, temperature, stopped):
    pid = first(store, "SELECT p.prospect_id FROM prospects p WHERE p.sequence_status = 'Active' AND p.lead_temperature = 'Cold' AND "
                       "(SELECT COUNT(*) FROM follow_ups f WHERE f.prospect_id = p.prospect_id AND f.status = 'Pending') >= 1 ORDER BY 1").prospect_id \
        if not store.df("SELECT 1 FROM prospects p WHERE p.sequence_status='Active' AND p.lead_temperature='Cold' AND EXISTS (SELECT 1 FROM follow_ups f WHERE f.prospect_id=p.prospect_id AND f.status='Pending')").empty \
        else active_prospect_with_pending(store)
    fid = store.follow_ups(pid).query("status == 'Pending'").iloc[0].followup_id
    store.update_followup(fid, {"outcome": outcome})                                               # an outcome alone completes it
    row = store.get("prospects", "prospect_id", pid)
    assert row["response_status"] == response
    if temperature:
        assert schema.TEMPERATURES.index(row["lead_temperature"]) >= schema.TEMPERATURES.index(temperature)
    assert row["stop_reason"] == stopped and row["sequence_status"] == ("Stopped" if stopped else "Active")
    if stopped:
        assert len(store.follow_ups(pid).query("status == 'Pending'")) == 0


def test_cancelled_follow_ups_cannot_be_reopened(store):
    pid = first(store, "SELECT prospect_id FROM prospects WHERE sequence_status = 'Stopped' AND EXISTS "
                       "(SELECT 1 FROM follow_ups f WHERE f.prospect_id = prospects.prospect_id AND f.status = 'Cancelled') ORDER BY 1").prospect_id
    fid = store.follow_ups(pid).query("status == 'Cancelled'").iloc[0].followup_id
    with pytest.raises(ValidationError, match="only its notes"):
        store.update_followup(fid, {"status": "Pending"})


# ---------------------------------------------------------------- opportunities
def test_add_opportunity_computes_money_and_copies_segment_and_region(store):
    oid = store.add_opportunity({"account_id": "ACC-101", "prospect_id": "PRO-3001", "gp_margin_pct": 30, **NEW_OPP})
    row = store.get("opportunities", "opportunity_id", oid)
    assert oid == "OPP-1051" and row["stage"] == "Prospecting" and row["close_probability"] == 0.10
    assert (row["expected_revenue"], row["expected_gross_profit"], row["expected_delivery_cost"]) == (250000, 75000, 175000)
    assert (row["customer_segment"], row["hq_region"], row["owner"]) == ("AI Labs", "Europe", "Dips")


@pytest.mark.parametrize("data, message", [
    ({"deal_value": 0}, "Deal value"), ({"deal_value": "lots"}, "Deal value"), ({"stage": "Won"}, "open"), ({"stage": "Closed"}, "Stage"),
    ({"service_capability": "Magic"}, "Service capability"), ({"modality": "Barter"}, "Modality"), ({"close_probability": 1.5}, "probability"),
    ({"gp_margin_pct": 120}, "GP margin"), ({"expected_close_date": "soon"}, "date"), ({"name": ""}, "name is required")])
def test_opportunity_validation(store, data, message):
    with pytest.raises(ValidationError, match=message):
        store.add_opportunity({"account_id": "ACC-101", **{**NEW_OPP, **data}})
    assert store.counts()["opportunities"] == 50


def test_opportunity_deduplication_and_cross_account_prospect(store):
    store.add_opportunity({"account_id": "ACC-101", **NEW_OPP})
    with pytest.raises(ValidationError, match="Duplicate"):
        store.add_opportunity({"account_id": "ACC-101", **{**NEW_OPP, "name": " atlas   PILOT "}})
    other = first(store, "SELECT prospect_id FROM prospects WHERE account_id <> 'ACC-101' ORDER BY 1").prospect_id
    with pytest.raises(ValidationError, match="does not belong"):
        store.add_opportunity({"account_id": "ACC-101", **{**NEW_OPP, "name": "Other deal"}, "prospect_id": other})


def test_stage_rules_won_lost_and_default_probabilities(store):
    oid = store.add_opportunity({"account_id": account_without_closed_opp(store), **NEW_OPP})
    store.update_opportunity(oid, {"stage": "Proposal"})
    assert store.get("opportunities", "opportunity_id", oid)["close_probability"] == 0.60                      # new stage -> its default
    store.update_opportunity(oid, {"stage": "Negotiation", "close_probability": 0.9})
    assert store.get("opportunities", "opportunity_id", oid)["close_probability"] == 0.9                       # explicit value wins
    store.update_opportunity(oid, {"stage": "Won", "close_probability": 0.2})
    won = store.get("opportunities", "opportunity_id", oid)
    assert won["close_probability"] == 1.0 and won["closed_date"] == metrics.AS_OF.date().isoformat() and won["outcome_reason"] == "Not recorded"
    assert store.get("accounts", "account_id", won["account_id"])["status"] == "Customer"
    store.update_opportunity(oid, {"stage": "Qualified"})                                                       # re-opening clears the closure
    reopened = store.get("opportunities", "opportunity_id", oid)
    assert reopened["closed_date"] is None and reopened["outcome_reason"] is None and reopened["close_probability"] == 0.25
    store.update_opportunity(oid, {"stage": "Lost", "outcome_reason": "Went in-house"})
    lost = store.get("opportunities", "opportunity_id", oid)
    assert lost["close_probability"] == 0.0 and lost["outcome_reason"] == "Went in-house"


def test_changing_value_or_margin_recomputes_revenue_cost_and_gp(store):
    oid = store.add_opportunity({"account_id": "ACC-101", "gp_margin_pct": 40, **NEW_OPP})
    store.update_opportunity(oid, {"deal_value": 500000})
    row = store.get("opportunities", "opportunity_id", oid)
    assert (row["expected_revenue"], row["expected_gross_profit"]) == (500000, 200000)                           # margin kept at 40%
    store.update_opportunity(oid, {"gp_margin_pct": 25})
    assert store.get("opportunities", "opportunity_id", oid)["expected_gross_profit"] == 125000


def test_update_opportunity_is_row_level(store):
    others = table_hash(store, "opportunities", "opportunity_id <> 'OPP-1001'")
    store.update_opportunity("OPP-1001", {"next_action": "Send revised proposal"})
    assert table_hash(store, "opportunities", "opportunity_id <> 'OPP-1001'") == others
    assert store.update_opportunity("OPP-1001", {"next_action": "Send revised proposal"}) is False


# ---------------------------------------------------------------- KYC
def test_kyc_save_load_completeness_and_template(store):
    data, done = store.kyc_profile("ACC-101")
    assert done == 1.0 and "Multimodal Data Services" in data["requested_capabilities"]
    blank = kyc.clean({})
    assert kyc.completeness(blank) == 0.0
    changed = store.save_kyc("ACC-103", {**blank, "website": "www.example.com", "requested_capabilities": ["Annotation and Labeling", "AI Consulting"]})
    saved, completeness = store.kyc_profile("ACC-103")
    assert changed and saved["requested_capabilities"] == "Annotation and Labeling; AI Consulting" and 0 < completeness < 0.3
    assert store.save_kyc("ACC-103", saved) is False
    with pytest.raises(ValidationError, match="Last reviewed"):
        store.save_kyc("ACC-103", {**saved, "last_reviewed": "yesterday"})
    template = kyc.template_csv().decode().strip().splitlines()
    assert template[0].split(",")[:2] == ["account_id", "account_name"] and set(template[0].split(",")[2:]) == set(kyc.KEYS)
    assert len(template) == 2 and set(template[1].split(",")) == {""}                                            # a header and one blank row
    assert "Chief" not in kyc.template_csv().decode()


# ---------------------------------------------------------------- audit, atomicity, reset
def test_every_write_leaves_an_audit_row(store):
    start = len(store.audit(1000))
    aid = store.add_account({"account_name": "Audit Co"})
    pid = store.add_prospect({"account_id": aid, "full_name": "Pat Audit"})
    store.update_prospect(pid, {"lead_temperature": "Warm"})
    store.set_channel(pid, "Email", True)
    store.add_opportunity({"account_id": aid, **NEW_OPP})
    audit = store.audit(1000)
    assert len(audit) >= start + 5
    new = audit.iloc[: len(audit) - start]                                                         # only the rows this test added
    assert set(new.actor) == {"demo"} and {"insert", "update", "channel_on"} <= set(new.action)


def test_a_rejected_write_changes_nothing(store):
    counts, audit = store.counts(), len(store.audit(1000))
    for call in (lambda: store.add_account({"account_name": "Deepcurrent Labs"}),
                 lambda: store.add_prospect({"account_id": "ACC-101", "full_name": "Dup", "email": "tomas.zielinski@deepcurrentlabs.example.com"}),
                 lambda: store.add_opportunity({"account_id": "ACC-101", **{**NEW_OPP, "deal_value": -5}})):
        with pytest.raises(ValidationError):
            call()
    assert store.counts() == counts and len(store.audit(1000)) == audit


def test_reset_needs_confirmation_and_only_rebuilds_the_demo_file(store, tmp_path):
    store.add_account({"account_name": "Temporary Co"})
    with pytest.raises(ValidationError, match="confirmation"):
        store.reset_demo()
    assert store.counts()["accounts"] == 65
    other = GTMStore(tmp_path / "other.db")
    other.add_account({"account_name": "Elsewhere Co"})
    store.reset_demo(confirm=True)
    assert store.counts()["accounts"] == 64 and other.counts()["accounts"] == 65                                  # the other database is untouched
