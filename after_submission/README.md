# After the submission: TLC on the model

Everything in this folder was done on Sun 22 Nov 2026, a week after the report was submitted (Sun 15 Nov, about 23:10 Pacific). Nothing here is in the report, and no reported number changes.

## Why

During the sprint, two tools read the description of the wiring: the bench's own search (`custody/prove.py`) and Z3, through the script that `model/gen_z3.py` writes. Both found all 10 known connection mistakes (11 names, since F3 and PF17 are one patch) and nothing on the clean wiring (`night/proof/proofs_list.md`, Appendix C of the report). The TLA+ model, `model/Custody.tla`, was written as a third description. The sprint's own TLC run, on Sat 14 Nov, stopped with an exception (`night/proof/tlc_output.txt`), so the model was never checked before the submission.

## What ran

1. **The model as submitted.** TLC 2.19 checked `night/proof/Custody.tla` (identical to `model/Custody.tla`) with `SPECIFICATION Spec` and `INVARIANTS P1 P2 P3 P4`. It found no error: 214 states generated, 188 distinct, depth 46 (`tlc_as_submitted.txt` in this folder).
2. **Each known mistake.** `tlc_mistakes.py` applies each mistake's patch to a copy of the wiring in memory, writes the model with `model/gen_tla.py`, and runs TLC with the same configuration. TLC stops at the first state that breaks a property and prints the path to it. The models and outputs are in `tlc_mistakes/<id>/`, and the summary is `tlc_mistakes/summary.json`. The clean model it writes, `tlc_mistakes/clean/Custody.tla`, is byte-identical to `model/Custody.tla` (sha256 `19477f15ba2cce7e…`), so the generator reproduces the submitted model.

## Result

| Mistake | Rule | TLC stopped on | The bench's own search names first (14 Nov) | Distinct states TLC found |
|---|---|---|---|---|
| F2 | 2 | P2 | P2 | 72 |
| F3 | 3 | P3 | P3 | 26 |
| PF06 | 1 | P1 | P1 | 27 |
| PF07 | 1 | P1 | P1 | 9 |
| PF10 | 2 | P2 | P2 | 44 |
| PF11 | 2 | P2 | P2 | 126 |
| PF12 | 2 | P2 | P2 | 170 |
| PF14 | 2 | P2 | P2 | 113 |
| PF16 | 3 | P3 | P3 | 8 |
| PF17 | 3 | P3 | P3 | 26 |
| PF18 | 3 | P3 | P3 | 130 |
| Clean wiring | | no error | nothing | 188, all of them |

TLC stopped on every one of the 10 known mistakes (11 names, since F3 and PF17 carry the same patch) and found no error in the clean wiring. On every row it stopped on the property the bench's own search names first. Z3 also found all 10, after one repair of its generated script for two of them (Appendix G). TLC needed no change to `model/gen_tla.py`.

The list of 14 Nov also holds three clean controls, PC4, PC5 and PC6, each a rare event with no patch. The program runs them too, but they give the clean wiring's model byte for byte, because the model already explores every rare event within its bounds; their outputs are in `tlc_mistakes/` and add nothing to the clean run.

## What this shows and what it does not

The three descriptions of the wiring agree on every known mistake, and TLC can fail: on a wrong wiring it reports the broken property with a path to it. All three read the wiring as described, inside the same bounds (at most one rare event per visit, the four events of `model/README.md`). Whether the running programs follow that description is a separate question, which the report's Section 4.4 leaves open. Each row names only the first property TLC met. A mistake can break more than one: Z3 found P3 and P4 for F3, for example.

To run it again from the folder above this one, with Java and the TLA+ tools installed:

    JAVA=/path/to/java TLA_JAR=/path/to/tla2tools.jar python3 after_submission/tlc_mistakes.py
