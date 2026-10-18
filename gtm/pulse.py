"""Executive Pulse calculations. Pure functions over the V2 store's tables; every number on the page comes from here.

Definitions (shown as tooltips in the UI)
  Accounts Closed     distinct accounts with at least one Won opportunity
  Open Pipeline       sum of deal value of opportunities in an open stage (Prospecting..Negotiation)
  Weighted Pipeline   sum of deal value x close probability over open opportunities
  Won Revenue         sum of expected revenue of Won opportunities (actual, not forecast)
  Won Gross Profit    sum of expected gross profit of Won opportunities
  GP Margin           Won gross profit / Won revenue
  Total Leads         prospects in the workspace (a lead is a prospect being worked)
  Warm / Hot Leads    prospects whose lead temperature is Warm / Hot
  Qualified Leads     prospects whose qualification status is Qualified
  Win Rate            Won / (Won + Lost) opportunities; open deals are not counted
  Pending Follow-ups  follow-ups still Pending on an active sequence (stopped sequences have none: stopping cancels them)
"""
import pandas as pd

import metrics
from gtm import clock, schema

STALL_DAYS = metrics.STALL_DAYS


def load(store):
    return {"accounts": store.accounts(), "prospects": store.prospects(), "follow_ups": store.follow_ups(),
            "activities": store.activities(), "opps": store.opportunities(), "targets": store.targets(),
            "kyc": store.df("SELECT account_id, data_json FROM kyc_profiles")}


def _div(a, b):
    return a / b if b else 0.0


def _won(opps):
    return opps[opps.stage == "Won"]


def _open(opps):
    return opps[opps.stage.isin(schema.OPEN_STAGES)]


def commercial_kpis(opps):
    won, open_ = _won(opps), _open(opps)
    lost = opps[opps.stage == "Lost"]
    revenue, gp = float(won.expected_revenue.sum()), float(won.expected_gross_profit.sum())
    return {"accounts_closed": int(won.account_id.nunique()), "open_pipeline": float(open_.deal_value.sum()),
            "weighted_pipeline": float((open_.deal_value * open_.close_probability).sum()), "won_revenue": revenue, "won_gp": gp,
            "gp_margin": _div(gp, revenue), "open_deals": len(open_), "won_deals": len(won), "lost_deals": len(lost),
            "win_rate": _div(len(won), len(won) + len(lost))}


def lead_kpis(prospects, follow_ups, opps, as_of=None):
    as_of = (as_of or clock.today()).isoformat()
    pending = follow_ups[follow_ups.status == "Pending"]
    c = commercial_kpis(opps)
    return {"total_leads": len(prospects), "warm_leads": int((prospects.lead_temperature == "Warm").sum()),
            "hot_leads": int((prospects.lead_temperature == "Hot").sum()),
            "qualified_leads": int((prospects.qualification_status == "Qualified").sum()), "win_rate": c["win_rate"],
            "pending_followups": len(pending), "overdue_followups": int((pending.due_date < as_of).sum()),
            "stopped_sequences": int((prospects.sequence_status == schema.SEQUENCE_STOPPED).sum())}


# ---------------------------------------------------------------- chart tables
def stage_summary(opps):
    g = opps.assign(weighted=opps.deal_value * opps.close_probability).groupby("stage").agg(
        deals=("opportunity_id", "size"), value=("deal_value", "sum"), weighted=("weighted", "sum"))
    return g.reindex(schema.STAGES).fillna(0).reset_index()


def monthly_target_vs_actual(opps, targets):
    t = targets.groupby("month", as_index=False).agg(target=("target", "sum"), gp_target=("gp_target", "sum"))
    won = _won(opps).assign(month=lambda d: d.closed_date.fillna(d.expected_close_date).str[:7])
    actual = won.groupby("month", as_index=False).agg(actual=("expected_revenue", "sum"), actual_gp=("expected_gross_profit", "sum"))
    open_ = _open(opps).assign(month=lambda d: d.expected_close_date.str[:7], forecast=lambda d: d.deal_value * d.close_probability)
    forecast = open_.groupby("month", as_index=False).agg(forecast=("forecast", "sum"))
    out = t.merge(actual, on="month", how="left").merge(forecast, on="month", how="left").fillna(0.0)
    return out.sort_values("month").reset_index(drop=True)


def forecast_outside_months(opps, months):
    """Weighted pipeline whose expected close month is NOT among `months` (e.g. 2027 deals under a 2026 chart), so charts reconcile."""
    open_ = _open(opps)
    outside = ~open_.expected_close_date.fillna("").str[:7].isin(list(months))
    return float((open_.deal_value * open_.close_probability)[outside].sum())


def breakdown(opps, column):
    """Open and won value by a dimension (HQ region, customer segment, capability, modality)."""
    rows = []
    for key, g in opps.groupby(column):
        rows.append({column: key, "open_value": float(_open(g).deal_value.sum()), "won_value": float(_won(g).expected_revenue.sum()),
                     "deals": len(g), "open_deals": len(_open(g)), "total_value": float(g.deal_value.sum())})
    return pd.DataFrame(rows, columns=[column, "open_value", "won_value", "deals", "open_deals", "total_value"]).sort_values("total_value", ascending=False).reset_index(drop=True)


def capability_demand(opps, kyc_df):
    """Distinct accounts requesting each capability: through an opportunity OR a KYC 'requested capabilities' entry."""
    import json
    asked = {c: set() for c in schema.CAPABILITIES}
    for r in opps.itertuples():
        if r.service_capability in asked:
            asked[r.service_capability].add(r.account_id)
    for r in kyc_df.itertuples():
        for cap in [x.strip() for x in str(json.loads(r.data_json).get("requested_capabilities", "")).split(";") if x.strip()]:
            if cap in asked:
                asked[cap].add(r.account_id)
    open_value = _open(opps).groupby("service_capability").deal_value.sum()
    out = pd.DataFrame([{"capability": c, "accounts": len(a), "open_value": float(open_value.get(c, 0.0))} for c, a in asked.items()])
    return out.sort_values(["accounts", "open_value"], ascending=False).reset_index(drop=True)


def sdr_performance(prospects, opps, activities, follow_ups):
    rows = []
    for sdr in schema.SDRS:
        p = prospects[prospects.owner == sdr]
        o = opps[opps.owner == sdr]
        rows.append({"sdr": sdr, "prospects": len(p), "touches": int((activities.owner == sdr).sum()),
                     "hot": int((p.lead_temperature == "Hot").sum()), "qualified": int((p.qualification_status == "Qualified").sum()),
                     "meetings": int((p.response_status == "Meeting booked").sum()), "opps": len(o),
                     "won_revenue": float(_won(o).expected_revenue.sum()), "open_pipeline": float(_open(o).deal_value.sum()),
                     "pending_followups": int(((follow_ups.owner == sdr) & (follow_ups.status == "Pending")).sum())})
    return pd.DataFrame(rows).sort_values(["won_revenue", "qualified"], ascending=False).reset_index(drop=True)


def pipeline_health(opps, follow_ups, as_of=None):
    as_of = as_of or clock.today()
    open_ = _open(opps).copy()
    last = pd.to_datetime(open_.last_activity_date, errors="coerce")
    open_["idle_days"] = (pd.Timestamp(as_of) - last).dt.days
    stalled = open_[open_.idle_days > STALL_DAYS]
    late = open_[open_.stage.isin(["Proposal", "Negotiation"])]
    pending = follow_ups[follow_ups.status == "Pending"]
    return {"open_deals": len(open_), "stalled_deals": len(stalled), "stalled_value": float(stalled.deal_value.sum()),
            "late_stage_value": float(late.deal_value.sum()), "late_stage_share": _div(late.deal_value.sum(), open_.deal_value.sum()),
            "overdue_followups": int((pending.due_date < as_of.isoformat()).sum()),
            "coverage": _div((open_.deal_value * open_.close_probability).sum(), open_.deal_value.sum()),
            "stalled_ids": list(stalled.opportunity_id)}


# ---------------------------------------------------------------- the whole page in one call
def snapshot(store, as_of=None):
    t = load(store)
    as_of = as_of or clock.today()
    snap = {"as_of": as_of, "commercial": commercial_kpis(t["opps"]), "leads": lead_kpis(t["prospects"], t["follow_ups"], t["opps"], as_of),
            "stage": stage_summary(t["opps"]), "monthly": monthly_target_vs_actual(t["opps"], t["targets"]),
            "forecast_outside": forecast_outside_months(t["opps"], t["targets"].month.unique()),
            "region": breakdown(t["opps"], "hq_region"), "segment": breakdown(t["opps"], "customer_segment"),
            "capability": breakdown(t["opps"], "service_capability"), "modality": breakdown(t["opps"], "modality"),
            "demand": capability_demand(t["opps"], t["kyc"]), "sdr": sdr_performance(t["prospects"], t["opps"], t["activities"], t["follow_ups"]),
            "health": pipeline_health(t["opps"], t["follow_ups"], as_of)}
    snap["summary"] = executive_summary(snap)
    return snap


def executive_summary(snap):
    """Plain-language bullets, derived only from the numbers in the snapshot (no model involved)."""
    money = metrics.money
    cap, demand, sdr, h, c = snap["capability"], snap["demand"], snap["sdr"], snap["health"], snap["commercial"]
    by_rev = cap[cap.won_value > 0].sort_values("won_value", ascending=False).head(3)
    revenue = [f"{r.service_capability}: {money(r.won_value)} won" for r in by_rev.itertuples()] or ["No won revenue yet."]
    capabilities = [f"{r.capability}: requested by {r.accounts} accounts ({money(r.open_value)} open)" for r in demand.head(3).itertuples()]
    top = sdr.head(3)
    sdrs = [f"{r.sdr}: {money(r.won_revenue)} won, {r.qualified} qualified leads, {r.touches} touches" for r in top.itertuples()]
    health = [f"{h['open_deals']} open deals; {h['late_stage_share']:.0%} of open value is in Proposal or Negotiation.",
              f"{h['stalled_deals']} deals ({money(h['stalled_value'])}) have had no activity for {STALL_DAYS}+ days.",
              f"{h['overdue_followups']} follow-ups are overdue.",
              f"Weighted pipeline is {money(c['weighted_pipeline'])}, {h['coverage']:.0%} of open pipeline."]
    return {"revenue_by_service": revenue, "requested_capabilities": capabilities, "sdr_performance": sdrs, "pipeline_health": health}
