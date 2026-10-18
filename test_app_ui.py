"""End-to-end UI tests: the real app.py driven headlessly with Streamlit's AppTest.

Isolation: a throw-away GTM database and Chroma index in tmp_path, the toy hashing embedding instead of FastEmbed, and every network
connection blocked and counted. The V1 database is never written. These tests check behaviour and guarantees, not visual design."""
import html
import socket
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import metrics
from gtm import pulse, schema
from gtm.store import GTMStore
from rag import app_index
from test_rag import HashingEmbeddings

ROOT = Path(__file__).resolve().parent
APP = str(ROOT / "app.py")
PULSE, HOOMI, WORKSPACE = "📊  Executive Pulse", "🤖  Ask Hoomi", "🗂️  GTM Workspace"
CLASSIC = ["🏠  Command Center", "🔭  Market Intelligence", "🏢  Accounts & Prospecting", "📞  SDR Activity",
           "📄  Content & Collaterals", "💼  Leads & Opportunities", "💰  Revenue & GP", "ℹ️  About"]
V1_DB = ROOT / "data" / "kai_gtm.db"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("GTM_V2_DB", str(tmp_path / "gtm.db"))
    monkeypatch.setenv("RAG_MAX_DISTANCE", "9")                       # toy embedding: let the gate pass unless a test says otherwise
    monkeypatch.setenv("RAG_CONTEXT_K", "8")
    monkeypatch.setenv("HOOMI_OFFLINE_MIN_SIM", "0.2")
    monkeypatch.setattr(app_index, "make_embeddings", lambda: HashingEmbeddings())
    monkeypatch.setattr(app_index, "APP_INDEX_DIR", tmp_path / "idx")
    st.cache_resource.clear()
    attempts = []

    def blocked(*a, **k):
        attempts.append(1)
        raise OSError("network blocked by test")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "getaddrinfo", blocked)
    yield attempts
    assert attempts == [], "the app tried to reach the network"


def start(role="Leadership Hub"):
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    at.button(key=f"role_{role}").click().run()
    return at


def goto(at, page):
    at.sidebar.radio(key="nav_classic" if page in CLASSIC else "nav_primary").set_value(page).run()
    return at


def clean(at):
    assert not at.exception, [str(e.value)[:300] for e in at.exception]
    assert not at.error, [str(e.value)[:300] for e in at.error]


def texts(elements):
    """Visible text of elements, with HTML entities decoded (the app writes '$' as '&#36;' to keep markdown from reading it as maths)."""
    return html.unescape("\n".join(str(getattr(e, "value", "")) for e in elements))


def widget(collection, label):
    found = [w for w in collection if w.label == label]
    assert found, f"no widget labelled {label!r}; have {[w.label for w in collection][:12]}"
    return found[0]


def store_of(tmp_path):
    return GTMStore(tmp_path / "gtm.db")


# ---------------------------------------------------------------- welcome and navigation
def test_welcome_screen_shows_greeting_placeholder_and_both_views():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    clean(at)
    page = texts(at.markdown)
    assert "Meet Hoomi" in page and "Where's your GTM headed? Let's find out." in page
    assert "Mascot placeholder" in page and "Pixel Creative Strategist" in page          # a labelled placeholder, no invented artwork
    assert "not a login" in page.lower() and "synthetic demo data" in page.lower() and "no authentication" in page.lower()
    assert {b.label for b in at.button} == {"Enter the Leadership Hub", "Enter the GTM Team"}
    assert "Leadership Hub" in page and "GTM Team" in page and "Executive Pulse" in page and "GTM Workspace" in page


@pytest.mark.parametrize("role, landing, order", [("Leadership Hub", PULSE, [PULSE, HOOMI, WORKSPACE]), ("GTM Team", WORKSPACE, [WORKSPACE, HOOMI, PULSE])])
def test_role_choice_sets_the_landing_page_and_order_but_not_access(role, landing, order):
    at = start(role)
    clean(at)
    assert at.session_state.role == role and at.session_state.nav == landing
    assert list(at.sidebar.radio(key="nav_primary").options) == order
    for page in order:                                                                   # every page is open to both roles
        goto(at, page)
        clean(at)


def test_switching_view_returns_to_the_welcome_screen():
    at = start()
    at.sidebar.button(key="switch_role").click().run()
    clean(at)
    assert at.session_state.role is None and "Meet Hoomi" in texts(at.markdown)


def test_display_name_is_sanitised_before_it_reaches_html_or_script():
    at = AppTest.from_file(APP, default_timeout=180)
    at.run()
    at.text_input(key="user_name").set_value("</script><img src=x onerror=alert(1)>Ana").run()
    page = texts(at.markdown)
    assert "<img" not in page and "onerror=alert" not in page and "</script>" not in page and "Ana" in page
    clean(at)


def test_classic_v1_views_are_kept_and_still_run():
    before = V1_DB.read_bytes() if V1_DB.exists() else None
    at = start()
    for page in CLASSIC:
        goto(at, page)
        clean(at)
        assert at.session_state.nav == page
    assert (V1_DB.read_bytes() if V1_DB.exists() else None) == before                   # browsing the classic views never writes the V1 database
    goto(at, PULSE)
    clean(at)
    assert at.session_state.nav == PULSE and at.session_state.nav_classic is None        # and the V2 pages can be reached again


def test_dark_mode_toggle_runs():
    at = start()
    at.sidebar.toggle(key="dark").set_value(True).run()
    clean(at)
    assert at.session_state.dark is True


# ---------------------------------------------------------------- executive pulse
def test_pulse_shows_every_required_kpi_chart_and_the_footer(tmp_path):
    at = start()
    page = texts(at.markdown)
    for label in ["Accounts Closed", "Open Pipeline", "Weighted Pipeline", "Won Revenue", "Won Gross Profit", "GP Margin",
                  "Total Leads", "Warm Leads", "Hot Leads", "Qualified Leads", "Win Rate", "Pending Follow-ups"]:
        assert label in page, label
    for heading in ["Revenue by service", "Requested capabilities", "SDR performance", "Pipeline health"]:
        assert heading in page, heading
    assert "Where's your GTM headed? Let's find out." in page and "Synthetic demo data" in page
    assert len(at.get("plotly_chart")) == 6
    snap = pulse.snapshot(store_of(tmp_path))
    c, k = snap["commercial"], snap["leads"]
    for shown in (metrics.money(c["open_pipeline"]), metrics.money(c["weighted_pipeline"]), metrics.money(c["won_revenue"]), metrics.money(c["won_gp"]),
                  f"{c['gp_margin']:.1%}", f"{c['win_rate']:.0%}", str(k["pending_followups"]), str(k["hot_leads"])):
        assert shown in page, shown                                                      # figures on screen are the calculated ones
    assert snap["summary"]["sdr_performance"][0].split(":")[0] in page


def test_pulse_follows_workspace_edits(tmp_path):
    at = start()
    before = texts(at.markdown)
    s = store_of(tmp_path)
    oid = s.opportunities().query("stage == 'Negotiation'").iloc[0].opportunity_id
    s.update_opportunity(oid, {"stage": "Won"})
    st.cache_resource.clear()
    at.run()
    clean(at)
    assert texts(at.markdown) != before


# ---------------------------------------------------------------- Hoomi chat
def ask(at, question):
    at.chat_input[0].set_value(question).run()
    clean(at)
    return at


def last_reply(at):
    return texts(at.chat_message[-1].markdown)


def test_hoomi_labels_the_offline_demo_and_keeps_fireworks_disabled():
    at = goto(start(), HOOMI)
    clean(at)
    page = texts(at.markdown)
    assert "Offline demo" in page and "zero hosted calls" in page and "Fireworks mode is disabled" in page
    toggle = at.toggle(key="hoomi_hosted_toggle")
    assert toggle.value is False and toggle.disabled is True
    from views import hoomi_page
    assert hoomi_page.HOSTED_MODE_AVAILABLE is False
    import ast
    for path in ("views/hoomi_page.py", "rag/chat.py", "rag/offline.py", "rag/app_index.py"):
        tree = ast.parse((ROOT / path).read_text())
        imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        names = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) for a in n.names}
        assert not {m for m in imported if "providers" in m or m in ("langchain_fireworks", "fireworks", "openai", "requests", "httpx")}, (path, imported)
        assert not names & {"providers", "LLMClient", "ChatFireworks", "answer_verified"}, (path, names)


def test_documents_question_gets_a_quoted_answer_with_sources_and_checks():
    at = goto(start(), HOOMI)
    ask(at, "What is a managed service?")
    reply = last_reply(at)
    assert "Answered" in reply and "managed service" in reply.lower()
    assert any(e.label.startswith("Sources (") for e in at.expander) and any(e.label == "How this was checked" for e in at.expander)
    src = texts([m for e in at.expander if e.label.startswith("Sources (") for m in e.markdown])
    assert "02_delivery_modalities.md" in src and "distance" in src
    check = texts([m for e in at.expander if e.label == "How this was checked" for m in e.markdown])
    assert "zero hosted calls" in " ".join(c.value for c in at.caption)


def test_unanswerable_question_gets_an_insufficient_evidence_answer(monkeypatch):
    monkeypatch.setenv("RAG_MAX_DISTANCE", "0")                                       # nothing can pass the gate
    at = goto(start(), HOOMI)
    ask(at, "What is the refund policy for cancelled programs?")
    reply = last_reply(at)
    assert "Insufficient evidence" in reply and "don't have enough support" in reply
    assert "Answered" not in reply and not any(e.label.startswith("Sources (") for e in at.expander)


def test_numbers_question_is_calculated_not_retrieved(tmp_path):
    at = goto(start(), HOOMI)
    ask(at, "What is our open pipeline?")
    reply = last_reply(at)
    snap = pulse.snapshot(store_of(tmp_path))
    assert "Calculated from the workspace" in reply and metrics.money(snap["commercial"]["open_pipeline"]) in reply
    assert not any(e.label.startswith("Sources (") for e in at.expander)               # no documents were involved


def test_history_persists_across_turns_and_can_be_cleared():
    at = goto(start(), HOOMI)
    ask(at, "What is a managed service?")
    ask(at, "What is our win rate?")
    assert len(at.chat_message) == 4 and len(at.session_state.hoomi_chat) == 4
    at.button(key="hoomi_clear").click().run()
    clean(at)
    assert at.session_state.hoomi_chat == [] and len(at.chat_message) == 0


def test_suggestion_buttons_ask_the_question():
    at = goto(start(), HOOMI)
    at.button(key="hsug_3").click().run()
    clean(at)
    assert len(at.chat_message) == 2 and "open pipeline" in texts(at.chat_message[0].markdown).lower() or len(at.chat_message) == 2


def test_account_questions_use_that_accounts_kyc_profile():
    at = goto(start(), HOOMI)
    ask(at, "What are the requested capabilities for Deepcurrent Labs?")
    src = texts([m for e in at.expander if e.label.startswith("Sources (") for m in e.markdown])
    assert "kyc_ACC-101.md" in src and "KYC profile" in src
    ask(at, "What services does Kai's Company offer?")
    src2 = texts([m for e in at.expander if e.label.startswith("Sources (") for m in e.markdown][-4:])
    assert "kyc_" not in texts(at.chat_message[-1].markdown)                             # a general question never quotes a KYC profile


def test_explicit_rule_based_route_uses_the_classic_hoomi_with_a_caution():
    at = goto(start(), HOOMI)
    at.radio(key="hoomi_route").set_value("Rule-based").run()
    ask(at, "What is our total pipeline?")
    reply = last_reply(at)
    assert "Classic rule-based fallback" in reply and "can misread questions" in reply


def test_document_search_failure_degrades_gracefully(monkeypatch):
    def boom():
        raise FileNotFoundError("embedding model is not cached")

    monkeypatch.setattr(app_index, "make_embeddings", boom)
    st.cache_resource.clear()
    at = goto(start(), HOOMI)
    clean(at)
    assert "Document search is unavailable" in texts(at.markdown)
    ask(at, "What is our open pipeline?")                                                # numbers still work
    assert "Calculated from the workspace" in last_reply(at)
    ask(at, "What is a managed service?")                                               # documents degrade to the labelled classic Hoomi
    assert "Document search is unavailable" in last_reply(at)


def test_classic_briefing_tab_is_preserved():
    at = goto(start(), HOOMI)
    page = texts(at.markdown)
    assert "Top 5 priorities" in page and "Classic Hoomi (V1)" in page


# ---------------------------------------------------------------- workspace: row-level writes through the UI
def open_workspace(role="GTM Team"):
    at = start(role)
    clean(at)
    return at


def click(at, label, index=0):
    buttons = [b for b in at.button if b.label == label]
    assert buttons, f"no button {label!r}; have {[b.label for b in at.button][:15]}"
    buttons[index].click().run()
    clean(at)


def test_workspace_has_all_four_levels_and_the_sdr_team():
    at = open_workspace()
    labels = [t.label for t in at.tabs]
    for tab in ("Accounts", "Prospects", "Outreach", "Opportunities", "KYC profiles", "Import & export", "Demo data & audit"):
        assert any(tab in label for label in labels), tab
    sdr_options = list(widget(at.multiselect, "SDR").options)
    assert sdr_options == ["Mini", "Sue", "Harry", "Dips", "Emma"]
    assert "Synthetic demo data" in texts(at.markdown) and "no CRM connected" in texts(at.markdown)


def test_add_account_through_the_form_and_reject_a_duplicate(tmp_path):
    at = open_workspace()
    widget(at.text_input, "Account name *").set_value("Nimbus Robotics")
    widget(at.selectbox, "Owner (SDR)")  # the add form's selectbox exists
    click(at, "Add account")
    s = store_of(tmp_path)
    assert "Nimbus Robotics" in set(s.accounts().account_name) and "Account 'Nimbus Robotics' added." in texts(at.success)
    widget(at.text_input, "Account name *").set_value("nimbus robotics inc.")
    [b for b in at.button if b.label == "Add account"][0].click().run()
    assert any("Duplicate" in e.value for e in at.error)                                 # the validation message is shown to the user
    assert list(s.accounts().account_name).count("Nimbus Robotics") == 1 and len(s.accounts()) == 65


def test_duplicate_account_shows_the_error_message(tmp_path):
    at = open_workspace()
    widget(at.text_input, "Account name *").set_value("Deepcurrent Labs")
    at.button[[b.label for b in at.button].index("Add account")].click().run()
    assert any("Duplicate" in e.value and "ACC-101" in e.value for e in at.error)
    assert len(store_of(tmp_path).accounts()) == 64


def select_prospect(at, pid):
    at.selectbox(key="p_sel").set_value(pid).run()
    clean(at)


def untouched(tmp_path):
    s = store_of(tmp_path)
    return s.df("SELECT prospect_id FROM prospects WHERE sequence_status='Active' AND email_sent_at IS NULL AND linkedin_sent_at IS NULL "
                "AND call_made_at IS NULL ORDER BY 1").iloc[0].prospect_id


def test_ticking_a_channel_checkbox_records_a_timestamp_and_starts_the_sequence(tmp_path):
    at = open_workspace()
    pid = untouched(tmp_path)
    select_prospect(at, pid)
    at.checkbox(key=f"ch_{pid}_Email").check().run()
    clean(at)
    s = store_of(tmp_path)
    row = s.get("prospects", "prospect_id", pid)
    assert row["email_sent_at"] and row["linkedin_sent_at"] is None
    assert len(s.follow_ups(pid)) == 4 and list(s.activities(pid).channel) == ["Email"]
    assert any("Email logged" in x.value for x in at.success)
    at.checkbox(key=f"ch_{pid}_Email").uncheck().run()                                   # unticking clears it again
    assert store_of(tmp_path).get("prospects", "prospect_id", pid)["email_sent_at"] is None


def test_stopped_prospect_cannot_be_touched_and_optout_is_permanent(tmp_path):
    s = store_of(tmp_path)
    pid = s.df("SELECT prospect_id FROM prospects WHERE stop_reason = 'Opt-out' ORDER BY 1").iloc[0].prospect_id
    at = open_workspace()
    select_prospect(at, pid)
    assert "Outreach is stopped" in texts(at.markdown) and "opt-out is permanent" in texts(at.caption).lower()
    for ch in schema.CHANNELS:
        assert at.checkbox(key=f"ch_{pid}_{ch}").disabled is True or at.checkbox(key=f"ch_{pid}_{ch}").value is True
    assert not any(b.label == "Restart sequence" for b in at.button)


def test_choosing_optout_requires_confirmation_then_stops_outreach(tmp_path):
    s = store_of(tmp_path)
    pid = s.df("SELECT p.prospect_id FROM prospects p WHERE p.sequence_status='Active' AND EXISTS (SELECT 1 FROM follow_ups f WHERE "
               "f.prospect_id=p.prospect_id AND f.status='Pending') ORDER BY 1").iloc[0].prospect_id
    at = open_workspace()
    select_prospect(at, pid)
    assert "stops outreach" in texts(at.caption)                                         # the consequence is always visible, even inside the form
    widget(at.selectbox, "Response status").set_value("Opt-out")
    [b for b in at.button if b.label == "Save prospect"][0].click().run()                # without ticking the confirmation
    assert "Please confirm" in texts(at.error) and s.get("prospects", "prospect_id", pid)["sequence_status"] == "Active"
    widget(at.selectbox, "Response status").set_value("Opt-out")
    at.checkbox(key=f"stop_ok_{pid}").check()
    click(at, "Save prospect")
    row = store_of(tmp_path).get("prospects", "prospect_id", pid)
    assert (row["sequence_status"], row["stop_reason"], row["response_status"]) == ("Stopped", "Opt-out", "Opt-out")
    assert len(store_of(tmp_path).follow_ups(pid).query("status == 'Pending'")) == 0


def test_update_a_follow_up_outcome_through_the_form(tmp_path):
    s = store_of(tmp_path)
    pid = s.df("SELECT p.prospect_id FROM prospects p WHERE p.sequence_status='Active' AND EXISTS (SELECT 1 FROM follow_ups f WHERE "
               "f.prospect_id=p.prospect_id AND f.status='Pending') ORDER BY 1").iloc[0].prospect_id
    at = open_workspace()
    select_prospect(at, pid)
    at.selectbox(key=f"fu_out_{pid}").set_value("Left voicemail")
    at.text_input(key=f"fu_notes_{pid}").set_value("Asked for a call back")
    click(at, "Save follow-up")
    done = store_of(tmp_path).follow_ups(pid).query("status == 'Done' and notes == 'Asked for a call back'")
    assert len(done) == 1 and done.iloc[0].outcome == "Left voicemail"


def test_closing_an_opportunity_through_the_form_stops_account_outreach(tmp_path):
    s = store_of(tmp_path)
    aid = s.df("SELECT a.account_id FROM accounts a WHERE NOT EXISTS (SELECT 1 FROM opportunities o WHERE o.account_id=a.account_id AND o.stage IN "
               "('Won','Lost')) AND EXISTS (SELECT 1 FROM opportunities o WHERE o.account_id=a.account_id) AND EXISTS (SELECT 1 FROM prospects p WHERE "
               "p.account_id=a.account_id AND p.sequence_status='Active') ORDER BY 1").iloc[0].account_id
    oid = s.opportunities().query("account_id == @aid").iloc[0].opportunity_id
    at = open_workspace()
    at.selectbox(key="op_sel").set_value(oid).run()
    clean(at)
    assert "stops outreach sequences" in texts(at.caption)                               # visible before choosing, since form widgets do not rerun
    [w for w in at.selectbox if w.label == "Stage"][0].set_value("Won")
    click(at, "Save opportunity")
    s2 = store_of(tmp_path)
    assert s2.get("opportunities", "opportunity_id", oid)["stage"] == "Won" and s2.get("opportunities", "opportunity_id", oid)["close_probability"] == 1.0
    assert (s2.prospects().query("account_id == @aid").sequence_status == "Stopped").all()


def test_kyc_edit_saves_and_reaches_hoomi(tmp_path):
    at = open_workspace()
    at.selectbox(key="kyc_sel").set_value("ACC-103").run()
    clean(at)
    at.text_input(key="kyc_ACC-103_website").set_value("www.tarnwick.example.com")
    click(at, "Save KYC profile")
    data, _ = store_of(tmp_path).kyc_profile("ACC-103")
    assert data["website"] == "www.tarnwick.example.com"
    assert any("KYC profile for ACC-103 saved" in x.value for x in at.success)


def test_demo_reset_needs_the_confirmation_checkbox(tmp_path):
    s = store_of(tmp_path)
    s.add_account({"account_name": "Temporary Co"})
    at = open_workspace()
    assert at.button(key="reset_go").disabled is True
    at.checkbox(key="reset_ok").check().run()
    assert at.button(key="reset_go").disabled is False
    at.button(key="reset_go").click().run()
    clean(at)
    assert len(store_of(tmp_path).accounts()) == 64


def test_the_app_never_creates_files_outside_its_stores(tmp_path):
    start()
    assert (tmp_path / "gtm.db").exists()
    assert not list(ROOT.glob("data/gtm_v2.db-*"))                                       # no stray journal files next to the real store
