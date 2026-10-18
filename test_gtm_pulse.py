"""Tests for the Executive Pulse calculations (gtm/pulse.py): definitions, totals that add up, and agreement with V1's own metrics."""
import pytest

import metrics
from gtm import pulse, schema
from gtm.store import GTMStore


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    return GTMStore(tmp_path_factory.mktemp("pulse") / "gtm.db")


@pytest.fixture(scope="module")
def snap(seeded):
    return pulse.snapshot(seeded)


def test_commercial_kpis_agree_with_the_independent_v1_metrics(snap):
    v1 = metrics.kpis(metrics.load_data())
    c = snap["commercial"]
    for key in ("open_pipeline", "weighted_pipeline", "won_revenue", "won_gp", "win_rate"):
        assert c[key] == pytest.approx(v1[key]), key
    assert c["gp_margin"] == pytest.approx(v1["gp_margin"])
    assert (c["open_deals"], c["won_deals"], c["lost_deals"]) == (v1["open_deals"], v1["won_deals"], v1["lost_deals"])


def test_commercial_definitions_on_a_tiny_hand_built_store(tmp_path):
    s = GTMStore(tmp_path / "tiny.db", seed=False)
    a, b = (s.add_account({"account_name": n, "owner": "Mini", "hq_region": "US", "customer_segment": "Enterprises"}) for n in ("Alpha", "Beta"))
    base = dict(service_capability="AI Consulting", modality="Managed service", gp_margin_pct=40)
    o1 = s.add_opportunity({"account_id": a, "name": "A1", "deal_value": 100000, "stage": "Proposal", **base})              # open, p=.6
    o2 = s.add_opportunity({"account_id": a, "name": "A2", "deal_value": 200000, **base})                                   # open, p=.1
    o3 = s.add_opportunity({"account_id": b, "name": "B1", "deal_value": 300000, **base})
    o4 = s.add_opportunity({"account_id": b, "name": "B2", "deal_value": 50000, **base})
    s.update_opportunity(o3, {"stage": "Won"})
    s.update_opportunity(o4, {"stage": "Lost"})
    c = pulse.commercial_kpis(s.opportunities())
    assert c["accounts_closed"] == 1 and c["open_pipeline"] == 300000 and c["weighted_pipeline"] == pytest.approx(100000 * .6 + 200000 * .1)
    assert c["won_revenue"] == 300000 and c["won_gp"] == 120000 and c["gp_margin"] == pytest.approx(.4)
    assert c["win_rate"] == pytest.approx(.5) and (c["won_deals"], c["lost_deals"], c["open_deals"]) == (1, 1, 2)
    assert o1 and o2


def test_lead_kpis_are_consistent_with_the_prospect_table(seeded, snap):
    p, f, k = seeded.prospects(), seeded.follow_ups(), snap["leads"]
    assert k["total_leads"] == len(p) == 109
    assert k["warm_leads"] + k["hot_leads"] <= k["total_leads"]
    assert k["warm_leads"] == int((p.lead_temperature == "Warm").sum()) and k["hot_leads"] == int((p.lead_temperature == "Hot").sum())
    assert k["qualified_leads"] == int((p.qualification_status == "Qualified").sum())
    assert k["win_rate"] == snap["commercial"]["win_rate"]
    assert k["pending_followups"] == int((f.status == "Pending").sum()) and 0 <= k["overdue_followups"] <= k["pending_followups"]
    assert k["stopped_sequences"] == int((p.sequence_status == "Stopped").sum())


def test_stopping_a_sequence_lowers_pending_follow_ups(tmp_path):
    s = GTMStore(tmp_path / "s.db")
    before = pulse.snapshot(s)["leads"]
    pid = s.df("SELECT p.prospect_id FROM prospects p WHERE p.sequence_status='Active' AND EXISTS "
               "(SELECT 1 FROM follow_ups f WHERE f.prospect_id=p.prospect_id AND f.status='Pending') ORDER BY 1").iloc[0].prospect_id
    n = len(s.follow_ups(pid).query("status == 'Pending'"))
    s.update_prospect(pid, {"response_status": "Opt-out"})
    after = pulse.snapshot(s)["leads"]
    assert after["pending_followups"] == before["pending_followups"] - n and after["stopped_sequences"] == before["stopped_sequences"] + 1
    assert after["total_leads"] == before["total_leads"]


def test_stage_summary_covers_every_stage_and_adds_up(seeded, snap):
    st_ = snap["stage"]
    assert list(st_.stage) == schema.STAGES
    opps = seeded.opportunities()
    assert st_.deals.sum() == len(opps) and st_.value.sum() == opps.deal_value.sum()
    open_ = st_[st_.stage.isin(schema.OPEN_STAGES)]
    assert open_.value.sum() == snap["commercial"]["open_pipeline"] and open_.weighted.sum() == pytest.approx(snap["commercial"]["weighted_pipeline"])


def test_monthly_target_vs_actual_adds_up(seeded, snap):
    m = snap["monthly"]
    assert list(m.month) == [f"2026-{i:02d}" for i in range(1, 13)]
    assert m.target.sum() == pytest.approx(seeded.targets().target.sum())
    assert m.actual.sum() == pytest.approx(snap["commercial"]["won_revenue"])
    assert snap["forecast_outside"] > 0                                                  # some open deals are expected to close in 2027
    assert m.forecast.sum() + snap["forecast_outside"] == pytest.approx(snap["commercial"]["weighted_pipeline"])
    assert m.actual_gp.sum() == pytest.approx(snap["commercial"]["won_gp"])


@pytest.mark.parametrize("key, column", [("region", "hq_region"), ("segment", "customer_segment"), ("capability", "service_capability"), ("modality", "modality")])
def test_breakdowns_add_up_to_the_totals(snap, key, column):
    b, c = snap[key], snap["commercial"]
    assert b.open_value.sum() == pytest.approx(c["open_pipeline"]) and b.won_value.sum() == pytest.approx(c["won_revenue"])
    assert b.deals.sum() == c["open_deals"] + c["won_deals"] + c["lost_deals"]
    assert not b[column].isna().any()


def test_vocabularies_match_the_data(snap):
    assert set(snap["region"].hq_region) <= set(schema.REGIONS) and set(snap["segment"].customer_segment) <= set(schema.SEGMENTS)
    assert set(snap["capability"].service_capability) <= set(schema.CAPABILITIES) and set(snap["modality"].modality) <= set(schema.MODALITIES)
    assert len(snap["modality"]) == 3                                                    # segment and modality are separate dimensions


def test_sdr_performance_covers_the_team_and_adds_up(seeded, snap):
    sdr = snap["sdr"]
    assert set(sdr.sdr) == set(schema.SDRS) and len(sdr) == 5
    assert sdr.won_revenue.sum() == pytest.approx(snap["commercial"]["won_revenue"])
    assert sdr.prospects.sum() == len(seeded.prospects()) and sdr.touches.sum() == len(seeded.activities())
    assert sdr.pending_followups.sum() == snap["leads"]["pending_followups"]
    assert list(sdr.won_revenue) == sorted(sdr.won_revenue, reverse=True)


def test_capability_demand_counts_distinct_accounts(snap):
    d = snap["demand"]
    assert set(d.capability) == set(schema.CAPABILITIES) and (d.accounts >= 0).all()
    assert d.accounts.iloc[0] == d.accounts.max()
    opps_accounts = snap["capability"].set_index("service_capability")
    assert (d.set_index("capability").accounts >= 0).all() and opps_accounts.deals.sum() > 0


def test_pipeline_health(seeded, snap):
    h = snap["health"]
    opps = seeded.opportunities()
    open_ = opps[opps.stage.isin(schema.OPEN_STAGES)]
    assert h["open_deals"] == len(open_) and 0 <= h["stalled_deals"] <= h["open_deals"] and len(h["stalled_ids"]) == h["stalled_deals"]
    assert 0 <= h["late_stage_share"] <= 1 and 0 < h["coverage"] <= 1
    assert h["stalled_value"] == pytest.approx(open_[open_.opportunity_id.isin(h["stalled_ids"])].deal_value.sum())


def test_executive_summary_is_derived_from_the_numbers(snap):
    s = snap["summary"]
    assert set(s) == {"revenue_by_service", "requested_capabilities", "sdr_performance", "pipeline_health"} and all(s.values())
    assert snap["sdr"].iloc[0].sdr in s["sdr_performance"][0]
    assert snap["demand"].iloc[0].capability in s["requested_capabilities"][0]
    top_service = snap["capability"].sort_values("won_value", ascending=False).iloc[0].service_capability
    assert top_service in s["revenue_by_service"][0]
    assert f"{snap['health']['open_deals']} open deals" in s["pipeline_health"][0]


def test_an_empty_store_gives_zeroes_not_errors(tmp_path):
    empty = GTMStore(tmp_path / "empty.db", seed=False)
    snap = pulse.snapshot(empty)
    assert snap["commercial"]["open_pipeline"] == 0 and snap["commercial"]["win_rate"] == 0 and snap["commercial"]["gp_margin"] == 0
    assert snap["leads"]["total_leads"] == 0 and snap["leads"]["pending_followups"] == 0
    assert len(snap["stage"]) == 7 and snap["sdr"].prospects.sum() == 0 and snap["summary"]["revenue_by_service"] == ["No won revenue yet."]
