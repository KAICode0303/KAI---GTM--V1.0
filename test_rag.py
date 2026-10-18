"""Offline tests for the RAG foundation. No network, no model download, no LLM.

A tiny word-hashing embedding stands in for FastEmbed: deterministic, and texts that share words end up close,
which is enough to check chunking, metadata, persistence and citations.
"""
import hashlib
import math
import re

import pytest
from langchain_core.embeddings import Embeddings

from rag import embeddings as emb
from rag import answer, ingest, retriever
from rag.answer import ContextPolicy

DIM = 256


class HashingEmbeddings(Embeddings):
    def _vec(self, text):
        v = [0.0] * DIM
        for w in re.findall(r"[a-z]+", text.lower()):
            if len(w) > 3:
                v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]

    def embed_documents(self, texts):
        return [self._vec(t) for t in texts]

    def embed_query(self, text):
        return self._vec(text)


@pytest.fixture(scope="module")
def chunks():
    return ingest.chunk_documents(ingest.load_documents())


@pytest.fixture()
def store(tmp_path, chunks):
    s = retriever.get_store(HashingEmbeddings(), persist_dir=tmp_path / "chroma")
    retriever.build_index(s, chunks)
    return s


# ---------------------------------------------------------------- documents and chunks
def test_corpus_has_three_sanitized_documents():
    docs = ingest.load_documents()
    assert len(docs) == 3
    assert {d.metadata["doc_type"] for d in docs} == {"capability", "icp", "case_study"}
    assert all(d.metadata["sanitized"] is True for d in docs)


def test_unsanitized_document_is_refused(tmp_path):
    (tmp_path / "x.md").write_text("---\ntitle: X\n---\nsome text", encoding="utf-8")
    with pytest.raises(ValueError, match="sanitized"):
        ingest.load_documents(tmp_path)


def test_chunks_keep_source_metadata_and_unique_ids(chunks):
    assert len(chunks) > 3                                           # documents really were split
    assert len({c.metadata["chunk_id"] for c in chunks}) == len(chunks)
    for c in chunks:
        assert c.metadata["source"].endswith(".md") and c.metadata["title"] and c.metadata["section"]
        assert "page" not in c.metadata                       # Markdown has no real page: never invent one
        assert len(c.page_content) <= 450


def test_chunks_follow_headings(chunks):
    sections = {(c.metadata["source"], c.metadata["section"]) for c in chunks}
    assert ("02_icp.md", "Best-fit customers") in sections and ("03_case_study.md", "Results after six months") in sections
    best_fit = next(c for c in chunks if c.metadata["section"] == "Best-fit customers")
    assert "Chief Data Officer" in best_fit.page_content and "Poor-fit" not in best_fit.page_content


# ---------------------------------------------------------------- retrieval with citations
@pytest.mark.parametrize("question, expected_source", [
    ("Which industries and buyers are the ideal customer?", "02_icp.md"),
    ("How did Northwind Health reduce reporting time?", "03_case_study.md"),
    ("What delivery modalities does Kai offer for engagements?", "01_capabilities.md"),
])
def test_retrieval_finds_the_right_document_with_citation(store, question, expected_source):
    hits = retriever.retrieve(store, question, k=3)
    assert hits and hits[0].source == expected_source
    assert hits[0].citation == f"[{expected_source} › {hits[0].section}]" and hits[0].page is None
    assert all(h.text for h in hits) and hits == sorted(hits, key=lambda h: h.distance)


def test_citation_formats():
    assert retriever.format_citation({"source": "a.md", "section": "Pricing"}) == "[a.md › Pricing]"
    assert retriever.format_citation({"source": "deck.pdf", "section": "Results", "page": 7}) == "[deck.pdf › Results, p.7]"
    assert retriever.format_citation({"source": "deck.pdf", "page": 7}) == "[deck.pdf, p.7]"       # real PDF page kept
    assert retriever.format_citation({"source": "a.md"}) == "[a.md]"


def test_max_distance_filters_hits(store):
    q = "Which industries and buyers are the ideal customer?"
    everything = retriever.retrieve(store, q, k=4)
    cutoff = (everything[0].distance + everything[-1].distance) / 2
    kept = retriever.retrieve(store, q, k=4, max_distance=cutoff)
    assert 0 < len(kept) < len(everything) and all(h.distance <= cutoff for h in kept)
    assert retriever.retrieve(store, q, k=4, max_distance=0.0) == []


def test_index_is_persistent_and_rebuild_has_no_duplicates(tmp_path, chunks):
    path = tmp_path / "chroma"
    s1 = retriever.get_store(HashingEmbeddings(), persist_dir=path)
    retriever.build_index(s1, chunks)
    retriever.build_index(s1, chunks)                                # run twice
    assert s1._collection.count() == len(chunks)
    del s1
    s2 = retriever.get_store(HashingEmbeddings(), persist_dir=path)  # reopen from disk
    assert s2._collection.count() == len(chunks)
    assert retriever.retrieve(s2, "Northwind Health reporting", k=1)[0].source == "03_case_study.md"


# ---------------------------------------------------------------- privacy guards
def test_fastembed_wrapper_is_lazy_and_blocks_downloads_by_default(tmp_path):
    e = emb.FastEmbedEmbeddings(cache_dir=tmp_path / "models")
    assert e._model is None and e.allow_download is False and not (tmp_path / "models").exists()
    assert emb.DEFAULT_MODEL == "BAAI/bge-small-en-v1.5"


def test_chroma_telemetry_is_disabled(store):
    assert store._client.get_settings().anonymized_telemetry is False


# ---------------------------------------------------------------- threshold configuration
def test_threshold_precedence(monkeypatch):
    monkeypatch.delenv("RAG_MAX_DISTANCE", raising=False)
    assert answer.resolve_max_distance() == answer.DEFAULT_MAX_DISTANCE
    monkeypatch.setenv("RAG_MAX_DISTANCE", "0.55")
    assert answer.resolve_max_distance() == 0.55                  # env beats default
    assert answer.resolve_max_distance(0.9) == 0.9                # argument beats env
    monkeypatch.setenv("RAG_MAX_DISTANCE", "abc")
    with pytest.raises(ValueError, match="RAG_MAX_DISTANCE"):
        answer.resolve_max_distance()


# ---------------------------------------------------------------- grounded answers and refusal
GOOD_Q = "Who is the buyer, a Chief Data Officer, among the best-fit customers?"      # shares words with one chunk
UNRELATED_Q = "Zebra volcano submarine banana?"                    # shares no words with the corpus


def _never_called(prompt):
    raise AssertionError("the model must not be called without evidence")


def test_answer_is_grounded_with_sources_from_retrieval(store, monkeypatch):
    monkeypatch.delenv("RAG_MAX_DISTANCE", raising=False)
    seen = {}

    def fake_llm(prompt):
        seen["prompt"] = prompt
        return "Healthcare, financial services and retail [02_icp.md › Best-fit customers]."

    out = answer.answer_question(store, GOOD_Q, fake_llm, max_distance=1.2)
    assert out.grounded and out.text.startswith("Healthcare")
    assert out.sources and all(s.startswith("[") and "›" in s for s in out.sources)
    assert out.sources == list(dict.fromkeys(h.citation for h in out.evidence.hits))   # built from chunks, not model text
    assert out.evidence.hits[0].citation in seen["prompt"]                              # context carries citations
    assert answer.INSUFFICIENT in seen["prompt"] and GOOD_Q in seen["prompt"]


def test_no_evidence_refuses_without_calling_the_model(store):
    out = answer.answer_question(store, GOOD_Q, _never_called, max_distance=0.0)       # nothing can be that close
    assert not out.grounded and out.text == answer.REFUSAL and out.sources == []
    assert not out.evidence.sufficient and out.evidence.best_distance > 0


def test_unrelated_question_is_refused_at_a_sensible_threshold(store):
    # cutoff chosen for the toy hashing embedding (good ~1.1, unrelated ~1.41); the real model has its own scale
    good = answer.gather_evidence(store, GOOD_Q, max_distance=1.25)
    bad = answer.gather_evidence(store, UNRELATED_Q, max_distance=1.25)
    assert good.sufficient and not bad.sufficient and bad.best_distance > good.best_distance
    assert not answer.answer_question(store, UNRELATED_Q, _never_called, max_distance=1.25).grounded


def test_model_saying_insufficient_becomes_a_refusal(store):
    out = answer.answer_question(store, GOOD_Q, lambda p: answer.INSUFFICIENT, max_distance=1.2)
    assert not out.grounded and out.text == answer.REFUSAL and out.sources == []


def test_empty_model_reply_becomes_a_refusal(store):
    assert not answer.answer_question(store, GOOD_Q, lambda p: "  ", max_distance=1.2).grounded


def test_threshold_is_configurable_through_environment(store, monkeypatch):
    monkeypatch.setenv("RAG_MAX_DISTANCE", "0.0")
    assert not answer.answer_question(store, GOOD_Q, _never_called).grounded
    monkeypatch.setenv("RAG_MAX_DISTANCE", "1.2")
    assert answer.answer_question(store, GOOD_Q, lambda p: "ok [x]").grounded


# ---------------------------------------------------------------- contextual embedding text
def test_embedding_text_adds_title_and_section_but_stored_text_is_original(tmp_path, chunks):
    lessons = next(c for c in chunks if c.metadata["section"] == "Lessons")
    text = retriever.embedding_text(lessons)
    assert text.startswith("Case Study - Northwind Health (synthetic) › Lessons") and text.endswith(lessons.page_content)
    store = retriever.get_store(HashingEmbeddings(), persist_dir=tmp_path / "c")
    retriever.build_index(store, chunks)
    got = store._collection.get(ids=["03_case_study.md#4"], include=["documents", "metadatas"])
    assert got["documents"][0] == lessons.page_content                      # original text, no header, is what is stored
    md = got["metadatas"][0]
    assert md["source"] == "03_case_study.md" and md["section"] == "Lessons" and "page" not in md
    assert md["embedded_with"] == "title+section"
    hit = retriever.retrieve(store, "Northwind Health analysts trained to maintain pipelines", k=1)[0]
    assert hit.citation == "[03_case_study.md › Lessons]" and "Case Study" not in hit.text


def test_contextual_embedding_pulls_context_free_chunks_closer(tmp_path, chunks):
    q = "Northwind Health analysts trained to maintain pipelines"          # the Lessons chunk never says 'Northwind'
    dist = {}
    for mode in (False, True):
        store = retriever.get_store(HashingEmbeddings(), persist_dir=tmp_path / f"c{mode}")
        retriever.build_index(store, chunks, contextual=mode)
        dist[mode] = next(h for h in retriever.retrieve(store, q, k=15) if h.section == "Lessons").distance
        md = store._collection.get(limit=1, include=["metadatas"])["metadatas"][0]
        assert md["embedded_with"] == ("title+section" if mode else "text")
    assert dist[True] < dist[False]


# ---------------------------------------------------------------- context selection is separate from the gate
def test_select_indices_rules():
    d = [0.5, 0.6, 0.9, 1.0]
    assert answer.select_indices(d, ContextPolicy(k=3)) == [0, 1, 2]                          # rank-based
    assert answer.select_indices(d, ContextPolicy(k=4, max_distance=0.7)) == [0, 1]            # absolute cap
    assert answer.select_indices(d, ContextPolicy(k=4, relative_margin=0.15)) == [0, 1]        # within best + 0.15
    assert answer.select_indices([0.9, 1.5], ContextPolicy(k=2, max_distance=0.7)) == [0]      # min_chunks keeps the best
    assert answer.select_indices(d, ContextPolicy(k=3, max_distance=0.0, min_chunks=2)) == [0, 1]
    assert answer.select_indices([], ContextPolicy()) == []


def test_context_policy_validation_and_description():
    for bad in (dict(k=0), dict(k=2, min_chunks=3), dict(max_distance=-1), dict(relative_margin=-0.1)):
        with pytest.raises(ValueError):
            ContextPolicy(**bad)
    assert ContextPolicy(k=6, relative_margin=0.25).describe() == "top-6, best+0.25"


def test_context_policy_environment(monkeypatch):
    for v in ("RAG_CONTEXT_K", "RAG_CONTEXT_MAX_DISTANCE", "RAG_CONTEXT_MARGIN", "RAG_CONTEXT_MIN_CHUNKS"):
        monkeypatch.delenv(v, raising=False)
    assert answer.resolve_context_policy() == ContextPolicy()
    monkeypatch.setenv("RAG_CONTEXT_K", "3")
    monkeypatch.setenv("RAG_CONTEXT_MARGIN", "0.2")
    assert answer.resolve_context_policy() == ContextPolicy(k=3, relative_margin=0.2)
    explicit = ContextPolicy(k=5)
    assert answer.resolve_context_policy(explicit) is explicit                                # argument beats environment
    monkeypatch.setenv("RAG_CONTEXT_K", "many")
    with pytest.raises(ValueError, match="RAG_CONTEXT_K"):
        answer.resolve_context_policy()


def test_context_chunks_are_not_filtered_by_the_gate_distance(store):
    best = answer.gather_evidence(store, GOOD_Q, max_distance=9.0, context=ContextPolicy(k=1)).best_distance
    gate = best + 0.01                                         # only the closest chunk is within the gate distance
    ev = answer.gather_evidence(store, GOOD_Q, max_distance=gate, context=ContextPolicy(k=3))
    assert ev.sufficient and len(ev.hits) == 3 and ev.hits[-1].distance > gate     # supporting chunks lie beyond the gate
    assert ev.max_distance == gate and ev.context == ContextPolicy(k=3)


def test_failed_gate_gives_no_context_whatever_the_policy(store):
    ev = answer.gather_evidence(store, GOOD_Q, max_distance=0.0, context=ContextPolicy(k=10))
    assert not ev.sufficient and ev.hits == [] and ev.best_distance > 0


def test_context_policy_reaches_the_model_prompt(store):
    seen = {}
    out = answer.answer_question(store, GOOD_Q, lambda p: seen.setdefault("p", p) and "ok [x]", max_distance=9.0,
                                 context=ContextPolicy(k=2))
    assert out.grounded and len(out.evidence.hits) == 2 and seen["p"].count("\n\n2. [") == 1 and "3. [" not in seen["p"]
