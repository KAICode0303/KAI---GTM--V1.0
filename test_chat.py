"""Routing and message tests for Hoomi's chat logic (rag/chat.py), using the toy embedding and a throw-away workspace."""
import pytest

from gtm import pulse
from gtm.store import GTMStore
from rag import app_index, chat
from rag.retriever import retrieve
from test_rag import HashingEmbeddings


@pytest.fixture(autouse=True)
def settings(monkeypatch):
    monkeypatch.setenv("RAG_MAX_DISTANCE", "9")
    monkeypatch.setenv("RAG_CONTEXT_K", "8")
    monkeypatch.setenv("HOOMI_OFFLINE_MIN_SIM", "0.2")


@pytest.fixture()
def env(tmp_path):
    g = GTMStore(tmp_path / "g.db")
    store, _ = app_index.ensure_index(HashingEmbeddings(), g, persist_dir=tmp_path / "idx")
    return g, store


def test_a_metric_question_is_calculated(env):
    g, store = env
    msg = chat.ask("What is our open pipeline?", "Auto", g, store)
    assert msg["kind"] == "numbers" and msg["sources"] == [] and "Executive Pulse" in msg["content"]


def test_a_question_about_one_account_never_gets_a_workspace_wide_figure(env):
    g, store = env
    msg = chat.ask("What are the requested capabilities for Deepcurrent Labs?", "Auto", g, store)
    assert msg["kind"] != "numbers" and "most requested capability" not in msg["content"]
    assert msg["meta"]["scope_account"] == "ACC-101" and all(s["chunk_id"].startswith("kyc_ACC-101") for s in msg["sources"])
    pipeline = chat.ask("What is the open pipeline for Deepcurrent Labs?", "Auto", g, store)
    assert pipeline["kind"] != "numbers"                                                 # routed to documents, so it cannot quote the global number
    forced = chat.ask("What is the open pipeline for Deepcurrent Labs?", "Numbers", g, store)
    assert forced["kind"] == "insufficient" and "whole workspace" in forced["content"] and "$" not in forced["content"]


def test_general_capability_demand_is_still_a_numbers_question(env):
    g, store = env
    assert chat.ask("What are the most requested capabilities?", "Auto", g, store)["kind"] == "numbers"


def test_documents_route_never_calculates(env):
    g, store = env
    msg = chat.ask("What is our open pipeline?", "Documents", g, store)
    assert msg["kind"] != "numbers"


def test_insufficient_evidence_is_final_and_not_rescued_by_the_v1_keyword_rules(env, monkeypatch):
    g, store = env
    monkeypatch.setenv("RAG_MAX_DISTANCE", "0")
    import hoomi
    monkeypatch.setattr(hoomi, "answer_with_mood", lambda *a, **k: pytest.fail("the V1 rules must not rescue a refusal"))
    msg = chat.ask("Who won the football world cup?", "Auto", g, store, ws=object())
    assert msg["kind"] == "insufficient" and "Insufficient evidence" in msg["content"] and msg["sources"] == []
    assert msg["meta"]["reason"] == "gate" and msg["meta"]["gate"] == 0 and msg["meta"]["best_distance"] is not None


def test_rule_based_is_only_used_when_chosen_or_search_is_unavailable(env):
    g, store = env

    class Ws:
        pass

    explicit = chat.ask("What is our total pipeline?", "Rule-based", g, store, ws=None)
    assert explicit["kind"] == "insufficient" and explicit["meta"]["route"] == "rulebased"           # no V1 workspace given: honest, no crash
    degraded = chat.ask("What is a managed service?", "Auto", g, None, "model missing", ws=None)
    assert degraded["kind"] == "insufficient" and "Document search is unavailable" in degraded["content"]


@pytest.mark.parametrize("raw", ["", "   ", "\x00\x01"])
def test_empty_questions_are_handled(env, raw):
    g, store = env
    assert chat.ask(raw, "Auto", g, store)["kind"] == "insufficient"


def test_questions_are_cleaned_and_capped():
    assert chat.clean_question("  hello \x00 \n  world  ") == "hello world"
    assert len(chat.clean_question("x" * 5000)) == chat.MAX_QUESTION_CHARS


def test_unknown_route_falls_back_to_auto(env):
    g, store = env
    assert chat.ask("What is our open pipeline?", "nonsense", g, store)["kind"] == "numbers"


def test_messages_carry_sources_with_verbatim_quotes_and_per_fact_checks(env):
    g, store = env
    msg = chat.ask("What is a managed service?", "Documents", g, store)
    assert msg["kind"] in ("answered", "partial") and msg["sources"] and msg["facts"]
    for s in msg["sources"]:
        assert s["quote"] in s["passage"] and s["citation"].startswith("[") and s["chunk_id"]
    assert msg["meta"]["model_calls"] == 0 and "offline" in msg["meta"]["engine"]


def test_the_chat_module_loads_no_provider_code_at_import_time():
    """Provider code is imported lazily, inside the hosted path only; nothing at module level can reach a network library."""
    import ast
    from pathlib import Path
    tree = ast.parse((Path(chat.__file__)).read_text())
    top = [n for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))]
    mods = {n.module for n in top if isinstance(n, ast.ImportFrom)} | {a.name for n in top if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and ("providers" in m or "fireworks" in m or m in ("requests", "httpx", "openai")) for m in mods), mods


def test_every_source_shows_the_sentence_that_came_from_its_own_chunk(env):
    """A fact backed by sentences from two chunks must list each chunk with its own quote (never another chunk's)."""
    g, store = env
    for q in ("What is a managed service?", "Who is the buyer at an AI lab and what signals matter?", "How do we position against crowd platforms?",
              "What does Deepcurrent Labs request?", "What is the difference between a fixed-scope project and a time-and-materials team?"):
        msg = chat.ask(q, "Documents", g, store)
        for s in msg["sources"]:
            assert s["quote"] in s["passage"], (q, s["chunk_id"])
        assert len({s["chunk_id"] for s in msg["sources"]}) == len(msg["sources"])



# ---------------------------------------------------------------- hosted (Fireworks) path: only with an approved client; mocked here
import json


class ScriptedClient:
    """Stands in for an approved LLMClient: returns scripted replies in order. It never touches a network."""

    def __init__(self, *replies):
        self.replies, self.prompts, self.sent = list(replies), [], []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        r = self.replies[len(self.prompts) - 1]
        if isinstance(r, Exception):
            raise r
        return r


def managed_service_replies(env):
    g, store = env
    hits = retrieve(store, "managed service", k=15, where={"doc_type": {"$ne": "kyc"}})
    chunk = next(h for h in hits if h.section == "Managed service")
    sentence = "A managed service is a recurring program where Kai's Company owns delivery against quality and throughput targets."
    gen = json.dumps({"requested_facts": ["what a managed service is"], "answer": sentence + " [fake.md › Invented]"})
    ver = json.dumps({"facts": [{"fact": "what a managed service is", "status": "supported", "claim": sentence + " [fake.md › Invented]",
                                 "supporting_chunk_ids": [chunk.chunk_id], "evidence_quote": "recurring program where Kai's Company owns delivery"}],
                      "unaddressed_parts": []})
    return gen, ver, chunk


def test_an_approved_client_gives_a_verified_natural_language_answer(env):
    g, store = env
    gen, ver, chunk = managed_service_replies(env)
    client = ScriptedClient(gen, ver)
    msg = chat.ask("What is a managed service?", "Documents", g, store, hosted=client)
    assert msg["kind"] == "answered" and msg["meta"]["engine"] == "fireworks-verified" and msg["meta"]["hosted_calls"] == 2
    assert len(client.prompts) == 2 and "Passage id:" in client.prompts[0]
    assert "fake.md" not in msg["content"] and "Invented" not in msg["content"]               # model-written citations never reach the user
    assert [s["chunk_id"] for s in msg["sources"]] == [chunk.chunk_id] and msg["sources"][0]["citation"] == chunk.citation
    assert msg["facts"][0]["supported"] and "verified" in msg["facts"][0]["detail"]


def test_the_default_is_offline_so_nothing_is_ever_sent(env):
    g, store = env
    msg = chat.ask("What is a managed service?", "Documents", g, store)                       # hosted=None
    assert msg["meta"]["model_calls"] == 0 and msg["meta"]["engine"] == "offline-extractive"


@pytest.mark.parametrize("replies, reason", [
    ((RuntimeError("boom"),), "the hosted call failed"),
    (("this is not json",), "the hosted reply was not usable"),
])
def test_a_failed_hosted_answer_falls_back_to_the_labelled_offline_answer(env, replies, reason):
    g, store = env
    msg = chat.ask("What is a managed service?", "Documents", g, store, hosted=ScriptedClient(*replies))
    assert reason in msg["content"].lower() and "offline answer instead" in msg["content"]
    assert msg["kind"] in ("answered", "partial") and msg["meta"]["engine"] == "offline-extractive" and msg["meta"]["hosted_fallback"]
    assert all(s["quote"] in s["passage"] for s in msg["sources"])


def test_an_unverifiable_hosted_answer_is_not_shown_as_verified(env):
    g, store = env
    gen, _ver, chunk = managed_service_replies(env)
    bad_ver = json.dumps({"facts": [{"fact": "what a managed service is", "status": "supported", "claim": "A managed service is a recurring program.",
                                     "supporting_chunk_ids": [chunk.chunk_id], "evidence_quote": "guaranteed ten-fold return on investment"}],
                          "unaddressed_parts": []})
    msg = chat.ask("What is a managed service?", "Documents", g, store, hosted=ScriptedClient(gen, bad_ver))
    assert msg["kind"] == "insufficient" and "Insufficient evidence" in msg["content"] and msg["sources"] == []   # fails closed, no invented support


def test_a_gate_refusal_stays_a_refusal_even_with_an_approved_client(env, monkeypatch):
    g, store = env
    monkeypatch.setenv("RAG_MAX_DISTANCE", "0")
    client = ScriptedClient()
    msg = chat.ask("Who won the football world cup?", "Documents", g, store, hosted=client)
    assert msg["kind"] == "insufficient" and client.prompts == [] and msg["sources"] == []   # no evidence means nothing is even sent


def test_a_configuration_error_from_the_client_becomes_a_message_not_a_crash(env):
    from rag.providers import HostedCallNotApproved
    g, store = env
    msg = chat.ask("What is a managed service?", "Documents", g, store, hosted=ScriptedClient(HostedCallNotApproved("not approved")))
    assert msg["kind"] == "insufficient" and "Fireworks is not available" in msg["content"] and "not approved" in msg["content"]


def test_metric_questions_never_use_the_hosted_client(env):
    g, store = env
    client = ScriptedClient()
    assert chat.ask("What is our open pipeline?", "Auto", g, store, hosted=client)["kind"] == "numbers" and client.prompts == []
