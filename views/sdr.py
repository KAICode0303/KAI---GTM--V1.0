"""Module 4 - SDR Activity (dedicated analytics tab)."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analytics as a
import theme
from theme import kpi_card, page_header, section, style
from views.common import note, show_table

CHANNELS = ["cold_calls", "emails_sent", "linkedin_outreach"]


def render(ws, raw_sdr_dates=None):
    page_header("SDR Activity", "Daily and weekly outreach, response and conversion: who is doing what, and how it compares with target.")
    s_all = ws.sdr
    if s_all.empty:
        theme.empty_state("No SDR activity in this period", "Widen the date range or owner filter in the sidebar.", "📭")
        return

    # local filters
    f1, f2, f3 = st.columns([2, 2, 1])
    reps = f1.multiselect("Reps", ws.owners, default=ws.owners, key="sdr_reps")
    lo, hi = s_all["date"].min().date(), s_all["date"].max().date()
    rng = f2.date_input("Dates", (lo, hi), min_value=lo, max_value=hi, key="sdr_dates")
    grain = f3.radio("View", ["Weekly", "Daily"], horizontal=True, key="sdr_grain")
    start, end = (rng[0], rng[1]) if isinstance(rng, (tuple, list)) and len(rng) == 2 else (lo, hi)
    s = s_all[s_all["owner"].isin(reps) & s_all["date"].between(pd.Timestamp(start), pd.Timestamp(end))]
    if s.empty:
        theme.empty_state("No activity for this selection", "Pick at least one rep and a valid date range.", "📭")
        return

    t = a.sdr_totals(s)
    cols = st.columns(6)
    cards = [("Outreach touches", f"{t['touches']:,}", f"{t['cold_calls']:,} calls · {t['emails_sent']:,} emails · {t['linkedin_outreach']:,} LinkedIn", "📣"),
             ("Response rate", f"{t['response_rate']:.1%}", f"{t['positive_responses']:,} positive responses", "💬"),
             ("Qualified leads", f"{t['qualified_leads']}", f"{t['response_to_qualified']:.1%} of positive responses", "✅"),
             ("Meetings booked", f"{t['meetings_booked']}", f"{t['qualified_to_meeting']:.0%} of qualified leads", "📅"),
             ("Meetings held", f"{t['meetings_held']}", f"{t['show_rate']:.0%} show rate", "🤝"),
             ("Accounts researched", f"{t['accounts_researched']:,}", f"{t['follow_ups']:,} follow-ups sent", "🔎")]
    for col, c in zip(cols, cards):
        with col:
            kpi_card(c[0], c[1], c[2], "SDR", c[3])
    note("Qualified leads and meetings count <b>SDR-sourced</b> leads (outbound and LinkedIn). The Command Center shows leads from <b>all</b> sources.")

    tab1, tab2, tab3, tab4 = st.tabs(["Trends", "Leaderboard", "Targets vs actuals", "Activity log"])
    with tab1:
        tr = a.sdr_trend(s, "W" if grain == "Weekly" else "D")
        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            fig = go.Figure()
            for ch, color in zip(CHANNELS, ["#00C7D1", "#5B8DEF", "#9B7BFF"]):
                fig.add_bar(x=tr["period"], y=tr[ch], name=a.SDR_LABELS[ch], marker_color=color)
            fig.update_layout(barmode="stack", title=f"Outreach volume ({grain.lower()})")
            st.plotly_chart(style(fig, 340))
        with c2, st.container(border=True):
            fig = go.Figure()
            fig.add_scatter(x=tr["period"], y=tr["response_rate"], name="Response rate", mode="lines+markers", line=dict(color="#2BE57E", width=3), yaxis="y")
            fig.add_bar(x=tr["period"], y=tr["meetings_booked"], name="Meetings booked", marker_color="rgba(245,165,36,.55)", yaxis="y2")
            fig.update_layout(title="Productivity: response rate and meetings", yaxis=dict(tickformat=".1%", title="Response rate"),
                              yaxis2=dict(overlaying="y", side="right", showgrid=False, title="Meetings"))
            st.plotly_chart(style(fig, 340))
        with st.container(border=True):
            steps = pd.DataFrame({"step": ["Touches", "Positive responses", "Qualified leads", "Meetings booked", "Meetings held"],
                                  "count": [t["touches"], t["positive_responses"], t["qualified_leads"], t["meetings_booked"], t["meetings_held"]]})
            fig = go.Figure(go.Funnel(y=steps["step"], x=steps["count"], textinfo="value+percent previous",
                                      marker=dict(color=["#5B8DEF", "#00C7D1", "#19D3A0", "#2BE57E", "#F5A524"])))
            fig.update_layout(title="Activity conversion funnel")
            st.plotly_chart(style(fig, 320))
    with tab2:
        lb = a.sdr_by_rep(s)
        lb.insert(0, "rank", range(1, len(lb) + 1))
        with st.container(border=True):
            metric = st.selectbox("Rank reps by", ["meetings_booked", "qualified_leads", "positive_responses", "touches", "response_rate", "productivity"],
                                  format_func=lambda x: a.SDR_LABELS.get(x, x.replace("_", " ").capitalize()), key="sdr_metric")
            d = lb.sort_values(metric)
            fig = px.bar(d, y="owner", x=metric, orientation="h", text=metric, color=metric,
                         color_continuous_scale=["#BFF5F2", "#00C7D1", "#2BE57E"])
            fig.update_traces(texttemplate="%{x:.3~s}")
            fig.update_layout(title="Rep leaderboard", coloraxis_showscale=False, yaxis_title=None)
            st.plotly_chart(style(fig, 150 + 55 * len(d)))
        show_table(lb[["rank", "owner", "touches", "positive_responses", "response_rate", "qualified_leads", "meetings_booked", "meetings_held", "productivity"]], {
            "rank": "#", "owner": "Rep", "touches": "Touches", "positive_responses": "Positive", "response_rate": st.column_config.NumberColumn("Response rate", format="percent"),
            "qualified_leads": "Qualified", "meetings_booked": "Booked", "meetings_held": "Held",
            "productivity": st.column_config.NumberColumn("Productivity", format="%.1f", help="(positive + 5×qualified + 8×meetings booked) per 100 touches")})
    with tab3:
        att = a.activity_attainment(s, ws.act_targets, len(reps), start, end)
        with st.container(border=True):
            fig = go.Figure()
            fig.add_bar(y=att["label"], x=att["actual"], name="Actual", orientation="h", marker_color="#00C7D1")
            fig.add_bar(y=att["label"], x=att["target"], name="Target", orientation="h", marker_color="rgba(245,165,36,.55)")
            fig.update_layout(barmode="group", title="Activity actual vs target", yaxis=dict(autorange="reversed"))
            st.plotly_chart(style(fig, 460))
        att["status"] = att["attainment"].map(lambda v: "🟢 On target" if v >= 0.95 else "🟡 Close" if v >= 0.75 else "🔴 Behind")
        show_table(att[["label", "actual", "target", "attainment", "status"]], {
            "label": "Metric", "actual": "Actual", "target": "Target", "attainment": st.column_config.ProgressColumn("Attainment", format="percent", min_value=0, max_value=1.3), "status": "Status"})
        note("Target = weekly target per rep × weeks in the selected period × number of reps selected.")
    with tab4:
        log = s.sort_values("date", ascending=False)
        show_table(log[["date", "owner"] + a.SDR_COLS], {"date": st.column_config.DateColumn("Date", format="ddd MMM D"), "owner": "Rep",
                   **{c: a.SDR_LABELS[c] for c in a.SDR_COLS}}, height=460)
        st.download_button("⬇️ Download log (CSV)", log.to_csv(index=False), "sdr_activity.csv")
