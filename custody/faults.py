"""Faults: loading, checking, planning, and the operations that plant them.

A fault is a JSON object (config/design_choices.json, "faults"). Step faults
are planted by wrapping steps and editing records; wiring faults by patching a
copy of the wiring's plumbing. Nothing here is handed to the chain: only the
bench calls this module.
"""
import copy
import dataclasses
import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from custody import world as world_mod
from custody.core import ContractError, Item, J, LANE_OF, StepOutput, Visit, make_item_id

ROOT = Path(__file__).resolve().parents[1]
KNOWN_NEEDS = ("expert_certainty_in", "stored_answer", "split")
STEP_OPS = ("extra_send", "keep_copy", "skip_delete", "late_delete", "rewrite", "inject", "false_log", "edit_record")
REWRITE_MODES = ("wrong_source", "drop_source", "set_level", "drop_ai_mark", "replace", "set_text")
FALSE_LOG_MODES = ("claim_delete", "add")      # a false_log without a mode changes or drops a line (version 2)
EDIT_RECORD_MODES = ("drop", "add")            # an edit_record without a mode sets one field of a stored line


# ------------------------------------------------------------------- loading

def load_faults(choices: J, root: Optional[Path] = None, include_sealed: bool = False) -> List[J]:
    """The development faults, and the sealed ones after them when asked for."""
    out = [copy.deepcopy(f) for f in choices["faults"]["development"]]
    if include_sealed:
        path = Path(root or ROOT) / choices["faults"]["sealed_file"]
        if path.exists():
            with open(str(path), "r", encoding="utf-8") as fh:
                for line in fh:
                    if line.strip():
                        out.append(json.loads(line))
    return out


# ------------------------------------------------------------------ planning

def _needs_of(fault: J) -> J:
    needs = dict(fault.get("needs") or {})
    for key in needs:
        if key not in KNOWN_NEEDS:
            raise ContractError("unknown key in needs: %r (fault %s)" % (key, fault.get("fault_id")))
    ops = fault.get("ops") or []
    if fault.get("rule") in (4, 5, 6) or any(op.get("op") == "inject" for op in ops):
        needs["split"] = "test"
    return needs


def _meets(visit: Visit, needs: J) -> bool:
    if "split" in needs and visit.split != needs["split"]:
        return False
    if "expert_certainty_in" in needs and visit.expert_certainty not in needs["expert_certainty_in"]:
        return False
    if "stored_answer" in needs and (visit.given_answer is not None) != bool(needs["stored_answer"]):
        return False
    return True


def _read_wiring() -> J:
    with open(str(ROOT / "wiring" / "wiring.json"), encoding="utf-8") as fh:
        return json.load(fh)


def fault_lane(fault: J, wiring: Optional[J] = None) -> Optional[str]:
    """The lane ('words' or 'advice') a fault touches, from the steps, duties, moves, detours, inject kinds and
    patch paths it names; None when it names nothing of a lane (it then fits either)."""
    p = (wiring or _read_wiring())["plumbing"]
    step_lane = {s: ln["id"] for ln in p["lanes"] for s in ln["steps"]}
    move_lane = {m["id"]: step_lane.get(m["step"]) for m in p["moves"]}
    duty_lane = {d["id"]: (move_lane.get(d["after"]) if "after" in d else step_lane.get(d.get("after_step")))
                 for d in p["duties"]}
    ids = dict(move_lane)
    ids.update(duty_lane)
    ids.update({d["id"]: ids.get(d["at"]) for d in p["detours"]})
    ids.update(step_lane)
    found = set()
    for op in fault.get("ops") or []:
        if op.get("op") == "inject":
            found.add("words" if op.get("kind") == "transcript" else "advice")
        for key in ("step", "duty"):
            if key in op:
                found.add(ids.get(op[key]))
    for ev in fault.get("events") or []:
        found.add(ids.get(ev.get("at")))
    for entry in fault.get("patch") or []:
        segs = [x for x in entry.get("path", "").split("/") if x]
        if len(segs) >= 3:
            found.add(ids.get(segs[2]))
    found.discard(None)
    return found.pop() if len(found) == 1 else None


def _lane_fits(fault: J, visits: List[Visit], wiring: Optional[J]) -> bool:
    exps = {v.experiment for v in visits}
    if len(exps) != 1 or next(iter(exps)) not in LANE_OF:
        return True
    lane = fault_lane(fault, wiring)
    return lane is None or lane == LANE_OF[next(iter(exps))]


def plan_faults_report(visits: List[Visit], faults: List[J], choices: J,
                       wiring: Optional[J] = None) -> Tuple[Dict[str, Optional[J]], List[str]]:
    """The plan, and the ids of the faults that no visit could take. When every case is of one experiment, a fault
    of the other lane is not planted and is not reported (Version 2)."""
    order = list(visits)
    if len(order) > choices["visits"]["e2e"]:
        random.Random(choices["seeds"]["faults"]).shuffle(order)
    plan: Dict[str, Optional[J]] = {v.visit_id: None for v in visits}
    unplaced: List[str] = []
    for fault in faults:
        if not _lane_fits(fault, visits, wiring):
            continue
        needs = _needs_of(fault)
        for visit in order:
            if plan[visit.visit_id] is None and _meets(visit, needs):
                plan[visit.visit_id] = fault
                break
        else:
            unplaced.append(str(fault.get("fault_id")))
    return plan, unplaced


def load_practice_faults(experiment: int, choices: J, root: Optional[Path] = None) -> List[J]:
    """The practice violations of one experiment (the 'faults' of the file in cases.trial.practice_faults)."""
    path = Path(root or ROOT) / choices["cases"]["trial"]["practice_faults"][str(experiment)]
    with open(str(path), "r", encoding="utf-8") as fh:
        return [copy.deepcopy(f) for f in json.load(fh)["faults"]]


def plan_trial(cases: List[Visit], faults: List[J], n_clean: int, choices: J,
               wiring: Optional[J] = None) -> Tuple[List[Visit], Dict[str, Optional[J]], List[str], List[str]]:
    """A trial selection: n_clean clean practice cases, plus each practice violation of the cases' lane on a
    different practice case that is not among the clean ones. The practice cases are put in order by seeds.faults.
    Returns (the chosen cases in case order, the plan, the ids of the clean ones, the ids no case could take)."""
    practice = [v for v in cases if v.split == "tune"]
    order = list(practice)
    random.Random(choices["seeds"]["faults"]).shuffle(order)
    clean, rest = order[:n_clean], order[n_clean:]
    plan: Dict[str, Optional[J]] = {}
    unplaced: List[str] = []
    for fault in faults:
        if not _lane_fits(fault, cases, wiring):
            continue
        needs = _needs_of(fault)
        needs.pop("split", None)  # the practice set is the one in use
        for visit in rest:
            if visit.visit_id not in plan and _meets(visit, needs):
                plan[visit.visit_id] = fault
                break
        else:
            unplaced.append(str(fault.get("fault_id")))
    chosen_ids = {v.visit_id for v in clean} | set(plan)
    chosen = [v for v in cases if v.visit_id in chosen_ids]
    full: Dict[str, Optional[J]] = {v.visit_id: plan.get(v.visit_id) for v in chosen}
    return chosen, full, [v.visit_id for v in clean], unplaced


def plan_faults(visits: List[Visit], faults: List[J], choices: J) -> Dict[str, Optional[J]]:
    return plan_faults_report(visits, faults, choices)[0]


# ------------------------------------------------------------------- patches

def _pick(container: Any, seg: str, path: str) -> Any:
    """The key, or index, that a path segment names in this container."""
    if isinstance(container, list):
        for i, el in enumerate(container):
            if isinstance(el, dict) and el.get("id") == seg:
                return i
        if seg.isdigit() and int(seg) < len(container):
            return int(seg)
        raise ContractError("patch path %s: no element %r" % (path, seg))
    if isinstance(container, dict):
        if seg in container:
            return seg
        raise ContractError("patch path %s: no key %r" % (path, seg))
    raise ContractError("patch path %s: cannot step into %r" % (path, seg))


def apply_patch(wiring: J, patch: List[J]) -> J:
    """A patched deep copy of the wiring. Only paths under /plumbing/ are allowed."""
    out = copy.deepcopy(wiring)
    for entry in patch or []:
        path = entry.get("path", "")
        if not path.startswith("/plumbing/"):
            raise ContractError("a patch may touch /plumbing/ only: %r" % (path,))
        op = entry.get("op")
        if op not in ("add", "remove", "replace"):
            raise ContractError("unknown patch op %r" % (op,))
        segs = [s for s in path.split("/") if s != ""]
        node = out
        for seg in segs[:-1]:
            node = node[_pick(node, seg, path)]
        last = segs[-1]
        if op == "add":
            if isinstance(node, list):
                if last == "-":
                    node.append(copy.deepcopy(entry["value"]))
                elif last.isdigit() and int(last) <= len(node):
                    node.insert(int(last), copy.deepcopy(entry["value"]))
                else:
                    raise ContractError("patch path %s: bad position" % (path,))
            elif isinstance(node, dict):
                node[last] = copy.deepcopy(entry["value"])
            else:
                raise ContractError("patch path %s: cannot add here" % (path,))
        else:
            key = _pick(node, last, path)
            if op == "remove":
                del node[key]
            else:
                node[key] = copy.deepcopy(entry["value"])
    return out


# ------------------------------------------------------------------ checking

def _ids(wiring: J, section: str) -> List[str]:
    return [e["id"] for e in wiring["plumbing"].get(section, [])]


def check_fault(fault: J, wiring: J, choices: J) -> None:
    """Raise ContractError when the fault does not fit the wiring or the format."""
    fid = fault.get("fault_id")
    if fault.get("kind") not in ("step", "wiring"):
        raise ContractError("fault %s: kind must be step or wiring" % fid)
    _needs_of(fault)
    patched = apply_patch(wiring, fault.get("patch") or [])
    steps = _ids(patched, "steps") + ["janitor"]
    duties = _ids(patched, "duties") + _ids(patched, "detours")
    kinds = wiring.get("kinds", [])
    for ev in fault.get("events") or []:
        if not any(d["on"] == ev.get("on") and d["at"] == ev.get("at") for d in wiring["plumbing"]["detours"]):
            raise ContractError("fault %s: no detour for event %r" % (fid, ev))
    for op in fault.get("ops") or []:
        name = op.get("op")
        if name not in STEP_OPS:
            raise ContractError("fault %s: unknown operation %r" % (fid, name))
        if "step" in op and op["step"] not in steps:
            raise ContractError("fault %s: unknown step %r" % (fid, op["step"]))
        if "duty" in op and op["duty"] not in duties:
            raise ContractError("fault %s: unknown duty %r" % (fid, op["duty"]))
        if "kind" in op and name != "inject" and kinds and op["kind"] not in kinds:
            raise ContractError("fault %s: unknown kind %r" % (fid, op["kind"]))
        if name == "rewrite":
            if op.get("mode") not in REWRITE_MODES:
                raise ContractError("fault %s: unknown rewrite mode %r" % (fid, op.get("mode")))
            if op["mode"] == "set_level" and op.get("level") not in choices["ladder"]["levels"]:
                raise ContractError("fault %s: unknown level %r" % (fid, op.get("level")))
            if op["mode"] == "set_text" and not isinstance(op.get("text"), str):
                raise ContractError("fault %s: rewrite mode set_text needs a text" % fid)
        if name == "inject" and op.get("kind") not in ("transcript", "question", "answer"):
            raise ContractError("fault %s: inject kind must be transcript, question or answer" % fid)
        if name in ("false_log", "edit_record"):
            _check_record_op(fid, op, wiring, patched)
        if name == "edit_record" and not (isinstance(op.get("position"), int) and op["position"] >= 0):
            raise ContractError("fault %s: edit_record needs a position from 0" % fid)


def _check_record_op(fid: Any, op: J, wiring: J, patched: J) -> None:
    """The modes of false_log (claim_delete, add) and edit_record (drop, add) and the fields each needs."""
    name, mode = op["op"], op.get("mode")
    allowed = FALSE_LOG_MODES if name == "false_log" else EDIT_RECORD_MODES
    if mode is not None and mode not in allowed:
        raise ContractError("fault %s: unknown %s mode %r" % (fid, name, mode))
    if mode == "claim_delete":
        duty = next((d for d in patched["plumbing"].get("duties", []) if d["id"] == op.get("duty")), None)
        if duty is None:
            raise ContractError("fault %s: claim_delete names a duty that is in the wiring" % fid)
    if mode == "add":
        places = {pl["id"] for pl in wiring.get("promise", {}).get("places", [])}
        for key in ("step", "kind", "from", "to"):
            if not isinstance(op.get(key), str):
                raise ContractError("fault %s: %s mode add needs %r" % (fid, name, key))
        for key in ("from", "to"):
            if places and op[key] not in places:
                raise ContractError("fault %s: unknown place %r" % (fid, op[key]))
        if not (isinstance(op.get("position"), int) and op["position"] >= 0):
            raise ContractError("fault %s: %s mode add needs a position from 0" % (fid, name))
    if name == "edit_record" and mode is None and not isinstance(op.get("field"), str):
        raise ContractError("fault %s: edit_record without a mode needs a field and a value" % fid)


def _enters_text(wiring: J, step_id: Optional[str]) -> Optional[str]:
    """The kind a step reads when it makes nothing and the text it reads enters the flow ready-made (version 3:
    the step `answer`); None for a step that makes an item. A rewrite planted at such a step changes the entering
    text, before its handover."""
    for spec in wiring["plumbing"]["steps"]:
        if spec["id"] == step_id and spec.get("makes") is None and spec.get("reads"):
            return spec["reads"][0]
    return None


# ---------------------------------------------------------- rewriting text

def _tags(text: str, choices: J) -> List[Tuple[int, int]]:
    tag = choices["markers"]["source_tag"]
    spans = []
    pos = 0
    while True:
        a = text.find(tag["open"], pos)
        if a < 0:
            break
        b = text.find(tag["close"], a + len(tag["open"]))
        if b < 0:
            break
        spans.append((a, b + len(tag["close"])))
        pos = b + len(tag["close"])
    return spans


def rewrite_text(text: str, op: J, choices: J) -> str:
    mode = op["mode"]
    tag = choices["markers"]["source_tag"]
    if mode == "wrong_source":
        wrong = choices["faults"]["wrong_source_id"]
        out, last = [], 0
        for a, b in _tags(text, choices):
            inner = text[a + len(tag["open"]):b - len(tag["close"])]
            n = len([p for p in inner.split(tag["separator"]) if p.strip()])
            new = tag["open"] + " " + (tag["separator"] + " ").join([wrong] * n) + tag["close"]
            out.append(text[last:a])
            out.append(new)
            last = b
        out.append(text[last:])
        return "".join(out)
    if mode == "drop_source":
        out, last = [], 0
        for a, b in _tags(text, choices):
            head = text[last:a]
            if head.endswith(" "):
                head = head[:-1]
            out.append(head)
            last = b
        out.append(text[last:])
        return "".join(out)
    if mode == "set_level":
        marker = choices["markers"]["claim"]
        lines = text.splitlines(keepends=True)
        for i, raw in enumerate(lines):
            if not raw.startswith(marker):
                continue
            body = raw.rstrip("\r\n")
            eol = raw[len(body):]
            at = body.find(tag["open"], len(marker))
            sentence = choices["ladder"]["canned"][op["level"]]
            new = marker + " " + sentence + ((" " + body[at:]) if at >= 0 else "")
            lines[i] = new + eol
            break
        return "".join(lines)
    if mode == "drop_ai_mark":
        mark = choices["markers"]["ai"]
        return "".join(ln for ln in text.splitlines(keepends=True) if ln.strip() != mark)
    if mode == "replace":
        return text.replace(op["find"], op["with"])
    if mode == "set_text":
        return op["text"]
    raise ContractError("unknown rewrite mode %r" % (mode,))


# ------------------------------------------------------------ planting faults

def changed_ids(base: J, patched: J) -> List[str]:
    """Ids of moves, duties and detours that a patch changed, added or removed."""
    out = []
    for section in ("moves", "duties", "detours"):
        a = {e["id"]: e for e in base["plumbing"].get(section, [])}
        b = {e["id"]: e for e in patched["plumbing"].get(section, [])}
        for key in sorted(set(a) | set(b)):
            if a.get(key) != b.get(key):
                out.append(key)
    return out


def apply_inject(visit: Visit, fault: Optional[J], world: world_mod.World) -> Visit:
    """A copy of the visit with each inject line appended as the last line of that raw input."""
    for op in (fault or {}).get("ops") or []:
        if op.get("op") != "inject":
            continue
        line = op["text"]
        kind = op["kind"]

        def add(t: str) -> str:
            return t + ("" if t.endswith("\n") or t == "" else "\n") + line

        if kind == "transcript":
            visit = dataclasses.replace(visit, conversation=add(visit.conversation))
        elif kind == "question":
            visit = dataclasses.replace(visit, question=add(visit.question))
        else:
            if visit.answer_text is None:
                raise ContractError("inject into the answer needs a case whose answer text has been made")
            visit = dataclasses.replace(visit, answer_text=add(visit.answer_text))
        world_mod.emit(world, "event", step="", fault_id=fault["fault_id"],
                       detail={"fault_op": "inject", "kind": kind, "text": line})
    return visit


def apply_entering_rewrites(visit: Visit, fault: Optional[J], world: world_mod.World, wiring: J, choices: J) -> Visit:
    """A copy of the visit whose entering answer text carries each rewrite planted at the step `answer` (a step that
    makes nothing): the text is changed before the handover a2. The changed item is tagged with the fault, as a
    rewrite inside a step would tag it."""
    for op in (fault or {}).get("ops") or []:
        if op.get("op") != "rewrite" or _enters_text(wiring, op.get("step")) is None:
            continue
        kind = _enters_text(wiring, op["step"])
        if kind != "answer" or visit.answer_text is None:
            raise ContractError("a rewrite at step %r needs a case with an entering answer text" % (op["step"],))
        text = rewrite_text(visit.answer_text, op, choices)
        if text == visit.answer_text:
            continue
        world_mod.tag_item(world, make_item_id(visit.visit_id, kind, "intake", text), fault["fault_id"])
        visit = dataclasses.replace(visit, answer_text=text)
        world_mod.emit(world, "event", step=op["step"], fault_id=fault["fault_id"],
                       detail={"fault_op": "rewrite", "step": op["step"], "mode": op["mode"], "kind": kind})
    return visit


def wrap_steps(steps: Dict[str, Any], fault: Optional[J], world: world_mod.World, wiring: J, choices: J) -> Dict[str, Any]:
    """The steps with the fault's operations planted in them (a new dict)."""
    out = dict(steps)
    if not fault:
        return out
    fid = fault["fault_id"]
    detour_at: Dict[str, List[str]] = {}
    for d in wiring["plumbing"].get("detours", []):
        detour_at.setdefault(d["at"], []).append(d["id"])

    def fire(op: J, detail: J) -> None:
        d = {"fault_op": op["op"]}
        d.update(detail)
        world_mod.emit(world, "event", step=detail.get("step", ""), fault_id=fid, detail=d)

    for op in fault.get("ops") or []:
        name = op["op"]
        if name == "rewrite" and _enters_text(wiring, op["step"]) is not None:
            continue  # planted on the entering text by apply_entering_rewrites
        if name in ("extra_send", "keep_copy", "rewrite"):
            inner = out[op["step"]]

            def make(inner=inner, op=op, name=name):
                def wrapped(ctx, inbox):
                    res = inner(ctx, inbox)
                    items, requests = list(res.items), list(res.requests)
                    if name == "extra_send":
                        requests.append({"op": "send", "kind": op["kind"], "to": op["to"], "logged": bool(op["logged"])})
                        world_mod.tag_request(world, op["step"], op["kind"], op["to"], fid)
                        fire(op, {"step": op["step"], "kind": op["kind"], "to": op["to"]})
                    elif name == "keep_copy":
                        requests.append({"op": "keep", "kind": op["kind"]})
                        world_mod.tag_keep(world, op["step"], op["kind"], fid)
                        fire(op, {"step": op["step"], "kind": op["kind"]})
                    else:
                        new_items = []
                        for it in items:
                            text = rewrite_text(it.text, op, choices)
                            if text == it.text:
                                new_items.append(it)
                                continue
                            nid = make_item_id(it.visit_id, it.kind, it.made_by, text)
                            world_mod.tag_item(world, nid, fid)
                            new_items.append(dataclasses.replace(it, item_id=nid, text=text))
                            fire(op, {"step": op["step"], "mode": op["mode"], "kind": it.kind})
                        items = new_items
                    return StepOutput(items=items, requests=requests, deletes=list(res.deletes))
                return wrapped
            out[op["step"]] = make()
        elif name in ("skip_delete", "late_delete"):
            inner = out["janitor"]

            def make_j(inner=inner, op=op, name=name):
                duty = op["duty"]
                names = {duty} | set(detour_at.get(duty, []))
                late = {"late:" + n for n in names}
                # the move id that a delete carries, so the handover is tagged
                world_mod.tag_move(world, duty, fid)

                def wrapped(ctx, inbox):
                    res = inner(ctx, inbox)
                    hit = ctx.duty in names or (name == "skip_delete" and ctx.duty in late)
                    if hit and res.deletes:
                        fire(op, {"step": "janitor", "duty": duty, "mode": name})
                        return StepOutput(items=list(res.items), requests=list(res.requests), deletes=[])
                    return res
                return wrapped
            out["janitor"] = make_j()
    return out


def _item_ids_at(world: world_mod.World, kind: str, place: str) -> List[str]:
    """Ids of the copies of a kind that sat at a place during the visit, in order, from the true record (the
    copies may be gone by the end of the visit)."""
    seen: List[str] = []
    for e in world_mod.truth_of(world):
        if e.item_id is None or (e.detail or {}).get("kind") != kind:
            continue
        here = (e.kind == "made" and e.place == place) or \
               (e.kind == "moved" and (e.detail or {}).get("action") == "send" and e.to_place == place)
        if here and e.item_id not in seen:
            seen.append(e.item_id)
    return seen


def _made_up_id(world: world_mod.World, choices: J, state: J) -> str:
    """A handover id for a line the bench adds, numbered like a real one: it counts on after the run's last real handover
    (the id shows nothing that tells a forged line from a real one)."""
    if "base" not in state:
        prefix = world.run_id + "#"
        nums = [int(e.handover_id[len(prefix):]) for e in world_mod.truth_of(world)
                if e.handover_id and e.handover_id.startswith(prefix) and e.handover_id[len(prefix):].isdigit()]
        state["base"] = max(nums) if nums else 0
    state["n"] = state.get("n", 0) + 1
    return choices["bench_plan"]["made_up_handover_id"].format(run_id=world.run_id, n=state["base"] + state["n"])


def _claim_position(log: List[J], duty: J) -> int:
    """Where the line of a deletion that did not happen would stand: just after the line of the move the duty
    follows (or, for a duty that follows a step, after that step's last line); at the end when there is none."""
    if "after" in duty:
        hits = [i for i, x in enumerate(log) if x.get("move_id") == duty["after"]]
    else:
        hits = [i for i, x in enumerate(log) if x.get("step") == duty.get("after_step")]
    return (hits[-1] + 1) if hits else len(log)


def apply_false_log(own_log: List[J], fault: Optional[J], world: world_mod.World, wiring: Optional[J] = None,
                    choices: Optional[J] = None) -> List[J]:
    """Change, drop or add lines of the own log, for each false_log operation. Without a mode: change (or, with
    change null, drop) the first matching send line. Mode claim_delete: add the line of the deletion of `duty` as if
    it had happened (the deletion itself is not carried out: a skip_delete stands beside it). Mode add: insert a send
    line at `position` (counting the intake lines) for a handover that never happened."""
    log = [dict(x) for x in own_log]
    made = {}
    for op in (fault or {}).get("ops") or []:
        if op.get("op") != "false_log":
            continue
        mode = op.get("mode")
        if mode in FALSE_LOG_MODES:
            if choices is None:
                raise ContractError("false_log mode %s needs the choices" % mode)
            if mode == "claim_delete":
                duty = next((d for d in (wiring or _read_wiring())["plumbing"]["duties"] if d["id"] == op["duty"]), None)
                if duty is None:
                    raise ContractError("claim_delete: no duty %r in the wiring" % (op["duty"],))
                kind, frm, to, step, move = duty["kind"], duty["place"], None, "janitor", duty["id"]
                pos = _claim_position(log, duty)
                action = "delete"
            else:
                kind, frm, to, step, move = op["kind"], op["from"], op["to"], op["step"], None
                pos = min(op["position"], len(log))
                action = "send"
            line = {"run_id": world.run_id, "t": log[pos - 1]["t"] if pos > 0 and "t" in log[pos - 1] else 0,
                    "step": step, "action": action, "kind": kind, "from": frm, "to": to,
                    "item_ids": _item_ids_at(world, kind, frm), "move_id": move,
                    "handover_id": _made_up_id(world, choices, made)}
            log.insert(pos, line)
            world_mod.emit(world, "edited", step=step, fault_id=fault["fault_id"],
                           detail={"where": "own_log", "position": pos, "field": "line", "mode": mode})
            continue
        for pos, line in enumerate(log):
            if line.get("step") == op["step"] and line.get("kind") == op["kind"] and line.get("action") == "send":
                break
        else:
            continue
        if op.get("change") is None:
            del log[pos]
            fields = ["line"]
        else:
            fields = sorted(op["change"])
            for k in fields:
                log[pos][k] = op["change"][k]
        for k in fields:
            world_mod.emit(world, "edited", step=op["step"], fault_id=fault["fault_id"],
                           detail={"where": "own_log", "position": pos, "field": k})
    return log


def _set_field(obj: J, field: str, value: Any) -> None:
    parts = field.split(".")
    for p in parts[:-1]:
        obj = obj[p]
    obj[parts[-1]] = value


def _added_entry(op: J, lines: List[J], where: str, world: world_mod.World, choices: J, made: J) -> J:
    """The stored line an edit_record of mode add inserts at op['position']."""
    pos = min(op["position"], len(lines))
    before = lines[pos - 1] if pos > 0 else None
    t = (before or {}).get("t", 0)
    hid = _made_up_id(world, choices, made)
    ids = _item_ids_at(world, op["kind"], op["from"])
    if where == "own_log":
        return {"run_id": world.run_id, "t": t, "step": op["step"], "action": "send", "kind": op["kind"],
                "from": op["from"], "to": op["to"], "item_ids": ids, "move_id": None, "handover_id": hid}
    from custody import journal as journal_mod  # the record's own fingerprint (the journal is the checker's file)
    rec = {"run_id": world.run_id, "seq": pos, "t": t, "prev_fp": (before or {}).get("fp", ""),
           "decision": choices["bench_plan"]["added_record"]["decision"], "labels": [], "verdicts": [],
           "receipt": None,
           "handover": {"action": "send", "step": op["step"], "from_place": op["from"], "to_place": op["to"],
                        "kind": op["kind"], "item_ids": ids, "handover_id": hid, "move_id": None,
                        "run_id": world.run_id, "t": t}}
    rec["fp"] = journal_mod.record_fingerprint(rec)
    return rec


def edit_lines(lines: List[J], fault: Optional[J], where: str, world: world_mod.World,
               choices: Optional[J] = None) -> List[J]:
    """Apply each edit_record operation to a list of stored lines (own log or journal). Without a mode the operation
    sets one field of the line at `position`; mode drop deletes that line; mode add inserts a line for a handover that
    never happened (the checker's record keeps its seq, prev_fp and fp as they are, so the witness check fails)."""
    out = [copy.deepcopy(x) for x in lines]
    made: J = {}
    for op in (fault or {}).get("ops") or []:
        if op.get("op") != "edit_record":
            continue
        pos = op["position"]
        mode = op.get("mode")
        if mode == "add":
            if choices is None:
                raise ContractError("edit_record mode add needs the choices")
            entry = _added_entry(op, out, where, world, choices, made)
            pos = min(pos, len(out))
            out.insert(pos, entry)
            field = "line"
        elif mode == "drop":
            if pos >= len(out):
                continue
            del out[pos]
            field = "line"
        else:
            if pos >= len(out):
                continue
            _set_field(out[pos], op["field"], op["value"])
            field = op["field"]
        world_mod.emit(world, "edited", fault_id=fault["fault_id"],
                       detail={"where": where, "position": pos, "field": field})
    return out
