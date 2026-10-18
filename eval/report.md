# Hoomi retrieval evaluation

Scope: **retrieval only** (local FastEmbed `BAAI/bge-small-en-v1.5` + Chroma, 15 chunks from 3 synthetic documents). No LLM was used, so this says **nothing about generated-answer accuracy**. Distances are Chroma's L2 distance for this model (smaller = closer), not a 0-1 score. Questions: `eval/questions.json`. Raw data: `eval/results.json`.

## 1. Retrieval quality (independent of any threshold)

| Group | Questions | Top-1 hit | Top-3 hit | ALL expected sections in top-3 | ALL expected in top-4 context | Required evidence in top-3 |
|---|---|---|---|---|---|---|
| direct | 6 | 3/6 (50%) | 5/6 (83%) | 5/6 (83%) | 5/6 (83%) | 5/6 (83%) |
| complex | 5 | 2/5 (40%) | 4/5 (80%) | 2/5 (40%) | 2/5 (40%) | 2/5 (40%) |
| all answerable | 11 | 5/11 (45%) | 9/11 (82%) | 7/11 (64%) | 7/11 (64%) | 7/11 (64%) |

*Top-1 hit*: the closest chunk is one of the expected sections. *Top-3 hit*: at least one expected section is in the top 3. For complex questions, the *ALL* columns are the cross-document test: every expected section must be present.

## 2. Threshold comparison

A question is *accepted* when its closest chunk is within the threshold, otherwise *refused*. Answerable: 11, unanswerable: 4.

| Threshold | Correct accepts | **False rejections** | Correct refusals | **False acceptances** | Accepted but required evidence missing from context | Accepted but an expected section missing |
|---|---|---|---|---|---|---|
| 0.55 | 4/11 | 7 | 2/4 | 2 | 2 | 2 |
| 0.60 | 7/11 | 4 | 2/4 | 2 | 5 | 5 |
| 0.65 | 11/11 | 0 | 2/4 | 2 | 8 | 8 |
| 0.70 (provisional) | 11/11 | 0 | 2/4 | 2 | 6 | 6 |
| 0.75 | 11/11 | 0 | 2/4 | 2 | 4 | 4 |
| 0.80 | 11/11 | 0 | 1/4 | 3 | 4 | 4 |
| 0.85 | 11/11 | 0 | 1/4 | 3 | 4 | 4 |
| 0.90 | 11/11 | 0 | 1/4 | 3 | 4 | 4 |

*False rejection* = an answerable question refused (Hoomi would wrongly say it lacks evidence). *False acceptance* = an unanswerable question accepted (the model would be given irrelevant context and could hallucinate).

### Separation and robustness

- Closest-chunk distance, **answerable** questions: min 0.401, median 0.589, max 0.635.
- Closest-chunk distance, **unanswerable** questions: min 0.472, median 0.650, max 1.209.
- The groups **overlap**: worst answerable (0.635) is farther than best unanswerable (0.472); no single threshold is error-free.
- Thresholds with zero errors on this set: none.
- Leave-one-out (choose a threshold on 14 questions, test on the held-out one): 12/15 correct; errors on U1, U2, U3. Chosen thresholds ranged 0.70 to 0.92.
- With only 15 questions (4 unanswerable) and a 15-chunk corpus, any threshold read off this table is a hypothesis, not a calibrated setting. A larger corpus will raise the distances of unrelated questions and reduce the margin.

## 3. Question-level results

Decision shown for the provisional threshold 0.70.

| ID | Type | Top-1 chunk (distance) | Top-1 hit | Top-3 hit | Decision @0.70 | Outcome |
|---|---|---|---|---|---|---|
| D1 | direct | 02_icp.md › Best-fit customers (0.472) | yes | yes | accept | correct accept |
| D2 | direct | 03_case_study.md › Results after six months (0.631) | yes | yes | accept | correct accept |
| D3 | direct | 01_capabilities.md › Capabilities overview (0.564) | no | yes | accept | correct accept |
| D4 | direct | 01_capabilities.md › Capabilities overview (0.401) | no | no | accept | correct accept |
| D5 | direct | 02_icp.md › Buying signals (0.484) | yes | yes | accept | correct accept |
| D6 | direct | 03_case_study.md › Results after six months (0.632) | no | yes | accept | correct accept |
| C1 | complex | 02_icp.md › Ideal customer profile (0.635) | no | yes | accept | correct accept |
| C2 | complex | 03_case_study.md › Case study: Northwind Health (0.589) | no | no | accept | correct accept |
| C3 | complex | 03_case_study.md › Case study: Northwind Health (0.517) | no | yes | accept | correct accept |
| C4 | complex | 01_capabilities.md › Applied AI and Machine Learning (0.599) | yes | yes | accept | correct accept |
| C5 | complex | 02_icp.md › Competitive positioning (0.619) | yes | yes | accept | correct accept |
| U1 | unanswerable | 03_case_study.md › Results after six months (0.773) | - | - | refuse | correct refusal |
| U2 | unanswerable | 01_capabilities.md › Capabilities overview (0.527) | - | - | accept | FALSE ACCEPTANCE |
| U3 | unanswerable | 01_capabilities.md › Capabilities overview (0.472) | - | - | accept | FALSE ACCEPTANCE |
| U4 | unanswerable | 01_capabilities.md › Analytics and Dashboards (1.209) | - | - | refuse | correct refusal |

### D1 (direct): Who is the typical buyer at our best-fit customers, and what industries are they in?

- Expected: `02_icp.md › Best-fit customers` (rank 1, distance 0.4725)
- Required evidence: “Chief Data Officer”; “healthcare, financial services and retail”
- Actual top-3: #1 `02_icp.md › Best-fit customers` 0.472; #2 `02_icp.md › Buying signals` 0.822; #3 `02_icp.md › Competitive positioning` 0.839
- Threshold 0.70: **accept** (closest 0.472, 1 of 4 context chunks kept); required evidence complete in kept context
- Design note: Single section holds both the buyer persona and the industries.

### D2 (direct): By how much did Northwind Health cut its reporting time?

- Expected: `03_case_study.md › Results after six months` (rank 1, distance 0.6315)
- Required evidence: “four days to under one hour”
- Actual top-3: #1 `03_case_study.md › Results after six months` 0.631; #2 `03_case_study.md › Case study: Northwind Health` 0.647; #3 `03_case_study.md › The challenge` 0.779
- Threshold 0.70: **accept** (closest 0.631, 2 of 4 context chunks kept); required evidence complete in kept context
- Design note: The Challenge section also mentions 'four days' (late reports): a plausible near-miss.

### D3 (direct): Can Kai's Company build a question-answering assistant over a client's own documents?

- Expected: `01_capabilities.md › Applied AI and Machine Learning` (rank 3, distance 0.6581)
- Required evidence: “answer questions from a client's own documents with citations”
- Actual top-3: #1 `01_capabilities.md › Capabilities overview` 0.564; #2 `03_case_study.md › What Kai's Company did` 0.629; #3 `01_capabilities.md › Applied AI and Machine Learning` 0.658
- Threshold 0.70: **accept** (closest 0.564, 3 of 4 context chunks kept); required evidence complete in kept context
- Design note: The case study also mentions a pilot assistant: a plausible near-miss.

### D4 (direct): What engagement models does Kai's Company offer?

- Expected: `01_capabilities.md › Delivery modalities` (rank 6, distance 0.917)
- Required evidence: “fixed-scope project”; “monthly managed service”; “time-and-materials”
- Actual top-3: #1 `01_capabilities.md › Capabilities overview` 0.401; #2 `02_icp.md › Competitive positioning` 0.591; #3 `03_case_study.md › What Kai's Company did` 0.670
- Threshold 0.70: **accept** (closest 0.401, 3 of 4 context chunks kept); required evidence **incomplete** in kept context
- Design note: Short section; positioning and case study also mention fixed-scope.

### D5 (direct): What public signals suggest a company is about to invest in data modernisation?

- Expected: `02_icp.md › Buying signals` (rank 1, distance 0.4837)
- Required evidence: “new data leadership hires”; “job postings for data engineers”
- Actual top-3: #1 `02_icp.md › Buying signals` 0.484; #2 `02_icp.md › Best-fit customers` 0.718; #3 `01_capabilities.md › Data Engineering` 0.777
- Threshold 0.70: **accept** (closest 0.484, 1 of 4 context chunks kept); required evidence complete in kept context
- Design note: 'data modernisation' also appears in Best-fit customers.

### D6 (direct): What reporting problems did the regional healthcare network face before the engagement?

- Expected: `03_case_study.md › The challenge` (rank 2, distance 0.6987)
- Required evidence: “five separate systems”
- Actual top-3: #1 `03_case_study.md › Results after six months` 0.632; #2 `03_case_study.md › The challenge` 0.699; #3 `03_case_study.md › Case study: Northwind Health` 0.763
- Threshold 0.70: **accept** (closest 0.632, 2 of 4 context chunks kept); required evidence complete in kept context
- Design note: Question avoids the client's name on purpose.

### C1 (complex): Is there a case study for a healthcare prospect, and does healthcare fit our ideal customer profile?

- Expected: `02_icp.md › Best-fit customers` (rank 2, distance 0.6418); `03_case_study.md › Case study: Northwind Health` (rank 3, distance 0.7237)
- Required evidence: “healthcare, financial services and retail”; “regional healthcare network”
- Actual top-3: #1 `02_icp.md › Ideal customer profile` 0.635; #2 `02_icp.md › Best-fit customers` 0.642; #3 `03_case_study.md › Case study: Northwind Health` 0.724
- Threshold 0.70: **accept** (closest 0.635, 2 of 4 context chunks kept); required evidence **incomplete** in kept context
- Design note: Needs the ICP industries (ICP doc) and the healthcare client (case study intro).

### C2 (complex): Does the Northwind Health project support our positioning of fixed-scope delivery with a clear handover?

- Expected: `02_icp.md › Competitive positioning` (rank 4, distance 0.8236); `03_case_study.md › Lessons` (rank 7, distance 0.915)
- Required evidence: “fixed-scope pricing and a clear handover”; “trained to maintain the pipelines”
- Actual top-3: #1 `03_case_study.md › Case study: Northwind Health` 0.589; #2 `01_capabilities.md › Delivery modalities` 0.706; #3 `03_case_study.md › Results after six months` 0.782
- Threshold 0.70: **accept** (closest 0.589, 1 of 4 context chunks kept); required evidence **incomplete** in kept context
- Design note: Claim in the ICP doc, proof point in the case study Lessons.

### C3 (complex): Which of our standard engagement models matches how Northwind Health was delivered?

- Expected: `01_capabilities.md › Delivery modalities` (rank 3, distance 0.8543); `03_case_study.md › Results after six months` (rank 6, distance 0.9075)
- Required evidence: “fixed-scope project”; “fixed-scope engagement of ten weeks”
- Actual top-3: #1 `03_case_study.md › Case study: Northwind Health` 0.517; #2 `02_icp.md › Competitive positioning` 0.837; #3 `01_capabilities.md › Delivery modalities` 0.854
- Threshold 0.70: **accept** (closest 0.517, 1 of 4 context chunks kept); required evidence **incomplete** in kept context
- Design note: Model list (capabilities) must be matched with the delivery fact (case study).

### C4 (complex): Before pitching our AI assistant capability, which buying signals and poor-fit warnings should an SDR check?

- Expected: `02_icp.md › Buying signals` (rank 4, distance 0.7932); `02_icp.md › Poor-fit customers` (rank 10, distance 0.9137); `01_capabilities.md › Applied AI and Machine Learning` (rank 1, distance 0.5989)
- Required evidence: “job postings for data engineers”; “no data team”; “retrieval-augmented assistants”
- Actual top-3: #1 `01_capabilities.md › Applied AI and Machine Learning` 0.599; #2 `01_capabilities.md › Capabilities overview` 0.714; #3 `03_case_study.md › What Kai's Company did` 0.761
- Threshold 0.70: **accept** (closest 0.599, 1 of 4 context chunks kept); required evidence **incomplete** in kept context
- Design note: Three sections across two documents.

### C5 (complex): How do we position against large consultancies, and what do we hand over to the client at the end of a model build?

- Expected: `02_icp.md › Competitive positioning` (rank 1, distance 0.6186); `01_capabilities.md › Applied AI and Machine Learning` (rank 2, distance 0.7364)
- Required evidence: “slower and costlier”; “handover guide”
- Actual top-3: #1 `02_icp.md › Competitive positioning` 0.619; #2 `01_capabilities.md › Applied AI and Machine Learning` 0.736; #3 `03_case_study.md › Lessons` 0.762
- Threshold 0.70: **accept** (closest 0.619, 1 of 4 context chunks kept); required evidence **incomplete** in kept context
- Design note: Positioning (ICP doc) plus the concrete handover artefact (capabilities).

### U1 (unanswerable): What is the company's refund policy for cancelled projects?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `03_case_study.md › Results after six months` 0.773; #2 `03_case_study.md › Lessons` 0.923; #3 `02_icp.md › Competitive positioning` 0.982
- Threshold 0.70: **refuse** (closest 0.773, 0 of 4 context chunks kept)
- Design note: Plausible business topic that no document covers.

### U2 (unanswerable): What hourly rate does Kai's Company charge for a data engineer?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `01_capabilities.md › Capabilities overview` 0.527; #2 `03_case_study.md › What Kai's Company did` 0.655; #3 `02_icp.md › Competitive positioning` 0.719
- Threshold 0.70: **accept** (closest 0.527, 2 of 4 context chunks kept)
- Design note: Hard negative: documents mention fixed-scope pricing and engineers but give no rates.

### U3 (unanswerable): How many employees does Kai's Company have?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `01_capabilities.md › Capabilities overview` 0.472; #2 `03_case_study.md › What Kai's Company did` 0.608; #3 `02_icp.md › Competitive positioning` 0.697
- Threshold 0.70: **accept** (closest 0.472, 3 of 4 context chunks kept)
- Design note: Hard negative: 'employees' appears only as the size of TARGET customers (500 to 5,000).

### U4 (unanswerable): Who won the football world cup?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `01_capabilities.md › Analytics and Dashboards` 1.209; #2 `02_icp.md › Competitive positioning` 1.217; #3 `02_icp.md › Best-fit customers` 1.221
- Threshold 0.70: **refuse** (closest 1.209, 0 of 4 context chunks kept)
- Design note: Completely off-topic control.

## 4. Cross-document questions: where the second document went

For each expected section: its rank among all 15 chunks, its distance, and its status at 0.70 with a top-4 context.

| ID | Expected section | Rank | Distance | Status @0.70 |
|---|---|---|---|---|
| C1 | 02_icp.md › Best-fit customers | 2 | 0.6418 | in context |
| C1 | 03_case_study.md › Case study: Northwind Health | 3 | 0.7237 | retrieved (#3) but over threshold |
| C2 | 02_icp.md › Competitive positioning | 4 | 0.8236 | retrieved (#4) but over threshold |
| C2 | 03_case_study.md › Lessons | 7 | 0.915 | ranked #7, outside top-4 |
| C3 | 01_capabilities.md › Delivery modalities | 3 | 0.8543 | retrieved (#3) but over threshold |
| C3 | 03_case_study.md › Results after six months | 6 | 0.9075 | ranked #6, outside top-4 |
| C4 | 02_icp.md › Buying signals | 4 | 0.7932 | retrieved (#4) but over threshold |
| C4 | 02_icp.md › Poor-fit customers | 10 | 0.9137 | ranked #10, outside top-4 |
| C4 | 01_capabilities.md › Applied AI and Machine Learning | 1 | 0.5989 | in context |
| C5 | 02_icp.md › Competitive positioning | 1 | 0.6186 | in context |
| C5 | 01_capabilities.md › Applied AI and Machine Learning | 2 | 0.7364 | retrieved (#2) but over threshold |

### How many chunks are needed to cover every expected section?

Ignoring the threshold: complex questions whose expected sections ALL rank within the top-k of the 15 chunks.

| Top-k | 3 | 4 | 6 | 8 | 10 |
|---|---|---|---|---|---|
| Complex questions fully covered | 2/5 (40%) | 2/5 (40%) | 3/5 (60%) | 4/5 (80%) | 5/5 (100%) |

A bigger k recovers more of the second document but passes more unrelated text to the model; with only 15 chunks, k=10 is two-thirds of the whole index, so this table shows the ranking is weak, not that k=10 is a good setting.

## 5. Analysis

*Written by hand from the tables above (index of 15 chunks, `bge-small-en-v1.5`). If the corpus, chunking or model changes, re-run `python -m rag.evaluate` and re-check these statements.*

**Headline.** Retrieval finds *a* relevant section most of the time (top-3 hit 9/11) but ranks the *best* one first only 5/11 times, and the distance threshold cannot separate answerable from unanswerable questions on this set. No threshold has zero errors; the distance ranges overlap.

**Why top-1 misses (6 of 11 answerable).** Five of the six top-1 misses (D3, D4, C1, C2, C3) returned a short *introductory* chunk instead of the answer section: `Capabilities overview` (D3, D4), `Ideal customer profile` (C1) and `Case study: Northwind Health` (C2, C3). These chunks carry the company or client name and little else, so any question that names "Kai's Company" or "Northwind Health" is pulled towards them. The sixth (D6) returned a neighbouring section of the same document, with the expected section second.

**Why no threshold works.** Distance here reflects topic and entity overlap, not whether the specific fact exists.
- The two hard negatives that name the company, U2 (hourly rate, 0.527) and U3 (employee count, 0.472), are *closer* than most correct answers; U3 is as close as D1 (0.472), the best direct question. Any threshold that refuses them (below about 0.47) would also refuse most answerable questions: 7 of 11 are refused at 0.55.
- 0.65 to 0.75 is the only region with no false rejections and at most two false acceptances; at 0.80 and above the near-domain U1 (0.773) is also accepted. 0.70 sits inside that region, so I have **not** changed it.
- Leave-one-out confirms the fragility: 12/15, with the held-out misses all on the unanswerable questions (U1 to U3).
- Conclusion: 0.70 is a coarse filter for clearly off-topic questions (it refuses U4 at 1.209 and U1 at 0.773). It is **not** a guard against hard negatives. The model-side `INSUFFICIENT_EVIDENCE` refusal has to carry that load, and its effectiveness is untested until a model is connected.

**Why cross-document questions fail.** By rank alone only 2/5 complex questions (C1, C5) have all expected sections in the top 4; once the 0.70 context filter is applied, **0/5** have complete evidence. The missing sections ranked 2nd to 10th, at distances of 0.72 to 0.92, similar to the distances of unanswerable questions' best hits (0.77 to 1.2).
1. *One query vector for two intents.* A question about the ICP *and* a case study lands between the two topics, nearest the generic intro chunks, so neither target section ranks first (C2, C3 returned only the Northwind intro chunk as top-1).
2. *Chunks have no context of their own.* `Lessons` never mentions Northwind Health, and `Poor-fit customers` never mentions AI assistants, so queries naming the client or the capability do not match them (C2 expected `Lessons` ranks 7th; C4 expected `Poor-fit customers` ranks 10th).
3. *One threshold doing two jobs.* The same cut-off decides whether to answer *and* which chunks to pass on. At 0.70, 6 of the 11 accepted questions have incomplete evidence (all five complex ones, plus D4): C1's second section (0.724, rank 3) and C5's (0.736, rank 2) are only just over the line and would have been included by a rank-based rule.
4. *Small k.* The default context of 4 chunks cuts off the sections ranked 6th, 7th and 10th. Coverage of all expected sections reaches 3/5 at k=6, 4/5 at k=8 and 5/5 only at k=10, two-thirds of this tiny index, which indicates weak ranking rather than a workable setting.

**Options to test next (not implemented, no changes made).**
- Prepend the document title and section heading to each chunk before embedding, so `Lessons` is embedded as "Case Study - Northwind Health › Lessons".
- Separate the *answer/refuse gate* (closest distance) from *context selection* (top-k by rank, perhaps with a relative cut-off such as "within X of the best hit").
- Merge or drop the near-empty intro chunks, which act as magnets.
- For multi-part questions, decompose into sub-queries (needs a model call) and merge the results; optionally add a reranker or keyword (hybrid) search.
- Re-run this evaluation after each change, and grow the question set (especially unanswerable and cross-document questions) before trusting any threshold.

## Limitations

- 15 questions written by the same author as the corpus: wording overlaps the documents more than real users' will.
- A 15-chunk synthetic corpus is far easier than a real library; expect lower hit rates and tighter margins at scale.
- Hit rates use section-level expectations; a near-duplicate section elsewhere can be a legitimate answer yet count as a miss.
- Retrieval only. Whether a model writes a correct, faithful, well-cited answer from this context is **not measured here**.
