"""The watcher on the courier (condition A+) and the review after the visit.

Both only flag; neither blocks, changes or deletes anything. Both read the
promise part of the wiring and nothing else of it.
"""
import re
from typing import Dict, List, Optional

from custody.core import (ContractError, Handover, Item, J, Signal, canon, claim_level,
                          has_ai_mark, hold_ticks, sources_named, strip_lead)
from custody.rules import place_problem

# After strip_lead: FLAG, a number, closing markdown, an optional colon or dash, then the reason.
_FLAG_LINE = re.compile(r"^FLAG\s*(\d+)[*_`]*\s*(?:[:\-\u2013\u2014]\s*)?(.*?)\s*$", re.IGNORECASE)
_NO_FLAGS = "no flags"
_FLAG_WORD = re.compile(r"\bFLAG\s*\d", re.IGNORECASE)
_FLAG_RANGE = re.compile(r"^FLAG\s*\d+\s*[\-\u2013\u2014]\s*\d", re.IGNORECASE)  # FLAG 1-2: two rules in one line (J4)
_RULE_LISTED = re.compile(r"(?m)^\s*Rule (\d+):")


def prompt_rules(prompt: str) -> set:
    """The rule numbers a watcher or reviewer prompt lists (its lines that start `Rule <n>:`); empty when none."""
    return {int(n) for n in _RULE_LISTED.findall(prompt or "")}


def every_prompt_fields(choices: J) -> Dict[str, str]:
    """The three fields every prompt takes; the caller of ai() fills them."""
    markers = choices["markers"]
    return {"claim_marker": markers["claim"], "source_open": markers["source_tag"]["open"],
            "ai_mark": markers["ai"]}


NONE_IN_FLOW = "(none in this flow)"
NO_PREVIOUS_ADVICE = "(none: this is the first advice text)"


def ai_parts_on(choices: J) -> bool:
    """The switch for the AI parts of the review and the monitor (D: ai_parts.on); on when the key is absent."""
    return bool((choices.get("ai_parts") or {}).get("on", True))


def ai_parts_off(choices: J) -> J:
    """A copy of the choices with the AI parts switched off: the review and the monitor then run their program
    parts only, and no AI call is made for them. The bench builds both from the run choices, so a run tool that
    passes this copy as the run choices turns the AI parts off."""
    out = dict(choices)
    out["ai_parts"] = dict(choices.get("ai_parts") or {}, on=False)
    return out


def parse_flags(reply: str, allowed_rules) -> List[tuple]:
    """(rule, reason) for each FLAG line of an AI reply whose rule number is allowed."""
    found = []
    for line in (reply or "").splitlines():
        m = _FLAG_LINE.match(strip_lead(line))
        if m and int(m.group(1)) in allowed_rules:
            found.append((int(m.group(1)), m.group(2).strip(" *_`") or "flagged by the AI reader"))
    return found


def validate_flags_answer(output: str, call=None) -> None:
    """The import check for a watcher or reviewer answer: the whole answer is the single line
    NO FLAGS, or every non-empty line is a flag line. Anything else, an empty answer included, is
    refused (ContractError) and the call stays pending. With the pending call given, a flag whose rule number
    the shown prompt does not list is refused, and so is a line that holds more than one FLAG (14 Nov, H4)."""
    lines = [ln for ln in (output or "").splitlines() if ln.strip()]
    if not lines:
        raise ContractError("the answer is empty; write NO FLAGS when there is nothing to flag")
    if len(lines) == 1 and strip_lead(lines[0]).rstrip(" \t*_`.").casefold() == _NO_FLAGS:
        return
    listed = prompt_rules((call or {}).get("prompt", ""))
    for ln in lines:
        m = _FLAG_LINE.match(strip_lead(ln))
        if not m:
            raise ContractError("the line %r is not a line of the form FLAG <rule number> <reason>; "
                                "the answer must be only such lines, or the single line NO FLAGS" % ln[:80])
        if len(_FLAG_WORD.findall(strip_lead(ln))) > 1:
            raise ContractError("the line %r holds more than one FLAG; write one flag on each line" % ln[:80])
        if _FLAG_RANGE.match(strip_lead(ln)):
            raise ContractError("the line %r holds a range of rules; write one flag on each line" % ln[:80])
        if listed and int(m.group(1)) not in listed:
            raise ContractError("the line %r flags rule %s, which the prompt does not list (it lists %s)"
                                % (ln[:80], m.group(1), ", ".join(str(n) for n in sorted(listed))))


class Watcher:
    """Reads every send between steps. Keeps the sources named so far and the last advice text's level."""

    def __init__(self, wiring: J, choices: J, ai, run_id: str):
        self.wiring = wiring
        self.choices = choices
        self.ai = ai
        self.run_id = run_id
        self.seen_sources: Optional[set] = None  # every source that an earlier advice text of this run named
        self.last_level: Optional[str] = None
        self.last_advice: Optional[str] = None
        self._patterns = [re.compile(p) for p in choices["watcher"]["instruction_patterns"]]
        self._rules = {int(k) for k in choices["watcher"]["checks"]}

    def look(self, h: Handover, items: List[Item]) -> List[Signal]:
        out: List[Signal] = []
        if h.action != "send":
            return out  # the watcher does not see deletions

        def flag(rule: int, item: Item, reason: str, part: str = "program") -> None:
            out.append(Signal(run_id=self.run_id, t=h.t, rule=rule, level="flag", by="watcher",
                              handover_id=h.handover_id, item_ids=[item.item_id], reason=reason, part=part))

        advice = self.choices["rules"]["advice_kinds"]
        for item in items:
            if any(p.search(item.text) for p in self._patterns):
                flag(0, item, "a line reads like an instruction to an AI")
            problem = place_problem(self.wiring, h.to_place, item.kind)
            if problem is not None:
                flag(1, item, problem)
            if item.kind in advice:
                named = sources_named(item.text, self.choices)
                if not named:
                    flag(4, item, "the advice text has no source tag")
                elif self.seen_sources is not None:
                    # 13 Nov: the same reading of rule 4 as the checker and the answer key. A text that names fewer
                    # sources than before breaks no rule (rules.rule4_all_sources_required false). A text that
                    # names a source which no earlier advice text of the run named does.
                    new = sorted(set(named) - self.seen_sources)
                    dropped = sorted(self.seen_sources - set(named))
                    if new:
                        flag(4, item, "the advice text names a source that no earlier advice text named: %s"
                             % ", ".join(new))
                    elif dropped and self.choices["rules"].get("rule4_all_sources_required", False):
                        flag(4, item, "the advice text leaves out a source that an earlier advice text named")
                if named:
                    self.seen_sources = (self.seen_sources or set()) | set(named)
                level = claim_level(item.text, self.choices)
                if level is not None and level != "undecided":
                    if self.last_level is not None and level != self.last_level:
                        flag(5, item, "the claim states %s where the advice text before it states %s"
                             % (level, self.last_level))
                    self.last_level = level
                if not has_ai_mark(item.text, self.choices):
                    flag(6, item, "the advice text has no AI mark")
            previous = self.last_advice
            if item.kind in advice:
                self.last_advice = item.text
            if not ai_parts_on(self.choices):
                continue
            fields = {"from": h.from_place, "to": str(h.to_place), "kind": item.kind, "text": item.text,
                      "previous_advice": previous if previous is not None else NO_PREVIOUS_ADVICE,
                      "promise": canon(self.wiring["promise"]["places"])}
            fields.update(every_prompt_fields(self.choices))
            for rule, reason in parse_flags(self.ai(self.choices["prompts"]["watcher"], fields), self._rules):
                flag(rule, item, reason, "ai")
        return out


def closing_time(own_log: List[J], choices: J) -> int:
    """The tick at which a case with this log has closed: one tick after its last entry, then the longest hold
    plus one, so that every deadline of the case has passed. The engine closes a case the same way
    (custody/engine.py, close); the review has only the log to count from."""
    holds = [v for v in choices["holds"].values() if isinstance(v, int) and not isinstance(v, bool)]
    last = max((line["t"] for line in own_log), default=0)
    return last + 1 + (max(holds) if holds else 0) + 1


def review(own_log: List[J], final: J, wiring: J, choices: J, ai, run_id: str) -> List[Signal]:
    """The after-the-fact review, in two parts. The program part flags rules 1, 2, 4 and 6 from the log and
    the final texts (part "program"). The AI part is asked about rules 1 to 6 and may flag any of them or
    rule 0 (part "ai"); with D: ai_parts.on false it is not run and no AI call is made.

    The AI is given the final["ai_answer"] (the first advice text of the case) when the engine supplies it;
    a field with no text reads "(none in this flow)". A log entry with action "intake" (keys t, kind, place,
    item or item_ids) counts as an arrival in the rule 2 scan; a log without such entries works as before.

    Rule 2, program part: a copy needs a logged delete at its place within the hold. The log shows a copy in two
    ways. It arrives (an intake line, or a send to the place), and the hold counts from the arrival. Or the place
    sends it on while the log shows no arrival there (a copy the service made itself; added 13 Nov), and the hold
    counts from the first such send.

    The signal's t is the closing time of the case as the log shows it (closing_time): the review reads the
    log after the case, once every deadline counted from the last entry has passed. Until 13 Nov (version 3)
    the t was the largest t in the log plus 1, which lies before the deadline of a copy that is never deleted,
    so that the scorer read the review's flag on such a copy as a warning that came before the violation.
    """
    t_signal = closing_time(own_log, choices)
    out: List[Signal] = []

    def flag(rule: int, reason: str, handover_id: Optional[str] = None, item_ids: Optional[List[str]] = None,
             part: str = "program") -> None:
        out.append(Signal(run_id=run_id, t=t_signal, rule=rule, level="flag", by="review",
                          handover_id=handover_id, item_ids=list(item_ids or []), reason=reason, part=part))

    deletes = [ln for ln in own_log if ln["action"] == "delete"]

    def undeleted(place, line, item_ids):
        """The hold at the place for the line's kind, and the line's items with no logged delete there within it,
        counted from the line's t. (None, []) when the place may keep the kind or may not hold it at all."""
        ticks = hold_ticks(wiring, choices, place, line["kind"])
        if ticks is None:
            return None, []
        return ticks, [i for i in item_ids
                       if not any(d["from"] == place and i in d["item_ids"] and d["t"] <= line["t"] + ticks
                                  for d in deletes)]

    arrived = set()  # (place, item) for every copy whose arrival the log shows
    for line in own_log:
        if line["action"] not in ("send", "intake"):
            continue
        intake = line["action"] == "intake"
        place = (line.get("place") or line.get("to")) if intake else line["to"]
        item_ids = list(line.get("item_ids") or ([line["item"]] if line.get("item") else [])) if intake \
            else line["item_ids"]
        arrived.update((place, i) for i in item_ids)
        if not intake:
            problem = place_problem(wiring, place, line["kind"])
            if problem is not None:
                flag(1, problem, line["handover_id"], item_ids)
        ticks, late = undeleted(place, line, item_ids)
        if late:
            flag(2, "%s %s %s at tick %d has no logged delete there within %d ticks"
                 % (line["kind"], "arrived at" if intake else "sent to", place, line["t"], ticks),
                 line.get("handover_id"), late)

    # The sender held what it sent (13 Nov, version 3, the owner's decision). A copy that a service made itself has
    # no arrival line. The first logged send of it from a place shows that the place held it, and the hold is
    # counted from that send. A copy whose arrival the log shows is left to the check above, which is stricter.
    checked = set()
    for line in sorted((ln for ln in own_log if ln["action"] == "send" and ln.get("from")), key=lambda ln: ln["t"]):
        sender = line["from"]
        item_ids = [i for i in line["item_ids"] if (sender, i) not in arrived and (sender, i) not in checked]
        checked.update((sender, i) for i in item_ids)
        ticks, late = undeleted(sender, line, item_ids)
        if late:
            flag(2, "%s sent on from %s at tick %d has no logged delete there within %d ticks"
                 % (line["kind"], sender, line["t"], ticks), line.get("handover_id"), late)

    patient_note = final.get("patient_note")
    if patient_note is not None:
        if not sources_named(patient_note, choices):
            flag(4, "the final note for the patient has no source tag")
        if not has_ai_mark(patient_note, choices):
            flag(6, "the final note for the patient has no AI mark")

    if not ai_parts_on(choices):
        return out
    fields = {"own_log": "\n".join(canon(line) for line in own_log),
              "note": final.get("note") or NONE_IN_FLOW,
              "ai_answer": final.get("ai_answer") or NONE_IN_FLOW,
              "patient_note": patient_note or NONE_IN_FLOW,
              "promise": canon(wiring["promise"]["places"])}
    fields.update(every_prompt_fields(choices))
    allowed = {int(k) for k in choices["review"].get("ai_asks", choices["review"]["checks"])} | {0}
    for rule, reason in parse_flags(ai(choices["prompts"]["reviewer"], fields), allowed):
        flag(rule, reason, part="ai")
    return out
