"""Offline tests for the evidence-verified answer pipeline (rag/verify.py). The 'model' is a scripted mock: no hosted call,
no key, no network. Retrieval uses the toy hashing embedding and the real synthetic corpus, with every chunk placed in the
context so chunk ids are deterministic."""
import json

import pytest

from rag import ingest, retriever, verify as vf
from rag.answer import REFUSAL, ContextPolicy
from rag.providers import HostedCallNotApproved, LLMClient, ProviderConfig
from test_rag import LEGACY_CORPUS, HashingEmbeddings

Q = "Who is the buyer at our best-fit customers, and how long does a typical project take?"
ALL = ContextPolicy(k=15)
BUYER = "The buyer is usually a Chief Data Officer, VP of Analytics or Head of Operations"
WEEKS = "small squad of two engineers and one lead over eight to twelve weeks"
LESSON = "The client's own analysts were trained to maintain the pipelines"


@pytest.fixture(scope="module")
def chunks():
    return ingest.chunk_documents(ingest.load_documents(LEGACY_CORPUS))


@pytest.fixture()
def store(tmp_path, chunks):
    s = retriever.get_store(HashingEmbeddings(), persist_dir=tmp_path / "chroma")
    retriever.build_index(s, chunks)
    return s


@pytest.fixture(scope="module")
def ids(chunks):
    sec = {(c.metadata["source"], c.metadata["section"]): c.metadata["chunk_id"] for c in chunks}
    return {"icp": sec[("02_icp.md", "Best-fit customers")], "eng": sec[("01_capabilities.md", "Data Engineering")],
            "lessons": sec[("03_case_study.md", "Lessons")], "results": sec[("03_case_study.md", "Results after six months")]}


class ScriptedLLM:
    """Returns the scripted replies in order and records every prompt. A reply that is an Exception is raised instead."""

    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if len(self.prompts) > len(self.replies):
            raise AssertionError("more model calls than scripted")
        r = self.replies[len(self.prompts) - 1]
        if isinstance(r, Exception):
            raise r
        return r


def gen(facts, answer):
    return json.dumps({"requested_facts": facts, "answer": answer})


def entry(fact, status="supported", claim="", ids=(), quote=""):
    return {"fact": fact, "status": status, "claim": claim, "supporting_chunk_ids": list(ids), "evidence_quote": quote}


def ver(entries, unaddressed=()):
    return json.dumps({"facts": entries, "unaddressed_parts": list(unaddressed)})


def ask(store, llm, question=Q, **kw):
    return vf.answer_verified(store, question, llm, max_distance=kw.pop("max_distance", 9.0), context=kw.pop("context", ALL), **kw)


F1, F2 = "buyer persona", "typical project length"
DRAFT2 = f"{BUYER} [02_icp.md › Best-fit customers]. Projects usually take eight to twelve weeks. We also guarantee 100 percent ROI."
CLAIM1 = f"{BUYER} [02_icp.md › Best-fit customers]."
CLAIM2 = "Projects usually take eight to twelve weeks."


# ---------------------------------------------------------------- happy paths
def test_single_fact_is_answered_with_citations_from_the_verified_chunk(store, ids):
    llm = ScriptedLLM(gen([F1], f"{BUYER} [02_icp.md › Best-fit customers]."),
                      ver([entry(F1, claim=CLAIM1, ids=[ids["icp"]], quote="Chief Data Officer, VP of Analytics")]))
    out = ask(store, llm)
    assert out.status == "answered" and out.reason == "" and out.model_calls == 2 and len(llm.prompts) == 2
    assert out.text == BUYER + "."                                           # model-written bracket citation removed
    assert out.sources == ["[02_icp.md › Best-fit customers]"] and out.source_chunk_ids == [ids["icp"]]
    assert [f.supported for f in out.facts] == [True] and out.facts[0].quote == "Chief Data Officer, VP of Analytics"


def test_multi_part_question_all_facts_supported_cites_both_documents_in_fact_order(store, ids):
    llm = ScriptedLLM(gen([F1, F2], DRAFT2),
                      ver([entry(F1, claim=CLAIM1, ids=[ids["icp"]], quote="Chief Data Officer"),
                           entry(F2, claim=CLAIM2, ids=[ids["eng"]], quote="eight to twelve weeks")]))
    out = ask(store, llm)
    assert out.status == "answered"
    assert out.source_chunk_ids == [ids["icp"], ids["eng"]]
    assert out.sources == ["[02_icp.md › Best-fit customers]", "[01_capabilities.md › Data Engineering]"]
    assert out.text == f"{BUYER}. {CLAIM2}"
    assert "ROI" not in out.text                                              # unclaimed draft content never reaches the user


def test_partial_answer_is_labelled_and_lists_the_unsupported_fact(store, ids):
    llm = ScriptedLLM(gen([F1, F2], DRAFT2),
                      ver([entry(F1, claim=CLAIM1, ids=[ids["icp"]], quote="Chief Data Officer"),
                           entry(F2, "unsupported")]))
    out = ask(store, llm)
    assert out.status == "partial" and out.reason == ""
    assert out.text.startswith(vf.PARTIAL_HEADER) and f"{vf.UNSUPPORTED_LABEL} {F2}" in out.text and BUYER in out.text
    assert "eight to twelve" not in out.text and out.sources == ["[02_icp.md › Best-fit customers]"]
    assert [(f.fact, f.supported) for f in out.facts] == [(F1, True), (F2, False)]


def test_reply_wrapped_in_a_json_code_fence_is_accepted(store, ids):
    llm = ScriptedLLM("```json\n" + gen([F1], f"{BUYER}.") + "\n```",
                      "```\n" + ver([entry(F1, claim=f"{BUYER}.", ids=[ids["icp"]], quote="Chief Data Officer")]) + "\n```")
    assert ask(store, llm).status == "answered"


# ---------------------------------------------------------------- citations come only from verified chunks
def test_only_chunks_that_contain_the_verified_quote_are_cited(store, ids):
    llm = ScriptedLLM(gen([F1], f"{BUYER}."),
                      ver([entry(F1, claim=f"{BUYER}.", ids=[ids["lessons"], ids["icp"]], quote="Chief Data Officer")]))
    out = ask(store, llm)
    assert out.source_chunk_ids == [ids["icp"]] and out.sources == ["[02_icp.md › Best-fit customers]"]


def test_citations_written_by_the_model_are_ignored(store, ids):
    draft = f"{BUYER} [fake_report.md › Invented section] [02_icp.md#9]."
    llm = ScriptedLLM(gen([F1], draft), ver([entry(F1, claim=draft, ids=[ids["icp"]], quote="Chief Data Officer")]))
    out = ask(store, llm)
    assert out.text == BUYER + "." and "fake_report" not in out.text and "#9" not in out.text
    assert out.sources == ["[02_icp.md › Best-fit customers]"]


def test_quote_matching_tolerates_case_whitespace_and_curly_quotes(store, ids):
    llm = ScriptedLLM(gen([F1], f"{LESSON}."),
                      ver([entry(F1, claim=f"{LESSON}.", ids=[ids["lessons"]], quote="THE CLIENT’S  own\nanalysts were trained")]))
    assert ask(store, llm).status == "answered"


def test_unsupported_entries_never_contribute_citations(store, ids):
    llm = ScriptedLLM(gen([F1, F2], DRAFT2),
                      ver([entry(F1, claim=CLAIM1, ids=[ids["icp"]], quote="Chief Data Officer"),
                           entry(F2, "unsupported", claim=CLAIM2, ids=[ids["eng"]], quote="eight to twelve weeks")]))
    out = ask(store, llm)
    assert out.source_chunk_ids == [ids["icp"]] and out.facts[1].chunk_ids == []


# ---------------------------------------------------------------- well-formed but ungrounded "supported" verdicts are downgraded
@pytest.mark.parametrize("name, bad, reason", [
    ("unknown chunk id", dict(ids=["nope.md#0"], quote="Chief Data Officer"), "unknown_chunk_id"),
    ("one unknown among known", dict(ids=["ICP", "nope.md#0"], quote="Chief Data Officer"), "unknown_chunk_id"),
    ("no chunk cited", dict(ids=[], quote="Chief Data Officer"), "no_chunk_cited"),
    ("quote from a different chunk", dict(ids=["ICP"], quote="eight to twelve weeks"), "quote_not_in_cited_chunk"),
    ("invented quote", dict(ids=["ICP"], quote="guaranteed ten-fold return on investment"), "quote_not_in_cited_chunk"),
    ("quote too short", dict(ids=["ICP"], quote="Chief"), "quote_missing_or_too_short"),
    ("empty quote", dict(ids=["ICP"], quote=""), "quote_missing_or_too_short"),
    ("claim not in draft", dict(ids=["ICP"], quote="Chief Data Officer", claim="Buyers are always the CEO."), "claim_not_in_draft"),
    ("empty claim", dict(ids=["ICP"], quote="Chief Data Officer", claim=""), "claim_not_in_draft"),
    ("claim is only a citation", dict(ids=["ICP"], quote="Chief Data Officer", claim="[02_icp.md › Best-fit customers]",
                                       draft="[02_icp.md › Best-fit customers]"), "claim_empty_after_cleanup"),
])
def test_ungrounded_supported_verdict_fails_closed(store, ids, name, bad, reason):
    draft = bad.get("draft", f"{BUYER}.")
    cited = [ids["icp"] if i == "ICP" else i for i in bad["ids"]]
    llm = ScriptedLLM(gen([F1], draft), ver([entry(F1, claim=bad.get("claim", f"{BUYER}."), ids=cited, quote=bad["quote"])]))
    out = ask(store, llm)
    assert out.status == "refused" and out.reason == "nothing_supported" and out.text == REFUSAL
    assert out.facts[0].supported is False and out.facts[0].reason == reason and out.sources == []


def test_a_downgraded_fact_in_a_multi_part_answer_becomes_a_labelled_partial(store, ids):
    llm = ScriptedLLM(gen([F1, F2], DRAFT2),
                      ver([entry(F1, claim=CLAIM1, ids=[ids["icp"]], quote="Chief Data Officer"),
                           entry(F2, claim=CLAIM2, ids=[ids["eng"]], quote="projects take about a fortnight")]))
    out = ask(store, llm)
    assert out.status == "partial" and out.facts[1].reason == "quote_not_in_cited_chunk"
    assert f"{vf.UNSUPPORTED_LABEL} {F2}" in out.text and out.source_chunk_ids == [ids["icp"]]


def test_unaddressed_parts_are_reported_as_unsupported(store, ids):
    llm = ScriptedLLM(gen([F1], f"{BUYER}."),
                      ver([entry(F1, claim=f"{BUYER}.", ids=[ids["icp"]], quote="Chief Data Officer")],
                          unaddressed=["what the project costs", "  ", F1]))        # blank and already-covered parts are ignored
    out = ask(store, llm)
    assert out.status == "partial" and [f.fact for f in out.facts] == [F1, "what the project costs"]
    assert out.facts[1].reason == "unaddressed_part" and f"{vf.UNSUPPORTED_LABEL} what the project costs" in out.text


def test_everything_unsupported_is_a_plain_refusal(store):
    out = ask(store, ScriptedLLM(gen([F1], "Some draft."), ver([entry(F1, "unsupported")])))
    assert out.status == "refused" and out.reason == "nothing_supported" and out.text == REFUSAL and out.sources == []


# ---------------------------------------------------------------- malformed verifier output fails closed
GOOD = entry(F1, claim=f"{BUYER}.", ids=["X"], quote="Chief Data Officer")


@pytest.mark.parametrize("name, raw", [
    ("prose", "I believe the answer is supported."),
    ("empty reply", ""),
    ("json list", "[]"),
    ("json number", "3"),
    ("missing facts key", json.dumps({"unaddressed_parts": []})),
    ("missing unaddressed_parts", json.dumps({"facts": [GOOD]})),
    ("facts not a list", json.dumps({"facts": "supported", "unaddressed_parts": []})),
    ("unaddressed not strings", json.dumps({"facts": [GOOD], "unaddressed_parts": [1]})),
    ("no entries", ver([])),
    ("too many entries", ver([GOOD, dict(GOOD, fact="another")])),
    ("ambiguous status", ver([dict(GOOD, status="partially_supported")])),
    ("maybe", ver([dict(GOOD, status="maybe")])),
    ("wrong-case status", ver([dict(GOOD, status="Supported")])),
    ("status missing", ver([{k: v for k, v in GOOD.items() if k != "status"}])),
    ("claim missing", ver([{k: v for k, v in GOOD.items() if k != "claim"}])),
    ("quote missing", ver([{k: v for k, v in GOOD.items() if k != "evidence_quote"}])),
    ("ids a string", ver([dict(GOOD, supporting_chunk_ids="X")])),
    ("ids not strings", ver([dict(GOOD, supporting_chunk_ids=[1])])),
    ("entry not an object", ver(["supported"])),
    ("fact text does not match", ver([dict(GOOD, fact="something else entirely")])),
])
def test_malformed_verification_refuses_the_whole_answer(store, ids, name, raw):
    raw = raw.replace('"X"', json.dumps(ids["icp"]))
    out = ask(store, ScriptedLLM(gen([F1], f"{BUYER}."), raw))
    assert out.status == "refused" and out.reason == "verification_invalid" and out.text == REFUSAL
    assert out.sources == [] and out.facts == [] and out.model_calls == 2 and out.detail.startswith("verification:")


def test_duplicate_or_missing_entries_for_a_multi_part_question_refuse(store, ids):
    e1 = entry(F1, claim=CLAIM1, ids=[ids["icp"]], quote="Chief Data Officer")
    for entries in ([e1, e1], [e1]):                                              # duplicate fact, and a dropped fact
        out = ask(store, ScriptedLLM(gen([F1, F2], DRAFT2), ver(entries)))
        assert out.status == "refused" and out.reason == "verification_invalid"


# ---------------------------------------------------------------- generation stage
@pytest.mark.parametrize("name, raw", [
    ("prose", "The buyer is a CDO."),
    ("missing facts", json.dumps({"answer": "x"})),
    ("empty facts", gen([], "x")),
    ("too many facts", gen([f"fact {i}" for i in range(vf.MAX_FACTS + 1)], "x")),
    ("non-string fact", json.dumps({"requested_facts": [1], "answer": "x"})),
    ("blank fact", gen(["  "], "x")),
    ("duplicate facts", gen(["Same fact", "same  FACT"], "x")),
    ("missing answer", json.dumps({"requested_facts": ["a"]})),
    ("blank answer", gen(["a"], "   ")),
])
def test_invalid_generation_refuses_without_calling_the_verifier(store, name, raw):
    llm = ScriptedLLM(raw)
    out = ask(store, llm)
    assert out.status == "refused" and out.reason == "generation_invalid" and out.model_calls == 1 and len(llm.prompts) == 1


def test_model_side_insufficient_evidence_is_a_refusal(store):
    llm = ScriptedLLM(gen([F1], vf.INSUFFICIENT))
    out = ask(store, llm)
    assert out.status == "refused" and out.reason == "model_insufficient" and out.text == REFUSAL and len(llm.prompts) == 1


# ---------------------------------------------------------------- gate, provider errors, configuration
def test_failed_gate_makes_no_model_call(store):
    llm = ScriptedLLM()
    out = ask(store, llm, max_distance=0.0)
    assert out.status == "refused" and out.reason == "gate" and out.model_calls == 0 and llm.prompts == []
    assert not out.evidence.sufficient


@pytest.mark.parametrize("fail_on, calls", [(0, 1), (1, 2)])
def test_provider_failure_refuses_and_does_not_leak_the_message(store, ids, fail_on, calls):
    ok = [gen([F1], f"{BUYER}."), RuntimeError("boom api_key=SECRET123")]
    replies = [RuntimeError("boom api_key=SECRET123")] if fail_on == 0 else ok
    out = ask(store, ScriptedLLM(*replies))
    assert out.status == "refused" and out.reason == "llm_error" and out.model_calls == calls
    assert "RuntimeError" in out.detail and "SECRET123" not in out.detail and out.text == REFUSAL


def test_configuration_errors_are_raised_not_hidden(store):
    with pytest.raises(HostedCallNotApproved):
        ask(store, LLMClient(ProviderConfig(model="m", api_key="fake", allow_hosted_calls=False)))
    out = ask(store, ScriptedLLM(), max_distance=0.0)                              # a refusal at the gate never reaches the client
    assert out.reason == "gate"


def test_index_without_chunk_ids_is_refused(tmp_path):
    from langchain_core.documents import Document
    s = retriever.get_store(HashingEmbeddings(), persist_dir=tmp_path / "c")
    s.add_documents([Document(page_content="buyer chief data officer best fit customers",
                              metadata={"source": "x.md", "title": "T", "doc_type": "icp", "section": "S"})], ids=["a"])
    llm = ScriptedLLM()
    out = ask(s, llm, question="chief data officer buyer customers")
    assert out.reason == "index_missing_chunk_ids" and llm.prompts == []


# ---------------------------------------------------------------- prompts
def test_prompts_carry_chunk_ids_facts_and_the_draft(store, ids):
    llm = ScriptedLLM(gen([F1, F2], DRAFT2), ver([entry(F1, "unsupported"), entry(F2, "unsupported")]))
    ask(store, llm)
    generate_prompt, verify_prompt = llm.prompts
    assert Q in generate_prompt and ids["icp"] in generate_prompt and "requested_facts" in generate_prompt
    assert "Do not write citations" in generate_prompt and vf.INSUFFICIENT in generate_prompt
    assert Q in verify_prompt and f"1. {F1}" in verify_prompt and f"2. {F2}" in verify_prompt
    assert DRAFT2 in verify_prompt and ids["eng"] in verify_prompt and "exactly one entry per requested fact" in verify_prompt
    assert "unaddressed_parts" in verify_prompt


# ---------------------------------------------------------------- helpers
def test_strip_citations_only_removes_citation_like_brackets():
    assert vf.strip_citations("Fact one [02_icp.md › Best-fit customers]. Fact two [a.md#3].") == "Fact one. Fact two."
    assert vf.strip_citations("Costs rise [see note] a lot.") == "Costs rise [see note] a lot."
    assert vf.strip_citations("[x.md › y]") == ""


def test_parse_generation_accepts_valid_and_normalises_whitespace():
    facts, answer = vf.parse_generation(gen(["buyer  persona", "project\nlength"], "  An answer. "))
    assert facts == ["buyer persona", "project length"] and answer == "An answer."
