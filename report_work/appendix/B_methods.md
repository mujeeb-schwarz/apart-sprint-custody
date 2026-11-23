# Appendix B. Methods in detail

The wiring is in `wiring/wiring.json` and every setting in `config/design_choices.json`. Figure B1 draws the two experiments, and Table B1 compares the methods.

## The two experiments

![Figure B1. The two experiments and where each method looks. Read each row from left to right. The monitor reads every handover. The gate sits on every handover and deletion and keeps its own record, whose fingerprints go to the witness outside the vendor. The review reads the system's own log after the case. Each case runs under one method at a time: Promised uses the review, Monitored the review and the monitor, Checked the gate alone. The dashed box holds every place the flow touches, the practice's record and the patient's copy included. In the bench the witness ran in the same process (Appendix E).](../figures/figB1_two_flows.png)

Table B1. What each method is, what it reads and what it cannot see.

<!-- widths: 11,29,32,28 -->
| Method | What it is | What it reads, and when | What it cannot see |
|---|---|---|---|
| Promised | A review of every case: a program, then an AI model | The system's own log, the incoming answer and the final texts, after the case | What the log omits or misstates without contradicting itself |
| Monitored | Promised's review, and a monitor on every message (a program and an AI model) | The same, and each message as it is sent; it cannot stop one | What sends no message: a missed deletion, an edited log |
| Checked | A gate on every handover and deletion, with its own record and a witness. A program with no AI; no review, no monitor | The labels and the text of each handover as it happens; **it can stop a send** | A copy kept inside a step, a handover that skips the gate, and what a text means |
| Proven | Checked, and a proof step that searches the connections for a break of rules 1 to 3 | The description of how the steps are connected, before any case runs | Whether the running programs match the description |

In Experiment 1 a program hands the transcript from the transcribing service to the AI note writer, where Claude Haiku 5.5 drafts the visit note. A program files the draft in the medical record. Four deletions remove the senders' copies and the medical record's draft.

In Experiment 2 the answer already exists at the evidence tool: the real tool's stored answer, or for a graded question a program's answer in fixed wording from the experts' conclusion and grade. After a program hands it to the doctor's workspace, one AI step writes a plan and a second writes the note for the patient.

Nine places are named to the patient. Most copies must be deleted within 10 steps of the bench's clock and the cache and retry queue within 4. Four unnamed places exist only as targets of planted violations. At the end of a case the clock passes every deadline and each deletion runs once more, late.

## The methods as built

**Promised.** After the case a review reads the system's own log, the incoming answer, the final texts and the named places. Its program flags a logged send to an unnamed place (rule 1), a copy in the log with no logged deletion in time (rule 2), and a final note for the patient with no source tag (rule 4) or no AI mark (rule 6). Its AI part on Claude Sonnet 5.5 is asked about all six rules, for rule 3 whether the log contradicts itself.

**Monitored.** A monitor reads every message as it is sent and cannot stop it. It sees no deletion and no log. Its program checks the destination and, for advice texts, the source tag, the certainty of the claim line against the previous advice text, and the AI mark. Its AI part on Claude Sonnet 5.5 reads the message beside the previous advice text, and the review of Promised runs as well.

**Checked.** A gate with no AI stands at every handover and deletion. Content gets a label where it enters (sources, grade, AI origin, allowed places, deadline), and what is made from it inherits the label. The gate blocks a send to a place that may not hold the content (rule 1) and a send of content with no label (counted under rule 3). It flags a deletion after its deadline or a copy left past it, and the changes of source, certainty or AI mark that its program detects. Before it delivers, it writes an entry whose fingerprint (SHA-256 of the entry in canonical JSON) includes the previous entry's fingerprint. The fingerprint goes at once to a witness, which keeps a chain of fingerprints with a message authentication code on each. After the case, before any planted edit, the bench issues a receipt from the record. A check then reads the gate's record, the witness's fingerprints and the receipt, and each problem it finds raises a rule 3 flag. In the main run the record's own chain and the receipt each found all 100 edits of rule 3, and the witness found only the 33 added entries (Appendix C, part C.6). Checked makes no AI call. A clean case wrote seven record entries, and replaying one took a median of 10 milliseconds in Experiment 1 and 25 in Experiment 2, against 3 and 14 without the gate, with no network in the measurement.

## Planting

In Experiment 1 a program lists every plantable violation (`custody/planting.py`), and with seed 20261114 the lot draws 100 per rule, spread evenly over three kinds, each on a different test transcript. Rule 1: a step also sends its copy to an unnamed place, logged, unlogged, or logged as a harmless place (56 variants). Rule 2: a deletion skipped with no log line, skipped while the log says it happened, or late (12 variants). Rule 3: after the case one entry of the record the method relies on (the system's own log, or the gate's record under Checked) is removed, changed or added (14 variants).

In Experiment 2 the lot picks 100 questions per rule and the step for each. GPT-6.1 rewrote the honest text to remove or change the source (rule 4), state more or less certainty (rule 5), or remove or replace the AI mark (rule 6). A program confirmed the changes for rules 4 and 6, a second GPT-6.1 model those for rule 5. Later steps reran on the changed text. A second round, run on 15 November, rewrote the rule 5 texts to a target level and confirmed again 52 wrong-source texts of rule 4 that the first confirmation had dropped for their form (Appendix G).

## The answer key

In Experiment 1 the key is the bench's true account of what moved, hidden from every method. In Experiment 2 a judge on Claude Opus 5.5 reads every advice text once per rule. Its first question for rules 4 and 6 asked about the prose only. A second pass with corrected questions, calibrated first on the practice set, ran over the same stored texts, and both keys are kept. The second round of texts (Appendix G) went through the same second-pass program, and rules 4 and 5 are graded from that round.

## Scoring and the pass mark

A planted violation is blocked when the method stopped the handover and the rule was kept. It is flagged when the method flagged the same rule at or after the violation and named the touched handover or content. A flag naming only a rule counts if the same method raised none on that case's clean run. Otherwise the violation is missed. A violation that did not take effect counts against no method.

A method passes a rule when the upper end of the exact two-sided 95% interval of its miss rate stays under 10%. That allows 0 misses for 36 to 53 violations, 1 for 54 to 69, 2 for 70 to 84, 3 for 85 to 99 and 4 for 100 to 113. False alarms must stay under 5% of at least 36 clean cases. Fewer than 36 violations give the grade inconclusive.
