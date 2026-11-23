"""The courier of each method: plain (A), watched (A+) and the gate (B and C).

B and C are one class. The gate reads the condition only to look up
choices["conditions"][condition]["courier"] and ["labels"]. Nothing here reads
the hidden record of the test bench.
"""
from dataclasses import asdict
from typing import Callable, Dict, List, Optional, Tuple

from custody.core import (ContractError, Handover, Item, J, LedgerError, Label,
                          Record, Signal)
from custody.labels import derive_label, moved_label, seed_label
from custody.rules import check_handover
from custody.watch import Watcher


class PlainCourier:
    """Delivers whatever is asked. Raises no signal and keeps no label."""

    def __init__(self, run_id: str, deliver: Callable):
        self.run_id = run_id
        self._deliver = deliver
        self.signals: List[Signal] = []

    def admit(self, item: Item, place: str, t: int, facts: J) -> None:
        return None

    def made(self, item: Item, place: str, t: int, step: str, parents: List[Item]) -> None:
        return None

    def send(self, h: Handover, items: List[Item]) -> bool:
        self._deliver(h, items)
        return True

    def close(self, t: int) -> None:
        return None


class WatchedCourier(PlainCourier):
    """The plain courier with a watcher that reads each send and only flags."""

    def __init__(self, run_id: str, deliver: Callable, watcher: Watcher):
        super().__init__(run_id, deliver)
        self.watcher = watcher

    def send(self, h: Handover, items: List[Item]) -> bool:
        self.signals.extend(self.watcher.look(h, items))
        self._deliver(h, items)
        return True


class GateCourier:
    """Holds a label for each place and item, checks every handover, writes the
    record, and only then delivers unless it blocks."""

    def __init__(self, run_id: str, wiring: J, choices: J, deliver: Callable, ledger):
        if ledger is None:
            raise ContractError("the gate needs a ledger")
        self.run_id = run_id
        self.wiring = wiring
        self.choices = choices
        self._deliver = deliver
        self.ledger = ledger
        self.signals: List[Signal] = []
        self.labels: Dict[Tuple[str, str], Label] = {}
        self._reported = set()
        self._kinds: Dict[str, str] = {}
        guards = choices["guards"]
        self.gate_on_send = guards["gate_on_send"]
        self.record_first = guards["record_first"]
        self.response = {int(k): v for k, v in choices["gate"]["response"].items()}

    # ------------------------------------------------------------ labels
    def admit(self, item: Item, place: str, t: int, facts: J) -> None:
        self._kinds[item.item_id] = item.kind
        self.labels[(place, item.item_id)] = seed_label(item, place, t, facts, self.wiring, self.choices)

    def made(self, item: Item, place: str, t: int, step: str, parents: List[Item]) -> None:
        self._kinds[item.item_id] = item.kind
        label = derive_label(item, place, t, [(p, self.labels.get((place, p.item_id))) for p in parents],
                             self.wiring, self.choices)
        if label is not None:
            self.labels[(place, item.item_id)] = label

    # ------------------------------------------------------------ rule 2 scan
    def _overdue(self, t: int) -> List[J]:
        found = []
        for (place, item_id), label in sorted(self.labels.items()):
            if label.delete_by is not None and t > label.delete_by and (place, item_id) not in self._reported:
                found.append({"place": place, "item_id": item_id, "delete_by": label.delete_by,
                              "kind": self._kinds.get(item_id, "copy")})
        return found

    # ------------------------------------------------------------ send / close
    def send(self, h: Handover, items: List[Item]) -> bool:
        for i in items:
            self._kinds[i.item_id] = i.kind
        labels = {i.item_id: self.labels.get((h.from_place, i.item_id)) for i in items}
        overdue = self._overdue(h.t) if h.action == "send" else []
        for o in overdue:
            self._reported.add((o["place"], o["item_id"]))
        # a copy past its deadline is reported once: a delete of a copy already reported is not judged again
        judged = {k: (None if (h.action == "delete" and (h.from_place, k) in self._reported) else v)
                  for k, v in labels.items()}
        verdicts = check_handover(h, items, judged, overdue, self.wiring, self.choices)
        if h.action == "delete":
            for item in items:
                lab = labels[item.item_id]
                if lab is not None and lab.delete_by is not None and h.t > lab.delete_by:
                    self._reported.add((h.from_place, item.item_id))
        broken = [v for v in verdicts if v["verdict"] == "broken"]
        blocked = (self.gate_on_send and h.action == "send"
                   and any(self.response[v["rule"]] == "block" for v in broken))
        decision = "block" if blocked else ("flag" if broken else "deliver")
        extra: List[Signal] = []

        def write() -> bool:
            record = Record(seq=0, run_id=self.run_id, t=h.t, handover=asdict(h),
                            labels=[asdict(l) for l in labels.values() if l is not None],
                            verdicts=[{"rule": v["rule"], "verdict": v["verdict"], "reason": v["reason"]}
                                      for v in verdicts],
                            decision=decision, prev_fp="", fp="", receipt=None)
            self.ledger.write(record)
            return True

        delivered = False
        if self.record_first:
            try:
                write()
            except LedgerError as err:
                if h.action == "send":
                    blocked, decision = True, "block"
                extra.append(self._signal(h, 3, "block" if blocked else "flag", [i.item_id for i in items],
                                          "the record could not be written: %s" % (err,)))
            if not blocked:
                self._move(h, items)
                delivered = True
        else:
            if not blocked:
                self._move(h, items)
                delivered = True
            try:
                write()
            except LedgerError as err:
                extra.append(self._signal(h, 3, "flag", [i.item_id for i in items],
                                          "the record could not be written: %s" % (err,)))
        level = "block" if blocked else "flag"
        for v in broken:
            self.signals.append(self._signal(h, v["rule"], level, v["item_ids"] or [i.item_id for i in items],
                                             v["reason"]))
        self.signals.extend(extra)
        return delivered

    def _signal(self, h: Handover, rule: int, level: str, item_ids: List[str], reason: str) -> Signal:
        return Signal(run_id=self.run_id, t=h.t, rule=rule, level=level, by="gate",
                      handover_id=h.handover_id, item_ids=list(item_ids), reason=reason)

    def _move(self, h: Handover, items: List[Item]) -> None:
        self._deliver(h, items)
        for item in items:
            if h.action == "send":
                src = self.labels.get((h.from_place, item.item_id))
                if src is not None and (h.to_place, item.item_id) not in self.labels:
                    self.labels[(h.to_place, item.item_id)] = moved_label(
                        src, h.to_place, h.kind, h.t, self.wiring, self.choices)
            else:
                self.labels.pop((h.from_place, item.item_id), None)

    def close(self, t: int) -> None:
        overdue = self._overdue(t)
        for o in overdue:
            self._reported.add((o["place"], o["item_id"]))
        verdicts = []
        for rule in self.choices["guards"]["rules_checked"]:
            if rule == 2 and overdue:
                reason = "; ".join("%s at %s is past its deadline %d" % (o["kind"], o["place"], o["delete_by"])
                                   for o in overdue)
                verdicts.append({"rule": 2, "verdict": "broken", "reason": reason})
            else:
                verdicts.append({"rule": rule, "verdict": "na", "reason": ""})
        decision = "flag" if overdue else "deliver"
        record = Record(seq=0, run_id=self.run_id, t=t, handover={"action": "close", "t": t}, labels=[],
                        verdicts=verdicts, decision=decision, prev_fp="", fp="", receipt=None)
        try:
            self.ledger.write(record)
        except LedgerError as err:
            self.signals.append(Signal(run_id=self.run_id, t=t, rule=3, level="flag", by="gate",
                                       handover_id=None, item_ids=[], reason="the record could not be written: %s" % (err,)))
        if overdue:
            self.signals.append(Signal(run_id=self.run_id, t=t, rule=2, level="flag", by="gate",
                                       handover_id=None, item_ids=[o["item_id"] for o in overdue],
                                       reason=verdicts[[v["rule"] for v in verdicts].index(2)]["reason"]))


def make_courier(condition: str, wiring: J, choices: J, deliver: Callable, ledger, ai, run_id: str):
    """The courier for a condition. The condition is read only to look up the
    courier kind and the labels switch in the choices."""
    try:
        spec = choices["conditions"][condition]
    except KeyError:
        raise ContractError("unknown condition: %r" % (condition,))
    kind, labels = spec["courier"], spec["labels"]
    if kind == "plain":
        return PlainCourier(run_id, deliver)
    if kind == "watched":
        return WatchedCourier(run_id, deliver, Watcher(wiring, choices, ai, run_id))
    if kind == "gate" and labels:
        return GateCourier(run_id, wiring, choices, deliver, ledger)
    raise ContractError("the choices name no courier of kind %r with labels %r" % (kind, labels))
