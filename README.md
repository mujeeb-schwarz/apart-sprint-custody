# Who can retrace an AI-assisted doctor's visit?

This is the test bench behind a research sprint report written for Apart Research's "AI x Epistemics" sprint (13 to 15 Nov 2026). The report is `report_work/draft/REPORT.pdf`.
In an AI-assisted visit the patient's words go out (transcript, note, record) and advice comes in (studies, an AI answer, the doctor's plan, a note for the patient). The bench builds a working copy of that chain, runs it on public clinical data with violations planted in it, and asks, for each of six rules a patient should be able to count on, which of three methods of checking is the least that is enough.
The three methods are Promised (a review of the system's own log after the case), Monitored (a monitor that reads every handover, plus the review) and Checked (a gate at every handover with a tamper-evident record and a witness).
Every AI answer used in the report is stored, so every reported number can be worked out again from the files with no AI call.
The follow-on work, on auditable records of what AI agents did, is at https://github.com/mujeeb-schwarz/witnessed-agent-records.

## Results

No method of checking passed all six rules. The table gives the planted violations each method missed, of 100 per rule (99 for rule 5). A method passes with at most 4 misses in 100 (3 in 99) and false alarms under 5%, and the last row names the first method that passes, in the order Promised, Monitored, Checked.

| Method | Rule 1, named places | Rule 2, deleted by deadline | Rule 3, record of handovers | Rule 4, source named | Rule 5, certainty unchanged | Rule 6, AI's part marked |
|---|---|---|---|---|---|---|
| Promised | fail, missed 67 | fail, missed 33 | fail, missed 12 | fail, missed 10 | **pass**, missed 0 | fail, missed 60 |
| Monitored | **pass**, missed 0 | fail, missed 33 | fail, missed 12 | **pass**, missed 1 | fail, missed 0, false alarms 25% | **pass**, missed 0 |
| Checked | **pass**, all blocked | **pass**, missed 0 | **pass**, missed 0 | fail, missed 45 | fail, missed 2, false alarms 25% | **pass**, missed 0 |
| **Least enough** | Monitored | Checked | Checked | Monitored | Promised | Monitored |

A review of the system's own log and final texts was enough for one rule, and a monitor for three more. Only the gate's record, with its witness, caught the copies never deleted and the planted edits of the record. This is Table 2 of the report (`report_work/draft/REPORT.pdf`, section 4), and "Recomputing the reported numbers" below works it out again from the stored files.

## Layout

| Path | What it holds |
|---|---|
| `docs/FRAME.md` | The contract every part is built to: data model, chain, conditions, the six rules, bench and scorer |
| `wiring/wiring.json` | The wiring of a visit: places, allowed moves, deadlines, named places. The chain and the formal model both read it |
| `config/design_choices.json` | Every tunable choice in one file: thresholds, the certainty ladder, deadlines, counts, prompts, the pass mark |
| `custody/` | The code: the chain's steps, the gate and its checker, the record and witness, the review, the monitor, the bench, the planting of violations, the scorer |
| `prompts/` | The instructions given to each AI step, one file per version |
| `tools/` | Programs to build cases, draw a plan, run the bench, check a receipt and score a run |
| `tests/` | The main tests (no AI call) |
| `model/` | The formal model of the wiring: a TLA+ model and a Z3 script, both written from the wiring file. What has checked them, and when, is at the top of `model/README.md` |
| `plans/` | The plans drawn by lot for the practice (`tune/`) and test (`test/`) splits |
| `faults/practice/` | The practice violations used during development |
| `data/cases/` | The cases of both experiments, built from the public data sets; these are what the runs used. The MedEvidence study texts are withheld in this copy, and `tools/restore_study_texts.py` puts them back from the data set (see "Data and licences"). Rebuilding the cases needs the raw sets (`data/raw/README.md`) and `data/retired/visits.jsonl`, the earlier joined list the splits were drawn from, which is not included |
| `runs/` | Every run folder: inputs and outputs as JSON lines, the record, the witness log, receipts, scores |
| `live_*/` | The exported AI calls and the stored answers of each live run |
| `rejudge/` | The second pass of the judge for rules 4 and 6, and its calibration |
| `round2/` | Round 2 of the changed texts of Experiment 2 |
| `outside/`, `sealed/` | The outside model's work: changed texts, confirmations, judge calls, and the sealed attack ideas |
| `ablation/` | The witness test: what each part of the tamper-evident record adds |
| `forger/` | The AI forger test for rule 3 |
| `night/` | The night runner's plans and logs, and the formal proof's output |
| `report_work/` | The report: `draft/` (the built report and its sources), `appendix/`, `analysis/` (the scripts that recompute the numbers), `figures/`, `refs/`, `build/` |
| `after_submission/` | Work done on Sun 22 Nov 2026, a week after the submission: TLC on the model as submitted and on the model of each known connection mistake. Nothing in it is in the report |
| `PREKICKOFF_MANIFEST.txt` | Every file that existed before the sprint's kickoff, with its sha256 |

Folders named `private/` hold blinded tokens, id maps and stored calls, and no credentials.

## Running the tests

The tests make no AI call. Python 3.9 and the standard library are enough. From the repository root:

    python3 -m unittest discover -s tests
    python3 ablation/tests/test_witness_test.py
    python3 forger/tests/test_forger.py
    python3 round2/tests/test_round2.py
    python3 rejudge/tests/test_rejudge.py

Counts for the main suite (`tests/`, 691 tests), with `z3-solver` installed (without it the Z3 tests skip too):

- This repository as published, without the public data sets: 617 passed, 73 skipped, 1 expected failure. Measured on Sun 15 Nov 2026, and again on Sun 22 Nov, after the study texts were withheld.
- With the three public data sets downloaded into `data/raw/` (see `data/raw/README.md`): 689 passed, 1 skipped, 1 expected failure, measured on Sun 15 Nov, before the study texts were withheld. Since Sun 22 Nov, put the texts back first with `python3 tools/restore_study_texts.py`. Until then `test_cases.TheTwoLists` fails: it rebuilds the cases from the data sets and compares them with `data/cases/`, which holds the markers. On Sun 22 Nov, in a copy that also had `data/retired/` (so the test that needs it ran too), the suite gave 690 passed and 1 expected failure with the texts restored, and that one failure before.

The skipped tests read the public data sets and say so in their skip message (`tests/raw_data_guard.py`); with the data in place they run unchanged. The one test still skipped with the data needs `data/retired/visits.jsonl`, an earlier case list that is not included. The expected failure is `test_lenient_import.NothingStoredChanges.test_stored_answers`. In 77 stored monitor and review answers, a command line written out by the model follows the FLAG lines, and the strict answer format rejects it. The runs used the lenient import, and the report counts these lines (Appendix A.2). The extra suites pass: 10, 13, 19 and 10 tests.

Other parts need more than the standard library: `z3-solver` for `model/` and the proof scripts; `matplotlib` and `numpy` for the figures in `report_work/figures/`; `python-docx`, `lxml`, `pypdf` and LibreOffice for `report_work/build/`.

The end-to-end check runs sixteen visits of each experiment under every condition with fixed text and no AI at all:

    python3 tools/run_e2e.py

## Recomputing the reported numbers

Every script below reads the stored files only and makes no AI call.

- Scores of one run folder: `python3 tools/score.py runs/night_e1` (and `runs/night_e2`, `runs/night_e2_second_pass`, `runs/round2_e2`, `runs/round2_e2_second_pass`). The parts reported apart (the hidden instruction, the repeat check, results by kind): `python3 tools/score_parts.py RUN_DIR`.
- The tables of the results and Appendix C: `cd report_work/analysis/scripts && python3 build.py && python3 after_review.py` (writes `tables.json`), then from the repository root `python3 report_work/analysis/final_scripts/final_numbers.py .`, `python3 report_work/analysis/final_scripts/add_other_numbers.py .` and `python3 report_work/analysis/final_scripts/rule5_levels.py .`. Run on this copy on Sun 22 Nov 2026, the sequence gives the same `final_numbers.json`, which holds the report's numbers (Appendix C names the exceptions). `tables.json` comes out with a new date, three counts under `same_text` 100 higher (652, 652 and 420 in place of 552, 552 and 320), and a key the stored file lacks, `cases.e1.hidden` (100). The stored `tables.json` was built at 13:37 on 15 Nov, before the last write of `runs/night_e1` at 13:42 added the 100 cases of the hidden instruction, and the report cites none of these.
- An independent recomputation by the statistical reviewer, with its own exact intervals: `report_work/analysis/review_scripts/recompute.py` and the other scripts in that folder.
- The witness test: `python3 ablation/witness_test.py --out ablation/out`.
- Appendix J (data): `python3 -I report_work/analysis/data_appendix.py` (needs `data/raw/`).
- Re-running `tools/score.py` in this copy rewrites `scores.json` with `page_matches_filing` false, because the predictions page was edited for publication; the scores themselves are unchanged.
- The report PDF cannot be rebuilt from the repository alone: `report_work/build/` needs Apart's Word template (not included) and LibreOffice. The PDF and its Markdown sources are included in `report_work/draft/`.
- The working notes and audits behind the report are not in this copy: the night log, the audits of the bookkeeping and of the proof, the calibration notes, the builders' notes and the notes on where each number comes from. Appendix G lists every change after the freeze with its date, reason and effect on the numbers, and the raw notes are available from the author on request. Without the night log, the timeline check in `report_work/figures/figG1_timeline.py` cannot run here; the figure itself is included.

## What predates the sprint's kickoff

Work began on Thu 12 Nov 2026 at about 22:26 Pacific with the download of the public data sets. The kickoff talk was at 14:15 UTC on Fri 13 Nov. `PREKICKOFF_MANIFEST.txt` lists every file as it stood at 12:31 UTC that day, with its fingerprint and time. Before the kickoff: the data sets as downloaded, the wiring, the settings file, the first frame of the design, the chain's steps, the gate, the record, the witness, the review, the monitor, the bench and the scorer (`custody/`, 24 files), a first formal model, the first prompts, the tests, and runs on stand-in text only. Everything else, including the two experiments, the planting by lot, the outside model's part, the live runs and the predictions, was made during the sprint (Appendix H of the report).

## What needs AI calls, and is stored instead

These parts called models and are not needed to recompute anything, because their answers are stored:

- The live runs (`tools/run_live.py`, `tools/answer_calls.py`): the AI steps, monitor, review and judge, answered by Claude models through the Claude Code command-line program. Prompts and answers are in `live_*/` and the run folders in `runs/`.
- The outside model (`tools/outside_texts.py`, `custody/outside.py`): changed texts, attack ideas and a second judge, through the Codex command-line program. Stored in `outside/`, `sealed/` and `round2/`.
- The second pass of the judge (`rejudge/rejudge.py answer`) and the AI forger test (`forger/run.py f1`, `f2`).

Running any of these again needs those programs and an account; the stored answers are what the report rests on.

The public copy also differs from the working copy in tools/answer_calls.py and config/design_choices.json (wording withheld, paths and names removed). The fingerprints in live_*/frozen.json and config/predictions_filed*.json are those of the working copy, so the freeze guard (tools/run_advice.py) refuses a new live run here.

Note: the exact wording of the hidden instructions has been withheld in this copy (see below). Replaying the hidden-instruction runs from scratch therefore cannot reproduce those prompts byte for byte; the stored answers and every score computed from them are unchanged.

## Data and licences

The code in this repository is under the MIT licence (`LICENSE`). The cases in `data/cases/` and the texts in the run folders are derived from ACI-Bench (CC BY 4.0), MedEvidence (MIT) and Real-POCQi (CC BY 4.0), and keep those licences. The consultations are mock ones made for research; any patient in a figure is invented from that public data. See `data/raw/README.md` for the sources.

## Data credits

- **ACI-Bench.** Yim, W., Fu, Y., Ben Abacha, A., Snider, N., Lin, T., Yetisgen, M., Scientific Data 10, 586 (2023); https://github.com/wyim/aci-bench. Licence CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The texts in `data/cases/` and in the run folders were selected and reformatted from it.
- **MedEvidence.** Polzak, C., Lozano, A., Sun, M. W., Burgess, J., Zhang, Y., Wu, K., Yeung-Levy, S., arXiv:2505.22787 (2025); https://huggingface.co/datasets/clcp/med-evidence. Licence MIT (https://opensource.org/licenses/MIT). The texts in `data/cases/` and in the run folders were selected and reformatted from it.
- **Real-POCQi.** Feng, J., Patel, V., Heagerty, P., Mai, Y., Sivaraman, V., Vossler, P., Ouyang, J., Jena, A. B., arXiv:2606.28960 (2026); https://huggingface.co/datasets/jjfenglab/Real-POCQi. Licence CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The texts in `data/cases/` and in the run folders were selected and reformatted from it.

The MedEvidence data set is under the MIT licence, and the studies it quotes stay under their publishers' licences. So on Sun 22 Nov 2026, a week after the submission, the study texts of the MedEvidence cases were withheld from this copy: 574 texts from 304 studies. 72 of the studies are full articles of 17,000 to 78,000 characters, and they make up 176 of the texts; the other 232 studies are shorter texts of at most 3,921 characters. Each text is replaced with a marker that names its question and its source, for example `[study text withheld: medev:0 pmid:17466514]`, in the 16 files that held one: `data/cases/exp2.jsonl`, and run and calibration files in `runs/` and `rejudge/calib/` that hold copies of its texts. `data/cases/withheld_study_texts.json` lists them. The titles and source ids stay. To put the texts back, download MedEvidence into `data/raw/` and run `python3 tools/restore_study_texts.py`. It checks that each file then has the sha256 it had before. The numbers do not depend on the texts: recomputed with the texts withheld and with them restored, `tables.json` and `final_numbers.json` come out the same as each other.

## Dual use, and the withheld wording

A list of what a log review cannot see helps both a buyer and a vendor who wants to pass a review while breaking a promise. The kinds of violation and the counts are published here. The exact wording of the hidden instructions used in the hidden-instruction parts of both experiments is not: wherever it appeared (settings, plans, run files, exported prompts and stored AI answers that quote it), it has been replaced with `[hidden instruction: wording withheld, see Appendix A.2 of the report]`, and, in stored monitor and review answers, every quotation of a test wording and every close repetition of its phrases with `[withheld]`. Descriptions in the model's own words are kept, and so is the rest of each answer. Counts and outcomes are unchanged. The practice wording used for development and in the no-AI tests is kept, because the tests depend on it.

The outside model's sealed attack ideas (127, in `sealed/ideas_exp1.json` and copied in `night/ideas/`) are published by kind and count only. Each idea's own sentences are replaced with `[withheld: full text of the attack idea]`. The kept files give each idea's shape: its number, rule and step, its group (already in our list, new and plantable, or new and not plantable), and for each idea that ran its fault key (step, kind and place) and outcome per method and per case. `night/ideas/ideas_compared.md` keeps 12 example fault definitions, one per family, which show the kind, the place and what the log is made to show. `night/ideas/ideas_tally.json` holds one row per idea, and `python3 night/ideas/tally_ideas.py` recomputes the counts from it: 127 ideas, 60 new and plantable, 54 that took effect under Checked, none missed by Checked, and all 48 aimed at rule 3 missed by Promised and by Monitored. Without the text, `night/ideas/ideas_compare.py` and `run_ideas.py` cannot be run again from the start.

The two predictions pages have the author's name, a session label and one local path replaced. The fingerprint in `config/predictions_filed.json` is that of the page as filed, which the author keeps.

The witness key in `config/design_choices.json` is a fixed test key, written in plain text on purpose so that stored files come out the same every time; a real witness would use its own key.
