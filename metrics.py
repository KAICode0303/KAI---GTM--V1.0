"""All business calculations live here, so the dashboard (app.py) and Hoomi (hoomi.py)
always agree on the numbers.

Financial definitions used everywhere:
  Open pipeline      = sum of deal_value for open deals (not Won / Lost)
  Weighted pipeline  = sum of deal_value x close_probability for open deals
  Won revenue        = sum of expected_revenue for Won deals  (actual, not forecast)
  Won gross profit   = sum of expected_gross_profit for Won deals  (revenue - delivery cost)
  GP margin          = Won gross profit / Won revenue
  Win rate           = Won deals / (Won + Lost deals)   (open deals are not counted)
"""
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
AS_OF = pd.Timestamp("2026-10-08")  # "today" in our fictional dataset
STALL_DAYS = 30                      # open deal with no activity for this long = stalled
HIGH_VALUE = 500_000                 # open deal at or above this = high value
STAGES = ["Prospecting", "Qualified", "Discovery", "Proposal", "Negotiation", "Won", "Lost"]
OPEN_STAGES = STAGES[:5]


def load_data(path=None):
    """Read the opportunities CSV and add a few helper columns."""
    return prepare_opps(pd.read_csv(path or DATA_DIR / "opportunities.csv"))


def prepare_opps(df):
    """Parse dates and add helper columns. Works on data from the CSV or from the SQLite database."""
    df = df.copy()
    for c in ["expected_close_date", "last_activity_date", "created_date", "next_follow_up_date"]:
        if c in df.columns:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    df["is_open"] = df["stage"].isin(OPEN_STAGES)
    df["weighted_value"] = df["deal_value"] * df["close_probability"]
    df["weighted_gp"] = df["expected_gross_profit"] * df["close_probability"]
    df["days_since_activity"] = (AS_OF - df["last_activity_date"]).dt.days
    if "next_follow_up_date" in df.columns:
        df["overdue_followup"] = df["is_open"] & (df["next_follow_up_date"] < AS_OF)
        df["days_overdue"] = (AS_OF - df["next_follow_up_date"]).dt.days.where(df["overdue_followup"], 0)
    if "created_date" in df.columns:
        end = df["expected_close_date"].where(~df["is_open"], AS_OF)   # closed deals age until they closed
        df["deal_age_days"] = (end - df["created_date"]).dt.days
    return df


def load_targets(path=None):
    return pd.read_csv(path or DATA_DIR / "targets.csv")


def money(x):
    """Format dollars compactly: 1_250_000 -> '$1.25M', 480_000 -> '$480K'."""
    x = float(x)
    if abs(x) >= 1_000_000:
        return f"${x / 1_000_000:.2f}M"
    if abs(x) >= 1_000:
        return f"${x / 1_000:.0f}K"
    return f"${x:.0f}"


def _safe_div(a, b):
    return a / b if b else 0.0


def kpis(df):
    """Headline numbers for any (possibly filtered) set of deals. Safe on empty data."""
    open_df = df[df["is_open"]]
    won = df[df["stage"] == "Won"]
    lost = df[df["stage"] == "Lost"]
    return {
        "open_pipeline": float(open_df["deal_value"].sum()),
        "weighted_pipeline": float(open_df["weighted_value"].sum()),
        "won_revenue": float(won["expected_revenue"].sum()),
        "won_gp": float(won["expected_gross_profit"].sum()),
        "gp_margin": _safe_div(won["expected_gross_profit"].sum(), won["expected_revenue"].sum()),
        "win_rate": _safe_div(len(won), len(won) + len(lost)),
        "open_deals": int(len(open_df)),
        "won_deals": int(len(won)),
        "lost_deals": int(len(lost)),
    }


def funnel(df):
    """Deal count, value and weighted value per stage, in pipeline order."""
    g = df.groupby("stage").agg(deals=("opportunity_id", "count"),
                                value=("deal_value", "sum"),
                                weighted=("weighted_value", "sum"))
    return g.reindex(STAGES, fill_value=0).reset_index()


def summarize_by(df, column):
    """Open pipeline, weighted pipeline, won revenue and won GP grouped by `column`
    (sales_owner, region, customer_segment or service_offering)."""
    if df.empty:
        return pd.DataFrame(columns=[column, "deals", "open_pipeline", "weighted_pipeline",
                                     "won_revenue", "won_gp", "gp_margin", "win_rate"])
    rows = []
    for name, part in df.groupby(column):
        k = kpis(part)
        rows.append({column: name, "deals": len(part), "open_pipeline": k["open_pipeline"],
                     "weighted_pipeline": k["weighted_pipeline"], "won_revenue": k["won_revenue"],
                     "won_gp": k["won_gp"], "gp_margin": k["gp_margin"], "win_rate": k["win_rate"]})
    return pd.DataFrame(rows).sort_values("won_revenue", ascending=False).reset_index(drop=True)


def targets_vs_actuals(df, targets, owners=None):
    """Monthly target vs Won revenue, from January up to the current month (AS_OF).

    Targets belong to reps, so only the sales-owner filter changes the target.
    Returns (by_month, by_rep) DataFrames."""
    last_month = AS_OF.strftime("%Y-%m")
    t = targets[targets["month"] <= last_month]
    if owners:
        t = t[t["sales_owner"].isin(owners)]
    won = df[df["stage"] == "Won"].copy()
    won["month"] = won["expected_close_date"].dt.strftime("%Y-%m")

    by_month = t.groupby("month")["target"].sum().to_frame("target")
    by_month["actual"] = won.groupby("month")["expected_revenue"].sum()
    by_month = by_month.fillna(0).reset_index()

    by_rep = t.groupby("sales_owner")["target"].sum().to_frame("target")
    by_rep["actual"] = won.groupby("sales_owner")["expected_revenue"].sum()
    by_rep = by_rep.fillna(0).reset_index()
    by_rep["attainment"] = by_rep.apply(lambda r: _safe_div(r["actual"], r["target"]), axis=1)
    return by_month, by_rep


def stalled_deals(df, days=STALL_DAYS):
    """Open deals with no activity for more than `days` days, most stale first."""
    s = df[df["is_open"] & (df["days_since_activity"] > days)]
    return s.sort_values("days_since_activity", ascending=False)


def at_risk_deals(df):
    """Open deals that look risky: stalled, or late-stage (Proposal/Negotiation)
    with no activity for over 14 days."""
    late = df["stage"].isin(["Proposal", "Negotiation"]) & (df["days_since_activity"] > 14)
    stalled = df["days_since_activity"] > STALL_DAYS
    r = df[df["is_open"] & (late | stalled)]
    return r.sort_values("weighted_value", ascending=False)


def high_value_deals(df, threshold=HIGH_VALUE):
    h = df[df["is_open"] & (df["deal_value"] >= threshold)]
    return h.sort_values("deal_value", ascending=False)


def overdue_followups(df):
    """Open deals whose next follow-up date has passed, most overdue first."""
    if "overdue_followup" not in df.columns:
        return df.iloc[0:0]
    return df[df["overdue_followup"]].sort_values("days_overdue", ascending=False)
