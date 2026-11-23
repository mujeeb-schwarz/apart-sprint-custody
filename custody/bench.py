"""The test bench: one run of one visit under one condition, and a batch of runs.

Everything another builder supplies arrives in `parts` (steps, ai,
recording_ai, run_visit, make_courier, review, make_ledger, build_receipt,
check_receipt, prove). Nothing is imported across builders.

Hidden record: the truth events and the fault plan stay in this module's
reach. The engine, courier, review, ledger and receipt builder get a copy of
the choices without the key "faults"; the engine, courier, review and receipt
builder also get no "witness"; the engine gets a visit already blanked of
what is true.
"""
import copy
import dataclasses
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from custody import faults as faults_mod
from custody import store
from custody import world as world_mod
from custody.core import (AICallMissing, CustodyError, J, RunResult, SALT_FIELD, Signal, Visit, canon)
from custody.world import World

ROOT = Path(__file__).resolve().parents[1]
NOT_RUN = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}


HIDDEN_FROM_METHODS = ("faults", "planting", "bench_plan")


def run_choices(choices: J) -> J:
    """A copy of the choices without the keys faults, planting and bench_plan (what the methods hold: the test
    wordings of the hidden line, the plan's counts and the planting wordings are the bench's own; fix round, item 6)."""
    return {k: copy.deepcopy(v) for k, v in choices.items() if k not in HIDDEN_FROM_METHODS}


def hidden_lines_of(choices: J) -> J:
    """The test split's wordings of the hidden line, for the stand-in AI only (assemble.make_parts hidden_lines)."""
    p = choices.get("planting") or {}
    return {"transcript": list(p.get("inject_texts_test", [])), "answer": list(p.get("certainty_texts_test", []))}


def _public_choices(choices: J) -> J:
    """The run choices without the witness key too: what the chain and the gate may see."""
    return {k: v for k, v in run_choices(choices).items() if k != "witness"}


def _witness_key(choices: J) -> bytes:
    w = choices["witness"]
    if w.get("use") == "key_file":
        return bytes.fromhex((ROOT / w["key_file"]).read_text(encoding="utf-8").strip())
    return bytes.fromhex(w["test_key_hex"])


def _blank(visit: Visit) -> Visit:
    return dataclasses.replace(visit, expert_answer=None, split="", matched=False, meta={}, clean_of=None)


def _as_dict(rec: Any) -> J:
    return asdict(rec) if dataclasses.is_dataclass(rec) else dict(rec)


class _LedgerTap:
    """What the courier sees of the ledger: write and records only."""

    def __init__(self, write: Any, records: Any):
        self.write = write
        self.records = records


def _tap_ledger(inner: Any, world: World) -> _LedgerTap:
    def write(record: Any) -> Any:
        filled = inner.write(record)
        rec = _as_dict(filled)
        h = rec.get("handover") or {}
        world_mod.emit(world, "recorded", step=h.get("step", ""), place=h.get("from_place"),
                       to_place=h.get("to_place"), handover_id=h.get("handover_id"),
                       detail={"seq": rec.get("seq"), "fp": rec.get("fp")})
        return filled
    return _LedgerTap(write, lambda: [r for r in inner.records()])


def _salted(inner: Any, salt: str, unsalted: Any = ()) -> Any:
    """The AI with a salt in every call's fields, except the prompts in `unsalted` (the steps before a planted one)."""
    def ai(prompt_id: str, fields: J) -> str:
        if prompt_id in unsalted:
            return inner(prompt_id, fields)
        return inner(prompt_id, dict(fields, **{SALT_FIELD: salt}))
    return ai


def _steps_before(visit: Visit, step: str, wiring: J, choices: J) -> List[str]:
    """The prompt ids of the AI steps that run before `step` in the visit's lane."""
    from custody.core import LANE_OF
    out: List[str] = []
    specs = {s["id"]: s for s in wiring["plumbing"]["steps"]}
    for lane in wiring["plumbing"]["lanes"]:
        if lane["id"] != LANE_OF.get(visit.experiment):
            continue
        for sid in lane["steps"]:
            if sid == step:
                return out
            if specs[sid].get("prompt"):
                out.append(choices["prompts"][specs[sid]["prompt"]])
    return out


def _review_choices(rchoices: J, cond: J, choices: J) -> J:
    """The choices the review is built from. Part 3 (13 Nov): under a method whose signals_counted does not hold
    "review", the review's AI part is switched off for that unit (its program part still runs), so no call is made,
    exported or answered for a result the scorer would never read. Driven by the config, never by a method's name."""
    if choices.get("bench_plan", {}).get("skip_uncounted_review_ai") and "review" not in cond["signals_counted"]:
        return dict(rchoices, ai_parts=dict(rchoices.get("ai_parts") or {}, on=False))
    return rchoices


def _promise_view(wiring: J) -> J:
    return {"promise": wiring["promise"]}


def run_one(visit: Visit, condition: str, fault: Optional[J], parts: J, wiring: J, choices: J,
            run_dir: Any, rep: int = 0) -> RunResult:
    started = time.perf_counter()
    run_dir = Path(str(run_dir))
    run_id = "%s.%s.r%d" % (visit.visit_id, condition, rep)
    rchoices = _public_choices(choices)
    cond = choices["conditions"][condition]
    if fault and fault.get("fault_record") and cond.get("labels"):
        fault = fault["fault_record"]  # version 3: a rule 3 violation is done to the record the method relies on

    # 1. patch the wiring
    if fault:
        faults_mod.check_fault(fault, wiring, choices)
    patched = faults_mod.apply_patch(wiring, (fault or {}).get("patch") or [])

    # 2. proof, under C
    proof = dict(NOT_RUN)
    proof_signals: List[Signal] = []
    used = patched
    if cond.get("prove_first"):
        proof = parts["prove"](patched)
        ce = proof.get("counterexample")
        if proof.get("status") == "counterexample" and ce:
            proof_signals.append(Signal(run_id=run_id, t=-1, rule=int(ce.get("rule", 0)), level="block",
                                        by="proof", handover_id=None, item_ids=[],
                                        reason="proof: rule %s, property %s" % (ce.get("rule"), ce.get("property"))))
            used = copy.deepcopy(wiring)
    result_proof = proof["status"] if cond.get("prove_first") else "none"

    # 3. world, ledger, courier
    world = World(run_id, used, run_choices(choices))
    if fault:
        for mid in faults_mod.changed_ids(wiring, patched):
            world_mod.tag_move(world, mid, fault["fault_id"])
        for ev in fault.get("events") or []:
            world_mod.tag_event(world, ev["on"], ev["at"], fault["fault_id"])
        if fault.get("patch"):
            world_mod.emit(world, "event", fault_id=fault["fault_id"],
                           detail={"fault_op": "patch", "paths": [p["path"] for p in fault["patch"]]})
    sink: List[J] = []
    set_grade = getattr(parts["ai"], "set_visit_grade", None)  # the canned AI alone has it
    if set_grade is not None:
        set_grade(visit.expert_certainty)
    inner_ai = parts["ai"]
    salt = (visit.meta.get("unit") or {}).get("salt")
    if salt:  # the repeat check: every AI call of this unit is asked afresh (the salt is in the call id, never in a prompt)
        before = _steps_before(visit, visit.meta["unit"]["salt_from"], used, choices) if visit.meta["unit"].get("salt_from") else ()
        inner_ai = _salted(parts["ai"], salt, before)
    ai = parts["recording_ai"](inner_ai, sink)
    ledger = None
    tap = None
    if cond.get("labels"):
        ledger = parts["make_ledger"](run_dir, run_id, run_choices(choices))
        tap = _tap_ledger(ledger, world)
    view = _promise_view(used)
    courier = parts["make_courier"](condition, view, rchoices,
                                    lambda h, items: world.deliver(h, items), tap, ai, run_id)

    # 4. steps and visit
    # the wrappers are the bench's own: they read the fault settings from the full choices
    steps = faults_mod.wrap_steps(parts["steps"], fault, world, used, choices)
    entering = visit
    compose = parts.get("compose_answer")
    if compose is not None and visit.answer_text is None and visit.experiment != 1:
        entering = dataclasses.replace(visit, answer_text=compose(visit, rchoices))  # version 3: the answer enters ready-made
    entering = faults_mod.apply_inject(entering, fault, world)
    entering = faults_mod.apply_entering_rewrites(entering, fault, world, used, choices)
    given = _blank(entering)

    crashed = False
    own_log: List[J] = []
    final: J = {"note": None, "patient_note": None}
    review_signals: List[Signal] = []
    ledger_signals: List[Signal] = []
    receipt_ok: Optional[bool] = None
    crash_note = None
    try:
        # 5. the engine
        events = [dict(e) for e in (fault or {}).get("events") or []]
        out = parts["run_visit"](given, used, steps, ai, courier, world, events, rchoices, run_id)
        own_log = faults_mod.apply_false_log(list(out["own_log"]), fault, world, used, choices)
        final = out["final"]
        own_log = [dict(x) for x in own_log]
        for line in own_log:
            line.setdefault("run_id", run_id)

        # 6. the receipt
        records: List[J] = [_as_dict(r) for r in ledger.records()] if ledger is not None else []
        receipt = parts["build_receipt"](run_id, condition, records, proof, used, rchoices)
        store.write_json(store.run_path(run_dir, "receipts", run_id + ".json"), receipt)

        # 7. planted edits after the visit
        if condition in ("A", "A+"):
            own_log = faults_mod.edit_lines(own_log, fault, "own_log", world, choices)
        else:
            jpath = store.run_path(run_dir, "journal", run_id + ".jsonl")
            lines = store.read_jsonl(jpath)
            edited = faults_mod.edit_lines(lines, fault, "journal", world, choices)
            if edited != lines:
                store.write_jsonl(jpath, edited)

        # 8. the review, and the receipt check against the files read back
        review_signals = list(parts["review"](own_log, final, view, _review_choices(rchoices, cond, choices), ai, run_id))
        if ledger is not None:
            jrecs = store.read_jsonl(store.run_path(run_dir, "journal", run_id + ".jsonl"))
            wlog = store.read_jsonl(store.run_path(run_dir, "witness", "log.jsonl"))
            res = parts["check_receipt"](receipt, jrecs, wlog, _witness_key(choices))
            receipt_ok = bool(res["ok"])
            for problem in res["problems"]:
                ledger_signals.append(Signal(run_id=run_id, t=world.now(), rule=3, level="flag", by="ledger",
                                             handover_id=None, item_ids=[], reason=str(problem)))
    except AICallMissing:
        world_mod.release(world)
        raise
    except Exception as exc:  # a crash is a result, not a stop
        crashed = True
        crash_note = {"run_id": run_id, "error": type(exc).__name__, "message": str(exc)}

    # 9. store
    signals = proof_signals + list(courier.signals) + review_signals + ledger_signals
    texts = world_mod.made_of(world)
    produced = {"note": final.get("note") is not None, "patient_note": final.get("patient_note") is not None}
    counts = world_mod.counts_of(world)
    result = RunResult(
        run_id=run_id, visit_id=visit.visit_id, conversation_id=visit.conversation_id, condition=condition,
        rep=rep, split=visit.split, produced=produced, asked=counts["asked"], delivered=counts["delivered"],
        signals=len(signals), ai_calls=len(sink), proof=result_proof, receipt_ok=receipt_ok, crashed=crashed,
        experiment=visit.experiment)
    store.ensure_visit(run_dir, asdict(visit), fault)
    store.append_jsonl(store.run_path(run_dir, "results.jsonl"), [asdict(result)])
    store.append_jsonl(store.run_path(run_dir, "signals.jsonl"), [asdict(s) for s in signals])
    store.append_jsonl(store.run_path(run_dir, "ai_calls.jsonl"), [dict(row, run_id=run_id) for row in sink])
    store.append_jsonl(store.run_path(run_dir, "texts.jsonl"), texts)
    store.append_jsonl(store.run_path(run_dir, "own_log.jsonl"), own_log)
    store.append_jsonl(store.run_path(run_dir, store.HIDDEN, "truth.jsonl"),
                       [asdict(e) for e in world_mod.truth_of(world)])
    if crash_note:
        store.append_jsonl(store.run_path(run_dir, store.HIDDEN, "crashes.jsonl"), [crash_note])
    store.append_jsonl(store.run_path(run_dir, "timing.jsonl"),
                       [{"run_id": run_id, "seconds": round(time.perf_counter() - started, 6)}])
    world_mod.release(world)
    return result


_APPENDED = ("results.jsonl", "signals.jsonl", "ai_calls.jsonl", "texts.jsonl", "own_log.jsonl",
             "timing.jsonl", "witness/log.jsonl", "hidden/truth.jsonl", "hidden/crashes.jsonl")


def _snapshot(run_dir: Path) -> Dict[str, Optional[int]]:
    out: Dict[str, Optional[int]] = {}
    for rel in _APPENDED:
        p = Path(str(run_dir)) / rel
        out[rel] = p.stat().st_size if p.exists() else None
    return out


def _roll_back(run_dir: Path, snap: Dict[str, Optional[int]], run_id: str) -> None:
    """Undo what a crashed run wrote, so its retry leaves no trace of the first try."""
    root = Path(str(run_dir))
    for rel, size in snap.items():
        p = root / rel
        if not p.exists():
            continue
        if size is None:
            p.unlink()
        else:
            with open(str(p), "r+b") as fh:
                fh.truncate(size)
    for rel in ("journal/%s.jsonl" % run_id, "receipts/%s.json" % run_id):
        p = root / rel
        if p.exists():
            p.unlink()


def run_all(visits: List[Visit], conditions: List[str], plan: Dict[str, Optional[J]], parts: J, wiring: J,
            choices: J, run_dir: Any) -> List[RunResult]:
    """Every visit under every condition. A crashed run is retried once; a second crash stays recorded."""
    results = []
    for visit in visits:
        for condition in conditions:
            fault = plan.get(visit.visit_id)
            snap = _snapshot(Path(str(run_dir)))
            try:
                res = run_one(visit, condition, fault, parts, wiring, choices, run_dir)
                if res.crashed:
                    _roll_back(Path(str(run_dir)), snap, res.run_id)
                    res = run_one(visit, condition, fault, parts, wiring, choices, run_dir)
            except AICallMissing:
                _roll_back(Path(str(run_dir)), snap, "%s.%s.r0" % (visit.visit_id, condition))
                raise
            results.append(res)
    return results
