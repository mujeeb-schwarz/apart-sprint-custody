"""Bounded check of the custody wiring in Z3. NOT YET RUN: Z3 was not installed
on the night this file was written (model/gen_z3.py wrote it). Do not edit by hand.

Needs: pip install z3-solver. Run: python3 custody_z3.py
sat   = some order of events, within the bounds, breaks a property (it is printed).
unsat = none does, inside the bounds. Only that answer, from Z3, may be called a proof.

The idea: the rare events are free Boolean variables, at most MAX_EVENTS true.
The clock, whether each (place, kind) holds a copy, and its arrival tick are
Z3 terms built step by step along the plumbing. Each break is a Boolean term;
the solver is asked for an assignment of the events that makes one true.
"""
import json
from z3 import Bool, BoolVal, If, Int, IntVal, Not, And, Or, Solver, Sum, is_true, sat

PROGRAM = json.loads(r'''{
 "allowed": [
  [
   "transcriber",
   "transcript"
  ],
  [
   "note_writer",
   "transcript"
  ],
  [
   "note_writer",
   "note_draft"
  ],
  [
   "note_writer_cache",
   "transcript"
  ],
  [
   "note_writer_queue",
   "note_draft"
  ],
  [
   "record",
   "note_draft"
  ],
  [
   "record",
   "note"
  ],
  [
   "clinician",
   "question"
  ],
  [
   "clinician",
   "answer"
  ],
  [
   "clinician",
   "plan"
  ],
  [
   "advice_tool",
   "answer"
  ],
  [
   "summary_writer",
   "plan"
  ],
  [
   "summary_writer",
   "patient_note"
  ],
  [
   "patient",
   "patient_note"
  ]
 ],
 "close_advance": 11,
 "holds": [
  [
   "transcriber",
   "transcript",
   10
  ],
  [
   "note_writer",
   "transcript",
   10
  ],
  [
   "note_writer",
   "note_draft",
   10
  ],
  [
   "note_writer_cache",
   "transcript",
   4
  ],
  [
   "note_writer_queue",
   "note_draft",
   4
  ],
  [
   "record",
   "note_draft",
   10
  ],
  [
   "advice_tool",
   "answer",
   10
  ],
  [
   "summary_writer",
   "plan",
   10
  ],
  [
   "summary_writer",
   "patient_note",
   10
  ]
 ],
 "ignored_detours": [],
 "max_events": 1,
 "points": [
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "kind": "transcript",
       "place": "transcriber",
       "t": "intake"
      }
     ]
    }
   ],
   "label": "intake words"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "id": "transcriber",
       "makes": "",
       "place": "transcriber",
       "reads": [
        "transcript"
       ],
       "t": "step"
      }
     ]
    }
   ],
   "label": "step transcriber"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "from": "transcriber",
       "gated": true,
       "kind": "transcript",
       "move": "w2",
       "need": "",
       "t": "send",
       "to": "note_writer"
      }
     ]
    },
    {
     "detour": "r2",
     "event": "resume@w2",
     "ops": [
      {
       "from": "transcriber",
       "gated": true,
       "kind": "transcript",
       "move": "w2c",
       "need": "",
       "t": "send",
       "to": "note_writer_cache"
      },
      {
       "from": "transcriber",
       "gated": true,
       "kind": "transcript",
       "move": "w2",
       "need": "",
       "t": "send",
       "to": "note_writer"
      },
      {
       "kind": "transcript",
       "need": "",
       "place": "note_writer_cache",
       "t": "delete",
       "via": "r2"
      }
     ]
    }
   ],
   "label": "move w2"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "kind": "transcript",
       "need": "w2",
       "place": "transcriber",
       "t": "delete",
       "via": "d3"
      }
     ]
    },
    {
     "detour": "r3",
     "event": "crash@d3",
     "ops": [
      {
       "kind": "transcript",
       "need": "w2",
       "place": "transcriber",
       "t": "delete",
       "via": "r3"
      }
     ]
    }
   ],
   "label": "duty d3"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "id": "note_writer",
       "makes": "note_draft",
       "place": "note_writer",
       "reads": [
        "transcript"
       ],
       "t": "step"
      }
     ]
    }
   ],
   "label": "step note_writer"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "from": "note_writer",
       "gated": true,
       "kind": "note_draft",
       "move": "w3",
       "need": "",
       "t": "send",
       "to": "record"
      }
     ]
    },
    {
     "detour": "r1",
     "event": "timeout@w3",
     "ops": [
      {
       "from": "note_writer",
       "gated": true,
       "kind": "note_draft",
       "move": "w3q",
       "need": "",
       "t": "send",
       "to": "note_writer_queue"
      },
      {
       "from": "note_writer",
       "gated": true,
       "kind": "note_draft",
       "move": "w3",
       "need": "",
       "t": "send",
       "to": "record"
      },
      {
       "kind": "note_draft",
       "need": "",
       "place": "note_writer_queue",
       "t": "delete",
       "via": "r1"
      }
     ]
    }
   ],
   "label": "move w3"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "kind": "transcript",
       "need": "w3",
       "place": "note_writer",
       "t": "delete",
       "via": "d4"
      }
     ]
    },
    {
     "detour": "r4",
     "event": "overlap@d4",
     "ops": [
      {
       "kind": "transcript",
       "need": "w3",
       "place": "note_writer",
       "t": "delete",
       "via": "r4"
      }
     ]
    }
   ],
   "label": "duty d4"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "kind": "note_draft",
       "need": "w3",
       "place": "note_writer",
       "t": "delete",
       "via": "d5"
      }
     ]
    }
   ],
   "label": "duty d5"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "id": "record",
       "makes": "note",
       "place": "record",
       "reads": [
        "note_draft"
       ],
       "t": "step"
      }
     ]
    }
   ],
   "label": "step record"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "kind": "note_draft",
       "need": "",
       "place": "record",
       "t": "delete",
       "via": "d6"
      }
     ]
    }
   ],
   "label": "duty d6"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "kind": "question",
       "place": "clinician",
       "t": "intake"
      },
      {
       "kind": "answer",
       "place": "advice_tool",
       "t": "intake"
      }
     ]
    }
   ],
   "label": "intake advice"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "id": "answer",
       "makes": "",
       "place": "advice_tool",
       "reads": [
        "answer"
       ],
       "t": "step"
      }
     ]
    }
   ],
   "label": "step answer"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "from": "advice_tool",
       "gated": true,
       "kind": "answer",
       "move": "a2",
       "need": "",
       "t": "send",
       "to": "clinician"
      }
     ]
    }
   ],
   "label": "move a2"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "kind": "answer",
       "need": "a2",
       "place": "advice_tool",
       "t": "delete",
       "via": "d8"
      }
     ]
    }
   ],
   "label": "duty d8"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "id": "plan",
       "makes": "plan",
       "place": "clinician",
       "reads": [
        "question",
        "answer"
       ],
       "t": "step"
      }
     ]
    }
   ],
   "label": "step plan"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "from": "clinician",
       "gated": true,
       "kind": "plan",
       "move": "a3",
       "need": "",
       "t": "send",
       "to": "summary_writer"
      }
     ]
    }
   ],
   "label": "move a3"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "id": "patient_note",
       "makes": "patient_note",
       "place": "summary_writer",
       "reads": [
        "plan"
       ],
       "t": "step"
      }
     ]
    }
   ],
   "label": "step patient_note"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "from": "summary_writer",
       "gated": true,
       "kind": "patient_note",
       "move": "a4",
       "need": "",
       "t": "send",
       "to": "patient"
      }
     ]
    }
   ],
   "label": "move a4"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "kind": "plan",
       "need": "a4",
       "place": "summary_writer",
       "t": "delete",
       "via": "d9"
      }
     ]
    }
   ],
   "label": "duty d9"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "kind": "patient_note",
       "need": "a4",
       "place": "summary_writer",
       "t": "delete",
       "via": "d10"
      }
     ]
    }
   ],
   "label": "duty d10"
  },
  {
   "alts": [
    {
     "event": null,
     "ops": [
      {
       "t": "close"
      }
     ]
    }
   ],
   "label": "close"
  }
 ]
}''')
ALLOWED = set(tuple(x) for x in PROGRAM["allowed"])
HOLDS = [tuple(x) for x in PROGRAM["holds"]]
MAX_EVENTS = PROGRAM["max_events"]


class St:
    def __init__(self):
        self.t = IntVal(0)
        self.pres = {}      # (place, kind) -> Bool term
        self.arr = {}       # (place, kind) -> Int term
        self.deliv = {}     # move id -> Bool term

    def copy(self):
        o = St()
        o.t = self.t
        o.pres = dict(self.pres)
        o.arr = dict(self.arr)
        o.deliv = dict(self.deliv)
        return o

    def has(self, key):
        return self.pres.get(key, BoolVal(False))

    def put(self, key, when, arrival):
        old_p, old_a = self.has(key), self.arr.get(key, IntVal(0))
        new_a = If(old_p, If(old_a < arrival, old_a, arrival), arrival)
        self.pres[key] = Or(old_p, when)
        self.arr[key] = If(when, new_a, old_a)


breaks = []   # (property, label, Bool term)


def run(ops, st, guard):
    for op in ops:
        kind = op["t"]
        if kind == "intake":
            key = (op["place"], op["kind"])
            st.put(key, BoolVal(True), st.t)
            if key not in ALLOWED:
                breaks.append(("P1", "start " + str(key), guard))
        elif kind == "step":
            ran = And(*[st.has((op["place"], k)) for k in op["reads"]]) if op["reads"] else BoolVal(True)
            st.t = If(ran, st.t + 1, st.t)
            if op["makes"]:
                key = (op["place"], op["makes"])
                st.put(key, ran, st.t)
                if key not in ALLOWED:
                    breaks.append(("P1", "make " + str(key), And(guard, ran)))
        elif kind == "send":
            active = st.deliv.get(op["need"], BoolVal(False)) if op["need"] else BoolVal(True)
            has = And(active, st.has((op["from"], op["kind"])))
            st.t = If(has, st.t + 1, st.t)
            key = (op["to"], op["kind"])
            st.put(key, has, st.t)
            st.deliv[op["move"]] = Or(st.deliv.get(op["move"], BoolVal(False)), has)
            if key not in ALLOWED:
                breaks.append(("P1", "send %s to %s" % (op["move"], op["to"]), And(guard, has)))
            if not op["gated"]:
                breaks.append(("P3", "move %s skips the gate" % op["move"], And(guard, has)))
                breaks.append(("P4", "move %s has no journal record" % op["move"], And(guard, has)))
        elif kind == "delete":
            key = (op["place"], op["kind"])
            active = st.deliv.get(op["need"], BoolVal(False)) if op["need"] else BoolVal(True)
            has = And(active, st.has(key))
            st.t = If(has, st.t + 1, st.t)
            st.pres[key] = And(st.has(key), Not(has))
        elif kind == "close":
            st.t = st.t + 1 + PROGRAM["close_advance"]
        for place, k, hold in HOLDS:
            key = (place, k)
            if key in st.pres:
                breaks.append(("P2", "%s at %s past its deadline" % (k, place),
                               And(guard, st.pres[key], st.t > st.arr[key] + hold)))


def merge(cond, a, b):
    o = St()
    o.t = If(cond, a.t, b.t)
    for key in set(a.pres) | set(b.pres):
        o.pres[key] = If(cond, a.has(key), b.has(key))
        o.arr[key] = If(cond, a.arr.get(key, IntVal(0)), b.arr.get(key, IntVal(0)))
    for key in set(a.deliv) | set(b.deliv):
        o.deliv[key] = If(cond, a.deliv.get(key, BoolVal(False)), b.deliv.get(key, BoolVal(False)))
    return o


events = {}
solver = Solver()
state = St()
for n, point in enumerate(PROGRAM["points"]):
    normal, detours = point["alts"][0], point["alts"][1:]
    chosen = []
    for alt in detours:
        ev = events.setdefault(alt["event"], Bool("ev_" + alt["event"].replace("@", "_at_")))
        chosen.append((ev, alt))
    if chosen:
        solver.add(Sum([If(ev, 1, 0) for ev, _ in chosen]) <= 1)
    none_fired = And(*[Not(ev) for ev, _ in chosen]) if chosen else BoolVal(True)
    after = state.copy()
    run(normal["ops"], after, none_fired)
    for ev, alt in chosen:
        branch = state.copy()
        run(alt["ops"], branch, ev)
        after = merge(ev, branch, after)
    state = after
if events:
    solver.add(Sum([If(ev, 1, 0) for ev in events.values()]) <= MAX_EVENTS)
solver.add(Or(*[b for _, _, b in breaks]))

if solver.check() == sat:
    m = solver.model()
    fired = [name for name, ev in sorted(events.items()) if is_true(m.eval(ev, model_completion=True))]
    broken = sorted({(p, lab) for p, lab, b in breaks if is_true(m.eval(b, model_completion=True))})
    print("sat: a property can break. Events fired:", fired or "none")
    for p, lab in broken:
        print("  ", p, lab)
else:
    print("unsat: no property breaks inside the bounds (a result from Z3, not from this file's author)")
