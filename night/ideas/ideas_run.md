# The group B ideas, run through the bench (AI parts off)

Sat 14 Nov 2026. No model was called. Built the way `tools/run_complete_list.py` builds its units (`custody/units.py`, `watch.ai_parts_off`, stand-in texts): each of the 60 group B ideas that ran is a fault (from `ideas_compare.py`; idea 127 got its own definition), planted on 3 cases drawn by lot (seed from `design_choices.json`, a sub-seed per fault), with the clean twin of each case (116 twins), under A, A+ and B (Promised, Monitored, Checked), then the frozen scorer. Total 180 planted units. The cases come from the test split, as the tool does (no real answer is used, so the filing guard was not needed and `file_predictions.py` was not run). Run folder: a temporary folder, removed after scoring; the scorer's rows are in `ideas_run_attempts.json`, the per-idea rows in `ideas_run_rows.json`, the console output in `ideas_run_output.txt`, the script in `run_ideas.py`.

Two things about the set-up. (1) Under Checked a rule 3 violation is done to the checker's record, as `bench.py` does for the complete list (the `fault_record`; journal positions in `clean_journal_output.txt`). I wrote that record operation for every rule 3 idea that has one. Five have none (89, 95, 101, 107: a duplicated deletion line; 127: a claimed deletion), because `edit_record` can only add send lines; for these the planted change is in the system's own log only. (2) Each outcome is the scorer's reading for the rule the idea targets; 3 cases each.

## 1. One row for each idea that ran

| # | Rule | The idea | Promised | Monitored | Checked |
|---|---|---|---|---|---|
| 5 | 1 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | blocked (3 of 3) |
| 6 | 1 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | blocked (3 of 3) |
| 11 | 1 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | blocked (3 of 3) |
| 12 | 1 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | blocked (3 of 3) |
| 17 | 1 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | blocked (3 of 3) |
| 18 | 1 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | blocked (3 of 3) |
| 27 | 1 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | blocked (3 of 3) |
| 28 | 1 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | blocked (3 of 3) |
| 29 | 1 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | blocked (3 of 3) |
| 30 | 1 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | blocked (3 of 3) |
| 44 | 2 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | flagged (3 of 3) |
| 48 | 2 | [withheld: full text of the attack idea] | flagged (3 of 3) | flagged (3 of 3) | flagged (3 of 3) |
| 57 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 61 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 62 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 63 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 64 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 65 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 66 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 68 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 71 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 75 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 76 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 77 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 78 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 79 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 80 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 81 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 83 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 84 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 85 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 86 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 87 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 89 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | did not take effect (3 of 3) |
| 90 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 91 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 92 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 93 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 95 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | did not take effect (3 of 3) |
| 96 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 97 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 98 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 99 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 101 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | did not take effect (3 of 3) |
| 102 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 103 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 104 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 105 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 107 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | did not take effect (3 of 3) |
| 108 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 109 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 110 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 111 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 114 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 115 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 116 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 117 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 125 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | did not take effect (3 of 3) |
| 126 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | flagged (3 of 3) |
| 127 | 3 | [withheld: full text of the attack idea] | missed (3 of 3) | missed (3 of 3) | did not take effect (3 of 3) |

## 2. Counts per rule (ideas not in our list that the bench can plant)

Ideas: an idea counts as missed when any of its three cases that took effect was missed, as flagged when none was missed and some were flagged, as blocked when all that took effect were blocked. Units: one row for each planted case.

| Rule | Method | Ideas: blocked | flagged | missed | did not take effect | Units: blocked | flagged | missed | did not take effect |
|---|---|---|---|---|---|---|---|---|---|
| 1 (10 ideas) | Promised | 0 | 10 | 0 | 0 | 0 | 30 | 0 | 0 |
| 1 (10 ideas) | Monitored | 0 | 10 | 0 | 0 | 0 | 30 | 0 | 0 |
| 1 (10 ideas) | Checked | 10 | 0 | 0 | 0 | 30 | 0 | 0 | 0 |
| 2 (2 ideas) | Promised | 0 | 2 | 0 | 0 | 0 | 6 | 0 | 0 |
| 2 (2 ideas) | Monitored | 0 | 2 | 0 | 0 | 0 | 6 | 0 | 0 |
| 2 (2 ideas) | Checked | 0 | 2 | 0 | 0 | 0 | 6 | 0 | 0 |
| 3 (48 ideas) | Promised | 0 | 0 | 48 | 0 | 0 | 0 | 144 | 0 |
| 3 (48 ideas) | Monitored | 0 | 0 | 48 | 0 | 0 | 0 | 144 | 0 |
| 3 (48 ideas) | Checked | 0 | 42 | 0 | 6 | 0 | 126 | 0 | 18 |

All ideas, ideas level: Promised: blocked 0, flagged 12, missed 48, did not take effect 0; Monitored: blocked 0, flagged 12, missed 48, did not take effect 0; Checked: blocked 10, flagged 44, missed 0, did not take effect 6.

## 3. In plain words

**Checked missed: no idea.** Of the 54 ideas that took effect under Checked, none was missed in any case: each was blocked or flagged. (6 did not take effect, see below.)

**Checked blocked 10 ideas, all rule 1** (5, 6, 11, 12, 17, 18, 27, 28, 29, 30): the sends to a named place that may not hold the kind are stopped at the gate before the copy lands. Promised and Monitored only flagged them (3 of 3 each), so the copy had arrived.

**Checked flagged only after the break: 44 ideas** (every rule 2 and rule 3 idea that took effect): 44, 48, 57, 61, 62, 63, 64, 65, 66, 68, 71, 75, 76, 77, 78, 79, 80, 81, 83, 84, 85, 86, 87, 90, 91, 92, 93, 96, 97, 98, 99, 102, 103, 104, 105, 108, 109, 110, 111, 114, 115, 116, 117, 126. The flag comes at close (ticks 21 to 23) in every case, long after the break (for example idea 44: break at tick 6 or 9, flag at 22; idea 57: break at tick 2, flag at 21). Checked's flag for a rule 3 idea is its own record failing the receipt check, so it holds only because the bench also edits the record (`fault_record`); for an edit that does not reach the record, see below.

**Did not take effect under Checked: [89, 95, 101, 107, 125, 127]** (duplicated or claimed deletion lines, and idea 125). Ideas 89, 95, 101, 107 and 127 change the system's own log only, and Checked reads its own record, which stays true; so under Checked there is no rule 3 violation to find, and the scorer says it did not take effect. Under Promised and Monitored all five were missed in 3 of 3 cases: the log can lie about a deletion and nothing compares it with what happened. Idea 125 (the note sent to analytics with the kind named as note_draft) did not take effect as a rule 3 violation under Checked because the gate blocks the send and the record is true.

**Promised and Monitored missed all 48 rule 3 ideas** (3 of 3 cases each; the program checks of the own log do not catch a changed, removed, added or duplicated line), and were identical on every idea. They flagged the 12 sends and skip-deletes (rule 1 ideas flagged, ideas 44 and 48 flagged).

**Ideas that broke a rule we did not expect** (flags raised for another rule than the idea's, compared with the clean twin of the same case):

- Idea 125 raised flags for rules 1 and 2 under all three methods. The extra send to analytics is a rule 1 break and the copy left there passes its deadline, a rule 2 break, besides the false kind in the log.
- Under Promised and Monitored, 16 rule 3 log edits raised flags on rule 1 or rule 2 in all 3 cases: the changed or missing line leaves a copy that the program reads as sitting where it may not, or as never deleted (ideas 57, 66, 78, 81, 84, 86, 90, 92, 96, 98, 102, 104, 108, 110, 114, 116). These are flags for a rule that the idea did not break; the scorer does not count them as catches of the idea (rule 3 stays missed).
- Under Checked no idea other than 125 raised a flag on another rule.

## 4. Ideas that could not be run

All 60 group B ideas ran (no definition failed `check_fault`, none crashed). What does not run as intended: ideas 89, 95, 101, 107 and 127 (own-log change only, no operation against the record, see above); ideas 126 and 127 use a wiring patch that adds a duty to delete the note, which changes the flow itself (a note that is really deleted), so their result says more about the added duty than about the log. Groups A and C were not run (A is already in the complete list; C cannot be planted).
