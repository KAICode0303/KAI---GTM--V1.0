"""Offline tests for the retrieval-evaluation machinery (rag/evaluate.py). No network, no model, no LLM.

These check the question file and the scoring logic. They do NOT assert real-model retrieval quality: that is what
`python -m rag.evaluate` measures and what eval/report.md records.
"""
import json
from collections import Counter

import pytest

from rag import evaluate as ev
from rag import ingest, retriever
from rag.answer import ContextPolicy
from test_rag import HashingEmbeddings


@pytest.fixture(scope="module")
def chunks():
    return ingest.chunk_documents(ingest.load_documents())


@pytest.fixture(scope="module")
def questions():
    return ev.load_questions()


# ---------------------------------------------------------------- the question set itself
def test_question_mix_and_ids(questions):
    assert len(questions) == 15
    assert Counter(q["category"] for q in questions) == {"direct": 6, "complex": 5, "unanswerable": 4}
    assert len({q["id"] for q in questions}) == 15
    for q in questions:
        assert q["answerable"] == (q["category"] != "unanswerable")
        assert q["question"].strip().endswith("?")


def test_expected_sections_and_evidence_exist_in_the_corpus(questions, chunks):
    text_of = {}
    for c in chunks:
        text_of.setdefault((c.metadata["source"], c.metadata["section"]), []).append(c.page_content)
    for q in questions:
        if not q["answerable"]:
            assert q["expected"] == [] and q["required_evidence"] == []
            continue
        assert q["expected"] and q["required_evidence"]
        for e in q["expected"]:
            assert (e["source"], e["section"]) in text_of, f"{q['id']}: unknown section {e}"
        expected_text = ev.norm(" ".join(t for e in q["expected"] for t in text_of[(e["source"], e["section"])]))
        for phrase in q["required_evidence"]:
            assert ev.norm(phrase) in expected_text, f"{q['id']}: evidence {phrase!r} not in its expected sections"


def test_complex_questions_span_two_documents(questions):
    for q in (q for q in questions if q["category"] == "complex"):
        assert len({e["source"] for e in q["expected"]}) >= 2, q["id"]


# ---------------------------------------------------------------- run + report with the toy embedding
@pytest.fixture(scope="module")
def results(tmp_path_factory, chunks, questions):
    store = retriever.get_store(HashingEmbeddings(), persist_dir=tmp_path_factory.mktemp("c") / "chroma")
    retriever.build_index(store, chunks)
    return ev.run(store, questions)


def test_run_ranks_every_chunk_for_every_question(results, chunks):
    assert len(results) == 15
    for r in results:
        d = [h["distance"] for h in r["ranking"]]
        assert len(d) == len(chunks) and d == sorted(d)
        assert [h["rank"] for h in r["ranking"]] == list(range(1, len(chunks) + 1))
        for e in r["expected"]:
            assert e["rank"] is not None                      # every expected section was found in the index
    assert not any(r["top1_hit"] for r in results if not r["answerable"])


def test_report_renders_and_does_not_claim_answer_accuracy(results):
    report = ev.render_report(results, notes="hand-written note")
    for heading in ["## 1. Retrieval quality", "## 2. Gate comparison", "## 3. Question-level results",
                    "## 4. Cross-document", "## 5. Analysis", "## Limitations"]:
        assert heading in report
    assert "hand-written note" in report and "nothing about generated-answer accuracy" in report
    assert all(f"### {r['id']} " in report for r in results)


def test_saved_results_match_the_question_file(questions):
    if ev.RESULTS.exists():
        assert [r["id"] for r in json.loads(ev.RESULTS.read_text())] == [q["id"] for q in questions]


# ---------------------------------------------------------------- scoring logic on hand-built results
def fake(qid, answerable, dists, texts=None, expected=()):
    texts = texts or [""] * len(dists)
    ranking = [{"rank": i, "source": "a.md", "section": f"s{i}", "distance": d, "text": texts[i - 1]}
               for i, d in enumerate(dists, 1)]
    exp = [{"source": "a.md", "section": f"s{i}", "rank": i, "distance": dists[i - 1]} for i in expected]
    return {"id": qid, "category": "direct" if answerable else "unanswerable", "answerable": answerable, "ranking": ranking,
            "expected": exp, "required_evidence": ["gold"] if answerable else []}


def test_score_counts_each_outcome():
    rs = [fake("A", True, [0.5, 0.9]),        # accepted at 0.7
          fake("B", True, [0.8, 0.9]),        # false rejection at 0.7
          fake("C", False, [0.9, 1.0]),       # correct refusal
          fake("D", False, [0.6, 0.9])]       # false acceptance
    s = ev.score(rs, 0.7)
    assert (s["correct_accept"], s["false_rejection"], s["correct_refusal"], s["false_acceptance"]) == (1, 1, 1, 1)
    s2 = ev.score(rs, 0.85)
    assert (s2["correct_accept"], s2["false_rejection"], s2["correct_refusal"], s2["false_acceptance"]) == (2, 0, 1, 1)
    assert ev.errors(rs, 0.7) == 2


def test_context_is_limited_to_k_and_threshold_and_evidence_is_checked():
    r = fake("E", True, [0.5, 0.6, 0.65, 0.68, 0.69], ["x", "x", "x", "x", "GOLD in fifth chunk"], expected=[1, 5])
    assert len(ev.context_at(r, 0.7)) == ev.CONTEXT_K == 4           # 5th chunk is within threshold but beyond k
    assert not ev.evidence_complete(r, 0.7)
    assert ev.sections_in_context(r, 0.7) == 1
    r2 = fake("F", True, [0.5, 0.9], ["has Gold standard text", ""], expected=[1])
    assert ev.evidence_complete(r2, 0.7) and ev.sections_in_context(r2, 0.7) == 1
    assert ev.score([r2], 0.4)["false_rejection"] == 1


def test_accepted_with_missing_evidence_is_counted():
    r = fake("G", True, [0.5, 0.8], ["nothing", "gold"], expected=[1, 2])
    assert ev.score([r], 0.7)["accepted_with_missing_evidence"] == 1
    assert ev.score([r], 0.9)["accepted_with_missing_evidence"] == 0


def test_zero_error_range_and_overlap_detection():
    separable = [fake("A", True, [0.5]), fake("B", True, [0.6]), fake("C", False, [0.9])]
    lo, hi = ev.zero_error_range(separable)
    assert 0.6 <= lo <= 0.61 and 0.89 <= hi <= 0.9
    overlapping = separable + [fake("D", False, [0.45])]
    assert ev.zero_error_range(overlapping) is None


def test_leave_one_out_reports_one_row_per_question():
    rs = [fake(f"A{i}", True, [0.5 + i / 100]) for i in range(5)] + [fake(f"U{i}", False, [0.9 + i / 100]) for i in range(3)]
    held = ev.leave_one_out(rs)
    assert [h["id"] for h in held] == [r["id"] for r in rs] and all(h["error"] == 0 for h in held)


def test_k_coverage_counts_complex_questions_fully_covered():
    r1 = fake("C1", True, [0.5, 0.6, 0.7], expected=[1, 3])
    r2 = fake("C2", True, [0.5, 0.6, 0.7], expected=[1, 2])
    r1["category"] = r2["category"] = "complex"
    assert ev.k_coverage([r1, r2], 2) == (1, 2) and ev.k_coverage([r1, r2], 3) == (2, 2)


# ---------------------------------------------------------------- gate vs context in the scoring, and the comparison
def test_context_at_old_rule_vs_new_policy():
    r = fake("H", True, [0.5, 0.9, 0.95, 1.0], ["a", "b", "gold", "d"], expected=[1, 3])
    assert len(ev.context_at(r, 0.7)) == 1                                   # old rule: only chunks within the gate
    assert [h["rank"] for h in ev.context_at(r, 0.7, ContextPolicy(k=3))] == [1, 2, 3]
    assert ev.context_at(r, 0.4, ContextPolicy(k=3)) == []                   # failed gate: nothing is given
    assert not ev.evidence_complete(r, 0.7) and ev.evidence_complete(r, 0.7, ContextPolicy(k=3))
    assert ev.sections_in_context(r, 0.7) == 1 and ev.sections_in_context(r, 0.7, ContextPolicy(k=3)) == 2


def test_score_with_policy_changes_evidence_but_not_gate_outcomes():
    rs = [fake("A", True, [0.5, 0.9, 0.95], ["x", "y", "gold"], expected=[1, 3]), fake("U", False, [0.9, 1.0])]
    old, new = ev.score(rs, 0.7), ev.score(rs, 0.7, ContextPolicy(k=3))
    for k in ("correct_accept", "false_rejection", "correct_refusal", "false_acceptance"):
        assert old[k] == new[k]
    assert (old["evidence_complete"], new["evidence_complete"]) == (0, 1)
    assert (old["context_chunks"], new["context_chunks"]) == (1, 3)


def test_verdict_improved_regressed_same():
    st = lambda acc, complete, top1: {"accepted": acc, "complete": complete, "top1": top1}
    ans_q, un_q = {"answerable": True}, {"answerable": False}
    assert ev.verdict(ans_q, st(True, False, False), st(True, True, False)) == "improved"
    assert ev.verdict(ans_q, st(True, True, True), st(True, False, True)) == "regressed"
    assert ev.verdict(ans_q, st(True, True, True), st(True, True, True)) == "same"
    assert ev.verdict(ans_q, st(True, True, True), st(False, False, True)) == "regressed"       # new false rejection
    assert ev.verdict(un_q, st(False, False, False), st(True, False, False)) == "regressed"     # new false acceptance
    assert ev.verdict(un_q, st(True, False, False), st(False, False, False)) == "improved"


def test_report_with_baseline_has_comparison_and_policy_grid(results):
    baseline = [dict(r) for r in results]
    report = ev.render_report(results, baseline=baseline, policy=ContextPolicy(k=6))
    assert "## Comparison with the baseline" in report and "Question-level changes, A → C" in report
    for label in ("A. Baseline", "B. Old embedding", "D. New embedding", "C. New embedding"):
        assert label in report
    assert "Context-selection policies" in report and "top-6" in report
    assert "Improved (0)" in report and "Regressed (0)" in report                  # identical runs: nothing changes
    assert "## Comparison with the baseline" not in ev.render_report(results, policy=ContextPolicy(k=6))


def test_questions_file_is_unchanged_by_this_work(questions):
    import hashlib
    # fingerprint of eval/questions.json as committed in the evaluation checkpoint: the questions must not be edited
    # to improve scores. If you intentionally add questions, update this fingerprint and re-baseline.
    assert hashlib.md5(ev.QUESTIONS.read_bytes()).hexdigest() == "c2eb015f3b3d6c0b190ce73da3010d1f"
