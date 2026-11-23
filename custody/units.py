"""Version 3: the units of a plan.

A unit is one case with at most one planted violation, run under each method asked for. Its id is the case id for a
clean unit and '<case>+<plant id>' for a planted one (a kept copy, a hidden instruction and a repeat included; the
repeat check adds '+r<n>'). Every unit keeps the case's conversation and question ids and names the clean case it
was made from in `clean_of`, so that the scorer pairs a planted unit with the clean unit of the same case.

Only the bench side reads this module (it knows the faults). Counts and wordings are in config "bench_plan".
"""
import copy
import dataclasses
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from custody.core import ContractError, DataError, J, Visit, fingerprint

JOINER = "+"
PARTS = ("clean", "planted", "kept_copy", "hidden", "repeat")


def case_of(unit_id: str) -> str:
    """The case a unit was made from."""
    return unit_id.split(JOINER, 1)[0]


def unit_id(case_id: str, plant_id: Optional[str] = None, repeat: Optional[int] = None) -> str:
    out = case_id if plant_id is None else JOINER.join([case_id, plant_id])
    return out if repeat is None else "%s%sr%d" % (out, JOINER, repeat)


def read_json(path: Any, what: str) -> J:
    try:
        return json.loads(Path(str(path)).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise DataError("cannot read %s %s: %s" % (what, path, e))


def variants_by_id(catalogue: J) -> Dict[str, J]:
    """The variants of a catalogue file (tools/make_plan.py) by variant id."""
    rows = catalogue["variants"] if isinstance(catalogue, dict) else catalogue
    return {v["variant_id"]: v for v in rows}


def fault_of_variant(variant: J) -> J:
    """The fault a unit plants: the variant's `fault`, with its `fault_record` (rule 3: the operation against the
    checker's record, used under Checked) carried inside it."""
    fault = copy.deepcopy(variant["fault"])
    if variant.get("fault_record"):
        fault["fault_record"] = copy.deepcopy(variant["fault_record"])
    return fault


def hidden_answer_fault(choices: J, row: J) -> J:
    """Experiment 2, part 2b: the hidden instruction in the answer text (builder A's inject, kind answer)."""
    cfg = choices["bench_plan"]["hidden_answer"]
    text = choices["canned"]["injection_certainty"]["text"]
    if row.get("wording") is not None:  # the test split: one of planting.certainty_texts_test, by the row's index
        text = choices["planting"]["certainty_texts_test"][row["wording"]]
    return {"fault_id": cfg["fault_id"], "kind": "step", "rule": cfg["rule"], "says": cfg["says"],
            "ops": [{"op": "inject", "kind": "answer", "text": text}],
            "patch": [], "events": [], "needs": {}}


def reword_hidden(fault: J, row: J, choices: J) -> J:
    """Experiment 1, test split: the hidden line takes the wording of the row (planting.inject_texts_test[wording]),
    for the place the variant names (the last part of its id, A.hidden_instruction.<place>)."""
    place = fault["fault_id"].rsplit(".", 1)[1]
    ap = choices["planting"]["apart"]
    text = choices["planting"]["inject_texts_test"][row["wording"]].format(kind=ap["hidden_instruction_kind"], place=place)
    for op in fault["ops"]:
        if op["op"] == "inject":
            op["text"] = text
    return fault


def make_unit(case: Visit, uid: str, part: str, row: Optional[J], salt: Optional[str] = None) -> Visit:
    if uid == case.visit_id:
        return case
    info = {"part": part, "plant_id": row["plant_id"] if row else None, "rule": row["rule"] if row else None}
    if salt:
        info["salt"] = salt
    return dataclasses.replace(case, visit_id=uid, clean_of=case.visit_id, meta=dict(case.meta, unit=info))


def build(plan: J, part: str, cases: List[Visit], choices: J, catalogue: Optional[J] = None,
          exp2_faults: Optional[J] = None, rule: Optional[int] = None) -> Tuple[List[Visit], Dict[str, Optional[J]]]:
    """The units of one part of a plan, in the plan's order, and their faults by unit id.

    clean: the plan's clean cases (Experiment 2: every case of the plan's split); planted: the planted rows (for
    Experiment 1 their fault comes from the catalogue by variant_id, for Experiment 2 from the faults file of
    tools/make_plan.py faults-exp2, so a row with no fault there is not run); kept_copy and hidden: those rows;
    repeat: the planted rows named in plan['repeat'], each run again as '<case>+<plant id>+r<n>' with fresh answers.
    With `rule`, the rows of that rule only (clean: the cases that have a planted row of that rule)."""
    if part not in PARTS:
        raise ContractError("part must be one of %s" % ", ".join(PARTS))
    exp = plan["experiment"]
    by_case = {v.visit_id: v for v in cases if v.split == plan["split"]}
    by_variant = variants_by_id(catalogue) if catalogue is not None else None
    if catalogue is not None and plan.get("catalogue_sha256"):
        rows = catalogue["variants"] if isinstance(catalogue, dict) else catalogue
        if fingerprint(rows) != plan["catalogue_sha256"]:
            raise ContractError("the list of variants is not the one this plan was drawn from (its fingerprint differs): "
                                "draw the plan again from this list, or use the list written with the plan")
    faults2 = (exp2_faults or {}).get("faults", {})

    def need_catalogue() -> Dict[str, J]:
        if by_variant is None:
            raise ContractError("an Experiment 1 plan is run with its list of variants (--catalogue)")
        return by_variant

    def fault_for(row: J) -> Optional[J]:
        if exp == 1:
            v = need_catalogue().get(row["variant_id"])
            if v is None:
                raise ContractError("the list has no variant %s" % row["variant_id"])
            return fault_of_variant(v)
        return copy.deepcopy(faults2.get(row["plant_id"]))

    def case(cid: str) -> Visit:
        if cid not in by_case:
            raise ContractError("the plan names the case %s, which is not a case of the split %s" % (cid, plan["split"]))
        return by_case[cid]

    def keep(row: J) -> bool:
        return rule is None or row.get("rule") == rule

    units: List[Visit] = []
    faults: Dict[str, Optional[J]] = {}
    if part == "clean":
        ids = plan["clean"] if "clean" in plan else sorted(by_case)
        if rule is not None:
            twins = {r["case"] for r in plan["planted"] if r["rule"] == rule}
            ids = [c for c in ids if c in twins]
        for cid in ids:
            units.append(case(cid))
            faults[cid] = None
    elif part == "repeat":
        base = {r["plant_id"]: r for r in plan["planted"]}
        n = choices["bench_plan"]["repeat_number"]
        for pid in plan["repeat"]:
            row = base.get(pid)
            if row is None or not keep(row):
                continue
            f = fault_for(row)
            if f is None:
                continue
            f["unit_part"] = "repeat"
            uid = unit_id(row["case"], pid, n)
            u = make_unit(case(row["case"]), uid, part, row, "r%d" % n)
            if exp == 2:  # the steps before the planted one are not asked afresh: the changed text is the old one, planted again
                u.meta["unit"]["salt_from"] = row["step"]
            units.append(u)
            faults[uid] = f
    else:
        key = {"planted": "planted", "kept_copy": "kept_copy", "hidden": "hidden"}[part]
        for row in plan.get(key, []):
            if not keep(row):
                continue
            if part == "hidden" and exp == 2:
                f = hidden_answer_fault(choices, row)
            else:
                f = fault_for(row)
                if part == "hidden" and f is not None and row.get("wording") is not None:
                    f = reword_hidden(f, row, choices)
            if f is None:
                continue
            uid = unit_id(row["case"], row["plant_id"])
            units.append(make_unit(case(row["case"]), uid, part, row))
            faults[uid] = f
    return units, faults


def exp2_faults(plan: J, confirmed: List[J], choices: J) -> J:
    """The faults of the planted units of Experiment 2: per rule the first planting.per_rule confirmed rows in the
    plan's order, one fault each (rewrite, mode set_text, at the row's step). The file is
    {experiment, per_rule, faults: {plant_id: fault}, counts: {rule: n}}."""
    cap = choices["planting"]["per_rule"]
    order = {r["plant_id"]: i for i, r in enumerate(plan["planted"])}
    plan_row = {r["plant_id"]: r for r in plan["planted"]}
    ok = [r for r in confirmed if r.get("plant_id") in plan_row and isinstance(r.get("changed_text"), str)
          and not r.get("unparsed") and r.get("status") != "unparsed"]
    ok.sort(key=lambda r: order[r["plant_id"]])
    out: J = {}
    counts: Dict[str, int] = {}
    seen = set()
    for r in ok:
        row = plan_row[r["plant_id"]]
        k = str(row["rule"])
        if r["plant_id"] in seen or counts.get(k, 0) >= cap:
            continue
        seen.add(r["plant_id"])
        counts[k] = counts.get(k, 0) + 1
        out[row["plant_id"]] = {
            "fault_id": row["plant_id"], "kind": "step", "rule": row["rule"],
            "says": "The text at the step %s is replaced by a changed text (%s)." % (row["step"], row["kind"]),
            "ops": [{"op": "rewrite", "step": row["step"], "mode": "set_text", "text": r["changed_text"],
                     "changed_kind": row["kind"]}],
            "patch": [], "events": [], "needs": {}}
    return {"experiment": 2, "per_rule": cap, "faults": out, "counts": dict(sorted(counts.items()))}
