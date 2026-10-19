"""Hoomi: a RAG chatbot over approved documents, KYC profiles and the workspace numbers, plus the classic V1 briefing.

Answers come from (a) calculations over the workspace, (b) document search (local FastEmbed vectors in Chroma) answered either by the OFFLINE
extractive engine (default, zero hosted calls) or, only if you choose it AND explicitly approve it, in natural language by Fireworks AI through
the verified generate-then-verify pipeline, or (c) the classic rule-based Hoomi when document search is unavailable or when you choose it.
Hosted calls are off by default: they need the provider configured in your own .env AND a per-session approval checkbox on this page.
"""
import dataclasses

import streamlit as st

import hoomi
import theme
from gtm import numbers_qa
from rag import app_index, chat
from theme import section
from views import mascot

MAX_HISTORY = 60
KIND_BADGE = {"answered": ("ok", "Answered · quoted from documents"), "partial": ("warn", "Partial answer"),
              "insufficient": ("warn", "Insufficient evidence"), "numbers": ("ok", "Workspace figures"),
              "rulebased": ("off", "Classic rule-based fallback")}
ENGINES = ("Offline demo (quoted sentences)", "Fireworks (natural language, needs your approval)")


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


def source_title(citation):
    """'[05_case_study_model_evaluation.md › Scope]' -> ('05_case_study_model_evaluation.md', 'Scope')."""
    body = citation.strip("[]")
    file, _, section = body.partition(" › ")
    return file, section


def render_message(msg):
    """One chat message: a status badge, the answer, readable citation cards, and an expandable Technical Details section."""
    if msg["role"] == "user":
        st.markdown(theme.safe(msg["content"]))
        return
    cls, label = KIND_BADGE.get(msg["kind"], ("off", msg["kind"]))
    meta = msg.get("meta", {})
    if meta.get("engine") == "fireworks-verified" and msg["kind"] in ("answered", "partial"):
        label = "Answered · Fireworks, verified against sources" if msg["kind"] == "answered" else "Partial answer · Fireworks, verified"
    st.markdown(f'<span class="badge {cls}">{label}</span>', unsafe_allow_html=True)
    st.markdown(theme.safe(msg["content"]))
    if msg.get("sources"):
        cards = []
        for s in msg["sources"]:
            file, section = source_title(s["citation"])
            kyc = " · KYC profile" if s.get("doc_type") == "kyc" else ""
            cards.append(f'<div class="src"><span class="cite">📄 {file}</span> <span class="sec">› {section}{kyc}</span><br><q>{s["quote"]}</q></div>')
        st.markdown(theme.safe(f'<div class="src-head">Sources ({len(cards)})</div>' + "".join(cards)), unsafe_allow_html=True)
    technical = msg.get("facts") or meta
    if technical:
        with st.expander("Technical Details"):
            for f in msg.get("facts", []):
                mark = "✅" if f["supported"] else "⚠️"
                score = f" (similarity {f['score']:.2f})" if f.get("score") is not None else ""
                st.markdown(theme.safe(f"{mark} **{f['fact']}**{score}: {f['detail']}"))
            for s in msg.get("sources", []):
                st.markdown(theme.safe(f'<small><code>{s["chunk_id"]}</code> · distance {s["distance"]:.2f} · {s["citation"]}</small>'), unsafe_allow_html=True)
            bits = []
            if meta.get("engine"):
                bits.append(f"engine: {meta['engine']}" + (f", route: {meta['route']}" if meta.get("route") else ""))
            if meta.get("best_distance") is not None:
                bits.append(f"closest passage distance {meta['best_distance']:.2f} against a gate of {meta['gate']:g}")
            if meta.get("scope_account"):
                bits.append(f"search scoped to the KYC profile of {meta['scope_account']}")
            if meta.get("hosted_calls"):
                u = meta.get("usage") or {}
                tokens = f" ({u['input_tokens']} in, {u['output_tokens']} out)" if u.get("input_tokens") is not None and u.get("output_tokens") is not None else ""
                bits.append(f"{meta['hosted_calls']} hosted call(s) to Fireworks, approved by you{tokens}")
            else:
                bits.append("zero hosted calls")
            line = "; ".join(bits)
            st.caption(line[:1].upper() + line[1:] + ".")


def _suggest(question):
    st.session_state.hoomi_pending = question


def hosted_setup():
    """What the Fireworks option needs. Returns (client or None, status text). A client exists ONLY when the provider is configured in the
    user's own .env and the user has ticked the approval checkbox on this page. Nothing here sends anything."""
    from rag import providers                                           # imported only when the user opens this option
    try:
        cfg = providers.load_config()
    except (ValueError, NotImplementedError) as exc:
        return None, f"Fireworks is not set up: {exc}"
    missing = [name for name, ok in (("LLM_MODEL", cfg.model), (providers.API_KEY_ENV["fireworks"], cfg.api_key)) if not ok]
    if missing:
        return None, f"Fireworks is not set up yet: add {' and '.join(missing)} to your .env (see .env.example). Until then answers stay offline."
    approved = st.checkbox("I approve sending my question and the retrieved passages to Fireworks AI during this session. Nothing else is sent, "
                           "and no keys are shown.", key="hoomi_hosted_ok")
    if not approved:
        return None, "Waiting for your approval. Until you tick the box, nothing is sent and answers stay offline."
    sig = (cfg.provider, cfg.model, cfg.max_tokens, cfg.temperature)
    held = st.session_state.get("hoomi_client")
    if held is None or held[0] != sig:                                  # the approval is the decision; the RAG_ALLOW_HOSTED_CALLS variable is ignored
        held = (sig, providers.LLMClient(dataclasses.replace(cfg, allow_hosted_calls=True)))
        st.session_state.hoomi_client = held
    return held[1], f"Approved for this session: {cfg.provider} / {cfg.model}."


def knowledge_panel(info, cited):
    """All seven approved source documents, always visible. Documents cited in this conversation are highlighted."""
    from rag.ingest import load_documents
    rows = []
    try:
        docs = load_documents(app_index.APP_CORPUS_DIR)
    except Exception:
        docs = []
    for d in docs:
        md = d.metadata
        on = " on" if md["source"] in cited else ""
        rows.append(f'<div class="kb-doc{on}"><span class="kb-type">{md["doc_type"].replace("_", " ")}</span><b>{md["title"]}</b><small>{md["source"]}</small></div>')
    st.markdown(theme.safe(f'<div class="kb"><div class="kb-title">Knowledge base · {len(docs)} sources</div>' + "".join(rows) +
                           '<div class="kb-foot">Answers quote these documents. The sources used are shown under each answer.</div></div>'), unsafe_allow_html=True)


def history_panel():
    """Recent questions from this session; clicking one asks it again."""
    asked = [m["content"] for m in st.session_state.get("hoomi_chat", []) if m["role"] == "user"]
    if not asked:
        st.markdown('<div class="kb"><div class="kb-title">History</div><div class="kb-foot">Your questions will appear here.</div></div>', unsafe_allow_html=True)
        return
    st.markdown('<div class="kb-title" style="margin-top:.2rem">History</div>', unsafe_allow_html=True)
    for i, q in enumerate(reversed(asked[-6:])):
        st.button(q if len(q) < 60 else q[:57] + "…", key=f"hhist_{i}", width="stretch", on_click=_suggest, args=(q,), help="Ask this again")


def _chat(ws, name, gtm_store):
    """Suggestions, settings, the conversation, the knowledge base panel and the pinned chat input (the input must be created at the page's top level)."""
    st.session_state.setdefault("hoomi_chat", [])
    knowledge, error, info = load_knowledge(gtm_store)
    with st.expander("⚙️ Answer settings", expanded=False):
        c1, c2 = st.columns(2, vertical_alignment="center")
        with c1:
            st.radio("Answer from", chat.ROUTES, key="hoomi_route", horizontal=True,
                     help="Auto sends metric questions to the calculations and everything else to the documents. 'Rule-based' is the classic V1 Hoomi.")
        with c2:
            engine = st.radio("Answer style", ENGINES, key="hoomi_engine", horizontal=True,
                              help="Offline answers quote the documents. Fireworks writes a natural-language answer, then every claim is checked against the sources.")
        client, status = (None, "")
        if engine == ENGINES[1]:
            client, status = hosted_setup()
            (st.success if client else st.info)(status)
    engine = st.session_state.get("hoomi_engine", ENGINES[0])
    if knowledge is not None:
        st.caption(f"{info['chunks']} passages from {info['documents'] - info['kyc_documents']} documents and {info['kyc_documents']} KYC profiles · "
                   f"gate distance {chat.gate_text()} (provisional) · searched locally.")
    else:
        st.markdown(theme.safe(f'<div class="warn"><b>Document search is unavailable.</b> {error}. Metric questions and the classic rule-based Hoomi still work. '
                               f'To enable document search, run <code>python -m rag.app_index</code> once (see README).</div>'), unsafe_allow_html=True)

    main, side = st.columns([2.6, 1.15], gap="large")
    with side:
        knowledge_slot = st.container()
        history_slot = st.container()
    with main:
        st.markdown('<div class="sug-head">Try a question</div>', unsafe_allow_html=True)
        cols = st.columns(3)
        for i, q in enumerate(chat.DOC_SUGGESTIONS[:4] + numbers_qa.SUGGESTIONS[:2]):
            cols[i % 3].button(q, key=f"hsug_{i}", width="stretch", on_click=_suggest, args=(q,))
        conversation = st.container()                                   # filled below, after the input has been read
    prompt = st.chat_input("Ask Hoomi about capabilities, ideal customers, case studies, a KYC profile, or the numbers…")
    question = st.session_state.pop("hoomi_pending", None) or prompt
    if question:
        history = st.session_state.hoomi_chat
        shown = chat.clean_question(question)
        with st.spinner("Hoomi is looking…"):
            before = len(client.sent) if client is not None else 0
            reply = chat.ask(question, st.session_state.get("hoomi_route", "Auto"), gtm_store, knowledge, error, ws, hosted=client)
            if client is not None and len(client.sent) > before:
                reply["meta"]["usage"] = client.total_usage()
        history += [{"role": "user", "content": shown}, reply]
        del history[:-MAX_HISTORY]
    history = st.session_state.hoomi_chat
    cited = {s["chunk_id"].split("#")[0] for m in history for s in m.get("sources", [])}
    with conversation:
        if not history:
            theme.empty_state("Ask me anything about Kai's Company", "I quote the approved documents with citations, work out the numbers from the workspace, "
                              "and tell you plainly when I don't have enough evidence. Pick a question above or type below.", "💬")
        for m in history:
            with st.chat_message(m["role"], avatar="🧑‍💼" if m["role"] == "user" else "🐱"):
                render_message(m)
        if history and st.button("Clear conversation", key="hoomi_clear"):
            st.session_state.hoomi_chat = []
            st.rerun()
    with knowledge_slot:
        knowledge_panel(info, cited)
    with history_slot:
        history_panel()


def _briefing(ws, name):
    """The classic V1 briefing, unchanged: priorities, alerts and quick answers from the V1 demo data store."""
    st.session_state.setdefault("hoomi_hist", [])
    mood = st.session_state.get("hoomi_mood", "greet")
    b = hoomi.briefing(ws, name)
    c1, c2 = st.columns([1, 3], vertical_alignment="center")
    with c1:
        mascot.render(190, caption=False)
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
                    f'<p>Ask in plain language. Answers come from the approved documents with citations, from calculations over the workspace, or a plain '
                    f'"I don\'t have enough evidence".</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="mode-bar"><span class="badge ok">Offline by default</span> '
                '<span style="color:var(--muted);font-size:.84rem">Nothing leaves this computer unless you choose Fireworks and approve it</span></div>',
                unsafe_allow_html=True)
    _chat(ws, name, gtm_store)
