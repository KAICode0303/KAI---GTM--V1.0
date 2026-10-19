"""Offline demo engine: EXTRACTIVE answers from approved documents, with zero hosted calls and no generative model.

It reuses the production pieces - the answerability gate, context selection, chunk ids, `assemble()` and citations - and replaces
only the model: for each part of the question it picks the retrieved sentence closest in meaning (local FastEmbed vectors) and
quotes it verbatim. Because every sentence is copied from a retrieved chunk, quotes and citations are verified by construction.

What it is NOT: it cannot reason, combine facts, or paraphrase. It returns the best matching sentence(s), or says the evidence is
insufficient. It is a clearly labelled demo mode, not a substitute for the hosted pipeline in rag/verify.py.

MIN_SIM is a provisional similarity floor for a sentence to count as an answer; like the gate distance it depends on the embedding
model and the corpus, and was set from a handful of manual checks, not tuned on an evaluation set.
"""
import math
import os
import re

import numpy as np

from rag.answer import REFUSAL, ContextPolicy, gather_evidence
from rag.verify import FactResult, VerifiedAnswer, assemble

ENGINE = "offline-extractive"
MIN_SIM = 0.62                           # provisional; override with HOOMI_OFFLINE_MIN_SIM
MAX_PARTS = 4
OFFLINE_CONTEXT_K = 6
RUNNER_UP_MARGIN = 0.05
MIN_SENTENCE_CHARS = 25
GAP_MIN_OVERLAP = 0.6                    # a 'not stated' sentence refuses only if it covers most of what the question asks about
LEX_WEIGHT = 0.25                        # weight of the keyword-overlap bonus added to a sentence's embedding similarity
_QUESTION_WORDS = r"(?:how|what|which|who|whom|whose|when|where|why|does|do|did|is|are|can|could|will|should)"
_BRAND = {"kai", "kais", "company", "companys", "companies"}      # present in nearly every passage, so they say nothing about relevance
_STOP = set("""a an and are as at be been being by can could describe did do does for from give had has have how i if in into is it its of on or our
please should show so summarise summarize tell that the their them there these this those to us was we were what when where which who whom whose why will with
would you your about between during each both any all some more most such than then also""".split())
_LIMITS = re.compile(r"\b(limitations?|caveats?|constraints?|boundar(?:y|ies)|shortcomings?|drawbacks?|weakness(?:es)?)\b", re.I)
# a sentence in which the documents themselves say something is NOT stated, reported, quantified or available
_GAP = re.compile(r"\b(?:no\b[^.]*?\b(?:is|are)\s+(?:stated|reported|provided|given|included|available)|does not (?:state|report|quantify|establish|claim|mention)|"
                  r"do not (?:establish|invent|provide|include)|not (?:stated|reported|provided|independently|recalculated)|is not (?:a|an|proof)|not (?:a )?(?:statement|claim)|"
                  r"are not independently|not validated|no [a-z-]+ (?:or|nor) )", re.I)


def min_sim(value=None):
    if value is not None:
        return float(value)
    raw = os.environ.get("HOOMI_OFFLINE_MIN_SIM", "").strip()
    try:
        return float(raw) if raw else MIN_SIM
    except ValueError:
        raise ValueError("HOOMI_OFFLINE_MIN_SIM must be a number") from None


def _stem(word):
    for suffix in ("ing", "ed", "es", "s", "ly"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[:-len(suffix)]
    return word


def focus_terms(text):
    """The words that carry a question's topic: lower-cased, stemmed, without stop words or the company's own name."""
    words = re.findall(r"[a-z0-9]+", text.lower().replace("'s", ""))
    return {_stem(w) for w in words if w not in _STOP and w not in _BRAND and len(w) > 1}


def strip_brand(text):
    """The question without the company's name: 'Kai's Company' appears in almost every passage and otherwise pulls a generic sentence up."""
    return " ".join(re.sub(r"\bkai(?:'s|s)?(?:\s+company(?:'s)?)?\b", " ", text, flags=re.I).split())


def _words(text):
    return {_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())}


_SYNONYMS = {"servic": ("capabilit", "offering", "support"), "offer": ("capabilit", "offering", "support", "cover"), "capabilit": ("servic", "support"),
             "buyer": ("persona", "decision"), "persona": ("buyer",), "customer": ("client", "organization", "compan")}


def _has(words, term):
    return any(w.startswith(t) or (t.startswith(w) and len(w) > 3) for w in words for t in (term, *_SYNONYMS.get(term, ())))


def term_weights(terms, texts):
    """Rarer terms count more: 'scope' (one section) says more than 'case study' (every case study)."""
    pools = [_words(t) for t in texts]
    n = max(len(pools), 1)
    return {t: math.log((n + 1) / (1 + sum(_has(w, t) for w in pools))) + 0.1 for t in terms}


def overlap(terms, text, weights=None):
    """Weighted fraction of `terms` that start a word in `text` (stem match)."""
    if not terms:
        return 0.0
    words, w = _words(text), weights or {}
    total = sum(w.get(t, 1.0) for t in terms)
    return sum(w.get(t, 1.0) for t in terms if _has(words, t)) / total


def _names_section(heading, focus):
    """True when EVERY content word of a section heading is in the question ('Scope' is named by 'what was the scope...'; a long generic heading is not)."""
    words = [w for w in re.findall(r"[a-z0-9]+", heading.lower()) if w not in _STOP]
    return bool(words) and all(any(_stem(w).startswith(t) or t.startswith(_stem(w)) for t in focus) for w in words)


_SPREAD = re.compile(r"\b(compare|comparison|compared|across|both|versus|vs|differ(?:s|ence|ences|ent)?)\b", re.I)
_QUANTITY = re.compile(r"\b(percent(?:age)?|how (?:much|many)|by what|price|pricing|cost|rate|revenue|uplift|improvement|improve[ds]?)\b", re.I)


def is_gap(sentence):
    return bool(_GAP.search(sentence))


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
    out = []
    for p in pieces:                                                     # "Describe the case study and its limitations" asks for two things
        m = re.match(r"^(?P<base>.+?),?\s+and\s+(?:its|their|the)\s+(?P<lim>limitations?|caveats?|constraints?)\s*$", p, re.I)
        out += [m["base"], f"{m['lim']} of {re.sub(r'^(describe|explain|summari[sz]e|tell me about)\s+', '', m['base'], flags=re.I)}"] if m else [p]
    return out[:max_parts]


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


def _documented_gap(evidence, parts, cand, score):
    """The best sentence is the documents' own statement that the thing asked for is not stated or reported. Refuse, and show that statement."""
    cid, sentence, _ = cand
    hit = next(h for h in evidence.hits if h.chunk_id == cid)
    text = (f"The approved documents say this is not available: \"{sentence}\" {hit.citation}. I won't guess a figure or detail they do not state.")
    facts = [FactResult(p, False, reason="documented_gap: the documents state this is not available", chunk_ids=[cid], quote=sentence, score=score) for p in parts]
    return VerifiedAnswer("refused", text, facts, [hit.citation], [cid], "documented_gap", evidence=evidence, model_calls=0, engine=ENGINE)


def answer_offline(store, question, max_distance=None, context=None, where=None, floor=None):
    """Gate, then one best sentence per question part. Returns a VerifiedAnswer with engine='offline-extractive' and no model calls."""
    floor = min_sim(floor)
    if context is None and not os.environ.get("RAG_CONTEXT_K", "").strip():
        context = ContextPolicy(k=OFFLINE_CONTEXT_K)                       # the extractive demo was tuned on six passages; the hosted model gets the wider default
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
        facts, used = [], set()
        for part in parts:
            focus, wants_limits = focus_terms(part), bool(_LIMITS.search(part))
            sims = sent_v @ _unit([vec.embed_query(strip_brand(part) or part)])[0]
            weights = term_weights(focus, [ctx for _, _, ctx in cands])
            lex = np.array([overlap(focus, ctx, weights) for _, _, ctx in cands])
            gap = np.array([is_gap(s_) for _, s_, _ in cands])
            head = np.array([0.2 * _names_section(ctx.split(":")[0], focus) for _, _, ctx in cands])               # the question names the section ("scope", "approach")
            score = sims + LEX_WEIGHT * lex + head + (0.12 * gap if wants_limits else 0.0)
            order = [int(i) for i in np.argsort(-score)]
            best = order[0]
            doc_of = lambda i: cands[i][0].split("#")[0]
            floor_ok = lambda i: sims[i] >= floor or (lex[i] >= 0.9 and sims[i] >= floor - 0.08)       # a sentence that contains all the question's topic words may sit a little below the floor
            if floor_ok(best) and (lex[best] > 0 or not focus):          # a sentence with none of the question's topic words is not an answer
                keep = [best] + [i for i in order[1:3] if floor_ok(i) and score[i] >= score[best] - RUNNER_UP_MARGIN and lex[i] > 0]
                if _SPREAD.search(part):                                      # a comparison needs each document's own best sentence, not three from one
                    seen_docs = {doc_of(i) for i in keep}
                    for i in order:
                        if doc_of(i) not in seen_docs and sims[i] >= floor and lex[i] > 0 and len(seen_docs) < 3:
                            keep.append(i)
                            seen_docs.add(doc_of(i))
                if wants_limits:                                              # a limitations question gets every limitation statement of that document
                    keep += [i for i in order if gap[i] and i not in keep and cands[i][0].split("#")[0] == cands[best][0].split("#")[0]][:3]
                asks_number = bool(_QUANTITY.search(part)) and lex[best] < GAP_MIN_OVERLAP
                said_absent = next((i for i in order if gap[i] and lex[i] > 0 and doc_of(i) == doc_of(best)), None) if asks_number else None
                if said_absent is not None and not gap[best]:                 # asks for a figure; the best document itself says no such figure is reported
                    return _documented_gap(evidence, parts, cands[said_absent], float(score[said_absent]))
                if gap[best] and not wants_limits and lex[best] >= GAP_MIN_OVERLAP:                            # the documents themselves say this is not stated: a cited refusal, not an answer
                    return _documented_gap(evidence, parts, cands[best], float(score[best]))
                fresh = [i for i in keep if cands[i][1] not in used] or keep[:1]   # a sentence already given for an earlier part is not repeated
                used.update(cands[i][1] for i in fresh)
                keep = fresh
                facts.append(FactResult(part, True, claim=" ".join(cands[i][1] for i in keep), chunk_ids=list(dict.fromkeys(cands[i][0] for i in keep)),
                                        quote=cands[best][1], score=float(sims[best]), quotes=[(cands[i][0], cands[i][1]) for i in keep]))
            else:
                why = (f"best sentence similarity {sims[best]:.2f} is below {floor:.2f}" if sims[best] < floor
                       else "no retrieved sentence mentions what the question asks about")
                facts.append(FactResult(part, False, reason=why, score=float(sims[best])))
    status, text, sources, ids, reason = assemble(facts, evidence.hits)
    return VerifiedAnswer(status, text, facts, sources, ids, reason, evidence=evidence, model_calls=0, engine=ENGINE)
