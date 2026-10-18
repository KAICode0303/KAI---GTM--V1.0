"""Module 6 - Leads & Opportunities (searchable tables, aging, simple local editing saved to SQLite)."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import analytics as a
import db
import metrics as m
import theme
from metrics import money
from theme import kpi_card, page_header, section, style
from views.common import date_col, money_col, note, search, show_table

STAGE_PROB = {"Prospecting": .10, "Qualified": .25, "Discovery": .40, "Proposal": .60, "Negotiation": .80, "Won": 1.0, "Lost": 0.0}
EDITABLE = ["stage", "close_probability", "expected_close_date", "next_follow_up_date", "next_action", "outcome_reason"]


def _save_edits(original, edited):
    """Write changed rows back to the database. Rules keep the data consistent (Won = 100%, Lost = 0%)."""
    raw = db.read("opportunities").set_index("opportunity_id")
    changed = 0
    for oid, new in edited.set_index("opportunity_id").iterrows():
        old = original.set_index("opportunity_id").loc[oid]
        diff = [c for c in EDITABLE if not (pd.isna(old[c]) and pd.isna(new[c])) and old[c] != new[c]]
        if not diff:
            continue
        changed += 1
        stage = new["stage"]
        prob = float(new["close_probability"]) if not pd.isna(new["close_probability"]) else STAGE_PROB[stage]
        if stage in ("Won", "Lost"):
            prob = STAGE_PROB[stage]
        elif "stage" in diff and "close_probability" not in diff:
            prob = STAGE_PROB[stage]                         # new stage -> default probability for that stage
        raw.loc[oid, "stage"], raw.loc[oid, "close_probability"] = stage, min(max(prob, 0), 1)
        for c in ["expected_close_date", "next_follow_up_date"]:
            raw.loc[oid, c] = "" if pd.isna(new[c]) else pd.Timestamp(new[c]).strftime("%Y-%m-%d")
        raw.loc[oid, "next_action"] = new["next_action"] or ""
        reason = "" if pd.isna(new["outcome_reason"]) else new["outcome_reason"]     # missing is None (pandas 2) or NaN (pandas 3)
        if stage in ("Won", "Lost"):
            if pd.Timestamp(raw.loc[oid, "expected_close_date"] or m.AS_OF) > m.AS_OF:
                raw.loc[oid, "expected_close_date"] = m.AS_OF.strftime("%Y-%m-%d")   # closed deals close today at the latest
            reason = reason or "Not recorded"
            raw.loc[oid, "next_follow_up_date"] = ""
        else:
            reason = ""
        raw.loc[oid, "outcome_reason"] = reason
    db.write("opportunities", raw.reset_index())
    return changed


def render(ws):
    page_header("Leads & Opportunities", "Search, filter and update every lead and deal. Edits are saved locally in SQLite.")
    tab_o, tab_a, tab_l = st.tabs(["Opportunities", "Deal aging & outcomes", "Leads"])
    opps = ws.opps

    with tab_o:
        if opps.empty:
            theme.empty_state("No opportunities match", "Widen the filters in the sidebar.", "🔭")
        else:
            c1, c2, c3 = st.columns([3, 2, 2])
            q = c1.text_input("🔎 Search client, ID, owner, service or next action", key="opp_q")
            status = c2.multiselect("Show", ["On track", "Stalled", "Overdue follow-up", "Won", "Lost"], key="opp_status", placeholder="All statuses")
            edit = c3.toggle("✏️ Edit mode", key="opp_edit", help="Change stage, probability, dates, next action and outcome reason.")
            t = search(opps, q, ["opportunity_id", "client_name", "sales_owner", "service_offering", "customer_segment", "next_action", "region"])
            t = t.assign(status=t.apply(lambda r: r["stage"] if not r["is_open"] else "Stalled" if r["days_since_activity"] > m.STALL_DAYS
                                        else "Overdue follow-up" if r["overdue_followup"] else "On track", axis=1))
            if status:
                t = t[t["status"].isin(status) | (t["overdue_followup"] & ("Overdue follow-up" in status)) | ((t["days_since_activity"] > m.STALL_DAYS) & t["is_open"] & ("Stalled" in status))]
            t = t.sort_values(["is_open", "weighted_value"], ascending=[False, False])
            if t.empty:
                theme.empty_state("Nothing matches your search", "Try a different word or clear the status filter.", "🔍")
            elif not edit:
                st.caption(f"{len(t)} opportunities · open deals first, by weighted value")
                show_table(t[["opportunity_id", "client_name", "sales_owner", "region", "service_offering", "stage", "status", "deal_value", "close_probability", "weighted_value",
                              "expected_revenue", "expected_delivery_cost", "expected_gross_profit", "gp_margin_pct", "expected_close_date", "created_date", "deal_age_days",
                              "last_activity_date", "next_follow_up_date", "next_action", "outcome_reason"]], {
                    "opportunity_id": "ID", "client_name": "Client", "sales_owner": "Owner", "region": "Region", "service_offering": "Service", "stage": "Stage", "status": "Status",
                    "deal_value": money_col("Deal value"), "close_probability": st.column_config.ProgressColumn("Probability", format="percent", min_value=0, max_value=1),
                    "weighted_value": money_col("Weighted"), "expected_revenue": money_col("Proj. revenue"), "expected_delivery_cost": money_col("Delivery cost"),
                    "expected_gross_profit": money_col("Proj. GP"), "gp_margin_pct": st.column_config.NumberColumn("GP %", format="%.1f%%"),
                    "expected_close_date": date_col("Expected close"), "created_date": date_col("Created"), "deal_age_days": st.column_config.NumberColumn("Age (days)"),
                    "last_activity_date": date_col("Last follow-up"), "next_follow_up_date": date_col("Next follow-up"), "next_action": "Next action", "outcome_reason": "Won/Lost reason"}, height=520, key="opp_table")
                st.download_button("⬇️ Download these rows (CSV)", t.to_csv(index=False), "opportunities_filtered.csv")
            else:
                note("Edit cells, then press <b>Save changes</b>. Won deals are set to 100% and Lost to 0%; a new stage resets probability to that stage's default unless you edit it.")
                view = t[["opportunity_id", "client_name", "sales_owner", "deal_value"] + EDITABLE].reset_index(drop=True)
                edited = st.data_editor(view, hide_index=True, width="stretch", height=480, key="opp_editor",
                                        disabled=["opportunity_id", "client_name", "sales_owner", "deal_value"],
                                        column_config={"opportunity_id": "ID", "client_name": "Client", "sales_owner": "Owner", "deal_value": money_col("Deal value"),
                                                       "stage": st.column_config.SelectboxColumn("Stage", options=m.STAGES, required=True),
                                                       "close_probability": st.column_config.NumberColumn("Probability", min_value=0.0, max_value=1.0, step=0.05, format="percent"),
                                                       "expected_close_date": date_col("Expected close"), "next_follow_up_date": date_col("Next follow-up"),
                                                       "next_action": "Next action", "outcome_reason": "Won/Lost reason"})
                b1, b2 = st.columns([1, 4])
                if b1.button("💾 Save changes", type="primary", key="opp_save"):
                    n = _save_edits(view, edited)
                    st.toast(f"Saved {n} changed deal(s).", icon="✅") if n else st.toast("No changes to save.")
                    if n:
                        st.rerun()
                b2.caption("Reset everything on the About page.")

    with tab_a:
        if opps.empty:
            theme.empty_state("No opportunities match", "", "🔭")
        else:
            c1, c2 = st.columns(2)
            op = opps[opps["is_open"]]
            with c1, st.container(border=True):
                if op.empty:
                    theme.empty_state("No open deals", "", "🏁")
                else:
                    ag = op.groupby("stage")["deal_age_days"].mean().reindex(m.OPEN_STAGES).dropna().reset_index()
                    fig = go.Figure(go.Bar(x=ag["stage"], y=ag["deal_age_days"], marker_color="#00C7D1", text=ag["deal_age_days"].round(0), textposition="outside"))
                    fig.update_layout(title="Average age of open deals by stage (days)")
                    st.plotly_chart(style(fig, 340))
            with c2, st.container(border=True):
                if op.empty:
                    theme.empty_state("No open deals", "", "🏁")
                else:
                    fig = px.scatter(op, x="deal_age_days", y="deal_value", size="weighted_value", color="stage", hover_name="client_name",
                                     labels={"deal_age_days": "Age (days)", "deal_value": "Deal value"})
                    fig.update_layout(title="Open deals: age vs value (bubble = weighted value)", yaxis_tickprefix="$", yaxis_tickformat="~s")
                    st.plotly_chart(style(fig, 340))
            reasons = a.win_loss_reasons(opps)
            section("Won / lost reasons")
            if reasons.empty:
                theme.empty_state("No closed deals in this selection", "", "🏁")
            else:
                show_table(reasons.sort_values(["stage", "deals"], ascending=[False, False]).rename(columns={"stage": "Outcome", "outcome_reason": "Reason", "deals": "Deals", "value": "Value"}),
                           {"Value": money_col("Value")})

    with tab_l:
        leads = ws.leads
        if leads.empty:
            theme.empty_state("No leads in this period", "Widen the date range in the sidebar.", "🌱")
        else:
            lm = a.lead_metrics(leads, opps)
            cols = st.columns(5)
            for col, c in zip(cols, [("Leads", lm["leads"], "created in period", "🌱"), ("Qualified", lm["qualified"], f"{lm['qualified'] / lm['leads']:.0%} of leads", "✅"),
                                     ("Meetings held", lm["meetings_held"], f"{lm['meetings_booked']} booked", "🤝"), ("Opportunities", lm["opportunities"], f"{lm['lead_to_opp']:.0%} lead→opp", "🚀"),
                                     ("Won", lm["won"], f"{lm['opp_to_win']:.0%} opp→win", "🏆")]):
                with col:
                    kpi_card(c[0], f"{c[1]:,}", c[2], "", c[3])
            c1, c2, c3 = st.columns([3, 2, 2])
            lq = c1.text_input("🔎 Search leads", key="lead_q")
            lst = c2.multiselect("Status", sorted(leads["qualification_status"].unique()), key="lead_status", placeholder="All")
            lsrc = c3.multiselect("Source", sorted(leads["lead_source"].unique()), key="lead_src", placeholder="All")
            lt = search(leads.merge(ws.accounts[["account_id", "account_name"]], on="account_id", how="left"), lq, ["lead_id", "account_name", "lead_source", "owner", "qualification_status"])
            if lst:
                lt = lt[lt["qualification_status"].isin(lst)]
            if lsrc:
                lt = lt[lt["lead_source"].isin(lsrc)]
            with st.container(border=True):
                src = a.leads_by_source(leads, opps)
                fig = go.Figure()
                fig.add_bar(x=src["lead_source"], y=src["leads"], name="Leads", marker_color="#00C7D1")
                fig.add_bar(x=src["lead_source"], y=src["opportunities"], name="Became opportunities", marker_color="#2BE57E")
                fig.update_layout(title="Lead sources and conversion", barmode="group")
                st.plotly_chart(style(fig, 300))
            show_table(lt.sort_values("created_date", ascending=False)[["lead_id", "account_name", "lead_source", "owner", "qualification_status", "created_date", "qualified_date",
                                                                        "meeting_booked_date", "meeting_held_date", "opportunity_id", "disqualification_reason"]], {
                "lead_id": "Lead", "account_name": "Account", "lead_source": "Source", "owner": "Owner", "qualification_status": "Status", "created_date": date_col("Created"),
                "qualified_date": date_col("Qualified"), "meeting_booked_date": date_col("Meeting booked"), "meeting_held_date": date_col("Meeting held"),
                "opportunity_id": "Opportunity", "disqualification_reason": "Disqualified because"}, height=420)
