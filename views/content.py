"""Module 5 - Content & Collaterals."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analytics as a
import metrics as m
import theme
from theme import kpi_card, page_header, section, style
from views.common import date_col, note, search, show_table

STATUS_ORDER = ["Not Started", "Drafting", "In Review", "Approved", "Delivered"]
APPROVAL_ORDER = ["Draft", "Manager Review", "Legal Review", "Final Approval", "Approved"]


def render(ws):
    page_header("Content & Collaterals", "Capability decks, case studies, proposals, campaigns and RFPs: who owns what, what's late, what's next.")
    c = ws.collateral
    if c.empty:
        theme.empty_state("No collateral items", "Widen the filters in the sidebar.", "📄")
        return
    f1, f2, f3, f4 = st.columns([2, 2, 2, 3])
    types = f1.multiselect("Type", sorted(c["content_type"].unique()), key="col_type", placeholder="All types")
    status = f2.multiselect("Status", STATUS_ORDER, key="col_status", placeholder="All statuses")
    pri = f3.multiselect("Priority", ["High", "Medium", "Low"], key="col_pri", placeholder="All")
    q = f4.text_input("🔎 Search title, owner, next action", key="col_q")
    d = c
    if types:
        d = d[d["content_type"].isin(types)]
    if status:
        d = d[d["status"].isin(status)]
    if pri:
        d = d[d["priority"].isin(pri)]
    d = search(d, q, ["item_id", "title", "owner", "next_action", "customer_segment"])
    if d.empty:
        theme.empty_state("Nothing matches", "Clear a filter or search term.", "🔍")
        return

    s = a.collateral_summary(d)
    cols = st.columns(5)
    for col, card in zip(cols, [("Items", f"{s['total']}", f"{s['done']} approved or delivered", "📚"), ("Completion", f"{s['completion_rate']:.0%}", "approved + delivered", "✅"),
                                ("Overdue", f"{s['overdue']}", "past due date, not done", "⏰"), ("Due in 7 days", f"{s['due_soon']}", "upcoming deadlines", "🗓️"),
                                ("Open effort", f"{s['open_hours']:.0f} h", "estimated hours remaining", "⏳")]):
        with col:
            kpi_card(card[0], card[1], card[2], "", card[3])

    st.write("")
    tab1, tab2, tab3 = st.tabs(["Analytics", "Tracker", "Overdue & next actions"])
    with tab1:
        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            g = d.groupby(["content_type", "status"]).size().reset_index(name="items")
            fig = px.bar(g, y="content_type", x="items", color="status", orientation="h", category_orders={"status": STATUS_ORDER},
                         color_discrete_sequence=["#B7C9CC", "#5B8DEF", "#F5A524", "#2BE57E", "#00C7D1"])
            fig.update_layout(title="Status by content type", yaxis_title=None)
            st.plotly_chart(style(fig, 360))
        with c2, st.container(border=True):
            w = a.collateral_workload(d)
            fig = go.Figure()
            fig.add_bar(x=w["owner"], y=w["open_items"], name="Open items", marker_color="#00C7D1")
            fig.add_bar(x=w["owner"], y=w["overdue"], name="Overdue", marker_color="#FF7A8A")
            fig.add_scatter(x=w["owner"], y=w["open_hours"], name="Open hours", mode="lines+markers", yaxis="y2", line=dict(color="#F5A524", width=3))
            fig.update_layout(title="Workload by owner", barmode="group", yaxis2=dict(overlaying="y", side="right", showgrid=False, title="Hours"))
            st.plotly_chart(style(fig, 360))
        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            ap = d.groupby("approval_stage").size().reindex(APPROVAL_ORDER, fill_value=0).reset_index(name="items")
            fig = go.Figure(go.Funnel(y=ap["approval_stage"], x=ap["items"], textinfo="value", marker=dict(color=["#B7C9CC", "#5B8DEF", "#9B7BFF", "#F5A524", "#2BE57E"])))
            fig.update_layout(title="Approval pipeline")
            st.plotly_chart(style(fig, 320))
        with c2, st.container(border=True):
            t = d.assign(week=d["due_date"].dt.to_period("W-SUN").dt.start_time)
            g = t.groupby(["week", "is_done"]).size().reset_index(name="items")
            g["state"] = g["is_done"].map({True: "Done", False: "Open"})
            fig = px.bar(g, x="week", y="items", color="state", color_discrete_map={"Done": "#2BE57E", "Open": "#F5A524"})
            fig.add_vline(x=m.AS_OF.timestamp() * 1000, line_dash="dash", line_color="#FF7A8A", annotation_text="today")
            fig.update_layout(title="Deadlines by week")
            st.plotly_chart(style(fig, 320))
    with tab2:
        show_table(d.sort_values(["is_done", "due_date"])[["item_id", "title", "content_type", "owner", "status", "approval_stage", "priority", "due_date", "days_overdue",
                                                          "account_id", "opportunity_id", "customer_segment", "next_action"]], {
            "item_id": "ID", "title": "Title", "content_type": "Type", "owner": "Owner", "status": "Status", "approval_stage": "Approval", "priority": "Priority",
            "due_date": date_col("Due"), "days_overdue": st.column_config.NumberColumn("Days overdue"), "account_id": "Account", "opportunity_id": "Opportunity",
            "customer_segment": "Segment", "next_action": "Next action"}, height=500)
        st.download_button("⬇️ Download (CSV)", d.to_csv(index=False), "collateral.csv")
    with tab3:
        o = d[d["overdue"]].sort_values(["priority", "days_overdue"], ascending=[True, False])
        if o.empty:
            theme.empty_state("Nothing overdue", "All collateral is on schedule.", "🎉")
        for r in o.itertuples():
            st.markdown(f'<div class="warn"><b>{r.title}</b> · {r.owner} · {r.priority} priority · <b>{int(r.days_overdue)} days overdue</b><br>'
                        f'<span style="opacity:.8">Status: {r.status} ({r.approval_stage}) → Next: {r.next_action}</span></div>', unsafe_allow_html=True)
