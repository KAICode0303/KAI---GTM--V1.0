"""Routing and message tests for Hoomi's chat logic (rag/chat.py), using the toy embedding and a throw-away workspace."""
import pytest

from gtm import pulse
from gtm.store import GTMStore
from rag import app_index, chat
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


def test_the_chat_module_has_no_hosted_provider_dependency():
    import ast
    from pathlib import Path
    tree = ast.parse((Path(chat.__file__)).read_text())
    mods = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not any(m and ("providers" in m or "fireworks" in m or m == "rag.verify") for m in mods), mods


def test_every_source_shows_the_sentence_that_came_from_its_own_chunk(env):
    """A fact backed by sentences from two chunks must list each chunk with its own quote (never another chunk's)."""
    g, store = env
    for q in ("What is a managed service?", "Who is the buyer at an AI lab and what signals matter?", "How do we position against crowd platforms?",
              "What does Deepcurrent Labs request?", "What is the difference between a fixed-scope project and a time-and-materials team?"):
        msg = chat.ask(q, "Documents", g, store)
        for s in msg["sources"]:
            assert s["quote"] in s["passage"], (q, s["chunk_id"])
        assert len({s["chunk_id"] for s in msg["sources"]}) == len(msg["sources"])
