"""Module 2 - Market Intelligence & Research (market research, prospecting-tool research, account research)."""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import theme
from theme import kpi_card, page_header, style
from views.common import date_col, note, search, show_table

STATUS_COLORS = {"Completed": "#2BE57E", "Adopted": "#00C7D1", "In Progress": "#5B8DEF", "Planned": "#B7C9CC", "Rejected": "#FF7A8A"}


def _status_cards(df):
    counts = df["status"].value_counts()
    cols = st.columns(4)
    for col, (label, icon) in zip(cols, [("Planned", "🗓️"), ("In Progress", "🔬"), ("Completed", "✅"), ("Total", "📚")]):
        with col:
            kpi_card(label, f"{len(df) if label == 'Total' else int(counts.get(label, 0))}", "", "", icon)


def _detail(df, id_col, title_col, fields):
    """Pick a record and read the full text in a friendly card."""
    pick = st.selectbox("Open a record", df[id_col] + " · " + df[title_col], key=f"detail_{id_col}_{len(df)}")
    r = df[df[id_col] == pick.split(" · ")[0]].iloc[0]
    body = "".join(f"<p style='margin:.35rem 0'><b>{label}:</b> {r[col]}</p>" for label, col in fields)
    st.markdown(f'<div class="bubble">{body}</div>', unsafe_allow_html=True)


def render(ws):
    page_header("Market Intelligence & Research", "Why we chose these markets and accounts, and which prospecting tools are worth using. Demo data only, no live tool connections.")
    tab_m, tab_t, tab_a = st.tabs(["Industry & market research", "Prospecting tool research", "Account research"])

    with tab_m:
        d = ws.market
        if d.empty:
            theme.empty_state("No market research for these filters", "", "🧭")
        else:
            _status_cards(d)
            q = st.text_input("🔎 Search topic, hypothesis, findings", key="mkt_q")
            d = search(d, q, ["topic", "business_hypothesis", "findings", "research_objective", "customer_segment"])
            c1, c2 = st.columns(2)
            with c1, st.container(border=True):
                g = d.groupby(["customer_segment", "status"]).size().reset_index(name="studies")
                fig = px.bar(g, y="customer_segment", x="studies", color="status", orientation="h", color_discrete_map=STATUS_COLORS)
                fig.update_layout(title="Research by segment and status", yaxis_title=None)
                st.plotly_chart(style(fig, 330))
            with c2, st.container(border=True):
                g = d.groupby(["source_tool", "priority"]).size().reset_index(name="studies")
                fig = px.bar(g, x="source_tool", y="studies", color="priority", color_discrete_map={"High": "#FF7A8A", "Medium": "#F5A524", "Low": "#B7C9CC"})
                fig.update_layout(title="Sources used, by priority")
                st.plotly_chart(style(fig, 330))
            show_table(d[["research_id", "topic", "customer_segment", "region", "priority", "status", "owner", "source_tool", "start_date", "next_action"]], {
                "research_id": "ID", "topic": "Topic", "customer_segment": "Segment", "region": "Region", "priority": "Priority", "status": "Status", "owner": "Owner",
                "source_tool": "Source", "start_date": date_col("Started"), "next_action": "Next action"}, height=330)
            if len(d):
                _detail(d, "research_id", "topic", [("Objective", "research_objective"), ("Hypothesis", "business_hypothesis"), ("Findings", "findings"),
                                                  ("What it means for Kai's Company", "implication_for_kai")])

    with tab_t:
        d = ws.tools
        note("This tab compares <b>prospecting and research tools</b> in general (Apollo, ZoomInfo, LinkedIn, etc.). Ratings and findings are fictional demo opinions; nothing is connected to these services.")
        _status_cards(d)
        c1, c2 = st.columns([3, 2])
        with c1, st.container(border=True):
            fig = go.Figure()
            for col, label, color in [("data_coverage", "Data coverage", "#00C7D1"), ("data_accuracy", "Accuracy", "#2BE57E"), ("ease_of_use", "Ease of use", "#5B8DEF"), ("value_for_money", "Value for money", "#F5A524")]:
                fig.add_bar(x=d["tool_name"], y=d[col], name=label, marker_color=color)
            fig.update_layout(title="Tool comparison (1 = weak, 5 = strong, demo ratings)", barmode="group", yaxis_range=[0, 5.3], xaxis_tickangle=-25)
            st.plotly_chart(style(fig, 380))
        with c2, st.container(border=True):
            d2 = d.assign(overall=d[["data_coverage", "data_accuracy", "ease_of_use", "value_for_money"]].mean(axis=1)).sort_values("overall")
            fig = go.Figure(go.Bar(y=d2["tool_name"], x=d2["overall"], orientation="h", marker_color="#00C7D1", text=d2["overall"].round(1)))
            fig.update_layout(title="Overall score", xaxis_range=[0, 5.3])
            st.plotly_chart(style(fig, 380))
        show_table(d[["tool_id", "tool_name", "category", "status", "recommendation", "owner", "start_date", "next_action"]], {
            "tool_id": "ID", "tool_name": "Tool", "category": "Category", "status": "Status", "recommendation": "Recommendation", "owner": "Owner",
            "start_date": date_col("Started"), "next_action": "Next action"})
        _detail(d, "tool_id", "tool_name", [("Objective", "research_objective"), ("Hypothesis", "hypothesis"), ("Findings", "findings")])

    with tab_a:
        d = ws.acct_research.merge(ws.accounts[["account_id", "account_name", "customer_segment", "region"]], on="account_id", how="left")
        if d.empty:
            theme.empty_state("No account research for these filters", "", "🔬")
        else:
            c1, c2, c3 = st.columns([3, 2, 2])
            q = c1.text_input("🔎 Search account, signals, findings", key="acr_q")
            pri = c2.multiselect("Account priority", ["High", "Medium", "Low"], key="acr_pri", placeholder="All")
            src = c3.multiselect("Source tool", sorted(d["source_tool"].unique()), key="acr_src", placeholder="All")
            d = search(d, q, ["account_name", "buying_signals", "findings", "why_selected", "relevant_technologies"])
            if pri:
                d = d[d["account_priority"].isin(pri)]
            if src:
                d = d[d["source_tool"].isin(src)]
            if d.empty:
                theme.empty_state("Nothing matches", "", "🔍")
                return
            _status_cards(d)
            c1, c2 = st.columns(2)
            with c1, st.container(border=True):
                g = d.groupby(["icp_fit", "account_priority"]).size().reset_index(name="accounts")
                fig = px.bar(g, x="icp_fit", y="accounts", color="account_priority", category_orders={"icp_fit": ["Strong", "Good", "Weak"]},
                             color_discrete_map={"High": "#2BE57E", "Medium": "#F5A524", "Low": "#B7C9CC"})
                fig.update_layout(title="ICP fit vs account priority")
                st.plotly_chart(style(fig, 320))
            with c2, st.container(border=True):
                g = d.groupby("source_tool").size().reset_index(name="accounts").sort_values("accounts")
                fig = go.Figure(go.Bar(y=g["source_tool"], x=g["accounts"], orientation="h", marker_color="#5B8DEF"))
                fig.update_layout(title="Where research came from")
                st.plotly_chart(style(fig, 320))
            show_table(d[["research_id", "account_name", "customer_segment", "icp_fit", "account_priority", "buying_signals", "source_tool", "status", "owner", "research_date", "next_action"]], {
                "research_id": "ID", "account_name": "Account", "customer_segment": "Segment", "icp_fit": "ICP fit", "account_priority": "Priority", "buying_signals": "Buying signals",
                "source_tool": "Source", "status": "Status", "owner": "Owner", "research_date": date_col("Researched"), "next_action": "Next action"}, height=330)
            _detail(d.assign(label=d["account_name"]), "research_id", "label", [("Objective", "research_objective"), ("Hypothesis", "business_hypothesis"),
                                                                              ("Why selected", "why_selected"), ("Buying signals", "buying_signals"),
                                                                              ("Relevant technologies", "relevant_technologies"), ("Findings", "findings")])
