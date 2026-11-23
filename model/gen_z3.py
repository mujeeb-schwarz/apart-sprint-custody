"""Writes a script for the same bounded check, in Z3's Python form.

Z3 is not installed, so the script it writes has never been run. Only the
fact that it is valid Python is checked (tests/test_model.py). A formal tool's
result is the only thing that may be called a proof; this generator proves
nothing.

    python3 model/gen_z3.py [OUT_PATH]     (with no path, the script goes to the screen)
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custody.prove import build_program, load_choices, load_wiring  # noqa: E402

TEMPLATE = '''"""Bounded check of the custody wiring in Z3. NOT YET RUN: Z3 was not installed
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

PROGRAM = json.loads(r\'\'\'%(program)s\'\'\')
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
                breaks.append(("P1", "send %%s to %%s" %% (op["move"], op["to"]), And(guard, has)))
            if not op["gated"]:
                breaks.append(("P3", "move %%s skips the gate" %% op["move"], And(guard, has)))
                breaks.append(("P4", "move %%s has no journal record" %% op["move"], And(guard, has)))
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
                # A delete at a place that no move has filled creates a presence term (False) and no arrival
                # tick; the default arrival 0 is never used, because the presence term is False there.
                breaks.append(("P2", "%%s at %%s past its deadline" %% (k, place),
                               And(guard, st.pres[key], st.t > st.arr.get(key, IntVal(0)) + hold)))


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
'''


def generate(wiring=None, choices=None) -> str:
    wiring = wiring if wiring is not None else load_wiring()
    choices = choices if choices is not None else load_choices()
    prog = build_program(wiring, choices)
    return TEMPLATE % {"program": json.dumps(prog, indent=1, sort_keys=True)}


def main(argv) -> int:
    text = generate()
    if len(argv) > 1:
        with open(argv[1], "w", encoding="utf-8") as f:
            f.write(text)
        print("wrote", argv[1])
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
