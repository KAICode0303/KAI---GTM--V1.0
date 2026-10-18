"""Hoomi chat logic (no Streamlit): routing, the offline document engine, structured numbers and the V1 rule-based fallback.

Three answer paths, kept apart on purpose:
  numbers    GTM metrics, calculated from the workspace (gtm/numbers_qa.py). Exact, never retrieved or generated.
  documents  approved synthetic documents + KYC profiles, answered by the OFFLINE EXTRACTIVE engine (rag/offline.py):
             quoted sentences, verified citations, an explicit insufficient-evidence answer. Zero hosted calls.
  rulebased  the classic V1 Hoomi (hoomi.answer_with_mood) over the V1 data store, kept as a fallback.

This module deliberately imports nothing from rag.providers: the hosted (Fireworks) pipeline is disabled in the app.
"""
import re

import hoomi
from gtm import numbers_qa, pulse
from rag import app_index, offline
from rag.answer import resolve_max_distance
from rag.verify import _fold, answer_verified

MAX_QUESTION_CHARS = 500
ROUTES = ("Auto", "Documents", "Numbers", "Rule-based")
ENGINE_LABEL = "Offline demo (extractive, no AI model, zero hosted calls)"
DOC_SUGGESTIONS = ["What services does Kai's Company offer?", "What is a managed service and when should we recommend it?",
                   "Who is the buyer at an AI lab and what signals should we look for?", "How do we position against crowd labeling platforms?",
                   "Which case study shows RLHF results, and what was the improvement?", "What does Deepcurrent Labs request?"]
INSUFFICIENT_HELP = ("Try rephrasing, ask about a service, segment, modality, positioning point, case study or a named account's KYC profile, "
                     "or ask a metric question such as the open pipeline.")


def clean_question(text):
    q = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(text or ""))
    return " ".join(q.split())[:MAX_QUESTION_CHARS]


def _message(kind, content, **extra):
    return {"role": "assistant", "kind": kind, "content": content, "sources": [], "facts": [], "meta": {}, **extra}


def from_verified(result, route, scope_account=None):
    """Turn an offline VerifiedAnswer into a chat message with sources and a per-fact check list."""
    ev = result.evidence
    by_id = {h.chunk_id: h for h in ev.hits} if ev else {}
    meta = {"engine": result.engine or "model", "route": route, "gate": ev.max_distance if ev else None,
            "best_distance": ev.best_distance if ev else None, "scope_account": scope_account, "model_calls": result.model_calls}
    if result.status == "refused":
        why = {"gate": "The closest passage was too far from your question to count as evidence.",
               "nothing_supported": "No retrieved sentence matched closely enough."}.get(result.reason, "No supporting evidence was found.")
        near = f" Closest passage distance {ev.best_distance:.2f} (limit {ev.max_distance:.2f})." if ev and ev.best_distance is not None else ""
        msg = _message("insufficient", f"**Insufficient evidence.** I don't have enough support in the approved documents to answer that. {why}{near} {INSUFFICIENT_HELP}")
        msg["meta"] = {**meta, "reason": result.reason}
        msg["facts"] = [{"fact": f.fact, "supported": False, "detail": f.reason, "score": f.score} for f in result.facts]
        return msg
    sources, seen = [], set()
    for f in result.facts:
        # each chunk is shown with the sentence that actually came from IT, never another chunk's quote
        pairs = f.quotes if f.quotes else [(cid, f.quote) for cid in f.chunk_ids[:1]]
        for cid, quote in (pairs if f.supported else []):
            if cid not in seen and cid in by_id and _fold(quote) in _fold(by_id[cid].text):
                seen.add(cid)
                h = by_id[cid]
                sources.append({"citation": h.citation, "chunk_id": cid, "quote": quote, "passage": h.text, "distance": h.distance, "doc_type": h.doc_type})
    msg = _message("answered" if result.status == "answered" else "partial", result.text, sources=sources)
    ok_detail = "quoted verbatim from the cited passage" if result.engine else "verified: the quote was found in the cited passage"
    msg["facts"] = [{"fact": f.fact, "supported": f.supported, "detail": f.reason or ok_detail, "score": f.score} for f in result.facts]
    msg["meta"] = meta
    return msg


def ask(question, route="Auto", gtm_store=None, knowledge=None, knowledge_error="", ws=None, hosted=None):
    """Answer one question. Returns an assistant message dict. Never raises for ordinary input.

    hosted: None (default) keeps everything offline. Pass an approved LLM client (rag.providers.LLMClient) to answer document questions
    in natural language with the verified generate-then-verify pipeline; the caller is responsible for the user's explicit approval."""
    q = clean_question(question)
    if not q:
        return _message("insufficient", "Type a question and I'll look it up.")
    if route not in ROUTES:
        route = "Auto"
    if route == "Rule-based":                                          # explicit choice of the classic V1 Hoomi
        return _rulebased(q, ws, "")
    want = numbers_qa.route(q) if route == "Auto" else route.lower()
    named = app_index.account_in_question(q, gtm_store) if gtm_store is not None else None
    if named and want == "numbers":
        # The numbers I calculate are workspace-wide. A question about ONE account must never be answered with a workspace-wide figure.
        if route == "Numbers":
            return _message("insufficient", f"**I can't calculate that for one account.** My figures cover the whole workspace, not {named}. "
                                            f"Open the GTM Workspace for account-level records, or ask about its KYC profile.",
                            meta={"route": "numbers", "engine": "calculation"})
        want = "documents"

    if want == "numbers" and gtm_store is not None:
        text = numbers_qa.answer(q, pulse.snapshot(gtm_store))
        if text:
            return _message("numbers", text, meta={"route": "numbers", "engine": "calculation"})
        if route == "Numbers":
            return _message("insufficient", "**I can't calculate that.** I answer these metrics: " + "; ".join(numbers_qa.SUGGESTIONS[:6]) + ".",
                            meta={"route": "numbers", "engine": "calculation"})
        want = "documents"

    if knowledge is None:                                              # document search unavailable: degrade to the classic rule-based Hoomi
        return _rulebased(q, ws, f"Document search is unavailable ({knowledge_error or 'no knowledge base loaded'}).")

    where, account = app_index.scope_filter(q, gtm_store)
    if hosted is not None:
        return _hosted_answer(q, knowledge, where, account, hosted)
    # An insufficient-evidence answer is final: it is never "rescued" by the loose V1 keyword rules (which could, for example,
    # read "who won the football world cup" as a won-revenue question).
    return from_verified(offline.answer_offline(knowledge, q, where=where), "documents", account)


FALLBACK_REASONS = {"llm_error": "the hosted call failed", "generation_invalid": "the hosted reply was not usable",
                    "verification_invalid": "the hosted answer could not be verified"}


def _hosted_answer(q, knowledge, where, account, client):
    """Natural-language answer through the verified pipeline. If the hosted step fails or cannot be verified, show the offline answer instead
    (clearly labelled). A refusal for lack of evidence is final, exactly as offline."""
    from rag.providers import ConfigurationError
    try:
        result = answer_verified(knowledge, q, client, where=where)
    except ConfigurationError as exc:
        msg = _message("insufficient", f"**Fireworks is not available.** {exc}", meta={"route": "documents", "engine": "fireworks"})
        return msg
    if result.status == "refused" and result.reason in FALLBACK_REASONS:
        offline_msg = from_verified(offline.answer_offline(knowledge, q, where=where), "documents", account)
        offline_msg["content"] = (f"_{FALLBACK_REASONS[result.reason].capitalize()} ({result.detail or result.reason}), so this is the offline answer instead._\n\n"
                                  + offline_msg["content"])
        offline_msg["meta"].update(hosted_fallback=result.reason, hosted_calls=result.model_calls)
        return offline_msg
    msg = from_verified(result, "documents", account)
    msg["meta"].update(engine="fireworks-verified", hosted_calls=result.model_calls)
    return msg


def _rulebased(question, ws, notice):
    if ws is None:
        return _message("insufficient", f"{notice} {INSUFFICIENT_HELP}".strip(), meta={"route": "rulebased"})
    text, _mood = hoomi.answer_with_mood(question, ws)
    if text.startswith("I only know some topics"):
        return _message("insufficient", f"{notice} **Insufficient evidence.** {INSUFFICIENT_HELP}".strip(), meta={"route": "rulebased"})
    note = f"_{notice}_\n\n" if notice else ""
    return _message("rulebased", f"{note}{text}\n\n_Classic rule-based Hoomi: keyword matching over the classic data store. It can misread questions, "
                                 f"so check important figures against the Executive Pulse._",
                    meta={"route": "rulebased", "engine": "rule-based"})


def gate_text():
    return f"{resolve_max_distance():g}"
