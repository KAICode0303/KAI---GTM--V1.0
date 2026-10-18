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
from rag import ingest, retriever

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
        assert c.metadata["source"].endswith(".md") and c.metadata["page"] == 1 and c.metadata["title"]
        assert len(c.page_content) <= 450


# ---------------------------------------------------------------- retrieval with citations
@pytest.mark.parametrize("question, expected_source", [
    ("Which industries and buyers are the ideal customer?", "02_icp.md"),
    ("How did Northwind Health reduce reporting time?", "03_case_study.md"),
    ("What delivery modalities does Kai offer for engagements?", "01_capabilities.md"),
])
def test_retrieval_finds_the_right_document_with_citation(store, question, expected_source):
    hits = retriever.retrieve(store, question, k=3)
    assert hits and hits[0].source == expected_source
    assert hits[0].citation == f"[{expected_source}, p.1]"
    assert all(h.text for h in hits) and hits == sorted(hits, key=lambda h: h.distance)


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
