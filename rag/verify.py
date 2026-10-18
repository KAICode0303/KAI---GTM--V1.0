"""Evidence-verified answering: draft an answer, then check it fact by fact against the retrieved passages.

Pipeline (`answer_verified`):
  1. GATE + CONTEXT   gather_evidence() as before. A failed gate refuses with no model call.
  2. GENERATE         model call 1 returns JSON: the distinct facts the question asks for ("requested_facts") and a draft "answer".
  3. VERIFY           model call 2 judges EACH requested fact: supported or unsupported, the exact sentence of the draft that
                      states it ("claim"), the supporting chunk ids and a short verbatim "evidence_quote".
  4. CHECK IN CODE    nothing the verifier says is trusted blindly. A fact stays "supported" only if its cited chunk ids are in
                      the context, its quote literally appears in a cited chunk, and its claim is an exact excerpt of the draft.
  5. ASSEMBLE         the final text is built ONLY from supported claims (exact draft excerpts, with any model-written bracket
                      citations removed). Unsupported facts are listed under an explicit "Partial answer" label. Citations are
                      derived ONLY from the chunks that contain a verified quote, never from model-written text.

Fail closed: output that is not valid JSON, has the wrong shape, an out-of-range status, a fact list that does not match the
requested facts, or a missing field makes the whole answer a refusal. A well-formed but ungrounded "supported" fact is
downgraded to unsupported. An exception from the provider is a refusal; configuration errors (missing key, hosted calls not
approved) are raised, never hidden.

Limits (be aware): the code can prove a quote exists in a cited chunk and that a claim is in the draft; it cannot prove that the
quote really entails the claim. That judgement is the verifier model's, and it is untested against a real model.
"""
import json
import re
from dataclasses import dataclass, field

from rag.answer import INSUFFICIENT, REFUSAL, gather_evidence
from rag.providers import ConfigurationError

MAX_FACTS = 6
MIN_QUOTE_CHARS = 12                 # a "quote" shorter than this is not evidence
STATUSES = ("supported", "unsupported")
PARTIAL_HEADER = "Partial answer: only part of your question is supported by the approved documents."
UNSUPPORTED_LABEL = "Not found in the approved documents:"

GENERATE_PROMPT = """You are Hoomi, a GTM assistant. Use ONLY the passages below.
1. List the distinct facts the question asks for as "requested_facts": short phrases, at most {max_facts}. A single-part question has exactly one.
2. Write a concise "answer" that addresses each requested fact using only the passages. Do not write citations or passage ids in the answer. If the passages cannot support an answer, set "answer" to exactly {sentinel}.
Reply with ONLY a JSON object: {{"requested_facts": ["..."], "answer": "..."}}

Passages:
{passages}

Question: {question}"""

VERIFY_PROMPT = """You are a strict evidence checker. Use ONLY the passages below, never outside knowledge.
For EACH requested fact, decide whether the draft answer's statement of that fact is directly supported by a passage.
Reply with ONLY a JSON object:
{{"facts": [{{"fact": "<requested fact, copied exactly>", "status": "supported" or "unsupported",
   "claim": "<the exact sentence(s) copied from the draft answer that state this fact; empty if unsupported>",
   "supporting_chunk_ids": ["<passage ids>"], "evidence_quote": "<a short exact quote copied from a cited passage; empty if unsupported>"}}],
 "unaddressed_parts": ["<any part of the question that none of the requested facts covers; otherwise an empty list>"]}}
Include exactly one entry per requested fact. Use "unsupported" whenever the passages do not clearly state the fact.

Question: {question}

Requested facts:
{facts}

Draft answer:
{draft}

Passages:
{passages}"""


class InvalidModelOutput(ValueError):
    """The model's reply cannot be trusted structurally. Callers fail closed."""


# ---------------------------------------------------------------- small helpers
def _ws(text):
    return " ".join(str(text).split())


def _fold(text):
    """Whitespace-collapsed, lower-cased, straight quotes: for tolerant quote matching only."""
    return _ws(str(text).replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')).lower()


_CITATION = re.compile(r"\s*\[[^\[\]]*(?:\.md|›|#\d)[^\[\]]*\]")


def strip_citations(text):
    """Remove model-written bracket citations; the real citations are added from verified chunks."""
    return _ws(_CITATION.sub("", text))


def strip_fence(raw):
    t = raw.strip()
    m = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", t, re.DOTALL | re.IGNORECASE)
    return m.group(1) if m else t


def parse_json_object(raw, what):
    if not isinstance(raw, str):
        raise InvalidModelOutput(f"{what}: reply is not text")
    try:
        data = json.loads(strip_fence(raw))
    except ValueError:
        raise InvalidModelOutput(f"{what}: reply is not valid JSON") from None
    if not isinstance(data, dict):
        raise InvalidModelOutput(f"{what}: JSON is not an object")
    return data


def format_passages(hits):
    return "\n\n".join(f"Passage id: {h.chunk_id} | source: {h.source} › {h.section}\n{h.text}" for h in hits)


# ---------------------------------------------------------------- stage 2: generation
def build_generation_prompt(evidence, max_facts=MAX_FACTS):
    return GENERATE_PROMPT.format(max_facts=max_facts, sentinel=INSUFFICIENT, passages=format_passages(evidence.hits),
                                  question=evidence.question)


def parse_generation(raw, max_facts=MAX_FACTS):
    data = parse_json_object(raw, "generation")
    facts, answer = data.get("requested_facts"), data.get("answer")
    if not isinstance(facts, list) or not 1 <= len(facts) <= max_facts:
        raise InvalidModelOutput(f"generation: requested_facts must be a list of 1 to {max_facts} items")
    if not all(isinstance(f, str) and f.strip() for f in facts):
        raise InvalidModelOutput("generation: every requested fact must be a non-empty string")
    facts = [_ws(f) for f in facts]
    if len({_fold(f) for f in facts}) != len(facts):
        raise InvalidModelOutput("generation: duplicate requested facts")
    if not isinstance(answer, str) or not answer.strip():
        raise InvalidModelOutput("generation: answer must be a non-empty string")
    return facts, answer.strip()


# ---------------------------------------------------------------- stage 3-4: verification
@dataclass
class FactResult:
    fact: str
    supported: bool
    claim: str = ""                                   # exact draft excerpt (citations removed); only when supported
    chunk_ids: list = field(default_factory=list)     # ONLY chunks that contain the verified quote
    quote: str = ""
    reason: str = ""                                  # why a fact is unsupported
    score: float = None                               # similarity of the chosen sentence (offline extractive engine only)


def build_verification_prompt(evidence, facts, draft):
    return VERIFY_PROMPT.format(question=evidence.question, facts="\n".join(f"{i}. {f}" for i, f in enumerate(facts, 1)),
                                draft=draft, passages=format_passages(evidence.hits))


def _ground(fact, entry, hits_by_id, draft):
    """Accept a 'supported' verdict only if code can confirm its three claims; otherwise downgrade to unsupported."""
    if entry["status"] == "unsupported":
        return FactResult(fact, False, reason="judged_unsupported")
    ids = entry["supporting_chunk_ids"]
    if not ids:
        return FactResult(fact, False, reason="no_chunk_cited")
    if any(i not in hits_by_id for i in ids):
        return FactResult(fact, False, reason="unknown_chunk_id")
    quote = _fold(entry["evidence_quote"])
    if len(quote) < MIN_QUOTE_CHARS:
        return FactResult(fact, False, reason="quote_missing_or_too_short")
    verified = [i for i in dict.fromkeys(ids) if quote in _fold(hits_by_id[i].text)]
    if not verified:
        return FactResult(fact, False, reason="quote_not_in_cited_chunk")
    claim = _ws(entry["claim"])
    if not claim or claim not in _ws(draft):
        return FactResult(fact, False, reason="claim_not_in_draft")
    shown = strip_citations(claim)
    if not shown:
        return FactResult(fact, False, reason="claim_empty_after_cleanup")
    return FactResult(fact, True, claim=shown, chunk_ids=verified, quote=_ws(entry["evidence_quote"]))


def parse_verification(raw, facts, hits, draft):
    """Return one FactResult per requested fact (plus one per unaddressed part). Raises InvalidModelOutput on any structural doubt."""
    data = parse_json_object(raw, "verification")
    entries, unaddressed = data.get("facts"), data.get("unaddressed_parts")
    if not isinstance(entries, list) or not isinstance(unaddressed, list) or not all(isinstance(u, str) for u in unaddressed):
        raise InvalidModelOutput("verification: 'facts' and 'unaddressed_parts' must both be lists")
    if len(entries) != len(facts):
        raise InvalidModelOutput("verification: needs exactly one entry per requested fact")
    by_fold, seen, graded = {_fold(f): f for f in facts}, set(), {}
    hits_by_id = {h.chunk_id: h for h in hits}
    for e in entries:
        if not isinstance(e, dict):
            raise InvalidModelOutput("verification: each fact entry must be an object")
        for name, kind in (("fact", str), ("status", str), ("claim", str), ("evidence_quote", str), ("supporting_chunk_ids", list)):
            if not isinstance(e.get(name), kind):
                raise InvalidModelOutput(f"verification: entry field '{name}' is missing or has the wrong type")
        if not all(isinstance(i, str) for i in e["supporting_chunk_ids"]):
            raise InvalidModelOutput("verification: supporting_chunk_ids must be strings")
        if e["status"] not in STATUSES:
            raise InvalidModelOutput("verification: status must be exactly 'supported' or 'unsupported'")
        key = _fold(e["fact"])
        if key not in by_fold or key in seen:
            raise InvalidModelOutput("verification: entries must match the requested facts one-to-one")
        seen.add(key)
        graded[key] = _ground(by_fold[key], e, hits_by_id, draft)
    results = [graded[_fold(f)] for f in facts]
    for part in (_ws(u) for u in unaddressed):
        if part and _fold(part) not in by_fold:
            results.append(FactResult(part, False, reason="unaddressed_part"))
    return results


# ---------------------------------------------------------------- stage 5: assembly and the public API
@dataclass
class VerifiedAnswer:
    status: str                                       # "answered" | "partial" | "refused"
    text: str
    facts: list = field(default_factory=list)         # FactResult per requested fact
    sources: list = field(default_factory=list)       # citations from verified chunks only
    source_chunk_ids: list = field(default_factory=list)
    reason: str = ""                                  # when refused: gate | llm_error | generation_invalid | model_insufficient | ...
    detail: str = ""                                  # diagnostic text (never contains the prompt or any key)
    evidence: object = None
    model_calls: int = 0
    engine: str = ""                                  # e.g. "offline-extractive"; empty for the model-backed pipeline


def assemble(facts, hits):
    supported = [f for f in facts if f.supported]
    if not supported:
        return "refused", REFUSAL, [], [], "nothing_supported"
    by_id = {h.chunk_id: h for h in hits}
    ids = list(dict.fromkeys(i for f in supported for i in f.chunk_ids))
    sources = [by_id[i].citation for i in ids]
    text = " ".join(dict.fromkeys(f.claim for f in supported))                 # two facts can share one verified sentence
    missing = [f.fact for f in facts if not f.supported]
    if missing:
        text = f"{PARTIAL_HEADER}\n\n{text}\n\n{UNSUPPORTED_LABEL} " + "; ".join(missing)
        return "partial", text, sources, ids, ""
    return "answered", text, sources, ids, ""


def answer_verified(store, question, llm, max_distance=None, context=None, max_facts=MAX_FACTS):
    """Gate, generate, verify, assemble. `llm(prompt) -> str` is any provider (a mock in tests)."""
    evidence = gather_evidence(store, question, max_distance=max_distance, context=context)

    def refuse(reason, detail="", calls=0):
        return VerifiedAnswer("refused", REFUSAL, reason=reason, detail=detail, evidence=evidence, model_calls=calls)

    if not evidence.sufficient:
        return refuse("gate")
    if any(not h.chunk_id for h in evidence.hits):
        return refuse("index_missing_chunk_ids", "rebuild the index with rag.retriever.build_index")

    def call(prompt):
        try:
            return llm(prompt), None
        except ConfigurationError:
            raise                                     # setup problems are loud, not refusals
        except Exception as exc:                      # provider or network failure: fail closed
            return None, type(exc).__name__

    raw, err = call(build_generation_prompt(evidence, max_facts))
    if err:
        return refuse("llm_error", f"generation call failed: {err}", 1)
    try:
        facts, draft = parse_generation(raw, max_facts)
    except InvalidModelOutput as exc:
        return refuse("generation_invalid", str(exc), 1)
    if INSUFFICIENT in draft:
        return refuse("model_insufficient", calls=1)

    raw, err = call(build_verification_prompt(evidence, facts, draft))
    if err:
        return refuse("llm_error", f"verification call failed: {err}", 2)
    try:
        results = parse_verification(raw, facts, evidence.hits, draft)
    except InvalidModelOutput as exc:
        return refuse("verification_invalid", str(exc), 2)

    status, text, sources, ids, reason = assemble(results, evidence.hits)
    return VerifiedAnswer(status, text, results, sources, ids, reason, evidence=evidence, model_calls=2)
