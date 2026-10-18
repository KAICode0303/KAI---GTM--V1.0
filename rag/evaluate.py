"""Retrieval evaluation: does the right chunk come back, and does a distance threshold accept/refuse correctly?

Measures RETRIEVAL only. No LLM is involved, so nothing here says anything about generated-answer accuracy.
Read-only on the index; uses the cached FastEmbed model (downloads blocked) and local Chroma.

Run:  HF_HUB_OFFLINE=1 .venv312/bin/python -m rag.evaluate
Writes: eval/results.json (raw, per question) and eval/report.md (readable; appends eval/analysis_notes.md if present).
"""
import json
import re
import statistics
from pathlib import Path

from rag.retriever import retrieve

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "eval"
QUESTIONS = EVAL_DIR / "questions.json"
RESULTS = EVAL_DIR / "results.json"
REPORT = EVAL_DIR / "report.md"
NOTES = EVAL_DIR / "analysis_notes.md"

CONTEXT_K = 4                      # chunks the answer step would see (same default as answer.gather_evidence)
PROVISIONAL = 0.70                 # the provisional threshold being examined, not a recommendation
SWEEP = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]


def load_questions(path=QUESTIONS):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def norm(text):
    """Lower-case, straight apostrophes, collapsed whitespace: so evidence phrases match across line wraps."""
    return re.sub(r"\s+", " ", text.replace("’", "'")).lower()


def key(h):
    return (h["source"], h["section"])


# ---------------------------------------------------------------- run
def run(store, questions):
    """Rank EVERY chunk for every question (so we can see where an expected section landed), then score it."""
    n_chunks = store._collection.count()
    results = []
    for q in questions:
        ranking = [{"rank": i, "source": h.source, "section": h.section, "distance": round(h.distance, 4), "text": h.text}
                   for i, h in enumerate(retrieve(store, q["question"], k=n_chunks), 1)]
        expected = [(e["source"], e["section"]) for e in q["expected"]]
        rank_of = {key(h): h for h in ranking}
        detail = []
        for src, sec in expected:
            h = rank_of.get((src, sec))
            detail.append({"source": src, "section": sec, "rank": h["rank"] if h else None,
                           "distance": h["distance"] if h else None})
        top3 = {key(h) for h in ranking[:3]}
        ctx = {key(h) for h in ranking[:CONTEXT_K]}
        top3_text = norm(" ".join(h["text"] for h in ranking[:3]))
        results.append({
            "id": q["id"], "category": q["category"], "question": q["question"], "answerable": q["answerable"],
            "expected": detail, "required_evidence": q["required_evidence"], "ranking": ranking,
            "top1_hit": bool(expected) and key(ranking[0]) in expected,
            "top3_hit": bool(expected) and any(e in top3 for e in expected),
            "all_expected_in_top3": bool(expected) and all(e in top3 for e in expected),
            "all_expected_in_context": bool(expected) and all(e in ctx for e in expected),
            "evidence_in_top3": bool(q["required_evidence"]) and all(norm(p) in top3_text for p in q["required_evidence"]),
        })
    return results


# ---------------------------------------------------------------- threshold scoring
def context_at(r, t):
    """Chunks the answer step would be given at threshold t."""
    return [h for h in r["ranking"][:CONTEXT_K] if h["distance"] <= t]


def accepted(r, t):
    return r["ranking"][0]["distance"] <= t


def evidence_complete(r, t):
    text = norm(" ".join(h["text"] for h in context_at(r, t)))
    return all(norm(p) in text for p in r["required_evidence"])


def sections_in_context(r, t):
    keys = {key(h) for h in context_at(r, t)}
    return sum((e["source"], e["section"]) in keys for e in r["expected"])


def score(results, t):
    s = {"threshold": t, "correct_accept": 0, "false_rejection": 0, "correct_refusal": 0, "false_acceptance": 0,
         "accepted_with_missing_evidence": 0, "accepted_with_missing_section": 0}
    for r in results:
        if r["answerable"]:
            if not accepted(r, t):
                s["false_rejection"] += 1
                continue
            s["correct_accept"] += 1
            s["accepted_with_missing_evidence"] += not evidence_complete(r, t)
            s["accepted_with_missing_section"] += sections_in_context(r, t) < len(r["expected"])
        else:
            s["false_acceptance" if accepted(r, t) else "correct_refusal"] += 1
    return s


def errors(results, t):
    s = score(results, t)
    return s["false_rejection"] + s["false_acceptance"]


def zero_error_range(results, lo=0.30, hi=1.40):
    grid = [round(lo + i / 100, 2) for i in range(int((hi - lo) * 100) + 1)]
    ok = [t for t in grid if errors(results, t) == 0]
    return (min(ok), max(ok)) if ok else None


def best_threshold(results):
    grid = [round(0.40 + i / 100, 2) for i in range(91)]
    errs = {t: errors(results, t) for t in grid}
    best = min(errs.values())
    return statistics.median([t for t in grid if errs[t] == best])      # middle of the best plateau


def leave_one_out(results):
    """Pick a threshold on 14 questions, test it on the 15th. A rough guard against reading too much into one cut-off."""
    held = []
    for i, r in enumerate(results):
        t = best_threshold(results[:i] + results[i + 1:])
        held.append({"id": r["id"], "chosen_threshold": t, "error": errors([r], t)})
    return held


COVERAGE_KS = [3, 4, 6, 8, 10]


def k_coverage(results, k):
    """Complex questions whose expected sections ALL rank within the top k (no threshold)."""
    cx = [r for r in results if r["category"] == "complex"]
    return sum(all(e["rank"] is not None and e["rank"] <= k for e in r["expected"]) for r in cx), len(cx)


def rate(num, den):
    return f"{num}/{den} ({num / den:.0%})" if den else "n/a"


def retrieval_summary(results):
    out = {}
    groups = {"direct": [r for r in results if r["category"] == "direct"],
              "complex": [r for r in results if r["category"] == "complex"]}
    groups["all answerable"] = groups["direct"] + groups["complex"]
    for name, rs in groups.items():
        out[name] = {"n": len(rs), "top1": sum(r["top1_hit"] for r in rs), "top3": sum(r["top3_hit"] for r in rs),
                     "all_top3": sum(r["all_expected_in_top3"] for r in rs),
                     "all_context": sum(r["all_expected_in_context"] for r in rs),
                     "evidence_top3": sum(r["evidence_in_top3"] for r in rs)}
    return out


# ---------------------------------------------------------------- report
def _status(e, t):
    if e["rank"] is None:
        return "not in index"
    if e["rank"] <= CONTEXT_K:
        return "in context" if e["distance"] <= t else f"retrieved (#{e['rank']}) but over threshold"
    return f"ranked #{e['rank']}, outside top-{CONTEXT_K}"


def render_report(results, notes=""):
    summ, sw = retrieval_summary(results), [score(results, t) for t in SWEEP]
    ans = [r for r in results if r["answerable"]]
    un = [r for r in results if not r["answerable"]]
    top1 = lambda r: r["ranking"][0]["distance"]
    zr, loo = zero_error_range(results), leave_one_out(results)
    L = []
    w = L.append
    w("# Hoomi retrieval evaluation\n")
    w("Scope: **retrieval only** (local FastEmbed `BAAI/bge-small-en-v1.5` + Chroma, 15 chunks from 3 synthetic documents). "
      "No LLM was used, so this says **nothing about generated-answer accuracy**. Distances are Chroma's L2 distance for this "
      "model (smaller = closer), not a 0-1 score. Questions: `eval/questions.json`. Raw data: `eval/results.json`.\n")

    w("## 1. Retrieval quality (independent of any threshold)\n")
    w("| Group | Questions | Top-1 hit | Top-3 hit | ALL expected sections in top-3 | ALL expected in top-4 context | Required evidence in top-3 |")
    w("|---|---|---|---|---|---|---|")
    for name, g in summ.items():
        w(f"| {name} | {g['n']} | {rate(g['top1'], g['n'])} | {rate(g['top3'], g['n'])} | {rate(g['all_top3'], g['n'])} | "
          f"{rate(g['all_context'], g['n'])} | {rate(g['evidence_top3'], g['n'])} |")
    w("\n*Top-1 hit*: the closest chunk is one of the expected sections. *Top-3 hit*: at least one expected section is in the top 3. "
      "For complex questions, the *ALL* columns are the cross-document test: every expected section must be present.\n")

    w("## 2. Threshold comparison\n")
    w("A question is *accepted* when its closest chunk is within the threshold, otherwise *refused*. "
      f"Answerable: {len(ans)}, unanswerable: {len(un)}.\n")
    w("| Threshold | Correct accepts | **False rejections** | Correct refusals | **False acceptances** | Accepted but required evidence missing from context | Accepted but an expected section missing |")
    w("|---|---|---|---|---|---|---|")
    for s in sw:
        mark = " (provisional)" if s["threshold"] == PROVISIONAL else ""
        w(f"| {s['threshold']:.2f}{mark} | {s['correct_accept']}/{len(ans)} | {s['false_rejection']} | {s['correct_refusal']}/{len(un)} | "
          f"{s['false_acceptance']} | {s['accepted_with_missing_evidence']} | {s['accepted_with_missing_section']} |")
    w("\n*False rejection* = an answerable question refused (Hoomi would wrongly say it lacks evidence). "
      "*False acceptance* = an unanswerable question accepted (the model would be given irrelevant context and could hallucinate).\n")

    w("### Separation and robustness\n")
    a_d, u_d = sorted(top1(r) for r in ans), sorted(top1(r) for r in un)
    w(f"- Closest-chunk distance, **answerable** questions: min {a_d[0]:.3f}, median {statistics.median(a_d):.3f}, max {a_d[-1]:.3f}.")
    w(f"- Closest-chunk distance, **unanswerable** questions: min {u_d[0]:.3f}, median {statistics.median(u_d):.3f}, max {u_d[-1]:.3f}.")
    if a_d[-1] < u_d[0]:
        w(f"- The groups are separable: gap between worst answerable ({a_d[-1]:.3f}) and best unanswerable ({u_d[0]:.3f}) is {u_d[0] - a_d[-1]:.3f}.")
    else:
        w(f"- The groups **overlap**: worst answerable ({a_d[-1]:.3f}) is farther than best unanswerable ({u_d[0]:.3f}); no single threshold is error-free.")
    w(f"- Thresholds with zero errors on this set: {f'{zr[0]:.2f} to {zr[1]:.2f}' if zr else 'none'}"
      f"{f' (width {zr[1] - zr[0]:.2f})' if zr else ''}.")
    bad = [h for h in loo if h["error"]]
    w(f"- Leave-one-out (choose a threshold on 14 questions, test on the held-out one): {len(loo)-len(bad)}/{len(loo)} correct"
      f"{'; errors on ' + ', '.join(h['id'] for h in bad) if bad else ''}. Chosen thresholds ranged "
      f"{min(h['chosen_threshold'] for h in loo):.2f} to {max(h['chosen_threshold'] for h in loo):.2f}.")
    w("- With only 15 questions (4 unanswerable) and a 15-chunk corpus, any threshold read off this table is a hypothesis, "
      "not a calibrated setting. A larger corpus will raise the distances of unrelated questions and reduce the margin.\n")

    w("## 3. Question-level results\n")
    w(f"Decision shown for the provisional threshold {PROVISIONAL:.2f}.\n")
    w("| ID | Type | Top-1 chunk (distance) | Top-1 hit | Top-3 hit | Decision @0.70 | Outcome |")
    w("|---|---|---|---|---|---|---|")
    for r in results:
        h = r["ranking"][0]
        acc = accepted(r, PROVISIONAL)
        outcome = ("correct accept" if acc else "FALSE REJECTION") if r["answerable"] else ("FALSE ACCEPTANCE" if acc else "correct refusal")
        w(f"| {r['id']} | {r['category']} | {h['source']} › {h['section']} ({h['distance']:.3f}) | "
          f"{'yes' if r['top1_hit'] else ('no' if r['answerable'] else '-')} | {'yes' if r['top3_hit'] else ('no' if r['answerable'] else '-')} | "
          f"{'accept' if acc else 'refuse'} | {outcome} |")
    w("")
    for r in results:
        w(f"### {r['id']} ({r['category']}): {r['question']}\n")
        if r["answerable"]:
            w("- Expected: " + "; ".join(f"`{e['source']} › {e['section']}` (rank {e['rank']}, distance {e['distance']})" for e in r["expected"]))
            w("- Required evidence: " + "; ".join(f"“{p}”" for p in r["required_evidence"]))
        else:
            w("- Expected: **no supporting evidence in the corpus** (should be refused).")
        w("- Actual top-3: " + "; ".join(f"#{h['rank']} `{h['source']} › {h['section']}` {h['distance']:.3f}" for h in r["ranking"][:3]))
        acc = accepted(r, PROVISIONAL)
        line = f"- Threshold {PROVISIONAL:.2f}: **{'accept' if acc else 'refuse'}** (closest {r['ranking'][0]['distance']:.3f}, {len(context_at(r, PROVISIONAL))} of {CONTEXT_K} context chunks kept)"
        if r["answerable"] and acc:
            line += f"; required evidence {'complete' if evidence_complete(r, PROVISIONAL) else '**incomplete**'} in kept context"
        w(line)
        if r.get("notes"):
            w(f"- Design note: {r['notes']}")
        w("")

    w("## 4. Cross-document questions: where the second document went\n")
    w(f"For each expected section: its rank among all 15 chunks, its distance, and its status at {PROVISIONAL:.2f} with a top-{CONTEXT_K} context.\n")
    w("| ID | Expected section | Rank | Distance | Status @0.70 |")
    w("|---|---|---|---|---|")
    for r in (r for r in results if r["category"] == "complex"):
        for e in r["expected"]:
            w(f"| {r['id']} | {e['source']} › {e['section']} | {e['rank']} | {e['distance']} | {_status(e, PROVISIONAL)} |")
    w("")
    w("### How many chunks are needed to cover every expected section?\n")
    w("Ignoring the threshold: complex questions whose expected sections ALL rank within the top-k of the 15 chunks.\n")
    w("| Top-k | " + " | ".join(str(k) for k in COVERAGE_KS) + " |")
    w("|---|" + "---|" * len(COVERAGE_KS))
    w("| Complex questions fully covered | " + " | ".join(rate(*k_coverage(results, k)) for k in COVERAGE_KS) + " |")
    w("\nA bigger k recovers more of the second document but passes more unrelated text to the model; with only 15 chunks, "
      "k=10 is two-thirds of the whole index, so this table shows the ranking is weak, not that k=10 is a good setting.\n")
    if notes.strip():
        w("## 5. Analysis\n")
        w(notes.strip() + "\n")
    w("## Limitations\n")
    w("- 15 questions written by the same author as the corpus: wording overlaps the documents more than real users' will.")
    w("- A 15-chunk synthetic corpus is far easier than a real library; expect lower hit rates and tighter margins at scale.")
    w("- Hit rates use section-level expectations; a near-duplicate section elsewhere can be a legitimate answer yet count as a miss.")
    w("- Retrieval only. Whether a model writes a correct, faithful, well-cited answer from this context is **not measured here**.")
    return "\n".join(L) + "\n"


def main():
    from rag.embeddings import FastEmbedEmbeddings
    from rag.retriever import get_store
    store = get_store(FastEmbedEmbeddings())          # cached model, downloads blocked; opens the existing index only
    questions = load_questions()
    results = run(store, questions)
    for r, q in zip(results, questions):
        r["notes"] = q.get("notes", "")
    EVAL_DIR.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    notes = NOTES.read_text(encoding="utf-8") if NOTES.exists() else ""
    REPORT.write_text(render_report(results, notes), encoding="utf-8")
    summ = retrieval_summary(results)
    print("chunks in index:", store._collection.count())
    for name, g in summ.items():
        print(f"{name:15} n={g['n']:2} top1={g['top1']} top3={g['top3']} all_top3={g['all_top3']} all_ctx={g['all_context']} evid_top3={g['evidence_top3']}")
    print("complex fully covered at top-k:", {k: k_coverage(results, k)[0] for k in COVERAGE_KS})
    for t in SWEEP:
        s = score(results, t)
        print(f"t={t:.2f} accept={s['correct_accept']} FR={s['false_rejection']} refuse={s['correct_refusal']} FA={s['false_acceptance']} "
              f"missing_evid={s['accepted_with_missing_evidence']} missing_sec={s['accepted_with_missing_section']}")
    print("report:", REPORT)


if __name__ == "__main__":
    main()
