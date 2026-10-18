"""Offline tests for the Hoomi app index (rag/app_index.py) and the extractive offline engine (rag/offline.py).
The toy hashing embedding stands in for FastEmbed, so these tests check mechanics and guarantees (verified quotes, scoping, incremental
refresh, no model calls), not semantic quality."""
import shutil
from pathlib import Path

import pytest

from gtm.store import GTMStore
from rag import app_index, offline
from rag.answer import ContextPolicy, REFUSAL
from rag.retriever import retrieve
from test_rag import HashingEmbeddings

ROOT = Path(__file__).resolve().parent
ALL = ContextPolicy(k=12)


@pytest.fixture()
def gtm(tmp_path):
    return GTMStore(tmp_path / "gtm.db")


@pytest.fixture()
def corpus(tmp_path):
    dst = tmp_path / "corpus"
    shutil.copytree(app_index.APP_CORPUS_DIR, dst)
    return dst


@pytest.fixture()
def index(tmp_path, gtm, corpus):
    store, info = app_index.ensure_index(HashingEmbeddings(), gtm, persist_dir=tmp_path / "idx", corpus_dir=corpus)
    return store, info, gtm, corpus, tmp_path / "idx"


# ---------------------------------------------------------------- the documents
def test_app_corpus_is_sanitized_and_aligned_with_the_demo_data():
    docs = app_index.build_documents(None)
    assert len(docs) == 5 and all(d.metadata["sanitized"] is True for d in docs)
    text = " ".join(d.page_content for d in docs)
    from gtm import schema
    for name in schema.CAPABILITIES + schema.MODALITIES + schema.SEGMENTS:
        assert name.lower().replace("-", " ") in text.lower().replace("-", " "), name
    assert "fictional" in text and "@" not in text                                     # synthetic, with no contact details


def test_unsanitized_corpus_file_is_refused(corpus, gtm):
    (corpus / "99_secret.md").write_text("---\ntitle: Real client list\n---\nconfidential", encoding="utf-8")
    with pytest.raises(ValueError, match="sanitized"):
        app_index.build_documents(gtm, corpus)


def test_kyc_documents_are_one_per_account_written_as_quotable_sentences(gtm):
    docs = app_index.kyc_documents(gtm)
    assert len(docs) == 64 and all(d.metadata["doc_type"] == "kyc" and d.metadata["sanitized"] for d in docs)
    d = next(x for x in docs if x.metadata["account_id"] == "ACC-101")
    assert d.metadata["source"] == "kyc_ACC-101.md" and d.page_content.startswith("# KYC profile: Deepcurrent Labs (ACC-101)")
    assert "Requested capabilities for Deepcurrent Labs: Multimodal Data Services." in d.page_content
    assert "## Requested capabilities" in d.page_content and "Deepcurrent Labs is in the AI Labs segment" in d.page_content
    sparse = min(docs, key=lambda x: len(x.page_content))
    assert "None" not in sparse.page_content and ": ." not in sparse.page_content        # empty fields are skipped, not printed


# ---------------------------------------------------------------- incremental index
def test_first_build_then_no_change_then_one_kyc_edit(index):
    store, info, gtm, corpus, idx = index
    assert info["updated"] == 69 and info["chunks"] > 300 and info["rebuilt"]
    before = store._collection.get(include=[])["ids"]
    store2, info2 = app_index.ensure_index(HashingEmbeddings(), gtm, persist_dir=idx, corpus_dir=corpus)
    assert info2["updated"] == 0 and not info2["rebuilt"] and sorted(store2._collection.get(include=[])["ids"]) == sorted(before)
    data, _ = gtm.kyc_profile("ACC-103")
    gtm.save_kyc("ACC-103", {**data, "pain_points": "Urgent need for faster safety review labeling turnaround."})
    store3, info3 = app_index.ensure_index(HashingEmbeddings(), gtm, persist_dir=idx, corpus_dir=corpus)
    assert info3["updated"] == 1 and info3["removed"] == 0
    got = store3._collection.get(where={"source": "kyc_ACC-103.md"}, include=["documents"])["documents"]
    assert any("faster safety review labeling turnaround" in d for d in got)
    assert not any(data["pain_points"] and data["pain_points"] in d for d in got if data["pain_points"] != "Urgent need for faster safety review labeling turnaround.")
    assert store3._collection.count() >= len(before) - 8                                    # nothing else was disturbed


def test_removed_documents_leave_the_index(index):
    store, info, gtm, corpus, idx = index
    (corpus / "05_case_studies.md").unlink()
    store2, info2 = app_index.ensure_index(HashingEmbeddings(), gtm, persist_dir=idx, corpus_dir=corpus)
    assert info2["removed"] == 1 and info2["documents"] == 68
    assert store2._collection.get(where={"source": "05_case_studies.md"}, include=[])["ids"] == []
    assert store2._collection.get(where={"source": "01_service_catalog.md"}, include=[])["ids"]


def test_a_different_embedding_model_rebuilds_everything(index):
    store, info, gtm, corpus, idx = index

    class Other(HashingEmbeddings):
        model_name = "some-other-model"

    _, info2 = app_index.ensure_index(Other(), gtm, persist_dir=idx, corpus_dir=corpus)
    assert info2["updated"] == info["updated"]                                              # params changed -> nothing reused


def test_the_app_index_is_separate_from_the_evaluation_index():
    assert app_index.APP_INDEX_DIR.name == "app_chroma" and app_index.APP_INDEX_DIR != (ROOT / ".rag_index" / "chroma")
    assert app_index.APP_CORPUS_DIR == ROOT / "rag_corpus" / "gtm"


# ---------------------------------------------------------------- scoping: KYC only for the account the question names
@pytest.mark.parametrize("question", ["What does Deepcurrent Labs request?", "what does deepcurrent labs, inc. need", "Tell me about ACC-101",
                                      "KYC for DEEPCURRENT LABS please"])
def test_named_account_is_detected_by_name_or_id(gtm, question):
    assert app_index.account_in_question(question, gtm) == "ACC-101"


def test_no_account_means_general_documents_only(gtm):
    assert app_index.account_in_question("What services do we offer?", gtm) is None
    flt, aid = app_index.scope_filter("What services do we offer?", gtm)
    assert aid is None and flt == {"doc_type": {"$ne": "kyc"}}
    flt, aid = app_index.scope_filter("What does Deepcurrent Labs request?", gtm)
    assert aid == "ACC-101" and flt == {"$or": [{"account_id": "ACC-101"}, {"doc_type": {"$ne": "kyc"}}]}


def test_the_longest_matching_account_name_wins(tmp_path):
    g = GTMStore(tmp_path / "g.db", seed=False)
    g.add_account({"account_name": "Atlas"})
    long_id = g.add_account({"account_name": "Atlas Robotics"})
    assert app_index.account_in_question("What does Atlas Robotics need?", g) == long_id


def test_retrieval_respects_the_scope(index):
    store, _, gtm, _, _ = index
    general, _ = app_index.scope_filter("Which capabilities are requested?", gtm)
    hits = retrieve(store, "requested capabilities for accounts", k=15, where=general)
    assert hits and all(h.doc_type != "kyc" for h in hits)                                  # 64 KYC profiles never flood a general question
    scoped, aid = app_index.scope_filter("What are the requested capabilities for Deepcurrent Labs?", gtm)
    kyc_hits = [h for h in retrieve(store, "requested capabilities Deepcurrent Labs", k=30, where=scoped) if h.doc_type == "kyc"]
    assert kyc_hits and {h.source for h in kyc_hits} == {"kyc_ACC-101.md"}                  # only that account's profile is searchable


# ---------------------------------------------------------------- the offline engine
@pytest.mark.parametrize("question, parts", [
    ("What is a managed service and when should we recommend it?", ["What is a managed service", "when should we recommend it"]),
    ("How long does a typical project take, and how many people work on it?", ["How long does a typical project take", "how many people work on it"]),
    ("Which case study shows RLHF results, and what was the improvement?", ["Which case study shows RLHF results", "what was the improvement"]),
    ("Who is the buyer? What signals matter?", ["Who is the buyer", "What signals matter"]),
    ("What are the fixed-scope project and the managed service?", ["What are the fixed-scope project and the managed service"]),   # 'and' not before a question word
    ("Compare Annotation and Labeling with RLHF", ["Compare Annotation and Labeling with RLHF"]),
    ("services", ["services"]),
])
def test_questions_are_split_only_at_real_part_boundaries(question, parts):
    assert offline.split_question(question) == parts


def test_split_is_capped():
    assert len(offline.split_question("What is a? What is b? What is c? What is d? What is e? What is f?")) == offline.MAX_PARTS


def test_sentences_skip_headings_and_unwrap_bullets():
    text = "# Title\n\n## Section\nShort.\nThis sentence is long enough to count. Another sentence is also long enough here.\n- A bullet line that is long enough to keep."
    assert offline.sentences(text) == ["This sentence is long enough to count.", "Another sentence is also long enough here.",
                                       "A bullet line that is long enough to keep."]


def test_answer_is_quoted_from_the_documents_with_verified_citations(index):
    store, _, gtm, _, _ = index
    q = "How long does a time-and-materials team engagement last and who directs the work?"
    ans = offline.answer_offline(store, q, max_distance=9, context=ALL, where={"doc_type": {"$ne": "kyc"}}, floor=0.2)
    assert ans.engine == "offline-extractive" and ans.model_calls == 0 and ans.status in ("answered", "partial")
    by_id = {h.chunk_id: h for h in ans.evidence.hits}
    assert ans.source_chunk_ids and ans.sources
    for f in ans.facts:
        if f.supported:
            assert f.quote and f.quote in by_id[f.chunk_ids[0]].text                          # the quote is verbatim from the cited chunk
            assert all(cid in by_id for cid in f.chunk_ids)
    for cid in ans.source_chunk_ids:
        assert by_id[cid].citation in ans.sources


def test_gate_failure_refuses_without_searching_sentences(index):
    store, _, _, _, _ = index
    ans = offline.answer_offline(store, "What services do we offer?", max_distance=0.0, context=ALL)
    assert ans.status == "refused" and ans.reason == "gate" and ans.text == REFUSAL and ans.sources == [] and ans.model_calls == 0


def test_similarity_floor_turns_weak_matches_into_unsupported_facts(index):
    store, _, _, _, _ = index
    q = "What is the managed service?"
    assert offline.answer_offline(store, q, max_distance=9, context=ALL, where={"doc_type": {"$ne": "kyc"}}, floor=0.2).status == "answered"
    strict = offline.answer_offline(store, q, max_distance=9, context=ALL, where={"doc_type": {"$ne": "kyc"}}, floor=0.999)
    assert strict.status == "refused" and strict.reason == "nothing_supported" and not strict.facts[0].supported
    assert "below 1.00" in strict.facts[0].reason or "below 0.999" in strict.facts[0].reason or "similarity" in strict.facts[0].reason


def test_a_multi_part_question_can_be_a_labelled_partial_answer(index, monkeypatch):
    store, _, _, _, _ = index
    q = "What is the managed service? and what is quantum teleportation chocolate?"
    monkeypatch.setattr(offline, "split_question", lambda question: ["What is the managed service", "xyzzy plugh frobnicate"])
    ans = offline.answer_offline(store, q, max_distance=9, context=ALL, where={"doc_type": {"$ne": "kyc"}}, floor=0.45)
    assert ans.status == "partial" and [f.supported for f in ans.facts] == [True, False]
    assert "Partial answer" in ans.text and "xyzzy plugh frobnicate" in ans.text


def test_shared_sentences_are_not_repeated_in_the_text(index, monkeypatch):
    store, _, _, _, _ = index
    monkeypatch.setattr(offline, "split_question", lambda question: ["managed service recurring program", "managed service recurring program owns delivery"])
    ans = offline.answer_offline(store, "x", max_distance=9, context=ALL, where={"doc_type": {"$ne": "kyc"}}, floor=0.1)
    sentences = [s for s in ans.text.split(". ") if s]
    assert len(sentences) == len(set(sentences))


def test_floor_can_be_set_through_the_environment(monkeypatch):
    monkeypatch.delenv("HOOMI_OFFLINE_MIN_SIM", raising=False)
    assert offline.min_sim() == offline.MIN_SIM and offline.min_sim(0.9) == 0.9
    monkeypatch.setenv("HOOMI_OFFLINE_MIN_SIM", "0.7")
    assert offline.min_sim() == 0.7
    monkeypatch.setenv("HOOMI_OFFLINE_MIN_SIM", "high")
    with pytest.raises(ValueError, match="HOOMI_OFFLINE_MIN_SIM"):
        offline.min_sim()


def test_the_offline_engine_cannot_reach_a_hosted_provider():
    source = (ROOT / "rag" / "offline.py").read_text() + (ROOT / "rag" / "app_index.py").read_text()
    for forbidden in ("providers", "LLMClient", "ChatFireworks", "fireworks", "requests", "httpx", "urllib"):
        assert forbidden not in source, forbidden
