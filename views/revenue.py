"""Module 7 - Revenue & Gross Profit."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analytics as a
import metrics as m
import theme
from metrics import money
from theme import kpi_card, page_header, section, style
from views.common import note, show_table, money_col


def render(ws):
    page_header("Revenue & Gross Profit", "Targets, realized results and weighted forecast. Open pipeline is never counted as realized revenue.")
    opps = ws.opps
    if opps.empty:
        theme.empty_state("No data for these filters", "Widen the filters in the sidebar.", "💸")
        return
    k, g = m.kpis(opps), a.forecast_gap(opps, ws.targets, ws.owners)

    cols = st.columns(6)
    cards = [("Realized revenue", money(g["rev_won"]), f"{g['rev_attainment']:.0%} of FY target {money(g['fy_rev_target'])}", "ACTUAL", "🏆"),
             ("Realized GP", money(g["gp_won"]), f"{g['gp_attainment']:.0%} of FY GP target {money(g['fy_gp_target'])}", "ACTUAL", "💎"),
             ("GP margin", f"{k['gp_margin']:.1%}", "realized GP ÷ realized revenue", "ACTUAL", "📈"),
             ("Weighted revenue forecast", money(g["rev_forecast"]), "open deals closing by Dec 31", "FORECAST", "⚖️"),
             ("Projected GP (weighted)", money(g["gp_forecast"]), "open deals closing by Dec 31", "FORECAST", "🔮"),
             ("Risk-adjusted gap", money(abs(g["risk_gap"])), "short of plan" if g["risk_gap"] > 0 else "ahead of plan", "FORECAST", "🧭")]
    for col, c in zip(cols, cards):
        with col:
            kpi_card(*c)
    note("<b>How to read this:</b> <b>Realized</b> = Won deals only. <b>Weighted forecast</b> = open deal value × close probability. "
         "<b>Risk-adjusted</b> also removes the weighted value of stalled deals.")

    mr = a.monthly_revenue_gp(opps, ws.targets, ws.owners)
    tab1, tab2, tab3, tab4 = st.tabs(["Monthly trends", "Forecast gap", "By region · service · rep", "Win / loss"])

    with tab1:
        c1, c2 = st.columns(2)
        for col, title, act, fc, tgt in [(c1, "Revenue", "rev_actual", "rev_forecast", "rev_target"), (c2, "Gross profit", "gp_actual", "gp_forecast", "gp_target")]:
            with col, st.container(border=True):
                fig = go.Figure()
                fig.add_bar(x=mr["month"], y=mr[act], name="Realized (Won)", marker_color="#2BE57E")
                fig.add_bar(x=mr["month"], y=mr[fc], name="Weighted forecast (open)", marker_color="rgba(91,141,239,.45)")
                fig.add_scatter(x=mr["month"], y=mr[tgt], name="Target", mode="lines+markers", line=dict(color="#F5A524", width=3))
                fig.update_layout(title=f"{title}: target vs realized vs forecast", barmode="stack", yaxis_tickprefix="$", yaxis_tickformat="~s")
                st.plotly_chart(style(fig, 360))
        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            mm = mr[mr["rev_actual"] > 0]
            fig = go.Figure(go.Scatter(x=mm["month"], y=mm["gp_margin"], mode="lines+markers", line=dict(color="#00C7D1", width=3)))
            fig.update_layout(title="Realized GP margin by month", yaxis_tickformat=".0%")
            if mm.empty:
                theme.empty_state("No Won deals yet", "", "📉")
            else:
                st.plotly_chart(style(fig, 300))
        with c2, st.container(border=True):
            pg = a.projected_vs_realized_gp(opps)
            fig = go.Figure()
            fig.add_bar(x=pg["sales_owner"], y=pg["realized_gp"], name="Realized GP", marker_color="#2BE57E")
            fig.add_bar(x=pg["sales_owner"], y=pg["projected_gp"], name="Projected GP (weighted, open)", marker_color="rgba(91,141,239,.55)")
            fig.update_layout(title="Projected vs realized GP by rep", barmode="group", yaxis_tickprefix="$", yaxis_tickformat="~s")
            st.plotly_chart(style(fig, 300))

    with tab2:
        with st.container(border=True):
            fig = go.Figure(go.Waterfall(
                orientation="v", x=["FY revenue target", "Realized (Won)", "Weighted forecast", "Stalled deals (risk)", "Risk-adjusted gap"],
                measure=["absolute", "relative", "relative", "relative", "total"],
                y=[g["fy_rev_target"], -g["rev_won"], -g["rev_forecast"], g["stalled_weighted"], g["risk_gap"]],
                connector=dict(line=dict(color="rgba(0,160,170,.4)")), increasing=dict(marker=dict(color="#F5A524")),
                decreasing=dict(marker=dict(color="#2BE57E")), totals=dict(marker=dict(color="#5B8DEF")),
                texttemplate="%{y:$,.3~s}"))
            fig.update_layout(title="From plan to forecast: what is still uncovered?", yaxis_tickprefix="$", yaxis_tickformat="~s")
            st.plotly_chart(style(fig, 400))
        c1, c2, c3 = st.columns(3)
        with c1:
            kpi_card("Open pipeline (closing by Dec 31)", money(g["open_fy_pipeline"]), f"{g['coverage']:.1f}× coverage of remaining target", "FORECAST", "🌊")
        with c2:
            kpi_card("Commit view gap", money(abs(g["commit_gap"])), "ahead of plan" if g["commit_gap"] < 0 else "short (Won + Proposal/Negotiation only)", "FORECAST", "🔒")
        with c3:
            need = max(g["fy_rev_target"] - g["rev_won"], 0) / max(g["months_left"], 1)
            kpi_card("Needed per month", money(need), f"to hit plan in {g['months_left']} remaining months", "", "🗓️")
        note("Forecast gap = FY target − realized − weighted forecast. A <b>negative</b> gap means the weighted forecast covers the plan; "
             "the risk-adjusted view removes stalled deals, which are the least reliable part of the forecast.")

    with tab3:
        dim = st.radio("Break down by", ["Region", "Service", "Sales rep"], horizontal=True, key="rev_dim")
        col = {"Region": "region", "Service": "service_offering", "Sales rep": "sales_owner"}[dim]
        d = m.summarize_by(opps, col).sort_values("won_revenue")
        with st.container(border=True):
            fig = go.Figure()
            fig.add_bar(y=d[col], x=d["won_revenue"], name="Realized revenue", orientation="h", marker_color="#2BE57E")
            fig.add_bar(y=d[col], x=d["won_gp"], name="Realized GP", orientation="h", marker_color="#00C7D1")
            fig.add_bar(y=d[col], x=d["weighted_pipeline"], name="Weighted pipeline", orientation="h", marker_color="rgba(91,141,239,.55)")
            fig.update_layout(barmode="group", title=f"Revenue and GP by {dim.lower()}", xaxis_tickprefix="$", xaxis_tickformat="~s")
            st.plotly_chart(style(fig, 140 + 70 * len(d)))
        show_table(d.sort_values("won_revenue", ascending=False).rename(columns={col: dim}).drop(columns=["deals"]), {
            "open_pipeline": money_col("Open pipeline"), "weighted_pipeline": money_col("Weighted"), "won_revenue": money_col("Won revenue"),
            "won_gp": money_col("Won GP"), "gp_margin": st.column_config.NumberColumn("GP margin", format="percent"),
            "win_rate": st.column_config.NumberColumn("Win rate", format="percent")})

    with tab4:
        c1, c2 = st.columns(2)
        reasons = a.win_loss_reasons(opps)
        with c1, st.container(border=True):
            if reasons.empty:
                theme.empty_state("No closed deals", "", "🏁")
            else:
                fig = go.Figure()
                for stg, color in [("Won", "#2BE57E"), ("Lost", "#FF7A8A")]:
                    r = reasons[reasons["stage"] == stg].sort_values("deals")
                    fig.add_bar(y=r["outcome_reason"], x=r["deals"], name=stg, orientation="h", marker_color=color)
                fig.update_layout(title="Why we win and lose", barmode="group")
                st.plotly_chart(style(fig, 380))
        with c2, st.container(border=True):
            closed = opps[~opps["is_open"]]
            if closed.empty:
                theme.empty_state("No closed deals", "", "🏁")
            else:
                seg = closed.groupby("customer_segment")["stage"].agg(won=lambda s: (s == "Won").sum(), lost=lambda s: (s == "Lost").sum()).reset_index()
                seg["win_rate"] = seg["won"] / (seg["won"] + seg["lost"])
                fig = go.Figure(go.Bar(y=seg["customer_segment"], x=seg["win_rate"], orientation="h", marker_color="#00C7D1",
                                       text=[f"{w}W / {l}L" for w, l in zip(seg["won"], seg["lost"])]))
                fig.update_layout(title="Win rate by segment", xaxis_tickformat=".0%")
                st.plotly_chart(style(fig, 380))
