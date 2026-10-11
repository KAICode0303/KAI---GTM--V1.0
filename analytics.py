"""Calculations for leads, SDR activity, collateral, revenue / gross profit and trends.

(Pipeline basics - open pipeline, weighted pipeline, win rate - live in metrics.py.)

Key definitions
  Lead -> Opportunity = opportunities / leads
  Opportunity -> Win  = Won deals / all opportunities
  Response rate       = positive responses / (calls + emails + LinkedIn touches)
  Realized revenue/GP = Won deals ONLY.   Open pipeline is never counted as realized.
  Weighted forecast   = open deal value (or GP) x close probability
"""
import numpy as np
import pandas as pd

import metrics as m

AS_OF = m.AS_OF
FY_END = pd.Timestamp("2026-12-31")
TOUCH_COLS = ["cold_calls", "emails_sent", "linkedin_outreach"]
SDR_COLS = ["cold_calls", "emails_sent", "linkedin_outreach", "follow_ups", "accounts_researched",
            "positive_responses", "qualified_leads", "meetings_booked", "meetings_held"]
SDR_LABELS = {"cold_calls": "Cold calls", "emails_sent": "Emails sent", "linkedin_outreach": "LinkedIn outreach",
              "follow_ups": "Follow-ups", "accounts_researched": "Accounts researched",
              "positive_responses": "Positive responses", "qualified_leads": "Qualified leads",
              "meetings_booked": "Meetings booked", "meetings_held": "Meetings held"}


def _div(a, b):
    return float(a) / float(b) if b else 0.0


# ------------------------------------------------------------------ leads & conversion
def lead_metrics(leads, opps):
    """Lead and meeting counts plus the two conversion rates (leads and opps should already be filtered)."""
    n_leads = len(leads)
    linked = leads[leads["opportunity_id"].fillna("") != ""]
    won_ids = set(opps.loc[opps["stage"] == "Won", "opportunity_id"])
    n_opps = len(linked)
    return {
        "leads": n_leads,
        "qualified": int(leads["qualified_date"].notna().sum()),
        "meetings_booked": int(leads["meeting_booked_date"].notna().sum()),
        "meetings_held": int(leads["meeting_held_date"].notna().sum()),
        "opportunities": n_opps,
        "won": int(linked["opportunity_id"].isin(won_ids).sum()),
        "lead_to_opp": _div(n_opps, n_leads),
        "opp_to_win": _div(linked["opportunity_id"].isin(won_ids).sum(), n_opps),
    }


def conversion_funnel(leads, opps):
    """Rows for a Lead -> Qualified -> Meeting -> Opportunity -> Won funnel chart."""
    k = lead_metrics(leads, opps)
    return pd.DataFrame({"stage": ["Leads", "Qualified", "Meeting held", "Opportunity", "Won"],
                         "count": [k["leads"], k["qualified"], k["meetings_held"], k["opportunities"], k["won"]]})


def leads_by_source(leads, opps):
    if leads.empty:
        return pd.DataFrame(columns=["lead_source", "leads", "opportunities", "conversion"])
    g = leads.assign(has_opp=leads["opportunity_id"].fillna("") != "").groupby("lead_source").agg(
        leads=("lead_id", "count"), opportunities=("has_opp", "sum")).reset_index()
    g["conversion"] = g["opportunities"] / g["leads"]
    return g.sort_values("leads", ascending=False)


# ------------------------------------------------------------------ SDR activity
def sdr_totals(sdr):
    t = {c: int(sdr[c].sum()) for c in SDR_COLS}
    touches = sum(t[c] for c in TOUCH_COLS)
    t["touches"] = touches
    t["response_rate"] = _div(t["positive_responses"], touches)
    t["response_to_qualified"] = _div(t["qualified_leads"], t["positive_responses"])
    t["qualified_to_meeting"] = _div(t["meetings_booked"], t["qualified_leads"])
    t["show_rate"] = _div(t["meetings_held"], t["meetings_booked"])
    return t


def sdr_by_rep(sdr):
    """Leaderboard: totals and rates per rep, ranked by meetings booked then qualified leads."""
    if sdr.empty:
        return pd.DataFrame(columns=["owner"] + SDR_COLS + ["touches", "response_rate", "productivity"])
    g = sdr.groupby("owner")[SDR_COLS].sum()
    g["touches"] = g[TOUCH_COLS].sum(axis=1)
    g["response_rate"] = g["positive_responses"] / g["touches"].replace(0, np.nan)
    g["response_rate"] = g["response_rate"].fillna(0)
    # simple productivity score: weighted outcomes per 100 touches
    g["productivity"] = (g["positive_responses"] + 5 * g["qualified_leads"] + 8 * g["meetings_booked"]) / g["touches"].replace(0, np.nan) * 100
    g["productivity"] = g["productivity"].fillna(0)
    return g.sort_values(["meetings_booked", "qualified_leads"], ascending=False).reset_index()


def sdr_trend(sdr, freq="W"):
    """Totals per week ('W') or day ('D')."""
    if sdr.empty:
        return pd.DataFrame(columns=["period"] + SDR_COLS)
    d = sdr.copy()
    d["period"] = d["date"].dt.to_period("W-SUN").dt.start_time if freq == "W" else d["date"]
    out = d.groupby("period")[SDR_COLS].sum().reset_index()
    out["touches"] = out[TOUCH_COLS].sum(axis=1)
    out["response_rate"] = out["positive_responses"] / out["touches"].replace(0, np.nan)
    return out


def activity_attainment(sdr, act_targets, n_reps, start, end):
    """Actual vs target for each activity metric. Target = weekly target x weeks in period x reps."""
    weeks = max(np.busday_count(pd.Timestamp(start).date(), (min(pd.Timestamp(end), AS_OF) + pd.Timedelta(days=1)).date()) / 5, 0)
    rows = []
    for r in act_targets.itertuples():
        actual = int(sdr[r.metric].sum()) if r.metric in sdr.columns else 0
        target = r.weekly_target * weeks * n_reps
        rows.append({"metric": r.metric, "label": SDR_LABELS.get(r.metric, r.metric), "actual": actual,
                     "target": round(target), "attainment": _div(actual, target)})
    return pd.DataFrame(rows)


# ------------------------------------------------------------------ collateral
def prepare_collateral(df):
    df = df.copy()
    df["is_done"] = df["status"].isin(["Approved", "Delivered"])
    df["overdue"] = ~df["is_done"] & (df["due_date"] < AS_OF)
    df["days_overdue"] = (AS_OF - df["due_date"]).dt.days.where(df["overdue"], 0)
    df["due_soon"] = ~df["is_done"] & df["due_date"].between(AS_OF, AS_OF + pd.Timedelta(days=7))
    return df


def collateral_summary(col):
    n = len(col)
    return {"total": n, "done": int(col["is_done"].sum()), "overdue": int(col["overdue"].sum()),
            "due_soon": int(col["due_soon"].sum()), "completion_rate": _div(col["is_done"].sum(), n),
            "open_hours": float(col.loc[~col["is_done"], "effort_hours"].sum())}


def collateral_workload(col):
    """Open items, overdue items and open effort hours per owner."""
    if col.empty:
        return pd.DataFrame(columns=["owner", "open_items", "overdue", "open_hours"])
    o = col[~col["is_done"]]
    g = o.groupby("owner").agg(open_items=("item_id", "count"), overdue=("overdue", "sum"), open_hours=("effort_hours", "sum"))
    return g.reindex(sorted(col["owner"].unique()), fill_value=0).reset_index()


# ------------------------------------------------------------------ revenue & gross profit
def _targets(targets, owners):
    t = targets[targets["sales_owner"].isin(owners)]
    return t[t["month"] <= "2026-12"]


def monthly_revenue_gp(opps, targets, owners):
    """One row per month of 2026: targets, REALIZED (Won) and WEIGHTED FORECAST (open deals) for revenue and GP."""
    t = _targets(targets, owners).groupby("month")[["target", "gp_target"]].sum()
    out = t.rename(columns={"target": "rev_target", "gp_target": "gp_target"})
    won = opps[opps["stage"] == "Won"].copy()
    won["month"] = won["expected_close_date"].dt.strftime("%Y-%m")
    op = opps[opps["is_open"]].copy()
    op["month"] = op["expected_close_date"].dt.strftime("%Y-%m")
    op["w_rev"] = op["expected_revenue"] * op["close_probability"]
    out["rev_actual"] = won.groupby("month")["expected_revenue"].sum()
    out["gp_actual"] = won.groupby("month")["expected_gross_profit"].sum()
    out["rev_forecast"] = op.groupby("month")["w_rev"].sum()
    out["gp_forecast"] = op.groupby("month")["weighted_gp"].sum()
    out = out.fillna(0).reset_index()
    out["gp_margin"] = out.apply(lambda r: _div(r["gp_actual"], r["rev_actual"]), axis=1)
    return out


def forecast_gap(opps, targets, owners):
    """Full-year 2026 outlook: target vs realized vs weighted forecast closing by year-end."""
    t = _targets(targets, owners)
    fy_rev, fy_gp = float(t["target"].sum()), float(t["gp_target"].sum())
    won = opps[opps["stage"] == "Won"]
    op = opps[opps["is_open"] & (opps["expected_close_date"] <= FY_END)]
    rev_won, gp_won = float(won["expected_revenue"].sum()), float(won["expected_gross_profit"].sum())
    rev_fc = float((op["expected_revenue"] * op["close_probability"]).sum())
    gp_fc = float(op["weighted_gp"].sum())
    to_go = max(fy_rev - rev_won, 0)
    commit = op[op["stage"].isin(["Proposal", "Negotiation"])]       # conservative: only late-stage deals
    rev_commit = rev_won + float((commit["expected_revenue"] * commit["close_probability"]).sum())
    stalled_w = float(op.loc[op["days_since_activity"] > m.STALL_DAYS, "weighted_value"].sum())
    return {"fy_rev_target": fy_rev, "fy_gp_target": fy_gp, "rev_won": rev_won, "gp_won": gp_won,
            "rev_forecast": rev_fc, "gp_forecast": gp_fc,
            "rev_commit": rev_commit, "commit_gap": fy_rev - rev_commit, "stalled_weighted": stalled_w,
            "rev_risk_adjusted": rev_won + rev_fc - stalled_w, "risk_gap": fy_rev - (rev_won + rev_fc - stalled_w),
            "rev_gap": fy_rev - rev_won - rev_fc, "gp_gap": fy_gp - gp_won - gp_fc,
            "rev_attainment": _div(rev_won, fy_rev), "gp_attainment": _div(gp_won, fy_gp),
            "open_fy_pipeline": float(op["deal_value"].sum()), "coverage": _div(op["deal_value"].sum(), to_go),
            "months_left": max(12 - AS_OF.month, 0) + 1}


def projected_vs_realized_gp(opps):
    """Per owner: GP already realized (Won) vs weighted projected GP from open deals."""
    if opps.empty:
        return pd.DataFrame(columns=["sales_owner", "realized_gp", "projected_gp"])
    g = pd.DataFrame({"realized_gp": opps[opps["stage"] == "Won"].groupby("sales_owner")["expected_gross_profit"].sum(),
                      "projected_gp": opps[opps["is_open"]].groupby("sales_owner")["weighted_gp"].sum()}).fillna(0)
    return g.reset_index().rename(columns={"index": "sales_owner"})


def win_loss_reasons(opps):
    closed = opps[~opps["is_open"] & (opps["outcome_reason"].fillna("") != "")]
    if closed.empty:
        return pd.DataFrame(columns=["stage", "outcome_reason", "deals", "value"])
    return closed.groupby(["stage", "outcome_reason"]).agg(deals=("opportunity_id", "count"),
                                                           value=("deal_value", "sum")).reset_index()


# ------------------------------------------------------------------ pipeline trend
def pipeline_trend(opps, months=("2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10")):
    """Open pipeline value at each month-end (today for the current month), rebuilt from created and close dates.
    A deal counts as 'open' at date D if it was created on/before D and had not yet closed (Won/Lost) by D."""
    rows = []
    for mo in months:
        d = min(pd.Period(mo).end_time.normalize(), AS_OF)
        created = opps["created_date"] <= d
        still_open = opps["is_open"] | (opps["expected_close_date"] > d)
        live = opps[created & still_open]
        won_to_date = opps[(opps["stage"] == "Won") & (opps["expected_close_date"] <= d)]
        rows.append({"month": mo, "open_pipeline": float(live["deal_value"].sum()), "deals": len(live),
                     "won_to_date": float(won_to_date["expected_revenue"].sum())})
    return pd.DataFrame(rows)


def pipeline_created_by_month(opps):
    c = opps.dropna(subset=["created_date"]).copy()
    c["month"] = c["created_date"].dt.strftime("%Y-%m")
    return c.groupby("month").agg(created=("opportunity_id", "count"), value=("deal_value", "sum")).reset_index()
