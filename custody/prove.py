"""Our own cross-check of the wiring: it tries the orders of events its bounds allow.

This is not a formal proof and nothing here may be called one. A formal tool
(TLC for model/Custody.tla, or Z3 for the script that model/gen_z3.py writes)
has not run. Until one has, the result of `prove` never has the status
"passed", so the receipt's level "proven" stays unavailable.

What it does. It reads the wiring (W) and the bounds (D: holds, D: model),
turns the plumbing into a list of program points, and explores the states
reachable when, at each point, either the normal path or one allowed detour
runs (a rare event: a timeout and retry, a resume, a crash, an overlap), with
at most `max_events_per_visit` events in all. It checks four properties:

    P1 (rule 1)  no copy sits at a place that is not named or may not hold its kind
    P2 (rule 2)  no copy is present after its deadline
    P3 (rule 3)  every move passes the gate
    P4 (rule 3)  every delivered handover has a journal record the witness holds

and returns the first failing sequence of events, step by step.

Limits, stated plainly. An event happens only where a detour in the wiring says
so (one position for each event, at most one event per visit); an event at any
other point is never tried. A path stops at its first break, so the "violated"
list and the "states" count of a faulty wiring understate what is wrong; the
counterexample itself is correct. A move no lane step runs and a detour at an
unknown position raise ContractError instead of being left out. A detour on an
event outside the model is legal but never explored; it is listed under
"ignored_detours" in the report and in the not_run result of `prove`. The cross-check is not connected to the bench.

Choices made, each stated in docs/notes/MODEL.md: the wiring is judged by what
it asks for, so a send asked to a place that is not named counts as a P1 break
even though the gate would block it at run time; a place holds at most one
copy of a kind (the earliest arrival counts); one visit at a time, with the
overlap of two visits entering as the event "overlap".

Standard library only. Python 3.9.
"""
import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custody.core import ContractError, hold_ticks, is_named, may_hold  # noqa: E402

J = Dict[str, Any]

PROPERTIES = [
    {"id": "P1", "rule": 1},
    {"id": "P2", "rule": 2},
    {"id": "P3", "rule": 3},
    {"id": "P4", "rule": 3},
]

# The only statuses this program returns. "passed" is left out on purpose:
# only a formal tool's run may produce it.
NOT_RUN = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}


def load_choices() -> J:
    with open(str(ROOT / "config" / "design_choices.json"), encoding="utf-8") as f:
        return json.load(f)


def load_wiring(path: Optional[str] = None) -> J:
    with open(path or str(ROOT / "wiring" / "wiring.json"), encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------- the program

def _find(items: List[J], ident: str, what: str) -> J:
    for it in items:
        if it.get("id") == ident:
            return it
    raise ContractError("the wiring refers to an unknown %s: %r" % (what, ident))


def build_program(wiring: J, choices: J) -> J:
    """The plumbing as a list of program points, each with its alternatives.

    A point is entered once. Its first alternative is the normal path; each
    further one is a detour fired by a rare event. Shared by prove.py, gen_tla.py
    and gen_z3.py, so the three describe the same thing.
    """
    plumbing = wiring["plumbing"]
    moves, duties = plumbing["moves"], plumbing["duties"]
    model = choices["model"]
    allowed_events = set(model["events"])
    all_detours = list(plumbing.get("detours", []))
    detours = [d for d in all_detours if d.get("on") in allowed_events]
    # A detour on an event outside the model is legal (the bounds may leave an event out), but it is
    # never explored, so it is listed and reported, never dropped without a word.
    ignored = [{"detour": d.get("id"), "on": d.get("on")} for d in all_detours if d.get("on") not in allowed_events]

    def send_op(move: J, need: str) -> J:
        return {"t": "send", "move": move["id"], "kind": move["kind"], "from": move["from"],
                "to": move["to"], "gated": bool(move.get("via_gate")), "need": need}

    def detour_ops(det: J, need: str) -> List[J]:
        ops: List[J] = []
        for item in det.get("do", []):
            if "send" in item:
                ops.append(send_op(_find(moves, item["send"], "move"), need))
            elif "delete" in item:
                kind, place = item["delete"]
                ops.append({"t": "delete", "kind": kind, "place": place, "need": need, "via": det["id"]})
            else:
                raise ContractError("a detour item is neither a send nor a delete: %r" % (item,))
        return ops

    def alts_for(at: str, normal: List[J], need: str) -> List[J]:
        alts = [{"event": None, "ops": normal}]
        for det in detours:
            if det.get("at") == at:
                alts.append({"event": "%s@%s" % (det["on"], at), "detour": det["id"],
                             "ops": detour_ops(det, need)})
        return alts

    points: List[J] = []
    placed_moves: set = set()
    placed_ids: set = set()
    steps = {s["id"]: s for s in plumbing["steps"]}
    for lane in plumbing["lanes"]:
        # Version 3: each lane takes in its own raw inputs when it starts (a case runs one lane, so an answer that
        # enters at tick 0 never waits for the other lane's steps)
        reads = {k for sid in lane["steps"] for k in steps[sid]["reads"]}
        intake_ops = [{"t": "intake", "kind": e["kind"], "place": e["place"]}
                      for e in plumbing["intake"] if e["kind"] in reads]
        points.append({"label": "intake " + lane["id"], "alts": [{"event": None, "ops": intake_ops}]})
        for sid in lane["steps"]:
            st = steps[sid]
            points.append({"label": "step " + sid, "alts": [{"event": None, "ops": [
                {"t": "step", "id": sid, "place": st["place"], "reads": list(st["reads"]),
                 "makes": st["makes"] or ""}]}]})
            for mv in moves:
                if mv.get("step") != sid or mv.get("detour_only"):
                    continue
                placed_moves.add(mv["id"])
                placed_ids.add(mv["id"])
                points.append({"label": "move " + mv["id"], "alts": alts_for(mv["id"], [send_op(mv, "")], "")})
                for du in duties:
                    if du.get("after") == mv["id"]:
                        normal = [{"t": "delete", "kind": du["kind"], "place": du["place"],
                                   "need": mv["id"], "via": du["id"]}]
                        placed_ids.add(du["id"])
                        points.append({"label": "duty " + du["id"], "alts": alts_for(du["id"], normal, mv["id"])})
            for du in duties:  # a duty that names a step runs once the step has run (version 3); it needs no move
                if du.get("after_step") == sid:
                    normal = [{"t": "delete", "kind": du["kind"], "place": du["place"], "need": "", "via": du["id"]}]
                    placed_ids.add(du["id"])
                    points.append({"label": "duty " + du["id"], "alts": alts_for(du["id"], normal, "")})
    for mv in moves:
        if mv["id"] not in placed_moves and not mv.get("detour_only"):
            raise ContractError("move %s is never run by any lane step" % mv["id"])
    for d in detours:
        if d.get("at") not in placed_ids:
            raise ContractError("detour %s sits at %r, which is no placed move or duty" % (d.get("id"), d.get("at")))
    holds = []
    for place in wiring["promise"]["places"]:
        for kind in place.get("may_hold", {}):
            h = hold_ticks(wiring, choices, place["id"], kind)
            if h is not None:
                holds.append([place["id"], kind, h])
    allowed = [[p["id"], k] for p in wiring["promise"]["places"] if p.get("named") is True
               for k in p.get("may_hold", {})]
    points.append({"label": "close", "alts": [{"event": None, "ops": [{"t": "close"}]}]})
    longest = max([h[2] for h in holds] or [0])
    return {"points": points, "allowed": allowed, "ignored_detours": ignored, "holds": holds,
            "max_events": int(model["max_events_per_visit"]), "close_advance": longest + 1}


# ---------------------------------------------------------------- the exploring

class _State:
    """One situation: the clock, the copies, what was delivered, the events used."""
    __slots__ = ("t", "copies", "delivered", "used", "n")

    def __init__(self, t=0, copies=None, delivered=None, used=None, n=0):
        self.t = t
        self.copies = dict(copies or {})      # (place, kind) -> earliest arrival
        self.delivered = frozenset(delivered or ())
        self.used = frozenset(used or ())
        self.n = n                            # handovers asked so far

    def key(self, pidx: int, oidx: int) -> Tuple:
        return (pidx, oidx, self.t, tuple(sorted(self.copies.items())),
                tuple(sorted(self.delivered)), tuple(sorted(self.used)))

    def clone(self) -> "_State":
        return _State(self.t, self.copies, self.delivered, self.used, self.n)


def _exec(op: J, st: _State, prog: J, wiring: J) -> Tuple[List[str], List[Tuple[str, int, str]]]:
    """Run one operation on st (changed in place). Returns trace lines and breaks."""
    lines: List[str] = []
    breaks: List[Tuple[str, int, str]] = []
    allowed = {(p, k) for p, k in prog["allowed"]}
    kind_of = op["t"]

    def put(place: str, kind: str, arrival: int) -> None:
        old = st.copies.get((place, kind))
        st.copies[(place, kind)] = arrival if old is None else min(old, arrival)

    if kind_of == "intake":
        put(op["place"], op["kind"], st.t)
        lines.append("t%d intake: %s at %s" % (st.t, op["kind"], op["place"]))
        if (op["place"], op["kind"]) not in allowed:
            breaks.append(("P1", 1, "%s starts at %s, which is not named or may not hold it" % (op["kind"], op["place"])))
    elif kind_of == "step":
        if all((op["place"], k) in st.copies for k in op["reads"]):
            st.t += 1
            lines.append("t%d step %s%s" % (st.t, op["id"], " makes " + op["makes"] if op["makes"] else ""))
            if op["makes"]:
                put(op["place"], op["makes"], st.t)
                if (op["place"], op["makes"]) not in allowed:
                    breaks.append(("P1", 1, "%s is made at %s, which is not named or may not hold it" % (op["makes"], op["place"])))
        else:
            lines.append("t%d step %s skipped (an input is missing)" % (st.t, op["id"]))
    elif kind_of == "send":
        if op["need"] and op["need"] not in st.delivered:
            lines.append("t%d send %s skipped (move %s was not delivered)" % (st.t, op["move"], op["need"]))
        elif (op["from"], op["kind"]) in st.copies:
            st.t += 1
            st.n += 1
            how = "record %d written first" % st.n if op["gated"] else "NO RECORD: this move skips the gate"
            lines.append("t%d send %s %s %s > %s (%s)" % (st.t, op["move"], op["kind"], op["from"], op["to"], how))
            put(op["to"], op["kind"], st.t)
            st.delivered = st.delivered | {op["move"]}
            if (op["to"], op["kind"]) not in allowed:
                breaks.append(("P1", 1, "a copy of %s is asked to %s, which is not named or may not hold it" % (op["kind"], op["to"])))
            if not op["gated"]:
                breaks.append(("P3", 3, "move %s reaches %s without passing the gate" % (op["move"], op["to"])))
                breaks.append(("P4", 3, "handover %d was delivered and has no journal record" % st.n))
        else:
            lines.append("t%d send %s does nothing (no %s at %s)" % (st.t, op["move"], op["kind"], op["from"]))
    elif kind_of == "delete":
        if op["need"] and op["need"] not in st.delivered:
            lines.append("t%d delete %s skipped (move %s was not delivered)" % (st.t, op["via"], op["need"]))
        elif (op["place"], op["kind"]) in st.copies:
            st.t += 1
            st.n += 1
            del st.copies[(op["place"], op["kind"])]
            lines.append("t%d delete %s: %s at %s (record %d written first)" % (st.t, op["via"], op["kind"], op["place"], st.n))
        else:
            lines.append("t%d delete %s finds no %s at %s" % (st.t, op["via"], op["kind"], op["place"]))
    elif kind_of == "close":
        st.t += 1
        st.t += prog["close_advance"]
        lines.append("t%d close: the clock passes every deadline" % st.t)
    else:
        raise ContractError("unknown operation %r" % (kind_of,))
    for place, kind, hold in prog["holds"]:
        arrival = st.copies.get((place, kind))
        if arrival is not None and st.t > arrival + hold:
            breaks.append(("P2", 2, "%s is still at %s at t%d; it arrived at t%d and may stay %d ticks"
                           % (kind, place, st.t, arrival, hold)))
    return lines, breaks


def cross_check(wiring: J, choices: Optional[J] = None) -> J:
    """Explore the orders of events the bounds allow (see the module docstring for the limits). Returns a full report.

    {"checked_by": "custody.prove (our own cross-check, not a formal proof)",
     "ok": bool, "states": distinct situations tried, "scenarios": event sets met,
     "violated": the property ids broken somewhere, "counterexample": None or
     {"rule", "property", "trace", "why"}}
    The counterexample is the first one found, in a fixed order, so a second run agrees.
    """
    choices = choices if choices is not None else load_choices()
    prog = build_program(wiring, choices)
    points = prog["points"]
    seen = set()
    violated: List[str] = []
    first: Optional[J] = None
    scenarios = set()

    # Depth-first over the points; at each point every alternative is tried.
    stack: List[Tuple[int, _State, List[str]]] = [(0, _State(), [])]
    while stack:
        pidx, st, trace = stack.pop()
        if pidx >= len(points):
            scenarios.add(tuple(sorted(st.used)))
            continue
        k = st.key(pidx, -1)
        if k in seen:
            continue
        seen.add(k)
        alts = points[pidx]["alts"]
        nxt = []
        for alt in alts:
            if alt["event"] is not None:
                if alt["event"] in st.used or len(st.used) >= prog["max_events"]:
                    continue
            cur = st.clone()
            tr = list(trace)
            if alt["event"] is not None:
                cur.used = cur.used | {alt["event"]}
                tr.append("-- rare event %s: detour %s runs in place of %s" % (alt["event"], alt["detour"], points[pidx]["label"]))
            failed = False
            for oidx, op in enumerate(alt["ops"]):
                lines, breaks = _exec(op, cur, prog, wiring)
                tr.extend(lines)
                seen.add(cur.key(pidx, oidx))
                for pid, rule, why in sorted(breaks, key=lambda b: b[0]):
                    if pid not in violated:
                        violated.append(pid)
                if breaks and first is None:
                    pid, rule, why = sorted(breaks, key=lambda b: b[0])[0]
                    first = {"rule": rule, "property": pid, "why": why,
                             "trace": list(tr) + ["BREAK %s: %s" % (pid, why)],
                             "also_broken": sorted(b[0] for b in breaks if b[0] != pid)}
                if breaks:
                    failed = True
                    break
            if not failed:
                nxt.append((pidx + 1, cur, tr))
        # push in reverse so the normal path is explored first
        for item in reversed(nxt):
            stack.append(item)
    return {
        "checked_by": "custody.prove (our own cross-check, not a formal proof)",
        "ok": first is None,
        "states": len(seen),
        "scenarios": len(scenarios),
        "ignored_detours": prog["ignored_detours"],
        "bounds": {"max_events_per_visit": prog["max_events"],
                   "events": sorted({a["event"] for pt in points for a in pt["alts"] if a["event"]})},
        "violated": sorted(violated),
        "counterexample": first,
    }


def prove(wiring: J, choices: Optional[J] = None) -> J:
    """The result in the form of D: model.result_format.

    Status is "counterexample" with the failing sequence when a property breaks.
    With no counterexample the status is "not_run": our cross-check found
    nothing, and a formal tool has not run, so no rule is listed as proven.
    """
    report = cross_check(wiring, choices)
    ce = report["counterexample"]
    if ce is None:
        out = dict(NOT_RUN)
        if report["ignored_detours"]:
            out["ignored_detours"] = report["ignored_detours"]   # events left out of the bounds: never explored
        return out
    return {"status": "counterexample", "proven_rules": [],
            "counterexample": {"rule": ce["rule"], "property": ce["property"], "trace": ce["trace"]},
            "states": report["states"]}


def apply_patch(wiring: J, patch: List[J]) -> J:
    """A copy of the wiring with a fault's patch applied (used by tests and the CLI).

    A path segment that follows a list picks the element with that id, or the
    element at that position when the segment is a number, counting from 0.
    """
    out = copy.deepcopy(wiring)
    for step in patch:
        segs = [s for s in step["path"].split("/") if s]
        if not segs or segs[0] != "plumbing":
            raise ContractError("a patch must start with /plumbing/: %r" % (step["path"],))
        node: Any = out
        for seg in segs[:-1]:
            node = _child(node, seg)
        last = segs[-1]
        if isinstance(node, list):
            idx = _index(node, last)
            if step["op"] == "remove":
                del node[idx]
            elif step["op"] == "replace":
                node[idx] = step["value"]
            else:
                node.insert(idx, step["value"])
        else:
            if step["op"] == "remove":
                del node[last]
            else:
                node[last] = step["value"]
    return out


def _index(lst: List[Any], seg: str) -> int:
    if seg.isdigit():
        return int(seg)
    for i, el in enumerate(lst):
        if isinstance(el, dict) and el.get("id") == seg:
            return i
    raise ContractError("no element %r in the list" % (seg,))


def _child(node: Any, seg: str) -> Any:
    if isinstance(node, list):
        return node[_index(node, seg)]
    return node[seg]


def main(argv: List[str]) -> int:
    path = argv[1] if len(argv) > 1 else None
    report = cross_check(load_wiring(path))
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
