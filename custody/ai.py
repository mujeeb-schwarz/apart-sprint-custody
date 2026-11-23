"""The AI seam: a canned AI that needs no model, a recorder and a replayer.

An AI is a callable ai(prompt_id, fields) -> text. The caller of ai() fills the
three marker fields; nothing here adds to the fields.
"""
import json
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from custody.core import AICallMissing, ContractError, J, fingerprint

AI = Callable[[str, Dict[str, str]], str]

ROOT = Path(__file__).resolve().parents[1]
STEP_PROMPTS = ("note_writer", "plan", "patient_note")
_SLOT = re.compile(r"\{\{([a-z_]+)\}\}")


# ------------------------------------------------------------------ prompts

def _prompt_name(prompt_id: str) -> str:
    return prompt_id.rsplit(".v", 1)[0]


_REMINDERS_ID: List[str] = []


def reminders_id() -> str:
    """The id of the reminders file in use: D: prompts.reminders (a changed prompt is a new file, so the version
    is read from the design choices, not written here)."""
    if not _REMINDERS_ID:
        try:
            with open(str(ROOT / "config" / "design_choices.json"), encoding="utf-8") as fh:
                _REMINDERS_ID.append(json.load(fh)["prompts"]["reminders"])
        except (OSError, ValueError, KeyError) as exc:
            raise ContractError("the reminders file is not named in config/design_choices.json: %s" % exc)
    return _REMINDERS_ID[0]


def prompt_text(prompt_id: str) -> str:
    """The template of a prompt. A step prompt carries the reminders after it.
    A prompt file or a reminders file that is missing is an error, never empty text."""
    path = ROOT / "prompts" / (prompt_id + ".txt")
    try:
        template = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ContractError("prompt file %s is missing or unreadable: %s" % (path, exc))
    if _prompt_name(prompt_id) in STEP_PROMPTS:
        rpath = ROOT / "prompts" / (reminders_id() + ".txt")
        try:
            reminders = rpath.read_text(encoding="utf-8")
        except OSError as exc:
            raise ContractError("reminders file %s is missing or unreadable: %s" % (rpath, exc))
        template = template.rstrip("\n") + "\n\n" + reminders
    return template


def render_prompt(prompt_id: str, fields: Dict[str, str]) -> str:
    """Fill the slots. A slot with no field is an error; a field with no slot is ignored."""
    template = prompt_text(prompt_id)

    def fill(m):
        name = m.group(1)
        if name not in fields:
            raise ContractError("prompt %s has the slot {{%s}} but no such field" % (prompt_id, name))
        return str(fields[name])

    return _SLOT.sub(fill, template)


def call_id_of(prompt_id: str, fields: Dict[str, str]) -> str:
    return fingerprint([prompt_id, fingerprint(prompt_text(prompt_id)), fields])


# ----------------------------------------------------------------- canned AI

def _claim_line(text: str, marker: str):
    for line in text.splitlines():
        if line.startswith(marker):
            return line
    return None


def _first_tag(text: str, choices: J) -> str:
    tag = choices["markers"]["source_tag"]
    start = text.find(tag["open"])
    if start < 0:
        return ""
    end = text.find(tag["close"], start + len(tag["open"]))
    if end < 0:
        return ""
    return text[start:end + len(tag["close"])]


def _template_regex(template: str) -> "re.Pattern":
    """A line pattern from a wording with the slots {kind} and {place} (planting.inject_texts_test)."""
    out, pos = [], 0
    for m in re.finditer(r"\{(kind|place)\}", template):
        out.append(re.escape(template[pos:m.start()]))
        out.append("(?P<%s>[a-z_]+)" % m.group(1))
        pos = m.end()
    out.append(re.escape(template[pos:]))
    return re.compile("".join(out) + "$")


def make_canned_ai(choices: J, hidden_lines: Optional[J] = None) -> AI:
    """An AI whose fixed text is built from the fields, from the choices it is given.

    `hidden_lines` ({"transcript": [wording with {kind} and {place}], "answer": [line]}, from bench.hidden_lines_of) are the
    extra wordings of the hidden line that the stand-in obeys besides the practice wording of canned.injection: the test
    split's wordings reach the stand-in this way, never through the run choices the methods hold (fix round, item 6)."""
    markers = choices["markers"]
    claim = markers["claim"]
    mark = markers["ai"]
    tag = markers["source_tag"]
    ladder = choices["ladder"]
    inj = re.compile(choices["canned"]["injection"]["pattern"])
    state = {"grade": None}  # canned only: the grade of the visit being run, set by the bench; never a field
    obeys = bool(choices["canned"]["injection"].get("obeys", True))
    cert = choices["canned"].get("injection_certainty") or {}
    cert_pat = re.compile(cert["pattern"]) if cert.get("pattern") and cert.get("obeys", True) else None
    extra_inj = [_template_regex(t) for t in (hidden_lines or {}).get("transcript", [])]
    extra_cert = {ln.strip() for ln in (hidden_lines or {}).get("answer", [])}

    def injected(fields: Dict[str, str]) -> List[str]:
        lines: List[str] = []
        if not obeys:
            return lines
        for value in fields.values():
            for line in str(value).split("\n"):
                m = inj.match(line)
                if m:
                    action = "SEND %s TO %s" % (m.group(1), m.group(2))
                else:
                    m = next((x for x in (r.match(line) for r in extra_inj) if x), None)
                    action = "SEND %s TO %s" % (m.group("kind"), m.group("place")) if m else None
                if action and action not in lines:
                    lines.append(action)
        return lines

    def ai(prompt_id: str, fields: Dict[str, str]) -> str:
        name = _prompt_name(prompt_id)
        if name == "note_writer":
            out = ["VISIT NOTE (draft)", fields["transcript"][:600]]
        elif name == "plan":
            answer = fields["answer"]
            line = _claim_line(answer, claim)
            if line is None:
                first = next((ln for ln in answer.splitlines() if ln.strip()), "")
                line = ("%s %s %s" % (claim, first[:200], _first_tag(answer, choices))).rstrip()
            if obeys and any((cert_pat is not None and cert_pat.match(ln)) or ln.strip() in extra_cert
                             for ln in answer.split("\n")):
                # a hidden instruction in the answer: the stand-in states its claim at the top level (version 3)
                line = ("%s %s %s" % (claim, ladder["canned"][ladder["levels"][-1]], _first_tag(answer, choices))).rstrip()
            out = ["PLAN", line, mark]
        elif name == "patient_note":
            plan_text = fields["plan"]
            line = _claim_line(plan_text, claim)
            if line is None:
                line = "%s %s" % (claim, next((ln for ln in plan_text.splitlines() if ln.strip()), ""))
            out = ["FOR YOU", line, mark]
        else:
            return ""
        out.extend(injected(fields))
        return "\n".join(out)

    def set_visit_grade(grade) -> None:
        """The stand-in needs the expert grade to write its text. It arrives here, by the bench,
        and never through the fields of a call, so no export or call id can carry it."""
        state["grade"] = grade

    ai.set_visit_grade = set_visit_grade
    return ai


# ------------------------------------------------------ recording and replay

def recording_ai(inner: AI, sink: List[Dict[str, Any]]) -> AI:
    """Wraps an AI; each call is stored in sink as {call_id, prompt_id, fields, output}."""
    def ai(prompt_id: str, fields: Dict[str, str]) -> str:
        output = inner(prompt_id, fields)
        sink.append({"call_id": call_id_of(prompt_id, fields), "prompt_id": prompt_id,
                     "fields": dict(fields), "output": output})
        return output

    return ai


def replay_ai(rows: List[Dict[str, Any]]) -> AI:
    """Returns the stored text of a call, or raises AICallMissing."""
    table = {row["call_id"]: row["output"] for row in rows}

    def ai(prompt_id: str, fields: Dict[str, str]) -> str:
        cid = call_id_of(prompt_id, fields)
        if cid not in table:
            raise AICallMissing(cid, prompt_id, dict(fields))
        return table[cid]

    return ai
