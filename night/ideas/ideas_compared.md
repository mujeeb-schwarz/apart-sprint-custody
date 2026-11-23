# The outside model's sealed ideas against our list of plantable violations

Opened Sat 14 Nov 2026 with `python3 tools/outside_texts.py ideas --out sealed/ideas_exp1.json --open --freeze-file live_night_e1/frozen.json` (it only prints the file and renames the seal marker `ideas_exp1.json.sealed` to `.opened`; no model is called). The file holds 127 ideas (rule 1: 30, rule 2: 24, rule 3: 73). Our list is `plans/test/exp1_catalogue.json` (90 variants). Every idea is in exactly one group.

## Counts

| Group | Meaning | All | Rule 1 | Rule 2 | Rule 3 |
|---|---|---|---|---|---|
| A | already in our list | 55 | 20 | 16 | 19 |
| B | not in our list; the bench can plant it with its existing operations | 60 | 10 | 2 | 48 |
| C | not in our list; the bench cannot plant it | 12 | 0 | 6 | 6 |

Reading the groups:

- Group A is large because the model was given the step names, the places and the duties, so it wrote the same kinds of break that our list was built from. Four of its rule 2 ideas ('timer restarts') are the same planted result as a late delete: the bench counts a copy's age from its earliest arrival, so they are filed under late delete.
- Nine ideas in group A are rule 3 ideas whose planted result is a rule 2 or rule 1 kind in our list (a deletion that did not happen but the log says it did; an extra send the log leaves out or names wrongly).
- Group B is mostly the same kinds as ours, but aimed at a line our list never touches: the log line of a deletion, the source field, the lines of the rare-event handovers (resume, timeout), a duplicated line, and sends to a named place that may not hold the kind.
- Group C is what the bench has no operation for: a log line claiming a deletion at a store that no duty empties (the cache and the queue), a late deletion in those stores, and a handover that is logged while the real one is stopped.

## One row for each idea

Words: step; what is sent, kept or changed; what the log shows (shortened).

| # | Rule | The idea | Group | Our kind, or the operations, or what is missing |
|---|---|---|---|---|
| 1 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 2 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 3 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 4 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 5 | 1 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 6 | 1 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 7 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 8 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 9 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 10 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 11 | 1 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 12 | 1 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 13 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 14 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 15 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 16 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 17 | 1 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 18 | 1 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 19 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 20 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 21 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 22 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 23 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 24 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 25 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 26 | 1 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 27 | 1 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 28 | 1 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 29 | 1 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 30 | 1 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 31 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 32 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 33 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 34 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 35 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 36 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 37 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 38 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 39 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 40 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 41 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 42 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 43 | 2 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 44 | 2 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 45 | 2 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 46 | 2 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 47 | 2 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 48 | 2 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 49 | 2 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 50 | 2 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 51 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 52 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 53 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 54 | 2 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 55 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 56 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 57 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 58 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 59 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 60 | 3 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 61 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 62 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 63 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 64 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 65 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 66 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 67 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 68 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 69 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 70 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 71 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 72 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 73 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 74 | 3 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 75 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 76 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 77 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 78 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 79 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 80 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 81 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 82 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 83 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 84 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 85 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 86 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 87 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 88 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 89 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 90 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 91 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 92 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 93 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 94 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 95 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 96 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 97 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 98 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 99 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 100 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 101 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 102 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 103 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 104 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 105 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 106 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 107 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 108 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 109 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 110 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 111 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 112 | 3 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 113 | 3 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 114 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 115 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 116 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 117 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 118 | 3 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 119 | 3 | [withheld: full text of the attack idea] | C | [withheld: full text of the attack idea] |
| 120 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 121 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 122 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 123 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 124 | 3 | [withheld: full text of the attack idea] | A | [withheld: full text of the attack idea] |
| 125 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 126 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |
| 127 | 3 | [withheld: full text of the attack idea] | B | [withheld: full text of the attack idea] |

## Group B as fault definitions (not run)

Form checked with `custody.faults.check_fault` against the wiring and the design choices (it raised nothing for 59 of 59 definitions). Positions in `edit_record` and `false_log add` are the places in the system's own log of the practice case c0001 (see `clean_logs_output.txt`: no event, timeout@w3, resume@w2); under Checked the same `edit_record` edits the checker's record (its own numbering), so those positions would be set again. Twelve families are shown once; the full set of 59 is built and checked by `ideas_compare.py`, and the rest of a family changes the step, kind, place or position.

`r1_note_writer_note_draft_note_writer_cache`
```json
{
 "fault_id": "IDEA.r1.note_writer.note_draft.note_writer_cache",
 "kind": "step",
 "rule": 1,
 "says": "The step note_writer also sends its copy of the note_draft to note_writer_cache, which is a named place that may not hold a note_draft, and the system's own log shows the send.",
 "ops": [
  {
   "op": "extra_send",
   "step": "note_writer",
   "kind": "note_draft",
   "to": "note_writer_cache",
   "logged": true
  }
 ],
 "patch": [],
 "events": [],
 "needs": {}
}
```

`r1_record_note_note_writer`
```json
{
 "fault_id": "IDEA.r1.record.note.note_writer",
 "kind": "step",
 "rule": 1,
 "says": "The step record also sends its copy of the note to note_writer, which is a named place that may not hold a note, and the system's own log shows the send.",
 "ops": [
  {
   "op": "extra_send",
   "step": "record",
   "kind": "note",
   "to": "note_writer",
   "logged": true
  }
 ],
 "patch": [],
 "events": [],
 "needs": {}
}
```

`r2_skip_r1`
```json
{
 "fault_id": "IDEA.r2.skip_r1",
 "kind": "step",
 "rule": 2,
 "says": "On the timeout event the note_draft copy at note_writer_queue is never deleted.",
 "ops": [
  {
   "op": "skip_delete",
   "duty": "r1"
  }
 ],
 "patch": [],
 "events": [
  {
   "on": "timeout",
   "at": "w3"
  }
 ],
 "needs": {}
}
```

`r3_from_w2`
```json
{
 "fault_id": "IDEA.r3.w2.source_changed",
 "kind": "step",
 "rule": 3,
 "says": "The log line for w2 names note_writer_cache as the sender.",
 "ops": [
  {
   "op": "false_log",
   "step": "transcriber",
   "kind": "transcript",
   "change": {
    "from": "note_writer_cache"
   }
  }
 ],
 "patch": [],
 "events": [],
 "needs": {}
}
```

`r3_dup_w2`
```json
{
 "fault_id": "IDEA.r3.w2.duplicate_line",
 "kind": "step",
 "rule": 3,
 "says": "The log shows the handover w2 twice; it happened once.",
 "ops": [
  {
   "op": "false_log",
   "mode": "add",
   "position": 2,
   "step": "transcriber",
   "kind": "transcript",
   "from": "transcriber",
   "to": "note_writer"
  }
 ],
 "patch": [],
 "events": [],
 "needs": {}
}
```

`r3_w2c_drop`
```json
{
 "fault_id": "IDEA.r3.w2c.line_missing",
 "kind": "step",
 "rule": 3,
 "says": "On the resume event the log line for w2c is missing.",
 "ops": [
  {
   "op": "false_log",
   "step": "transcriber",
   "kind": "transcript",
   "change": null
  }
 ],
 "patch": [],
 "events": [
  {
   "on": "resume",
   "at": "w2"
  }
 ],
 "needs": {}
}
```

`r3_drop_second_w3`
```json
{
 "fault_id": "IDEA.r3.w3.second_send_missing",
 "kind": "step",
 "rule": 3,
 "says": "After the draft send times out and is sent again, the system's own log has only the first handover.",
 "ops": [
  {
   "op": "edit_record",
   "mode": "drop",
   "position": 4
  }
 ],
 "patch": [],
 "events": [
  {
   "on": "timeout",
   "at": "w3"
  }
 ],
 "needs": {}
}
```

`r3_drop_d3`
```json
{
 "fault_id": "IDEA.r3.d3.deletion_line_missing",
 "kind": "step",
 "rule": 3,
 "says": "The deletion by d3 happens and the log has no line for it.",
 "ops": [
  {
   "op": "edit_record",
   "mode": "drop",
   "position": 2
  }
 ],
 "patch": [],
 "events": [],
 "needs": {}
}
```

`r3_d3_t`
```json
{
 "fault_id": "IDEA.r3.d3.deletion_line_t",
 "kind": "step",
 "rule": 3,
 "says": "The deletion by d3 happens and its log line has the wrong time.",
 "ops": [
  {
   "op": "edit_record",
   "position": 2,
   "field": "t",
   "value": 0
  }
 ],
 "patch": [],
 "events": [],
 "needs": {}
}
```

`r3_dup_d3`
```json
{
 "fault_id": "IDEA.r3.d3.deletion_logged_twice",
 "kind": "step",
 "rule": 3,
 "says": "The deletion by d3 happens once and the log shows it twice.",
 "ops": [
  {
   "op": "false_log",
   "mode": "claim_delete",
   "duty": "d3"
  }
 ],
 "patch": [],
 "events": [],
 "needs": {}
}
```

`r3_masked_kind`
```json
{
 "fault_id": "IDEA.r3.record.note.analytics.kind_masked",
 "kind": "step",
 "rule": 3,
 "says": "The step record sends its copy of the note to analytics and the system's own log shows the send, but names the kind as note_draft.",
 "ops": [
  {
   "op": "extra_send",
   "step": "record",
   "kind": "note",
   "to": "analytics",
   "logged": true
  },
  {
   "op": "false_log",
   "step": "record",
   "kind": "note",
   "change": {
    "kind": "note_draft"
   }
  }
 ],
 "patch": [],
 "events": [],
 "needs": {}
}
```

`r3_note_duty`
```json
{
 "fault_id": "IDEA.r3.note_duty_hidden",
 "kind": "wiring",
 "rule": 3,
 "says": "A duty deletes the note at the record after the filing step, and the system's own log has no line for it.",
 "ops": [
  {
   "op": "edit_record",
   "mode": "drop",
   "position": 7
  }
 ],
 "patch": [
  {
   "op": "add",
   "path": "/plumbing/duties/-",
   "value": {
    "id": "d99",
    "kind": "note",
    "place": "record",
    "after_step": "record"
   }
  }
 ],
 "events": [],
 "needs": {}
}
```
