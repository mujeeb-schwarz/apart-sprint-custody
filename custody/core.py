"""The shared data model of the custody build, the three readers of text and
three lookups on the wiring.

The architect wrote this file before the builders started. Every builder
imports it and no builder changes it. docs/FRAME.md, section 3, describes it;
where the two differ, this file wins. The allowed values of each field are in
config/design_choices.json under "values".
"""
from dataclasses import dataclass, asdict  # asdict gives the JSON form
from typing import Any, Callable, Dict, List, Optional
import hashlib
import json
import re

J = Dict[str, Any]

# Version 2: the lane each experiment runs (1: the patient's words going out, 2: advice coming in)
LANE_OF = {1: "words", 2: "advice"}


# ---------------------------------------------------------------- data model

# Version 3 (the repeat check): the field a salt travels in when the AI is called for a repeated unit. It is part of
# the call id (so the call is asked again) and is never in a prompt: a prompt only fills the slots it has.
SALT_FIELD = "_salt"

@dataclass(frozen=True)
class Visit:
    visit_id: str
    conversation_id: str
    conversation: str
    question_id: str
    question: str
    evidence: List[J]  # [{"source_id", "title", "text"}]
    expert_answer: Optional[str]
    expert_certainty: Optional[str]
    given_answer: Optional[str]
    given_by: Optional[str]
    split: str
    matched: bool
    meta: J
    # Version 2: 1 = a conversation (the words flow), 2 = a question (the advice flow). 0 = an old joined visit,
    # which runs every lane; the case files never hold it.
    experiment: int = 0
    # Version 3: the text of the answer as it enters the advice flow. The bench makes it with the program that
    # composes it (custody.visits.compose_answer) on the copy it hands to the engine; a case file holds null.
    answer_text: Optional[str] = None
    # Version 3: for a unit made from a case by plan (custody/units.py) the id of the clean case it was made from;
    # null for a case itself. The scorer pairs a planted unit with the clean unit of that case through it.
    clean_of: Optional[str] = None


@dataclass(frozen=True)
class Item:
    item_id: str
    visit_id: str
    kind: str
    text: str
    made_by: str
    parents: List[str]  # item ids


@dataclass(frozen=True)
class Label:
    item_id: str
    source: List[str]
    certainty: Optional[str]
    ai_made: bool
    allowed: List[str]
    delete_by: Optional[int]


@dataclass(frozen=True)
class Handover:
    handover_id: str
    run_id: str
    t: int
    action: str  # "send" or "delete"
    step: str
    from_place: str
    to_place: Optional[str]  # None for a delete
    kind: str  # the one kind this handover carries; the engine sets it
    item_ids: List[str]
    move_id: Optional[str]


@dataclass(frozen=True)
class Signal:
    run_id: str
    t: int
    rule: int
    level: str
    by: str
    handover_id: Optional[str]
    item_ids: List[str]
    reason: str
    part: str = "program"  # which part raised it: "program" or "ai" (Version 2, part 3)


@dataclass(frozen=True)
class WitnessReceipt:
    index: int
    record_fp: str
    prev_head: str
    head: str
    t: int
    mac: str


@dataclass(frozen=True)
class Record:
    seq: int
    run_id: str
    t: int
    handover: J
    labels: List[J]
    verdicts: List[J]
    decision: str
    prev_fp: str
    fp: str
    receipt: Optional[J]


@dataclass(frozen=True)
class TruthEvent:
    seq: int
    run_id: str
    t: int
    kind: str
    step: str
    place: Optional[str]
    to_place: Optional[str]
    item_id: Optional[str]
    handover_id: Optional[str]
    fault_id: Optional[str]
    detail: J


@dataclass(frozen=True)
class RunResult:
    run_id: str
    visit_id: str
    conversation_id: str
    condition: str
    rep: int
    split: str
    produced: Dict[str, bool]
    asked: int
    delivered: int
    signals: int
    ai_calls: int
    proof: str
    receipt_ok: Optional[bool]
    crashed: bool
    experiment: int = 0


@dataclass
class StepContext:
    visit: Visit
    step: str
    place: str
    t: int
    ai: Callable[[str, Dict[str, str]], str]
    spec: J
    choices: J
    duty: Optional[str]


@dataclass
class StepOutput:
    items: List[Item]
    requests: List[J]
    deletes: List[str]


# ------------------------------------------------------- writing and ids

def canon(x: Any) -> str:
    """The one way JSON is written: sorted keys, no spaces, one line."""
    return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def fingerprint(x: Any) -> str:
    """sha256 in hex, of a text as it is or of anything else through canon."""
    return hashlib.sha256((x if isinstance(x, str) else canon(x)).encode("utf-8")).hexdigest()


def make_item_id(visit_id: str, kind: str, made_by: str, text: str) -> str:
    return fingerprint([visit_id, kind, made_by, text])[:16]


# ------------------------------------------------------------- exceptions

class CustodyError(Exception):
    pass


class ContractError(CustodyError):
    """An argument or a file breaks the frame."""


class DataError(CustodyError):
    """A data file is missing or malformed."""


class LedgerError(CustodyError):
    """The journal or the witness refused."""


class AICallMissing(CustodyError):
    """Replay holds no stored text for this call."""

    def __init__(self, call_id: str, prompt_id: str, fields: Dict[str, str]):
        super().__init__("no stored text for call %s (prompt %s)" % (call_id, prompt_id))
        self.call_id = call_id
        self.prompt_id = prompt_id
        self.fields = fields


# ------------------------------------------------- the three readers of text
# config/design_choices.json, "readers", says how each one reads. They serve
# the gate, the watcher, the canned AI and the scorer alike.

_MD = " \t>#*_`-"  # markdown and spaces a reader steps over at the start of a line


_LIST_NUM = re.compile(r"^\d+[.)]\s+")
_TRAIL = " \t*_`.,;:!"


def strip_lead(line: str) -> str:
    """A line without the markdown, quote marks, bullets and list numbers a reader steps over at its start."""
    prev = None
    while prev != line:
        prev = line
        line = line.lstrip(_MD + "\u2022+")
        line = _LIST_NUM.sub("", line)
    return line


def strip_line(line: str) -> str:
    """strip_lead, and spaces, backticks, asterisks and closing punctuation at the end."""
    return strip_lead(line).rstrip(_TRAIL)


def _claim_pattern(choices: J):
    name = choices["markers"]["claim"].rstrip(":").strip()
    # markdown, bullets and list numbers may come before the marker ("1. **Claim**: X might help.")
    return re.compile(r"^(?:[" + re.escape(_MD + "\u2022+") + r"]|\d+[.)][ \t]+)*" + re.escape(name)
                      + r"[ \t*_`]*:", re.IGNORECASE)


def claim_line_count(text: str, choices: J) -> int:
    """How many lines of the text are claim lines, read as claim_line reads them."""
    pattern = _claim_pattern(choices)
    return sum(1 for ln in text.splitlines() if pattern.match(ln))


_WIRING_NAMES: Dict[str, Any] = {}


def wiring_names(choices: J):
    """(item kinds, place ids) the wiring knows, read once from D: markers.action.wiring_file (default
    wiring/wiring.json under the project folder): `kinds` and the ids of promise.places."""
    from pathlib import Path
    name = (choices["markers"].get("action") or {}).get("wiring_file", "wiring/wiring.json")
    if name not in _WIRING_NAMES:
        path = Path(__file__).resolve().parents[1] / name
        try:
            with open(str(path), encoding="utf-8") as fh:
                w = json.load(fh)
            _WIRING_NAMES[name] = (set(w["kinds"]), {p["id"] for p in w["promise"]["places"]})
        except (OSError, ValueError, KeyError) as exc:
            raise DataError("cannot read the wiring file %s for the send lines: %s" % (path, exc))
    return _WIRING_NAMES[name]


def action_line(line: str, choices: J):
    """How one line reads as a send request (D: markers.action; 14 Nov, H3).

    After strip_line (markdown, list markers, backticks, spaces, closing punctuation) the line is:
      ("send", kind, place) when it is the canonical upper-case form `SEND <kind> TO <place>` and the kind is
        an item kind the wiring knows; or when it is in any other case (`Send transcript to analytics`) and the
        kind is an item kind AND the place is a place the wiring knows;
      ("near", None, None) when it starts with "send " and holds " to " and is not a send by those rules
        (it is counted, causes no send, and is never cut from the text);
      None otherwise: a longer sentence that merely holds such words is not an action line."""
    action = choices["markers"].get("action") or {}
    pattern = action.get("pattern")
    if not pattern:
        return None
    kinds, places = wiring_names(choices)
    stripped = strip_line(line)
    m = re.match(pattern, stripped)
    if m:
        return ("send", m.group(1), m.group(2)) if m.group(1) in kinds else ("near", None, None)
    lenient = action.get("lenient_pattern")
    if lenient:
        m = re.match(lenient, stripped, re.IGNORECASE)
        if m and m.group(1).lower() in kinds and m.group(2).lower() in places:
            return ("send", m.group(1).lower(), m.group(2).lower())
    low = stripped.lower()
    if low.startswith("send ") and " to " in low:
        return ("near", None, None)
    return None


def action_near_misses(text: str, choices: J) -> int:
    """How many whole lines of the text look like a send and name no known kind or place."""
    return sum(1 for ln in text.split("\n") if (action_line(ln, choices) or ("",))[0] == "near")


def claim_line(text: str, choices: J) -> Optional[str]:
    """The words after the claim marker on the first claim line, or None.

    Tolerant of leading spaces, of markdown around the marker ('**Claim:**',
    '> Claim:', '**Claim**:') and of upper or lower case.
    """
    pattern = _claim_pattern(choices)
    for ln in text.splitlines():
        m = pattern.match(ln)
        if m:
            return ln[m.end():]
    return None


def _has_phrase(line: str, phrase: str, case_sensitive: bool) -> bool:
    flags = 0 if case_sensitive else re.IGNORECASE
    tail = r"(?!\w)"
    if phrase.lower() == "may":
        tail += r"(?!\s+\d)"  # 'may 2019' is a month, not the verb
    return re.search(r"(?<!\w)" + re.escape(phrase) + tail, line, flags) is not None


def claim_level(text: str, choices: J) -> Optional[str]:
    """The ladder level stated on the first claim line; None with no claim line;
    "undecided" when the line holds a hedge the ladder does not list (the judge decides).

    Order: wordings that name a level outright (ladder.named), then the phrases in
    ladder.test_order, then the hedges the ladder does not know, then the default.
    Phrases in ladder.case_sensitive_phrases match only as written ('may', the verb).
    """
    line = claim_line(text, choices)
    if line is None:
        return None
    ladder = choices["ladder"]
    sensitive = set(ladder.get("case_sensitive_phrases", []))
    for level in ladder["levels"]:
        for phrase in ladder.get("named", {}).get(level, []):
            if _has_phrase(line, phrase, False):
                return level
    for level in ladder["test_order"]:
        for phrase in ladder["phrases"][level]:
            if _has_phrase(line, phrase, phrase in sensitive):
                return level
    for phrase in ladder.get("undecided_hedges", []):
        if _has_phrase(line, phrase, False):
            return "undecided"
    for phrase in ladder.get("undecided_case_sensitive", []):
        if _has_phrase(line, phrase, True):
            return "undecided"
    return ladder["default"]


_ID_OK = re.compile(r"^[a-z0-9_.\-]+:[^\s]+$")


def normalise_id(source_id: str) -> str:
    """A source id as compared: lower case, no spaces ('PMID: 1' -> 'pmid:1')."""
    return re.sub(r"\s+", "", source_id).lower()


def _tag_ids(text: str, choices: J) -> List[str]:
    tag = choices["markers"]["source_tag"]
    core = tag["open"].strip().lstrip("[(").rstrip(":").strip()
    pattern = re.compile(r"[\[(]\s*" + re.escape(core) + r"s?\s*:([^\])]*)[\])]", re.IGNORECASE)
    seps = r"[" + re.escape(tag["separator"]) + r",]"
    found: List[str] = []
    for m in pattern.finditer(text):
        for part in re.split(seps, m.group(1)):
            part = normalise_id(part)
            if part and part not in found:
                found.append(part)
    return found


def sources_named(text: str, choices: J) -> List[str]:
    """Every readable id inside every source tag, normalised, in order of first appearance.

    The tag may be written with a capital or round brackets; ids split on ';' and ','.
    An id that does not read as 'kind:value' is not listed here: see sources_unreadable.
    """
    return [i for i in _tag_ids(text, choices) if _ID_OK.match(i)]


def sources_unreadable(text: str, choices: J) -> List[str]:
    """The ids inside source tags that the reader cannot read; the judge decides them."""
    return [i for i in _tag_ids(text, choices) if not _ID_OK.match(i)]


def has_ai_mark(text: str, choices: J) -> bool:
    """True when some line, trimmed of spaces and markdown, equals the AI mark, ignoring case.

    Presence only: the rule tests that the mark is there, not what the text is about.
    """
    mark = choices["markers"]["ai"].casefold()
    return any(ln.strip(_MD).casefold() == mark for ln in text.splitlines())


# ------------------------------------------------- three lookups on the wiring
# A place missing from the wiring's promise is not named and may hold nothing.
# In "may_hold" a kind with the value null may stay for good; a kind that is
# absent may not be held at all. These helpers keep the two apart.

def _place(wiring: J, place: str) -> Optional[J]:
    for entry in wiring["promise"]["places"]:
        if entry["id"] == place:
            return entry
    return None


def is_named(wiring: J, place: str) -> bool:
    """True when the promise lists the place with named true."""
    entry = _place(wiring, place)
    return entry is not None and entry.get("named") is True


def may_hold(wiring: J, place: str, kind: str) -> bool:
    """True when the promise lets the place hold the kind, for a time or for good."""
    entry = _place(wiring, place)
    return entry is not None and kind in entry.get("may_hold", {})


def hold_ticks(wiring: J, choices: J, place: str, kind: str) -> Optional[int]:
    """The ticks a copy of the kind may sit at the place, counted from arrival.

    None when the copy may stay for good, and None when the place may not hold
    the kind at all (ask may_hold first: that case is rule 1's).
    """
    if not may_hold(wiring, place, kind):
        return None
    name = _place(wiring, place)["may_hold"][kind]
    if name is None:
        return None
    holds = choices["holds"]
    if name not in holds or isinstance(holds[name], bool) or not isinstance(holds[name], int):
        raise ContractError("the wiring names a hold that the choices do not define: %r" % (name,))
    return holds[name]
