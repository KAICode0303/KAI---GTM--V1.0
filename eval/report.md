# Hoomi retrieval evaluation

Scope: **retrieval only** (local FastEmbed `BAAI/bge-small-en-v1.5` + Chroma, 15 chunks from 3 synthetic documents). No LLM was used, so this says **nothing about generated-answer accuracy**. Distances are Chroma's L2 distance for this model (smaller = closer), not a 0-1 score. Questions: `eval/questions.json` (unchanged). Raw data: `eval/results.json`. Context policy used below: **top-6**.

## Comparison with the baseline (same 15 questions, unchanged)

Two changes were made: (1) each chunk is now *embedded* with its document title and section heading in front (the stored text and citations are unchanged); (2) the answerability gate is separated from context selection. Gate distance is 0.70 in every row. *Old rule* = top-4 chunks each within 0.70; *new policy* = top-6.

| Variant | Top-1 hit | Top-3 hit | All expected in top-3 | Required evidence complete in context | ...of which complex | False rejections | Correct refusals | False acceptances | Avg chunks given |
|---|---|---|---|---|---|---|---|---|---|
| A. Baseline: old embedding, old rule | 5/11 (45%) | 9/11 (82%) | 7/11 (64%) | 5/11 (45%) | 0/5 | 0 | 2/4 | 2 | 1.6 |
| B. Old embedding, new policy | 5/11 (45%) | 9/11 (82%) | 7/11 (64%) | 9/11 (82%) | 3/5 | 0 | 2/4 | 2 | 6.0 |
| D. New embedding, old rule | 6/11 (55%) | 10/11 (91%) | 8/11 (73%) | 6/11 (55%) | 1/5 | 0 | 2/4 | 2 | 2.5 |
| **C. New embedding, new policy (current)** | 6/11 (55%) | 10/11 (91%) | 8/11 (73%) | 10/11 (91%) | 4/5 | 0 | 2/4 | 2 | 6.0 |

*Top-1, top-3 and all-expected-in-top-3 depend only on the embedding, so A = B and C = D on those columns. Required evidence complete = every required phrase appears in the context given to the model (refused questions count as not complete). Avg chunks given = mean context size over accepted answerable questions: a rough proxy for how much unrelated text the model must read.*

### Question-level changes, A → C

| ID | Type | Top-1 distance | Top-1 hit | Gate @0.70 | Evidence complete | Chunks given | Verdict |
|---|---|---|---|---|---|---|---|
| D1 | direct | 0.472 → 0.437 | yes → yes | accept → accept | yes → yes | 1 → 6 | **same** |
| D2 | direct | 0.631 → 0.376 | yes → yes | accept → accept | yes → yes | 2 → 6 | **same** |
| D3 | direct | 0.564 → 0.612 | no → no | accept → accept | yes → yes | 3 → 6 | **same** |
| D4 | direct | 0.401 → 0.444 | no → no | accept → accept | no → yes | 3 → 6 | **improved** |
| D5 | direct | 0.484 → 0.514 | yes → yes | accept → accept | yes → yes | 1 → 6 | **same** |
| D6 | direct | 0.632 → 0.688 | no → no | accept → accept | yes → yes | 2 → 6 | **same** |
| C1 | complex | 0.635 → 0.603 | no → yes | accept → accept | no → yes | 2 → 6 | **improved** |
| C2 | complex | 0.589 → 0.615 | no → no | accept → accept | no → no | 1 → 6 | **same** |
| C3 | complex | 0.517 → 0.541 | no → no | accept → accept | no → yes | 1 → 6 | **improved** |
| C4 | complex | 0.599 → 0.553 | yes → yes | accept → accept | no → yes | 1 → 6 | **improved** |
| C5 | complex | 0.619 → 0.647 | yes → yes | accept → accept | no → yes | 1 → 6 | **improved** |
| U1 | unanswerable | 0.773 → 0.848 | - | refuse → refuse | - | 0 → 0 | **same** |
| U2 | unanswerable | 0.527 → 0.584 | - | accept → accept | - | 2 → 6 | **same** |
| U3 | unanswerable | 0.472 → 0.521 | - | accept → accept | - | 3 → 6 | **same** |
| U4 | unanswerable | 1.209 → 1.196 | - | refuse → refuse | - | 0 → 0 | **same** |

**Improved (5):** D4, C1, C3, C4, C5. **Regressed (0):** none. **Unchanged (10):** D1, D2, D3, D5, D6, C2, U1, U2, U3, U4.


## 1. Retrieval quality (independent of any threshold)

| Group | Questions | Top-1 hit | Top-3 hit | ALL expected sections in top-3 | ALL expected in top-4 | Required evidence in top-3 |
|---|---|---|---|---|---|---|
| direct | 6 | 3/6 (50%) | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) | 6/6 (100%) |
| complex | 5 | 3/5 (60%) | 4/5 (80%) | 2/5 (40%) | 3/5 (60%) | 2/5 (40%) |
| all answerable | 11 | 6/11 (55%) | 10/11 (91%) | 8/11 (73%) | 9/11 (82%) | 8/11 (73%) |

*Top-1 hit*: the closest chunk is one of the expected sections. *Top-3 hit*: at least one expected section is in the top 3. For complex questions, the *ALL* columns are the cross-document test: every expected section must be present.

## 2. Gate comparison

The *gate* accepts a question when its closest chunk is within the distance, otherwise refuses. Context selection then follows the policy (top-6) and no longer depends on the gate distance. Answerable: 11, unanswerable: 4.

| Gate distance | Correct accepts | **False rejections** | Correct refusals | **False acceptances** | Evidence complete in context | Accepted but required evidence missing | Accepted but an expected section missing |
|---|---|---|---|---|---|---|---|
| 0.55 | 5/11 | 6 | 3/4 | 1 | 5/11 | 0 | 0 |
| 0.60 | 6/11 | 5 | 2/4 | 2 | 6/11 | 0 | 0 |
| 0.65 | 10/11 | 1 | 2/4 | 2 | 9/11 | 1 | 1 |
| 0.70 (provisional) | 11/11 | 0 | 2/4 | 2 | 10/11 | 1 | 1 |
| 0.75 | 11/11 | 0 | 2/4 | 2 | 10/11 | 1 | 1 |
| 0.80 | 11/11 | 0 | 2/4 | 2 | 10/11 | 1 | 1 |
| 0.85 | 11/11 | 0 | 1/4 | 3 | 10/11 | 1 | 1 |
| 0.90 | 11/11 | 0 | 1/4 | 3 | 10/11 | 1 | 1 |

*False rejection* = an answerable question refused (Hoomi would wrongly say it lacks evidence). *False acceptance* = an unanswerable question accepted (the model would be given irrelevant context and could hallucinate).

### Context-selection policies (gate fixed at 0.70)

| Policy | Evidence complete | ...complex | Accepted but a section missing | Avg chunks given |
|---|---|---|---|---|
| Old rule (top-4, each within gate) | 6/11 (55%) | 1/5 | 5 | 2.5 |
| top-4 | 9/11 (82%) | 3/5 | 2 | 4.0 |
| top-6 | 10/11 (91%) | 4/5 | 1 | 6.0 |
| top-8 | 11/11 (100%) | 5/5 | 0 | 8.0 |
| top-6, best+0.15 | 8/11 (73%) | 2/5 | 3 | 3.0 |
| top-6, best+0.25 | 10/11 (91%) | 4/5 | 1 | 4.5 |
| top-8, best+0.25 | 11/11 (100%) | 5/5 | 0 | 5.1 |

These are descriptive. The gate does not change with the policy (refusals are identical in every row); only what the model sees does. The default is not tuned to this table: a larger k trades completeness for more irrelevant text.


### Separation and robustness

- Closest-chunk distance, **answerable** questions: min 0.376, median 0.553, max 0.688.
- Closest-chunk distance, **unanswerable** questions: min 0.521, median 0.716, max 1.196.
- The groups **overlap**: worst answerable (0.688) is farther than best unanswerable (0.521); no single gate distance is error-free.
- Gate distances with zero errors on this set: none.
- Leave-one-out (choose a gate distance on 14 questions, test on the held-out one): 12/15 correct; errors on U1, U2, U3. Chosen distances ranged 0.74 to 0.94.
- With only 15 questions (4 unanswerable) and a 15-chunk corpus, any distance read off this table is a hypothesis, not a calibrated setting. A larger corpus will raise the distances of unrelated questions and reduce the margin.

## 3. Question-level results

Gate 0.70; context policy top-6.

| ID | Type | Top-1 chunk (distance) | Top-1 hit | Top-3 hit | Gate @0.70 | Evidence complete | Outcome |
|---|---|---|---|---|---|---|---|
| D1 | direct | 02_icp.md › Best-fit customers (0.437) | yes | yes | accept | yes | correct accept |
| D2 | direct | 03_case_study.md › Results after six months (0.376) | yes | yes | accept | yes | correct accept |
| D3 | direct | 01_capabilities.md › Capabilities overview (0.612) | no | yes | accept | yes | correct accept |
| D4 | direct | 01_capabilities.md › Capabilities overview (0.444) | no | yes | accept | yes | correct accept |
| D5 | direct | 02_icp.md › Buying signals (0.514) | yes | yes | accept | yes | correct accept |
| D6 | direct | 03_case_study.md › Results after six months (0.688) | no | yes | accept | yes | correct accept |
| C1 | complex | 02_icp.md › Best-fit customers (0.603) | yes | yes | accept | yes | correct accept |
| C2 | complex | 03_case_study.md › Results after six months (0.615) | no | no | accept | no | correct accept |
| C3 | complex | 03_case_study.md › Case study: Northwind Health (0.541) | no | yes | accept | yes | correct accept |
| C4 | complex | 01_capabilities.md › Applied AI and Machine Learning (0.553) | yes | yes | accept | yes | correct accept |
| C5 | complex | 02_icp.md › Competitive positioning (0.647) | yes | yes | accept | yes | correct accept |
| U1 | unanswerable | 03_case_study.md › Results after six months (0.848) | - | - | refuse | - | correct refusal |
| U2 | unanswerable | 01_capabilities.md › Data Engineering (0.584) | - | - | accept | - | FALSE ACCEPTANCE |
| U3 | unanswerable | 01_capabilities.md › Capabilities overview (0.521) | - | - | accept | - | FALSE ACCEPTANCE |
| U4 | unanswerable | 02_icp.md › Buying signals (1.196) | - | - | refuse | - | correct refusal |

### D1 (direct): Who is the typical buyer at our best-fit customers, and what industries are they in?

- Expected: `02_icp.md › Best-fit customers` (rank 1, distance 0.4367)
- Required evidence: “Chief Data Officer”; “healthcare, financial services and retail”
- Actual top-3: #1 `02_icp.md › Best-fit customers` 0.437; #2 `02_icp.md › Poor-fit customers` 0.670; #3 `02_icp.md › Buying signals` 0.720
- Gate 0.70: **accept** (closest 0.437); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: Single section holds both the buyer persona and the industries.

### D2 (direct): By how much did Northwind Health cut its reporting time?

- Expected: `03_case_study.md › Results after six months` (rank 1, distance 0.3764)
- Required evidence: “four days to under one hour”
- Actual top-3: #1 `03_case_study.md › Results after six months` 0.376; #2 `03_case_study.md › The challenge` 0.549; #3 `03_case_study.md › Case study: Northwind Health` 0.738
- Gate 0.70: **accept** (closest 0.376); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: The Challenge section also mentions 'four days' (late reports): a plausible near-miss.

### D3 (direct): Can Kai's Company build a question-answering assistant over a client's own documents?

- Expected: `01_capabilities.md › Applied AI and Machine Learning` (rank 2, distance 0.6178)
- Required evidence: “answer questions from a client's own documents with citations”
- Actual top-3: #1 `01_capabilities.md › Capabilities overview` 0.612; #2 `01_capabilities.md › Applied AI and Machine Learning` 0.618; #3 `03_case_study.md › What Kai's Company did` 0.647
- Gate 0.70: **accept** (closest 0.612); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: The case study also mentions a pilot assistant: a plausible near-miss.

### D4 (direct): What engagement models does Kai's Company offer?

- Expected: `01_capabilities.md › Delivery modalities` (rank 2, distance 0.555)
- Required evidence: “fixed-scope project”; “monthly managed service”; “time-and-materials”
- Actual top-3: #1 `01_capabilities.md › Capabilities overview` 0.444; #2 `01_capabilities.md › Delivery modalities` 0.555; #3 `01_capabilities.md › Applied AI and Machine Learning` 0.617
- Gate 0.70: **accept** (closest 0.444); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: Short section; positioning and case study also mention fixed-scope.

### D5 (direct): What public signals suggest a company is about to invest in data modernisation?

- Expected: `02_icp.md › Buying signals` (rank 1, distance 0.5138)
- Required evidence: “new data leadership hires”; “job postings for data engineers”
- Actual top-3: #1 `02_icp.md › Buying signals` 0.514; #2 `01_capabilities.md › Data Engineering` 0.777; #3 `02_icp.md › Best-fit customers` 0.786
- Gate 0.70: **accept** (closest 0.514); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: 'data modernisation' also appears in Best-fit customers.

### D6 (direct): What reporting problems did the regional healthcare network face before the engagement?

- Expected: `03_case_study.md › The challenge` (rank 2, distance 0.7259)
- Required evidence: “five separate systems”
- Actual top-3: #1 `03_case_study.md › Results after six months` 0.688; #2 `03_case_study.md › The challenge` 0.726; #3 `03_case_study.md › Case study: Northwind Health` 0.846
- Gate 0.70: **accept** (closest 0.688); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: Question avoids the client's name on purpose.

### C1 (complex): Is there a case study for a healthcare prospect, and does healthcare fit our ideal customer profile?

- Expected: `02_icp.md › Best-fit customers` (rank 1, distance 0.6034); `03_case_study.md › Case study: Northwind Health` (rank 3, distance 0.6958)
- Required evidence: “healthcare, financial services and retail”; “regional healthcare network”
- Actual top-3: #1 `02_icp.md › Best-fit customers` 0.603; #2 `02_icp.md › Poor-fit customers` 0.690; #3 `03_case_study.md › Case study: Northwind Health` 0.696
- Gate 0.70: **accept** (closest 0.603); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: Needs the ICP industries (ICP doc) and the healthcare client (case study intro).

### C2 (complex): Does the Northwind Health project support our positioning of fixed-scope delivery with a clear handover?

- Expected: `02_icp.md › Competitive positioning` (rank 7, distance 0.7953); `03_case_study.md › Lessons` (rank 4, distance 0.6498)
- Required evidence: “fixed-scope pricing and a clear handover”; “trained to maintain the pipelines”
- Actual top-3: #1 `03_case_study.md › Results after six months` 0.615; #2 `01_capabilities.md › Delivery modalities` 0.641; #3 `03_case_study.md › Case study: Northwind Health` 0.645
- Gate 0.70: **accept** (closest 0.615); 6 chunk(s) given to the model; required evidence **incomplete** in that context
- Design note: Claim in the ICP doc, proof point in the case study Lessons.

### C3 (complex): Which of our standard engagement models matches how Northwind Health was delivered?

- Expected: `01_capabilities.md › Delivery modalities` (rank 6, distance 0.7147); `03_case_study.md › Results after six months` (rank 3, distance 0.5901)
- Required evidence: “fixed-scope project”; “fixed-scope engagement of ten weeks”
- Actual top-3: #1 `03_case_study.md › Case study: Northwind Health` 0.541; #2 `03_case_study.md › The challenge` 0.570; #3 `03_case_study.md › Results after six months` 0.590
- Gate 0.70: **accept** (closest 0.541); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: Model list (capabilities) must be matched with the delivery fact (case study).

### C4 (complex): Before pitching our AI assistant capability, which buying signals and poor-fit warnings should an SDR check?

- Expected: `02_icp.md › Buying signals` (rank 2, distance 0.6312); `02_icp.md › Poor-fit customers` (rank 4, distance 0.7729); `01_capabilities.md › Applied AI and Machine Learning` (rank 1, distance 0.5535)
- Required evidence: “job postings for data engineers”; “no data team”; “retrieval-augmented assistants”
- Actual top-3: #1 `01_capabilities.md › Applied AI and Machine Learning` 0.553; #2 `02_icp.md › Buying signals` 0.631; #3 `01_capabilities.md › Capabilities overview` 0.724
- Gate 0.70: **accept** (closest 0.553); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: Three sections across two documents.

### C5 (complex): How do we position against large consultancies, and what do we hand over to the client at the end of a model build?

- Expected: `02_icp.md › Competitive positioning` (rank 1, distance 0.6474); `01_capabilities.md › Applied AI and Machine Learning` (rank 3, distance 0.752)
- Required evidence: “slower and costlier”; “handover guide”
- Actual top-3: #1 `02_icp.md › Competitive positioning` 0.647; #2 `03_case_study.md › Lessons` 0.742; #3 `01_capabilities.md › Applied AI and Machine Learning` 0.752
- Gate 0.70: **accept** (closest 0.647); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: Positioning (ICP doc) plus the concrete handover artefact (capabilities).

### U1 (unanswerable): What is the company's refund policy for cancelled projects?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `03_case_study.md › Results after six months` 0.848; #2 `03_case_study.md › Lessons` 0.930; #3 `01_capabilities.md › Delivery modalities` 0.955
- Gate 0.70: **refuse** (closest 0.848); 0 chunk(s) given to the model
- Design note: Plausible business topic that no document covers.

### U2 (unanswerable): What hourly rate does Kai's Company charge for a data engineer?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `01_capabilities.md › Data Engineering` 0.584; #2 `01_capabilities.md › Capabilities overview` 0.612; #3 `03_case_study.md › What Kai's Company did` 0.671
- Gate 0.70: **accept** (closest 0.584); 6 chunk(s) given to the model
- Design note: Hard negative: documents mention fixed-scope pricing and engineers but give no rates.

### U3 (unanswerable): How many employees does Kai's Company have?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `01_capabilities.md › Capabilities overview` 0.521; #2 `03_case_study.md › What Kai's Company did` 0.558; #3 `02_icp.md › Competitive positioning` 0.742
- Gate 0.70: **accept** (closest 0.521); 6 chunk(s) given to the model
- Design note: Hard negative: 'employees' appears only as the size of TARGET customers (500 to 5,000).

### U4 (unanswerable): Who won the football world cup?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `02_icp.md › Buying signals` 1.196; #2 `02_icp.md › Competitive positioning` 1.223; #3 `02_icp.md › Best-fit customers` 1.243
- Gate 0.70: **refuse** (closest 1.196); 0 chunk(s) given to the model
- Design note: Completely off-topic control.

## 4. Cross-document questions: where the second document went

For each expected section: its rank among all 15 chunks, its distance, and whether the current policy (top-6) includes it.

| ID | Expected section | Rank | Distance | Status |
|---|---|---|---|---|
| C1 | 02_icp.md › Best-fit customers | 1 | 0.6034 | in context |
| C1 | 03_case_study.md › Case study: Northwind Health | 3 | 0.6958 | in context |
| C2 | 02_icp.md › Competitive positioning | 7 | 0.7953 | ranked #7, outside top-6 |
| C2 | 03_case_study.md › Lessons | 4 | 0.6498 | in context |
| C3 | 01_capabilities.md › Delivery modalities | 6 | 0.7147 | in context |
| C3 | 03_case_study.md › Results after six months | 3 | 0.5901 | in context |
| C4 | 02_icp.md › Buying signals | 2 | 0.6312 | in context |
| C4 | 02_icp.md › Poor-fit customers | 4 | 0.7729 | in context |
| C4 | 01_capabilities.md › Applied AI and Machine Learning | 1 | 0.5535 | in context |
| C5 | 02_icp.md › Competitive positioning | 1 | 0.6474 | in context |
| C5 | 01_capabilities.md › Applied AI and Machine Learning | 3 | 0.752 | in context |

### How many chunks are needed to cover every expected section?

Ignoring any threshold: complex questions whose expected sections ALL rank within the top-k of the 15 chunks.

| Top-k | 3 | 4 | 6 | 8 | 10 |
|---|---|---|---|---|---|
| Complex questions fully covered | 2/5 (40%) | 3/5 (60%) | 4/5 (80%) | 5/5 (100%) | 5/5 (100%) |

A bigger k recovers more of the second document but passes more unrelated text to the model; with only 15 chunks, k=10 is two-thirds of the whole index, so this table shows how well the ranking works, not that k=10 is a good setting.

## 5. Analysis

*Written by hand from the tables above, for the index with title+section embeddings and the top-6 context policy. The pre-change analysis is preserved in `eval/report_baseline.md`. Re-check these statements if the corpus, chunking, model or policy changes.*

**Headline.** The improvement is real but small and comes mostly from one of the two changes. Required evidence reached the model for **10 of 11** answerable questions, up from 5 of 11 (cross-document: 4 of 5, up from 0 of 5), with **no new false rejections or false acceptances** and no question worse off on the gate or evidence measures. The answerability gate itself is **not improved**: the answerable and unanswerable distance ranges still overlap, and U2 and U3 are still wrongly accepted.

**Which change did what.** The four-way table separates them.
- *Context policy (separating context selection from the gate)* is the main effect: required-evidence coverage 5 → 9 on the old index (A → B), and 6 → 10 on the new one (D → C). It recovers sections that sit past the gate distance, for example C5's "Applied AI" section (0.752) and C4's "Poor-fit customers" (0.773).
- *Title+section embeddings* moved ranking by about one question each: top-1 5 → 6 (C1), top-3 9 → 10 (D4: Delivery modalities rose from rank 6 to rank 2), all-expected-in-top-3 7 → 8. With 11 answerable questions, a single question is not evidence of a trend.
- The embedding change **reshuffled** cross-document sections rather than uniformly lifting them. "Lessons" (C2) rose from rank 7 to 4, but "Competitive positioning" (C2) fell from 4 to 7; in C3, "Delivery modalities" fell from 3 to 6 while "Results after six months" rose from 6 to 3.

**Costs and regressions to be aware of.**
1. *Gate headroom got tighter.* The farthest answerable top-1 distance rose from 0.635 to 0.688 (D6). At the provisional 0.70 gate, D6 now passes by only 0.012, and at 0.65 there is one false rejection where there was none. The zero-false-rejection region moved from 0.65-0.75 to 0.70-0.80 and is no wider. Unanswerable questions moved away (median best-hit distance 0.650 → 0.716; U1 0.773 → 0.848, so U1 is now refused up to a gate of 0.80), but the closest unanswerable (U3) is still 0.521, nearer than most answerable questions. Leave-one-out is unchanged at 12/15, with the same three misses.
2. *More text reaches the model.* The average context grew from 1.6 to 6.0 chunks. That includes the two falsely accepted questions: U2 and U3 now hand the model 6 chunks of irrelevant text instead of 2 and 3, which raises the hallucination risk if the gate lets them through. The model-side `INSUFFICIENT_EVIDENCE` refusal remains the only defence against them, and it is untested until a model is connected. Six chunks is 40% of this 15-chunk index; on a real corpus it is an ordinary size, so this ratio does not transfer.
3. *The intro-chunk problem persists.* "Capabilities overview" is still the top hit for D3 (0.612), D4 (0.444) and U3 (0.521), and "Case study: Northwind Health" for C3. Prefixing every chunk with its document title makes chunks of the same document more alike, which does not help distinguish an intro from an answer section.

**Still failing.** C2 is the one answerable question with incomplete evidence: "Competitive positioning" is now ranked 7th (0.795), just outside the top-6. Among the unanswerable questions, U2 and U3 are still accepted. D3, D4 and D6 still have a non-expected section as top-1, though their required evidence is in context.

**About the policy defaults.** `top-6` was fixed before these results were seen and is a provisional starting point. The policy grid shows that `top-8` and `top-8 + best+0.25` reach 11/11 (the latter with an average of 5.1 chunks), but picking a setting from this table would be tuning on the 15 questions. Treat those as candidates to validate on new questions, not as a recommendation.

**What this does not show.** Retrieval only: nothing here measures whether a model writes correct, faithful or well-cited answers from this context. The question set, corpus and chunk count are small and written by one author, so differences of one question (such as 5 → 6 top-1 hits) are within noise.

**Next candidates (not implemented).** Merge or drop the near-empty intro chunks that act as magnets; add new unanswerable and cross-document questions before choosing any threshold or policy; query decomposition for multi-part questions (needs a model call); a reranker or keyword (hybrid) search. A better test of the gate needs questions whose answer is *almost* in the corpus.

## Limitations

- 15 questions written by the same author as the corpus: wording overlaps the documents more than real users' will.
- A 15-chunk synthetic corpus is far easier than a real library; expect lower hit rates and tighter margins at scale.
- Hit rates use section-level expectations; a near-duplicate section elsewhere can be a legitimate answer yet count as a miss.
- Retrieval only. Whether a model writes a correct, faithful, well-cited answer from this context is **not measured here**.
