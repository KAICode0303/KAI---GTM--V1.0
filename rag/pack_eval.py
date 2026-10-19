"""Evaluation of the Kai's Company knowledge pack (seven Markdown documents): direct, cross-document and unanswerable questions.

Two things are measured, and kept apart:
  OFFLINE  the real engine: local FastEmbed vectors, local Chroma, extractive answers. Fully real; no model, no network.
  HOSTED   the Fireworks pipeline's CODE (generate, verify, evidence check, citations) driven by MOCK models. This tests that the
           verifier rejects invented figures, fake quotes and fake citations. It says nothing about how a real model writes.
No paid or hosted call is ever made here.

Run:  HF_HUB_OFFLINE=1 .venv312/bin/python -m rag.pack_eval        Writes eval/pack_results.json and eval/pack_report.md
"""
import json
import re
from pathlib import Path

from gtm import numbers_qa
from rag import app_index, embeddings as emb, offline
from rag.verify import answer_verified

ROOT = Path(__file__).resolve().parent.parent
QUESTIONS = ROOT / "eval" / "pack_questions.json"
EVAL_INDEX = ROOT / ".rag_index" / "pack_eval_chroma"          # its own index: the evaluation never touches the app's index
RESULTS, REPORT = ROOT / "eval" / "pack_results.json", ROOT / "eval" / "pack_report.md"
_FOLD = lambda t: " ".join(t.replace("’", "'").lower().split())


def _passages(prompt):
    """[(chunk id, text)] parsed from the 'Passage id: X | source: ...' blocks the verified pipeline puts in its prompts."""
    parts = re.split(r"(?m)^Passage id: (\S+) \|[^\n]*\n", prompt)
    return [(parts[i], parts[i + 1].split("\n\n")[0].strip()) for i in range(1, len(parts) - 1, 2)]


def faithful_mock(question_phrases):
    """A well-behaved model: drafts from the first passage that contains the key phrase, says INSUFFICIENT_EVIDENCE otherwise."""
    def llm(prompt):
        if "strict evidence checker" in prompt:
            draft = re.search(r"Draft answer:\n(.*?)\n\nPassages:", prompt, re.S).group(1).strip()
            fact = "the answer"                                   # the mock's own generation step always names its single fact this
            for cid, text in _passages(prompt):
                sent = next((s for s in re.split(r"(?<=[.!?])\s+", text) if _FOLD(s) in _FOLD(draft)), None)
                if sent:
                    return json.dumps({"facts": [{"fact": fact, "status": "supported", "claim": draft, "supporting_chunk_ids": [cid], "evidence_quote": sent}],
                                       "unaddressed_parts": []})
            return json.dumps({"facts": [{"fact": fact, "status": "unsupported", "claim": "", "supporting_chunk_ids": [], "evidence_quote": ""}], "unaddressed_parts": []})
        hit = next(((cid, t) for cid, t in _passages(prompt) for p in question_phrases if p and _FOLD(p) in _FOLD(t)), None)
        if not hit:
            return json.dumps({"requested_facts": ["the answer"], "answer": "INSUFFICIENT_EVIDENCE"})
        sent = next(s for s in re.split(r"(?<=[.!?])\s+", hit[1]) if any(_FOLD(p) in _FOLD(s) for p in question_phrases if p))
        return json.dumps({"requested_facts": ["the answer"], "answer": sent})
    return llm


def hallucinating_mock(prompt):
    """A badly-behaved model that invents a figure, then 'verifies' it with a quote that is not in any passage."""
    if "strict evidence checker" in prompt:
        cid = _passages(prompt)[0][0]
        draft = re.search(r"Draft answer:\n(.*?)\n\nPassages:", prompt, re.S).group(1).strip()
        return json.dumps({"facts": [{"fact": "the answer", "status": "supported", "claim": draft, "supporting_chunk_ids": [cid],
                                      "evidence_quote": "Kai's Company charges 150 dollars per hour for evaluators"}], "unaddressed_parts": []})
    return json.dumps({"requested_facts": ["the answer"], "answer": "Kai's Company charges 150 dollars per hour for evaluators."})


def run(store):
    qs = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    rows = []
    for q in qs:
        where = {"doc_type": {"$ne": "kyc"}}
        routed = numbers_qa.route(q["question"])                                   # the app sends metric-sounding questions to the calculator first
        off = offline.answer_offline(store, q["question"], where=where)
        cited = sorted({c.split(" › ")[0].strip("[") for c in off.sources})
        text = _FOLD(off.text)
        answerable = q["category"] != "unanswerable"
        if answerable:
            ok = routed == "documents" and off.status in ("answered", "partial") and set(q["sources"]) <= set(cited) and all(_FOLD(p) in text for p in q["phrases"])
        else:
            ok = routed == "documents" and off.status == "refused"
        hosted = answer_verified(store, q["question"], faithful_mock(q["phrases"]), where=where)
        h_cited = sorted({c.split(" › ")[0].strip("[") for c in hosted.sources})
        h_ok = (hosted.status in ("answered", "partial") and bool(h_cited) and all(_FOLD(p) in _FOLD(hosted.text) for p in q["phrases"])) if answerable else hosted.status == "refused"
        bad = answer_verified(store, q["question"], hallucinating_mock, where=where)
        rows.append({**q, "offline": {"status": off.status, "reason": off.reason, "cited": cited, "pass": ok, "answer": off.text},
                     "hosted_mock_faithful": {"status": hosted.status, "reason": hosted.reason, "cited": h_cited, "pass": h_ok, "answer": hosted.text},
                     "hosted_mock_hallucinating": {"status": bad.status, "reason": bad.reason, "invented_text_shown": "150 dollars" in bad.text}})
    return rows


def render(rows, info):
    n = lambda cat, key: (sum(r[key]["pass"] for r in rows if r["category"] == cat), sum(r["category"] == cat for r in rows))
    lines = ["# Knowledge pack evaluation (seven approved documents)", "",
             f"Index: {info['chunks']} chunks, {info['documents']} documents (fingerprint {info['fingerprint']}). Real local FastEmbed vectors and Chroma. "
             "No hosted or paid call was made: the Fireworks pipeline was exercised with MOCK models only.", "",
             "| Category | Offline engine (real) | Hosted pipeline + faithful mock |", "|---|---|---|"]
    for cat in ("direct", "cross-document", "unanswerable"):
        a, b = n(cat, "offline"), n(cat, "hosted_mock_faithful")
        lines.append(f"| {cat} | {a[0]}/{a[1]} | {b[0]}/{b[1]} |")
    shown = sum(r["hosted_mock_hallucinating"]["invented_text_shown"] for r in rows)
    lines += ["", f"Hallucinating mock (invents '150 dollars per hour' with a fake quote): invented text shown to the user in **{shown}/{len(rows)}** questions "
                  "(the evidence check rejects it every time).", "", "## Per question", ""]
    for r in rows:
        o = r["offline"]
        lines += [f"### {r['id']} ({r['category']}): {r['question']}",
                  f"- Offline: **{'PASS' if o['pass'] else 'FAIL'}** · {o['status']}{' (' + o['reason'] + ')' if o['reason'] else ''} · cited: {', '.join(o['cited']) or 'none'}",
                  f"- Hosted pipeline, faithful mock: **{'PASS' if r['hosted_mock_faithful']['pass'] else 'FAIL'}** · {r['hosted_mock_faithful']['status']} "
                  f"· cited: {', '.join(r['hosted_mock_faithful']['cited']) or 'none'}",
                  f"- Answer: {o['answer'][:360].replace(chr(10), ' ')}", ""]
    notes = ROOT / "eval" / "pack_notes.md"
    if notes.exists():
        lines += ["", notes.read_text(encoding="utf-8")]
    return "\n".join(lines)


def main():
    store, info = app_index.ensure_index(emb.FastEmbedEmbeddings(), None, persist_dir=EVAL_INDEX)
    rows = run(store)
    RESULTS.write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    REPORT.write_text(render(rows, info), encoding="utf-8")
    print(render(rows, info).split("## Per question")[0])
    for r in rows:
        if not r["offline"]["pass"] or not r["hosted_mock_faithful"]["pass"]:
            print("FAIL", r["id"], r["offline"]["status"], r["offline"]["cited"], r["hosted_mock_faithful"]["status"], "|", r["offline"]["answer"][:160])


if __name__ == "__main__":
    main()
