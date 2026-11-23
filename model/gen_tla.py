"""Writes model/Custody.tla from wiring/wiring.json and config/design_choices.json.

The TLA+ tools are not installed, so the file it writes has never been checked
by TLC. The file says so at its top. A formal tool's result is the only thing
that may be called a proof; this generator proves nothing.

    python3 model/gen_tla.py [OUT_PATH]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custody.prove import build_program, load_choices, load_wiring  # noqa: E402


def s(x) -> str:
    return json.dumps(x)


def op_tla(op) -> str:
    t = op["t"]
    if t == "intake":
        return '[t |-> "intake", place |-> %s, kind |-> %s]' % (s(op["place"]), s(op["kind"]))
    if t == "step":
        reads = "{" + ", ".join(s(k) for k in op["reads"]) + "}"
        return '[t |-> "step", id |-> %s, place |-> %s, reads |-> %s, makes |-> %s]' % (
            s(op["id"]), s(op["place"]), reads, s(op["makes"]))
    if t == "send":
        return ('[t |-> "send", move |-> %s, kind |-> %s, from |-> %s, to |-> %s, gated |-> %s, need |-> %s]'
                % (s(op["move"]), s(op["kind"]), s(op["from"]), s(op["to"]),
                   "TRUE" if op["gated"] else "FALSE", s(op["need"])))
    if t == "delete":
        return '[t |-> "delete", kind |-> %s, place |-> %s, need |-> %s]' % (s(op["kind"]), s(op["place"]), s(op["need"]))
    return '[t |-> "close"]'


def seq(ops) -> str:
    return "<<" + ", ".join(op_tla(o) for o in ops) + ">>"


HEADER = r"""---------------------------- MODULE Custody ----------------------------
(***************************************************************************)
(* NOT YET CHECKED. The TLA+ tools (TLC, Apalache) were not installed on   *)
(* the night this file was written, so it has never been parsed or run.   *)
(* It was written by model/gen_tla.py from wiring/wiring.json and         *)
(* config/design_choices.json. Do not edit it by hand: change the wiring  *)
(* and write it again. Only a TLC run that finishes with no violated      *)
(* invariant may be called a proof, and then only for the bounds below.   *)
(*                                                                         *)
(* To check it: put "SPECIFICATION Spec" and "INVARIANTS P1 P2 P3 P4" in a *)
(* Custody.cfg beside this file and run TLC. A violated invariant gives   *)
(* the failing sequence of steps.                                          *)
(*                                                                         *)
(* How to read it, in ten minutes: Program is the plumbing as a list of    *)
(* points. Each point has a normal path and, where the wiring has one, a  *)
(* detour for a rare event. Next runs the steps of one path one at a      *)
(* time, then moves to the next point. P1 to P4 are the four properties.  *)
(***************************************************************************)
EXTENDS Integers, Sequences, FiniteSets
"""

BODY = r"""
VARIABLES pc, rest, clock, copies, delivered, used, n, handed, jr, ws
vars == <<pc, rest, clock, copies, delivered, used, n, handed, jr, ws>>

\* A copy is [place, kind, arr]: where it sits, what it is, the tick it arrived.
\* A place holds at most one copy of a kind; the earliest arrival is kept.

Min(a, b) == IF a < b THEN a ELSE b
Have(p, k) == \E c \in copies : c.place = p /\ c.kind = k
Arr(p, k) == (CHOOSE c \in copies : c.place = p /\ c.kind = k).arr
Without(p, k) == {c \in copies : ~(c.place = p /\ c.kind = k)}
Put(p, k, a) ==
    Without(p, k) \cup {[place |-> p, kind |-> k,
                         arr |-> IF Have(p, k) THEN Min(a, Arr(p, k)) ELSE a]}

Init == /\ pc = 1 /\ rest = <<>> /\ clock = 0 /\ copies = {}
        /\ delivered = {} /\ used = {} /\ n = 0 /\ handed = {} /\ jr = {} /\ ws = {}

\* One primitive operation. An operation guarded by "need" runs only when
\* that move was delivered.
Skipped(op) == op.t \in {"send", "delete"} /\ op.need # "" /\ op.need \notin delivered

Exec(op) ==
  \/ /\ op.t = "intake"
     /\ copies' = Put(op.place, op.kind, clock)
     /\ UNCHANGED <<clock, delivered, n, handed, jr, ws>>
  \/ /\ op.t = "step"
     /\ IF \A k \in op.reads : Have(op.place, k)
        THEN /\ clock' = clock + 1
             /\ copies' = IF op.makes = "" THEN copies ELSE Put(op.place, op.makes, clock + 1)
        ELSE UNCHANGED <<clock, copies>>
     /\ UNCHANGED <<delivered, n, handed, jr, ws>>
  \/ /\ op.t = "send"
     /\ IF Have(op.from, op.kind)
        THEN /\ clock' = clock + 1
             /\ copies' = Put(op.to, op.kind, clock + 1)
             /\ n' = n + 1
             /\ handed' = handed \cup {[n |-> n + 1, gated |-> op.gated]}
             /\ jr' = IF op.gated THEN jr \cup {n + 1} ELSE jr
             /\ ws' = IF op.gated THEN ws \cup {n + 1} ELSE ws
             /\ delivered' = delivered \cup {op.move}
        ELSE UNCHANGED <<clock, copies, n, handed, jr, ws, delivered>>
  \/ /\ op.t = "delete"
     /\ IF Have(op.place, op.kind)
        THEN /\ clock' = clock + 1
             /\ copies' = Without(op.place, op.kind)
             /\ n' = n + 1
             /\ handed' = handed \cup {[n |-> n + 1, gated |-> TRUE]}
             /\ jr' = jr \cup {n + 1}
             /\ ws' = ws \cup {n + 1}
        ELSE UNCHANGED <<clock, copies, n, handed, jr, ws>>
     /\ UNCHANGED delivered
  \/ /\ op.t = "close"
     /\ clock' = clock + 1 + CloseAdvance
     /\ UNCHANGED <<copies, delivered, n, handed, jr, ws>>

RunOp == /\ rest # <<>>
         /\ IF Skipped(Head(rest)) THEN UNCHANGED <<clock, copies, delivered, n, handed, jr, ws>>
                                   ELSE Exec(Head(rest))
         /\ rest' = Tail(rest)
         /\ UNCHANGED <<pc, used>>

\* Enter the next point by one of its alternatives. A detour needs its rare
\* event to be unused and the bound MaxEvents to leave room.
Enter == /\ rest = <<>> /\ pc <= Len(Program)
         /\ \E a \in Program[pc] :
              /\ a.ev = "" \/ (a.ev \notin used /\ Cardinality(used) < MaxEvents)
              /\ rest' = a.ops
              /\ used' = IF a.ev = "" THEN used ELSE used \cup {a.ev}
         /\ pc' = pc + 1
         /\ UNCHANGED <<clock, copies, delivered, n, handed, jr, ws>>

Done == /\ rest = <<>> /\ pc > Len(Program) /\ UNCHANGED vars

Next == RunOp \/ Enter \/ Done
Spec == Init /\ [][Next]_vars

\* P1 (rule 1): every copy sits at a named place that may hold its kind.
P1 == \A c \in copies : <<c.place, c.kind>> \in Allowed
\* P2 (rule 2): no copy is present after its deadline (arrival plus hold).
P2 == \A c \in copies : \A h \in Holds :
        (h.place = c.place /\ h.kind = c.kind) => clock <= c.arr + h.hold
\* P3 (rule 3): every handover passed the gate.
P3 == \A h \in handed : h.gated
\* P4 (rule 3): every handover has a journal record that the witness holds.
P4 == \A h \in handed : h.n \in jr /\ h.n \in ws

=============================================================================
"""


def generate(wiring=None, choices=None) -> str:
    wiring = wiring if wiring is not None else load_wiring()
    choices = choices if choices is not None else load_choices()
    prog = build_program(wiring, choices)
    out = [HEADER]
    out.append("\\* Bounds, from config/design_choices.json: model and holds.")
    out.append("MaxEvents == %d" % prog["max_events"])
    out.append("CloseAdvance == %d   \\* the longest hold plus one tick" % prog["close_advance"])
    out.append("")
    out.append("\\* Allowed: the (place, kind) pairs the patient was told about.")
    out.append("Allowed == {" + ", ".join("<<%s, %s>>" % (s(p), s(k)) for p, k in prog["allowed"]) + "}")
    out.append("\\* Holds: the deadline in ticks for each (place, kind) with a hold.")
    out.append("Holds == {" + ", ".join("[place |-> %s, kind |-> %s, hold |-> %d]" % (s(p), s(k), h)
                                         for p, k, h in prog["holds"]) + "}")
    out.append("")
    out.append("\\* Program: one entry for each point of the plumbing. Each alternative is")
    out.append("\\* the normal path (ev = \"\") or a detour fired by the rare event ev.")
    out.append("Program == <<")
    lines = []
    for pt in prog["points"]:
        alts = []
        for a in pt["alts"]:
            alts.append('[ev |-> %s, ops |-> %s]' % (s(a["event"] or ""), seq(a["ops"])))
        lines.append("  \\* %s\n  {%s}" % (pt["label"], ",\n   ".join(alts)))
    out.append(",\n".join(lines))
    out.append(">>")
    out.append(BODY)
    return "\n".join(out)


def main(argv) -> int:
    target = Path(argv[1]) if len(argv) > 1 else ROOT / "model" / "Custody.tla"
    text = generate()
    with open(str(target), "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote", target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
