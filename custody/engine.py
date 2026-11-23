"""The engine: walks the wiring for one visit.

Order of work: intake, each lane's steps, then close. Every send or delete
ticks, is told to the world, then goes to the courier (or straight to the world
when its move skips the gate). A rare event swaps a move or a duty for its
detour. At close the clock passes every deadline and each duty runs once more.
"""
from typing import Any, Dict, List, Optional

from custody.core import Handover, Item, J, LANE_OF, StepContext, Visit, make_item_id


def _longest_hold(choices: J) -> int:
    holds = [v for v in choices["holds"].values() if isinstance(v, int) and not isinstance(v, bool)]
    return max(holds) if holds else 0


def _intake_text(visit: Visit, kind: str) -> str:
    if kind == "transcript":
        return visit.conversation
    if kind == "question":
        return visit.question
    if kind == "answer":
        if visit.answer_text is None:
            raise ValueError("the case has no answer text to take in (the bench composes it first)")
        return visit.answer_text
    raise ValueError("no intake text for kind %r" % (kind,))


def _intake_facts(visit: Visit, kind: str) -> Dict[str, Any]:
    if kind == "transcript":
        return {"source": [visit.conversation_id], "certainty": None, "ai_made": False}
    if kind == "question":
        return {"source": [visit.question_id], "certainty": None, "ai_made": False}
    if kind == "answer":
        if visit.given_answer is not None:
            source = ["tool:%s" % visit.given_by]
        else:
            source = [e["source_id"] for e in visit.evidence]
        return {"source": source, "certainty": visit.expert_certainty, "ai_made": True}
    raise ValueError("no intake facts for kind %r" % (kind,))


class _Run:
    def __init__(self, visit, wiring, steps, ai, courier, world, events, choices, run_id):
        self.visit = visit
        self.plumbing = wiring["plumbing"]
        self.steps = steps
        self.ai = ai
        self.courier = courier
        self.world = world
        self.choices = {k: v for k, v in choices.items() if k != "witness"}  # steps never see the witness key
        self.run_id = run_id
        self.pending = [dict(e) for e in (events or [])]
        self.n = 0
        self.log: List[J] = []
        self.skipped: List[J] = []
        self.moves = {m["id"]: m for m in self.plumbing["moves"]}
        self.specs = {s["id"]: s for s in self.plumbing["steps"]}
        self.detours = list(self.plumbing.get("detours", []))
        # Version 2: a case of experiment 1 runs the words lane, one of experiment 2 the advice lane. Only that lane's
        # inputs are taken in and only its steps, moves, duties and detours run. Experiment 0 (an old joined visit) runs all.
        lane = LANE_OF.get(visit.experiment)
        self.lanes_run = [ln for ln in self.plumbing["lanes"] if lane is None or ln["id"] == lane]
        self.lane_steps = {s for ln in self.lanes_run for s in ln["steps"]}
        self.lane_reads = {k for s in self.lane_steps for k in self.specs[s]["reads"]}
        self.lane_moves = {m["id"] for m in self.plumbing["moves"] if m["step"] in self.lane_steps}
        self.lane_duties = {d["id"] for d in self.plumbing["duties"]
                            if d.get("after") in self.lane_moves or d.get("after_step") in self.lane_steps}
        self.detours = [d for d in self.detours if d["at"] in self.lane_moves | self.lane_duties]
        self.answer_text: Optional[str] = None  # the case's first advice text, for the review

    # ------------------------------------------------------------- helpers
    def _copies(self, place: str, kind: str) -> List[Item]:
        return [c for c in self.world.copies(place) if c.kind == kind]

    def _context(self, step: str, place: str, t: int, spec: J, duty: Optional[str]) -> StepContext:
        return StepContext(visit=self.visit, step=step, place=place, t=t, ai=self.ai,
                           spec=spec, choices=self.choices, duty=duty)

    def _handover(self, action, step, kind, from_place, to_place, items, move_id,
                  via_gate=True, logged=True) -> bool:
        t = self.world.tick()
        self.n += 1
        h = Handover(handover_id="%s#%d" % (self.run_id, self.n), run_id=self.run_id, t=t,
                     action=action, step=step, from_place=from_place, to_place=to_place,
                     kind=kind, item_ids=[i.item_id for i in items], move_id=move_id)
        if via_gate and logged:
            self.log.append({"run_id": self.run_id, "t": t, "step": step, "action": action,
                             "kind": kind, "from": from_place, "to": to_place,
                             "item_ids": list(h.item_ids), "move_id": move_id,
                             "handover_id": h.handover_id})
        self.world.asked(h, items)
        if via_gate:
            return bool(self.courier.send(h, items))
        self.world.deliver(h, items)
        return True

    # -------------------------------------------------------- moves, duties
    def _take_event(self, at: str) -> Optional[J]:
        for event in self.pending:
            if event.get("used") or event.get("at") != at:
                continue
            for detour in self.detours:
                if detour["on"] == event.get("on") and detour["at"] == at:
                    event["used"] = True
                    self.world.note("event", {"on": detour["on"], "at": at, "detour": detour["id"]})
                    return detour
        return None

    def _move(self, move: J) -> bool:
        copies = self._copies(move["from"], move["kind"])
        if not copies:
            return False
        return self._handover("send", move["step"], move["kind"], move["from"], move["to"],
                              copies, move["id"], via_gate=move.get("via_gate", True))

    def _delete_copies(self, kind: str, place: str, duty: str, spec: J, move_id: str) -> None:
        copies = self._copies(place, kind)
        if not copies:
            return
        ctx = self._context("janitor", place, self.world.now(), spec, duty)
        out = self.steps["janitor"](ctx, list(copies))
        by_id = {c.item_id: c for c in copies}
        for item_id in out.deletes:
            if item_id in by_id:
                self._handover("delete", "janitor", kind, place, None, [by_id[item_id]], move_id)

    def _run_detour(self, detour: J) -> bool:
        delivered = False
        for action in detour["do"]:
            if "send" in action:
                move = self.moves[action["send"]]
                ok = self._move(move)
                if move["id"] == detour["at"] and ok:
                    delivered = True
            elif "delete" in action:
                kind, place = action["delete"]
                self._delete_copies(kind, place, detour["id"], detour, detour["id"])
        return delivered

    def _run_move(self, move: J) -> bool:
        detour = self._take_event(move["id"])
        if detour is not None:
            return self._run_detour(detour)
        return self._move(move)

    def _run_duty(self, duty: J) -> None:
        detour = self._take_event(duty["id"])
        if detour is not None:
            self._run_detour(detour)
            return
        self._delete_copies(duty["kind"], duty["place"], duty["id"], duty, duty["id"])

    # ------------------------------------------------------------- the visit
    def intake(self) -> None:
        for entry in self.plumbing["intake"]:
            kind = entry["kind"]
            if kind not in self.lane_reads:
                continue
            text = _intake_text(self.visit, kind)
            item = Item(item_id=make_item_id(self.visit.visit_id, kind, "intake", text),
                        visit_id=self.visit.visit_id, kind=kind, text=text,
                        made_by="intake", parents=[])
            self.world.put(entry["place"], item, "intake")
            if kind == "answer" and self.answer_text is None:
                self.answer_text = text  # the case's first advice text, for the review
            # the system's own log records the arrival of each raw input (Version 2, part 2)
            self.log.append({"run_id": self.run_id, "t": 0, "step": "intake", "action": "intake",
                             "kind": kind, "place": entry["place"], "item": item.item_id})
            self.courier.admit(item, entry["place"], 0, _intake_facts(self.visit, kind))

    def _requests(self, step_id: str, place: str, requests: List[J]) -> None:
        for req in requests:
            kind = req.get("kind")
            copies = self._copies(place, kind) if kind else []
            if not copies:
                self.skipped.append({"step": step_id, "why": "request dropped, no copy held",
                                     "op": req.get("op"), "kind": kind})
                continue
            if req.get("op") == "send":
                self._handover("send", step_id, kind, place, req["to"], copies, None,
                               logged=bool(req.get("logged", True)))
            elif req.get("op") == "keep":
                for c in copies:
                    made_by = "keep:%s" % step_id
                    self.world.keep(place, Item(
                        item_id=make_item_id(c.visit_id, kind, made_by, c.text),
                        visit_id=c.visit_id, kind=kind, text=c.text, made_by=made_by,
                        parents=[c.item_id]))

    def lanes(self) -> None:
        for lane in self.lanes_run:
            for step_id in lane["steps"]:
                spec = self.specs[step_id]
                place = spec["place"]
                inbox = [c for c in self.world.copies(place) if c.kind in spec["reads"]]
                missing = [k for k in spec["reads"] if not any(c.kind == k for c in inbox)]
                if missing:
                    self.skipped.append({"step": step_id, "why": "missing input", "kinds": missing})
                    continue
                t = self.world.tick()
                out = self.steps[step_id](self._context(step_id, place, t, spec, None), list(inbox))
                for item in out.items:
                    self.world.put(place, item, step_id)
                    self.courier.made(item, place, t, step_id, list(inbox))
                self._requests(step_id, place, out.requests)
                for move in self.plumbing["moves"]:
                    if move["step"] != step_id or move.get("detour_only"):
                        continue
                    if self._run_move(move):
                        for duty in self.plumbing["duties"]:
                            if duty.get("after") == move["id"]:
                                self._run_duty(duty)
                # a duty that names this step runs once the step has run and made its item (version 3)
                for duty in self.plumbing["duties"]:
                    if duty.get("after_step") == step_id:
                        self._run_duty(duty)

    def close(self) -> None:
        self.world.tick()
        self.world.advance(_longest_hold(self.choices) + 1)
        for duty in self.plumbing["duties"]:
            if duty["id"] in self.lane_duties and self._copies(duty["place"], duty["kind"]):
                self._delete_copies(duty["kind"], duty["place"], "late:" + duty["id"], duty, duty["id"])
        self.courier.close(self.world.now())

    def final(self) -> J:
        out: J = {}
        final_at = self.plumbing.get("final") or {}
        for kind in ("note", "patient_note"):
            copies = self._copies(final_at.get(kind, "patient"), kind)
            out[kind] = copies[0].text if copies else None
        out["ai_answer"] = self.answer_text
        return out


def run_visit(visit, wiring, steps, ai, courier, world, events, choices, run_id):
    """Run one visit; returns {own_log, final, skipped}.

    The visit and the choices arrive as the caller wants the steps to see them."""
    run = _Run(visit, wiring, steps, ai, courier, world, events, choices, run_id)
    run.intake()
    run.lanes()
    run.close()
    return {"own_log": run.log, "final": run.final(), "skipped": run.skipped}
