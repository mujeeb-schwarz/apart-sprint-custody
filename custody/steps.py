"""The steps of the chain: the six of the wiring and the janitor (version 3: the question and the AI answer are gone;
the answer enters the advice flow ready-made and the step `answer` hands it on).

Every step has one signature, Step = Callable[[StepContext, List[Item]], StepOutput].
A step reads only what its context and inbox give it. The expert grade is not in any field of an AI call (13 Nov).
"""
import re
from typing import Dict, List, Optional

from custody.core import Item, StepContext, StepOutput, action_line, make_item_id


def _empty() -> StepOutput:
    return StepOutput(items=[], requests=[], deletes=[])


def _first(inbox: List[Item], kind: str) -> Optional[Item]:
    for it in inbox:
        if it.kind == kind:
            return it
    return None


def _text(inbox: List[Item], kind: str) -> str:
    it = _first(inbox, kind)
    return it.text if it is not None else ""


def every_prompt_fields(choices) -> Dict[str, str]:
    """The three fields every prompt gets, filled by the caller of ai()."""
    markers = choices["markers"]
    return {
        "claim_marker": markers["claim"],
        "source_open": markers["source_tag"]["open"],
        "ai_mark": markers["ai"],
    }


def split_actions(text: str, choices):
    """Split a text into (text without action lines, list of send requests).

    A line is a send when it is the canonical pattern, or (the lenient reading, core.action_line) when
    it reads `send <kind> to <place>` once markdown, list markers, backticks, spaces, closing punctuation
    and case are set aside. A whole line that starts "send " and holds " to " with other names causes no
    send and stays in the text (a near miss, counted by the scorer from the texts)."""
    action = choices["markers"].get("action") or {}
    if not action.get("pattern"):
        return text, []
    kept: List[str] = []
    requests = []
    for line in text.split("\n"):
        read = action_line(line, choices)
        if read is not None and read[0] == "send":
            requests.append({"op": "send", "kind": read[1], "to": read[2],
                             "logged": bool(action.get("logged", True))})
            if not action.get("strip_from_text", True):
                kept.append(line)
        else:
            kept.append(line)
    return "\n".join(kept), requests


def _make(ctx: StepContext, inbox: List[Item], kind: str, text: str) -> StepOutput:
    """Make the one item of a step. Action lines turn into send requests."""
    text, requests = split_actions(text, ctx.choices)
    item = Item(
        item_id=make_item_id(ctx.visit.visit_id, kind, ctx.step, text),
        visit_id=ctx.visit.visit_id,
        kind=kind,
        text=text,
        made_by=ctx.step,
        parents=[i.item_id for i in inbox],
    )
    return StepOutput(items=[item], requests=requests, deletes=[])


def _ai_text(ctx: StepContext, fields: Dict[str, str]) -> str:
    prompt_id = ctx.choices["prompts"][ctx.spec["prompt"]]
    full = dict(fields)
    full.update(every_prompt_fields(ctx.choices))
    return ctx.ai(prompt_id, full)


# ------------------------------------------------------------ program steps

def transcriber(ctx, inbox):
    """Holds the transcript and passes it on; makes nothing (13 Nov, version 2: the data set has no audio)."""
    return _empty()


def answer(ctx, inbox):
    """Hands the tool's answer to the doctor: a program that reads the answer and makes nothing new (version 3)."""
    return _empty()


def record(ctx, inbox):
    """Files the draft in the chart as the note, text unchanged."""
    return _make(ctx, inbox, ctx.spec["makes"], _text(inbox, "note_draft"))


def janitor(ctx, inbox):
    return StepOutput(items=[], requests=[], deletes=[i.item_id for i in inbox])


# ------------------------------------------------------------------ AI steps

def note_writer(ctx, inbox):
    text = _ai_text(ctx, {"transcript": _text(inbox, "transcript")})
    return _make(ctx, inbox, "note_draft", text)


def plan(ctx, inbox):
    fields = {"question": _text(inbox, "question"), "answer": _text(inbox, "answer")}
    return _make(ctx, inbox, "plan", _ai_text(ctx, fields))


def patient_note(ctx, inbox):
    return _make(ctx, inbox, "patient_note", _ai_text(ctx, {"plan": _text(inbox, "plan")}))


STEPS = {
    "transcriber": transcriber,
    "note_writer": note_writer,
    "record": record,
    "answer": answer,
    "plan": plan,
    "patient_note": patient_note,
    "janitor": janitor,
}
