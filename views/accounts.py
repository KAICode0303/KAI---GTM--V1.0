"""Module 3 - Accounts & Prospecting."""
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import metrics as m
import theme
from metrics import money
from theme import kpi_card, page_header, section, style
from views.common import date_col, money_col, note, search, show_table

STATUS_ORDER = ["Not Started", "Researching", "Contacted", "Engaged", "Meeting Booked", "Opportunity", "Customer", "Nurture"]


def render(ws):
    page_header("Accounts & Prospecting", "Fictional target accounts and the people we're talking to: fit, status, owner and what happens next.")
    acc = ws.accounts
    if acc.empty:
        theme.empty_state("No accounts match", "Widen the filters in the sidebar.", "🏢")
        return
    c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
    q = c1.text_input("🔎 Search account, industry, persona or next action", key="acc_q")
    st_f = c2.multiselect("Prospecting status", STATUS_ORDER, key="acc_status", placeholder="All")
    min_icp = c3.slider("Min ICP score", 0, 100, 0, key="acc_icp")
    size = c4.multiselect("Company size", sorted(acc["company_size"].unique()), key="acc_size", placeholder="All")
    d = search(acc, q, ["account_id", "account_name", "industry", "decision_maker_persona", "next_action", "customer_segment"])
    if st_f:
        d = d[d["prospecting_status"].isin(st_f)]
    if size:
        d = d[d["company_size"].isin(size)]
    d = d[d["icp_score"] >= min_icp]
    if d.empty:
        theme.empty_state("No accounts match", "Lower the ICP score or clear a filter.", "🔍")
        return

    cons = ws.contacts[ws.contacts["account_id"].isin(d["account_id"])]
    cols = st.columns(5)
    for col, c in zip(cols, [("Accounts", f"{len(d)}", f"of {len(acc)} in view", "🏢"), ("Avg ICP score", f"{d['icp_score'].mean():.0f}", "fit with ideal customer", "🎯"),
                             ("Strong ICP (80+)", f"{(d['icp_score'] >= 80).sum()}", "highest-fit accounts", "⭐"), ("Contacts", f"{len(cons)}", "decision-maker personas mapped", "👥"),
                             ("In pipeline", f"{(d['prospecting_status'] == 'Opportunity').sum()}", "active opportunities", "🌊")]):
        with col:
            kpi_card(c[0], c[1], c[2], "", c[3])

    tab1, tab2, tab3 = st.tabs(["Overview", "Account 360", "Contacts"])
    with tab1:
        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            g = d["prospecting_status"].value_counts().reindex(STATUS_ORDER).dropna().reset_index()
            g.columns = ["status", "accounts"]
            fig = go.Figure(go.Bar(x=g["status"], y=g["accounts"], marker_color="#00C7D1", text=g["accounts"], textposition="outside"))
            fig.update_layout(title="Prospecting status")
            fig.update_yaxes(range=[0, g["accounts"].max() * 1.18])
            st.plotly_chart(style(fig, 340))
        with c2, st.container(border=True):
            fig = px.box(d.assign(segment=d["customer_segment"].str.replace(" Companies", "").str.replace("Product and Technology", "Product & Tech").str.replace("Robotics and Physical AI", "Robotics")), x="segment", y="icp_score", points="all", color_discrete_sequence=["#2BE57E"])
            fig.update_layout(title="ICP score by segment", xaxis_title=None, xaxis_tickangle=-20)
            st.plotly_chart(style(fig, 340))
        show_table(d.sort_values("icp_score", ascending=False)[["account_id", "account_name", "industry", "customer_segment", "region", "company_size", "icp_score",
                                                               "decision_maker_persona", "owner", "prospecting_status", "last_contact_date", "next_action", "research_rationale"]], {
            "account_id": "ID", "account_name": "Account", "industry": "Industry", "customer_segment": "Segment", "region": "Region", "company_size": "Size",
            "icp_score": st.column_config.ProgressColumn("ICP", min_value=0, max_value=100, format="%d"), "decision_maker_persona": "Decision-maker persona",
            "owner": "Owner", "prospecting_status": "Status", "last_contact_date": date_col("Last contact"), "next_action": "Next action", "research_rationale": "Why this account"}, height=420)
        st.download_button("⬇️ Download (CSV)", d.to_csv(index=False), "accounts.csv")
    with tab2:
        pick = st.selectbox("Choose an account", d["account_id"] + " · " + d["account_name"], key="acc_pick")
        aid = pick.split(" · ")[0]
        r = d[d["account_id"] == aid].iloc[0]
        st.markdown(f'<div class="bubble"><b style="font-size:1.1rem">{r.account_name}</b> · {r.industry} · {r.region} · {r.company_size} employees<br>'
                    f'ICP score <b>{r.icp_score}</b> · Owner <b>{r.owner}</b> · Status <b>{r.prospecting_status}</b><br>'
                    f'Persona: {r.decision_maker_persona}<br><i>{r.research_rationale}</i><br>Next action: <b>{r.next_action}</b></div>', unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            st.markdown("**👥 Contacts**")
            show_table(ws.contacts[ws.contacts["account_id"] == aid][["contact_name", "title", "email", "contact_status"]],
                       {"contact_name": "Name", "title": "Title", "email": "Email (fictional)", "contact_status": "Status"})
        with c2, st.container(border=True):
            st.markdown("**💼 Opportunities**")
            o = ws.opps[ws.opps["account_id"] == aid]
            if o.empty:
                st.caption("No opportunities yet (or hidden by filters).")
            else:
                show_table(o[["opportunity_id", "stage", "deal_value", "close_probability", "next_action"]],
                           {"opportunity_id": "ID", "stage": "Stage", "deal_value": money_col("Value"), "close_probability": st.column_config.NumberColumn("Prob.", format="percent"), "next_action": "Next action"})
        c1, c2 = st.columns(2)
        with c1, st.container(border=True):
            st.markdown("**🌱 Leads**")
            l = ws.leads[ws.leads["account_id"] == aid]
            if l.empty:
                st.caption("No leads in this period.")
            else:
                show_table(l[["lead_id", "lead_source", "qualification_status", "created_date", "opportunity_id"]],
                           {"lead_id": "Lead", "lead_source": "Source", "qualification_status": "Status", "created_date": date_col("Created"), "opportunity_id": "Opportunity"})
        with c2, st.container(border=True):
            st.markdown("**📄 Collateral & 🔬 research**")
            cl = ws.collateral[ws.collateral["account_id"] == aid]
            rs = ws.acct_research[ws.acct_research["account_id"] == aid]
            for x in cl.itertuples():
                st.markdown(f"- 📄 {x.title} · {x.status} · due {x.due_date:%b %d}")
            for x in rs.itertuples():
                st.markdown(f"- 🔬 Research {x.research_id}: {x.icp_fit} fit, signals: {x.buying_signals}")
            if cl.empty and rs.empty:
                st.caption("No linked collateral or research yet.")
    with tab3:
        ct = cons.merge(d[["account_id", "account_name", "owner"]], on="account_id")
        cq = st.text_input("🔎 Search contacts", key="con_q")
        ct = search(ct, cq, ["contact_name", "title", "account_name", "email"])
        show_table(ct[["contact_id", "contact_name", "title", "account_name", "owner", "email", "contact_status", "is_primary"]], {
            "contact_id": "ID", "contact_name": "Name", "title": "Title", "account_name": "Account", "owner": "Owner", "email": "Email (fictional)",
            "contact_status": "Status", "is_primary": st.column_config.CheckboxColumn("Primary")}, height=460)
        note("All people and email addresses are invented (example.com addresses).")
