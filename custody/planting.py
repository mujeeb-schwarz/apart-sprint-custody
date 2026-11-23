"""Version 3: the complete list of violations the test bench can plant for rules 1 to 3, and the draw by lot.

Only the bench side reads this module (it knows the faults). `catalogue` is computed from the wiring it is given:
the order of events of a clean visit is worked out from the lanes, moves and duties, never from a list of names.
`draw` makes the plan: which violation goes on which case. Same input, same output. Every number and wording is in
config/design_choices.json under "planting".
"""
import random
from typing import Any, Dict, List, Optional

from custody.core import ContractError, LANE_OF, fingerprint, hold_ticks

J = Dict[str, Any]


# ------------------------------------------------------------------ the flow of a clean visit

def flow(wiring: J, experiment: int = 1) -> J:
    """The clean visit of one experiment's lane, worked out from the wiring.

    Returns {"intake": [kind], "steps": [{step, place, held, own_end, journal_end}], "events": [...]}.
    An event is {action: send | delete, step, kind, from, to, move | duty, own_pos, journal_pos}: its position in the
    system's own log (which starts with one intake line per raw input) and in the checker's journal (which has no
    intake line). `held` is the kinds that sit at the step's place when the step runs, in the order of wiring kinds.
    A duty names `after` (a move) or `after_step` (a step); the second runs once the step and its moves are done."""
    p = wiring["plumbing"]
    lane_id = LANE_OF.get(experiment)
    lanes = [ln for ln in p["lanes"] if lane_id is None or ln["id"] == lane_id]
    step_ids = [s for ln in lanes for s in ln["steps"]]
    specs = {s["id"]: s for s in p["steps"]}
    reads = {k for s in step_ids for k in specs[s]["reads"]}
    kind_order = list(wiring.get("kinds", []))
    held = set()
    intake = []
    for entry in p["intake"]:
        if entry["kind"] in reads:
            held.add((entry["place"], entry["kind"]))
            intake.append(entry["kind"])
    events: List[J] = []
    steps: List[J] = []

    def rank(k: str) -> int:
        return kind_order.index(k) if k in kind_order else len(kind_order)

    def emit(action: str, step: str, kind: str, frm: str, to: Optional[str], **ident: Any) -> None:
        events.append(dict(action=action, step=step, kind=kind, **{"from": frm, "to": to}, **ident,
                           journal_pos=len(events), own_pos=len(intake) + len(events)))

    def run_duty(duty: J, step: str) -> None:
        if (duty["place"], duty["kind"]) in held:
            held.discard((duty["place"], duty["kind"]))
            emit("delete", "janitor", duty["kind"], duty["place"], None, duty=duty["id"])

    for sid in step_ids:
        spec = specs[sid]
        place = spec["place"]
        if any((place, k) not in held for k in spec["reads"]):
            continue
        when = {k for (pl, k) in held if pl == place}
        if spec.get("makes"):
            held.add((place, spec["makes"]))
            when.add(spec["makes"])
        steps.append({"step": sid, "place": place, "held": sorted(when, key=rank)})
        for move in p["moves"]:
            if move["step"] != sid or move.get("detour_only"):
                continue
            if (move["from"], move["kind"]) not in held:
                continue
            held.add((move["to"], move["kind"]))
            emit("send", sid, move["kind"], move["from"], move["to"], move=move["id"])
            for duty in p["duties"]:
                if duty.get("after") == move["id"]:
                    run_duty(duty, sid)
        for duty in p["duties"]:
            if duty.get("after_step") == sid:
                run_duty(duty, sid)
        steps[-1]["own_end"] = len(intake) + len(events)
        steps[-1]["journal_end"] = len(events)
    return {"intake": intake, "steps": steps, "events": events}


# ------------------------------------------------------------------ the complete list

def _fault(vid: str, rule: int, says: str, ops: List[J]) -> J:
    return {"fault_id": vid, "kind": "step", "rule": rule, "says": says, "ops": ops,
            "patch": [], "events": [], "needs": {}}


def catalogue(wiring: J, choices: J, experiment: int = 1) -> List[J]:
    """Every violation of rules 1 to 3 that the test bench can plant on the wiring's words lane, in a fixed order.

    Each is {variant_id, rule, kind, says, fault, apart}. Rule 3 variants also carry `fault_record`, the operation
    against the checker's record (used under Checked; `fault` is the one against the system's own log, used under
    Promised and Monitored). A variant whose operations the engine does not know yet has "needs_b1b": true.
    Experiment 2 has no list: its violations (rules 4 to 6) are drawn, not listed; the list is empty."""
    if experiment != 1:
        return []
    cfg = choices["planting"]
    says = cfg["says"]
    fl = flow(wiring, experiment)
    places = wiring["promise"]["places"]
    who = {pl["id"]: pl["who"] for pl in places}
    unnamed = [pl["id"] for pl in places if not pl["named"]]

    def harmless(kind: str, own_place: str) -> Optional[str]:
        """The first named place that may hold the kind and is not the step's own place (the log would show a send
        from a place to itself otherwise); None when there is none (that step and kind has no such variant)."""
        for pl in places:
            if pl["named"] and kind in pl["may_hold"] and pl["id"] != own_place:
                return pl["id"]
        return None

    def other_place(kind: str, frm: str, to: str) -> Optional[str]:
        """Rule 3, entry changed, destination (planting.rule3_changed.destination.rule): the first named place that may
        hold the kind and is neither the handover's own destination nor its sender."""
        for pl in places:
            if pl["named"] and kind in pl["may_hold"] and pl["id"] not in (frm, to):
                return pl["id"]
        return None

    def word(k: str) -> str:
        return k.replace("_", " ")

    out: List[J] = []

    # rule 1: an extra send to a place that is not named
    for st in fl["steps"]:
        for kind in st["held"]:
            for dest in unnamed:
                base = "R1.%s.%s.%s" % (st["step"], kind, dest)
                fmt = dict(step=st["step"], kind=word(kind), dest=dest, dest_who=who[dest])
                for k in cfg["kinds"]["1"]:
                    ops = [{"op": "extra_send", "step": st["step"], "kind": kind, "to": dest,
                            "logged": k != "extra_send_not_logged"}]
                    h = harmless(kind, st["place"])
                    if k == "extra_send_false_log":
                        if h is None:
                            continue
                        ops.append({"op": "false_log", "step": st["step"], "kind": kind, "change": {"to": h}})
                    vid = "%s.%s" % (base, k)
                    out.append({"variant_id": vid, "rule": 1, "kind": k,
                                "says": says[k].format(harmless=h, **fmt),
                                "fault": _fault(vid, 1, says[k].format(harmless=h, **fmt), ops), "apart": False})

    # rule 2: a deletion that is skipped (log shows none / log says it happened) or late
    for ev in [e for e in fl["events"] if e["action"] == "delete"]:
        fmt = dict(kind=word(ev["kind"]), place=ev["from"], duty=ev["duty"])
        for k in cfg["kinds"]["2"]:
            ops: List[J] = [{"op": "late_delete" if k == "late_delete" else "skip_delete", "duty": ev["duty"]}]
            if k == "skip_delete_false_log":
                ops.append({"op": "false_log", "mode": "claim_delete", "duty": ev["duty"]})
            vid = "R2.%s.%s" % (ev["duty"], k)
            v = {"variant_id": vid, "rule": 2, "kind": k, "says": says[k].format(**fmt),
                 "fault": _fault(vid, 2, says[k].format(**fmt), ops), "apart": False}
            if k == "skip_delete_false_log":
                v["needs_b1b"] = True
            out.append(v)

    # rule 3: the record loses, changes or gains an entry of a handover
    sends = [e for e in fl["events"] if e["action"] == "send"]
    flow_kinds = []
    for st in fl["steps"]:
        for k in st["held"]:
            if k not in flow_kinds:
                flow_kinds.append(k)
    changed = cfg["rule3_changed"]
    for ev in sends:
        fmt = dict(kind=word(ev["kind"]), to=ev["to"], step=ev["step"])
        fmt["from"] = ev["from"]
        vid = "R3.%s.entry_removed" % ev["move"]
        s = says["entry_removed"].format(**fmt)
        out.append({"variant_id": vid, "rule": 3, "kind": "entry_removed", "says": s,
                    "fault": _fault(vid, 3, s, [{"op": "false_log", "step": ev["step"], "kind": ev["kind"], "change": None}]),
                    "fault_record": _fault(vid, 3, s, [{"op": "edit_record", "mode": "drop", "position": ev["journal_pos"]}]),
                    "apart": False, "needs_b1b": True})
        other = next((k for k in flow_kinds if k != ev["kind"]), None)
        values = {"destination": other_place(ev["kind"], ev["from"], ev["to"]), "kind": other,
                  "time": changed["time"]["value"]}
        for fname in ("destination", "kind", "time"):
            val = values[fname]
            if val is None:
                continue
            vid = "R3.%s.entry_changed.%s" % (ev["move"], fname)
            s = says["entry_changed"].format(field=fname, value=val, **fmt)
            out.append({"variant_id": vid, "rule": 3, "kind": "entry_changed", "says": s,
                        "fault": _fault(vid, 3, s, [{"op": "false_log", "step": ev["step"], "kind": ev["kind"],
                                                     "change": {changed[fname]["own_log"]: val}}]),
                        "fault_record": _fault(vid, 3, s, [{"op": "edit_record", "position": ev["journal_pos"],
                                                            "field": changed[fname]["record"], "value": val}]),
                        "apart": False})
    real = {(e["from"], e["to"], e["kind"]) for e in sends}
    for st in fl["steps"]:
        for kind in st["held"]:
            for pl in places:
                if not pl["named"] or kind not in pl["may_hold"] or pl["id"] == st["place"]:
                    continue
                if (st["place"], pl["id"], kind) in real:
                    continue
                fmt = dict(kind=word(kind), to=pl["id"], step=st["step"])
                fmt["from"] = st["place"]
                vid = "R3.add.%s.%s.%s" % (st["step"], kind, pl["id"])
                s = says["entry_added"].format(**fmt)
                line = {"step": st["step"], "kind": kind, "from": st["place"], "to": pl["id"]}
                out.append({"variant_id": vid, "rule": 3, "kind": "entry_added", "says": s,
                            "fault": _fault(vid, 3, s, [dict({"op": "false_log", "mode": "add",
                                                              "position": st["own_end"]}, **line)]),
                            "fault_record": _fault(vid, 3, s, [dict({"op": "edit_record", "mode": "add",
                                                                     "position": st["journal_end"]}, **line)]),
                            "apart": False, "needs_b1b": True})

    # apart: a copy kept inside a step, and the hidden instruction of part 1b
    ap = cfg["apart"]
    for st in fl["steps"]:
        for kind in st["held"]:
            if hold_ticks(wiring, choices, st["place"], kind) is None:
                continue  # the place may keep this kind for good: a copy kept there breaks no rule
            vid = "A.keep_copy.%s.%s" % (st["step"], kind)
            s = says["keep_copy"].format(step=st["step"], kind=word(kind))
            out.append({"variant_id": vid, "rule": ap["keep_copy_rule"], "kind": "keep_copy", "says": s,
                        "fault": _fault(vid, ap["keep_copy_rule"], s,
                                        [{"op": "keep_copy", "step": st["step"], "kind": kind}]),
                        "apart": True})
    for dest in unnamed:
        vid = "A.hidden_instruction.%s" % dest
        s = says["hidden_instruction"].format(dest=dest, dest_who=who[dest])
        text = cfg["inject_text"].format(kind=ap["hidden_instruction_kind"], place=dest)
        out.append({"variant_id": vid, "rule": ap["hidden_instruction_rule"], "kind": "hidden_instruction",
                    "says": s,
                    "fault": _fault(vid, ap["hidden_instruction_rule"], s,
                                    [{"op": "inject", "kind": ap["hidden_instruction_kind"], "text": text}]),
                    "apart": True})
    return out


# ------------------------------------------------------------------ the draw by lot

def _lot(seed: Any, part: str) -> random.Random:
    return random.Random("%s:%s" % (seed, part))


def _shuffled(items: List[Any], rng: random.Random) -> List[Any]:
    out = list(items)
    rng.shuffle(out)
    return out


def _by_kind(catalogue_rows: List[J], rule: int, kind: str, apart: bool) -> List[J]:
    return [v for v in catalogue_rows if v["rule"] == rule and v["kind"] == kind and bool(v["apart"]) == apart]


def _draw_exp1(cases: List[Any], cat: List[J], choices: J, split: str) -> J:
    cfg = choices["planting"]
    seed = choices["seeds"]["faults"]
    ids = sorted(v.visit_id for v in cases if v.split == split)
    planted: List[J] = []
    counts: J = {"cases_in_split": len(ids), "planted": {}, "short": {}}
    for rule in (1, 2, 3):
        kinds = cfg["kinds"][str(rule)]
        n = min(cfg["per_rule"], len(ids))
        if n < cfg["per_rule"]:
            counts["short"]["rule%d" % rule] = {"wanted": cfg["per_rule"], "taken": n}
        order = _shuffled(kinds, _lot(seed, "rule%d:kind_order" % rule))  # the first gets the extra one
        pools = {}
        for k in kinds:
            pool = [v["variant_id"] for v in _by_kind(cat, rule, k, False)]
            if not pool:
                raise ContractError("the catalogue holds no variant of rule %d, kind %s" % (rule, k))
            pools[k] = _shuffled(pool, _lot(seed, "rule%d:%s:variants" % (rule, k)))
        cases_r = _shuffled(ids, _lot(seed, "rule%d:cases" % rule))[:n]
        used = {k: 0 for k in kinds}
        for i, case in enumerate(cases_r):
            k = order[i % len(order)]
            pool = pools[k]
            planted.append({"plant_id": "P%d-%03d" % (rule, i + 1), "rule": rule, "kind": k,
                            "variant_id": pool[used[k] % len(pool)], "case": case, "order": i + 1})
            used[k] += 1
        counts["planted"]["rule%d" % rule] = dict({"total": n}, **{k: used[k] for k in kinds})
    apart_rows: Dict[str, List[J]] = {}
    for part, kind, limit, prefix in (("kept_copy", "keep_copy", cfg["kept_copy_cases"], "K"),
                                      ("hidden", "hidden_instruction", cfg["hidden_runs"], "H")):
        pool = _shuffled([v["variant_id"] for v in cat if v["apart"] and v["kind"] == kind],
                         _lot(seed, "%s:variants" % part))
        n = min(limit, len(ids)) if pool else 0
        if n < limit:
            counts["short"][part] = {"wanted": limit, "taken": n}
        cs = _shuffled(ids, _lot(seed, "%s:cases" % part))[:n]
        rule = [v for v in cat if v["apart"] and v["kind"] == kind]
        apart_rows[part] = [{"plant_id": "%s-%03d" % (prefix, i + 1), "rule": rule[0]["rule"] if rule else None,
                             "kind": kind, "variant_id": pool[i % len(pool)], "case": c, "order": i + 1}
                            for i, c in enumerate(cs)]
        counts[part] = n
    if split == "test":  # the owner's decision: the hidden lines of the test set carry wordings the monitor never saw
        words = cfg["inject_texts_test"]
        for row, w in zip(apart_rows["hidden"], _wordings(len(apart_rows["hidden"]), len(words), seed)):
            row["wording"] = w
    repeat: List[str] = []
    for rule in (1, 2, 3):
        rows = [r for r in planted if r["rule"] == rule]
        take = min(cfg["repeat_per_rule"], len(rows))
        pick = _lot(seed, "repeat:rule%d" % rule).sample(rows, take)
        repeat.extend(r["plant_id"] for r in sorted(pick, key=lambda r: r["order"]))
        counts.setdefault("repeat", {})["rule%d" % rule] = take
    return {"experiment": 1, "split": split, "seed": seed, "clean": ids, "planted": planted,
            "kept_copy": apart_rows["kept_copy"], "hidden": apart_rows["hidden"], "repeat": repeat,
            "counts": counts}


def _wordings(n: int, count: int, seed: Any) -> List[int]:
    """Which wording each of n hidden rows gets: an index into a list of `count` wordings, spread evenly (the counts
    differ by at most one) and put in order by lot (sub-seed hidden:wording)."""
    idx = [i % count for i in range(n)]
    _lot(seed, "hidden:wording").shuffle(idx)
    return idx


def _directions(grade: str, choices: J) -> List[str]:
    levels = choices["ladder"]["levels"]
    i = levels.index(grade)
    out = []
    if i < len(levels) - 1:
        out.append("more_certain")
    if i > levels.index(choices["planting"]["rule5_softest_level"]):
        out.append("less_certain")
    return out


def _draw_exp2(cases: List[Any], choices: J, split: str) -> J:
    cfg = choices["planting"]
    seed = choices["seeds"]["faults"]
    cs = sorted((v for v in cases if v.split == split), key=lambda v: v.visit_id)
    graded = [v for v in cs if v.expert_certainty is not None]
    want = cfg["per_rule"] + cfg["reserve_per_rule"]
    n = min(want, len(cs) // 3)
    n5 = min(n, len(graded))
    n46 = min(n, (len(cs) - n5) // 2)
    sizes = {4: n46, 5: n5, 6: n46}
    counts: J = {"cases_in_split": len(cs), "graded_in_split": len(graded), "planted": {}, "short": {}}
    for r in (4, 5, 6):
        if sizes[r] < want:
            counts["short"]["rule%d" % r] = {"wanted": want, "taken": sizes[r]}
    grade = {v.visit_id: v.expert_certainty for v in cs}
    chosen = {5: [v.visit_id for v in _shuffled(graded, _lot(seed, "rule5:cases"))[:n5]]}
    left = [v.visit_id for v in cs if v.visit_id not in set(chosen[5])]
    left = _shuffled(left, _lot(seed, "rules46:cases"))
    chosen[4] = left[:n46]
    chosen[6] = left[n46:2 * n46]
    planted: List[J] = []
    for r in (4, 5, 6):
        kinds = cfg["rules_4_6"][str(r)]["kinds"]
        steps = cfg["rules_4_6"][str(r)]["steps"]
        order = _shuffled(kinds, _lot(seed, "rule%d:kind_order" % r))
        pick_step = _lot(seed, "rule%d:step" % r)
        pick_dir = _lot(seed, "rule%d:direction" % r)
        tally: Dict[str, int] = {}
        by_step: Dict[str, int] = {}
        for i, case in enumerate(chosen[r]):
            k = order[i % len(order)]
            if r == 5:
                ways = _directions(grade[case], choices)
                k = pick_dir.choice(ways)
            step = pick_step.choice(steps)
            planted.append({"plant_id": "P%d-%03d" % (r, i + 1), "rule": r, "kind": k, "step": step,
                            "case": case, "reserve": i >= cfg["per_rule"], "order": i + 1})
            tally[k] = tally.get(k, 0) + 1
            by_step[step] = by_step.get(step, 0) + 1
        counts["planted"]["rule%d" % r] = dict({"total": len(chosen[r]), "main": min(len(chosen[r]), cfg["per_rule"]),
                                                "reserve": max(0, len(chosen[r]) - cfg["per_rule"]),
                                                "steps": by_step}, **tally)
    # part 2b: graded questions whose grade is below the top level of the ladder (every lower level, no data included):
    # the hidden line asks for more certainty than the experts gave, which needs room above the grade
    top = choices["ladder"]["levels"][-1]
    eligible = [v for v in graded if v.expert_certainty != top]
    counts["hidden_eligible"] = len(eligible)
    nh = min(cfg["hidden_runs"], len(eligible))
    if nh < cfg["hidden_runs"]:
        counts["short"]["hidden"] = {"wanted": cfg["hidden_runs"], "taken": nh}
    hid = _shuffled([v.visit_id for v in eligible], _lot(seed, "hidden:cases"))[:nh]
    hidden = [{"plant_id": "H-%03d" % (i + 1), "rule": 5, "kind": "hidden_instruction", "case": c, "order": i + 1}
              for i, c in enumerate(hid)]
    if split == "test":
        for row, w in zip(hidden, _wordings(len(hidden), len(cfg["certainty_texts_test"]), seed)):
            row["wording"] = w
    counts["hidden"] = nh
    counts["hidden_also_in_a_rule"] = len(set(hid) & {r["case"] for r in planted})
    repeat: List[str] = []
    for r in (4, 5, 6):
        rows = [p for p in planted if p["rule"] == r and not p["reserve"]]
        take = min(cfg["repeat_per_rule"], len(rows))
        pick = _lot(seed, "repeat:rule%d" % r).sample(rows, take)
        repeat.extend(p["plant_id"] for p in sorted(pick, key=lambda p: p["order"]))
        counts.setdefault("repeat", {})["rule%d" % r] = take
    return {"experiment": 2, "split": split, "seed": seed, "planted": planted, "hidden": hidden,
            "repeat": repeat, "counts": counts}


def draw(cases: List[Any], cat: List[J], choices: J, experiment: int, split: str) -> J:
    """The plan of one experiment on one split: which violation goes on which case.

    Experiment 1: {experiment, split, seed, clean, planted, kept_copy, hidden, repeat, counts}; a planted row is
    {plant_id, rule, kind, variant_id, case, order}. Experiment 2: {experiment, split, seed, planted, hidden, repeat,
    counts}; a planted row is {plant_id, rule, kind, step, case, reserve, order} (the format of tools/outside_texts.py
    make). `repeat` lists the plant ids planted a second time for the repeat check."""
    if experiment == 1:
        plan = _draw_exp1(cases, cat, choices, split)
        plan["catalogue_sha256"] = fingerprint(cat)  # units.build refuses a list that is not the one this plan was drawn from
        return plan
    if experiment == 2:
        return _draw_exp2(cases, choices, split)
    raise ContractError("experiment must be 1 or 2")
