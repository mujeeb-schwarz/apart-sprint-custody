"""The AI judge for the advice rules (4, 5 and 6).

The program reads most advice texts by itself, with the three readers of
custody.core. A text that does not follow the markers (no source tag, no claim
line, no AI mark) cannot be read that way, and only the judge decides it. The
judge also reads a sample of texts that do carry the markers, so that a person
can see where it and the readers differ.

What the judge sees is an allow-list: the text of one item, the visit's true
source ids and the rule's question (D: rules.judge_sees), plus the three marker
fields every prompt gets. The expert grade stays in the program: it is in the
job but in no field of the call (so not in the call id either), and the judge is never
told it. For rule 5 the judge reports the level the text itself states; the program
compares that level with the grade here (13 Nov). It never gets a run id, a
condition, a signal, a label or a record (D: rules.judge_never_sees). A text is
judged once for each (item_id, rule) and the verdict serves every run that made
that item.

This module imports the standard library and custody.core only. The AI arrives
as an argument: ai(prompt_id, fields) -> text.
"""
import random
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from custody.core import (ContractError, J, claim_level, has_ai_mark, normalise_id, sources_named,
                          sources_unreadable, strip_line)

AI = Callable[[str, Dict[str, str]], str]

RULES = (4, 5, 6)
JUDGE_NAME = "live"  # the value of "judge" in judge.jsonl: an AI answered through the helper files
FIELD_KEYS = ("text", "true_sources", "rule")

# What the judge is asked to reply, by rule. The question itself is read from D (rules.left_to_judge).
_FORM = {
    4: ("Reply with one line, either VERDICT kept (the prose names at least one of the true sources and no "
        "source outside that list) or VERDICT broken (it names no true source, or it names one outside the list)."),
    5: ("Reply with one line, LEVEL followed by exactly one of: %s, none. Choose the level the text itself states "
        "(none when it states no level). Report what the text says, whatever the evidence may really show."),
    6: ("Reply with one line, either VERDICT kept (the prose plainly says that an AI or an automated tool wrote or "
        "generated the text) or VERDICT broken (it does not)."),
}
_EXPECTS = {4: "verdict", 5: "level", 6: "verdict"}
_RUN_ID = re.compile(r"v\d{4}\.(?:A\+|A|B|C)\.r\d+")
_VERDICT_LINE = re.compile(r"^verdict\s*:?\s*(kept|broken)$")  # on a line already stripped and lowered
_LEVEL_LINE = re.compile(r"^level\s*:?\s*([a-z ]+)$")


# ------------------------------------------------------- the program's own reading

def true_sources(visit: J) -> List[str]:
    """The ids a text may truly name: the visit's evidence, or the tool of a stored answer."""
    if visit.get("given_answer") is not None:
        return ["tool:%s" % visit["given_by"]]
    return [e["source_id"] for e in visit.get("evidence") or []]


def key_source_of(choices: J, key_source: Optional[str] = None) -> str:
    """Where the answer key for rules 4 to 6 comes from: "judge" (default; D: rules.key_source) or "readers"."""
    ks = key_source or choices["rules"].get("key_source", "judge")
    if ks not in ("judge", "readers"):
        raise ContractError("rules.key_source must be judge or readers, not %r" % (ks,))
    return ks


def needs_judge(rule: int, text: str, visit: J, choices: J, level_source: str = "reader_first",
                key_source: str = "readers") -> bool:
    """True when the three readers cannot read this text for the rule (it is the scorer's own test).
    With level_source judge_all every advice text needs the judge's level for rule 5, graded visit or not.
    With key_source judge every advice text needs the judge, for each of rules 4, 5 and 6 (Version 2)."""
    if key_source == "judge" and rule in RULES:
        return True
    if rule == 4:
        return not sources_named(text, choices) or bool(sources_unreadable(text, choices))
    if rule == 5:
        if level_source == "judge_all":
            return True
        return visit.get("expert_certainty") is not None and claim_level(text, choices) in (None, "undecided")
    if rule == 6:
        return not has_ai_mark(text, choices)
    return False


def program_verdict(rule: int, text: str, visit: J, choices: J) -> Optional[str]:
    """kept or broken as the readers decide it, or None where they cannot read the text."""
    if rule == 4 and sources_named(text, choices):
        truth = {normalise_id(t) for t in true_sources(visit)}
        if any(n not in truth for n in sources_named(text, choices)):
            return "broken"  # a readable id outside the truth is firm, whatever else the tag holds
    if needs_judge(rule, text, visit, choices):
        return None
    if rule == 4:
        return "kept"
    if rule == 5:
        return "kept" if claim_level(text, choices) == visit.get("expert_certainty") else "broken"
    if rule == 6:
        return "kept"
    raise ContractError("rule %r is not judged" % (rule,))


# ------------------------------------------------------------ what the judge sees

def rule_text(rule: int, choices: J) -> str:
    """The rule's question and the form of the reply, as one field."""
    if rule not in RULES:
        raise ContractError("the judge reads rules 4, 5 and 6, not %r" % (rule,))
    question = choices["rules"]["left_to_judge"][str(rule)]
    form = _FORM[rule]
    if rule == 5:
        form = form % ", ".join(choices["ladder"]["levels"])
    return "Rule %d. %s %s" % (rule, question, form)


def judge_fields(job: J, choices: J) -> Dict[str, str]:
    """The fields the judge's prompt is filled with, and nothing else.

    Built from an allow-list. The job's own run-free fields (visit_id, item_id) stay in the program.
    """
    markers = choices["markers"]
    fields = {
        "text": job["text"],
        "true_sources": "; ".join(job["true_sources"]),
        "rule": rule_text(job["rule"], choices),
        "claim_marker": markers["claim"],
        "source_open": markers["source_tag"]["open"],
        "ai_mark": markers["ai"],
    }
    blind_check(fields)
    return fields


def blind_check(fields: Dict[str, str]) -> None:
    """Refuses a field set that carries a run id, or any key beyond the allow-list and the marker fields."""
    allowed = set(FIELD_KEYS) | {"claim_marker", "source_open", "ai_mark"}
    extra = set(fields) - allowed
    if extra:
        raise ContractError("the judge is not given the fields %s" % sorted(extra))
    for key, value in fields.items():
        if _RUN_ID.search(str(value)):
            raise ContractError("the judge field %s carries a run id" % key)


# --------------------------------------------------------------- the jobs

def _advice(texts: List[J], choices: J) -> List[J]:
    kinds = choices["rules"]["advice_kinds"]
    return [t["item"] for t in texts if t["item"]["kind"] in kinds]


def _job(item: J, visit: J, rule: int, choices: Optional[J] = None) -> J:
    job = {"visit_id": item["visit_id"], "item_id": item["item_id"], "rule": rule, "text": item["text"],
           "true_sources": true_sources(visit), "grade": visit.get("expert_certainty")}
    if rule == 5 and choices is not None:
        job["reader_level"] = claim_level(item["text"], choices)  # stays in the program; stored beside the judge's level
    return job


def build_jobs(texts: List[J], visits: Dict[str, J], choices: J, splits: Optional[List[str]] = None,
               level_source: str = "reader_first", key_source: Optional[str] = None) -> List[J]:
    """One job for each (item_id, rule) with an advice text, in sorted order: under key_source judge (the default,
    D: rules.key_source) every answer, plan and patient note for each of rules 4, 5 and 6; under readers only the
    texts the readers cannot read.

    `texts` are rows of texts.jsonl; only each row's item is used, so a run id on the row never
    reaches a job. With `splits` given, only the visits of those splits are taken.
    """
    seen: Dict[Tuple[str, int], J] = {}
    ks = key_source_of(choices, key_source)
    for item in _advice(texts, choices):
        visit = visits[item["visit_id"]]
        if splits is not None and visit.get("split") not in splits:
            continue
        for rule in RULES:
            if needs_judge(rule, item["text"], visit, choices, level_source, ks):
                seen.setdefault((item["item_id"], rule), _job(item, visit, rule, choices))
    return [seen[k] for k in sorted(seen)]


def sample_jobs(texts: List[J], visits: Dict[str, J], choices: J, splits: Optional[List[str]] = None,
                level_source: str = "reader_first") -> List[J]:
    """The marked sample: advice texts that the readers can read, drawn with seeds.judge.

    From test visits by default; with `splits` given, from the visits of those splits (the tool passes the
    splits of the run in hand, so a tuning run gets a sample too: 14 Nov, H6). Rule 5 only counts where the
    visit has a grade, and not under judge_all, where every text is judged for its level anyway. The draw is
    over the sorted (item_id, rule) pairs, so the same texts and seed give the same sample.
    """
    pool: Dict[Tuple[str, int], J] = {}
    for item in _advice(texts, choices):
        visit = visits[item["visit_id"]]
        if visit.get("split") not in (splits if splits is not None else ["test"]):
            continue
        for rule in RULES:
            if rule == 5 and (visit.get("expert_certainty") is None or level_source == "judge_all"):
                continue
            if not needs_judge(rule, item["text"], visit, choices):
                pool.setdefault((item["item_id"], rule), _job(item, visit, rule, choices))
    keys = sorted(pool)
    n = choices["rules"]["judge_marked_sample"]
    rng = random.Random(choices["seeds"]["judge"])
    pick = sorted(rng.sample(keys, min(n, len(keys))))
    return [pool[k] for k in pick]


# ------------------------------------------------------- reading the reply

def _answer_lines(output: str, expects: Optional[str] = None) -> List[Tuple[str, str]]:
    """Every answer line of the reply as (form, value), read leniently for form: markdown, bold, list
    markers and trailing punctuation are stripped, case is ignored, and a hyphen or underscore inside the
    value counts as a space ("very-low" is "very low"). With `expects` given only lines of that kind count."""
    found = []
    for line in output.splitlines():
        s = re.sub(r"[*`]", "", strip_line(line)).replace("_", " ").replace("-", " ")
        s = re.sub(r"\s+", " ", s).strip(" .,;:!").casefold()
        m = _VERDICT_LINE.match(s)
        if m:
            found.append(("verdict", m.group(1)))
            continue
        m = _LEVEL_LINE.match(s)
        if m:
            found.append(("level", m.group(1).strip()))
    return [f for f in found if expects in (None, f[0])]


def parse_answer(output: str, expects: Optional[str] = None) -> Tuple[str, str]:
    """("verdict", kept|broken) or ("level", a ladder level or none), from the one line of the kind asked for.

    A reply with no such line, or with two or more, is refused (ContractError), so that the first of two
    conflicting lines never wins."""
    lines = _answer_lines(output, expects)
    if not lines:
        raise ContractError("no line of the form %s" % (
            {"verdict": "'VERDICT kept|broken'", "level": "'LEVEL <level>'"}.get(expects or "")
            or "'VERDICT kept|broken' or 'LEVEL <level>'"))
    if len(lines) > 1:
        raise ContractError("the reply holds %d answer lines (%s); it must hold exactly one" % (
            len(lines), "; ".join("%s %s" % f for f in lines[:4])))
    return lines[0]


def _levels(choices: J) -> set:
    return set(choices["ladder"]["levels"]) | {"none"}


def make_validator(choices: J) -> Callable[[str, J], None]:
    """The check an import runs on a judge answer: the form the call asked for, a level on the ladder."""
    levels = _levels(choices)

    def validate(output: str, call: J) -> None:
        want = call.get("expects")
        form, value = parse_answer(output, want if want in ("verdict", "level") else None)
        if form == "level" and value not in levels:
            raise ContractError("level %r is not on the ladder" % value)

    return validate


def rule_of_prompt(prompt: str, choices: J) -> Optional[int]:
    """The rule a judge prompt asks about, found by the rule's own wording (rule_text) in the prompt."""
    for rule in RULES:
        if rule_text(rule, choices) in prompt:
            return rule
    return None


def expects_of(prompt_id: str, fields: Dict[str, str], judge_prompt: str) -> str:
    """What kind of answer a call wants, for the pending file: a judge call names its form; others say 'text'."""
    if prompt_id != judge_prompt:
        return "text"
    m = re.match(r"Rule (\d)\.", fields.get("rule", ""))
    return _EXPECTS.get(int(m.group(1)), "text") if m else "text"


def verdict_of(rule: int, output: str, grade: Optional[str], choices: J) -> str:
    """kept, broken or undecided from the judge's reply.

    Rules 4 and 6 take the judge's verdict. Rule 5 takes the level it reports and compares it with the
    grade here: the same level is kept, another level is broken (hardened or softened), none is undecided.
    """
    if rule in (4, 6):
        return parse_answer(output, "verdict")[1]
    form, value = parse_answer(output, "level")
    if value not in _levels(choices):
        raise ContractError("level %r is not on the ladder" % value)
    if value == "none" or grade is None:
        return "undecided"
    return "kept" if value == grade else "broken"


# ----------------------------------------------------------------- judging

def judge_jobs(ai: AI, jobs: List[J], choices: J, lenient: bool = False) -> List[J]:
    """One judge.jsonl row for each job: {visit_id, item_id, rule, verdict, judge, prompt_id}
    (rule 5 rows also carry "level", the level the judge reported, or "none").

    With lenient true, a job whose answer is not there yet (an empty or unreadable reply, as a
    collecting AI returns for a missing call) gets no row. Otherwise AICallMissing and ContractError
    pass through.
    """
    prompt_id = choices["prompts"]["judge"]
    rows = []
    announce = getattr(ai, "set_case", None)  # a collecting AI wants to know the case of each call
    for job in jobs:
        if announce is not None:
            announce(job["visit_id"])
        out = ai(prompt_id, judge_fields(job, choices))
        try:
            verdict = verdict_of(job["rule"], out, job["grade"], choices)
        except ContractError:
            if lenient and not out.strip():
                continue
            raise
        row = {"visit_id": job["visit_id"], "item_id": job["item_id"], "rule": job["rule"],
               "verdict": verdict, "judge": JUDGE_NAME, "prompt_id": prompt_id}
        if job["rule"] == 5:
            row["level"] = parse_answer(out, "level")[1]  # the level the judge reported (13 Nov, G7)
            if "reader_level" in job:
                row["reader_level"] = job["reader_level"]  # the reader's, stored beside it (14 Nov, H6)
        rows.append(row)
    if announce is not None:
        announce(None)
    return rows


def compare_with_readers(rows: List[J], jobs: List[J], visits: Dict[str, J], choices: J) -> J:
    """Where the judge and the readers differ on the marked sample. The readers decide kept or broken;
    an undecided judge verdict counts as a difference."""
    by_key = {(j["item_id"], j["rule"]): j for j in jobs}
    differ = []
    agree = 0
    for row in rows:
        job = by_key[(row["item_id"], row["rule"])]
        reader = program_verdict(row["rule"], job["text"], visits[row["visit_id"]], choices)
        if reader == row["verdict"]:
            agree += 1
        else:
            differ.append({"visit_id": row["visit_id"], "item_id": row["item_id"], "rule": row["rule"],
                           "readers": reader, "judge": row["verdict"]})
    return {"judged": len(rows), "agree": agree, "differ": len(differ), "differences": differ}
