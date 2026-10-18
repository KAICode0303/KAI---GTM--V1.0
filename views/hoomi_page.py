"""Hoomi: grounded Q&A (offline demo) over approved documents, KYC profiles and the workspace numbers, plus the classic V1 briefing.

The Fireworks (hosted) mode is EXPLICITLY DISABLED in this build: this page never imports the provider layer and never calls a hosted
service. Answers come from (a) calculations over the workspace, (b) the offline extractive engine over approved synthetic documents,
or (c) the classic rule-based Hoomi when document search is unavailable or when you choose it.
"""
import streamlit as st

import hoomi
import theme
from gtm import numbers_qa
from rag import app_index, chat
from theme import section
from views import mascot

HOSTED_MODE_AVAILABLE = False            # Fireworks mode stays off; see README for the separate, explicitly confirmed smoke test
MAX_HISTORY = 60
KIND_BADGE = {"answered": ("ok", "Answered · quoted from documents"), "partial": ("warn", "Partial answer"),
              "insufficient": ("warn", "Insufficient evidence"), "numbers": ("ok", "Calculated from the workspace"),
              "rulebased": ("off", "Classic rule-based fallback")}


@st.cache_resource(show_spinner=False)
def _embeddings():
    return app_index.make_embeddings()                                   # cached local FastEmbed model; never downloads


def load_knowledge(gtm_store):
    """(store or None, error text, info). Document search degrades gracefully if the local model or index is unavailable."""
    try:
        emb = _embeddings()
        with st.spinner("Preparing Hoomi's knowledge base (local; first run takes about a minute)…"):
            store, info = app_index.ensure_index(emb, gtm_store)
        return store, "", info
    except Exception as exc:                                              # e.g. embedding model not cached yet
        return None, f"{type(exc).__name__}: {str(exc)[:140]}", {}


def render_message(msg):
    """One chat message: a status badge, the text, the sources with verified quotes, and how it was checked."""
    if msg["role"] == "user":
        st.markdown(theme.safe(msg["content"]))
        return
    cls, label = KIND_BADGE.get(msg["kind"], ("off", msg["kind"]))
    meta = msg.get("meta", {})
    st.markdown(f'<span class="badge {cls}">{label}</span>', unsafe_allow_html=True)
    st.markdown(theme.safe(msg["content"]))
    if msg.get("sources"):
        with st.expander(f"Sources ({len(msg['sources'])})"):
            for s in msg["sources"]:
                kyc = " · KYC profile" if s.get("doc_type") == "kyc" else ""
                st.markdown(theme.safe(f'<div class="src"><span class="cite">{s["citation"]}</span> <small>{s["chunk_id"]} · distance {s["distance"]:.2f}{kyc}</small>'
                                       f'<br><q>{s["quote"]}</q></div>'), unsafe_allow_html=True)
    if msg.get("facts"):
        with st.expander("How this was checked"):
            for f in msg["facts"]:
                mark = "✅" if f["supported"] else "⚠️"
                score = f" (similarity {f['score']:.2f})" if f.get("score") is not None else ""
                st.markdown(theme.safe(f"{mark} **{f['fact']}**{score}: {f['detail']}"))
            bits = []
            if meta.get("best_distance") is not None:
                bits.append(f"closest passage distance {meta['best_distance']:.2f} against a gate of {meta['gate']:g}")
            if meta.get("scope_account"):
                bits.append(f"search scoped to the KYC profile of {meta['scope_account']}")
            bits.append("zero hosted calls")
            st.caption("; ".join(bits).capitalize() + ".")


def _suggest(question):
    st.session_state.hoomi_pending = question


def _chat(ws, name, gtm_store):
    st.session_state.setdefault("hoomi_chat", [])
    knowledge, error, info = load_knowledge(gtm_store)
    left, right = st.columns([3, 2], vertical_alignment="center")
    with left:
        st.radio("Answer from", chat.ROUTES, key="hoomi_route", horizontal=True, label_visibility="collapsed",
                 help="Auto sends metric questions to the calculations and everything else to the documents. 'Rule-based' is the classic V1 Hoomi.")
    with right:
        st.toggle("Fireworks AI (hosted)", value=False, disabled=True, key="hoomi_hosted_toggle",
                  help="Disabled in this build. Hosted AI would send your question and retrieved passages to a provider.")
    if knowledge is not None:
        st.caption(f"Knowledge base: {info['chunks']} passages from {info['documents'] - info['kyc_documents']} documents and {info['kyc_documents']} KYC profiles · "
                   f"gate distance {chat.gate_text()} (provisional) · all local.")
    else:
        st.markdown(theme.safe(f'<div class="warn"><b>Document search is unavailable.</b> {error}. Metric questions and the classic rule-based Hoomi still work. '
                               f'To enable document search, run <code>python -m rag.app_index</code> once (see README).</div>'), unsafe_allow_html=True)

    st.markdown("**Try a question**")
    cols = st.columns(3)
    for i, q in enumerate(chat.DOC_SUGGESTIONS[:3] + numbers_qa.SUGGESTIONS[:3]):
        cols[i % 3].button(q, key=f"hsug_{i}", width="stretch", on_click=_suggest, args=(q,))

    prompt = st.chat_input("Ask about services, segments, positioning, a KYC profile, or the numbers…")
    question = st.session_state.pop("hoomi_pending", None) or prompt
    if question:
        history = st.session_state.hoomi_chat
        shown = chat.clean_question(question)
        with st.spinner("Hoomi is looking…"):
            reply = chat.ask(question, st.session_state.get("hoomi_route", "Auto"), gtm_store, knowledge, error, ws)
        history += [{"role": "user", "content": shown}, reply]
        del history[:-MAX_HISTORY]
    history = st.session_state.hoomi_chat
    if not history:
        theme.empty_state("Ask me anything about Kai's Company", "I quote approved documents with citations, calculate the numbers from the workspace, "
                          "and tell you plainly when I don't have enough evidence.", "💬")
    for m in history:
        with st.chat_message(m["role"]):
            render_message(m)
    if history and st.button("Clear conversation", key="hoomi_clear"):
        st.session_state.hoomi_chat = []
        st.rerun()


def _briefing(ws, name):
    """The classic V1 briefing, unchanged: priorities, alerts and quick answers from the V1 demo data store."""
    st.session_state.setdefault("hoomi_hist", [])
    mood = st.session_state.get("hoomi_mood", "greet")
    b = hoomi.briefing(ws, name)
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    with c1:
        st.markdown(hoomi.hoomi_svg(190, mood), unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="hero" style="margin:0">{theme.sparkles()}<div class="eyebrow">Classic Hoomi (V1)</div><h1>Your sales intelligence buddy</h1>'
                    f'<p>{b["greeting"]}</p></div>', unsafe_allow_html=True)
        st.write("")
        st.markdown(theme.safe('<div class="bubble">' + hoomi.md_to_html("\n".join(f"- {x}" for x in b["bullets"])) + "</div>"), unsafe_allow_html=True)
    section("Top 5 priorities", "ranked by value and urgency")
    for i, p in enumerate(hoomi.top_priorities(ws), 1):
        st.markdown(theme.safe(f'<div class="ok"><b>{i}. {p["icon"]} {p["title"]}</b><br><span style="opacity:.85">{p["detail"]}</span></div>'), unsafe_allow_html=True)
    left, right = st.columns([3, 2])
    with left:
        section("Quick questions", "classic rule-based answers over the V1 data store")
        with st.form("ask_hoomi_v1", clear_on_submit=True):
            typed = st.text_input("Your question", placeholder="e.g. Which opportunities are at risk?", label_visibility="collapsed")
            go = st.form_submit_button("Ask classic Hoomi", type="primary")
        cols = st.columns(3)
        clicked = None
        for i, q in enumerate(hoomi.SUGGESTED_QUESTIONS):
            if cols[i % 3].button(q, key=f"hq_{i}", width="stretch"):
                clicked = q
        question = clicked or (typed if go else None)
        if question:
            text, mood_new = hoomi.answer_with_mood(question, ws)
            st.session_state.hoomi_hist.insert(0, (question, text))
            st.session_state.hoomi_mood = mood_new if mood_new in ("success", "alert") else "greet"
            st.rerun()
        for qn, ans in st.session_state.hoomi_hist[:5]:
            st.markdown(f"**You:** {qn}")
            st.markdown(theme.safe(f'<div class="bubble">{hoomi.md_to_html(ans)}</div>'), unsafe_allow_html=True)
            st.write("")
    with right:
        section("Alerts")
        with st.container(border=True):
            st.markdown("**⏸️ Stalled deals**")
            al = hoomi.stalled_alerts(ws.opps)
            for x in al[:4]:
                st.markdown(theme.safe(f'<div class="warn">{hoomi.md_to_html(x)}</div>'), unsafe_allow_html=True)
            if not al:
                st.caption("None 🎉")
            st.markdown("**⏰ Overdue follow-ups**")
            ov = hoomi.overdue_alerts(ws.opps)
            for x in ov[:4]:
                st.markdown(theme.safe(f'<div class="warn">{hoomi.md_to_html(x)}</div>'), unsafe_allow_html=True)
            if not ov:
                st.caption("None 🎉")
        with st.container(border=True):
            st.markdown("**💰 Revenue, GP & reps**")
            for x in hoomi.financial_insights(ws) + hoomi.rep_insights(ws):
                st.markdown(theme.safe(f"- {x}"))


def render(ws, name="", gtm_store=None):
    left, right = st.columns([1, 3], vertical_alignment="center")
    with left:
        mascot.render(170)
    with right:
        st.markdown(f'<div class="hero" style="margin:0">{theme.sparkles()}<div class="eyebrow">Hoomi · your GTM assistant</div><h1>Ask Hoomi</h1>'
                    f'<p>Answers come from approved documents with citations, calculations over the workspace, or a plain '
                    f'"I don\'t have enough evidence".</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="mode-bar"><span class="badge ok">Offline demo</span> '
                '<span style="color:var(--muted);font-size:.84rem">Extractive (no AI model) · zero hosted calls · nothing leaves this computer · '
                'Fireworks mode is disabled in this build</span></div>', unsafe_allow_html=True)
    tab_chat, tab_brief = st.tabs(["💬 Ask Hoomi", "📋 Classic briefing (V1 data)"])
    with tab_chat:
        _chat(ws, name, gtm_store)
    with tab_brief:
        _briefing(ws, name)
