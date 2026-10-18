"""Offline tests for the provider layer (rag/providers.py). No hosted call is ever made: models are mocks, keys are fake,
and one test disables sockets to prove that building the real ChatFireworks object touches no network."""
import socket
import subprocess
from pathlib import Path

import pytest

from rag import providers as pv

ROOT = Path(__file__).resolve().parent
FAKE_KEY = "fake-key-for-tests-not-real"


def cfg(**kw):
    base = dict(model="accounts/fireworks/models/test-model", api_key=FAKE_KEY)
    base.update(kw)
    return pv.ProviderConfig(**base)


# ---------------------------------------------------------------- configuration
def test_defaults_when_environment_is_empty():
    c = pv.load_config(env={})
    assert (c.provider, c.model, c.api_key) == ("fireworks", "", "")
    assert (c.temperature, c.max_tokens, c.timeout, c.max_retries) == (0.0, 1024, 60.0, 2)
    assert c.json_mode is False and c.allow_hosted_calls is False         # hosted calls are OFF unless approved


def test_values_are_read_from_the_environment():
    c = pv.load_config(env={"LLM_PROVIDER": " Fireworks ", "LLM_MODEL": "m-1", "FIREWORKS_API_KEY": FAKE_KEY,
                            "LLM_TEMPERATURE": "0.2", "LLM_MAX_TOKENS": "256", "LLM_TIMEOUT": "9.5", "LLM_MAX_RETRIES": "0",
                            "LLM_JSON_MODE": "true", "RAG_ALLOW_HOSTED_CALLS": "1"})
    assert (c.provider, c.model, c.api_key) == ("fireworks", "m-1", FAKE_KEY)
    assert (c.temperature, c.max_tokens, c.timeout, c.max_retries) == (0.2, 256, 9.5, 0)
    assert c.json_mode and c.allow_hosted_calls


@pytest.mark.parametrize("value, expected", [("1", True), ("true", True), ("YES", True), ("on", True),
                                             ("0", False), ("false", False), ("", False), ("maybe", False)])
def test_approval_flag_only_turns_on_for_explicit_yes(value, expected):
    assert pv.load_config(env={"RAG_ALLOW_HOSTED_CALLS": value}).allow_hosted_calls is expected


def test_bad_numbers_name_the_variable_but_not_the_value():
    with pytest.raises(ValueError) as exc:
        pv.load_config(env={"LLM_MAX_TOKENS": "secret-looking-value"})
    assert "LLM_MAX_TOKENS" in str(exc.value) and "secret-looking-value" not in str(exc.value)


def test_unknown_and_planned_providers():
    with pytest.raises(ValueError, match="Unknown"):
        pv.load_config(env={"LLM_PROVIDER": "nonsense"})
    for planned in ("openai", "anthropic"):
        with pytest.raises(NotImplementedError, match="not enabled"):
            pv.load_config(env={"LLM_PROVIDER": planned})


def test_key_is_never_in_repr_or_redacted_summary():
    c = cfg()
    assert FAKE_KEY not in repr(c) and FAKE_KEY not in str(c.redacted())
    assert c.redacted()["api_key_set"] is True and pv.ProviderConfig().redacted()["api_key_set"] is False


def test_dotenv_is_loaded_only_when_reading_the_real_environment(monkeypatch):
    calls = []
    monkeypatch.setattr(pv, "_load_dotenv", lambda: calls.append(1))
    pv.load_config(env={})                                   # explicit dict: never touches .env
    pv.load_config(env=None, use_dotenv=False)               # real environment, but dotenv switched off
    assert calls == []
    pv.load_config(env=None, use_dotenv=True)
    assert calls == [1]


# ---------------------------------------------------------------- building the model (no calls)
def test_missing_model_or_key_is_a_configuration_error_without_echoing_secrets():
    with pytest.raises(pv.ConfigurationError, match="LLM_MODEL"):
        pv.build_chat_model(cfg(model=""))
    with pytest.raises(pv.MissingApiKeyError) as exc:
        pv.build_chat_model(cfg(api_key=""))
    assert "FIREWORKS_API_KEY" in str(exc.value)


def test_build_chat_model_passes_settings_to_langchain_fireworks(monkeypatch):
    seen = {}

    class FakeChat:
        def __init__(self, **kw):
            seen.update(kw)

    monkeypatch.setattr(pv, "_fireworks_class", lambda: FakeChat)
    pv.build_chat_model(cfg(temperature=0.1, max_tokens=300, timeout=7, max_retries=1))
    assert seen == {"model": "accounts/fireworks/models/test-model", "api_key": FAKE_KEY, "temperature": 0.1,
                    "max_tokens": 300, "timeout": 7, "max_retries": 1}
    seen.clear()
    pv.build_chat_model(cfg(json_mode=True))
    assert seen["model_kwargs"] == {"response_format": {"type": "json_object"}}


def test_real_chatfireworks_object_builds_without_any_network(monkeypatch):
    def no_network(*a, **k):
        raise AssertionError("network access attempted while building the chat model")

    monkeypatch.setattr(socket, "socket", no_network)
    monkeypatch.setattr(socket, "create_connection", no_network)
    monkeypatch.setattr(socket, "getaddrinfo", no_network)
    model = pv.build_chat_model(cfg(temperature=0, max_tokens=64, timeout=5, max_retries=0))
    assert type(model).__name__ == "ChatFireworks"
    assert model.model_name == "accounts/fireworks/models/test-model" and model.max_tokens == 64


# ---------------------------------------------------------------- the client and the approval guard
class FakeModel:
    def __init__(self, content="reply"):
        self.content, self.prompts = content, []

    def invoke(self, prompt):
        self.prompts.append(prompt)
        return type("Msg", (), {"content": self.content})()


def test_unapproved_hosted_call_is_refused_before_any_model_is_built(monkeypatch):
    monkeypatch.setattr(pv, "build_chat_model", lambda c: pytest.fail("a model must not be built without approval"))
    client = pv.LLMClient(cfg(allow_hosted_calls=False))
    with pytest.raises(pv.HostedCallNotApproved, match="RAG_ALLOW_HOSTED_CALLS"):
        client("a question and passages")
    assert client.sent == []


def test_approved_call_goes_to_the_model_and_is_logged_without_text_or_key():
    model, log = FakeModel("hello"), []
    client = pv.LLMClient(cfg(allow_hosted_calls=True), model=model, on_send=log.append)
    assert client("some private passage text") == "hello"
    assert model.prompts == ["some private passage text"]
    assert len(client.sent) == 1 and log == client.sent
    rec = client.sent[0]
    assert (rec.provider, rec.model, rec.prompt_chars) == ("fireworks", "accounts/fireworks/models/test-model", 25)
    assert "private" not in repr(rec) and FAKE_KEY not in repr(rec)


def test_client_builds_the_model_lazily_and_only_once(monkeypatch):
    built = []
    monkeypatch.setattr(pv, "build_chat_model", lambda c: built.append(1) or FakeModel("x"))
    client = pv.LLMClient(cfg(allow_hosted_calls=True))
    assert built == []
    client("a")
    client("b")
    assert built == [1]


def test_message_content_lists_are_flattened_to_text():
    client = pv.LLMClient(cfg(allow_hosted_calls=True), model=FakeModel([{"type": "text", "text": "one "}, "two"]))
    assert client("p") == "one two"


# ---------------------------------------------------------------- .env.example
def test_env_example_has_placeholders_only_and_covers_every_setting():
    lines = (ROOT / ".env.example").read_text().splitlines()
    active = dict(ln.split("=", 1) for ln in lines if ln.strip() and not ln.lstrip().startswith("#"))
    assert active["FIREWORKS_API_KEY"] == "your-fireworks-api-key-here"
    assert "your-model-id" in active["LLM_MODEL"] and active["RAG_ALLOW_HOSTED_CALLS"] == "0"
    text = "\n".join(lines)
    for name in ("LLM_PROVIDER", "LLM_MODEL", "FIREWORKS_API_KEY", "LLM_TEMPERATURE", "LLM_MAX_TOKENS", "LLM_TIMEOUT",
                 "LLM_MAX_RETRIES", "LLM_JSON_MODE", "RAG_ALLOW_HOSTED_CALLS", "RAG_MAX_DISTANCE", "RAG_CONTEXT_K",
                 "RAG_CONTEXT_MAX_DISTANCE", "RAG_CONTEXT_MARGIN", "RAG_CONTEXT_MIN_CHUNKS"):
        assert name in text, name
    for value in active.values():                              # nothing in the template resembles a real secret
        assert not value.startswith(("fw_", "sk-")) and len(value) < 60


def test_env_is_ignored_by_git_but_the_example_is_not():
    try:
        def ignored(path):
            return subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0
        assert ignored(".env") and ignored(".env.local") and not ignored(".env.example")
    except FileNotFoundError:
        pytest.skip("git not available")
