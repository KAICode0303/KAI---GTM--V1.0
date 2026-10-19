"""Grounded answering with an insufficient-evidence refusal path.

The model call is injected as `generate(prompt) -> str`, so this module works with any provider (and with a fake in
tests). No provider is configured or called here.

Two separate decisions:
  1. ANSWERABILITY GATE - "is there any evidence at all?" The model is NOT called, and the refusal is returned, when
     retrieval is empty or the CLOSEST chunk is farther than `max_distance`.
  2. CONTEXT SELECTION - "which chunks does the model see?" Only runs once the gate has passed. A ContextPolicy picks
     the chunks by rank (`k`), with an optional absolute cap and an optional margin relative to the best hit. A chunk
     is therefore no longer dropped just because it is farther than the gate distance: supporting evidence for the
     second half of a multi-part question often sits further away than the best hit.
After generation, the answer is replaced by the refusal if the model replies with the INSUFFICIENT sentinel.

All distance settings depend on the embedding model and the corpus. DEFAULT_MAX_DISTANCE and the ContextPolicy
defaults are PROVISIONAL starting points (BAAI/bge-small-en-v1.5, 3-document synthetic corpus); recalibrate on the
evaluation set. Environment overrides: RAG_MAX_DISTANCE (gate), RAG_CONTEXT_K, RAG_CONTEXT_MAX_DISTANCE,
RAG_CONTEXT_MARGIN, RAG_CONTEXT_MIN_CHUNKS.
"""
import os
from dataclasses import dataclass, field
from typing import Optional

from rag.retriever import retrieve

DEFAULT_MAX_DISTANCE = 0.70        # answerability gate - provisional, not universally correct
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


# ---------------------------------------------------------------- configuration
def _env_number(name, cast):
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return cast(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None


def resolve_max_distance(max_distance=None):
    """Gate distance. Explicit argument > RAG_MAX_DISTANCE environment variable > provisional default."""
    if max_distance is not None:
        return float(max_distance)
    env = _env_number("RAG_MAX_DISTANCE", float)
    return DEFAULT_MAX_DISTANCE if env is None else env


@dataclass(frozen=True)
class ContextPolicy:
    """Which retrieved chunks are handed to the model once the gate has passed.

    k:               at most this many chunks, taken in rank order.
    max_distance:    optional absolute cap; chunks farther than this are dropped (None = no cap).
    relative_margin: optional; keep only chunks within (best distance + margin) (None = no relative cut).
    min_chunks:      the top chunks that are always kept, so a passed gate never yields an empty context.
    """
    k: int = 8
    max_distance: Optional[float] = None
    relative_margin: Optional[float] = None
    min_chunks: int = 1

    def __post_init__(self):
        if self.k < 1 or not 1 <= self.min_chunks <= self.k:
            raise ValueError("ContextPolicy needs k >= 1 and 1 <= min_chunks <= k")
        if (self.max_distance is not None and self.max_distance < 0) or (self.relative_margin is not None and self.relative_margin < 0):
            raise ValueError("ContextPolicy distances must be >= 0")

    def describe(self):
        parts = [f"top-{self.k}"]
        if self.max_distance is not None:
            parts.append(f"cap {self.max_distance:g}")
        if self.relative_margin is not None:
            parts.append(f"best+{self.relative_margin:g}")
        if self.min_chunks > 1:
            parts.append(f"min {self.min_chunks}")
        return ", ".join(parts)


def resolve_context_policy(policy=None):
    """Explicit ContextPolicy > environment variables > defaults."""
    if policy is not None:
        return policy
    base = ContextPolicy()
    k = _env_number("RAG_CONTEXT_K", int)
    min_chunks = _env_number("RAG_CONTEXT_MIN_CHUNKS", int)
    return ContextPolicy(k=base.k if k is None else k,
                         max_distance=_env_number("RAG_CONTEXT_MAX_DISTANCE", float),
                         relative_margin=_env_number("RAG_CONTEXT_MARGIN", float),
                         min_chunks=base.min_chunks if min_chunks is None else min_chunks)


def select_indices(distances, policy):
    """Positions (in rank order) of the chunks to keep. `distances` must be sorted closest-first."""
    if not distances:
        return []
    best, keep = distances[0], []
    for i, d in enumerate(distances[:policy.k]):
        within = ((policy.max_distance is None or d <= policy.max_distance)
                  and (policy.relative_margin is None or d <= best + policy.relative_margin))
        if i < policy.min_chunks or within:
            keep.append(i)
    return keep


# ---------------------------------------------------------------- evidence and answers
@dataclass
class Evidence:
    question: str
    hits: list                       # the selected context, closest first (empty when the gate refused)
    max_distance: float              # the answerability GATE distance
    context: ContextPolicy = None
    best_distance: float = None      # closest chunk overall (even if refused) - useful when tuning
    sufficient: bool = False         # did the gate pass?


@dataclass
class Answer:
    text: str
    grounded: bool                   # False = refusal
    sources: list = field(default_factory=list)      # citations built from the retrieved chunks, never from model text
    evidence: Evidence = None


def gather_evidence(store, question, max_distance=None, context=None, where=None):
    gate = resolve_max_distance(max_distance)
    policy = resolve_context_policy(context)
    ranked = retrieve(store, question, k=policy.k, where=where)
    best = ranked[0].distance if ranked else None
    passed = bool(ranked) and best <= gate
    hits = [ranked[i] for i in select_indices([h.distance for h in ranked], policy)] if passed else []
    return Evidence(question=question, hits=hits, max_distance=gate, context=policy, best_distance=best, sufficient=passed)


def build_prompt(evidence):
    context = "\n\n".join(f"{i}. {h.citation}\n{h.text}" for i, h in enumerate(evidence.hits, 1))
    return PROMPT.format(sentinel=INSUFFICIENT, context=context, question=evidence.question)


def answer_question(store, question, generate, max_distance=None, context=None):
    evidence = gather_evidence(store, question, max_distance=max_distance, context=context)
    if not evidence.sufficient:
        return Answer(text=REFUSAL, grounded=False, evidence=evidence)           # model never called
    reply = (generate(build_prompt(evidence)) or "").strip()
    if not reply or INSUFFICIENT in reply:
        return Answer(text=REFUSAL, grounded=False, evidence=evidence)
    sources = list(dict.fromkeys(h.citation for h in evidence.hits))
    return Answer(text=reply, grounded=True, sources=sources, evidence=evidence)
