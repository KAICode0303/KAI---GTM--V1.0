"""Module 1 - Executive Command Center."""
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import analytics as a
import hoomi
import metrics as m
import theme
from views import mascot
from metrics import money
from theme import CHART_COLORS, kpi_card, section, style
from views.common import date_col, money_col, note, pick_clicked, show_table

DIMENSIONS = {"Sales rep": "sales_owner", "Region": "region", "Customer segment": "customer_segment", "Service": "service_offering"}


def render(ws, name=""):
    opps = ws.opps
    p = theme.palette()

    # ---- hero with Hoomi
    c1, c2 = st.columns([1, 4], vertical_alignment="center")
    with c1:
        mascot.render(150, caption=False)
    with c2:
        b = hoomi.briefing(ws, name)
        st.markdown(f'<div class="hero" style="margin:0">{theme.sparkles()}<div class="eyebrow">Kai\'s Company</div>'
                    f'<h1>Sales &amp; GTM Command Center</h1><p>{b["greeting"]}</p></div>', unsafe_allow_html=True)

    if opps.empty:
        theme.empty_state("No opportunities match these filters", "Widen the period, owners, regions or other filters in the sidebar.", "🔭")
        return

    k = m.kpis(opps)
    lm = a.lead_metrics(ws.leads, opps)
    n_st, n_ov = len(m.stalled_deals(opps)), len(m.overdue_followups(opps))

    # ---- KPI cards
    r1 = st.columns(6)
    cards1 = [("Open pipeline", money(k["open_pipeline"]), f"{k['open_deals']} open deals", "FORECAST", "🌊", "Sum of deal value for deals not yet Won or Lost"),
              ("Weighted pipeline", money(k["weighted_pipeline"]), "value × close probability", "FORECAST", "⚖️", "Deal value multiplied by closing probability"),
              ("Won revenue", money(k["won_revenue"]), f"{k['won_deals']} won deals", "ACTUAL", "🏆", "Realized revenue from Won deals only"),
              ("Won gross profit", money(k["won_gp"]), "revenue − delivery cost", "ACTUAL", "💎", "Won revenue minus expected delivery cost"),
              ("GP margin", f"{k['gp_margin']:.1%}", "won GP ÷ won revenue", "ACTUAL", "📈", "Gross profit as a share of revenue"),
              ("Win rate", f"{k['win_rate']:.0%}", f"{k['won_deals']} won / {k['lost_deals']} lost", "ACTUAL", "🎯", "Won ÷ (Won + Lost); open deals excluded")]
    for col, c in zip(r1, cards1):
        with col:
            kpi_card(*c[:5], tip=c[5])
    st.write("")
    r2 = st.columns(6)
    cards2 = [("Qualified leads", f"{lm['qualified']:,}", "all sources, in period", "", "✅", "Leads that passed qualification"),
              ("Meetings held", f"{lm['meetings_held']:,}", f"{lm['meetings_booked']} booked", "", "🤝", "Discovery meetings that took place"),
              ("Lead → Opp", f"{lm['lead_to_opp']:.0%}", f"{lm['opportunities']} of {lm['leads']} leads", "", "🔀", "Opportunities ÷ leads"),
              ("Opp → Win", f"{lm['opp_to_win']:.0%}", f"{lm['won']} of {lm['opportunities']} opps", "", "🚀", "Won ÷ all opportunities created"),
              ("Stalled deals", f"{n_st}", f"no activity {m.STALL_DAYS}+ days", "", "⏸️", "Open deals with no activity for more than 30 days"),
              ("Late follow-ups", f"{n_ov}", "next follow-up date passed", "", "⏰", "Open deals whose next follow-up date is in the past")]
    for col, c in zip(r2, cards2):
        with col:
            kpi_card(*c[:5], tip=c[5])

    # ---- executive summary
    g = a.forecast_gap(opps, ws.targets, ws.owners)
    reps = m.summarize_by(opps, "sales_owner")
    regs = m.summarize_by(opps, "region").sort_values("open_pipeline", ascending=False)
    lines = [f"Open pipeline is <b>{money(k['open_pipeline'])}</b> (<b>{money(k['weighted_pipeline'])}</b> weighted). "
             f"Realized revenue is <b>{money(k['won_revenue'])}</b> with <b>{money(k['won_gp'])}</b> gross profit at a <b>{k['gp_margin']:.1%}</b> margin; "
             f"win rate is <b>{k['win_rate']:.0%}</b>.",
             f"<b>{reps.iloc[0]['sales_owner']}</b> leads on Won revenue and <b>{regs.iloc[0]['region']}</b> holds the largest open pipeline.",
             f"Against the full-year revenue plan of <b>{money(g['fy_rev_target'])}</b>, <b>{g['rev_attainment']:.0%}</b> is realized; "
             f"after removing stalled deals the forecast is {'short' if g['risk_gap'] > 0 else 'ahead'} by <b>{money(abs(g['risk_gap']))}</b>."]
    st.write("")
    with st.container(border=True):
        st.markdown("**📋 Executive summary**")
        st.markdown(theme.safe("<br>".join(lines)), unsafe_allow_html=True)
        if n_st or n_ov:
            note(theme.safe(f"⚠️ <b>{n_st} stalled deals</b> ({money(m.stalled_deals(opps)['deal_value'].sum())}) and <b>{n_ov} overdue follow-ups</b> need attention."), "warn")

    # ---- funnels
    section("Pipeline & conversion", "stage snapshot today and lead-to-win journey")
    c1, c2 = st.columns(2)
    fn = m.funnel(opps)
    fo = fn[fn["stage"].isin(m.OPEN_STAGES + ["Won"])]
    with c1, st.container(border=True):
        fig = go.Figure(go.Funnel(y=fo["stage"], x=fo["value"], texttemplate="%{x:$,.0s}", textposition="inside",
                                  marker=dict(color=["#00C7D1", "#19CFC6", "#33D6B8", "#4EDDA6", "#6BE48F", "#2BE57E"][:len(fo)]),
                                  hovertemplate="%{y}: %{x:$,.0f}<extra></extra>"))
        fig.update_layout(title="Deal value by current stage (Won = realized)")
        st.plotly_chart(style(fig, 360))
    with c2, st.container(border=True):
        cf = a.conversion_funnel(ws.leads, opps)
        fig = go.Figure(go.Funnel(y=cf["stage"], x=cf["count"], textinfo="value+percent previous",
                                  marker=dict(color=["#5B8DEF", "#00C7D1", "#2BE57E", "#F5A524", "#9B7BFF"])))
        fig.update_layout(title="Lead → Qualified → Meeting → Opportunity → Won")
        st.plotly_chart(style(fig, 360))

    # ---- trend + targets
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        tr = a.pipeline_trend(opps)
        fig = go.Figure()
        fig.add_scatter(x=tr["month"], y=tr["open_pipeline"], name="Open pipeline (forecast)", fill="tozeroy", mode="lines+markers",
                        line=dict(color="#5B8DEF", width=3), fillcolor="rgba(91,141,239,.14)")
        fig.add_scatter(x=tr["month"], y=tr["won_to_date"], name="Won to date (realized)", mode="lines+markers", line=dict(color="#2BE57E", width=3))
        fig.update_layout(title="Pipeline trend (month-end)", yaxis_tickprefix="$", yaxis_tickformat="~s")
        st.plotly_chart(style(fig, 340))
    with c2, st.container(border=True):
        mr = a.monthly_revenue_gp(opps, ws.targets, ws.owners)
        mr = mr[mr["month"] <= "2026-12"]
        fig = go.Figure()
        fig.add_bar(x=mr["month"], y=mr["rev_actual"], name="Won (realized)", marker_color="#2BE57E")
        fig.add_bar(x=mr["month"], y=mr["rev_forecast"], name="Weighted forecast", marker_color="rgba(91,141,239,.45)")
        fig.add_scatter(x=mr["month"], y=mr["rev_target"], name="Target", mode="lines+markers", line=dict(color="#F5A524", width=3))
        fig.update_layout(title="Monthly target vs actual", barmode="stack", yaxis_tickprefix="$", yaxis_tickformat="~s")
        st.plotly_chart(style(fig, 340))

    # ---- performance with drilldown
    section("Performance & drilldown", "click a bar to see the deals behind it")
    dim_label = st.radio("Break down by", list(DIMENSIONS), horizontal=True, label_visibility="collapsed")
    col = DIMENSIONS[dim_label]
    g = m.summarize_by(opps, col).sort_values("won_revenue")
    with st.container(border=True):
        fig = go.Figure()
        fig.add_bar(y=g[col], x=g["won_revenue"], name="Won revenue", orientation="h", marker_color="#2BE57E")
        fig.add_bar(y=g[col], x=g["won_gp"], name="Won gross profit", orientation="h", marker_color="#00C7D1")
        fig.add_bar(y=g[col], x=g["weighted_pipeline"], name="Weighted pipeline", orientation="h", marker_color="#5B8DEF")
        fig.update_layout(barmode="group", title=f"Performance by {dim_label.lower()}", xaxis_tickprefix="$", xaxis_tickformat="~s")
        event = st.plotly_chart(style(fig, 150 + 70 * len(g)), on_select="rerun", selection_mode="points", key=f"drill_{col}")
    picked = pick_clicked(event, "y")
    options = ["(all)"] + list(g[col][::-1])
    chosen = st.selectbox("Drill into", options, index=options.index(picked) if picked in options else 0, key=f"drill_sel_{col}_{picked}")
    sub = opps if chosen == "(all)" else opps[opps[col] == chosen]
    with st.expander(f"Deals: {chosen} ({len(sub)})", expanded=chosen != "(all)"):
        show_table(sub.sort_values("deal_value", ascending=False)[["opportunity_id", "client_name", "sales_owner", "stage", "deal_value",
                   "close_probability", "expected_gross_profit", "next_action"]], {
            "opportunity_id": "ID", "client_name": "Client", "sales_owner": "Owner", "stage": "Stage", "deal_value": money_col("Deal value"),
            "close_probability": st.column_config.ProgressColumn("Close prob.", format="percent", min_value=0, max_value=1),
            "expected_gross_profit": money_col("Exp. GP"), "next_action": "Next action"}, height=300)

    # ---- attention
    section("Needs attention", "stalled deals and overdue follow-ups")
    c1, c2 = st.columns(2)
    with c1, st.container(border=True):
        st.markdown(f"**⏸️ Stalled deals ({n_st})**")
        s = m.stalled_deals(opps)
        if s.empty:
            theme.empty_state("Nothing stalled", "Every open deal had activity in the last 30 days.", "🎉")
        else:
            show_table(s[["client_name", "sales_owner", "stage", "deal_value", "days_since_activity", "next_action"]], {
                "client_name": "Client", "sales_owner": "Owner", "stage": "Stage", "deal_value": money_col("Value"),
                "days_since_activity": st.column_config.NumberColumn("Days quiet"), "next_action": "Next action"}, height=280)
    with c2, st.container(border=True):
        st.markdown(f"**⏰ Overdue follow-ups ({n_ov})**")
        o = m.overdue_followups(opps)
        if o.empty:
            theme.empty_state("All caught up", "No follow-up dates have passed.", "🎉")
        else:
            show_table(o[["client_name", "sales_owner", "stage", "next_follow_up_date", "days_overdue", "next_action"]], {
                "client_name": "Client", "sales_owner": "Owner", "stage": "Stage", "next_follow_up_date": date_col("Follow-up due"),
                "days_overdue": st.column_config.NumberColumn("Days overdue"), "next_action": "Next action"}, height=280)
