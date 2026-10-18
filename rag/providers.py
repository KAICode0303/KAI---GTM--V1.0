"""Configurable chat-model provider (Fireworks AI first; OpenAI and Anthropic can be added later).

Nothing here calls a hosted model on import or on construction. A call happens only when `LLMClient.__call__` runs, and
only if hosted calls have been explicitly approved (`RAG_ALLOW_HOSTED_CALLS`, default off), because a call sends the
question and the retrieved passages to the provider. Local embeddings (FastEmbed) and the Chroma index never leave the machine.

Settings come from the environment (a git-ignored `.env` is loaded if present; see `.env.example`):
    LLM_PROVIDER (default fireworks)   LLM_MODEL (required)      FIREWORKS_API_KEY (required for fireworks)
    LLM_TEMPERATURE  LLM_MAX_TOKENS  LLM_TIMEOUT  LLM_MAX_RETRIES  LLM_JSON_MODE  RAG_ALLOW_HOSTED_CALLS
The API key is held in a field that is excluded from repr and is never logged or included in error messages.
"""
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENABLED_PROVIDERS = ("fireworks",)
PLANNED_PROVIDERS = ("openai", "anthropic")          # same interface; not enabled until their packages are installed
API_KEY_ENV = {"fireworks": "FIREWORKS_API_KEY"}
TRUE_VALUES = {"1", "true", "yes", "on"}


class ConfigurationError(RuntimeError):
    """Setup problem the caller must fix (missing key or model, hosted calls not approved). Never retried or swallowed."""


class MissingApiKeyError(ConfigurationError):
    pass


class HostedCallNotApproved(ConfigurationError):
    pass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "fireworks"
    model: str = ""                                  # required; there is deliberately no default model id
    api_key: str = field(default="", repr=False)     # excluded from repr
    temperature: float = 0.0
    max_tokens: int = 1024
    timeout: float = 60.0
    max_retries: int = 2
    json_mode: bool = False                          # ask the provider for a JSON-object response (untested against the live API)
    allow_hosted_calls: bool = False                 # explicit approval to send the question and passages to the provider

    def redacted(self):
        """Safe summary for logs and the UI: never includes the key."""
        return {"provider": self.provider, "model": self.model, "api_key_set": bool(self.api_key),
                "temperature": self.temperature, "max_tokens": self.max_tokens, "timeout": self.timeout,
                "max_retries": self.max_retries, "json_mode": self.json_mode, "allow_hosted_calls": self.allow_hosted_calls}


def _load_dotenv():
    """Load ROOT/.env into os.environ without overriding variables that are already set."""
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)


def _number(env, name, cast, default):
    raw = str(env.get(name, "")).strip()
    if not raw:
        return default
    try:
        return cast(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number") from None          # the value itself is not echoed


def load_config(env=None, use_dotenv=True):
    """Build a ProviderConfig. env=None reads os.environ (after loading .env when use_dotenv); pass a dict to avoid both."""
    if env is None:
        if use_dotenv:
            _load_dotenv()
        env = os.environ
    provider = str(env.get("LLM_PROVIDER", "fireworks")).strip().lower() or "fireworks"
    if provider in PLANNED_PROVIDERS:
        raise NotImplementedError(f"Provider {provider!r} is planned but not enabled yet; enabled: {', '.join(ENABLED_PROVIDERS)}.")
    if provider not in ENABLED_PROVIDERS:
        raise ValueError(f"Unknown LLM_PROVIDER {provider!r}; enabled: {', '.join(ENABLED_PROVIDERS)}.")
    return ProviderConfig(
        provider=provider,
        model=str(env.get("LLM_MODEL", "")).strip(),
        api_key=str(env.get(API_KEY_ENV[provider], "")).strip(),
        temperature=_number(env, "LLM_TEMPERATURE", float, 0.0),
        max_tokens=_number(env, "LLM_MAX_TOKENS", int, 1024),
        timeout=_number(env, "LLM_TIMEOUT", float, 60.0),
        max_retries=_number(env, "LLM_MAX_RETRIES", int, 2),
        json_mode=str(env.get("LLM_JSON_MODE", "")).strip().lower() in TRUE_VALUES,
        allow_hosted_calls=str(env.get("RAG_ALLOW_HOSTED_CALLS", "")).strip().lower() in TRUE_VALUES)


def _fireworks_class():
    from langchain_fireworks import ChatFireworks
    return ChatFireworks


def build_chat_model(config):
    """Create the LangChain chat model. Needs a model id and a key; does NOT send anything."""
    if not config.model:
        raise ConfigurationError("LLM_MODEL is not set (there is no default model; see .env.example).")
    if config.provider == "fireworks":
        if not config.api_key:
            raise MissingApiKeyError(f"{API_KEY_ENV['fireworks']} is not set.")
        kwargs = dict(model=config.model, api_key=config.api_key, temperature=config.temperature,
                      max_tokens=config.max_tokens, timeout=config.timeout, max_retries=config.max_retries)
        if config.json_mode:
            kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        return _fireworks_class()(**kwargs)
    raise NotImplementedError(f"Provider {config.provider!r} is not enabled.")


def _text(content):
    """Chat models return a string or a list of content parts; keep only the text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p if isinstance(p, str) else str(p.get("text", "")) for p in content if isinstance(p, (str, dict)))
    return str(content)


@dataclass(frozen=True)
class SendRecord:
    """What was sent, without the text: enough to audit that a hosted call happened and how much left the machine."""
    provider: str
    model: str
    prompt_chars: int
    timestamp: float


class LLMClient:
    """`client(prompt) -> str`, the interface the answer pipeline expects. Refuses hosted calls that are not approved."""

    def __init__(self, config, model=None, on_send=None):
        self.config = config
        self._model = model                          # injectable for tests; otherwise built lazily on the first approved call
        self._on_send = on_send
        self.sent = []

    def __call__(self, prompt):
        if not self.config.allow_hosted_calls:
            raise HostedCallNotApproved("Hosted model calls are not approved. This would send the question and retrieved "
                                        "passages to the provider; set RAG_ALLOW_HOSTED_CALLS=1 to approve.")
        if self._model is None:
            self._model = build_chat_model(self.config)
        record = SendRecord(self.config.provider, self.config.model, len(prompt), time.time())
        self.sent.append(record)
        if self._on_send:
            self._on_send(record)
        return _text(self._model.invoke(prompt).content)
