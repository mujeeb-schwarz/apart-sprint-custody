# Appendix F. Predictions as filed

Before the test set ran, the AI assistant and I each wrote predictions alone, then compared them and filed one page on Fri 13 Nov at 22:33 Pacific, an hour before the code was frozen, and filed the same page again at 23:31 with the fingerprint of the final scorer. The page's fingerprint is stored with the run (`config/predictions_filed.json`), and the page is in the repository (`docs/predictions_as_filed.md`). In the public copy the page has my name, a session label and one local path replaced, so the stored fingerprint is that of the page as filed, which I keep.

Table F1. Filed grades beside the results.

<!-- widths: 8,30,22,18,22 -->
| Rule | Filed: Promised, Monitored, Checked | Result | Filed least that is enough, counting connection mistakes | Result on planted violations |
|---|---|---|---|---|
| 1 | fail, pass, pass | as filed | Proven | Monitored |
| 2 | fail, fail, pass | as filed | Proven | Checked |
| 3 | fail, fail, pass | as filed | Proven | Checked |
| 4 | fail, fail, pass | Monitored passed and Checked failed | Checked | Monitored |
| 5 | fail, fail, and for Checked the author pass, the assistant fail | Promised passed; Monitored and Checked failed | the author Checked, the assistant none | Promised |
| 6 | fail, pass, pass | as filed | Monitored | Monitored |

The filed plan named Proven, which is Checked with the proof step, for rules 1 to 3, because both predictions expected connection mistakes that Checked alone lets through. That expectation held: 9 of 10 known connection mistakes got past Checked alone (Section 4.4). Table 2 reports planted violations only, so its row reads Monitored, Checked and Checked.

![Figure F1. For each rule and method, the grade filed before the run and the result. Three results differ from what both predictions filed, and one cell was filed with two different predictions. The results for rules 4 and 5 come from the second round of planted texts (Appendix G).](../figures/figF1_predictions.png)

Table F1 and Figure F1 set the filed grades beside the results. Of the 17 grades on which both predictions agreed, 14 came out as filed. The three surprises were that Monitored passed rule 4, Checked failed rule 4 and Promised passed rule 5. All three come from the second round of planted texts for rules 4 and 5 (Appendix G). In the first round Checked passed rule 4 as filed, because the wrong sources written in words had been dropped before the run, and rule 5 was inconclusive for every method, with 7 violations. Four numbers were filed as well.

1. Misses under Promised across rules 1 to 3: filed 151 to 225 of 300. Result: 112, below the filed range. The review's AI found 88 of 100 edits of the log.
2. Misses among the planted changes of certainty: filed 5 to 20 of 100 for Promised and for Monitored, and for Checked 0 to 4 (mine) or 18 (the assistant's). Result on 99 violations: 0, 0 and 2.
3. Natural violations in 413 clean questions: filed 11 to 40. Result: 7.
4. Connection mistakes that Checked alone lets happen: filed "most or all of the list". Result: 9 of 10.

One filed reason could be tested, and it held. For rule 6 the page says that the review looks for the AI mark only in the final note and that the next AI step puts a fresh mark on its own text. I measured that split: 40 of 40 caught in the final note, 0 of 60 earlier.

**The witness test.** For the witness test of Sections 4.3 and 4.4 only the AI assistant filed predictions, in the log of changes, before any code for it was written. Careless forger: at least 67 of 100 flagged by the chain alone and 100 with the witness; result 100 and 100. Careful forger: 0 and 100; result 0 and 100. Operator: 0 and 0; result 0 and 100, because a receipt issued before the edit still gave the edit away. The fourth forger, who rebuilds that receipt, was added after these results and was flagged by neither check.

**The forger test of the system's own log.** The AI assistant filed predictions in the log of changes on Sun 15 Nov at 19:32, before any code: the review's AI would flag 30 to 60 of 100 edits under the program forger and 20 to 40 under GPT-6.1. The results were 56 and 15. The first prediction held, and the second was too high. By kind, it expected most removed entries to stay flagged, which held for the program (33 of 33) and failed for GPT-6.1 (15 of 33), and most changed and added entries to be missed, which held except for the program's changed entries (18 of 34 flagged).

