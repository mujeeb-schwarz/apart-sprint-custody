# The proof's list: connection mistakes, a proof tool, and what Checked does

Written Sat 14 Nov 2026. No AI model was called. Z3 is version 5.4.1. The wiring file was never changed (every patch was applied to a copy in memory).

## The list

The bench knows 11 connection mistakes: F2 and F3 (`config/design_choices.json`) and PF06, PF07, PF10, PF11, PF12, PF14, PF16, PF17, PF18 (`faults/practice/practice_faults.json`). `practice_advice_faults.json` holds no connection mistake (PA01 to PA13 are all of the kind "step"). The three clean cases PC4, PC5 and PC6 (a rare event with no patch) are controls, shown under the table.

Columns: "Own search" = `custody/prove.py` on the patched wiring (the property it names first). "Z3" = the Z3 script that `model/gen_z3.py` writes for the patched wiring (sat = a path breaks a property). Promised / Monitored / Checked = the scorer's outcome when the mistake is planted on one practice case with stand-in texts (c0001 for the first flow, q0001 for the second).

| Mistake | Its sentence | Patch | Rare event | Own search | Z3 | Promised | Monitored | Checked |
|---|---|---|---|---|---|---|---|---|
| F2 (rule 2) | When the draft send is retried after a timeout, the copy of the draft parked in the retry queue is never deleted. | remove `detours/r1/do/2` | timeout at w3 | finds P2 | sat (P2, timeout@w3) | flagged | flagged | flagged |
| F3 (rule 3) | The note draft reaches the chart by a path that skips the gate, so no record is written. | `moves/w3/via_gate` = false | none | finds P3, P4 | sat (P3, P4) | missed | missed | missed |
| PF06 (rule 1) | When the draft send times out, the retry copy of the note draft goes to a troubleshooting store instead of the retry queue. | `moves/w3q/to` = debug_bucket | timeout at w3 | finds P1 | sat (P1) | flagged | flagged | blocked |
| PF07 (rule 1) | When the visit pauses and resumes, the cached transcript goes to a store of training examples by a side road that skips the gate and the log. | `moves/w2c/to` = training_store; `via_gate` = false | resume at w2 | finds P1 (also P3, P4) | sat (P1, P3, P4) | missed | missed | missed |
| PF10 (rule 2) | When the visit pauses and resumes, the transcript parked in the note service's cache is never deleted. | remove `detours/r2/do/2` | resume at w2 | finds P2 | sat (P2, resume@w2) | flagged | flagged | flagged |
| PF11 (rule 2) | When two visits overlap, the note service's deletion of the transcript does nothing at its time and happens only at close. | remove `detours/r4/do/0` | overlap at d4 | finds P2 | sat (P2, overlap@d4) | flagged | flagged | flagged |
| PF12 (rule 2) | The duty that deletes the patient note from the summary service's store is removed from the wiring. | remove `duties/d10` | none | finds P2 | sat (P2) | flagged | flagged | flagged |
| PF14 (rule 2) | After a crash, the restart deletes the transcript at the note service's cache, where it never was, instead of at the scribe service. | `detours/r3/do/0` = delete transcript at note_writer_cache | crash at d3 | finds P2 | sat (P2, crash@d3) | flagged | flagged | flagged |
| PF16 (rule 3) | The transcript reaches the note service by a path that skips the gate. | `moves/w2/via_gate` = false | none | finds P3, P4 | sat (P3, P4) | missed | missed | flagged |
| PF17 (rule 3) | The note draft reaches the chart by a path that skips the gate. | `moves/w3/via_gate` = false | none | finds P3, P4 | sat (P3, P4) | missed | missed | missed |
| PF18 (rule 3) | The plan reaches the summary service by a path that skips the gate. | `moves/a3/via_gate` = false | none | finds P3, P4 | sat (P3, P4) | missed | missed | flagged |

Counts: own search finds 11 of 11; Z3 finds 11 of 11 (sat); on the unpatched wiring both find nothing (own search ok, Z3 unsat), so the two tools agree with each other on every row. Checked: 1 blocked (PF06), 7 flagged (F2, PF10, PF11, PF12, PF14, PF16, PF18), 3 missed (F3, PF07, PF17). Promised and Monitored: 0 blocked, 6 flagged (F2, PF06, PF10, PF11, PF12, PF14), 5 missed (F3, PF07, PF16, PF17, PF18); Monitored equals Promised on every row.

Controls (PC4, PC5, PC6): the unpatched wiring plus one rare event. Own search and Z3 find nothing (as for the clean wiring), and in the replay the scorer reports "did not take effect" under all three methods with no signal raised. That is the correct result: the rare events alone break nothing.

## In plain words

Blocked means the violation never happened. Flagged means it happened and a flag followed. Missed means it happened and no flag ever came. In the scorer's rows the violation comes first in every flagged case (for example F2: violation at tick 9, flag at tick 22).

**Checked lets 10 of the 11 mistakes happen.** Only PF06 (the retry copy sent to a store that is not named) is blocked, because the gate stops that send. The other ten take effect, and a proof tool finds every one of them before any case runs:

- Seven are flagged after they happened: F2, PF10, PF11, PF12, PF14 (a copy that stays past its deadline; the flag comes at close, ticks 20 to 22, long after the break at ticks 6 to 16) and PF16, PF18 (a handover that skips the gate; the flag comes two ticks after the break, when the next handover shows the missing record).
- Three are never flagged: F3 and PF17 (the note draft reaches the chart without a record; the same patch, tested twice) and PF07 (the transcript goes to a training store by a side road that skips the gate and the log). Under Checked they stay invisible in this replay, though both tools find them in the wiring at once. They are the cases where a proof does what no method does at run time.

Own search and Z3 agree on all 11, so for this list the proof adds no mistake the own search misses. What the proof's list shows is that it covers all three Checked-missed mistakes and the seven flagged-after ones in advance.

## What could not be expressed, and what to know

- Nothing in the list was inexpressible: every patch changes only moves, duties, detours or a gate flag, which is what the Z3 program models. Step mistakes (kind "step", for example F7) change what a step does to a text and are not in the Z3 program at all.
- One repair was needed for Z3 on PF06 and PF07. The generated script crashed with a KeyError because it reads an arrival tick for a place that a delete aimed at while no move had filled it (the patch sends the retry copy elsewhere, so the retry queue is never filled). `proof_list.py` changes one expression in the generated text in memory (`st.arr[key]` becomes `st.arr.get(key, IntVal(0))`; the place has no copy, so the value is never used). `model/gen_z3.py` was not edited. Unrepaired, the script would crash on those two. Worth fixing in the generator.
- The events Z3 prints for the gate-skip mistakes (F3, PF16, PF17, PF18 show "timeout@w3") are not needed for the break; the solver picked any assignment. Those mistakes break on the normal path (the own search shows none).
- Both tools judge the wiring by what it asks. PF06 is a P1 break for them even though, at run time, the gate blocks the send; that is why the replay says blocked while the proof says broken.
- One replay per mistake on one practice case with stand-in texts; the outcome for F3, PF17 and the others is one case, not a rate. The own search's list of broken properties for a faulty wiring understates what is wrong (it stops at the first break).

Files: `proof_list.py` and `proof_list_output.txt` (parts a and b, with each counterexample's events), `proof_rows.json` (full traces), `replay.py`, `replay_output.txt`, `replay_rows.json` (part 3).
