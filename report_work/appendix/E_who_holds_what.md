# Appendix E. Who holds what

In the test bench every part except the AI models ran in one program on one machine. The witness signs nothing. It computes a message authentication code with a fixed test key kept in plain text in the configuration (`config/design_choices.json`, key `witness`). The operator of the machine could therefore rewrite the gate's record and the witness's fingerprints together, and no check would notice, unless a receipt issued before the edit is kept elsewhere (Section 4.4). The steps and the gate never get the key. Table E1 sets out who would run each part in practice.

Table E1. Who would run each part, where it ran in the bench, and what it is trusted for.

<!-- widths: 12,20,22,22,24 -->
| Part | Who would run it in practice | Where it ran in the bench | Trusted for | If its operator colludes with the vendor |
|---|---|---|---|---|
| Gate | The vendor | In the bench's process, at every handover | Checking each handover and writing the record before delivery | Handovers can skip it unrecorded |
| Record | The vendor | A file in the run folder | One chained entry per handover and deletion | A careless edit breaks the chain; a recomputed chain shows only against fingerprints saved outside the record |
| Witness | A party other than the vendor | A file in the same run folder, test key in the configuration | Keeping each fingerprint where the vendor cannot write | The record can be rewritten; only a receipt saved earlier would show it |
| System's own log | The vendor | A file in the run folder | Saying what each step did | Promised sees only what it admits; Monitored also reads the messages |
| Monitor | The vendor or a contracted checker | In the bench's process, AI on Claude Sonnet 5.5 | Reading every message as it is sent | Messages pass unread |
| Review | The vendor's compliance team or an outside auditor | In the bench's process after each case, AI on Claude Sonnet 5.5 | Reading the log and final texts | A false log passes |
| Answer key | The bench only | The bench's true account (Experiment 1) and the judge on Claude Opus 5.5 (Experiment 2) | What happened | The grades lose their meaning |

A witness counts only when a party other than the vendor runs it, with its own key, on a machine the vendor cannot write to, a set-up I did not test.
