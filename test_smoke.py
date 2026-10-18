"""Offline tests for the manual smoke script (rag/smoke.py). The model is a mock and the keys are fake: nothing is sent anywhere.
The script's dry-run default and its explicit --confirm-hosted-call requirement are what these tests pin down."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

from rag import ingest, retriever, smoke
from test_rag import HashingEmbeddings

ROOT = Path(__file__).resolve().parent
FAKE_KEY = "fake-key-for-tests-not-real"
ENV = {"LLM_PROVIDER": "fireworks", "LLM_MODEL": "accounts/fireworks/models/test-model", "FIREWORKS_API_KEY": FAKE_KEY}
WEEKS = "A typical data engineering project takes eight to twelve weeks."
TEAM = "It is staffed by two engineers and one lead [01_capabilities.md › Data Engineering]."


@pytest.fixture(autouse=True)
def stable_retrieval_settings(monkeypatch):
    for name in list(__import__("os").environ):
        if name.startswith("RAG_") or name.startswith("LLM_") or name == "FIREWORKS_API_KEY":
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RAG_MAX_DISTANCE", "9")               # toy embedding: let the gate pass
    monkeypatch.setenv("RAG_CONTEXT_K", "15")                 # and put every chunk in context so ids are deterministic


@pytest.fixture()
def store(tmp_path):
    s = retriever.get_store(HashingEmbeddings(), persist_dir=tmp_path / "chroma")
    retriever.build_index(s, ingest.chunk_documents(ingest.load_documents()))
    return s


class Reply:
    def __init__(self, content, usage=None, meta=None):
        self.content, self.usage_metadata, self.response_metadata = content, usage, meta or {}


class ScriptedModel:
    def __init__(self, *replies):
        self.replies, self.prompts = list(replies), []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return self.replies[len(self.prompts) - 1]


class ExplodingModel:
    def invoke(self, prompt):
        raise AssertionError("a hosted call was attempted")


def good_replies():
    gen = json.dumps({"requested_facts": ["typical project duration", "team size"], "answer": f"{WEEKS} {TEAM}"})
    ver = json.dumps({"facts": [
        {"fact": "typical project duration", "status": "supported", "claim": WEEKS,
         "supporting_chunk_ids": ["01_capabilities.md#1"], "evidence_quote": "eight to twelve weeks"},
        {"fact": "team size", "status": "supported", "claim": TEAM,
         "supporting_chunk_ids": ["01_capabilities.md#1"], "evidence_quote": "two engineers and one lead"}],
        "unaddressed_parts": []})
    return (Reply(gen, usage={"input_tokens": 900, "output_tokens": 120, "total_tokens": 1020}),
            Reply(ver, meta={"token_usage": {"prompt_tokens": 1100, "completion_tokens": 200, "total_tokens": 1300}}))


def run(argv, store, model=None, env=ENV):
    lines = []
    code = smoke.main(argv, env=dict(env), store=store, model=model, out=lines.append)
    return code, "\n".join(lines)


# ---------------------------------------------------------------- default: dry run, nothing is sent
def test_default_is_a_dry_run_and_never_touches_the_model(store):
    code, text = run([], store, model=ExplodingModel())
    assert code == 0 and "DRY RUN" in text and "No hosted call was made" in text
    assert "--confirm-hosted-call" in text and "LIVE" not in text
    assert "01_capabilities.md#1" in text and "Local retrieval:" in text and "Would send to fireworks" in text
    assert FAKE_KEY not in text


def test_environment_approval_alone_does_not_allow_a_call(store):
    code, text = run([], store, model=ExplodingModel(), env={**ENV, "RAG_ALLOW_HOSTED_CALLS": "1"})
    assert code == 0 and "No hosted call was made" in text
    assert "RAG_ALLOW_HOSTED_CALLS is set, but this script ignores it" in text


def test_dry_run_needs_neither_a_key_nor_a_model(store):
    code, text = run([], store, model=ExplodingModel(), env={})
    assert code == 0 and "LLM_MODEL not set" in text and "API key: NOT set" in text


def test_prompt_is_shown_only_when_asked(store):
    _, quiet = run([], store, model=ExplodingModel())
    _, loud = run(["--show-prompt"], store, model=ExplodingModel())
    assert "generation prompt" not in quiet and "generation prompt (exactly what would be sent)" in loud
    assert "Passage id: 01_capabilities.md#1" in loud and smoke.DEFAULT_QUESTION in loud


def test_question_can_be_overridden(store):
    _, text = run(["--question", "What delivery modalities are offered?"], store, model=ExplodingModel())
    assert "Question: What delivery modalities are offered?" in text and smoke.DEFAULT_QUESTION not in text


def test_flag_defaults():
    ap = smoke.build_parser()
    assert ap.parse_args([]).confirm_hosted_call is False
    assert ap.parse_args(["--confirm-hosted-call"]).confirm_hosted_call is True
    assert ap.parse_args([]).question == smoke.DEFAULT_QUESTION


# ---------------------------------------------------------------- confirmed: one mocked generate + verify run
def test_confirmed_run_prints_verified_citations_status_and_token_usage(store):
    model = ScriptedModel(*good_replies())
    code, text = run(["--confirm-hosted-call"], store, model=model)
    assert code == 0 and len(model.prompts) == 2
    assert "LIVE - hosted calls APPROVED by --confirm-hosted-call" in text and "Sending to fireworks/accounts/fireworks/models/test-model" in text
    assert "Result: ANSWERED (2 model call(s))" in text
    assert "eight to twelve weeks" in text and "[01_capabilities.md › Data Engineering]  [01_capabilities.md#1]" in text
    assert "[supported]   typical project duration" in text and 'quote: "two engineers and one lead"' in text
    assert "call 1 (generate): input 900, output 120, total 1020" in text          # from usage_metadata
    assert "call 2 (verify): input 1100, output 200, total 1300" in text           # from response_metadata
    assert "total: input 2000, output 320, total 2320" in text
    assert "Send log: 2 call(s)" in text and FAKE_KEY not in text


def test_missing_usage_is_reported_honestly(store):
    gen, ver = good_replies()
    model = ScriptedModel(Reply(gen.content), Reply(ver.content))
    code, text = run(["--confirm-hosted-call"], store, model=model)
    assert code == 0 and "call 1 (generate): not reported by the provider" in text and "total: not reported" in text


def test_partial_answer_shows_the_unsupported_fact(store):
    gen, ver = good_replies()
    data = json.loads(ver.content)
    data["facts"][1] = {"fact": "team size", "status": "unsupported", "claim": "", "supporting_chunk_ids": [], "evidence_quote": ""}
    code, text = run(["--confirm-hosted-call"], store, model=ScriptedModel(gen, Reply(json.dumps(data))))
    assert code == 0 and "Result: PARTIAL" in text and "[UNSUPPORTED] team size" in text and "Partial answer" in text


def test_refusal_is_reported_with_a_reason_and_a_distinct_exit_code(store):
    gen, _ = good_replies()
    code, text = run(["--confirm-hosted-call"], store, model=ScriptedModel(gen, Reply("not json")))
    assert code == 3 and "Result: REFUSED" in text and "reason: verification_invalid" in text


def test_failed_gate_sends_nothing_even_when_confirmed(store, monkeypatch):
    monkeypatch.setenv("RAG_MAX_DISTANCE", "0")
    code, text = run(["--confirm-hosted-call"], store, model=ExplodingModel())
    assert code == 3 and "gate FAILED" in text and "nothing will be sent" in text
    assert "reason: gate" in text and "Sending to" not in text


# ---------------------------------------------------------------- confirmed but not configured: stops before anything
@pytest.mark.parametrize("env, missing", [({"LLM_MODEL": "m"}, "FIREWORKS_API_KEY"), ({"FIREWORKS_API_KEY": FAKE_KEY}, "LLM_MODEL"),
                                         ({}, "LLM_MODEL, FIREWORKS_API_KEY")])
def test_confirmed_without_setup_stops_before_any_call(store, env, missing):
    code, text = run(["--confirm-hosted-call"], store, model=ExplodingModel(), env=env)
    assert code == 2 and f"Cannot make a hosted call: {missing} not set" in text and "Nothing was sent" in text
    assert "Local retrieval" not in text and FAKE_KEY not in text


def test_bad_configuration_is_reported_without_echoing_values(store):
    code, text = run([], store, model=ExplodingModel(), env={"LLM_MAX_TOKENS": "very-secret-looking"})
    assert code == 2 and "LLM_MAX_TOKENS" in text and "very-secret-looking" not in text
    code, text = run([], store, model=ExplodingModel(), env={"LLM_PROVIDER": "openai"})
    assert code == 2 and "not enabled" in text


def test_empty_index_is_reported(tmp_path):
    empty = retriever.get_store(HashingEmbeddings(), persist_dir=tmp_path / "empty")
    code, text = run([], empty, model=ExplodingModel())
    assert code == 2 and "index is empty" in text


# ---------------------------------------------------------------- the script itself
def test_help_runs_without_network_or_index():
    r = subprocess.run([sys.executable, "-m", "rag.smoke", "--help"], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "--confirm-hosted-call" in r.stdout and "DRY RUN" in r.stdout


def test_model_id_is_not_hardcoded_anywhere_in_the_source():
    source = "".join((ROOT / "rag" / n).read_text() for n in ("smoke.py", "providers.py", "verify.py")) + (ROOT / ".env.example").read_text()
    for forbidden in ("gpt-oss", "llama-v", "nemotron", "deepseek", "kimi", "glm-5", "qwen3"):
        assert forbidden not in source.lower(), forbidden
