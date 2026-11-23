"""The test bench's world: every copy of every item, the clock, and the hidden
truth record of everything that moves.

The truth is kept out of reach of anything handed to the chain: it does not
sit on the World object. It lives in this module's private table, and only the
bench reads it through the functions at the bottom (truth_of, made_of,
counts_of, emit, the tag_* functions and release).
"""
from dataclasses import asdict
from typing import Any, Dict, List, Optional

from custody.core import Handover, Item, J, TruthEvent


class _State:
    def __init__(self) -> None:
        self.events: List[TruthEvent] = []
        self.made: List[J] = []
        self.asked = 0
        self.delivered = 0
        self.request_tags: List[J] = []   # one-shot, matched on asked()
        self.keep_tags: List[J] = []      # one-shot, matched on keep()
        self.item_tags: Dict[str, str] = {}
        self.move_tags: Dict[str, str] = {}
        self.event_tags: List[J] = []
        self.handover_tags: Dict[str, str] = {}


_STATE: Dict[int, _State] = {}


def _st(world: "World") -> _State:
    return _STATE[id(world)]


class World:
    def __init__(self, run_id: str, wiring: J, choices: J):
        self.run_id = run_id
        self._clock = 0
        self._copies: Dict[str, Dict[str, Item]] = {}
        self._kept: Dict[str, List[Item]] = {}
        _STATE[id(self)] = _State()

    # ---------------------------------------------------------------- clock
    def now(self) -> int:
        return self._clock

    def tick(self) -> int:
        self._clock += 1
        return self._clock

    def advance(self, n: int) -> int:
        self._clock += int(n)
        return self._clock

    # --------------------------------------------------------------- copies
    def put(self, place: str, item: Item, step: str) -> None:
        held = self._copies.setdefault(place, {})
        if item.item_id not in held:
            held[item.item_id] = item
        s = _st(self)
        s.made.append({"run_id": self.run_id, "place": place, "t": self._clock, "item": asdict(item)})
        _emit(self, "made", step=step, place=place, item_id=item.item_id, detail={"kind": item.kind})

    def copies(self, place: str) -> List[Item]:
        """Declared copies only, in arrival order. A kept copy never shows here."""
        return list(self._copies.get(place, {}).values())

    def asked(self, h: Handover, items: List[Item]) -> None:
        s = _st(self)
        s.asked += 1
        fid = _match_request(s, h)
        if fid is None and h.move_id is not None:
            fid = s.move_tags.get(h.move_id)
        if fid is not None:
            s.handover_tags[h.handover_id] = fid
        for item in items:
            _emit(self, "asked", step=h.step, place=h.from_place, to_place=h.to_place, item_id=item.item_id,
                  handover_id=h.handover_id, fault_id=fid, detail={"action": h.action, "kind": h.kind}, t=h.t)

    def deliver(self, h: Handover, items: List[Item]) -> None:
        s = _st(self)
        s.delivered += 1
        fid = s.handover_tags.get(h.handover_id)
        for item in items:
            if h.action == "delete":
                self._copies.get(h.from_place, {}).pop(item.item_id, None)
            else:
                held = self._copies.setdefault(h.to_place, {})
                if item.item_id not in held:
                    held[item.item_id] = item
            _emit(self, "moved", step=h.step, place=h.from_place, to_place=h.to_place, item_id=item.item_id,
                  handover_id=h.handover_id, fault_id=fid, detail={"action": h.action, "kind": h.kind}, t=h.t)

    def keep(self, place: str, item: Item) -> None:
        s = _st(self)
        self._kept.setdefault(place, []).append(item)
        fid = None
        for tag in s.keep_tags:
            if item.made_by == "keep:" + tag["step"] and item.kind == tag["kind"]:
                fid = tag["fault_id"]
                s.keep_tags.remove(tag)
                break
        of = item.parents[0] if item.parents else None
        _emit(self, "kept", step=item.made_by, place=place, item_id=item.item_id, fault_id=fid,
              detail={"kind": item.kind, "of": of})

    def note(self, kind: str, detail: J) -> None:
        s = _st(self)
        fid = None
        for tag in s.event_tags:
            if tag["on"] == detail.get("on") and tag["at"] == detail.get("at"):
                fid = tag["fault_id"]
                break
        _emit(self, kind, step="", detail=dict(detail), fault_id=fid)


# ------------------------------------------------------------------ internals

def _match_request(s: _State, h: Handover) -> Optional[str]:
    if h.action != "send" or h.move_id is not None:
        return None
    for tag in s.request_tags:
        if tag["step"] == h.step and tag["kind"] == h.kind and tag["to"] == h.to_place:
            s.request_tags.remove(tag)
            return tag["fault_id"]
    return None


def _emit(world: World, kind: str, step: str = "", place: Optional[str] = None, to_place: Optional[str] = None,
          item_id: Optional[str] = None, handover_id: Optional[str] = None, fault_id: Optional[str] = None,
          detail: Optional[J] = None, t: Optional[int] = None) -> None:
    s = _st(world)
    if fault_id is None and item_id is not None:
        fault_id = s.item_tags.get(item_id)
    s.events.append(TruthEvent(
        seq=len(s.events), run_id=world.run_id, t=world.now() if t is None else t, kind=kind, step=step,
        place=place, to_place=to_place, item_id=item_id, handover_id=handover_id, fault_id=fault_id,
        detail=dict(detail or {})))


# --------------------------------------------------- bench-only functions
# The bench imports these. They are module functions so that no World object
# handed to the chain carries the truth or the tags.

def truth_of(world: World) -> List[TruthEvent]:
    return list(_st(world).events)


def made_of(world: World) -> List[J]:
    return list(_st(world).made)


def counts_of(world: World) -> Dict[str, int]:
    s = _st(world)
    return {"asked": s.asked, "delivered": s.delivered}


def emit(world: World, kind: str, step: str = "", place: Optional[str] = None, to_place: Optional[str] = None,
         item_id: Optional[str] = None, handover_id: Optional[str] = None, fault_id: Optional[str] = None,
         detail: Optional[J] = None) -> None:
    _emit(world, kind, step=step, place=place, to_place=to_place, item_id=item_id, handover_id=handover_id,
          fault_id=fault_id, detail=detail)


def tag_request(world: World, step: str, kind: str, to: str, fault_id: str) -> None:
    _st(world).request_tags.append({"step": step, "kind": kind, "to": to, "fault_id": fault_id})


def tag_keep(world: World, step: str, kind: str, fault_id: str) -> None:
    _st(world).keep_tags.append({"step": step, "kind": kind, "fault_id": fault_id})


def tag_item(world: World, item_id: str, fault_id: str) -> None:
    _st(world).item_tags[item_id] = fault_id


def tag_move(world: World, move_id: str, fault_id: str) -> None:
    _st(world).move_tags[move_id] = fault_id


def tag_event(world: World, on: str, at: str, fault_id: str) -> None:
    _st(world).event_tags.append({"on": on, "at": at, "fault_id": fault_id})


def release(world: World) -> None:
    _STATE.pop(id(world), None)
