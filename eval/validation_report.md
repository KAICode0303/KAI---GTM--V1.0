# Hoomi retrieval validation (held-out questions)

Scope: **retrieval only** (local FastEmbed `BAAI/bge-small-en-v1.5` + Chroma, 15 chunks from 3 synthetic documents). No LLM was used, so this says **nothing about generated-answer accuracy**. Distances are Chroma's L2 distance for this model (smaller = closer), not a 0-1 score. Questions: `eval/validation_questions.json`. Raw data: `eval/validation_results.json`. Gate distance 0.70; context policy: **top-6**.

**Settings in force (not changed for this run):** gate distance 0.70; context policy top-6; chunks embedded with `title+section`; 15 chunks in the index.

## Failures at the current settings

- **V2** (direct): How many shared KPIs did we define for the healthcare client, and what did we launch alongside them?
  - top-1 is `03_case_study.md › Lessons` (0.658), not an expected section
- **V3** (direct): What kind of company would we avoid selling to?
  - FALSE REJECTION: closest chunk `Poor-fit customers` is 0.852, over the 0.70 gate
- **V4** (complex): Is a ten-week fixed-scope engagement typical for us, or was Northwind Health unusual?
  - expected `01_capabilities.md › Data Engineering` not in context (rank 10, distance 0.9401)
  - required evidence missing from context: “eight to twelve weeks”
- **V5** (complex): What KPI and dashboard work do we offer, and what did that look like for Northwind Health?
  - top-1 is `03_case_study.md › Lessons` (0.500), not an expected section
- **V6** (complex): What evidence do we have that clients can run our deliverables without us?
  - FALSE REJECTION: closest chunk `Poor-fit customers` is 0.810, over the 0.70 gate
- **V7** (unanswerable): How much did Northwind Health pay for the project?
  - FALSE ACCEPTANCE: closest `03_case_study.md › Results after six months` 0.566 is within the gate; 6 chunk(s) of unrelated text would go to the model
- **V8** (unanswerable): Do we build our data warehouses on Snowflake, BigQuery or Redshift?
  - FALSE ACCEPTANCE: closest `01_capabilities.md › Data Engineering` 0.584 is within the gate; 6 chunk(s) of unrelated text would go to the model
- **V9** (unanswerable): Does Kai's Company hold HIPAA or SOC 2 certification?
  - FALSE ACCEPTANCE: closest `03_case_study.md › What Kai's Company did` 0.590 is within the gate; 6 chunk(s) of unrelated text would go to the model

Near the 0.70 gate (within 0.03): none.


## Does it generalise? Same settings, two question sets

| Question set | Top-1 hit | Top-3 hit | All expected in top-3 | Required evidence complete in context | ...of which complex | False rejections | Correct refusals | False acceptances | Avg chunks given |
|---|---|---|---|---|---|---|---|---|---|
| Original 15 questions (used to build the changes) | 6/11 (55%) | 10/11 (91%) | 8/11 (73%) | 10/11 (91%) | 4/5 | 0 | 2/4 | 2 | 6.0 |
| **Validation set (10, held out)** | 3/6 (50%) | 5/6 (83%) | 4/6 (67%) | 3/6 (50%) | 1/3 | 2 | 1/4 | 3 | 6.0 |

*The first set was used to build and tune the retrieval changes, so it is optimistic; the second was written afterwards and was not used to change any setting. With so few questions, one question moves a percentage by 9-25 points.*


## 1. Retrieval quality (independent of any threshold)

| Group | Questions | Top-1 hit | Top-3 hit | ALL expected sections in top-3 | ALL expected in top-4 | Required evidence in top-3 |
|---|---|---|---|---|---|---|
| direct | 3 | 2/3 (67%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) | 3/3 (100%) |
| complex | 3 | 1/3 (33%) | 2/3 (67%) | 1/3 (33%) | 1/3 (33%) | 1/3 (33%) |
| all answerable | 6 | 3/6 (50%) | 5/6 (83%) | 4/6 (67%) | 4/6 (67%) | 4/6 (67%) |

*Top-1 hit*: the closest chunk is one of the expected sections. *Top-3 hit*: at least one expected section is in the top 3. For complex questions, the *ALL* columns are the cross-document test: every expected section must be present.

## 2. Gate comparison

The *gate* accepts a question when its closest chunk is within the distance, otherwise refuses. Context selection then follows the policy (top-6) and no longer depends on the gate distance. Answerable: 6, unanswerable: 4.

| Gate distance | Correct accepts | **False rejections** | Correct refusals | **False acceptances** | Evidence complete in context | Accepted but required evidence missing | Accepted but an expected section missing |
|---|---|---|---|---|---|---|---|
| 0.55 | 3/6 | 3 | 4/4 | 0 | 2/6 | 1 | 1 |
| 0.60 | 3/6 | 3 | 1/4 | 3 | 2/6 | 1 | 1 |
| 0.65 | 3/6 | 3 | 1/4 | 3 | 2/6 | 1 | 1 |
| 0.70 (provisional) | 4/6 | 2 | 1/4 | 3 | 3/6 | 1 | 1 |
| 0.75 | 4/6 | 2 | 0/4 | 4 | 3/6 | 1 | 1 |
| 0.80 | 4/6 | 2 | 0/4 | 4 | 3/6 | 1 | 1 |
| 0.85 | 5/6 | 1 | 0/4 | 4 | 3/6 | 2 | 2 |
| 0.90 | 6/6 | 0 | 0/4 | 4 | 4/6 | 2 | 2 |

*False rejection* = an answerable question refused (Hoomi would wrongly say it lacks evidence). *False acceptance* = an unanswerable question accepted (the model would be given irrelevant context and could hallucinate).

### Context-selection policies (gate fixed at 0.70)

| Policy | Evidence complete | ...complex | Accepted but a section missing | Avg chunks given |
|---|---|---|---|---|
| Old rule (top-4, each within gate) | 3/6 (50%) | 1/3 | 1 | 3.0 |
| top-4 | 3/6 (50%) | 1/3 | 1 | 4.0 |
| top-6 | 3/6 (50%) | 1/3 | 1 | 6.0 |
| top-8 | 3/6 (50%) | 1/3 | 1 | 8.0 |
| top-6, best+0.15 | 3/6 (50%) | 1/3 | 1 | 3.2 |
| top-6, best+0.25 | 3/6 (50%) | 1/3 | 1 | 4.2 |
| top-8, best+0.25 | 3/6 (50%) | 1/3 | 1 | 4.8 |

These are descriptive. The gate does not change with the policy (refusals are identical in every row); only what the model sees does. The default is not tuned to this table: a larger k trades completeness for more irrelevant text.


### Separation and robustness

- Closest-chunk distance, **answerable** questions: min 0.399, median 0.579, max 0.852.
- Closest-chunk distance, **unanswerable** questions: min 0.566, median 0.587, max 0.730.
- The groups **overlap**: worst answerable (0.852) is farther than best unanswerable (0.566); no single gate distance is error-free.
- Gate distances with zero errors on this set: none.
- Leave-one-out (choose a gate distance on 9 questions, test on the held-out one): 2/10 correct; errors on V2, V3, V5, V6, V7, V8, V9, V10. Chosen distances ranged 0.49 to 1.04.
- With only 10 questions (4 unanswerable) and a 15-chunk corpus, any distance read off this table is a hypothesis, not a calibrated setting. A larger corpus will raise the distances of unrelated questions and reduce the margin.

## 3. Question-level results

Gate 0.70; context policy top-6.

| ID | Type | Top-1 chunk (distance) | Top-1 hit | Top-3 hit | Gate @0.70 | Evidence complete | Outcome |
|---|---|---|---|---|---|---|---|
| V1 | direct | 01_capabilities.md › Data Engineering (0.399) | yes | yes | accept | yes | correct accept |
| V2 | direct | 03_case_study.md › Lessons (0.658) | no | yes | accept | yes | correct accept |
| V3 | direct | 02_icp.md › Poor-fit customers (0.852) | yes | yes | refuse | - | FALSE REJECTION |
| V4 | complex | 03_case_study.md › Results after six months (0.425) | yes | yes | accept | no | correct accept |
| V5 | complex | 03_case_study.md › Lessons (0.500) | no | yes | accept | yes | correct accept |
| V6 | complex | 02_icp.md › Poor-fit customers (0.810) | no | no | refuse | - | FALSE REJECTION |
| V7 | unanswerable | 03_case_study.md › Results after six months (0.566) | - | - | accept | - | FALSE ACCEPTANCE |
| V8 | unanswerable | 01_capabilities.md › Data Engineering (0.584) | - | - | accept | - | FALSE ACCEPTANCE |
| V9 | unanswerable | 03_case_study.md › What Kai's Company did (0.590) | - | - | accept | - | FALSE ACCEPTANCE |
| V10 | unanswerable | 02_icp.md › Competitive positioning (0.730) | - | - | refuse | - | correct refusal |

### V1 (direct): How long does a typical data engineering project take, and how many people work on it?

- Expected: `01_capabilities.md › Data Engineering` (rank 1, distance 0.3994)
- Required evidence: “two engineers and one lead”; “eight to twelve weeks”
- Actual top-3: #1 `01_capabilities.md › Data Engineering` 0.399; #2 `03_case_study.md › Results after six months` 0.709; #3 `03_case_study.md › The challenge` 0.767
- Gate 0.70: **accept** (closest 0.399); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: Paraphrase: 'project take' / 'people' instead of the document's 'delivery' / 'squad'.

### V2 (direct): How many shared KPIs did we define for the healthcare client, and what did we launch alongside them?

- Expected: `03_case_study.md › What Kai's Company did` (rank 2, distance 0.669)
- Required evidence: “twelve shared KPIs”; “executive dashboard”
- Actual top-3: #1 `03_case_study.md › Lessons` 0.658; #2 `03_case_study.md › What Kai's Company did` 0.669; #3 `01_capabilities.md › Analytics and Dashboards` 0.699
- Gate 0.70: **accept** (closest 0.658); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: Client not named. 'KPI' also appears in Analytics and Dashboards and in Lessons.

### V3 (direct): What kind of company would we avoid selling to?

- Expected: `02_icp.md › Poor-fit customers` (rank 1, distance 0.852)
- Required evidence: “no data team”; “staff augmentation”
- Actual top-3: #1 `02_icp.md › Poor-fit customers` 0.852; #2 `02_icp.md › Best-fit customers` 0.905; #3 `02_icp.md › Competitive positioning` 0.924
- Gate 0.70: **refuse** (closest 0.852); 0 chunk(s) given to the model
- Design note: Paraphrase: 'avoid selling to' for 'poor-fit'.

### V4 (complex): Is a ten-week fixed-scope engagement typical for us, or was Northwind Health unusual?

- Expected: `01_capabilities.md › Data Engineering` (rank 10, distance 0.9401); `03_case_study.md › Results after six months` (rank 1, distance 0.4254)
- Required evidence: “eight to twelve weeks”; “fixed-scope engagement of ten weeks”
- Actual top-3: #1 `03_case_study.md › Results after six months` 0.425; #2 `03_case_study.md › The challenge` 0.519; #3 `03_case_study.md › Lessons` 0.580
- Gate 0.70: **accept** (closest 0.425); 6 chunk(s) given to the model; required evidence **incomplete** in that context
- Design note: Typical duration (capabilities) compared with the case-study duration.

### V5 (complex): What KPI and dashboard work do we offer, and what did that look like for Northwind Health?

- Expected: `01_capabilities.md › Analytics and Dashboards` (rank 3, distance 0.6286); `03_case_study.md › What Kai's Company did` (rank 2, distance 0.5446)
- Required evidence: “KPI frameworks”; “twelve shared KPIs”
- Actual top-3: #1 `03_case_study.md › Lessons` 0.500; #2 `03_case_study.md › What Kai's Company did` 0.545; #3 `01_capabilities.md › Analytics and Dashboards` 0.629
- Gate 0.70: **accept** (closest 0.500); 6 chunk(s) given to the model; required evidence complete in that context
- Design note: Capability description plus its case-study instance.

### V6 (complex): What evidence do we have that clients can run our deliverables without us?

- Expected: `01_capabilities.md › Applied AI and Machine Learning` (rank 9, distance 0.9302); `03_case_study.md › Lessons` (rank 4, distance 0.9072)
- Required evidence: “client team can run it”; “trained to maintain the pipelines”
- Actual top-3: #1 `02_icp.md › Poor-fit customers` 0.810; #2 `01_capabilities.md › Delivery modalities` 0.845; #3 `02_icp.md › Buying signals` 0.879
- Gate 0.70: **refuse** (closest 0.810); 0 chunk(s) given to the model
- Design note: Handover promise (capabilities) plus the proof point (case study). No section names the question's words.

### V7 (unanswerable): How much did Northwind Health pay for the project?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `03_case_study.md › Results after six months` 0.566; #2 `03_case_study.md › The challenge` 0.586; #3 `03_case_study.md › Case study: Northwind Health` 0.596
- Gate 0.70: **accept** (closest 0.566); 6 chunk(s) given to the model
- Design note: Hard negative: the case study covers the project in detail but gives no price; it says figures are invented.

### V8 (unanswerable): Do we build our data warehouses on Snowflake, BigQuery or Redshift?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `01_capabilities.md › Data Engineering` 0.584; #2 `02_icp.md › Buying signals` 0.721; #3 `01_capabilities.md › Applied AI and Machine Learning` 0.803
- Gate 0.70: **accept** (closest 0.584); 6 chunk(s) given to the model
- Design note: Hard negative: documents say 'cloud warehouse' and 'lakehouses' but name no platform.

### V9 (unanswerable): Does Kai's Company hold HIPAA or SOC 2 certification?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `03_case_study.md › What Kai's Company did` 0.590; #2 `01_capabilities.md › Capabilities overview` 0.639; #3 `02_icp.md › Competitive positioning` 0.758
- Gate 0.70: **accept** (closest 0.590); 6 chunk(s) given to the model
- Design note: Hard negative: healthcare is a target industry and a case study, but no certifications are mentioned.

### V10 (unanswerable): Which named consulting firms do we compete against most often?

- Expected: **no supporting evidence in the corpus** (should be refused).
- Actual top-3: #1 `02_icp.md › Competitive positioning` 0.730; #2 `01_capabilities.md › Capabilities overview` 0.902; #3 `02_icp.md › Best-fit customers` 0.909
- Gate 0.70: **refuse** (closest 0.730); 0 chunk(s) given to the model
- Design note: Hard negative: Competitive positioning discusses 'large consultancies' generically and names none.

## 4. Cross-document questions: where the second document went

For each expected section: its rank among all 15 chunks, its distance, and whether the current policy (top-6) includes it.

| ID | Expected section | Rank | Distance | Status |
|---|---|---|---|---|
| V4 | 01_capabilities.md › Data Engineering | 10 | 0.9401 | ranked #10, outside top-6 |
| V4 | 03_case_study.md › Results after six months | 1 | 0.4254 | in context |
| V5 | 01_capabilities.md › Analytics and Dashboards | 3 | 0.6286 | in context |
| V5 | 03_case_study.md › What Kai's Company did | 2 | 0.5446 | in context |
| V6 | 01_capabilities.md › Applied AI and Machine Learning | 9 | 0.9302 | ranked #9, outside top-6 |
| V6 | 03_case_study.md › Lessons | 4 | 0.9072 | in context |

### How many chunks are needed to cover every expected section?

Ignoring any threshold: complex questions whose expected sections ALL rank within the top-k of the 15 chunks.

| Top-k | 3 | 4 | 6 | 8 | 10 |
|---|---|---|---|---|---|
| Complex questions fully covered | 1/3 (33%) | 1/3 (33%) | 1/3 (33%) | 1/3 (33%) | 3/3 (100%) |

A bigger k recovers more of the second document but passes more unrelated text to the model; with only 15 chunks, k=10 is two-thirds of the whole index, so this table shows how well the ranking works, not that k=10 is a good setting.

## 5. Analysis

*Written by hand from the tables above. These 10 questions were written after the retrieval changes, were not used to change any setting, and were run once. Nothing was tuned in response. Because they have now been seen, they should not be used to choose settings; a further fresh set would be needed for that.*

**Headline.** The improvements measured on the original 15 questions only partly held up. Ranking generalised moderately (top-3 hit 5/6 against 10/11; top-1 hit 3/6 against 6/11), but the answerability gate and cross-document evidence did **not**: 2 false rejections, 3 false acceptances (against 0 and 2), and required evidence complete in the context for 3/6 answerable questions (cross-document 1/3), against 10/11 (4/5). The original-set figures were optimistic, as expected for a set used while building the changes. With 6 answerable and 4 unanswerable questions, each question is worth 17 and 25 points, so the size of the drop is uncertain; the gate failures, however, repeat a weakness already seen on the original set.

**The distance gate cannot work on this set.** The groups overlap completely: median closest distance is 0.579 for answerable and 0.587 for unanswerable questions. No gate distance has zero errors, and leave-one-out is 2/10.
- *False rejections* are well-phrased questions that share few words with their answer: V3 ("What kind of company would we avoid selling to?", correct section ranked first but at 0.852) and V6 (0.810).
- *False acceptances* are questions that reuse the corpus's vocabulary: V7 (price of the Northwind project, 0.566), V8 (warehouse platforms, 0.584) and V9 (certifications for a healthcare-adjacent firm, 0.590). Only V10 (named competitors, 0.730) is refused, narrowly.
- So distance measures topical proximity, not whether the *specific fact* exists. A stricter gate (0.55) refuses all four unanswerable questions but rejects 3 of 6 answerable ones; a looser one accepts everything. Nothing was changed; this repeats the earlier conclusion that the model-side refusal, or a relevance check beyond distance, must carry hard negatives, and it remains untested.
- The three false acceptances each pass 6 chunks of unrelated text to the model.

**Cross-document failures.**
- *V6* ("run our deliverables without us"): neither expected section is near the top (rank 9 at 0.930 and rank 4 at 0.907). The question's wording ("run", "without us") shares almost no vocabulary with "handover guide" or "trained to maintain", and this small embedding model does not bridge that paraphrase gap. It is also falsely rejected.
- *V4* ("is a ten-week engagement typical?"): the case-study section is top-1 (0.425), but the "Data Engineering" section that states the typical duration is ranked 10th (0.940), because the question never mentions data engineering. The top-6 context misses it, so the evidence is incomplete.
- *V5* succeeds on evidence: both sections are within the top 3, although top-1 is the "Lessons" section, which mentions KPIs. Cross-document coverage, then, is 1 of 3 here, against 4 of 5 on the original set.

**What did generalise.** The direct, paraphrased questions rank well: V1 is top-1 at 0.399, and direct required evidence is within the top 3 for 3/3. V2 and V5 have the required evidence in context even though their top-1 is a neighbouring section. The title+section embedding and the separated context policy caused no problems, but they also did not help here: **every context policy in the grid scores the same 3/6**, because the remaining failures are ranking and gate failures, not context size. The original-set gain from the context policy therefore does not transfer to these questions.

**Not measured.** Retrieval only: nothing here measures whether a model writes a correct, faithful or well-cited answer. The set is small and written by one author who knows the corpus.

**Next candidates (none implemented; any choice needs a fresh third question set).**
- A relevance check beyond distance, such as a local cross-encoder reranker score or a model-side verifier, to separate hard negatives from abstractly phrased true questions.
- Hybrid search (keyword plus semantic) so exact terms such as "SOC 2" or "Snowflake" count as evidence of absence, and so paraphrases still match semantically.
- A larger local embedding model (needs a download, so it needs your approval) for paraphrase robustness.
- Query rewriting or decomposition for multi-part and abstract questions (needs a model call).
- Merge or drop the near-empty intro chunks that attract questions naming the company.

## Limitations

- 10 questions written by the same author as the corpus: wording overlaps the documents more than real users' will.
- A 15-chunk synthetic corpus is far easier than a real library; expect lower hit rates and tighter margins at scale.
- Hit rates use section-level expectations; a near-duplicate section elsewhere can be a legitimate answer yet count as a miss.
- Retrieval only. Whether a model writes a correct, faithful, well-cited answer from this context is **not measured here**.
