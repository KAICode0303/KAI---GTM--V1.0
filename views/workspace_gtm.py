"""GTM Workspace: linked Accounts, Prospects, Outreach Activities and Opportunities over the V2 demo store.

Every change is a validated, row-level write with an audit entry (gtm/store.py). Lead temperature, response status and opportunity
stage are separate fields. Opt-out, rejection and closure stop outreach. Nothing here talks to a CRM; the CSV import is a local file.
"""
from datetime import timedelta

import pandas as pd
import streamlit as st

import theme
from gtm import clock, importers, kyc, schema
from gtm.validation import ValidationError
from metrics import money
from theme import kpi_card, section

CH_ICON = {"Email": "✉️", "LinkedIn": "🔗", "Call": "📞"}
CH_COL = schema.CHANNEL_COLUMN
STOP_STATUSES = list(schema.RESPONSE_STOPS)


# ---------------------------------------------------------------- small UI helpers
def flash(kind, text):
    st.session_state.setdefault("ws_flash", []).append((kind, text))


def show_flash():
    for kind, text in st.session_state.pop("ws_flash", []):
        {"success": st.success, "error": st.error, "warning": st.warning}.get(kind, st.info)(text)


def attempt(action, success, rerun=True):
    """Run a store write. Validation problems are shown together; success is flashed and the page refreshed."""
    try:
        result = action()
    except ValidationError as exc:
        for m in exc.messages:
            st.error(m)
        return None
    flash("success", success if result is not False else "No changes to save.")
    if rerun:
        st.rerun()
    return result


def badge(text, kind):
    return f'<span class="badge {kind}">{text}</span>'


def temp_badge(t):
    return badge(t, {"Hot": "hot", "Warm": "warm", "Cold": "cold"}.get(t, "off"))


def seq_badge(row):
    return badge("Active", "ok") if row["sequence_status"] == schema.SEQUENCE_ACTIVE else badge(f"Stopped · {row['stop_reason']}", "stop")


def table(df, height=None, key=None):
    st.dataframe(df, hide_index=True, width="stretch", key=key, **({"height": height} if height else {}))


def pick(label, df, id_col, text_fn, key, empty="Nothing matches the filters."):
    if df.empty:
        st.info(empty)
        return None
    ids = list(df[id_col])
    labels = {r[id_col]: text_fn(r) for _, r in df.iterrows()}
    return st.selectbox(label, ids, format_func=labels.get, key=key)


def opt(options, current):
    return options.index(current) if current in options else 0


def contains(df, text, cols):
    if not text.strip():
        return df
    hay = df[cols].fillna("").astype(str).agg(" ".join, axis=1).str.lower()
    return df[hay.str.contains(text.strip().lower(), regex=False)]


def ts(value):
    return f"✓ {str(value)[:16]}" if value else "–"


# ---------------------------------------------------------------- Accounts
def accounts_tab(store):
    acc, pro, opp = store.accounts(), store.prospects(), store.opportunities()
    acc = acc.merge(pro.groupby("account_id").size().rename("prospects"), on="account_id", how="left")
    acc = acc.merge(opp[opp.stage.isin(schema.OPEN_STAGES)].groupby("account_id").size().rename("open_opps"), on="account_id", how="left").fillna({"prospects": 0, "open_opps": 0})
    f = st.columns([1.2, 1.2, 1.2, 1.2, 2])
    sdr = f[0].multiselect("SDR", schema.SDRS, key="a_sdr", placeholder="All")
    seg = f[1].multiselect("Segment", schema.SEGMENTS, key="a_seg", placeholder="All")
    reg = f[2].multiselect("HQ region", schema.REGIONS, key="a_reg", placeholder="All")
    sta = f[3].multiselect("Status", schema.ACCOUNT_STATUSES, key="a_sta", placeholder="All")
    q = f[4].text_input("Search", key="a_q", placeholder="Name, industry, persona…")
    for col, vals in (("owner", sdr), ("customer_segment", seg), ("hq_region", reg), ("status", sta)):
        if vals:
            acc = acc[acc[col].isin(vals)]
    acc = contains(acc, q, ["account_name", "industry", "decision_maker_persona", "account_id"])
    st.caption(f"{len(acc)} accounts")
    table(acc[["account_id", "account_name", "customer_segment", "hq_region", "industry", "owner", "status", "icp_score", "prospects", "open_opps"]], 300)

    sel = pick("Open an account", acc, "account_id", lambda r: f"{r.account_id} · {r.account_name}", "a_sel")
    if sel:
        row = store.get("accounts", "account_id", sel)
        comp = store.kyc_profile(sel)[1]
        c = st.columns(4)
        with c[0]:
            kpi_card("Prospects", f"{int((pro.account_id == sel).sum())}", "linked prospects", icon="🧲")
        with c[1]:
            o = opp[opp.account_id == sel]
            kpi_card("Open pipeline", money(o[o.stage.isin(schema.OPEN_STAGES)].deal_value.sum()), f"{len(o)} {'opportunity' if len(o) == 1 else 'opportunities'}", icon="🌊")
        with c[2]:
            kpi_card("KYC completeness", f"{comp:.0%}", "of profile fields filled", icon="🪪")
        with c[3]:
            kpi_card("ICP score", f"{row['icp_score'] if row['icp_score'] is not None else '–'}", row["status"] or "", icon="🎯")
        with st.form(f"acct_edit_{sel}"):
            e = st.columns(3)
            owner = e[0].selectbox("Owner (SDR)", schema.SDRS, index=opt(schema.SDRS, row["owner"]))
            status = e[1].selectbox("Status", schema.ACCOUNT_STATUSES, index=opt(schema.ACCOUNT_STATUSES, row["status"]))
            icp = e[2].number_input("ICP score", 0, 100, int(row["icp_score"] or 0))
            e2 = st.columns(3)
            segment = e2[0].selectbox("Customer segment", schema.SEGMENTS, index=opt(schema.SEGMENTS, row["customer_segment"]))
            region = e2[1].selectbox("HQ region", schema.REGIONS, index=opt(schema.REGIONS, row["hq_region"]))
            size = e2[2].selectbox("Company size", schema.COMPANY_SIZES, index=opt(schema.COMPANY_SIZES, row["company_size"]))
            persona = st.text_input("Decision-maker persona", row["decision_maker_persona"] or "")
            notes = st.text_area("Notes", row["notes"] or "", height=80)
            if st.form_submit_button("Save account", type="primary"):
                attempt(lambda: store.update_account(sel, {"owner": owner, "status": status, "icp_score": icp, "customer_segment": segment, "hq_region": region,
                                                           "company_size": size, "decision_maker_persona": persona, "notes": notes}), f"{sel} saved.")
    with st.expander("➕ Add an account"):
        with st.form("acct_add", clear_on_submit=False):
            a = st.columns(3)
            name = a[0].text_input("Account name *")
            industry = a[1].text_input("Industry")
            owner = a[2].selectbox("Owner (SDR)", [""] + schema.SDRS)
            b = st.columns(4)
            segment = b[0].selectbox("Customer segment", [""] + schema.SEGMENTS)
            region = b[1].selectbox("HQ region", [""] + schema.REGIONS)
            size = b[2].selectbox("Company size", [""] + schema.COMPANY_SIZES)
            icp = b[3].text_input("ICP score (0-100)")
            persona = st.text_input("Decision-maker persona")
            notes = st.text_area("Notes", height=70)
            if st.form_submit_button("Add account", type="primary"):
                attempt(lambda: store.add_account({"account_name": name, "industry": industry, "owner": owner, "customer_segment": segment, "hq_region": region,
                                                   "company_size": size, "icp_score": icp, "decision_maker_persona": persona, "notes": notes}),
                        f"Account {name!r} added.")


# ---------------------------------------------------------------- Prospects (with channels and follow-ups)
def channels_text(r):
    return " ".join(f"{CH_ICON[c]}{'✓' if r[CH_COL[c]] else '–'}" for c in schema.CHANNELS)


def _toggle_channel(store, pid, channel, key):
    want = st.session_state[key]
    try:
        store.set_channel(pid, channel, want)
        flash("success", f"{channel} {'logged' if want else 'cleared'} for {pid}.")
    except ValidationError as exc:
        st.session_state[key] = not want
        for m in exc.messages:
            flash("error", m)


def prospects_tab(store):
    pro = store.prospects()
    fu = store.follow_ups()
    nxt = fu[fu.status == "Pending"].groupby("prospect_id").due_date.min().rename("next_follow_up")
    pro = pro.merge(nxt, on="prospect_id", how="left")
    f = st.columns([1.1, 1.1, 1.3, 1.1, 1.1, 2])
    sdr = f[0].multiselect("SDR", schema.SDRS, key="p_sdr", placeholder="All")
    tmp = f[1].multiselect("Lead temperature", schema.TEMPERATURES, key="p_tmp", placeholder="All")
    rsp = f[2].multiselect("Response status", schema.RESPONSE_STATUSES, key="p_rsp", placeholder="All")
    qua = f[3].multiselect("Qualification", schema.QUALIFICATIONS, key="p_qua", placeholder="All")
    seq = f[4].multiselect("Sequence", [schema.SEQUENCE_ACTIVE, schema.SEQUENCE_STOPPED], key="p_seq", placeholder="All")
    q = f[5].text_input("Search", key="p_q", placeholder="Name, account, title, email…")
    for col, vals in (("owner", sdr), ("lead_temperature", tmp), ("response_status", rsp), ("qualification_status", qua), ("sequence_status", seq)):
        if vals:
            pro = pro[pro[col].isin(vals)]
    pro = contains(pro, q, ["full_name", "account_name", "title", "email", "prospect_id"])
    view = pro.assign(channels=pro.apply(channels_text, axis=1))
    st.caption(f"{len(pro)} prospects · temperature, response status and qualification are separate fields")
    table(view[["prospect_id", "full_name", "account_name", "title", "owner", "lead_temperature", "response_status", "qualification_status",
                "sequence_status", "stop_reason", "channels", "next_follow_up"]], 300)

    sel = pick("Open a prospect", pro, "prospect_id", lambda r: f"{r.prospect_id} · {r.full_name} ({r.account_name})", "p_sel")
    if sel:
        prospect_detail(store, sel)
    with st.expander("➕ Add a prospect"):
        accounts = store.accounts()
        with st.form("pro_add", clear_on_submit=False):
            a = st.columns(3)
            acct = a[0].selectbox("Account *", list(accounts.account_id), format_func=dict(zip(accounts.account_id, accounts.account_name)).get)
            name = a[1].text_input("Full name *")
            title = a[2].text_input("Title")
            b = st.columns(3)
            email = b[0].text_input("Email")
            linkedin = b[1].text_input("LinkedIn URL")
            phone = b[2].text_input("Phone")
            c = st.columns(5)
            owner = c[0].selectbox("Owner (SDR)", ["(account owner)"] + schema.SDRS)
            source = c[1].selectbox("Lead source", schema.LEAD_SOURCES)
            temp = c[2].selectbox("Lead temperature", schema.TEMPERATURES)
            resp = c[3].selectbox("Response status", schema.RESPONSE_STATUSES)
            qual = c[4].selectbox("Qualification", schema.QUALIFICATIONS)
            if st.form_submit_button("Add prospect", type="primary"):
                attempt(lambda: store.add_prospect({"account_id": acct, "full_name": name, "title": title, "email": email, "linkedin_url": linkedin, "phone": phone,
                                                    "owner": "" if owner.startswith("(") else owner, "lead_source": source, "lead_temperature": temp,
                                                    "response_status": resp, "qualification_status": qual}), f"Prospect {name!r} added.")


def prospect_detail(store, pid):
    row = store.get("prospects", "prospect_id", pid)
    acct = store.get("accounts", "account_id", row["account_id"])
    st.markdown(f"### {row['full_name']} · {acct['account_name']}")
    st.markdown(f"{temp_badge(row['lead_temperature'])} {badge(row['response_status'], 'off')} {badge(row['qualification_status'], 'demo')} {seq_badge(row)}",
                unsafe_allow_html=True)
    stopped = row["sequence_status"] == schema.SEQUENCE_STOPPED
    if stopped:
        st.markdown(f'<div class="warn"><b>Outreach is stopped</b> ({row["stop_reason"]}, {str(row["stopped_at"])[:10]}). Pending follow-ups were cancelled '
                    f'and no new touches or follow-ups can be added.</div>', unsafe_allow_html=True)
        if row["stop_reason"] == schema.STOP_OPT_OUT:
            st.caption("An opt-out is permanent: this prospect must not be contacted again.")
        else:
            ok = st.checkbox("I understand this resumes outreach to this prospect", key=f"restart_ok_{pid}")
            if st.button("Restart sequence", key=f"restart_{pid}", disabled=not ok):
                attempt(lambda: store.restart_sequence(pid, confirm=True), f"Sequence restarted for {pid}.")

    section("First-touch channels", "tick when sent; the time is recorded")
    cols = st.columns(3)
    for col, ch in zip(cols, schema.CHANNELS):
        key = f"ch_{pid}_{ch}"
        col.checkbox(f"{CH_ICON[ch]} {ch}", value=bool(row[CH_COL[ch]]), key=key, disabled=stopped and not row[CH_COL[ch]],
                     on_change=_toggle_channel, args=(store, pid, ch, key))
        col.caption(ts(row[CH_COL[ch]]))

    with st.form(f"pro_edit_{pid}"):
        section("Edit prospect", "")
        a = st.columns(3)
        title = a[0].text_input("Title", row["title"] or "")
        email = a[1].text_input("Email", row["email"] or "")
        linkedin = a[2].text_input("LinkedIn URL", row["linkedin_url"] or "")
        b = st.columns(5)
        owner = b[0].selectbox("Owner (SDR)", schema.SDRS, index=opt(schema.SDRS, row["owner"]))
        source = b[1].selectbox("Lead source", schema.LEAD_SOURCES, index=opt(schema.LEAD_SOURCES, row["lead_source"]))
        temp = b[2].selectbox("Lead temperature", schema.TEMPERATURES, index=opt(schema.TEMPERATURES, row["lead_temperature"]))
        resp = b[3].selectbox("Response status", schema.RESPONSE_STATUSES, index=opt(schema.RESPONSE_STATUSES, row["response_status"]))
        qual = b[4].selectbox("Qualification", schema.QUALIFICATIONS, index=opt(schema.QUALIFICATIONS, row["qualification_status"]))
        # Widgets inside a form do not rerun the page when changed, so this note and checkbox are always shown (not conditional).
        st.caption("Setting the response to **Opt-out** or **Not interested** stops outreach: pending follow-ups are cancelled and no new touches are allowed.")
        confirm = st.checkbox("I understand that Opt-out / Not interested stops outreach (required for those two responses)", key=f"stop_ok_{pid}")
        if st.form_submit_button("Save prospect", type="primary"):
            if resp in STOP_STATUSES and resp != row["response_status"] and not confirm:
                st.error("Please confirm that you want to stop outreach.")
            else:
                attempt(lambda: store.update_prospect(pid, {"title": title, "email": email, "linkedin_url": linkedin, "owner": owner, "lead_source": source,
                                                           "lead_temperature": temp, "response_status": resp, "qualification_status": qual}), f"{pid} saved.")
    followups_panel(store, pid, row, stopped)


def followups_panel(store, pid, row, stopped):
    section("Follow-ups", "four standard steps (day 3, 7, 14, 21 after first touch) plus any extras")
    fu = store.follow_ups(pid)
    if fu.empty:
        st.caption("No follow-ups yet. Tick a first-touch channel above, or start the standard sequence now.")
        if not stopped and st.button("Start the standard four-step sequence", key=f"seq_{pid}"):
            attempt(lambda: store.start_sequence(pid), "Standard follow-ups created.")
    else:
        v = fu.assign(kind=fu.is_standard.map({1: "standard", 0: "extra"}))
        table(v[["seq_no", "kind", "due_date", "channel", "status", "outcome", "owner", "notes", "completed_at"]], key=f"fu_{pid}")
    pending = fu[fu.status == "Pending"] if not fu.empty else fu
    if not stopped and not pending.empty:
        with st.form(f"fu_update_{pid}"):
            st.markdown("**Update a pending follow-up**")
            ids = list(pending.followup_id)
            labels = {r.followup_id: f"#{r.seq_no} · {r.due_date} · {r.channel}" for r in pending.itertuples()}
            a = st.columns(4)
            fid = a[0].selectbox("Follow-up", ids, format_func=labels.get)
            outcome = a[1].selectbox("Outcome", schema.FOLLOWUP_OUTCOMES[1:], key=f"fu_out_{pid}")
            action = a[2].selectbox("Mark as", ["Done", "Skipped"], key=f"fu_act_{pid}")
            owner = a[3].selectbox("Owner", schema.SDRS, index=opt(schema.SDRS, row["owner"]), key=f"fu_own_{pid}")
            notes = st.text_input("Notes", key=f"fu_notes_{pid}")
            st.caption("Outcomes such as 'Opt-out request' or 'Replied - not interested' stop outreach; 'Meeting booked' and positive replies warm the lead.")
            if st.form_submit_button("Save follow-up", type="primary"):
                changes = {"status": action, "notes": notes, "owner": owner}
                if action == "Done":
                    changes["outcome"] = outcome
                attempt(lambda: store.update_followup(fid, changes), f"Follow-up {fid} marked {action}.")
    if not stopped:
        with st.expander("➕ Add an extra follow-up"):
            with st.form(f"fu_add_{pid}"):
                a = st.columns(3)
                due = a[0].date_input("Due date", clock.today() + timedelta(days=7), key=f"fu_due_{pid}")
                ch = a[1].selectbox("Channel", schema.CHANNELS, key=f"fu_ch_{pid}")
                own = a[2].selectbox("Owner", schema.SDRS, index=opt(schema.SDRS, row["owner"]), key=f"fu_own2_{pid}")
                note = st.text_input("Notes", key=f"fu_note2_{pid}")
                if st.form_submit_button("Add follow-up", type="primary"):
                    attempt(lambda: store.add_followup(pid, due, ch, note, own), "Extra follow-up added.")
    acts = store.activities(pid)
    if not acts.empty:
        with st.expander(f"Outreach history ({len(acts)})"):
            table(acts[["performed_at", "channel", "kind", "outcome", "notes", "owner"]], key=f"act_{pid}")


# ---------------------------------------------------------------- Outreach
def outreach_tab(store):
    acts, fu = store.activities(), store.follow_ups()
    section("Today's work list", f"pending follow-ups due on or before {clock.today():%b %d, %Y}")
    due = fu[(fu.status == "Pending") & (fu.due_date <= clock.today().isoformat())]
    sdr = st.multiselect("SDR", schema.SDRS, key="o_sdr", placeholder="All")
    if sdr:
        due, acts = due[due.owner.isin(sdr)], acts[acts.owner.isin(sdr)]
    st.caption(f"{len(due)} follow-ups due or overdue")
    table(due[["followup_id", "due_date", "full_name", "account_name", "channel", "seq_no", "owner", "notes"]].head(200), 260)
    c = st.columns(4)
    with c[0]:
        kpi_card("Touches logged", f"{len(acts)}", "all channels", icon="📨")
    for col, ch in zip(c[1:], schema.CHANNELS):
        with col:
            kpi_card(ch, f"{int((acts.channel == ch).sum())}", f"{CH_ICON[ch]} touches", icon=CH_ICON[ch])
    section("Outreach activity log", "first touches, follow-ups and manual entries")
    f = st.columns(3)
    chs = f[0].multiselect("Channel", schema.CHANNELS, key="o_ch", placeholder="All")
    kinds = f[1].multiselect("Kind", schema.ACTIVITY_KINDS, key="o_kind", placeholder="All")
    q = f[2].text_input("Search", key="o_q", placeholder="Prospect, account, outcome…")
    for col, vals in (("channel", chs), ("kind", kinds)):
        if vals:
            acts = acts[acts[col].isin(vals)]
    acts = contains(acts, q, ["full_name", "account_name", "outcome", "notes"])
    table(acts[["performed_at", "full_name", "account_name", "channel", "kind", "outcome", "notes", "owner"]].head(500), 320)
    with st.expander("➕ Log an activity"):
        pros = store.prospects()
        pros = pros[pros.sequence_status == schema.SEQUENCE_ACTIVE]
        with st.form("act_add"):
            a = st.columns(4)
            pid = a[0].selectbox("Prospect (active only)", list(pros.prospect_id), format_func={r.prospect_id: f"{r.full_name} ({r.account_name})" for r in pros.itertuples()}.get)
            ch = a[1].selectbox("Channel", schema.CHANNELS)
            when = a[2].date_input("Date", clock.today())
            outcome = a[3].text_input("Outcome")
            notes = st.text_input("Notes")
            if st.form_submit_button("Log activity", type="primary"):
                attempt(lambda: store.log_activity(pid, ch, outcome, notes, when), "Activity logged.")


# ---------------------------------------------------------------- Opportunities
def opportunities_tab(store):
    opp = store.opportunities()
    f = st.columns(6)
    sdr = f[0].multiselect("SDR", schema.SDRS, key="op_sdr", placeholder="All")
    stg = f[1].multiselect("Stage", schema.STAGES, key="op_stg", placeholder="All")
    cap = f[2].multiselect("Capability", schema.CAPABILITIES, key="op_cap", placeholder="All")
    mod = f[3].multiselect("Modality", schema.MODALITIES, key="op_mod", placeholder="All")
    seg = f[4].multiselect("Segment", schema.SEGMENTS, key="op_seg", placeholder="All")
    reg = f[5].multiselect("HQ region", schema.REGIONS, key="op_reg", placeholder="All")
    for col, vals in (("owner", sdr), ("stage", stg), ("service_capability", cap), ("modality", mod), ("customer_segment", seg), ("hq_region", reg)):
        if vals:
            opp = opp[opp[col].isin(vals)]
    q = st.text_input("Search", key="op_q", placeholder="Name, account…")
    opp = contains(opp, q, ["name", "account_name", "opportunity_id"])
    op = opp[opp.stage.isin(schema.OPEN_STAGES)]
    c = st.columns(4)
    with c[0]:
        kpi_card("Deals", f"{len(opp)}", f"{len(op)} open", icon="💼")
    with c[1]:
        kpi_card("Open pipeline", money(op.deal_value.sum()), "deal value", "FORECAST", "🌊")
    with c[2]:
        kpi_card("Weighted", money((op.deal_value * op.close_probability).sum()), "× probability", "FORECAST", "⚖️")
    with c[3]:
        kpi_card("Won revenue", money(opp[opp.stage == "Won"].expected_revenue.sum()), "in this view", "ACTUAL", "🏆")
    table(opp[["opportunity_id", "name", "account_name", "owner", "stage", "deal_value", "close_probability", "service_capability", "modality",
               "customer_segment", "hq_region", "expected_close_date", "next_action"]], 300)

    sel = pick("Open an opportunity", opp, "opportunity_id", lambda r: f"{r.opportunity_id} · {r['name']} [{r.stage}]", "op_sel")
    if sel:
        row = store.get("opportunities", "opportunity_id", sel)
        margin = round(100 * row["expected_gross_profit"] / row["expected_revenue"], 1) if row["expected_revenue"] else 40.0
        with st.form(f"opp_edit_{sel}"):
            st.markdown(f"### {row['name']}")
            a = st.columns(4)
            stage = a[0].selectbox("Stage", schema.STAGES, index=opt(schema.STAGES, row["stage"]))
            prob = a[1].number_input("Close probability", 0.0, 1.0, float(row["close_probability"]), 0.05, help="A new stage resets this to the stage default; Won = 1, Lost = 0.")
            value = a[2].number_input("Deal value ($)", 1.0, 1e9, float(row["deal_value"]), 10000.0)
            gp = a[3].number_input("GP margin %", 0.0, 100.0, float(margin), 1.0)
            b = st.columns(4)
            capability = b[0].selectbox("Service capability", schema.CAPABILITIES, index=opt(schema.CAPABILITIES, row["service_capability"]))
            modality = b[1].selectbox("Modality", schema.MODALITIES, index=opt(schema.MODALITIES, row["modality"]))
            owner = b[2].selectbox("Owner (SDR)", schema.SDRS, index=opt(schema.SDRS, row["owner"]))
            close = b[3].text_input("Expected close (YYYY-MM-DD)", row["expected_close_date"] or "")
            c2 = st.columns(2)
            action = c2[0].text_input("Next action", row["next_action"] or "")
            reason = c2[1].text_input("Outcome reason (for Won/Lost)", row["outcome_reason"] or "")
            st.caption("Setting the stage to **Won** or **Lost** closes the deal and stops outreach sequences for every active prospect at this account.")
            if st.form_submit_button("Save opportunity", type="primary"):
                changes = {"stage": stage, "deal_value": value, "gp_margin_pct": gp, "service_capability": capability, "modality": modality, "owner": owner,
                           "expected_close_date": close, "next_action": action, "outcome_reason": reason}
                if abs(prob - float(row["close_probability"])) > 1e-9:
                    changes["close_probability"] = prob
                attempt(lambda: store.update_opportunity(sel, changes), f"{sel} saved.")
    with st.expander("➕ Add an opportunity"):
        accounts = store.accounts()
        names = dict(zip(accounts.account_id, accounts.account_name))
        acct = st.selectbox("Account *", list(accounts.account_id), format_func=names.get, key="op_add_acct")
        pros = store.prospects()
        pros = pros[pros.account_id == acct]
        with st.form("opp_add"):
            a = st.columns(3)
            name = a[0].text_input("Opportunity name *")
            pid = a[1].selectbox("Prospect (optional)", [""] + list(pros.prospect_id), format_func=lambda x: dict(zip(pros.prospect_id, pros.full_name)).get(x, "(none)"))
            owner = a[2].selectbox("Owner (SDR)", ["(account owner)"] + schema.SDRS)
            b = st.columns(4)
            capability = b[0].selectbox("Service capability *", schema.CAPABILITIES)
            modality = b[1].selectbox("Modality *", schema.MODALITIES)
            value = b[2].number_input("Deal value ($) *", 1.0, 1e9, 100000.0, 10000.0)
            margin = b[3].number_input("GP margin %", 0.0, 100.0, 40.0, 1.0)
            c = st.columns(3)
            stage = c[0].selectbox("Stage", schema.OPEN_STAGES)
            close = c[1].text_input("Expected close (YYYY-MM-DD)")
            action = c[2].text_input("Next action")
            if st.form_submit_button("Add opportunity", type="primary"):
                attempt(lambda: store.add_opportunity({"account_id": acct, "name": name, "prospect_id": pid, "owner": "" if owner.startswith("(") else owner,
                                                       "service_capability": capability, "modality": modality, "deal_value": value, "gp_margin_pct": margin,
                                                       "stage": stage, "expected_close_date": close, "next_action": action}), f"Opportunity {name!r} added.")


# ---------------------------------------------------------------- KYC
def kyc_tab(store):
    st.markdown("A KYC profile is structured research on one account. It is synthetic here; never paste real confidential client information into the demo store.")
    c = st.columns(2)
    c[0].download_button("⬇️ Download blank KYC template (CSV)", kyc.template_csv(), "kyc_template.csv", "text/csv", key="kyc_tpl", width="stretch")
    up = c[1].file_uploader("Upload a filled template (CSV)", type=["csv"], key="kyc_up", label_visibility="collapsed")
    if up is not None and st.button("Import uploaded KYC rows", key="kyc_import"):
        import csv
        import io
        saved, bad = 0, []
        try:
            rows = list(csv.DictReader(io.StringIO(up.getvalue().decode("utf-8-sig"))))
        except Exception:
            rows = []
            st.error("Could not read that file as a CSV.")
        for n, r in enumerate(rows[: importers.MAX_ROWS], 2):
            aid, data = kyc.parse_template_row(r)
            try:
                saved += bool(store.save_kyc(aid, data))
            except ValidationError as exc:
                bad.append(f"row {n}: {'; '.join(exc.messages)}")
        flash("success", f"{saved} KYC profile(s) saved." + (f" {len(bad)} row(s) skipped: " + " | ".join(bad[:5]) if bad else ""))
        st.rerun()
    accounts = store.accounts()
    comp = store.kyc_completeness().set_index("account_id").completeness
    sel = pick("Account", accounts, "account_id", lambda r: f"{r.account_id} · {r.account_name} ({comp.get(r.account_id, 0):.0%} complete)", "kyc_sel")
    if not sel:
        return
    data, done = store.kyc_profile(sel)
    st.progress(done, text=f"Profile completeness {done:.0%}")
    with st.form(f"kyc_form_{sel}"):
        values = {}
        cols = st.columns(2)
        for i, (key, label, kind, help_) in enumerate(kyc.FIELDS):
            host = cols[i % 2]
            if kind.startswith("select:"):
                opts = [""] + kyc.vocab(kind)
                values[key] = host.selectbox(label, opts, index=opt(opts, data[key]), key=f"kyc_{sel}_{key}", help=help_ or None)
            elif kind.startswith("multi:"):
                opts = kyc.vocab(kind)
                values[key] = host.multiselect(label, opts, default=[x for x in (s.strip() for s in data[key].split(";")) if x in opts], key=f"kyc_{sel}_{key}", help=help_ or None)
            elif kind == "longtext":
                values[key] = host.text_area(label, data[key], height=80, key=f"kyc_{sel}_{key}", help=help_ or None)
            else:
                values[key] = host.text_input(label, data[key], key=f"kyc_{sel}_{key}", help=help_ or None)
        if st.form_submit_button("Save KYC profile", type="primary"):
            attempt(lambda: store.save_kyc(sel, values), f"KYC profile for {sel} saved.")
    name = accounts.set_index("account_id").account_name[sel]
    st.download_button("⬇️ Download this profile (CSV)", kyc.profile_csv(sel, name, data), f"kyc_{sel}.csv", "text/csv", key=f"kyc_dl_{sel}")


# ---------------------------------------------------------------- Import / export / demo data
def import_tab(store):
    section("Import prospects from CSV", "beta · local file only · future Apollo / ZoomInfo style exports")
    st.markdown("Upload a CSV with a company and a name (or first and last name). Common Apollo and ZoomInfo headers are recognised automatically. "
                "Each row is validated and de-duplicated first; nothing is written until you confirm. There is no live connection to any service.")
    c = st.columns(3)
    c[0].download_button("⬇️ Prospect import template", importers.prospect_template_csv(), "prospect_import_template.csv", "text/csv", key="imp_tpl", width="stretch")
    owner = c[1].selectbox("Assign imported prospects to", ["(account owner)"] + schema.SDRS, key="imp_owner")
    up = st.file_uploader("CSV file", type=["csv"], key="imp_up")
    if up is not None:
        raw = up.getvalue()
        who = None if owner.startswith("(") else owner
        try:
            mapping, prev = importers.preview(store, raw, who)
        except ValidationError as exc:
            for m in exc.messages:
                st.error(m)
            return
        st.caption("Detected columns: " + ", ".join(f"{k} ← {v}" for k, v in mapping.items()))
        counts = prev.status.value_counts()
        st.markdown(" ".join(badge(f"{n} {s}", "ok" if s == "ok" else "warn") for s, n in counts.items()), unsafe_allow_html=True)
        table(prev, 260)
        ok = int(counts.get("ok", 0))
        if ok and st.button(f"Import {ok} valid row(s)", type="primary", key="imp_go"):
            res = importers.import_rows(store, raw, who)
            flash("success", f"Imported {res['imported']} prospect(s); skipped {res['skipped']}." + (f" Problems: {' | '.join(res['errors'][:3])}" if res["errors"] else ""))
            st.rerun()
    section("Export", "CSV with spreadsheet-formula protection")
    tables = {"accounts": store.accounts(), "prospects": store.prospects(), "follow_ups": store.follow_ups(), "outreach_activities": store.activities(),
              "opportunities": store.opportunities()}
    cols = st.columns(len(tables))
    for col, (name, df) in zip(cols, tables.items()):
        col.download_button(f"⬇️ {name}", importers.to_safe_csv(df.drop(columns=["orig_json"], errors="ignore")), f"{name}.csv", "text/csv", key=f"exp_{name}", width="stretch")


def demo_tab(store):
    section("Demo data store", "synthetic records kept in a local, git-ignored SQLite file")
    counts = store.counts()
    st.markdown(" ".join(badge(f"{n} {t.replace('_', ' ')}", "demo") for t, n in counts.items()), unsafe_allow_html=True)
    st.caption(f"Demo clock: {clock.label()} · file: {store.path.name} · every change below is recorded in the audit log.")
    section("Audit log", "the latest 100 changes (actor is always 'demo': there is no login)")
    table(store.audit(100)[["ts", "table_name", "row_id", "action", "changes_json", "actor"]], 320)
    with st.expander("⚠️ Reset the demo data"):
        st.warning("This rebuilds the demo store from the synthetic seed and discards every edit you made. It touches only this demo file.")
        ok = st.checkbox("Yes, discard my edits and reset the demo data", key="reset_ok")
        if st.button("Reset demo data", key="reset_go", disabled=not ok):
            store.reset_demo(confirm=True)
            flash("success", "Demo data reset to the synthetic seed.")
            st.rerun()


def render(store):
    theme.page_header("GTM Workspace", "Accounts, prospects, outreach and opportunities, linked end to end. Every change is validated and saved row by row.",
                      eyebrow="Kai's GTM V2.0 · GTM Team")
    st.markdown(f'<span class="badge demo">Synthetic demo data</span> &nbsp;<span style="color:var(--muted);font-size:.82rem">{clock.label()} · '
                f'SDR team: {", ".join(schema.SDRS)} · no CRM connected</span>', unsafe_allow_html=True)
    show_flash()
    tabs = st.tabs(["🏢 Accounts", "🧲 Prospects", "📨 Outreach", "💼 Opportunities", "🪪 KYC profiles", "📥 Import & export", "🗃️ Demo data & audit"])
    for tab, fn in zip(tabs, (accounts_tab, prospects_tab, outreach_tab, opportunities_tab, kyc_tab, import_tab, demo_tab)):
        with tab:
            fn(store)
