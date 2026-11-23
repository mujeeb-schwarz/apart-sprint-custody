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

**AI systems now handle records that people must be able to trust later.** In American Medical Association surveys of US physicians, the share using AI rose from 38% in 2023 to 72% in 2026; in 2026, 28% used it for documentation such as visit notes and 39% for summaries of medical research, up from 21% and 13% in 2024 [@ama2026]. At one US medical group 7,260 physicians used an AI scribe in 2.58 million patient visits within fifteen months [@tpmg].

**Such a record moves through a chain of AI steps, and what happens to it there is hard to check from outside when the only account is the one the vendor writes.** I start with the doctor's visit because the stakes and the gap are both large there. A patient's words can reveal an illness that no one else knows of, and an AI scribe passes them on within minutes to a vendor's systems. In 2024, business associates, the vendors that act for US health care providers and insurers, accounted for 207 of the 243 million people affected by large breaches of health records, counted breach by breach [@hhsbreach]. In a national survey in 2023, 65.8% of US adults had low trust that their health system would use AI responsibly [@nong]. The patient's legal right to an account of who received their records also leaves out disclosures for treatment, payment and health care operations [@hipaa528].

**Two flows of information pass through AI during and after a visit, and each carries promises.** In the first the patient's words go out: an AI scribe, such as Microsoft's Dragon Copilot, Suki, Freed or Doximity Scribe, drafts the note, and its vendor promises where the words may go and when every copy is deleted; these four vendors' pages say that visit audio is kept for anywhere from no time to 90 days [@vendorpages]. In the second, advice comes in: an evidence tool such as OpenEvidence [@realpocqi] answers the doctor's question, and the doctor counts on the answer to name its true source and to keep the certainty of the evidence. The vendor's account of either flow is the *system's own log*, which the vendor writes and can also change, and in which a kept copy marked "deleted" looks like one that is gone. I test each flow in its own experiment and model a step or an operator that breaks a promise while the log says it was kept; an operator who also controls the witness defeats every method here (Section 4.4).

**I measured which way of checking is enough for which promise**, on a test bench simulating a visit with public data: a review of the system's own log and final texts (*Promised*), the same review with a monitor on every message (*Monitored*), and a checkpoint on every handover, the *gate*, that keeps its own record, with a simulated witness (*Checked*). Figure 1 shows one such visit, with words from a mock consultation and two of the planted violations.

**My main contributions are:**

1. **An answer to the sprint's second track**, which asks what minimal tamper-evident layer is missing from AI observability standards [@apart]. My answer, for the five standards I read, is a record of handovers and deletion duties whose fingerprints a witness holds, which two new fields would add (Appendix D).
2. **A measurement of which check is enough for which promise.** No method passed all six rules: a review of the system's own log and final texts was enough for one promise and a monitor for three more, while only the checkpoint's record caught the copies never deleted and the planted edits of the record (Table 2).
3. **A test bench for promises about records and the code to rerun it.** It grades any way of checking against six rules, 599 planted violations on public data and a pass mark filed before the run.

![Figure 1. One visit on the test bench. The words are from a mock consultation in ACI-Bench, and the note line is the AI note writer's stored output. Two planted violations, marked 1 and 2, are drawn together for illustrative purposes; each test case holds one. Each chip gives a method's outcome on all 33 cases of that kind, and the tiles name the first method that passed each rule.](../figures/fig1_visit_example.png)

## 2. Related Work

**Most similar prior work.** Five current standards describe the events that AI systems and health record systems log: OpenTelemetry's conventions for generative AI [@otel], the HL7 FHIR resources Provenance [@fhirprov], AuditEvent [@fhiraudit] and Evidence [@fhirevidence], and HL7's draft guide AI Transparency on FHIR [@aitfhir]. Tamper-evident logs, which an untrusted logger cannot rewrite unnoticed, have been studied for years [@crosby] and already record more than 2.5 billion web certificates [@ct; @ctsite]. Others report that output-only audits miss 41.7% of violations in multi-agent systems [@agentleak]. Agent defences that label data and check each tool call are built to stop a wrong send [@camel; @fides], and adaptive attacks can subvert AI monitors [@terekhov].

**Limits of the state of the art.** The five standards ask for no outside witness, and I found no field in them for the list of places data may go, for a deletion deadline with its copies, or for a third party's fingerprint of the record (Appendix D). In the work I read, no study measures when a tamper-evident log is needed.

**What this work adds, and when to use it.** My gate uses labels as those defences do and adds a duty that falls due later, such as a deletion. The measurement shows, promise by promise, which of the three ways of checking is enough, and a clinic or an auditor can rerun the bench on the promises that matter to them.

## 3. Methods

**Two experiments on public data** (Figure B1, Appendix B). In Experiment 1 the patient's words go out: a transcribing service hands the transcript to an AI note writer, which hands its draft to the medical record, and each step must delete its copy by a deadline. Its 157 test cases are mock consultations from ACI-Bench [@acibench]. In Experiment 2 advice comes in: an evidence tool's answer to the doctor's question becomes a plan and then a note for the patient, each written by an AI step. Its 413 cases are 213 questions from systematic reviews, 176 with the reviewers' grade of certainty (MedEvidence [@medevidence]), and 200 questions that physicians put to OpenEvidence, a clinical evidence tool (Real-POCQi [@realpocqi]).

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
4. *Proven* is Checked with a proof step: before any case runs, a search program and Z3 [@z3], a solver that checks logical statements, each look in the wiring for a path that breaks rules 1 to 3.

**How the gate keeps its record.** Content carries labels from the moment it enters: its sources, grade of certainty, AI origin, allowed places and deadline. At each handover the gate reads the labels, blocks a send to a place that is not allowed, and writes the handover into its record. A deletion enters the record only when it passes the gate, so a copy that is never deleted leaves an *open duty* after its deadline. The gate gives a *fingerprint* of each entry, a short value that changes with the entry and includes the fingerprint before it, to a *witness* that stands for a party outside the vendor, and after the case the bench issues a *case receipt*, a fingerprint of the record.

**Models and grading.** Claude Haiku 5.5 played the AI steps, Claude Sonnet 5.5 the AI parts of the review and the monitor, and Claude Opus 5.5 the judge of Experiment 2, with which a second judge, OpenAI's `gpt-6-astra`, agreed on 783 of 800 readings (none from the second round of rule 4). AI agents built and ran the bench under my direction (Appendix I). A planted violation is *blocked* when the method stops it beforehand, *flagged* when the method raises a flag for that rule at or after the violation, and *missed* otherwise; a flag on a clean case is a *false alarm*. A method *passes* a rule when the upper end of the exact 95% interval of its miss rate stays under 10% [@scipy], which allows 4 misses in 100, and when it raises false alarms on fewer than 5% of clean cases. The *least enough* method is the first of Promised, Monitored and Checked that passes.

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

**A gate helps only where a handover passes through it, so a flow wired wrong defeats it.** I replayed 10 known wiring mistakes, such as a handover that skips the gate, once each under Checked alone: it blocked 1, flagged 7 after the break and missed 2. Proven's search program and the Z3 solver [@z3] each found all 10 in the description of the wiring before any case ran (Appendix C). A running program that departs from that description could escape both.

**Two things escaped every method.** A copy that a step keeps without handing anything over meets no gate, no monitor and no log, and all 20 such cases were missed. An operator who rewrites the gate's record, the witness's copies and the case receipt together also escapes (Figure C3).

## 5. Discussion and Limitations

**For AI safety, the result shows what oversight through logs and monitors missed here.** Both shared a blind spot. A deletion that does not happen sends no message for a monitor to read, and a review learns of it only from the log, which in these cases said the deletion was done. An AI reviewer that reasons from the same log is no better placed, and against a log rewritten by another AI model it caught 15 of 100 edits. In this bench the gap closed when a part outside the acting step kept its record of what was due.

**Two fields would carry the gate's record into today's standards, one for each rule that only Checked passed.** For rule 2, a *deletion duty* in the handover entry names the copy that a step received and its deadline, and the later deletion event points back to it, so that a reader can list every duty still open. For rule 3, a *witness receipt* gives a third party's signed fingerprint of the record up to this entry, so that a later reader can tell whether the record is the one the witness saw. Appendix D writes both out for FHIR Provenance and for OpenTelemetry's generative AI conventions [@otel].

**The EU AI Act leaves the same gap for records outside health care.** From 2 December 2027 the EU AI Act's logging and log-keeping duties apply to new high-risk systems in areas such as education, employment, public benefits, migration and justice [@euaia; @omnibus]. The articles that set these duties ask neither for a tamper-evident log nor for a third party to hold it.

**Limitations** (Appendix A has more, with the dual-use risks).

- **The violations were planted**, and where a program decides, 100 cases repeat a few variants (12 for rule 2, 14 for rule 3). The counts measure what each method can see and give no rate of real violations.
- **Checked rests on three assumptions:** correct labels at entry, a gate on every handover and deletion, and an honest witness, which ran in the gate's own process with a test key (Appendix E). I did not test wrong labels or a false deletion report: a wrong label would let the gate pass a send it should block, and a vendor-run witness would leave rule 3 resting on careless edits only. Checked also differs from the other methods in several ways at once, so the bench isolates the witness only on rule 3 (Figure C3) and the gate on no rule.
- **The answer key of Experiment 2 is an AI judge.** Its question for rules 4 and 6 was corrected after the first run, a planned human reading of 40 texts did not take place, and one family of models played the steps, the monitor, the review and the judge.

**Future work.** Next come a witness run by a second party, a run without the gate, and the same bench on school or public-office records. Building the gate into one working scribe or evidence tool, with a vendor or a clinic, would then show the technical problems of real use, such as labelling content at entry and deleting copies in backups, and the barriers to adoption, such as who runs the witness. The two fields would go to OpenTelemetry's generative AI conventions as a pull request.

## 6. Conclusion

A log written by the vendor of an AI system can show only what the vendor records. In this bench such a log hid every copy that it wrongly called deleted, and a monitor on every message did not see those copies either. Once another AI model had rewritten the log, a review of it caught 15 of 100 edits. The checkpoint's record, with fingerprints at a simulated witness, showed the kept copies and every planted edit of that record, but let through advice naming a wrong source, which the monitor caught. The two fields proposed here would give that record a place in AI logging standards. Until they do, a clinic can ask its AI scribe vendor, in its contract, for this record and for a witness the vendor does not run, and so check reported deletions and edits itself.

## Code and Data

**Code and stored runs:** a repository that recomputes every reported number, available on request until its public release; parts predate the kickoff (Appendix H). **Data sets:** ACI-Bench [@acibench], MedEvidence [@medevidence], Real-POCQi [@realpocqi].

