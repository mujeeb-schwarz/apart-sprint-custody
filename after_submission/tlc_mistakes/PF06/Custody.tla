---------------------------- MODULE Custody ----------------------------
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

\* Bounds, from config/design_choices.json: model and holds.
MaxEvents == 1
CloseAdvance == 11   \* the longest hold plus one tick

\* Allowed: the (place, kind) pairs the patient was told about.
Allowed == {<<"transcriber", "transcript">>, <<"note_writer", "transcript">>, <<"note_writer", "note_draft">>, <<"note_writer_cache", "transcript">>, <<"note_writer_queue", "note_draft">>, <<"record", "note_draft">>, <<"record", "note">>, <<"clinician", "question">>, <<"clinician", "answer">>, <<"clinician", "plan">>, <<"advice_tool", "answer">>, <<"summary_writer", "plan">>, <<"summary_writer", "patient_note">>, <<"patient", "patient_note">>}
\* Holds: the deadline in ticks for each (place, kind) with a hold.
Holds == {[place |-> "transcriber", kind |-> "transcript", hold |-> 10], [place |-> "note_writer", kind |-> "transcript", hold |-> 10], [place |-> "note_writer", kind |-> "note_draft", hold |-> 10], [place |-> "note_writer_cache", kind |-> "transcript", hold |-> 4], [place |-> "note_writer_queue", kind |-> "note_draft", hold |-> 4], [place |-> "record", kind |-> "note_draft", hold |-> 10], [place |-> "advice_tool", kind |-> "answer", hold |-> 10], [place |-> "summary_writer", kind |-> "plan", hold |-> 10], [place |-> "summary_writer", kind |-> "patient_note", hold |-> 10]}

\* Program: one entry for each point of the plumbing. Each alternative is
\* the normal path (ev = "") or a detour fired by the rare event ev.
Program == <<
  \* intake words
  {[ev |-> "", ops |-> <<[t |-> "intake", place |-> "transcriber", kind |-> "transcript"]>>]},
  \* step transcriber
  {[ev |-> "", ops |-> <<[t |-> "step", id |-> "transcriber", place |-> "transcriber", reads |-> {"transcript"}, makes |-> ""]>>]},
  \* move w2
  {[ev |-> "", ops |-> <<[t |-> "send", move |-> "w2", kind |-> "transcript", from |-> "transcriber", to |-> "note_writer", gated |-> TRUE, need |-> ""]>>],
   [ev |-> "resume@w2", ops |-> <<[t |-> "send", move |-> "w2c", kind |-> "transcript", from |-> "transcriber", to |-> "note_writer_cache", gated |-> TRUE, need |-> ""], [t |-> "send", move |-> "w2", kind |-> "transcript", from |-> "transcriber", to |-> "note_writer", gated |-> TRUE, need |-> ""], [t |-> "delete", kind |-> "transcript", place |-> "note_writer_cache", need |-> ""]>>]},
  \* duty d3
  {[ev |-> "", ops |-> <<[t |-> "delete", kind |-> "transcript", place |-> "transcriber", need |-> "w2"]>>],
   [ev |-> "crash@d3", ops |-> <<[t |-> "delete", kind |-> "transcript", place |-> "transcriber", need |-> "w2"]>>]},
  \* step note_writer
  {[ev |-> "", ops |-> <<[t |-> "step", id |-> "note_writer", place |-> "note_writer", reads |-> {"transcript"}, makes |-> "note_draft"]>>]},
  \* move w3
  {[ev |-> "", ops |-> <<[t |-> "send", move |-> "w3", kind |-> "note_draft", from |-> "note_writer", to |-> "record", gated |-> TRUE, need |-> ""]>>],
   [ev |-> "timeout@w3", ops |-> <<[t |-> "send", move |-> "w3q", kind |-> "note_draft", from |-> "note_writer", to |-> "debug_bucket", gated |-> TRUE, need |-> ""], [t |-> "send", move |-> "w3", kind |-> "note_draft", from |-> "note_writer", to |-> "record", gated |-> TRUE, need |-> ""], [t |-> "delete", kind |-> "note_draft", place |-> "note_writer_queue", need |-> ""]>>]},
  \* duty d4
  {[ev |-> "", ops |-> <<[t |-> "delete", kind |-> "transcript", place |-> "note_writer", need |-> "w3"]>>],
   [ev |-> "overlap@d4", ops |-> <<[t |-> "delete", kind |-> "transcript", place |-> "note_writer", need |-> "w3"]>>]},
  \* duty d5
  {[ev |-> "", ops |-> <<[t |-> "delete", kind |-> "note_draft", place |-> "note_writer", need |-> "w3"]>>]},
  \* step record
  {[ev |-> "", ops |-> <<[t |-> "step", id |-> "record", place |-> "record", reads |-> {"note_draft"}, makes |-> "note"]>>]},
  \* duty d6
  {[ev |-> "", ops |-> <<[t |-> "delete", kind |-> "note_draft", place |-> "record", need |-> ""]>>]},
  \* intake advice
  {[ev |-> "", ops |-> <<[t |-> "intake", place |-> "clinician", kind |-> "question"], [t |-> "intake", place |-> "advice_tool", kind |-> "answer"]>>]},
  \* step answer
  {[ev |-> "", ops |-> <<[t |-> "step", id |-> "answer", place |-> "advice_tool", reads |-> {"answer"}, makes |-> ""]>>]},
  \* move a2
  {[ev |-> "", ops |-> <<[t |-> "send", move |-> "a2", kind |-> "answer", from |-> "advice_tool", to |-> "clinician", gated |-> TRUE, need |-> ""]>>]},
  \* duty d8
  {[ev |-> "", ops |-> <<[t |-> "delete", kind |-> "answer", place |-> "advice_tool", need |-> "a2"]>>]},
  \* step plan
  {[ev |-> "", ops |-> <<[t |-> "step", id |-> "plan", place |-> "clinician", reads |-> {"question", "answer"}, makes |-> "plan"]>>]},
  \* move a3
  {[ev |-> "", ops |-> <<[t |-> "send", move |-> "a3", kind |-> "plan", from |-> "clinician", to |-> "summary_writer", gated |-> TRUE, need |-> ""]>>]},
  \* step patient_note
  {[ev |-> "", ops |-> <<[t |-> "step", id |-> "patient_note", place |-> "summary_writer", reads |-> {"plan"}, makes |-> "patient_note"]>>]},
  \* move a4
  {[ev |-> "", ops |-> <<[t |-> "send", move |-> "a4", kind |-> "patient_note", from |-> "summary_writer", to |-> "patient", gated |-> TRUE, need |-> ""]>>]},
  \* duty d9
  {[ev |-> "", ops |-> <<[t |-> "delete", kind |-> "plan", place |-> "summary_writer", need |-> "a4"]>>]},
  \* duty d10
  {[ev |-> "", ops |-> <<[t |-> "delete", kind |-> "patient_note", place |-> "summary_writer", need |-> "a4"]>>]},
  \* close
  {[ev |-> "", ops |-> <<[t |-> "close"]>>]}
>>

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
