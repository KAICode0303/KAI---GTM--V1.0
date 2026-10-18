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
