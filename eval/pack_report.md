# Knowledge pack evaluation (seven approved documents)

Index: 53 chunks, 7 documents (fingerprint 6d7a23626eb5). Real local FastEmbed vectors and Chroma. No hosted or paid call was made: the Fireworks pipeline was exercised with MOCK models only.

| Category | Offline engine (real) | Hosted pipeline + faithful mock |
|---|---|---|
| direct | 7/8 | 8/8 |
| cross-document | 2/5 | 4/5 |
| unanswerable | 7/7 | 7/7 |

Hallucinating mock (invents '150 dollars per hour' with a fake quote): invented text shown to the user in **0/20** questions (the evidence check rejects it every time).

## Per question

### D1 (direct): What are Kai's Company's core AI evaluation capabilities?
- Offline: **PASS** · answered · cited: 01_capabilities.md, 02_icp_model_evaluation.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 01_capabilities.md
- Answer: Support may include rubric-based quality review, prompt evaluation and expert assessment of AI outputs. Model evaluation and benchmarking; human evaluation and preference judgments; prompt/response evaluation; AI agent and computer-use-agent testing; model validation; adversarial testing, red teaming and trust-and-safety assessments; specialized evaluators a

### D2 (direct): Which buyer personas should we target at a speech AI company?
- Offline: **PASS** · answered · cited: 03_icp_multilingual_speech_audio.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 03_icp_multilingual_speech_audio.md
- Answer: Executive sponsors: CTO, VP AI/ML, Head of Speech AI, Head of Conversational AI. Technical buyers: Head of ASR, Speech ML Lead, Director of AI Data, Head of Data Operations, Speech Data Engineering Lead.

### D3 (direct): Which priority segments does the robotics ICP list as Tier 1?
- Offline: **PASS** · answered · cited: 04_icp_robotics.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 04_icp_robotics.md
- Answer: Tier 3: robotics research labs. Tier 1: humanoid robotics, home/consumer robotics, autonomous vehicles and ADAS, robot learning/embodied AI. Tier 2: warehouse/logistics robotics, industrial robotics, drones/autonomous aerial systems, medical robotics and agricultural robotics.

### D4 (direct): What was the scope of the LLM evaluation case study?
- Offline: **PASS** · answered · cited: 05_case_study_model_evaluation.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 05_case_study_model_evaluation.md
- Answer: The source engagement describes a large batch of evaluation tasks, with several independent reviews of each prompt and a structured set of rubric questions per task. The case study reports support for high-volume evaluation throughput, improved consistency through multiple reviews, structured assessment across multiple model-quality dimensions and evidence-b

### D5 (direct): Which devices and video settings were used in the first-person household activity engagement?
- Offline: **FAIL** · answered · cited: 06_case_study_physical_ai.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 06_case_study_physical_ai.md
- Answer: Collection of first-person household activity recordings for an unnamed AI data program. Capture physical household tasks from a consistent first-person viewpoint while maintaining device, resolution, privacy and submission quality requirements. Broader first-person household activity coverage, more consistent activity recordings and privacy/QC controls in t

### D6 (direct): How was multilingual transcription work organized and how large was the program?
- Offline: **PASS** · answered · cited: 03_icp_multilingual_speech_audio.md, 07_case_study_multilingual.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 07_case_study_multilingual.md
- Answer: Transcription and annotation operations across a reported multi-language program. Large-scale multilingual transcription and annotation operations for an unnamed AI data program. The source describes an expanded multi-language program, with a planned pool of candidates for each language and a large resource base overall.

### D7 (direct): Who are the evaluation owners at AI model development companies?
- Offline: **PASS** · answered · cited: 02_icp_model_evaluation.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 02_icp_model_evaluation.md
- Answer: Evaluation owners: Head of AI Evaluation, Head of Model Quality, Evaluation Lead, Model Validation Lead.

### D8 (direct): What are the layers of Kai's Company's core delivery model?
- Offline: **PASS** · answered · cited: 01_capabilities.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 01_capabilities.md
- Answer: Four complementary layers support engagements: (1) human contributors and domain expertise, (2) technology, AI/ML automation and digital workflows, (3) global language, market and industry expertise, and (4) security, compliance and quality guardrails.

### X1 (cross-document): Compare the buying personas for robotics companies and for speech AI companies.
- Offline: **FAIL** · answered · cited: 02_icp_model_evaluation.md, 03_icp_multilingual_speech_audio.md, 04_icp_robotics.md
- Hosted pipeline, faithful mock: **FAIL** · answered · cited: 02_icp_model_evaluation.md
- Answer: Decision makers: CTO, Chief AI Officer, VP AI/ML, VP Robotics, VP Engineering, Head of Robotics, Head of AI/ML. Technical buyers: Director of Robotics, Director of AI/ML, Director of Data, Robotics Engineering Manager, ML Engineering Manager, Head of Data Operations, Head of AI Evaluation. Commercial stakeholders: procurement, sourcing, vendor management and

### X2 (cross-document): Which case study supports the multilingual speech ICP, and what does the ICP say about evidence?
- Offline: **FAIL** · answered · cited: 03_icp_multilingual_speech_audio.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 03_icp_multilingual_speech_audio.md
- Answer: This ICP is an adaptation synthesized from the supplied capability deck and the speech/audio/transcription engagements in the case-study deck. It is **not** a separately supplied or independently validated original ICP.

### X3 (cross-document): What capabilities and which ideal customer profile relate to the LLM evaluation case study?
- Offline: **FAIL** · partial · cited: 02_icp_model_evaluation.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 05_case_study_model_evaluation.md
- Answer: Partial answer: only part of your question is supported by the approved documents.  Need for specialist judgments → domain experts, technical experts, language specialists and specialized evaluators. Need for evaluation data → collection, annotation, enrichment, preference data and QA. Continuous evaluation across tasks, languages and domains → model evaluat

### X4 (cross-document): What privacy or compliance controls appear for physical-AI data collection and in the general capabilities?
- Offline: **PASS** · answered · cited: 01_capabilities.md, 06_case_study_physical_ai.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 06_case_study_physical_ai.md
- Answer: Real-world physical-task data collection; first-person or egocentric activity video; human demonstrations; sensor and LiDAR/geospatial data; environment data; annotation and physical-world validation support. Broader first-person household activity coverage, more consistent activity recordings and privacy/QC controls in the collection workflow. These are rel

### X5 (cross-document): Describe the first-person activity data case study and its limitations.
- Offline: **PASS** · answered · cited: 06_case_study_physical_ai.md
- Hosted pipeline, faithful mock: **PASS** · answered · cited: 06_case_study_physical_ai.md
- Answer: Collection of first-person household activity recordings for an unnamed AI data program. Broader first-person household activity coverage, more consistent activity recordings and privacy/QC controls in the collection workflow. The source does not quantify model-performance gains. The source connects the dataset to embodied-AI and activity-understanding workf

### U1 (unanswerable): What is Kai's Company's hourly price?
- Offline: **PASS** · refused (nothing_supported) · cited: none
- Hosted pipeline, faithful mock: **PASS** · refused · cited: none
- Answer: I don't have enough evidence in the approved GTM documents to answer that. Try rephrasing, or add a relevant document to the knowledge base.

### U2 (unanswerable): Which named customer bought these services?
- Offline: **PASS** · refused (gate) · cited: none
- Hosted pipeline, faithful mock: **PASS** · refused · cited: none
- Answer: I don't have enough evidence in the approved GTM documents to answer that. Try rephrasing, or add a relevant document to the knowledge base.

### U3 (unanswerable): What will Kai's Company's revenue be in five years?
- Offline: **PASS** · refused (nothing_supported) · cited: none
- Hosted pipeline, faithful mock: **PASS** · refused · cited: none
- Answer: I don't have enough evidence in the approved GTM documents to answer that. Try rephrasing, or add a relevant document to the knowledge base.

### U4 (unanswerable): By what percentage did the LLM evaluation case study improve model accuracy?
- Offline: **PASS** · refused (documented_gap) · cited: 05_case_study_model_evaluation.md
- Hosted pipeline, faithful mock: **PASS** · refused · cited: none
- Answer: The approved documents say this is not available: "No numerical accuracy uplift or financial return is reported." [05_case_study_model_evaluation.md › Reported outcomes]. I won't guess a figure or detail they do not state.

### U5 (unanswerable): Who won the football world cup?
- Offline: **PASS** · refused (gate) · cited: none
- Hosted pipeline, faithful mock: **PASS** · refused · cited: none
- Answer: I don't have enough evidence in the approved GTM documents to answer that. Try rephrasing, or add a relevant document to the knowledge base.

### U6 (unanswerable): What is the street address of Kai's Company's headquarters?
- Offline: **PASS** · refused (nothing_supported) · cited: none
- Hosted pipeline, faithful mock: **PASS** · refused · cited: none
- Answer: I don't have enough evidence in the approved GTM documents to answer that. Try rephrasing, or add a relevant document to the knowledge base.

### U7 (unanswerable): Which competitors does Kai's Company beat on price?
- Offline: **PASS** · refused (nothing_supported) · cited: none
- Hosted pipeline, faithful mock: **PASS** · refused · cited: none
- Answer: I don't have enough evidence in the approved GTM documents to answer that. Try rephrasing, or add a relevant document to the knowledge base.


## How to read this

- **Offline engine column is the real measurement.** Real local embeddings, real Chroma index, no model. It answers by quoting the best matching
  sentence(s), so it can name the right document and quote real text, but it cannot compose an answer across passages.
- **Hosted pipeline column is a test of the verification code, not of Fireworks.** The "faithful mock" model is scripted to find the key phrase, so
  8/8 and 4/5 only show that, given a well-behaved model, the pipeline produces cited answers and refuses when the model says it has no evidence.
  Real Fireworks answer quality has **not** been measured: no live call was approved.
- **The hallucinating mock is the meaningful safety result:** a model that invents "150 dollars per hour" and supports it with a quote that is in no
  passage is never shown to the user (0 of 20 questions), because the code checks that every quote exists in a cited passage.

## What the offline engine gets wrong (4 of the 20, all answerable questions)

| Question | What happened |
|---|---|
| D5 devices and video settings | Picked the "engagement type" sentence, not the Scope sentence that lists consumer mobile devices and high-definition capture. It matches the subject words, not the attribute asked for. |
| X1 compare robotics and speech personas | Cited robotics, speech and (spuriously) the model-evaluation ICP, and did not quote the speech "Head of ASR" line. |
| X2 case study plus what the ICP says about evidence | Returned the ICP's "source basis" sentence, not the case study. |
| X3 capabilities and which ICP fits the LLM evaluation case study | Second half unsupported, so a partial answer. |

None of these produced a wrong or invented statement: each quotes real text with a real citation. They are incomplete or off-target answers.

## Refusals (7 of 7 unanswerable correct)

Hourly price, a named customer, five-year revenue, an accuracy percentage the case study does not report, the football world cup, a street address and
competitor price comparisons are all refused. Two mechanisms matter: a sentence must share topic words with the question (so a generic
"Kai's Company is a platform-led..." sentence cannot answer a price question), and when the documents themselves say a figure is not reported, the refusal
quotes that statement with its citation (for the accuracy question: "No numerical accuracy uplift or financial return is reported").

## Bugs found and fixed while evaluating

- "Which buyer personas should we **target**" was routed to the metrics calculator because of the word "target" and answered with revenue figures.
  Fixed (only metric phrasings now select the target topic). "Revenue in **five years**" was likewise answered with won revenue so far; forecast and
  multi-year phrasings are no longer metric lookups.
- The first offline engine answered the hourly-price question with the positioning sentence. Fixed with the topic-word requirement above.

## Limits

- 20 questions written by the same person who tuned the engine's keyword rules: the results are optimistic and not a held-out test.
- Thresholds (gate distance 0.70, similarity floor 0.62, keyword weights) remain provisional.
- Operational figures from the source case studies (task volumes, language counts, resource totals, durations) were deliberately generalised in the
  knowledge documents before publication, so the questions test capabilities, segments, personas and workflows rather than exact numbers.
