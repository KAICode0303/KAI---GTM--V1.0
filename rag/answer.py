"""Grounded answering with an insufficient-evidence refusal path.

The model call is injected as `generate(prompt) -> str`, so this module works with any provider (and with a fake in
tests). No provider is configured or called here.

Refusal rules - the model is NOT called when:
  * retrieval returns nothing, or every chunk is farther than the distance threshold.
and the answer is replaced by the refusal when:
  * the model itself replies with the INSUFFICIENT sentinel.

The distance threshold depends on the embedding model and on the corpus. DEFAULT_MAX_DISTANCE is only a PROVISIONAL
starting point for BAAI/bge-small-en-v1.5 on the 3-document synthetic corpus; recalibrate it on the evaluation set.
Override it with the `max_distance` argument or the RAG_MAX_DISTANCE environment variable.
"""
import os
from dataclasses import dataclass, field

from rag.retriever import retrieve

DEFAULT_MAX_DISTANCE = 0.70        # provisional - not universally correct
INSUFFICIENT = "INSUFFICIENT_EVIDENCE"
REFUSAL = ("I don't have enough evidence in the approved GTM documents to answer that. "
           "Try rephrasing, or add a relevant document to the knowledge base.")

PROMPT = """You are Hoomi, a GTM assistant. Answer the question using ONLY the numbered context passages below.
- Cite the passages you use with their bracketed citation, exactly as written, e.g. [file.md › Section].
- If the passages do not contain the answer, reply with exactly: {sentinel}
- Do not use outside knowledge and do not guess.

Context:
{context}

Question: {question}
Answer:"""


def resolve_max_distance(max_distance=None):
    """Explicit argument > RAG_MAX_DISTANCE environment variable > provisional default."""
    if max_distance is not None:
        return float(max_distance)
    env = os.environ.get("RAG_MAX_DISTANCE", "").strip()
    if env:
        try:
            return float(env)
        except ValueError:
            raise ValueError(f"RAG_MAX_DISTANCE must be a number, got {env!r}") from None
    return DEFAULT_MAX_DISTANCE


@dataclass
class Evidence:
    question: str
    hits: list                       # chunks within the threshold, closest first
    max_distance: float
    best_distance: float = None      # closest chunk overall (even if rejected) - useful when tuning
    sufficient: bool = False


@dataclass
class Answer:
    text: str
    grounded: bool                   # False = refusal
    sources: list = field(default_factory=list)      # citations built from the retrieved chunks, never from model text
    evidence: Evidence = None


def gather_evidence(store, question, k=4, max_distance=None):
    limit = resolve_max_distance(max_distance)
    everything = retrieve(store, question, k=k)
    kept = [h for h in everything if h.distance <= limit]
    return Evidence(question=question, hits=kept, max_distance=limit,
                    best_distance=everything[0].distance if everything else None, sufficient=bool(kept))


def build_prompt(evidence):
    context = "\n\n".join(f"{i}. {h.citation}\n{h.text}" for i, h in enumerate(evidence.hits, 1))
    return PROMPT.format(sentinel=INSUFFICIENT, context=context, question=evidence.question)


def answer_question(store, question, generate, k=4, max_distance=None):
    evidence = gather_evidence(store, question, k=k, max_distance=max_distance)
    if not evidence.sufficient:
        return Answer(text=REFUSAL, grounded=False, evidence=evidence)           # model never called
    reply = (generate(build_prompt(evidence)) or "").strip()
    if not reply or INSUFFICIENT in reply:
        return Answer(text=REFUSAL, grounded=False, evidence=evidence)
    sources = list(dict.fromkeys(h.citation for h in evidence.hits))
    return Answer(text=reply, grounded=True, sources=sources, evidence=evidence)
