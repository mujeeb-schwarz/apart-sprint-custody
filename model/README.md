# The model of the wiring

**Status, Sun 22 Nov 2026, after the submission.** The rest of this page was written on Fri 13 Nov, before any formal tool had run, and is kept as written. What has run since:

- **Sat 14 Nov, during the sprint.** Z3 ran on the script that `model/gen_z3.py` writes. It found no break on the clean wiring and found all 10 known connection mistakes (11 names, since F3 and PF17 are one patch), after one repair of the generated script for two of them (`night/proof/proofs_list.md`; Appendix G of the report). TLC was tried the same night and stopped with an exception (`night/proof/tlc_output.txt`).
- **Sun 22 Nov, after the submission.** TLC 2.19 checked `Custody.tla` as submitted and found no error: 188 distinct states, depth 46 (`after_submission/tlc_as_submitted.txt`). It also stopped on each of the 10 known mistakes, each time on the property the bench's own search names first (`after_submission/README.md`).

So for these bounds, and for the wiring as described, two formal tools have checked it: Z3 on the description that `gen_z3.py` writes, and TLC on `Custody.tla`. The bench's own proof step is still the stand-in: `prove` in `custody/assemble.py` returns `not_run`. The report's main runs used Promised, Monitored and Checked with no proof step, and the report gives the proof tools' results apart (Appendix C.5).

Written on Fri 13 Nov 2026. Read this first: **no formal tool has run.** The TLA+ tools and Z3 are not installed, so `Custody.tla` has never been parsed or checked and the Z3 script has never been run. Nothing in this folder is a proof. Only a formal tool's result may be called one, and the receipt's level "proven" stays unavailable until one has run.

## What the model covers and what it assumes

| It covers | It assumes |
|---|---|
| The places where data can sit, named or not, and what each place may hold (`wiring/wiring.json`, `promise`). | The promise in the wiring is what the patient is told. No fault changes it. |
| The moves between places, each with its gate flag, and the duties that delete a copy after a move (`plumbing`). | A step can ask only for what the plumbing lists. No step can change the gate, the witness or the wiring file. |
| The deadlines: a copy may sit at a place for the hold's number of ticks counted from its arrival (`config/design_choices.json`, `holds`). | Time is logical: one tick for each step call and each handover asked. A delete with nothing to delete costs no tick. |
| The rare events: a retry after a timeout, a visit that resumes, a crash between copying and deleting, two visits that overlap (`plumbing`, `detours`), at most one event for each visit (`model`). | Only those events happen, inside those bounds. A visit with two events is outside the model. |
| Four properties. P1: no copy sits at a place that is not named or may not hold its kind. P2: no copy is present after its deadline, and none is left when the clock passes every deadline at close. P3: every move passes the gate. P4: every delivered handover has a journal record that the witness holds. | The gate, the journal written first and one witness work as the frame describes. The model records that a gated handover writes its record before it is delivered; it does not model the fingerprints. |
| The wiring as it asks, so a send asked to a place that is not named is a P1 break even though the gate would block it at run time. | A place holds at most one copy of a kind, and the earliest arrival counts. One visit runs at a time; the overlap of two visits enters as the event "overlap". |

Limits of the cross-check, in plain words:

- An event happens only where a detour in the wiring says so, one position for each event, at most one event per visit. The cross-check does not try an event at any other point.
- A path stops at its first break. The counterexample is right, but the list of broken properties and the count of situations for a faulty wiring understate what is wrong.
- A move that no lane step runs, and a detour at a position that is no placed move or duty are errors (`ContractError`). A detour on an event outside the model is never explored and is listed under `ignored_detours` in the report and in the `not_run` result.
- The "proven" level of a receipt follows the `proof` dict the receipt itself carries, and `check_receipt` compares each line against that same dict. A hand-made receipt with `{"status": "passed", "proven_rules": [1,2,3]}` would pass. Nothing in the program produces such a dict tonight. When a formal tool arrives, the witness should hold the fingerprint of the proof result and `check_receipt` should require it.
- The cross-check is not connected to the bench: `assemble.prove` is a stand-in that returns `not_run`.

## The three pieces and how they relate

All three read the same list of program points, built by `build_program` in `custody/prove.py` from the wiring file and the bounds. Change the wiring and write the pieces again; none is edited by hand.

| Piece | What it is | Status |
|---|---|---|
| `custody/prove.py` | Our own program. It tries every order of events inside the bounds (events fire only where the wiring's detours say, and a path stops at its first break), checks P1 to P4 and returns the failing sequence step by step, with the number of situations it tried. It is a cross-check. It is not a formal proof, and its result never carries the status "passed". With nothing found it returns `not_run` and lists no proven rule. | Runs and is tested. |
| `model/gen_tla.py` writes `model/Custody.tla` | The same places, moves, deadlines and four properties as a TLA+ specification, small enough to read in ten minutes. A TLA+ checker (TLC) can run it with `SPECIFICATION Spec` and `INVARIANTS P1 P2 P3 P4`. | Written, never parsed or run. |
| `model/gen_z3.py` | Writes a script that asks Z3 whether some choice of rare events breaks a property. Run `python3 model/gen_z3.py OUT.py`; with no path it prints the script. | Written, never run. Only its Python syntax is tested. |

The cross-check and the two written models are three descriptions of one wiring. When a formal tool runs one of them and finds no violation inside the bounds, that result (and only that one) is the proof for those bounds, and the joiner can then pass it on as `status: passed` with the rules it covered. Until then C equals B.

## Bounds used tonight

Holds of 10 ticks (in a visit) and 4 ticks (in a side store); at most one rare event for each visit; the four events above. On the clean wiring `prove.py` tries 210 situations in five event sets (236 before version 2 of 13 Nov, when the recording step and its moves and duties went) (no event, and each of the four events alone).
