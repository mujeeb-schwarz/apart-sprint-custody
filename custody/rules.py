"""The six rules as checks against labels, for the gate (B and C).

One function checks one rule for one item of one handover and returns a
verdict (kept, broken, undecided or na) with a reason. check_handover joins
the items of a handover into one verdict for each rule.
"""
from typing import Dict, List, Optional, Tuple

from custody.core import (Handover, Item, J, Label, claim_level, has_ai_mark,
                          is_named, may_hold, normalise_id, sources_named, sources_unreadable)

Result = Tuple[str, str]  # (verdict, reason)
NA: Result = ("na", "")


def place_problem(wiring: J, place: Optional[str], kind: str) -> Optional[str]:
    """Why the promise does not let the place hold the kind, or None when it does."""
    if place is None or not is_named(wiring, place):
        return "place %s is not named" % (place,)
    if not may_hold(wiring, place, kind):
        return "place %s may not hold %s" % (place, kind)
    return None


def rule1(h: Handover, item: Item, label: Optional[Label], wiring: J, choices: J) -> Result:
    if h.action != "send":
        return NA
    problem = place_problem(wiring, h.to_place, h.kind)
    if problem is not None:
        return ("broken", problem)
    if label is not None and h.to_place not in label.allowed:
        return ("broken", "place %s is not in the label's allowed places" % (h.to_place,))
    return ("kept", "")


def rule2(h: Handover, item: Item, label: Optional[Label], wiring: J, choices: J) -> Result:
    """Only a delete is judged here; copies left past their deadline come from the scan."""
    if h.action != "delete" or label is None:
        return NA
    if label.delete_by is not None and h.t > label.delete_by:
        return ("broken", "%s at %s deleted at tick %d, after its deadline %d"
                % (h.kind, h.from_place, h.t, label.delete_by))
    return ("kept", "")


def rule3(h: Handover, item: Item, label: Optional[Label], wiring: J, choices: J) -> Result:
    if h.action != "send":
        return NA
    if label is None:
        return ("broken", "no label at %s: the item came by an unrecorded path" % (h.from_place,))
    return ("kept", "")


def _advice(h: Handover, item: Item, label: Optional[Label], choices: J) -> bool:
    return h.action == "send" and item.kind in choices["rules"]["advice_kinds"] and label is not None


def rule4(h: Handover, item: Item, label: Optional[Label], wiring: J, choices: J) -> Result:
    if not _advice(h, item, label, choices):
        return NA
    named = sources_named(item.text, choices)
    if not named and sources_unreadable(item.text, choices):
        return ("undecided", "a source id in the tag cannot be read")
    if not named:
        return ("broken", "the text names no source")
    held = {normalise_id(s) for s in label.source}
    outside = [s for s in named if s not in held]
    if outside:
        return ("broken", "the text names %s, which the label does not list" % "; ".join(outside))
    if sources_unreadable(item.text, choices):
        return ("undecided", "a source id in the tag cannot be read")
    return ("kept", "")


def rule5(h: Handover, item: Item, label: Optional[Label], wiring: J, choices: J) -> Result:
    if not _advice(h, item, label, choices) or label.certainty is None:
        return NA
    level = claim_level(item.text, choices)
    if level is None:
        return ("undecided", "the text has no claim line")
    if level == "undecided":
        return ("undecided", "the claim line holds a hedge the ladder does not list")
    if level != label.certainty:
        levels = choices["ladder"]["levels"]
        way = "hardened" if levels.index(level) > levels.index(label.certainty) else "softened"
        return ("broken", "the claim states %s where the label says %s (%s)" % (level, label.certainty, way))
    return ("kept", "")


def rule6(h: Handover, item: Item, label: Optional[Label], wiring: J, choices: J) -> Result:
    if not _advice(h, item, label, choices) or not label.ai_made:
        return NA
    if not has_ai_mark(item.text, choices):
        return ("broken", "the text carries no AI mark")
    return ("kept", "")


CHECKS = {1: rule1, 2: rule2, 3: rule3, 4: rule4, 5: rule5, 6: rule6}


def combine(per_item: List[Tuple[str, Result]]) -> Result:
    """One verdict from the item verdicts: broken beats undecided beats kept beats na."""
    for wanted in ("broken", "undecided", "kept"):
        hits = [(i, r) for i, (v, r) in per_item if v == wanted]
        if hits:
            reason = "; ".join(("item %s: %s" % (i, r)) if r else ("item %s" % i) for i, r in hits) \
                if wanted != "kept" else ""
            return (wanted, reason)
    return NA


def check_handover(h: Handover, items: List[Item], labels: Dict[str, Optional[Label]],
                   overdue: List[J], wiring: J, choices: J) -> List[J]:
    """One dict {rule, verdict, reason, item_ids} for each rule in guards.rules_checked.

    labels maps an item id to its label at h.from_place (None when it has none).
    overdue lists copies past their deadline that the gate found by its scan:
    {place, item_id, kind, delete_by}; they break rule 2 for this handover.
    """
    out: List[J] = []
    for rule in choices["guards"]["rules_checked"]:
        per_item: List[Tuple[str, Result]] = []
        for item in items:
            per_item.append((item.item_id, CHECKS[rule](h, item, labels.get(item.item_id), wiring, choices)))
        verdict, reason = combine(per_item)
        item_ids = [i for i, (v, _) in per_item if v == "broken"]
        if rule == 2 and overdue:
            extra = "; ".join("%s at %s is past its deadline %d" % (o["kind"], o["place"], o["delete_by"])
                              for o in overdue)
            verdict = "broken"
            reason = "; ".join(x for x in (reason, extra) if x)
            item_ids = item_ids + [o["item_id"] for o in overdue if o["item_id"] not in item_ids]
        out.append({"rule": rule, "verdict": verdict, "reason": reason, "item_ids": item_ids})
    return out
