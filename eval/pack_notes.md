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
