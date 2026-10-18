"""Offline demo engine: EXTRACTIVE answers from approved documents, with zero hosted calls and no generative model.

It reuses the production pieces - the answerability gate, context selection, chunk ids, `assemble()` and citations - and replaces
only the model: for each part of the question it picks the retrieved sentence closest in meaning (local FastEmbed vectors) and
quotes it verbatim. Because every sentence is copied from a retrieved chunk, quotes and citations are verified by construction.

What it is NOT: it cannot reason, combine facts, or paraphrase. It returns the best matching sentence(s), or says the evidence is
insufficient. It is a clearly labelled demo mode, not a substitute for the hosted pipeline in rag/verify.py.

MIN_SIM is a provisional similarity floor for a sentence to count as an answer; like the gate distance it depends on the embedding
model and the corpus, and was set from a handful of manual checks, not tuned on an evaluation set.
"""
import os
import re

import numpy as np

from rag.answer import REFUSAL, gather_evidence
from rag.verify import FactResult, VerifiedAnswer, assemble

ENGINE = "offline-extractive"
MIN_SIM = 0.62                           # provisional; override with HOOMI_OFFLINE_MIN_SIM
MAX_PARTS = 4
RUNNER_UP_MARGIN = 0.05
MIN_SENTENCE_CHARS = 25
_QUESTION_WORDS = r"(?:how|what|which|who|whom|whose|when|where|why|does|do|did|is|are|can|could|will|should)"


def min_sim(value=None):
    if value is not None:
        return float(value)
    raw = os.environ.get("HOOMI_OFFLINE_MIN_SIM", "").strip()
    try:
        return float(raw) if raw else MIN_SIM
    except ValueError:
        raise ValueError("HOOMI_OFFLINE_MIN_SIM must be a number") from None


def split_question(question, max_parts=MAX_PARTS):
    """Break a multi-part question into its parts: at '?', ';', 'as well as', or ', and' / ' and' followed by a question word."""
    q = " ".join(question.split())
    pieces = []
    for chunk in re.split(r"\?+|;", q):
        chunk = chunk.strip(" ,.")
        if not chunk:
            continue
        pieces += [p.strip(" ,.") for p in re.split(rf",?\s+and\s+(?={_QUESTION_WORDS}\b)|\s+as well as\s+(?={_QUESTION_WORDS}\b)", chunk, flags=re.I) if p and p.strip(" ,.")]
    pieces = [p for p in pieces if len(p.split()) >= 2] or [q.strip(" ?")]
    return pieces[:max_parts]


def sentences(text):
    """Candidate answer sentences from a chunk: headings dropped, bullets unwrapped, split at sentence ends."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        for s in re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", line):
            s = s.strip()
            if len(s) >= MIN_SENTENCE_CHARS and s in text:
                out.append(s)
    return out


def _unit(vectors):
    v = np.asarray(vectors, dtype=float)
    return v / np.maximum(np.linalg.norm(v, axis=1, keepdims=True), 1e-12)


def answer_offline(store, question, max_distance=None, context=None, where=None, floor=None):
    """Gate, then one best sentence per question part. Returns a VerifiedAnswer with engine='offline-extractive' and no model calls."""
    floor = min_sim(floor)
    evidence = gather_evidence(store, question, max_distance=max_distance, context=context, where=where)
    if not evidence.sufficient:
        return VerifiedAnswer("refused", REFUSAL, reason="gate", evidence=evidence, engine=ENGINE)
    cands = list(dict.fromkeys((h.chunk_id, s, f"{h.section}: {s}") for h in evidence.hits for s in sentences(h.text)))
    parts = split_question(question)
    if not cands:
        facts = [FactResult(p, False, reason="no_sentences_in_context") for p in parts]
    else:
        vec = store.embeddings
        sent_v = _unit(vec.embed_documents([ctx for _, _, ctx in cands]))        # each sentence is embedded with its section heading
        facts = []
        for part in parts:
            sims = sent_v @ _unit([vec.embed_query(part)])[0]
            order = [int(i) for i in np.argsort(-sims)]
            best = order[0]
            if sims[best] >= floor:
                # the best sentence, plus the runner-up when it is nearly as good: a little more context, still verbatim
                keep = [best] + [i for i in order[1:2] if sims[i] >= floor and sims[i] >= sims[best] - RUNNER_UP_MARGIN]
                facts.append(FactResult(part, True, claim=" ".join(cands[i][1] for i in keep), chunk_ids=list(dict.fromkeys(cands[i][0] for i in keep)),
                                        quote=cands[best][1], score=float(sims[best]), quotes=[(cands[i][0], cands[i][1]) for i in keep]))
            else:
                facts.append(FactResult(part, False, reason=f"best sentence similarity {sims[best]:.2f} is below {floor:.2f}", score=float(sims[best])))
    status, text, sources, ids, reason = assemble(facts, evidence.hits)
    return VerifiedAnswer(status, text, facts, sources, ids, reason, evidence=evidence, model_calls=0, engine=ENGINE)
