"""Labels: the facts that travel beside a text, never inside it.

A label is made from the facts given at intake (admit) or from the labels of
the parents of a made item. It lives in the gate, keyed by place and item id.
"""
from dataclasses import replace
from typing import Dict, List, Optional, Tuple

from custody.core import (ContractError, Item, J, Label, hold_ticks)


def allowed_places(wiring: J, kind: str) -> List[str]:
    """Every place whose may_hold has the kind."""
    return [p["id"] for p in wiring["promise"]["places"] if kind in p.get("may_hold", {})]


def delete_by_for(wiring: J, choices: J, place: str, kind: str, arrival: int) -> Optional[int]:
    """Arrival plus the hold at the place, or None where the copy may stay."""
    ticks = hold_ticks(wiring, choices, place, kind)
    return None if ticks is None else arrival + ticks


def seed_label(item: Item, place: str, t: int, facts: J, wiring: J, choices: J) -> Label:
    """The label of an intake item, from the facts the engine hands to admit."""
    return Label(
        item_id=item.item_id,
        source=list(facts.get("source") or []),
        certainty=facts.get("certainty"),
        ai_made=bool(facts.get("ai_made")),
        allowed=allowed_places(wiring, item.kind),
        delete_by=delete_by_for(wiring, choices, place, item.kind, t),
    )


def lowest_grade(grades: List[Optional[str]], choices: J) -> Optional[str]:
    """The lowest level among the grades that are not None; None with no grade."""
    levels = choices["ladder"]["levels"]
    held = [g for g in grades if g is not None]
    if not held:
        return None
    for g in held:
        if g not in levels:
            raise ContractError("unknown certainty level: %r" % (g,))
    return min(held, key=levels.index)


def derive_label(item: Item, place: str, t: int,
                 parents: List[Tuple[Item, Optional[Label]]],
                 wiring: J, choices: J) -> Optional[Label]:
    """The label of a made item, from its parents' labels at the same place.

    Sources are the union of the parents' sources, leaving out a parent of kind
    question. Certainty is the lowest grade among the parents that have one.
    ai_made holds when any parent is AI-made, or when the item is of an advice
    kind (the gate cannot read the step's own flag; see docs/notes/GATE.md).
    A parent with no label leaves the new item without one, and so does having
    no parent at all.
    """
    if not parents or any(label is None for _, label in parents):
        return None
    sources: List[str] = []
    for parent, label in parents:
        if parent.kind == "question":
            continue
        for s in label.source:
            if s not in sources:
                sources.append(s)
    certainty = lowest_grade([label.certainty for _, label in parents], choices)
    ai_made = any(label.ai_made for _, label in parents) or item.kind in choices["rules"]["advice_kinds"]
    return Label(
        item_id=item.item_id,
        source=sources,
        certainty=certainty,
        ai_made=ai_made,
        allowed=allowed_places(wiring, item.kind),
        delete_by=delete_by_for(wiring, choices, place, item.kind, t),
    )


def moved_label(label: Label, to_place: str, kind: str, t: int, wiring: J, choices: J) -> Label:
    """The label of a copy that has arrived at to_place at tick t."""
    return replace(label, delete_by=delete_by_for(wiring, choices, to_place, kind, t))
