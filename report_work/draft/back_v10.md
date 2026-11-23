## References

<!-- references -->

<!-- pagebreak -->

## Appendix A. Limitations, dual use and ethics

### A.1 What the results establish

In two flows on public data, for planted violations of known kinds, the results show which of three methods of checking detected each violation, graded against a pass mark that was filed before the run.

They do not establish the following.

- **How often violations occur.** I planted every violation. No result says that any vendor breaks a promise.
- **How a capable adversary fares.** The planted edits of a log leave contradictions. Against a program that tidies the edited log the review's AI caught 56 of 100 edits, and against GPT-6.1 it caught 15 (Appendix C, part C.8). A forger who knows more of the review may do better still.
- **That the witness is independent.** It ran in the same process as the flow, with a test key. If the vendor controls the witness, an edit of the record can be hidden, and Checked's catches on rule 3 then hold only against careless edits, unless a receipt saved before the edit survives (Section 4.4).
- **That Checked prevents every violation.** It blocked sends to unnamed places, and flagged missed deletions and edits only after they happened.
- **That the receipt reports deletions rightly.** The bench writes the receipt before the gate's last check at the close of a case. Where the gate flagged an overdue copy only at that close, the receipt still states that every copy was deleted in time. The grades rest on the gate's flags, and the receipt serves here only as a fingerprint of the record.
- **That a named source supports its claim.** Rule 4 checks that a true source is named.
- **That the answer key is free of error.** A judge model reads the texts of Experiment 2. Its question for rules 4 and 6 was corrected after the run. A second judge from another maker agreed on 783 of 800 sampled readings, and the planned human reading did not take place.
- **Behaviour at scale or on audio.** The bench has two flows, text only, and one family of models for the steps, the monitor, the review and the judge. Errors that these models share could move the measured catches up or down.
- **Independent cases.** Rule 2's 100 planted violations rest on 12 variants and rule 3's on 14. Where a program decides, the count repeats one behaviour, so I report kinds beside counts.

### A.2 Dual use

**A list of what a log review cannot see helps both sides.** The kinds of violation and the sealed attack ideas describe how to hide a send, a kept copy or an edit from each method. A vendor could use them to pass a review while breaking a promise. I publish the kinds and the counts, because a buyer needs the same list to know which promises a log review cannot back, and the kinds are short and known to practitioners. The repository leaves out the full text of the sealed attack ideas and the exact wording of the hidden instructions used in the test runs; the practice wording used in development remains in the code.

**A pass could be sold as a certificate.** "Checked passed" holds for planted violations with an honest witness. A vendor that runs its own witness, or quotes a pass without the kinds it covers, would mislead. Any claim built on this bench should name the kinds, the pass mark and who ran the witness.

**The record is itself sensitive.** A record of handovers shows who received whose words and when. The witness should hold fingerprints and no content, and the record needs its own deadline. A monitor is one more reader of the patient's words, which is a privacy cost of Monitored that my grades do not show.

**A monitor reads the attacker's text too.** In the hidden-instruction runs of Experiment 1 the monitor's own AI wrote out the hidden command in 56 of 100 answers. My programs ignore such lines, so no flag changed. Adaptive attacks on monitoring models [@terekhov] and on defences against prompt injection [@nasr] are documented, and I report the count so that a buyer does not take a monitor's presence for a guarantee.

### A.3 Ethics and personal data

All three data sets are public and were made for research. ACI-Bench holds mock consultations. MedEvidence holds questions and conclusions from published systematic reviews. Real-POCQi holds questions that physicians put to OpenEvidence, filtered by its authors for identifying details and lightly rewritten, with stored answers from four AI systems. I used the files as published and added no data about any person. The models received only these texts and the bench's own prompts, rewrites and instructions.

<!-- include: ../appendix/B_methods.md -->

<!-- include: ../appendix/C_results.md -->

<!-- include: ../appendix/D_standards.md -->

<!-- include: ../appendix/E_who_holds_what.md -->

<!-- include: ../appendix/F_predictions.md -->

<!-- include: ../appendix/G_changes_after_freeze.md -->

<!-- include: ../appendix/H_before_kickoff.md -->

<!-- include: ../appendix/I_llm_usage.md -->

<!-- include: ../appendix/J_data.md -->
