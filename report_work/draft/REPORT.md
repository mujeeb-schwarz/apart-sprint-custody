---
title: "Is an AI system's own log enough? Six rules, three ways of checking, and what is missing from AI observability standards"
authors: "Mujeeb Schwarz-Hussain"
affiliations: "Independent researcher"
event: "AI x Epistemics Research Sprint"
date: "November 2026."
---

## Abstract

In a doctor's visit, an AI scribe turns the patient's sensitive and private health information into a note, and an AI evidence tool answers the doctor's questions. In a 2026 survey of US physicians, 28% used AI for documentation and 39% for summaries of medical research, up from 21% and 13% in 2024. Doctors count on advice that names its true source, and vendors promise where the patient's words may go and when every copy is deleted. The only log is their own, where a kept copy marked "deleted" looks like one that is gone. I wrote six such promises as rules for a simulated patient visit, planted 100 violations of each across two experiments, and compared three ways of checking. A review of that log and the final texts failed five of six rules and missed 182 of 599 violations, including all 33 copies its log called deleted. When another AI model rewrote the log, the review caught 15 of 100 edits. A monitor on every message missed the same 33 copies. Only a checkpoint at each handover caught them and every planted edit of its record: it records each copy handed over and its deadline, and a simulated witness holds the fingerprints. No method passed all six rules, since the checkpoint let through advice naming a wrong source like "Wikipedia", which the monitor caught. I propose two fields that would let the logging standards I read carry such a record: a deletion deadline and a witness's fingerprint.

## 1. Introduction

**AI systems now handle records that people must be able to trust later.** In American Medical Association surveys of US physicians, the share using AI rose from 38% in 2023 to 72% in 2026; in 2026, 28% used it for documentation such as visit notes and 39% for summaries of medical research, up from 21% and 13% in 2024 [1]. At one US medical group 7,260 physicians used an AI scribe in 2.58 million patient visits within fifteen months [2].

**Such a record moves through a chain of AI steps, and what happens to it there is hard to check from outside when the only account is the one the vendor writes.** I start with the doctor's visit because the stakes and the gap are both large there. A patient's words can reveal an illness that no one else knows of, and an AI scribe passes them on within minutes to a vendor's systems. In 2024, business associates, the vendors that act for US health care providers and insurers, accounted for 207 of the 243 million people affected by large breaches of health records, counted breach by breach [3]. In a national survey in 2023, 65.8% of US adults had low trust that their health system would use AI responsibly [4]. The patient's legal right to an account of who received their records also leaves out disclosures for treatment, payment and health care operations [5].

**Two flows of information pass through AI during and after a visit, and each carries promises.** In the first the patient's words go out: an AI scribe, such as Microsoft's Dragon Copilot, Suki, Freed or Doximity Scribe, drafts the note, and its vendor promises where the words may go and when every copy is deleted; these four vendors' pages say that visit audio is kept for anywhere from no time to 90 days [6]. In the second, advice comes in: an evidence tool such as OpenEvidence [7] answers the doctor's question, and the doctor counts on the answer to name its true source and to keep the certainty of the evidence. The vendor's account of either flow is the *system's own log*, which the vendor writes and can also change, and in which a kept copy marked "deleted" looks like one that is gone. I test each flow in its own experiment and model a step or an operator that breaks a promise while the log says it was kept; an operator who also controls the witness defeats every method here (Section 4.4).

**I measured which way of checking is enough for which promise**, on a test bench simulating a visit with public data: a review of the system's own log and final texts (*Promised*), the same review with a monitor on every message (*Monitored*), and a checkpoint on every handover, the *gate*, that keeps its own record, with a simulated witness (*Checked*). Figure 1 shows one such visit, with words from a mock consultation and two of the planted violations.

**My main contributions are:**

1. **An answer to the sprint's second track**, which asks what minimal tamper-evident layer is missing from AI observability standards [8]. My answer, for the five standards I read, is a record of handovers and deletion duties whose fingerprints a witness holds, which two new fields would add (Appendix D).
2. **A measurement of which check is enough for which promise.** No method passed all six rules: a review of the system's own log and final texts was enough for one promise and a monitor for three more, while only the checkpoint's record caught the copies never deleted and the planted edits of the record (Table 2).
3. **A test bench for promises about records and the code to rerun it.** It grades any way of checking against six rules, 599 planted violations on public data and a pass mark filed before the run.

![Figure 1. One visit on the test bench. The words are from a mock consultation in ACI-Bench, and the note line is the AI note writer's stored output. Two planted violations, marked 1 and 2, are drawn together for illustrative purposes; each test case holds one. Each chip gives a method's outcome on all 33 cases of that kind, and the tiles name the first method that passed each rule.](../figures/fig1_visit_example.png)

## 2. Related Work

**Most similar prior work.** Five current standards describe the events that AI systems and health record systems log: OpenTelemetry's conventions for generative AI [9], the HL7 FHIR resources Provenance [10], AuditEvent [11] and Evidence [12], and HL7's draft guide AI Transparency on FHIR [13]. Tamper-evident logs, which an untrusted logger cannot rewrite unnoticed, have been studied for years [14] and already record more than 2.5 billion web certificates [15, 16]. Others report that output-only audits miss 41.7% of violations in multi-agent systems [17]. Agent defences that label data and check each tool call are built to stop a wrong send [18, 19], and adaptive attacks can subvert AI monitors [20].

**Limits of the state of the art.** The five standards ask for no outside witness, and I found no field in them for the list of places data may go, for a deletion deadline with its copies, or for a third party's fingerprint of the record (Appendix D). In the work I read, no study measures when a tamper-evident log is needed.

**What this work adds, and when to use it.** My gate uses labels as those defences do and adds a duty that falls due later, such as a deletion. The measurement shows, promise by promise, which of the three ways of checking is enough, and a clinic or an auditor can rerun the bench on the promises that matter to them.

## 3. Methods

**Two experiments on public data** (Figure B1, Appendix B). In Experiment 1 the patient's words go out: a transcribing service hands the transcript to an AI note writer, which hands its draft to the medical record, and each step must delete its copy by a deadline. Its 157 test cases are mock consultations from ACI-Bench [21]. In Experiment 2 advice comes in: an evidence tool's answer to the doctor's question becomes a plan and then a note for the patient, each written by an AI step. Its 413 cases are 213 questions from systematic reviews, 176 with the reviewers' grade of certainty (MedEvidence [22]), and 200 questions that physicians put to OpenEvidence, a clinical evidence tool (Real-POCQi [7]).

**Six rules, with 100 violations planted for each (Table 1).** For each rule I drew 100 test cases by lot and planted one violation in each: a program for rules 1 to 3, and OpenAI's GPT-6.1 for rules 4 to 6, with a separate step confirming each change. One rewrite for rule 5 left the certainty unchanged, which leaves 599 planted violations. Clean cases, which have no planted violation, measure false alarms. Every case ran under every method on the same stored AI texts, which keeps the texts equal across methods.

Table 1. The six rules and the kinds of violation planted. Letters mark the kinds, and the number after each kind is its count of test cases.

<!-- widths: 6,34,60 -->
| Rule | The promise | The kinds of violation planted |
|---|---|---|
| 1 | The patient's words go only to named places. | A step also sends its copy to an unnamed place, and the log (a) shows it (33 cases), (b) leaves it out (33) or (c) names a harmless place (34). |
| 2 | Every copy is deleted by its deadline. | The deletion is (a) skipped (34 cases), (b) skipped while the log says it was done (33) or (c) done late (33). |
| 3 | Every handover is recorded, and a later edit of the record shows. | After the case, one entry of the record that the method relies on is (a) removed (33 cases), (b) changed (34) or (c) added (33). |
| 4 | Every advice text names a true source. | The source is (a) removed (47 cases), or replaced by a wrong one written (b) as a tool's identifier (8) or (c) in words, such as "Wikipedia" (45). |
| 5 | The certainty of the advice is not changed on the way. | The conclusion is rewritten to read (a) more certain (56 cases) or (b) less certain (44, one without effect). |
| 6 | The AI's part is marked as written by AI. | The AI mark is (a) removed (49 cases) or (b) replaced (51), in the final note (40) or at an earlier step (60). |

**Three methods and a proof step** (Table B1 in Appendix B gives what each reads and cannot see):

1. *Promised*, the baseline, reviews the system's own log and the final texts after every case, with a program and then an AI model.
2. *Monitored* keeps that review and adds a monitor that reads every message between the steps, with a program and an AI model. A flag from any part counts.
3. *Checked* replaces both with the gate on every handover and deletion: a program with no AI that can stop a send and keeps its own record.
4. *Proven* is Checked with a proof step: before any case runs, a search program and Z3 [23], a solver that checks logical statements, each look in the wiring for a path that breaks rules 1 to 3.

**How the gate keeps its record.** Content carries labels from the moment it enters: its sources, grade of certainty, AI origin, allowed places and deadline. At each handover the gate reads the labels, blocks a send to a place that is not allowed, and writes the handover into its record. A deletion enters the record only when it passes the gate, so a copy that is never deleted leaves an *open duty* after its deadline. The gate gives a *fingerprint* of each entry, a short value that changes with the entry and includes the fingerprint before it, to a *witness* that stands for a party outside the vendor, and after the case the bench issues a *case receipt*, a fingerprint of the record.

**Models and grading.** Claude Haiku 5.5 played the AI steps, Claude Sonnet 5.5 the AI parts of the review and the monitor, and Claude Opus 5.5 the judge of Experiment 2, with which a second judge, OpenAI's `gpt-6-astra`, agreed on 783 of 800 readings (none from the second round of rule 4). AI agents built and ran the bench under my direction (Appendix I). A planted violation is *blocked* when the method stops it beforehand, *flagged* when the method raises a flag for that rule at or after the violation, and *missed* otherwise; a flag on a clean case is a *false alarm*. A method *passes* a rule when the upper end of the exact 95% interval of its miss rate stays under 10% [24], which allows 4 misses in 100, and when it raises false alarms on fewer than 5% of clean cases. The *least enough* method is the first of Promised, Monitored and Checked that passes.

**Filed in advance, and what did not work.** I filed the plan, the pass mark and two sets of predictions and froze the code before the first test run (Appendix F). Five things did not work at first and were fixed after the freeze (Appendix G lists every change); among them, the judge's question for rules 4 and 6 read only the prose, and the first texts for rule 5 changed the certainty in only 7 of 100 cases. The grades of rules 4, 5 and 6 therefore come from a second pass of the judge and a second round of texts.

## 4. Results

**No method passed all six rules (Table 2), and the differences between methods are too large to be chance.** On the same cases, Checked caught 33 overdue copies and 12 edits that Monitored missed and lost none the other way, and Monitored caught 45 wrong sources that Checked missed, against 1 (exact McNemar tests, which compare two methods on the same cases, give p at most 0.0005 for each). Of 138 cases run twice, 137 gave the same outcome. Of 60 sealed attack ideas that GPT-6.1 wrote for rules 1 to 3, run with the AI parts off, Checked missed none of the 54 that took effect, and Promised and Monitored missed all 48 aimed at rule 3 (Appendix C.5).

Table 2. Planted violations missed, of 100 per rule (99 for rule 5), with the grade. A method passes with at most 4 misses in 100 (3 in 99) and false alarms under 5%; the bottom row names the first method that passes. Rule 3 edits the system's own log under Promised and Monitored and the gate's chained record under Checked. Rules 4 and 5 use the second round of texts (Appendix G).

<!-- widths: 15,13,14,14,13,17,14 -->
| Method | Rule 1<br>named places | Rule 2<br>deleted by deadline | Rule 3<br>record of handovers | Rule 4<br>source named | Rule 5<br>certainty unchanged | Rule 6<br>AI's part marked |
|---|---|---|---|---|---|---|
| Promised | fail<br>missed 67 | fail<br>missed 33 | fail<br>missed 12 | fail<br>missed 10 | **pass**<br>missed 0 | fail<br>missed 60 |
| Monitored | **pass**<br>missed 0 | fail<br>missed 33 | fail<br>missed 12 | **pass**<br>missed 1 | fail<br>missed 0<br>false alarms 25% | **pass**<br>missed 0 |
| Checked | **pass**<br>all blocked | **pass**<br>missed 0 | **pass**<br>missed 0 | fail<br>missed 45 | fail<br>missed 2<br>false alarms 25% | **pass**<br>missed 0 |
| **Least enough** | **Monitored** | **Checked** | **Checked** | **Monitored** | **Promised** | **Monitored** |

### 4.1 Where Promised failed: five of six rules

**A review sees only the log and the final texts, so each failure of Promised traces back to something those two did not show** (every kind is in Appendix C, Figure C1):

- Rule 1, missed 67: the log left the send out. The review flagged the 33 sends that the log showed and missed those that the log left out (33) or filed under a harmless place (34).
- Rule 2, missed 33: the log recorded a deletion that never happened. The review flagged the 67 overdue copies the log showed honestly and believed its "deleted" for the rest.
- Rule 3, missed 12: the log was edited after the case. The review's AI caught 88 careless edits, which leave a log that contradicts itself or the final texts. In a further test it caught 56 when a program also renumbered and re-timed the edited log, and 15 when GPT-6.1 rewrote the whole log, told only what the review asks about this rule (Appendix C.8).
- Rule 4, missed 10: a wrong source looked well formed. Eight of the ten named a wrong tool in the form of an honest source tag ("tool:chatgpt").
- Rule 6, missed 60: a later AI step covered the trace. The review flagged the 40 marks changed in the final note and missed the 60 changed earlier, because the next AI step marked its own text afresh.

**Promised passed rule 5 because its AI compares two texts**, the final note and the incoming answer: it flagged all 99 changes of certainty, with no false alarm on 207 clean questions.

### 4.2 What a monitor adds: rules 1, 4 and 6

**A monitor catches what shows in a message, so Monitored passed rules 1, 4 and 6.** It flagged all 100 sends to an unnamed place after the words had left, all 100 changed AI marks at the handover where each changed, and 99 of 100 removed or wrong sources. A skipped deletion and an edit of the log send no message, so it missed the same 33 deletions and 12 edits as Promised. It lost rule 5, because its program reads certainty from words and raised false alarms on 52 of 207 clean questions, 25% against a limit of 5%.

### 4.3 What a gate with its own record adds: rules 2 and 3

**The gate keeps track of the duty to delete, so Checked saw the deletions that never happened.** When the transcript reaches the AI note writer, the gate notes the new copy and its deadline, and if no deletion of that copy passes the gate in time, it flags the copy as overdue, whatever the system's own log says (Figure 1). Checked flagged all 100 overdue copies, including the 33 that the log called deleted, and all 100 edits of its own record. When the forger also recomputed the chain, the witness still caught all 100 (Appendix C.6); a review of a log forged by a program caught 56 (C.8). Checked raised no false alarm in 157 clean cases.

**The gate also stops a send before the words leave.** It blocked all 100 sends to an unnamed place. In 100 further runs, a line hidden in the patient's words told the AI note writer to send the transcript to an unnamed place, and it did so in 69. Checked blocked all 69, and the other methods flagged them after the send.

**Checked's limits come from the same design.** A gate acts on handovers, so it flagged the violations of rules 2 and 3 after they had happened and could force no deletion. Its program reads tags, so it let through the 45 wrong sources written in words, such as "Wikipedia", which the programs of Promised and Monitored read as no source, flagging 43 and 45. On rule 5 it shares the monitor's word-matching program and its false alarms.

### 4.4 What a proof step adds, and what no method caught

**A gate helps only where a handover passes through it, so a flow wired wrong defeats it.** I replayed 10 known wiring mistakes, such as a handover that skips the gate, once each under Checked alone: it blocked 1, flagged 7 after the break and missed 2. Proven's search program and the Z3 solver [23] each found all 10 in the description of the wiring before any case ran (Appendix C). A running program that departs from that description could escape both.

**Two things escaped every method.** A copy that a step keeps without handing anything over meets no gate, no monitor and no log, and all 20 such cases were missed. An operator who rewrites the gate's record, the witness's copies and the case receipt together also escapes (Figure C3).

## 5. Discussion and Limitations

**For AI safety, the result shows what oversight through logs and monitors missed here.** Both shared a blind spot. A deletion that does not happen sends no message for a monitor to read, and a review learns of it only from the log, which in these cases said the deletion was done. An AI reviewer that reasons from the same log is no better placed, and against a log rewritten by another AI model it caught 15 of 100 edits. In this bench the gap closed when a part outside the acting step kept its record of what was due.

**Two fields would carry the gate's record into today's standards, one for each rule that only Checked passed.** For rule 2, a *deletion duty* in the handover entry names the copy that a step received and its deadline, and the later deletion event points back to it, so that a reader can list every duty still open. For rule 3, a *witness receipt* gives a third party's signed fingerprint of the record up to this entry, so that a later reader can tell whether the record is the one the witness saw. Appendix D writes both out for FHIR Provenance and for OpenTelemetry's generative AI conventions [9].

**The EU AI Act leaves the same gap for records outside health care.** From 2 December 2027 the EU AI Act's logging and log-keeping duties apply to new high-risk systems in areas such as education, employment, public benefits, migration and justice [25, 26]. The articles that set these duties ask neither for a tamper-evident log nor for a third party to hold it.

**Limitations** (Appendix A has more, with the dual-use risks).

- **The violations were planted**, and where a program decides, 100 cases repeat a few variants (12 for rule 2, 14 for rule 3). The counts measure what each method can see and give no rate of real violations.
- **Checked rests on three assumptions:** correct labels at entry, a gate on every handover and deletion, and an honest witness, which ran in the gate's own process with a test key (Appendix E). I did not test wrong labels or a false deletion report: a wrong label would let the gate pass a send it should block, and a vendor-run witness would leave rule 3 resting on careless edits only. Checked also differs from the other methods in several ways at once, so the bench isolates the witness only on rule 3 (Figure C3) and the gate on no rule.
- **The answer key of Experiment 2 is an AI judge.** Its question for rules 4 and 6 was corrected after the first run, a planned human reading of 40 texts did not take place, and one family of models played the steps, the monitor, the review and the judge.

**Future work.** Next come a witness run by a second party, a run without the gate, and the same bench on school or public-office records. Building the gate into one working scribe or evidence tool, with a vendor or a clinic, would then show the technical problems of real use, such as labelling content at entry and deleting copies in backups, and the barriers to adoption, such as who runs the witness. The two fields would go to OpenTelemetry's generative AI conventions as a pull request.

## 6. Conclusion

A log written by the vendor of an AI system can show only what the vendor records. In this bench such a log hid every copy that it wrongly called deleted, and a monitor on every message did not see those copies either. Once another AI model had rewritten the log, a review of it caught 15 of 100 edits. The checkpoint's record, with fingerprints at a simulated witness, showed the kept copies and every planted edit of that record, but let through advice naming a wrong source, which the monitor caught. The two fields proposed here would give that record a place in AI logging standards. Until they do, a clinic can ask its AI scribe vendor, in its contract, for this record and for a witness the vendor does not run, and so check reported deletions and edits itself.

## Code and Data

**Code and stored runs:** a repository that recomputes every reported number, available on request until its public release; parts predate the kickoff (Appendix H). **Data sets:** ACI-Bench [21], MedEvidence [22], Real-POCQi [7].

## References

1. American Medical Association, Center for Digital Health and AI. 2026 Physician Survey on Augmented Intelligence. March 2026. [ama-assn.org/system/files/physician-ai-sentiment-report.pdf](https://www.ama-assn.org/system/files/physician-ai-sentiment-report.pdf)

2. Kaiser Permanente Division of Research. AI-assisted notetaking gains steady support from Kaiser Permanente physicians. 1 April 2025. Reports Tierney AA, Gayre G, Hoberman B, et al. Ambient artificial intelligence scribes: learnings after 1 year and over 2.5 million uses. NEJM Catalyst, 2025, doi:10.1056/CAT.25.0040. [divisionofresearch.kaiserpermanente.org](https://divisionofresearch.kaiserpermanente.org/?p=24811)

3. US Department of Health and Human Services, Office for Civil Rights. Annual Report to Congress on Breaches of Unsecured Protected Health Information for Calendar Year 2024. [hhs.gov/sites/default/files/breach-report-to-congress-2024.pdf](https://www.hhs.gov/sites/default/files/breach-report-to-congress-2024.pdf)

4. Nong P, Platt J. Patients' trust in health systems to use artificial intelligence. JAMA Network Open 8(2):e2460628, 2025. [doi:10.1001/jamanetworkopen.2024.60628](https://doi.org/10.1001/jamanetworkopen.2024.60628)

5. 45 CFR § 164.528, Accounting of disclosures of protected health information. Code of Federal Regulations, 2024 edition. [govinfo.gov](https://www.govinfo.gov/content/pkg/CFR-2024-title45-vol2/xml/CFR-2024-title45-vol2-sec164-528.xml)

6. Product pages on how long an AI scribe keeps visit audio, read 15 November 2026. Microsoft, Dragon Copilot frequently asked questions ([learn.microsoft.com](https://learn.microsoft.com/en-us/industry/healthcare/dragon-copilot/about/faqs)); Suki, Security FAQ ([developer.suki.ai](https://developer.suki.ai/documentation/references/faqs/security)); Freed, HIPAA compliance in AI scribes ([getfreed.ai](https://www.getfreed.ai/resources/hipaa-compliance-in-ai-scribes)); Doximity, Meet Doximity Scribe ([blog.doximity.com](https://blog.doximity.com/articles/meet-doximity-scribe)).

7. Feng J, Patel V, Heagerty P, Mai Y, Sivaraman V, Vossler P, Ouyang J, Jena AB. Expert evaluation of clinical AI tools on real point-of-care clinical queries. arXiv:2606.28960, 2026. Dataset Real-POCQi. [arxiv.org/abs/2606.28960](https://arxiv.org/abs/2606.28960)

8. Apart Research. AI x Epistemics Research Sprint, 13 to 15 November 2026, sprint page, Track 2: Trust Infrastructure. [apartresearch.com/sprints/ai-x-epistemics-research-sprint-2026-11-13-to-2026-11-15](https://apartresearch.com/sprints/ai-x-epistemics-research-sprint-2026-11-13-to-2026-11-15)

9. OpenTelemetry. Semantic conventions for generative AI systems (status: Development). Repository open-telemetry/semantic-conventions-genai, read 15 November 2026. [github.com/open-telemetry/semantic-conventions-genai](https://github.com/open-telemetry/semantic-conventions-genai)

10. HL7 International. Resource Provenance. FHIR R5 (v5.0.0), Trial Use. [hl7.org/fhir/R5/provenance.html](https://hl7.org/fhir/R5/provenance.html)

11. HL7 International. Resource AuditEvent. FHIR R5 (v5.0.0), Trial Use. [hl7.org/fhir/R5/auditevent.html](https://hl7.org/fhir/R5/auditevent.html)

12. HL7 International. Resource Evidence. FHIR R5 (v5.0.0), Trial Use. [hl7.org/fhir/R5/evidence.html](https://hl7.org/fhir/R5/evidence.html)

13. HL7 International, Electronic Health Records Work Group. AI Transparency on FHIR, implementation guide, continuous build of version 1.0.0 (based on FHIR R4), read 15 November 2026, with its source files ([github.com/HL7/aitransparency-ig](https://github.com/HL7/aitransparency-ig/tree/main/input/fsh)); ballot version 1.0.0-ballot, January 2026. [build.fhir.org/ig/HL7/aitransparency-ig](https://build.fhir.org/ig/HL7/aitransparency-ig/en/index.html)

14. Crosby SA, Wallach DS. Efficient data structures for tamper-evident logging. USENIX Security Symposium, 2009. [usenix.org](https://www.usenix.org/legacy/event/sec09/tech/full_papers/crosby.pdf)

15. Laurie B, Langley A, Kasper E. Certificate Transparency. RFC 6962, IETF, 2013. [rfc-editor.org/rfc/rfc6962](https://www.rfc-editor.org/rfc/rfc6962.txt)

16. Certificate Transparency. Community site, home page, read 15 November 2026. [certificate.transparency.dev](https://certificate.transparency.dev/)

17. El Yagoubi F, Badu-Marfo G, Al Mallah R. AgentLeak: a benchmark for internal-channel privacy leakage in multi-agent LLM systems. arXiv:2602.11510, 2026. [arxiv.org/abs/2602.11510](https://arxiv.org/abs/2602.11510)

18. Debenedetti E, Shumailov I, Fan T, Hayes J, Carlini N, Fabian D, Kern C, Shi C, Terzis A, Tramèr F. Defeating prompt injections by design. arXiv:2503.18813, 2025. [arxiv.org/abs/2503.18813](https://arxiv.org/abs/2503.18813)

19. Costa M, Köpf B, Kolluri A, Paverd A, Russinovich M, Salem A, Tople S, Wutschitz L, Zanella-Béguelin S. Securing AI agents with information-flow control. arXiv:2505.23643, 2025. [arxiv.org/abs/2505.23643](https://arxiv.org/abs/2505.23643)

20. Terekhov M, Panfilov A, Dzenhaliou D, Gulcehre C, Andriushchenko M, Prabhu A, Geiping J. Adaptive attacks on trusted monitors subvert AI control protocols. arXiv:2510.09462, 2025 (version 2, 2026). [arxiv.org/abs/2510.09462](https://arxiv.org/abs/2510.09462)

21. Yim W, Fu Y, Ben Abacha A, Snider N, Lin T, Yetisgen M. Aci-bench: a novel ambient clinical intelligence dataset for benchmarking automatic visit note generation. Scientific Data 10:586, 2023. [doi:10.1038/s41597-023-02487-3](https://www.nature.com/articles/s41597-023-02487-3)

22. Polzak C, Lozano A, Sun MW, Burgess J, Zhang Y, Wu K, Yeung-Levy S. Can large language models match the conclusions of systematic reviews? arXiv:2505.22787, 2025. Dataset MedEvidence. [arxiv.org/abs/2505.22787](https://arxiv.org/abs/2505.22787)

23. de Moura L, Bjørner N. Z3: an efficient SMT solver. TACAS 2008. [microsoft.com/en-us/research/publication/z3-an-efficient-smt-solver](https://www.microsoft.com/en-us/research/publication/z3-an-efficient-smt-solver/)

24. SciPy. scipy.stats.binomtest and proportion_ci, method 'exact' (Clopper-Pearson). SciPy v1.18.0 manual. [docs.scipy.org](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats._result_classes.BinomTestResult.proportion_ci.html)

25. Regulation (EU) 2024/1689 of the European Parliament and of the Council of 13 June 2024 laying down harmonised rules on artificial intelligence (Artificial Intelligence Act), Articles 12, 19 and 26 and Annex III. Official Journal of the European Union, 12 July 2024. [eur-lex.europa.eu](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401689)

26. Regulation (EU) 2026/1744 of the European Parliament and of the Council of 8 July 2026 amending Regulations (EU) 2024/1689, (EU) 2018/1139 and (EU) 2023/1230 as regards the simplification of the implementation of harmonised rules on artificial intelligence (Digital Omnibus on AI). Official Journal of the European Union, 24 July 2026. [eur-lex.europa.eu](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32026R1744)

27. Nasr M, Carlini N, Sitawarin C, Schulhoff SV, Hayes J, et al. The attacker moves second: stronger adaptive attacks bypass defenses against LLM jailbreaks and prompt injections. arXiv:2510.09023, 2025. [arxiv.org/abs/2510.09023](https://arxiv.org/abs/2510.09023)

28. International Organization for Standardization. ISO/IEC 24970, Artificial intelligence: AI system logging. Catalogue entry, stage 60.00 (International Standard under publication), read 15 November 2026. [iso.org/standard/88723.html](https://www.iso.org/standard/88723.html)

29. CEN-CENELEC. Artificial Intelligence (Joint Technical Committee 21), topic page and the work programme of CEN/CLC/JTC 21 linked from it, read 15 November 2026. [cencenelec.eu](https://www.cencenelec.eu/areas-of-work/cen-cenelec-topics/artificial-intelligence/)

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

**A monitor reads the attacker's text too.** In the hidden-instruction runs of Experiment 1 the monitor's own AI wrote out the hidden command in 56 of 100 answers. My programs ignore such lines, so no flag changed. Adaptive attacks on monitoring models [20] and on defences against prompt injection [27] are documented, and I report the count so that a buyer does not take a monitor's presence for a guarantee.

### A.3 Ethics and personal data

All three data sets are public and were made for research. ACI-Bench holds mock consultations. MedEvidence holds questions and conclusions from published systematic reviews. Real-POCQi holds questions that physicians put to OpenEvidence, filtered by its authors for identifying details and lightly rewritten, with stored answers from four AI systems. I used the files as published and added no data about any person. The models received only these texts and the bench's own prompts, rewrites and instructions.

## Appendix B. Methods in detail

The wiring is in `wiring/wiring.json` and every setting in `config/design_choices.json`. Figure B1 draws the two experiments, and Table B1 compares the methods.

### The two experiments

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

### The methods as built

**Promised.** After the case a review reads the system's own log, the incoming answer, the final texts and the named places. Its program flags a logged send to an unnamed place (rule 1), a copy in the log with no logged deletion in time (rule 2), and a final note for the patient with no source tag (rule 4) or no AI mark (rule 6). Its AI part on Claude Sonnet 5.5 is asked about all six rules, for rule 3 whether the log contradicts itself.

**Monitored.** A monitor reads every message as it is sent and cannot stop it. It sees no deletion and no log. Its program checks the destination and, for advice texts, the source tag, the certainty of the claim line against the previous advice text, and the AI mark. Its AI part on Claude Sonnet 5.5 reads the message beside the previous advice text, and the review of Promised runs as well.

**Checked.** A gate with no AI stands at every handover and deletion. Content gets a label where it enters (sources, grade, AI origin, allowed places, deadline), and what is made from it inherits the label. The gate blocks a send to a place that may not hold the content (rule 1) and a send of content with no label (counted under rule 3). It flags a deletion after its deadline or a copy left past it, and the changes of source, certainty or AI mark that its program detects. Before it delivers, it writes an entry whose fingerprint (SHA-256 of the entry in canonical JSON) includes the previous entry's fingerprint. The fingerprint goes at once to a witness, which keeps a chain of fingerprints with a message authentication code on each. After the case, before any planted edit, the bench issues a receipt from the record. A check then reads the gate's record, the witness's fingerprints and the receipt, and each problem it finds raises a rule 3 flag. In the main run the record's own chain and the receipt each found all 100 edits of rule 3, and the witness found only the 33 added entries (Appendix C, part C.6). Checked makes no AI call. A clean case wrote seven record entries, and replaying one took a median of 10 milliseconds in Experiment 1 and 25 in Experiment 2, against 3 and 14 without the gate, with no network in the measurement.

### Planting

In Experiment 1 a program lists every plantable violation (`custody/planting.py`), and with seed 20261114 the lot draws 100 per rule, spread evenly over three kinds, each on a different test transcript. Rule 1: a step also sends its copy to an unnamed place, logged, unlogged, or logged as a harmless place (56 variants). Rule 2: a deletion skipped with no log line, skipped while the log says it happened, or late (12 variants). Rule 3: after the case one entry of the record the method relies on (the system's own log, or the gate's record under Checked) is removed, changed or added (14 variants).

In Experiment 2 the lot picks 100 questions per rule and the step for each. GPT-6.1 rewrote the honest text to remove or change the source (rule 4), state more or less certainty (rule 5), or remove or replace the AI mark (rule 6). A program confirmed the changes for rules 4 and 6, a second GPT-6.1 model those for rule 5. Later steps reran on the changed text. A second round, run on 15 November, rewrote the rule 5 texts to a target level and confirmed again 52 wrong-source texts of rule 4 that the first confirmation had dropped for their form (Appendix G).

### The answer key

In Experiment 1 the key is the bench's true account of what moved, hidden from every method. In Experiment 2 a judge on Claude Opus 5.5 reads every advice text once per rule. Its first question for rules 4 and 6 asked about the prose only. A second pass with corrected questions, calibrated first on the practice set, ran over the same stored texts, and both keys are kept. The second round of texts (Appendix G) went through the same second-pass program, and rules 4 and 5 are graded from that round.

### Scoring and the pass mark

A planted violation is blocked when the method stopped the handover and the rule was kept. It is flagged when the method flagged the same rule at or after the violation and named the touched handover or content. A flag naming only a rule counts if the same method raised none on that case's clean run. Otherwise the violation is missed. A violation that did not take effect counts against no method.

A method passes a rule when the upper end of the exact two-sided 95% interval of its miss rate stays under 10%. That allows 0 misses for 36 to 53 violations, 1 for 54 to 69, 2 for 70 to 84, 3 for 85 to 99 and 4 for 100 to 113. False alarms must stay under 5% of at least 36 clean cases. Fewer than 36 violations give the grade inconclusive.

## Appendix C. Full results

Tables C1 and C2 give each cell as blocked / flagged / missed, and Figure C1 draws the same counts. Rules 1 to 3 come from `runs/night_e1`, rules 4 and 5 from the second round (`runs/round2_e2_second_pass`), rule 6 from `runs/night_e2_second_pass`; every number is in `report_work/analysis/final_numbers.json`, except those of the witness test (`ablation/out/results.json`, `ablation/out/results_forger4.json`) and of the forger test (`forger/out/results.json`).

![Figure C1. The planted violations of each rule by kind, and what each method did with them. Hatched segments were missed, and the grade stands right of each bar. For rule 5 the false alarms on clean questions decide the grade.](../figures/fig2_why_missed.png)

### C.1 Experiment 1 by kind of planted violation

Table C1. Rules 1 to 3: cases, distinct variants, and blocked / flagged / missed under each method.

<!-- widths: 8,30,9,11,14,14,14 -->
| Rule | Kind | Cases | Variants | Promised | Monitored | Checked |
|---|---|---|---|---|---|---|
| 1 | send logged | 33 | 20 | 0/33/0 | 0/33/0 | 33/0/0 |
| 1 | send not logged | 33 | 20 | 0/0/33 | 0/33/0 | 33/0/0 |
| 1 | send logged as a harmless place | 34 | 16 | 0/0/34 | 0/34/0 | 34/0/0 |
| 2 | deletion skipped | 34 | 4 | 0/34/0 | 0/34/0 | 0/34/0 |
| 2 | skipped, log says it happened | 33 | 4 | 0/0/33 | 0/0/33 | 0/33/0 |
| 2 | deletion late | 33 | 4 | 0/33/0 | 0/33/0 | 0/33/0 |
| 3 | entry removed | 33 | 2 | 0/33/0 | 0/33/0 | 0/33/0 |
| 3 | entry changed | 34 | 6 | 0/27/7 | 0/27/7 | 0/34/0 |
| 3 | entry added | 33 | 6 | 0/28/5 | 0/28/5 | 0/33/0 |

False alarms on 157 clean cases: one each under Promised and Monitored on rule 3, none elsewhere.

### C.2 Experiment 2 by kind and step

Table C2. Rules 4 to 6 by kind and by the step where the violation was planted, with rule 4's wrong sources also split by form.

<!-- widths: 8,30,10,17,17,18 -->
| Rule | Kind, step | Took effect | Promised | Monitored | Checked |
|---|---|---|---|---|---|
| 4 | source removed, answer | 12 | 0/12/0 | 0/12/0 | 0/12/0 |
| 4 | source removed, plan | 19 | 0/19/0 | 0/19/0 | 0/19/0 |
| 4 | source removed, note | 16 | 0/16/0 | 0/16/0 | 0/16/0 |
| 4 | wrong source, answer | 16 | 0/13/3 | 0/15/1 | 0/1/15 |
| 4 | wrong source, plan | 18 | 0/16/2 | 0/18/0 | 0/2/16 |
| 4 | wrong source, note | 19 | 0/14/5 | 0/19/0 | 0/5/14 |
| 4 | wrong source as a tool identifier | 8 | 0/0/8 | 0/7/1 | 0/8/0 |
| 4 | wrong source in words | 45 | 0/43/2 | 0/45/0 | 0/0/45 |
| 5 | more certain, plan | 30 | 0/30/0 | 0/30/0 | 0/30/0 |
| 5 | more certain, note | 26 | 0/26/0 | 0/26/0 | 0/26/0 |
| 5 | less certain, plan | 18 | 0/18/0 | 0/18/0 | 0/18/0 |
| 5 | less certain, note | 25 of 26 | 0/25/0 | 0/25/0 | 0/23/2 |
| 6 | mark removed, answer | 18 | 0/0/18 | 0/18/0 | 0/18/0 |
| 6 | mark removed, plan | 15 | 0/0/15 | 0/15/0 | 0/15/0 |
| 6 | mark removed, note | 16 | 0/16/0 | 0/16/0 | 0/16/0 |
| 6 | mark replaced, answer | 14 | 0/0/14 | 0/14/0 | 0/14/0 |
| 6 | mark replaced, plan | 13 | 0/0/13 | 0/13/0 | 0/13/0 |
| 6 | mark replaced, note | 24 | 0/24/0 | 0/24/0 | 0/24/0 |

The identifier is "tool:chatgpt"; the sources in words are "user-provided text" (29), "ChatGPT" (8) and "Wikipedia" (8). Honest texts carry `pmid:` numbers or the identifier of the clinical tool. On rule 5, of the 100 planted changes (99 took effect), 61 moved the grade two levels, 21 one level and 1 three levels, and 17 graded an answer that had no grade. Clean cases leave out the questions where an AI step broke the rule by itself: 6 of the 213 review questions for rule 5 and 1 of 413 for rule 4.

False alarms: rule 4, 1 of 412 under each method; rule 5, 0 of 207 under Promised and 52 of 207 under the others; rule 6, 0 of 413.

### C.3 Who raised the flags

Table C3. Violations caught, by the part that flagged them: program only / AI only / both.

<!-- widths: 10,30,30,30 -->
| Rule | Promised | Monitored | Checked |
|---|---|---|---|
| 1 | 0/0/33 | 0/0/100 | program blocked 100 |
| 2 | 39/0/28 | 39/0/28 | 100/0/0 |
| 3 | 0/88/0 | 0/88/0 | 100/0/0 |
| 4 | 70/0/20 | 13/0/86 | 55/0/0 |
| 5 | 0/99/0 | 0/0/99 | 97/0/0 |
| 6 | 0/0/40 | 0/0/100 | 100/0/0 |

Table C3 and Figure C2 show who raised the flags. The AI raised the false alarms of rule 3, and the program that reads certainty from words raised the 52 of rule 5. The programs of the review and the monitor read a source in words as "no source tag": Promised caught 43 of these 45 violations and Monitored all 45.

![Figure C2. For each rule and method, the planted violations that were caught, split by the part that raised the flag: program only, AI only, or both. Hatched white shows the ones missed. Under Checked on rule 1 the program blocked all of them. Rule 5 has 99 planted violations, because one planted change did not take effect.](../figures/figC1_who_flagged.png)

### C.4 Paired differences on the same cases

Table C4. Violations that one method caught and the other missed, with the exact two-sided McNemar test.

<!-- widths: 10,40,25,25 -->
| Rule | Pair | Counts | p |
|---|---|---|---|
| 1 | Monitored over Promised | 67 to 0 | below 0.0001 |
| 2 | Checked over Monitored | 33 to 0 | below 0.0001 |
| 3 | Checked over Monitored | 12 to 0 | 0.0005 |
| 4 | Monitored over Promised | 9 to 0 | 0.004 |
| 4 | Monitored over Checked | 45 to 1 | below 0.0001 |
| 4 | Promised over Checked | 43 to 8 | below 0.0001 |
| 5 | Promised over Checked | 2 to 0 | 0.5 |
| 5 | Monitored over Checked | 2 to 0 | 0.5 |
| 6 | Monitored over Promised | 60 to 0 | below 0.0001 |

Table C4 lists the pairs that differ. On rules 1, 2, 3 and 6, Checked over Promised gives the same counts as the pair listed; every other pair caught the same cases. On rule 1 Checked blocked where Monitored flagged.

### C.5 The parts that stand apart

- **Copy kept inside a step.** 20 cases on 4 variants; every method missed all 20.
- **Complete list, AI parts off.** 82 variants on 3 cases each, 246 cases. The programs of Promised see 3 of 9 kinds (162 missed), of Monitored 5 (54 missed), of Checked 9 (none missed).
- **The outside model's ideas.** GPT-6.1 wrote 127 ideas, sealed at 22:19 Pacific on Fri 13 Nov and opened after the freeze. Of these, 55 were on my list, 12 could not be planted, and 60 ran on 3 cases each with the AI parts off. The counts that follow are ideas. Under Checked 10 were blocked, 44 flagged after the break, 6 did not take effect, none missed. Promised and Monitored missed all 48 ideas for rule 3 and flagged the other 12.
- **Hidden instruction, Experiment 1.** The note writer obeyed in 69 of 100 runs. Checked blocked the 69 sends; Promised and Monitored flagged them after the send. The monitor's AI wrote out the command in 56 of its 100 answers.
- **Hidden instruction, Experiment 2.** Aimed at rule 5 in 100 runs; in none did the plan's grade differ from the answer's. The monitor flagged the hidden line in 93.
- **Connection mistakes.** 10 distinct, from my own list (11 names, one listed twice): 8 in the flow of Experiment 1 and 2 in the flow of Experiment 2. My search program (`custody/prove.py`) and Z3 each read the description of the wiring for one visit, with at most one of four rare events such as a crash or a timeout, and each found all 10 without running a case. Replayed once each under Checked alone: 1 blocked (a retry copy sent to an unnamed place), 7 flagged after the break, 2 missed (two handovers that skip the gate) [`report_work/audits/AUDIT_PROOF.md`]. Proven found all 10; Z3 needed, for two of them, the change to its generator listed in Appendix G, first made in memory on Sat 14 Nov.
- **Natural violations.** None in Experiment 1. In Experiment 2, 1 on rule 4 (missed by all) and 6 on rule 5 (Promised flagged 1, Monitored 4, Checked 4).
- **Repeat check.** 138 cases ran twice (63 of them from the first round of Experiment 2). One, a changed record entry, went from flagged to missed under Promised and Monitored.
- **Second judges.** 783 of 800 readings agreed: 188 of 200 (rule 5, round 1), 399 of 400 (rules 4 and 6), 196 of 200 (rule 5, round 2). None read round 2's rule 4 texts.
- **The witness test.** The 100 edits of rule 3 under four forgers and two checks, with no AI call. Careless forger: the chain alone flagged 100, the chain with the witness 100. Careful forger: 0 and 100. Operator who also rewrites the witness's log: 0 and 100, every flag from the receipt issued before the edit. Operator who also rebuilds the receipt: 0 and 0. Neither check reported anything on the 157 clean cases. Removing the last entry of a record was not among the edits.
- **Round 1 of rule 5.** 7 of 100 changes took effect. Promised missed 2 of them, Monitored 1, Checked 4.

### C.6 The witness test by safeguard

Figure C3 counts the 100 edits of rule 3 by the safeguard that reported a problem. The three safeguards are parts of one full check, and an edit counts for a part when the full check reported at least one problem of that part.

![Figure C3. Four forgers edit the gate's record, and each cell counts how many of the 100 edits that safeguard reported. Each further step of the forger silences one more safeguard, and the thorough operator is reported by none.](../figures/figC2_witness_test.png)

Under the careless forger the witness's saved fingerprints reported only the 33 added entries. The witness's part asks whether it holds a fingerprint for each entry of the record, so a removed entry and a changed entry that keeps its old fingerprint pass it, and the chain and the receipt report those. The filed predictions covered the chain alone and the full check (Appendix F). The fourth forger was added after the first three were seen.

### C.7 How to read the counts

Where a program decides a cell, each variant is either always caught or always missed. On rule 1 Promised missed every use of 36 of 56 variants and no use of the rest. Such a count repeats one behaviour, so the kinds are the evidence and a rate over 100 cases overstates it. Where an AI takes part, the exact 95% intervals are: Promised and Monitored on rule 3, 12 of 100 missed, 6.4 to 20.0% (the 12 sit in 4 of 14 variants, and resampling the variants gives 1.7 to 28.6%); Monitored on rule 4, 1 of 100, 0.0 to 5.4%; Promised on rule 5, 0 of 99, 0.0 to 3.7%; the note writer obeying the hidden instruction, 69 of 100, 59.0 to 77.9%.

### C.8 The forger test of the system's own log

The main run's edits of the system's own log were careless: the bench changed one entry and nothing else. After the reviews of this report, the same 100 edits of rule 3 were made by two careful forgers, and the frozen review of Promised read each forged log with the case's final texts. The decision, three conditions and the AI assistant's predictions were logged before any code was written (Appendix G), one agent built the test and a second audited it.

Table C5. Edits of the system's own log that the review flagged, out of 100, by forger and kind of edit.

<!-- widths: 46,14,14,14,12 -->
| Forger | Removed (33) | Changed (34) | Added (33) | All (100) |
|---|---|---|---|---|
| Careless: the main run's edit, nothing else touched | 33 | 27 | 28 | 88 |
| A program that also renumbers the log, moves times and adjusts the entries linked to the edit | 33 | 18 | 5 | 56 |
| GPT-6.1, which rewrites the whole log after being told the review's question for rule 3 | 15 | 0 | 0 | 15 |

Table C5 gives the counts. Every flag came from the review's AI, and its program raised none. All 100 forgeries of each forger took effect, and no edit that the review had missed in the main run was flagged under a forger. Five points belong beside these counts. Each forged log was reviewed once. Seventeen of GPT-6.1's logs are identical to the program's log for the same case, so the review's answer to that log was reused, which accounts for 6 of GPT-6.1's 15 flags. In 19 of its 85 missed logs GPT-6.1 added invented handovers, so that the log still shows the content reaching the place it truly reached; those logs are false, and they hide less than the planted edit alone. The program left 5 logs out of time order, and all 5 were flagged. Monitored was not run again, because its monitor does not read the log.

## Appendix D. What today's standards can carry for each rule

Table D1 sets each rule beside the fields that can carry part of it, and Table D2 writes out the two proposed fields. I read each page as raw text on 15 November 2026, and the field names below are copied from the pages. OpenTelemetry's conventions for generative AI have the status Development. FHIR Provenance, AuditEvent and Evidence are Trial Use in release 5. AI Transparency on FHIR is a draft guide; I read its continuous build and its source files, since no version has been published beyond a ballot.

Table D1. Fields that can carry part of each rule, and what I found no field for. "No standard" below means that I found no such field in the pages I read.

<!-- widths: 14,50,36 -->
| Rule | What today's standards can carry | What is missing |
|---|---|---|
| 1. The patient's words go only to named places | OpenTelemetry `gen_ai.input.messages`: "The chat history provided to the model as an input." `gen_ai.input.messages_ref`: "An absolute URI identifying the input messages in external storage." `gen_ai.transfer.target.name`: "The human-readable name of the agent targeted by the transfer." OpenTelemetry: capture is off by default (`OTEL_INSTRUMENTATION_GENAI_CAPTURE_CONTENT`, default `NO_CONTENT`). AuditEvent `agent.network[x]`, `agent.policy`: "Policy that authorized the agent participation in the event"; `entity.what`. Provenance `policy`, `authorization`, `agent.onBehalfOf`. | No standard holds a list of allowed destinations, and none has a field that says a copy went outside it. Every destination field records where data went and none says where it may go. |
| 2. Every copy is deleted by its deadline | Provenance `entity.role` code `removal`: "An entity that is removed from accessibility, usually through the DELETE operator." AuditEvent `action` code `D`: "Delete items, such as a doctor master file record." AuditEvent extension `auditevent-Lifecycle`, bound to ObjectLifecycleEvents. OpenTelemetry operation `delete_memory`. OpenTelemetry on external content: it "does not prescribe the URI scheme, object layout, serialization format, retention policy". | No standard has a deadline field, a list of copies, or a link from each copy to its deletion. A deletion can be recorded after it happens, but no field checks that it happened in time. |
| 3. Every handover is recorded, and a later edit of the record shows | Provenance `recorded` ("When the activity was recorded / updated"), `occurred[x]`, `signature` ("Signature on target"). AuditEvent `recorded` (1..1), `source.observer`: "The identity of source detecting the event". AuditEvent page text: servers "would not generally accept update or delete operations" on AuditEvent. That is advice in the page text and no field enforces it. AI Transparency `AIProvenance` is a Provenance profile and adds no integrity field. OpenTelemetry: no hash, signature or integrity attribute in the registry or spans page. | No standard has a fingerprint of the record held by an outside witness, a witness receipt, or a rule that the record is written before the handover. Provenance `signature` signs its target resource, and I found no field for a fingerprint of the log held by a third party. |
| 4. Every advice text names a true source | Evidence `citeAs[x]` ("Citation for this evidence"), `relatedArtifact`. Provenance `entity.what` with `entity.role` `source`: "An entity that is used as input to the activity that produced the target." AI Transparency `AIProvenance` entity slices `modelCard` and `inputPrompt`, both with role `derivation`. OpenTelemetry `gen_ai.retrieval.documents` (each document "SHOULD contain" `id` and `score`), `gen_ai.data_source.id`; OpenTelemetry marks retrieval attributes `Opt-In`. | No standard links a sentence in an AI answer to the document it came from. OpenTelemetry records which documents were retrieved for a call, and FHIR records which inputs fed a resource. Neither says which claim rests on which source. |
| 5. The certainty of the advice is not changed on the way | Evidence `certainty` with `type`, `rating` ("Assessment or judgement of the aspect"), `rater` ("Individual or group who did the rating"), `subcomponent`; rating codes `high`, `moderate`, `low`, `very-low` ("High quality evidence."). The Evidence page does not use the word GRADE. AI Transparency extension `AIconfidence`, context "Resource, Element": "The confidence that an AI system has in the result". Its `valueCodeableConcept` is bound (required) to `certainty-rating`, the same scale name. OpenTelemetry `gen_ai.evaluation.score.value`: "The evaluation score returned by the evaluator." | `AIconfidence` can sit on a single element and use the same four grades, so a grade can travel with a claim. It holds the AI's own confidence and has no rater, no link to the grade given by the experts, and no check that the grade arrived unchanged. OpenTelemetry has no certainty attribute; its evaluation score judges the response afterwards. |
| 6. The AI's part is marked as written by AI | AI Transparency security label `AIAST` "Artificial Intelligence asserted" in `meta.security`. Element-level label through `extension-inline-sec-label` with `PROCESSINLINELABEL` "process inline security label". `AIProvenance` `agent[AIagent].who` only `Reference(AIDevice)`, role `Artificial-Intelligence`; profiles `AIDevice`, `AIModelCard`, `AIInputPrompt`. Provenance and AuditEvent `agent.who` accept `Device`. OpenTelemetry `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model` ("The name of the model that generated the response."), `gen_ai.agent.name`, `gen_ai.operation.name`. | AI Transparency says it "does not define how AI use is determined". A label is a claim made by the system that produced the record, and the guide requires no independent check of it. OpenTelemetry names the model per call but cannot mark which part of the final text the model wrote. The base Provenance and AuditEvent pages contain no AI field and do not mention AI. |

Not opened: the code list behind the AuditEvent lifecycle extension. Sources: the OpenTelemetry repository `semantic-conventions-genai` (registry, spans and retrieval pages), the FHIR release 5 pages for Provenance, AuditEvent and Evidence with their code systems, and the source files of the AI Transparency on FHIR guide; the reference list gives the links.

### The two proposed fields

Table D2. The two fields I propose, written as five attributes of a handover event or a deletion event. The names are mine and are a starting point.

<!-- widths: 30,12,32,26 -->
| Field | Type | Meaning | Example |
|---|---|---|---|
| `custody.copy.id` | string | the copy that the receiving step now holds | `visit-0121/transcript@note-writer` |
| `custody.copy.delete_by` | timestamp | the deadline by which that copy must be deleted | `2026-11-14T10:15:00Z` |
| `custody.deletion.of` | string | on a deletion event, the id of the copy that it deletes | `visit-0121/transcript@note-writer` |
| `custody.witness.id` | string | the third party that holds a fingerprint of the record | `witness.example.org` |
| `custody.witness.fingerprint` | string | that party's signed fingerprint of the record up to and including this entry | a hash with the witness's signature |

A reader of the record lists every copy whose `delete_by` has passed and for which no event carries the matching `custody.deletion.of`. Each is an open duty. A reader who holds the witness's fingerprint computes the fingerprint of the record again and compares the two. In FHIR the same fields fit as extensions of Provenance: a deletion duty on the Provenance of a handover, and a fingerprint signed by the witness. The witness's fingerprint differs from Provenance's own `signature`, which signs the target resource.

### Where the two fields could be proposed

OpenTelemetry's conventions for generative AI have the status Development and sit in their own repository, where a change enters as a pull request and can be raised at a meeting of the project's special interest group for generative AI [9]. HL7's AI Transparency on FHIR is a ballot version with no official publication yet [13]. ISO/IEC 24970 on AI system logging reached the stage "International Standard under publication" after its final ballot closed on 24 October 2026, and I could not read its text [28]. CEN-CENELEC's joint committee for AI lists logging among the standards that will supplement its standards for the EU AI Act. Its work programme lists two logging drafts under approval: prEN 18229-3 (AI system requirements, Part 3: Logging), with a vote forecast for 30 November 2026, and the European adoption of ISO/IEC 24970 [29]. I could not read either draft.

## Appendix E. Who holds what

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

## Appendix F. Predictions as filed

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

## Appendix G. Changes after the freeze

The code, the settings, the prompts, the plan of planted violations and the scorer were frozen at Fri 13 Nov, 23:33 Pacific, each with its SHA-256 fingerprint (`live_night_e1/frozen.json`). Table G1 lists every later change, and Figure G1 places them in time. Each is logged in `night/night_notes.md`, in the two audits of Sun 15 Nov (`report_work/audits/`) or, for the judge's second pass, in `rejudge/calib/CALIBRATION_NOTES.md`.

![Figure G1. Events from the first download of data to the forger test, in order. Everything after the freeze at 23:33 on Friday 13 November is shaded. Amber dots mark changes made after it, and open dots are run events with no change. Times are Pacific.](../figures/figG1_timeline.png)

Table G1. Every change made after the freeze.

| When | What changed | Why | Could it change a reported number? | How the frozen result is kept |
|---|---|---|---|---|
| Sat 14 Nov 02:06 | Two shell scripts outside the frozen code restart the runner after a usage-limit stop (`night/chain_s.sh`) and start the outside model's texts once the clean cases are done (`night/chain_g.sh`) | At 23:43 the runner met the usage limit, did not recognise its reply and stopped | No. The audit found every planned case once under each method, none doubled, none lost | No frozen file changed |
| Sat 14 Nov 07:36 to 07:45 | The repeat check and the hidden-instruction part of Experiment 2 were started by a third script (`night/chain_one.sh`). From 07:37 every call failed with an expired sign-in, which one plain call outside the sandbox renewed at 07:45 | Running stages of the frozen plan; the sign-in expires about every 8 to 10 hours | No. Failed calls were asked again and never stored | No frozen file changed |
| Sat 14 Nov, from 07:45 | Second pass of the judge for rules 4 and 6, with corrected questions | The first question asked about the prose only, so texts with a correct source tag or AI mark counted as violations | Yes, the grades of rules 4 and 6 | Calibrated on the practice set against a condition fixed in advance; run by a separate program into new files; both keys kept (`rejudge/`) |
| Sun 15 Nov 13:11 to 13:28 | The program that takes in the answers of the monitor and the review now sets aside lines that are no flag, where it used to refuse the whole answer (`tools/run_advice.py`, `custody/ai_live.py`, `custody/score_parts.py`). Separate agents built and audited the change, and 691 tests pass | The hidden-instruction part of Experiment 1 had stopped in the night: the monitor's AI wrote out the hidden command, and the program refused such an answer | Only the hidden-instruction part of Experiment 1, which had no result before. The main table is unchanged line for line | The part ran to its end with the change declared (13:40 to 13:43) |
| Sun 15 Nov 13:14 to 13:23 | A second judge on another maker's model read 400 texts of the judge's second pass for rules 4 and 6 (`rejudge/second_judge.py`) | The outside review asked for an independent check of the corrected answer key | No. It agrees on 399 of 400 | New files only |
| Sun 15 Nov 13:18 | One expression in the Z3 generator (`model/gen_z3.py`) and a new test | The generated script crashed when a deletion aims at a place no move has filled (two connection mistakes) | No. The same change had been made in memory on Sat 14 Nov; the verdicts are the same (`report_work/audits/AUDIT_PROOF.md`) | The snapshot `night/proof/custody_z3.py` was left as it was |
| Sun 15 Nov from 13:36 | Round 2 of the planted texts for rule 5 (a target level two levels away where the scale allowed it, written by GPT-6.1 in its own words) and a corrected confirmation of 52 wrong-source texts for rule 4 (`round2/`) | Round 1's changes for rule 5 left the grade where it was in 93 of 100, by the judge's reading, and round 1's confirming program had dropped valid wrong-source texts for their form | Yes. The grades of rules 4 and 5 come from this run | New folders only (`runs/round2_e2`). The run of Sat 14 Nov is kept, and the decisions were logged before the run started |
| Sun 15 Nov 15:03 to 15:14 | The witness test (`ablation/`): four forgers against the gate's record and two checks, with no AI call. One agent built it and a second audited it | Three reviews of this report asked what the witness adds | It adds the forger results of Section 4.4 and Appendix C, part C.6, and changes no earlier number | New files only. The decision, two conditions and the predictions for the first three forgers were logged before any code was written; the fourth forger was added after their results |
| Sun 15 Nov 19:32 to 20:10 | The forger test (`forger/`): a program and GPT-6.1 forge the system's own log for the 100 edits of rule 3, and the frozen review reads the forged logs. One agent built it and a second audited it | The report said that a careful forger may leave fewer traces, without measuring it | It adds one sentence to Section 4.1 and Appendix C, part C.8, and changes no earlier number | New files only. The decision, three conditions and the predictions were logged before any code was written |

The repeat runs leave one gap: their log names call ids without the repeat's salt, so 1,017 used answers link to the store by their text only. The analysis of Sun 15 Nov also found one wrong table in the frozen scorer: the repeat check of Experiment 2 under the first answer key, where natural rows overwrite planted rows. I use the table of the second pass, which is correct.

## Appendix H. Work done before the kickoff

Work began on Thu 12 Nov 2026 at about 22:26 Pacific with the download of the public data sets, and the first project file was written at about 23:01. The sprint's kickoff talk was at 06:15 Pacific (14:15 UTC) on Fri 13 Nov. `PREKICKOFF_MANIFEST.txt` lists every file as it stood at 04:31 Pacific (12:31 UTC) that day, with its fingerprint and time.

**Before the kickoff.** The three data sets as downloaded; the wiring of a visit; the settings file; the first frame of the design (`docs/FRAME.md`); the chain's steps, the gate, the record, the witness, the review, the monitor, the bench and the scorer (`custody/`, 24 files); a first formal model (`model/`); the first prompts; the tests; and runs on stand-in text only. The visit then joined a conversation and a question in one case.

**During the sprint, on Fri 13 Nov.** I locked the first test plan at 14:37 Pacific and changed it at 14:43; version 2 followed at 16:34 and version 3 that evening. The two flows became two experiments, and a program now writes the answer of a graded question in place of an AI step. New code: the complete list and the draw by lot (`custody/planting.py`, `custody/units.py`), the outside model's part (`custody/outside.py`), the night runner and the live call tools, scoring by part, and the prompts `reviewer.v2`, `reminders.v2` and four for the outside model. The predictions were filed at 22:33, the code was frozen at 23:33, and the test set ran from 23:33.

## Appendix I. LLM Usage Statement

I collaborated with AI systems throughout this project. The idea and the key direction were mine, and both were refined in that collaboration.

- **Design.** I set the question, the six rules and the three methods, and I developed the experiment design and the test plan together with a Claude agent. I took the design decisions and filed my own predictions before the run.
- **Building and running.** Claude (Anthropic), working through Claude Code, wrote the code of the test bench, ran the experiments and analysed the results.
- **Inside the experiments.** Claude Haiku 5.5 played the AI steps, Claude Sonnet 5.5 the AI parts of the monitor and the review, and Claude Opus 5.5 the judge. OpenAI's GPT-6.1 wrote the planted texts of the second experiment and the sealed attack ideas and forged the logs of the forger test, a second GPT-6.1 model confirmed the changes for rule 5, and OpenAI's `gpt-6-astra` served as second judge.
- **Checking.** Separate Claude agents that were given no conclusions audited the code before the run and recomputed every reported number from the stored run files afterwards. GPT-6.1 reviewed the experimental work and drafts of this report, and its objections are answered in the text or listed as limits.
- **Writing.** I set the overall structure and direction of the report and gave input and feedback on each draft. Claude drafted the text from the run data and the audits and drew the figures. I reviewed and edited it and take responsibility for every line. Every number was checked against the run files by a script, and every reference was opened at its source on 15 November 2026.

### Agents and AI calls by part of the work

An agent is one separate run of a model on one task. Table I1 counts the agents started from 12 November, before and during the sprint, as the session records stood on Sun 15 Nov at 20:29 Pacific; a few ran after the count.

Table I1. AI agents by part of the work.

<!-- widths: 52,12,36 -->
| Part of the work | Agents | Models |
|---|---|---|
| Research and sources: literature, standards, data sets, numbers on the problem, past sprint reports | 52 | Claude Sonnet 5.5, Opus 5.5 |
| Design and building of the test bench | 46 | mostly Claude Sonnet 5.5; Opus 5.5, Fable 5.2, Haiku 5.5 |
| Audits of the code and of the results | 40 | Claude Opus 5.5, Sonnet 5.5, Fable 5.2 |
| Running the experiments: the first trial on the practice set | 196 | Claude Sonnet 5.5 (121), Haiku 5.5 (75) |
| Data analysis and statistics | 6 | Claude Opus 5.5, Sonnet 5.5 |
| Figures | 7 | Claude Opus 5.5, Sonnet 5.5 |
| Writing and editing | 7 | Claude Opus 5.5 |
| Reviews of the report: judges, readers, facts and reference checks | 37 | Claude Opus 5.5, Sonnet 5.5 |
| Coordination and other | 18 | Claude Opus 5.5, Sonnet 5.5 |
| **Total** | **409** | |

The 196 agents of the fourth row answered the AI steps of the first trial on the practice set. The test runs used no agents: their AI calls went to the models directly (Table I2). One coordinating assistant, on Claude Fable 5.2 and for part of the last evening on Claude Opus 5.5, started the agents and assembled their work.

Table I2. AI calls inside the experiments, by role.

<!-- widths: 46,34,20 -->
| Role | Model | Calls |
|---|---|---|
| AI steps: visit note, plan, note for the patient | Claude Haiku 5.5 | 1,793 |
| Monitor | Claude Sonnet 5.5 | 3,375 |
| Review | Claude Sonnet 5.5 | 3,370 |
| Judge | Claude Opus 5.5 | 7,038 |
| Planted texts | GPT-6.1 | 73 |
| Confirmation of planted texts | GPT-6.1, a second model | 30 |
| Sealed attack ideas | GPT-6.1 | 1 |
| Second judge | `gpt-6-astra` (OpenAI) | 240 |
| Review of the forged logs (forger test) | Claude Sonnet 5.5 | 183 |
| Forged logs (forger test) | GPT-6.1 | 102 |

## Appendix J. Data

Tables J1 and J2 and Figures J1 and J2 describe the data. Every number here is computed by `report_work/analysis/data_appendix.py` from the data files and saved in `data_appendix_numbers.json` beside it.

### The three data sets

Table J1. The three data sets as downloaded and as used.

<!-- widths: 14,23,13,17,10,10,13 -->
| Data set | What it holds | Made by | Public file | Practice and test | Licence | Real persons |
|---|---|---|---|---|---|---|
| ACI-Bench | Doctor-patient conversations with their visit notes, made for research | ACI-Bench [21] | 207 conversations in five files, all usable | 50 and 157 | CC BY 4.0 | No; the metadata hold names, which the bench does not read |
| MedEvidence | Questions from 100 systematic reviews, each with the experts' conclusion and studies, most with a certainty grade | MedEvidence [22] | 284 questions, 263 usable | 50 and 213 | MIT | No; findings about groups of patients in published studies |
| Real-POCQi | Physicians' questions put to a clinical AI tool, with stored answers from four AI systems and physicians' ratings | Real-POCQi [7] | 620 questions, 2,480 answers and 5,780 rating rows, all questions usable | 36 and 200 | CC BY 4.0 | Real physicians' questions that the authors filtered and lightly rewrote to remove identifying details |

The downloaded MedEvidence and Real-POCQi files carry no licence, so those cells give the licence on each dataset card on Hugging Face (huggingface.co/datasets/clcp/med-evidence and huggingface.co/datasets/jjfenglab/Real-POCQi) [7, 22].

![Figure J1. Each bar is one public data set, split into the test set, the practice set and the items not used. MedEvidence lost 21 questions that have no usable grade, and most of Real-POCQi was not drawn.](../figures/figJ1_case_sets.png)

### How the cases are built

Experiment 1 uses each of the 207 ACI-Bench conversations as one case. The practice set holds the first 50 of the training file by encounter number (D2N001 to D2N050), and the test set the other 157.

Experiment 2 has 499 cases. Its 413 test cases are 213 review questions, 176 with an expert grade and 37 at the level "no data", and 200 with a stored answer. Of the 263 usable MedEvidence questions in order of number, the first 50 form the practice set. All 620 Real-POCQi questions have a stored answer from the clinical AI tool used. The practice set holds 36, those an earlier joined list of visits (retired on 13 November) had placed with practice conversations, the 102nd to 137th by id sorted as text. The test set holds 200 drawn by lot from the other 584 with `random.Random(20261119).sample` over the ids sorted as text, and the script repeats the draw exactly.

No conversation or question sits in both sets, though one review supplies graded questions to both. The run files show that every test case ran in the scored runs and no practice case did. The transcripts, questions and stored answers match the downloaded files word for word, and the incoming answers for review questions are built in fixed wording (Appendix B).

### What was left out

No ACI-Bench conversation was left out, and its metadata on doctor and patient are not read. Of the 284 MedEvidence questions, 21 have no grade and an answer other than "insufficient data" (10 "no difference", 7 "higher", 3 "lower", 1 "uncertain effect"), so they have no usable grade; the 37 with no grade and that answer are kept at the level "no data". From Real-POCQi, 384 questions were not drawn, and the 1,860 answers of the other three systems and the 5,780 rating rows are unused.

### What the data looks like

Table J2. The test set's cases.

<!-- widths: 40,60 -->
| Measure | Value |
|---|---|
| Words per transcript (157) | median 1,239; range 693 to 2,707 |
| Lines per transcript, one speaker turn per line | median 48; range 7 to 136 |
| Lines by speaker tag | doctor 4,375; patient 3,993; patient guest 132; no tag 8 |
| Grade level of the review questions (213) | high 34; moderate 37; low 51; very low 54; no data 37 |
| Studies per graded question | median 2; range 1 to 10 |
| Words per stored answer (200) | median 475.5; range 162 to 887 |
| Words per stored-answer question | median 13; range 2 to 74 |
| Specialty of the stored-answer questions | Endocrinology 20; Oncology / Hematology 16; OB / GYN 14; Cardiology 13; Dermatology 13; other 124 (24 specialties) |

Words are counted between spaces, speaker tags included. The files mark speakers by line, so lines stand in for turns.

![Figure J2. The test set. (a) Length of the 157 mock consultations. (b) Grade level of the 213 review questions, 37 of them with no grade. (c) Length of the 200 stored answers. (d) Specialty of the 200 stored-answer questions. Dashed lines mark medians.](../figures/figJ2_test_data.png)

### Limits of this data

The conversations were made for research and enter as text, so the results say nothing about copies of recordings; the files do not say how the conversations were spoken, and the README notes speaker tags from speech recognition left uncorrected. The graded questions come from published reviews, so rule 5 is tested only on certainty that a program states in fixed wording from the reviews' grades. The stored answers come from one clinical AI tool, so the tests of rules 4 and 6 meet one tool's style of answer. All three sets are in English, and the 213 test questions from systematic reviews come from 74 reviews, so questions from one review are related cases.

The counts behind every cell of the results table are in Appendix C.
