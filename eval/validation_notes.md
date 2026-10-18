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
