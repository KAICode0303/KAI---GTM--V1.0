"""Manual smoke test for Hoomi's RAG pipeline: local retrieval, then (only if you confirm) one hosted generate + verify run.

    python -m rag.smoke                           DRY RUN (default): local retrieval only. Shows exactly what WOULD be sent. No hosted call.
    python -m rag.smoke --confirm-hosted-call     Makes the two hosted calls (generate, verify) to the provider named in your .env.

Hosted calls need the explicit flag above. RAG_ALLOW_HOSTED_CALLS in the environment is deliberately NOT enough on its own: this
script overrides it, so a stray variable can never trigger a call. A hosted call sends the question and the retrieved passages
(from the synthetic corpus here) to the provider. Embeddings and the Chroma index stay local (cached FastEmbed model, no downloads).

Exit codes: 0 completed (dry run, answered or partial) | 2 configuration problem, nothing was sent | 3 completed but refused.
"""
import argparse
import dataclasses
import os

from rag.answer import gather_evidence, resolve_context_policy, resolve_max_distance
from rag.providers import API_KEY_ENV, ConfigurationError, LLMClient, load_config
from rag.verify import MAX_FACTS, answer_verified, build_generation_prompt

# A two-part capabilities question: it exercises per-fact verification. Not a tuning target.
DEFAULT_QUESTION = "How long does a typical data engineering project take, and how many people work on it?"


def build_parser():
    ap = argparse.ArgumentParser(prog="python -m rag.smoke", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--question", default=DEFAULT_QUESTION, help="question to ask (default: a synthetic capabilities question)")
    ap.add_argument("--confirm-hosted-call", action="store_true",
                    help="REQUIRED to make the hosted calls. Without it nothing is sent anywhere (dry run).")
    ap.add_argument("--show-prompt", action="store_true", help="print the full generation prompt (the exact text that would be sent)")
    ap.add_argument("--no-dotenv", action="store_true", help="do not load .env (use only the process environment)")
    return ap


def _open_store():
    os.environ.setdefault("HF_HUB_OFFLINE", "1")                       # belt and braces: the model must come from the local cache
    from rag.embeddings import FastEmbedEmbeddings
    from rag.retriever import get_store
    return get_store(FastEmbedEmbeddings())


def _fmt_tokens(u):
    if not u:
        return "not reported by the provider"
    return ", ".join(f"{k.split('_')[0]} {u[k]}" for k in ("input_tokens", "output_tokens", "total_tokens") if u.get(k) is not None) or "not reported"


def main(argv=None, env=None, store=None, model=None, out=print):
    """env/store/model are injection points for tests; a real run leaves them None."""
    args = build_parser().parse_args(argv)
    confirmed = args.confirm_hosted_call
    try:
        config = load_config(env=env, use_dotenv=(env is None and not args.no_dotenv))
    except (ValueError, NotImplementedError) as exc:
        out(f"Configuration problem: {exc}")
        return 2
    env_says_yes = config.allow_hosted_calls
    config = dataclasses.replace(config, allow_hosted_calls=confirmed)  # the flag decides; the environment cannot approve a call

    out("=== Hoomi RAG smoke test ===")
    out(f"Mode: {'LIVE - hosted calls APPROVED by --confirm-hosted-call' if confirmed else 'DRY RUN - no hosted call will be made'}")
    s = config.redacted()
    out(f"Provider: {s['provider']} | model: {s['model'] or '(LLM_MODEL not set)'} | API key: {'set' if s['api_key_set'] else 'NOT set'} "
        f"| max_tokens {s['max_tokens']} | json_mode {s['json_mode']}")
    if env_says_yes and not confirmed:
        out("Note: RAG_ALLOW_HOSTED_CALLS is set, but this script ignores it. It requires --confirm-hosted-call.")

    if confirmed:                                                      # fail before retrieval or any call if setup is incomplete
        missing = [name for name, ok in (("LLM_MODEL", config.model), (API_KEY_ENV.get(config.provider, "API key"), config.api_key)) if not ok]
        if missing:
            out(f"Cannot make a hosted call: {', '.join(missing)} not set. Nothing was sent. See .env.example.")
            return 2

    store = store if store is not None else _open_store()
    if not store._collection.count():
        out("The Chroma index is empty. Build it first (rag.retriever.build_index). Nothing was sent.")
        return 2

    gate, policy = resolve_max_distance(), resolve_context_policy()
    out(f"\nQuestion: {args.question}")
    out(f"Gate distance {gate:g} | context policy: {policy.describe()}")
    evidence = gather_evidence(store, args.question)
    best = f"{evidence.best_distance:.3f}" if evidence.best_distance is not None else "n/a"
    out(f"Local retrieval: closest chunk {best} -> gate {'PASSED' if evidence.sufficient else 'FAILED (the model would not be called)'}")
    for h in evidence.hits:
        out(f"  - {h.chunk_id:<24} {h.citation}  distance {h.distance:.3f}  ({len(h.text)} chars)")

    if not confirmed:
        if evidence.sufficient:
            prompt = build_generation_prompt(evidence)
            chars = sum(len(h.text) for h in evidence.hits)
            out(f"\nWould send to {config.provider}/{config.model or '(model not set)'} in TWO calls: (1) generate, a prompt of "
                f"{len(prompt)} chars carrying the question and {len(evidence.hits)} passages ({chars} chars of passage text); "
                f"(2) verify, which also carries the draft answer, so slightly longer.")
            if args.show_prompt:
                out("\n--- generation prompt (exactly what would be sent) ---\n" + prompt + "\n--- end ---")
        out("\nNo hosted call was made. To run the live test:  python -m rag.smoke --confirm-hosted-call")
        return 0

    if evidence.sufficient:
        chars = sum(len(h.text) for h in evidence.hits)
        out(f"\nSending to {config.provider}/{config.model}: the question and {len(evidence.hits)} passages ({chars} chars of text).")
    else:
        out("\nThe gate failed, so nothing will be sent.")
    client = LLMClient(config, model=model)
    try:
        result = answer_verified(store, args.question, client, max_facts=MAX_FACTS)
    except ConfigurationError as exc:
        out(f"Configuration problem: {exc}")
        return 2

    out(f"\n=== Result: {result.status.upper()} ({result.model_calls} model call(s)) ===")
    if result.status == "refused":
        out(f"Refused. reason: {result.reason}" + (f" | detail: {result.detail}" if result.detail else ""))
    else:
        out(result.text)
        out("\nVerified citations (derived only from chunks whose quote was found in the text):")
        for c, cid in zip(result.sources, result.source_chunk_ids):
            out(f"  {c}  [{cid}]")
        out("\nPer requested fact:")
        for f in result.facts:
            if f.supported:
                out(f"  [supported]   {f.fact}\n                quote: \"{f.quote}\"  chunks: {', '.join(f.chunk_ids)}")
            else:
                out(f"  [UNSUPPORTED] {f.fact}  (reason: {f.reason})")
    out("\nToken usage (as reported by the provider):")
    for i, u in enumerate(client.usage, 1):
        out(f"  call {i} ({'generate' if i == 1 else 'verify'}): {_fmt_tokens(u)}")
    out(f"  total: {_fmt_tokens(client.total_usage())}")
    out(f"Send log: {len(client.sent)} call(s), prompt sizes {[r.prompt_chars for r in client.sent]} chars. No keys or text are logged.")
    return 3 if result.status == "refused" else 0


if __name__ == "__main__":
    raise SystemExit(main())
