"""The seven-document Kai's Company knowledge pack: corpus hygiene, the refusal rules of the offline engine, and the evidence check.

Uses toy hashing embeddings, so it is fast and offline. The real-embedding evaluation is rag/pack_eval.py (see eval/pack_report.md).
"""
import re
from pathlib import Path

import pytest

from rag import app_index, offline, pack_eval, retriever
from rag.ingest import chunk_documents
from test_rag import HashingEmbeddings

CORPUS = Path(__file__).resolve().parent / "rag_corpus"
EXPECTED = ["01_capabilities.md", "02_icp_model_evaluation.md", "03_icp_multilingual_speech_audio.md", "04_icp_robotics.md",
            "05_case_study_model_evaluation.md", "06_case_study_physical_ai.md", "07_case_study_multilingual.md"]


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("RAG_MAX_DISTANCE", "9")
    monkeypatch.setenv("RAG_CONTEXT_K", "53")                       # toy embeddings do not rank: put every chunk in context so ids are deterministic
    s = retriever.get_store(HashingEmbeddings(), persist_dir=tmp_path / "idx")
    retriever.build_index(s, chunk_documents(app_index.build_documents(None)))
    return s


def test_active_corpus_is_exactly_the_seven_documents():
    assert sorted(p.name for p in CORPUS.iterdir()) == EXPECTED


def test_corpus_has_no_contact_details_urls_or_legacy_synthetic_content():
    text = "\n".join(p.read_text(encoding="utf-8") for p in CORPUS.glob("*.md"))
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+|https?://|www\.|\b\d{3}[-. ]\d{3}[-. ]\d{4}\b", text)
    for legacy in ("Northwind", "Deepcurrent", "fictional", "PROJECT_DOCUMENT", "demo data"):
        assert legacy not in text, legacy


def test_every_section_has_a_citation_ready_heading(store):
    got = store._collection.get(include=["metadatas"])["metadatas"]
    assert {m["source"] for m in got} == set(EXPECTED) and all(m["section"] for m in got)


@pytest.mark.parametrize("question,parts", [
    ("Describe the first-person activity data case study and its limitations.",
     ["Describe the first-person activity data case study", "limitations of the first-person activity data case study"]),
    ("What is the scope of the case study?", ["What is the scope of the case study"])])
def test_a_limitations_clause_becomes_its_own_part(question, parts):
    got = offline.split_question(question)
    assert [g.lower() for g in got] == [p.lower() for p in parts]


def test_brand_words_do_not_count_as_topic_words():
    assert offline.focus_terms("What is Kai's Company's hourly price?") == {"hour", "price"}
    assert offline.strip_brand("What are Kai's Company's core AI capabilities?") == "What are core AI capabilities?"


@pytest.mark.parametrize("sentence,gap", [
    ("No standard hourly rate, fixed delivery duration, guaranteed future revenue or five-year company forecast is stated in this knowledge base.", True),
    ("The source does not quantify model-performance gains.", True),
    ("The source engagement describes a large batch of evaluation tasks, with several independent reviews of each prompt.", False)])
def test_documents_own_not_stated_sentences_are_recognised(sentence, gap):
    assert offline.is_gap(sentence) is gap


def test_a_hallucinating_model_is_never_shown_to_the_user(store):
    """The mock invents '150 dollars per hour' and 'verifies' it with a quote that is in no passage: the evidence check must refuse."""
    for q in ("What is Kai's Company's hourly price?", "What was the scope of the LLM evaluation case study?"):
        out = pack_eval.answer_verified(store, q, pack_eval.hallucinating_mock, where={"doc_type": {"$ne": "kyc"}})
        assert out.status == "refused" and "150" not in out.text and out.sources == []


def test_a_faithful_model_gets_a_cited_answer_and_a_model_that_says_insufficient_is_refused(store):
    where = {"doc_type": {"$ne": "kyc"}}
    ok = pack_eval.answer_verified(store, "What was the scope of the LLM evaluation case study?", pack_eval.faithful_mock(["a large batch of evaluation tasks"]), where=where)
    assert ok.status == "answered" and "a large batch of evaluation tasks" in ok.text and ok.sources and all(s.startswith("[0") for s in ok.sources)
    no = pack_eval.answer_verified(store, "Who won the football world cup?", pack_eval.faithful_mock([]), where=where)
    assert no.status == "refused" and no.sources == []


def test_the_pack_evaluation_set_covers_all_three_kinds():
    import json
    qs = json.loads(pack_eval.QUESTIONS.read_text(encoding="utf-8"))
    kinds = {q["category"] for q in qs}
    assert kinds == {"direct", "cross-document", "unanswerable"} and len(qs) >= 18
    assert all(not q["sources"] for q in qs if q["category"] == "unanswerable")
    assert all(set(q["sources"]) <= set(EXPECTED) for q in qs)


_MODEL = Path(__file__).resolve().parent / ".rag_index" / "models"
needs_model = pytest.mark.skipif(not any(_MODEL.glob("models--*")), reason="the local FastEmbed model is not cached")


@needs_model
def test_with_real_local_embeddings_unanswerable_questions_are_refused_and_answerable_ones_cite_the_right_document(tmp_path, monkeypatch):
    from rag import embeddings as emb
    monkeypatch.delenv("RAG_MAX_DISTANCE", raising=False)
    s, _ = app_index.ensure_index(emb.FastEmbedEmbeddings(), None, persist_dir=tmp_path / "idx")
    where = {"doc_type": {"$ne": "kyc"}}
    for q in ("What is Kai's Company's hourly price?", "What will Kai's Company's revenue be in five years?", "Who won the football world cup?",
              "Which named customer bought these services?"):
        assert offline.answer_offline(s, q, where=where).status == "refused", q
    a = offline.answer_offline(s, "What was the scope of the LLM evaluation case study?", where=where)
    assert a.status == "answered" and "[05_case_study_model_evaluation.md › Scope]" in a.sources and "a large batch of evaluation tasks" in a.text
    gap = offline.answer_offline(s, "By what percentage did the LLM evaluation case study improve model accuracy?", where=where)
    assert gap.status == "refused" and gap.reason == "documented_gap" and "No numerical accuracy uplift" in gap.text


@pytest.mark.parametrize("question", ["Which buyer personas should we target at a speech AI company?", "Which segments should we target first?",
                                      "Who do we target in robotics?"])
def test_target_as_a_verb_is_a_document_question_not_a_metric(question):
    from gtm import numbers_qa
    assert numbers_qa.route(question) == "documents"


@pytest.mark.parametrize("question", ["Are we on track for our monthly target?", "How far are we from the revenue target?", "What is our target?"])
def test_target_as_a_metric_is_still_a_numbers_question(question):
    from gtm import numbers_qa
    assert numbers_qa.route(question) == "numbers"


def test_every_pack_evaluation_question_is_routed_to_the_documents_not_the_calculator():
    import json
    from gtm import numbers_qa
    for q in json.loads(pack_eval.QUESTIONS.read_text(encoding="utf-8")):
        assert numbers_qa.route(q["question"]) == "documents", q["question"]


# ---------------------------------------------------------------- two-part question through the verified (mock) Fireworks pipeline
import json

TWO_PART = "Which AI model evaluation services does Kai's Company offer, and what types of companies should we target?"
SVC = "Model evaluation and benchmarking; human evaluation and preference judgments; prompt/response evaluation; AI agent and computer-use-agent testing"
TGT = "Tier 1: generative AI/LLM developers, foundation model companies, AI agent companies, enterprise AI platforms"


def _ids(store):
    got = store._collection.get(include=["documents", "metadatas"])
    by = {}
    for cid, doc in zip(got["ids"], got["documents"]):
        by[cid] = doc
    find = lambda needle: next(c for c, d in by.items() if needle in d)
    return find("Model evaluation and benchmarking; human evaluation"), find("Tier 1: generative AI/LLM developers"), find("Customer problems and service mapping")


def _run(store, svc_quote, svc_ids, tgt_quote=TGT, tgt_ids=None, draft=None):
    c_svc, c_tgt, _ = _ids(store)
    draft = draft or f"{SVC}. {TGT}."
    gen = json.dumps({"requested_facts": ["AI model evaluation services offered", "types of companies to target"], "answer": draft})
    ver = json.dumps({"facts": [
        {"fact": "AI model evaluation services offered", "status": "supported", "claim": SVC + ".", "supporting_chunk_ids": svc_ids(c_svc), "evidence_quote": svc_quote},
        {"fact": "types of companies to target", "status": "supported", "claim": TGT + ".", "supporting_chunk_ids": [c_tgt] if tgt_ids is None else tgt_ids,
         "evidence_quote": tgt_quote}], "unaddressed_parts": []})
    replies = iter([gen, ver])
    return pack_eval.answer_verified(store, TWO_PART, lambda prompt: next(replies), where={"doc_type": {"$ne": "kyc"}})


def test_the_services_chunk_exists_and_is_citable(store):
    c_svc, _, _ = _ids(store)
    assert c_svc.startswith("01_capabilities.md#")


def test_two_part_question_is_fully_supported_with_a_correct_quote(store):
    out = _run(store, SVC, lambda c: [c])
    assert out.status == "answered" and [f.supported for f in out.facts] == [True, True]
    assert "[01_capabilities.md › AI model evaluation and human feedback]" in out.sources and any(s.startswith("[02_icp_model_evaluation.md") for s in out.sources)


def test_a_quote_cited_to_the_wrong_chunk_is_still_rejected(store):
    """Verification is not weakened: real text attributed to the wrong passage fails closed (the model must cite the passage that contains the quote)."""
    _, _, wrong = _ids(store)
    out = _run(store, SVC, lambda c: [wrong])
    assert not out.facts[0].supported and out.facts[0].reason == "quote_not_in_cited_chunk" and out.status == "partial"


@pytest.mark.parametrize("quote", ["## AI model evaluation and human feedback\n" + SVC, "**" + SVC + "**", SVC.replace("; human", ";   human"),
                                   "Model evaluation and benchmarking; human evaluation ... AI agent and computer-use-agent testing"])
def test_formatting_and_ellipsis_in_a_real_quote_do_not_fail_verification(store, quote):
    assert _run(store, quote, lambda c: [c]).facts[0].supported


@pytest.mark.parametrize("quote", ["Kai's Company offers LLM benchmarking at fixed prices", "AI agent and computer-use-agent testing ... Model evaluation and benchmarking",
                                   "Model evaluation and benchmarking ... guaranteed ten-fold return", "short quote"])
def test_invented_reordered_or_too_short_quotes_are_still_rejected(store, quote):
    out = _run(store, quote, lambda c: [c])
    assert not out.facts[0].supported and out.facts[0].reason in ("quote_not_in_cited_chunk", "quote_missing_or_too_short")
    assert out.status == "partial" and "AI model evaluation services offered" in out.text


@needs_model
def test_with_real_embeddings_the_services_passage_is_retrieved_for_the_two_part_question(tmp_path, monkeypatch):
    from rag import embeddings as emb
    from rag.answer import gather_evidence
    for n in ("RAG_MAX_DISTANCE", "RAG_CONTEXT_K"):
        monkeypatch.delenv(n, raising=False)
    s, _ = app_index.ensure_index(emb.FastEmbedEmbeddings(), None, persist_dir=tmp_path / "idx")
    ev = gather_evidence(s, TWO_PART, where={"doc_type": {"$ne": "kyc"}})
    ids = [h.chunk_id for h in ev.hits]
    assert any(h.source == "01_capabilities.md" and h.section == "AI model evaluation and human feedback" for h in ev.hits), ids
    assert any(h.source == "02_icp_model_evaluation.md" for h in ev.hits)
