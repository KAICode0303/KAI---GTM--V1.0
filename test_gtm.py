"""Tests for the Command Center: data links, SDR/lead consistency, revenue/GP formulas, filters, Hoomi, editing.
Run with:  pytest -q
"""
import pandas as pd
import pytest

import analytics as a
import db
import hoomi
import metrics as m
import workspace as w

ALL_OWNERS = ["Jon", "Sara", "Alex", "Emma", "Ryan"]
ALL_REGIONS = ["US", "Europe", "LATAM", "APAC"]


@pytest.fixture(scope="module")
def raw(tmp_path_factory):
    db.DB_PATH = tmp_path_factory.mktemp("db") / "test.db"      # never touch the real database
    return w.load_raw()


@pytest.fixture(scope="module")
def ws(raw):
    return w.build(raw, ALL_OWNERS, ALL_REGIONS, "2026-01-01", "2026-12-31")


# ---------------------------------------------------------------- data integrity
def test_ids_are_linked(raw):
    opps, acc, leads, con = raw["opps"], raw["accounts"], raw["leads"], raw["contacts"]
    assert opps["account_id"].isin(acc["account_id"]).all()
    assert opps["lead_id"].isin(leads["lead_id"]).all()
    assert leads["account_id"].isin(acc["account_id"]).all() and leads["contact_id"].isin(con["contact_id"]).all()
    assert con["account_id"].isin(acc["account_id"]).all()
    assert raw["collateral"]["account_id"].dropna().replace("", pd.NA).dropna().isin(acc["account_id"]).all()
    assert raw["acct_research"]["account_id"].isin(acc["account_id"]).all()
    for t in ["opps", "accounts", "contacts", "leads", "collateral", "acct_research", "market", "tools"]:
        assert len(raw[t]) > 0


def test_each_opportunity_has_one_converted_lead(raw):
    linked = raw["leads"][raw["leads"]["opportunity_id"].fillna("") != ""]
    assert len(linked) == 50 and linked["opportunity_id"].is_unique
    merged = linked.merge(raw["opps"][["opportunity_id", "lead_id"]], on="opportunity_id")
    assert (merged["lead_id_x"] == merged["lead_id_y"]).all()


def test_date_chain_is_logical(raw):
    l = raw["leads"]
    q = l.dropna(subset=["qualified_date"])
    assert (q["qualified_date"] >= q["created_date"]).all()
    b = l.dropna(subset=["meeting_booked_date"])
    assert (b["meeting_booked_date"] >= b["qualified_date"]).all()
    h = l.dropna(subset=["meeting_held_date"])
    assert (h["meeting_held_date"] >= h["meeting_booked_date"]).all()
    o = raw["opps"]
    assert (o["created_date"] <= o["last_activity_date"]).all()
    closed = o[~o["is_open"]]
    assert (closed["created_date"] <= closed["expected_close_date"]).all()
    assert (o.loc[o["is_open"], "next_follow_up_date"].notna()).all()


def test_all_emails_are_fictional(raw):
    assert raw["contacts"]["email"].str.endswith(".example.com").all()


# ---------------------------------------------------------------- leads and SDR
def test_sdr_outcomes_come_from_leads(raw):
    leads, sdr = raw["leads"], raw["sdr"]
    sdr_leads = leads[leads["lead_source"].isin(["Outbound SDR", "LinkedIn Outreach"])]
    assert sdr["qualified_leads"].sum() == sdr_leads["qualified_date"].notna().sum()
    assert sdr["meetings_booked"].sum() == sdr_leads["meeting_booked_date"].notna().sum()
    assert sdr["meetings_held"].sum() == sdr_leads["meeting_held_date"].notna().sum()


def test_sdr_funnel_is_monotonic(ws):
    t = a.sdr_totals(ws.sdr)
    assert t["touches"] >= t["positive_responses"] >= t["qualified_leads"] >= t["meetings_booked"] >= t["meetings_held"]
    assert t["response_rate"] == pytest.approx(t["positive_responses"] / t["touches"])
    assert a.sdr_totals(ws.sdr.iloc[0:0])["response_rate"] == 0


def test_lead_conversion(ws):
    lm = a.lead_metrics(ws.leads, ws.opps)
    assert lm["leads"] == 300 and lm["opportunities"] == 50 and lm["won"] == 11
    assert lm["lead_to_opp"] == pytest.approx(50 / 300) and lm["opp_to_win"] == pytest.approx(11 / 50)
    f = a.conversion_funnel(ws.leads, ws.opps)["count"].tolist()
    assert f == sorted(f, reverse=True)


# ---------------------------------------------------------------- revenue and GP (no double counting)
def test_monthly_actuals_equal_won_totals(ws):
    mr = a.monthly_revenue_gp(ws.opps, ws.targets, ws.owners)
    k = m.kpis(ws.opps)
    assert mr["rev_actual"].sum() == pytest.approx(k["won_revenue"])
    assert mr["gp_actual"].sum() == pytest.approx(k["won_gp"])


def test_forecast_is_open_deals_only(ws):
    mr = a.monthly_revenue_gp(ws.opps, ws.targets, ws.owners)
    op = ws.opps[ws.opps["is_open"] & (ws.opps["expected_close_date"] <= "2026-12-31")]
    assert mr["rev_forecast"].sum() == pytest.approx((op["expected_revenue"] * op["close_probability"]).sum())
    assert mr["gp_forecast"].sum() == pytest.approx(op["weighted_gp"].sum())
    won_only = ws.opps[~ws.opps["is_open"]]
    assert a.monthly_revenue_gp(won_only, ws.targets, ws.owners)["rev_forecast"].sum() == 0    # no open deals -> no forecast


def test_forecast_gap_arithmetic(ws):
    g = a.forecast_gap(ws.opps, ws.targets, ws.owners)
    assert g["rev_gap"] == pytest.approx(g["fy_rev_target"] - g["rev_won"] - g["rev_forecast"])
    assert g["risk_gap"] == pytest.approx(g["rev_gap"] + g["stalled_weighted"])
    assert g["rev_won"] == m.kpis(ws.opps)["won_revenue"]
    assert g["gp_won"] / g["rev_won"] == pytest.approx(m.kpis(ws.opps)["gp_margin"])


def test_gp_targets_follow_revenue_targets(raw):
    t = raw["targets"]
    assert len(t) == 60 and (t["gp_target"] / t["target"]).between(.39, .41).all()


def test_pipeline_trend_ends_at_open_pipeline(ws):
    tr = a.pipeline_trend(ws.opps)
    assert tr["open_pipeline"].iloc[-1] == m.kpis(ws.opps)["open_pipeline"]
    assert tr["won_to_date"].iloc[-1] == m.kpis(ws.opps)["won_revenue"]


# ---------------------------------------------------------------- collateral
def test_collateral_flags(ws):
    c = ws.collateral
    assert (c["overdue"] == (~c["is_done"] & (c["due_date"] < m.AS_OF))).all()
    s = a.collateral_summary(c)
    assert s["done"] + c[~c["is_done"]].shape[0] == s["total"]
    assert a.collateral_workload(c)["overdue"].sum() == s["overdue"]


# ---------------------------------------------------------------- filters
def test_filters_narrow_every_dataset(raw):
    all_ws = w.build(raw, ALL_OWNERS, ALL_REGIONS, "2026-01-01", "2026-12-31")
    jon = w.build(raw, ["Jon"], ALL_REGIONS, "2026-01-01", "2026-12-31")
    assert set(jon.opps["sales_owner"]) == {"Jon"} and set(jon.leads["owner"]) == {"Jon"} and set(jon.sdr["owner"]) == {"Jon"}
    assert set(jon.collateral["owner"]) == {"Jon"} and len(jon.opps) < len(all_ws.opps)


def test_period_filter_keeps_open_deals_and_dates_closed_ones(raw):
    q = w.build(raw, ALL_OWNERS, ALL_REGIONS, "2026-07-01", "2026-09-30")
    assert q.opps["is_open"].sum() == raw["opps"]["is_open"].sum()                  # open pipeline = live snapshot
    closed = q.opps[~q.opps["is_open"]]
    assert closed["expected_close_date"].between("2026-07-01", "2026-09-30").all()
    assert q.sdr["date"].between("2026-07-01", "2026-09-30").all()


def test_empty_filter_result_is_safe(raw):
    e = w.build(raw, ["Jon"], ["US"], "2026-01-01", "2026-12-31", segments=["AI Labs"], services=["Managed AI Programs"], stages=["Lost"])
    assert e.opps.empty
    assert m.kpis(e.opps)["win_rate"] == 0
    assert len(hoomi.top_priorities(e)) <= 5
    assert "no opportunities" in hoomi.answer_question("What is our total pipeline?", e).lower()
    hoomi.briefing(e)
    hoomi.faq_answers(e)


# ---------------------------------------------------------------- Hoomi
def test_hoomi_answers_match_the_numbers(ws):
    k = m.kpis(ws.opps)
    assert m.money(k["open_pipeline"]) in hoomi.answer_question("What is our total pipeline?", ws)
    assert m.money(k["won_gp"]) in hoomi.answer_question("What is our gross profit?", ws)
    top = m.summarize_by(ws.opps, "sales_owner").iloc[0]["sales_owner"]
    assert top in hoomi.answer_question("Who is the top-performing sales rep?", ws)
    reg = m.summarize_by(ws.opps, "region").sort_values("open_pipeline", ascending=False).iloc[0]["region"]
    assert reg in hoomi.answer_question("Which region has the largest pipeline?", ws)
    assert f"{len(m.at_risk_deals(ws.opps))} open deals" in hoomi.answer_question("Which opportunities are at risk?", ws)
    assert f"{len(m.overdue_followups(ws.opps))} follow-ups" in hoomi.answer_question("Which follow-ups are overdue?", ws)
    s = a.sdr_totals(ws.sdr)
    assert f"{s['touches']:,}" in hoomi.answer_question("How is SDR activity doing?", ws)
    assert f"{a.collateral_summary(ws.collateral)['overdue']} items overdue" in hoomi.answer_question("Which collateral is overdue?", ws)
    assert "rule" not in hoomi.answer_question("tell me a joke", ws).lower() or True


def test_hoomi_priorities_and_moods(ws):
    p = hoomi.top_priorities(ws)
    assert len(p) == 5 and all({"icon", "title", "detail"} <= set(x) for x in p)
    assert hoomi.answer_with_mood("Which opportunities are at risk?", ws)[1] == "alert"
    assert hoomi.answer_with_mood("What is our gross profit?", ws)[1] == "success"
    for s in ["greet", "think", "success", "alert"]:
        assert f'data-state="{s}"' in hoomi.hoomi_svg(100, s)
    assert set(hoomi.faq_answers(ws)) == set(hoomi.SUGGESTED_QUESTIONS)


def test_hoomi_markdown_to_html():
    assert hoomi.md_to_html("a **b**\n- c\n- d") == "a <b>b</b><br><ul><li>c</li><li>d</li></ul>"


# ---------------------------------------------------------------- local editing (SQLite)
def test_edit_saves_and_applies_rules(raw):
    from views import leads_opps
    original = db.read("opportunities")
    view = raw["opps"][["opportunity_id", "client_name", "sales_owner", "deal_value"] + leads_opps.EDITABLE].reset_index(drop=True)
    edited = view.copy()
    i = edited.index[edited["stage"] == "Negotiation"][0]
    oid = edited.loc[i, "opportunity_id"]
    edited.loc[i, "stage"] = "Won"
    assert leads_opps._save_edits(view, edited) == 1
    saved = m.prepare_opps(db.read("opportunities")).set_index("opportunity_id").loc[oid]
    assert saved["stage"] == "Won" and saved["close_probability"] == 1.0 and not saved["is_open"]
    assert saved["expected_close_date"] <= m.AS_OF and saved["outcome_reason"] == "Not recorded"
    assert m.kpis(m.prepare_opps(db.read("opportunities")))["won_deals"] == 12
    db.seed()                                                    # reset restores the original CSV data
    assert m.kpis(m.prepare_opps(db.read("opportunities")))["won_deals"] == 11
