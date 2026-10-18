"""Retrieval evaluation: does the right chunk come back, and do the answerability gate and context selection behave?

Measures RETRIEVAL only. No LLM is involved, so nothing here says anything about generated-answer accuracy.
Read-only on the index; uses the cached FastEmbed model (downloads blocked) and local Chroma.

Two decisions are scored separately (see rag/answer.py):
  * the answerability GATE: accept when the closest chunk is within a distance, otherwise refuse;
  * CONTEXT SELECTION: which chunks the model would see, given a ContextPolicy. `policy=None` reproduces the earlier
    single-threshold rule (top-4 chunks, each within the gate distance) so old and new runs can be compared.

Run:  HF_HUB_OFFLINE=1 .venv312/bin/python -m rag.evaluate
Writes: eval/results.json (raw, per question) and eval/report.md (readable; appends eval/analysis_notes.md if present).
If eval/results_baseline.json exists, the report also compares against it.
"""
import json
import re
import statistics
from pathlib import Path

from rag.answer import ContextPolicy, resolve_context_policy, select_indices
from rag.retriever import retrieve

ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = ROOT / "eval"
QUESTIONS = EVAL_DIR / "questions.json"
RESULTS = EVAL_DIR / "results.json"
BASELINE = EVAL_DIR / "results_baseline.json"
REPORT = EVAL_DIR / "report.md"
NOTES = EVAL_DIR / "analysis_notes.md"

CONTEXT_K = 4                      # context size of the earlier rule (and the "top-4" ranking metrics)
PROVISIONAL = 0.70                 # the provisional gate distance being examined, not a recommendation
SWEEP = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]
COVERAGE_KS = [3, 4, 6, 8, 10]
POLICY_GRID = [ContextPolicy(k=4), ContextPolicy(k=6), ContextPolicy(k=8),
               ContextPolicy(k=6, relative_margin=0.15), ContextPolicy(k=6, relative_margin=0.25),
               ContextPolicy(k=8, relative_margin=0.25)]


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


# ---------------------------------------------------------------- gate and context scoring
def accepted(r, t):
    """The answerability gate: closest chunk within distance t."""
    return r["ranking"][0]["distance"] <= t


def context_at(r, t, policy=None):
    """Chunks the model would see. policy=None: the earlier rule (top-4, each within t)."""
    if policy is None:
        return [h for h in r["ranking"][:CONTEXT_K] if h["distance"] <= t]
    if not accepted(r, t):
        return []
    return [r["ranking"][i] for i in select_indices([h["distance"] for h in r["ranking"]], policy)]


def evidence_complete(r, t, policy=None):
    text = norm(" ".join(h["text"] for h in context_at(r, t, policy)))
    return all(norm(p) in text for p in r["required_evidence"])


def sections_in_context(r, t, policy=None):
    keys = {key(h) for h in context_at(r, t, policy)}
    return sum((e["source"], e["section"]) in keys for e in r["expected"])


def score(results, t, policy=None):
    s = {"threshold": t, "correct_accept": 0, "false_rejection": 0, "correct_refusal": 0, "false_acceptance": 0,
         "accepted_with_missing_evidence": 0, "accepted_with_missing_section": 0,
         "evidence_complete": 0, "evidence_complete_complex": 0, "context_chunks": 0}
    for r in results:
        if r["answerable"]:
            if not accepted(r, t):
                s["false_rejection"] += 1
                continue
            s["correct_accept"] += 1
            complete = evidence_complete(r, t, policy)
            s["evidence_complete"] += complete
            s["evidence_complete_complex"] += complete and r["category"] == "complex"
            s["accepted_with_missing_evidence"] += not complete
            s["accepted_with_missing_section"] += sections_in_context(r, t, policy) < len(r["expected"])
            s["context_chunks"] += len(context_at(r, t, policy))
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
    """Pick a gate distance on 14 questions, test it on the 15th. A rough guard against over-reading one cut-off."""
    held = []
    for i, r in enumerate(results):
        t = best_threshold(results[:i] + results[i + 1:])
        held.append({"id": r["id"], "chosen_threshold": t, "error": errors([r], t)})
    return held


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


# ---------------------------------------------------------------- baseline comparison
def variant_row(label, results, t, policy):
    summ, s = retrieval_summary(results)["all answerable"], score(results, t, policy)
    n_ans = summ["n"]
    n_un = sum(not r["answerable"] for r in results)
    avg_ctx = s["context_chunks"] / s["correct_accept"] if s["correct_accept"] else 0
    return (f"| {label} | {rate(summ['top1'], n_ans)} | {rate(summ['top3'], n_ans)} | {rate(summ['all_top3'], n_ans)} | "
            f"{rate(s['evidence_complete'], n_ans)} | {s['evidence_complete_complex']}/5 | {s['false_rejection']} | "
            f"{s['correct_refusal']}/{n_un} | {s['false_acceptance']} | {avg_ctx:.1f} |")


def q_state(r, t, policy):
    acc = accepted(r, t)
    return {"accepted": acc, "top1": r["top1_hit"], "top1_distance": r["ranking"][0]["distance"],
            "complete": acc and r["answerable"] and evidence_complete(r, t, policy),
            "ctx": len(context_at(r, t, policy))}


def verdict(r, before, after):
    """improved / regressed / same, judged on what matters for the question type."""
    if r["answerable"]:
        b = (before["accepted"], before["complete"], before["top1"])
        a = (after["accepted"], after["complete"], after["top1"])
    else:
        b, a = (not before["accepted"],), (not after["accepted"],)
    return "improved" if a > b else "regressed" if a < b else "same"


def render_comparison(results, baseline, policy):
    t = PROVISIONAL
    by_id = {r["id"]: r for r in baseline}
    L = []
    w = L.append
    w("## Comparison with the baseline (same 15 questions, unchanged)\n")
    w("Two changes were made: (1) each chunk is now *embedded* with its document title and section heading in front "
      "(the stored text and citations are unchanged); (2) the answerability gate is separated from context selection. "
      f"Gate distance is {t:.2f} in every row. *Old rule* = top-4 chunks each within {t:.2f}; "
      f"*new policy* = {policy.describe()}.\n")
    w("| Variant | Top-1 hit | Top-3 hit | All expected in top-3 | Required evidence complete in context | ...of which complex | False rejections | Correct refusals | False acceptances | Avg chunks given |")
    w("|---|---|---|---|---|---|---|---|---|---|")
    w(variant_row("A. Baseline: old embedding, old rule", baseline, t, None))
    w(variant_row("B. Old embedding, new policy", baseline, t, policy))
    w(variant_row("D. New embedding, old rule", results, t, None))
    w(variant_row("**C. New embedding, new policy (current)**", results, t, policy))
    w("\n*Top-1, top-3 and all-expected-in-top-3 depend only on the embedding, so A = B and C = D on those columns. "
      "Required evidence complete = every required phrase appears in the context given to the model (refused questions count as not complete). "
      "Avg chunks given = mean context size over accepted answerable questions: a rough proxy for how much unrelated text the model must read.*\n")

    w("### Question-level changes, A → C\n")
    w("| ID | Type | Top-1 distance | Top-1 hit | Gate @0.70 | Evidence complete | Chunks given | Verdict |")
    w("|---|---|---|---|---|---|---|---|")
    tally = {"improved": [], "regressed": [], "same": []}
    yn = lambda x: "yes" if x else "no"
    gate = lambda s: "accept" if s["accepted"] else "refuse"
    for r in results:
        b, a = q_state(by_id[r["id"]], t, None), q_state(r, t, policy)
        v = verdict(r, b, a)
        tally[v].append(r["id"])
        top1_cell = f"{yn(b['top1'])} → {yn(a['top1'])}" if r["answerable"] else "-"
        comp = f"{yn(b['complete'])} → {yn(a['complete'])}" if r["answerable"] else "-"
        w(f"| {r['id']} | {r['category']} | {b['top1_distance']:.3f} → {a['top1_distance']:.3f} | {top1_cell} | "
          f"{gate(b)} → {gate(a)} | {comp} | {b['ctx']} → {a['ctx']} | **{v}** |")
    w(f"\n**Improved ({len(tally['improved'])}):** {', '.join(tally['improved']) or 'none'}. "
      f"**Regressed ({len(tally['regressed'])}):** {', '.join(tally['regressed']) or 'none'}. "
      f"**Unchanged ({len(tally['same'])}):** {', '.join(tally['same']) or 'none'}.\n")
    return "\n".join(L) + "\n"


def render_policy_grid(results, gate=PROVISIONAL):
    n_ans = sum(r["answerable"] for r in results)
    L = []
    w = L.append
    w("### Context-selection policies (gate fixed at 0.70)\n")
    w("| Policy | Evidence complete | ...complex | Accepted but a section missing | Avg chunks given |")
    w("|---|---|---|---|---|")
    for label, pol in [("Old rule (top-4, each within gate)", None)] + [(p.describe(), p) for p in POLICY_GRID]:
        s = score(results, gate, pol)
        avg = s["context_chunks"] / s["correct_accept"] if s["correct_accept"] else 0
        w(f"| {label} | {rate(s['evidence_complete'], n_ans)} | {s['evidence_complete_complex']}/5 | {s['accepted_with_missing_section']} | {avg:.1f} |")
    w("\nThese are descriptive. The gate does not change with the policy (refusals are identical in every row); only what the model sees does. "
      "The default is not tuned to this table: a larger k trades completeness for more irrelevant text.\n")
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- report
def _status(e, t, policy):
    if e["rank"] is None:
        return "not in index"
    return "in context" if e["rank"] <= policy.k else f"ranked #{e['rank']}, outside top-{policy.k}"


def render_report(results, notes="", baseline=None, policy=None):
    policy = policy or resolve_context_policy()
    t0 = PROVISIONAL
    summ, sw = retrieval_summary(results), [score(results, t, policy) for t in SWEEP]
    ans = [r for r in results if r["answerable"]]
    un = [r for r in results if not r["answerable"]]
    top1 = lambda r: r["ranking"][0]["distance"]
    zr, loo = zero_error_range(results), leave_one_out(results)
    L = []
    w = L.append
    w("# Hoomi retrieval evaluation\n")
    w("Scope: **retrieval only** (local FastEmbed `BAAI/bge-small-en-v1.5` + Chroma, 15 chunks from 3 synthetic documents). "
      "No LLM was used, so this says **nothing about generated-answer accuracy**. Distances are Chroma's L2 distance for this "
      "model (smaller = closer), not a 0-1 score. Questions: `eval/questions.json` (unchanged). Raw data: `eval/results.json`. "
      f"Context policy used below: **{policy.describe()}**.\n")
    if baseline:
        w(render_comparison(results, baseline, policy))

    w("## 1. Retrieval quality (independent of any threshold)\n")
    w("| Group | Questions | Top-1 hit | Top-3 hit | ALL expected sections in top-3 | ALL expected in top-4 | Required evidence in top-3 |")
    w("|---|---|---|---|---|---|---|")
    for name, g in summ.items():
        w(f"| {name} | {g['n']} | {rate(g['top1'], g['n'])} | {rate(g['top3'], g['n'])} | {rate(g['all_top3'], g['n'])} | "
          f"{rate(g['all_context'], g['n'])} | {rate(g['evidence_top3'], g['n'])} |")
    w("\n*Top-1 hit*: the closest chunk is one of the expected sections. *Top-3 hit*: at least one expected section is in the top 3. "
      "For complex questions, the *ALL* columns are the cross-document test: every expected section must be present.\n")

    w("## 2. Gate comparison\n")
    w("The *gate* accepts a question when its closest chunk is within the distance, otherwise refuses. "
      f"Context selection then follows the policy ({policy.describe()}) and no longer depends on the gate distance. "
      f"Answerable: {len(ans)}, unanswerable: {len(un)}.\n")
    w("| Gate distance | Correct accepts | **False rejections** | Correct refusals | **False acceptances** | Evidence complete in context | Accepted but required evidence missing | Accepted but an expected section missing |")
    w("|---|---|---|---|---|---|---|---|")
    for s in sw:
        mark = " (provisional)" if s["threshold"] == t0 else ""
        w(f"| {s['threshold']:.2f}{mark} | {s['correct_accept']}/{len(ans)} | {s['false_rejection']} | {s['correct_refusal']}/{len(un)} | "
          f"{s['false_acceptance']} | {s['evidence_complete']}/{len(ans)} | {s['accepted_with_missing_evidence']} | {s['accepted_with_missing_section']} |")
    w("\n*False rejection* = an answerable question refused (Hoomi would wrongly say it lacks evidence). "
      "*False acceptance* = an unanswerable question accepted (the model would be given irrelevant context and could hallucinate).\n")
    w(render_policy_grid(results))

    w("### Separation and robustness\n")
    a_d, u_d = sorted(top1(r) for r in ans), sorted(top1(r) for r in un)
    w(f"- Closest-chunk distance, **answerable** questions: min {a_d[0]:.3f}, median {statistics.median(a_d):.3f}, max {a_d[-1]:.3f}.")
    w(f"- Closest-chunk distance, **unanswerable** questions: min {u_d[0]:.3f}, median {statistics.median(u_d):.3f}, max {u_d[-1]:.3f}.")
    if a_d[-1] < u_d[0]:
        w(f"- The groups are separable: gap between worst answerable ({a_d[-1]:.3f}) and best unanswerable ({u_d[0]:.3f}) is {u_d[0] - a_d[-1]:.3f}.")
    else:
        w(f"- The groups **overlap**: worst answerable ({a_d[-1]:.3f}) is farther than best unanswerable ({u_d[0]:.3f}); no single gate distance is error-free.")
    w(f"- Gate distances with zero errors on this set: {f'{zr[0]:.2f} to {zr[1]:.2f}' if zr else 'none'}"
      f"{f' (width {zr[1] - zr[0]:.2f})' if zr else ''}.")
    bad = [h for h in loo if h["error"]]
    w(f"- Leave-one-out (choose a gate distance on 14 questions, test on the held-out one): {len(loo)-len(bad)}/{len(loo)} correct"
      f"{'; errors on ' + ', '.join(h['id'] for h in bad) if bad else ''}. Chosen distances ranged "
      f"{min(h['chosen_threshold'] for h in loo):.2f} to {max(h['chosen_threshold'] for h in loo):.2f}.")
    w("- With only 15 questions (4 unanswerable) and a 15-chunk corpus, any distance read off this table is a hypothesis, "
      "not a calibrated setting. A larger corpus will raise the distances of unrelated questions and reduce the margin.\n")

    w("## 3. Question-level results\n")
    w(f"Gate {t0:.2f}; context policy {policy.describe()}.\n")
    w("| ID | Type | Top-1 chunk (distance) | Top-1 hit | Top-3 hit | Gate @0.70 | Evidence complete | Outcome |")
    w("|---|---|---|---|---|---|---|---|")
    for r in results:
        h = r["ranking"][0]
        acc = accepted(r, t0)
        outcome = ("correct accept" if acc else "FALSE REJECTION") if r["answerable"] else ("FALSE ACCEPTANCE" if acc else "correct refusal")
        comp = ("yes" if evidence_complete(r, t0, policy) else "no") if r["answerable"] and acc else "-"
        w(f"| {r['id']} | {r['category']} | {h['source']} › {h['section']} ({h['distance']:.3f}) | "
          f"{'yes' if r['top1_hit'] else ('no' if r['answerable'] else '-')} | {'yes' if r['top3_hit'] else ('no' if r['answerable'] else '-')} | "
          f"{'accept' if acc else 'refuse'} | {comp} | {outcome} |")
    w("")
    for r in results:
        w(f"### {r['id']} ({r['category']}): {r['question']}\n")
        if r["answerable"]:
            w("- Expected: " + "; ".join(f"`{e['source']} › {e['section']}` (rank {e['rank']}, distance {e['distance']})" for e in r["expected"]))
            w("- Required evidence: " + "; ".join(f"“{p}”" for p in r["required_evidence"]))
        else:
            w("- Expected: **no supporting evidence in the corpus** (should be refused).")
        w("- Actual top-3: " + "; ".join(f"#{h['rank']} `{h['source']} › {h['section']}` {h['distance']:.3f}" for h in r["ranking"][:3]))
        acc = accepted(r, t0)
        line = (f"- Gate {t0:.2f}: **{'accept' if acc else 'refuse'}** (closest {r['ranking'][0]['distance']:.3f}); "
                f"{len(context_at(r, t0, policy))} chunk(s) given to the model")
        if r["answerable"] and acc:
            line += f"; required evidence {'complete' if evidence_complete(r, t0, policy) else '**incomplete**'} in that context"
        w(line)
        if r.get("notes"):
            w(f"- Design note: {r['notes']}")
        w("")

    w("## 4. Cross-document questions: where the second document went\n")
    w(f"For each expected section: its rank among all 15 chunks, its distance, and whether the current policy ({policy.describe()}) includes it.\n")
    w("| ID | Expected section | Rank | Distance | Status |")
    w("|---|---|---|---|---|")
    for r in (r for r in results if r["category"] == "complex"):
        for e in r["expected"]:
            w(f"| {r['id']} | {e['source']} › {e['section']} | {e['rank']} | {e['distance']} | {_status(e, t0, policy)} |")
    w("")
    w("### How many chunks are needed to cover every expected section?\n")
    w("Ignoring any threshold: complex questions whose expected sections ALL rank within the top-k of the 15 chunks.\n")
    w("| Top-k | " + " | ".join(str(k) for k in COVERAGE_KS) + " |")
    w("|---|" + "---|" * len(COVERAGE_KS))
    w("| Complex questions fully covered | " + " | ".join(rate(*k_coverage(results, k)) for k in COVERAGE_KS) + " |")
    w("\nA bigger k recovers more of the second document but passes more unrelated text to the model; with only 15 chunks, "
      "k=10 is two-thirds of the whole index, so this table shows how well the ranking works, not that k=10 is a good setting.\n")
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
    baseline = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else None
    policy = resolve_context_policy()
    EVAL_DIR.mkdir(exist_ok=True)
    RESULTS.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
    notes = NOTES.read_text(encoding="utf-8") if NOTES.exists() else ""
    REPORT.write_text(render_report(results, notes, baseline, policy), encoding="utf-8")
    summ = retrieval_summary(results)
    print("chunks in index:", store._collection.count(), "| context policy:", policy.describe())
    for name, g in summ.items():
        print(f"{name:15} n={g['n']:2} top1={g['top1']} top3={g['top3']} all_top3={g['all_top3']} evid_top3={g['evidence_top3']}")
    for label, res, pol in ([("A baseline", baseline, None), ("B old-emb/new-pol", baseline, policy)] if baseline else []) + \
                           [("D new-emb/old-rule", results, None), ("C new-emb/new-pol", results, policy)]:
        s = score(res, PROVISIONAL, pol)
        print(f"{label:18} FR={s['false_rejection']} refuse={s['correct_refusal']} FA={s['false_acceptance']} "
              f"evid_complete={s['evidence_complete']}/11 (complex {s['evidence_complete_complex']}/5)")
    print("report:", REPORT)


if __name__ == "__main__":
    main()
