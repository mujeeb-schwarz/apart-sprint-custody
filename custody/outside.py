"""The outside model's part (Version 3, 13 Nov): a second model, called through the Codex command-line program.

What it is used for: ideas for Experiment 1, changed texts for Experiment 2, the confirmation that a text states
more or less certainty, a second judge and the owner's 40 texts. The tool is tools/outside_texts.py; this module
holds the pieces and imports the standard library only. It shares no code and no word list with the readers of the
methods (custody/watch.py, gate.py, rules.py, judge.py and the config keys markers, ladder, readers): the
confirming program for rules 4 and 6 and the parser for judge answers below have their own small patterns (D: outside).

Every call is one plain run of

    codex exec --skip-git-repo-check -s read-only -m MODEL -c model_reasoning_effort=EFFORT -C NEWDIR -o FILE

with the prompt on standard input, in a new empty temporary folder. Settings (model, effort, batch sizes, time
limit, retries, limit phrases) come from D: outside.
"""
import difflib
import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

ROOT = Path(__file__).resolve().parents[1]
J = Dict[str, Any]


class OutsideError(Exception):
    """A bad input or a missing file; the tool prints it and exits with code 2."""


class LimitStop(Exception):
    """A usage limit stopped the calls; what was answered so far is kept. The tool exits with code 5."""


# ------------------------------------------------------------------ settings and files

def load_choices(path: Any = None) -> J:
    p = Path(str(path)) if path else ROOT / "config" / "design_choices.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OutsideError("cannot read %s: %s" % (p, exc))


def settings(choices: J) -> J:
    s = dict(choices["outside"])
    for key in ("fixed_args", "retry_wait_seconds", "limit_phrases"):
        s[key] = list(s[key])
    return s


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_jsonl(path: Any) -> List[J]:
    p = Path(str(path))
    if not p.exists():
        return []
    out = []
    for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError as exc:
                raise OutsideError("%s line %d is not JSON: %s" % (p, n, exc))
    return out


def write_jsonl(path: Any, rows: Iterable[J]) -> None:
    """Whole-file write through a temporary file, so a stop in the middle leaves the old file intact."""
    p = Path(str(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + ".tmp")
    with open(str(tmp), "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
    os.replace(str(tmp), str(p))


def append_jsonl(path: Any, row: J) -> None:
    p = Path(str(path))
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(str(p), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        fh.flush()


def prompt_file(choices: J, name: str, root: Any = None) -> str:
    pid = choices["outside"]["prompts"][name]
    p = Path(str(root)) / "prompts" / (pid + ".txt") if root else ROOT / "prompts" / (pid + ".txt")
    try:
        return p.read_text(encoding="utf-8")
    except OSError as exc:
        raise OutsideError("cannot read the prompt file %s: %s" % (p, exc))


def fill(template: str, fields: Dict[str, str]) -> str:
    """Put each {{name}} slot's value in. One pass: a value that holds a slot is not filled again."""
    return re.sub(r"\{\{(\w+)\}\}", lambda m: fields[m.group(1)] if m.group(1) in fields else m.group(0), template)


# ------------------------------------------------------------------ the call

_MODEL_LINE = re.compile(r"(?im)^\s*model\s*:\s*([A-Za-z0-9][A-Za-z0-9._:/-]*)\s*$")
_TOKENS = re.compile(r"(?is)tokens used\s*:?\s*([\d][\d,._ ]*)")


def parse_output(stdout: str, stderr: str, last_message: Optional[str]) -> Tuple[str, Optional[str], Optional[int]]:
    """(reply text, model named in the output, tokens used) from what the program printed and the file it wrote.

    The reply is the text of the last-message file when it holds one; otherwise the text after the last line that
    reads `codex` in the output, up to a line `tokens used`. The model is the value of a line `model: X`."""
    both = (stderr or "") + "\n" + (stdout or "")
    m = _MODEL_LINE.search(both)
    model = m.group(1) if m else None
    t = _TOKENS.search(both)
    tokens = None
    if t:
        digits = re.sub(r"[^\d]", "", t.group(1).split("\n")[0])
        tokens = int(digits) if digits else None
    if last_message is not None and last_message.strip():
        return last_message, model, tokens
    lines = (stdout or "").splitlines()
    at = None
    for i, line in enumerate(lines):
        if line.strip() == "codex":
            at = i
    if at is None:
        return "", model, tokens
    body = []
    for line in lines[at + 1:]:
        if line.strip().lower().startswith("tokens used"):
            break
        body.append(line)
    return "\n".join(body).strip("\n"), model, tokens


def build_command(codex_bin: str, model: str, effort: str, workdir: str, outfile: str, fixed_args: List[str]) -> List[str]:
    return [codex_bin] + list(fixed_args) + ["-m", model, "-c", "model_reasoning_effort=%s" % effort,
                                             "-C", workdir, "-o", outfile]


def one_attempt(cmd: List[str], prompt: str, timeout: float, outfile: str, workdir: str) -> J:
    t0 = time.time()
    try:
        p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=workdir, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"code": "timeout", "stdout": "", "stderr": "", "message": None, "seconds": time.time() - t0}
    except OSError as exc:
        return {"code": "oserror", "stdout": "", "stderr": exc.__class__.__name__, "message": None,
                "seconds": time.time() - t0}
    message = None
    try:
        message = Path(outfile).read_text(encoding="utf-8")
    except OSError:
        pass
    return {"code": p.returncode, "stdout": p.stdout, "stderr": p.stderr, "message": message,
            "seconds": time.time() - t0}


def role_settings(choices: J, role: Optional[str]) -> Tuple[str, str]:
    """(model, effort) of a role (writer, confirmer, judge2, ideas) from D: outside.models and outside.efforts."""
    o = choices["outside"]
    return (o.get("models", {}).get(role) or o["model"], o.get("efforts", {}).get(role) or o["effort"])


def ask(prompt: str, choices: Optional[J] = None, model: Optional[str] = None, effort: Optional[str] = None,
        codex_bin: Optional[str] = None, timeout: Optional[float] = None, retries: Optional[int] = None,
        waits: Optional[List[float]] = None, sleep: Callable[[float], None] = time.sleep,
        log: Optional[Callable[[J], None]] = None, purpose: str = "", role: Optional[str] = None) -> J:
    """One question to the outside model. Returns {"text", "model", "tokens", "error", "limit", "attempts",
    "seconds"}. `text` is None when there is an error. `model` is the model named in the output (None when the
    output names none). `error` is None, "usage_limit", "wrong_model", "no_program", "empty", "timeout" or
    "exit N". A usage limit and a wrong model are never retried; a timeout, an empty reply and a failed exit
    are retried `retries` times after the waits of D: outside.retry_wait_seconds. `log` gets one row per
    attempt (no prompt text)."""
    choices = choices or load_choices()
    s = settings(choices)
    role_model, role_effort = role_settings(choices, role)
    model = model or role_model
    effort = effort or role_effort
    codex_bin = codex_bin or s["codex_bin"]
    timeout = timeout if timeout is not None else s["timeout_seconds"]
    retries = s["retries"] if retries is None else retries
    waits = list(s["retry_wait_seconds"] if waits is None else waits)
    phrases = [p.lower() for p in s["limit_phrases"]]
    result: J = {"text": None, "model": None, "tokens": None, "error": None, "limit": False, "attempts": 0, "seconds": 0.0}
    for attempt in range(retries + 1):
        work = tempfile.mkdtemp(prefix="outside_work_")
        outdir = tempfile.mkdtemp(prefix="outside_out_")
        outfile = os.path.join(outdir, "last_message.txt")
        try:
            cmd = build_command(codex_bin, model, effort, work, outfile, s["fixed_args"])
            got = one_attempt(cmd, prompt, timeout, outfile, work)
        finally:
            shutil.rmtree(work, ignore_errors=True)
            shutil.rmtree(outdir, ignore_errors=True)
        text, named, tokens = parse_output(got["stdout"], got["stderr"], got["message"])
        result.update({"model": named, "tokens": tokens, "attempts": attempt + 1,
                       "seconds": result["seconds"] + got["seconds"]})
        code = got["code"]
        error: Optional[str] = None
        if code == "oserror":
            error = "no_program"
        elif code == "timeout":
            error = "timeout"
        elif code != 0 or not text.strip():
            shown = ((got["stdout"] or "") + "\n" + (got["stderr"] or "")).lower()
            if any(p in shown for p in phrases):
                error = "usage_limit"
            else:
                error = "exit %s" % code if code != 0 else "empty"
        elif named is not None and named != model:
            error = "wrong_model"
        if log is not None:
            log({"purpose": purpose, "model_asked": model, "model_named": named, "tokens": tokens,
                 "seconds": round(got["seconds"], 2), "attempt": attempt, "error": error, "effort": effort})
        if error is None:
            result["text"] = text
            result["error"] = None
            return result
        result["error"] = error
        if error == "usage_limit":
            result["limit"] = True
            return result
        if error in ("wrong_model", "no_program"):
            return result
        if attempt < retries:
            sleep(waits[min(attempt, len(waits) - 1)] if waits else 0)
    return result


# ------------------------------------------------------------------ batches between delimiters

def delim(choices: J, kind: str, n: int, side: str) -> str:
    return choices["outside"]["delimiters"][kind][side].replace("{n}", str(n))


def frame(choices: J, kind: str, n: int, body: str) -> str:
    return "%s\n%s\n%s" % (delim(choices, kind, n, "begin"), body.strip("\n"), delim(choices, kind, n, "end"))


def parse_framed(choices: J, reply: str, kind: str, numbers: List[int]) -> Dict[int, str]:
    """Each wanted number's text between its two delimiter lines. Strict: a number is returned only when its
    begin line and its end line each appear exactly once, whole and on their own line, the end after the begin.
    A reply that holds a delimiter line of a number nobody asked for returns nothing at all."""
    lines = (reply or "").splitlines()
    marker = "\x00"  # stands for the number while the template is escaped
    begin_t = choices["outside"]["delimiters"][kind]["begin"].replace("{n}", marker)
    end_t = choices["outside"]["delimiters"][kind]["end"].replace("{n}", marker)
    begin_re = re.compile("^" + re.escape(begin_t).replace(re.escape(marker), r"(\d+)") + "$")
    end_re = re.compile("^" + re.escape(end_t).replace(re.escape(marker), r"(\d+)") + "$")
    begins: Dict[int, List[int]] = {}
    ends: Dict[int, List[int]] = {}
    for i, line in enumerate(lines):
        s = line.strip()
        mb, me = begin_re.match(s), end_re.match(s)
        if mb:
            begins.setdefault(int(mb.group(1)), []).append(i)
        if me:
            ends.setdefault(int(me.group(1)), []).append(i)
    wanted = set(numbers)
    if (set(begins) | set(ends)) - wanted:
        return {}
    out: Dict[int, str] = {}
    for n in numbers:
        b, e = begins.get(n, []), ends.get(n, [])
        if len(b) == 1 and len(e) == 1 and e[0] > b[0]:
            out[n] = "\n".join(lines[b[0] + 1:e[0]])
    return out


def ask_framed(choices: J, template_name: str, slot: str, kind: str, bodies: List[str], extra: Dict[str, str],
               ask_fn: Callable[[str, str], J], root: Any = None,
               parse: Optional[Callable[[str, List[int]], Dict[int, str]]] = None) -> Tuple[Dict[int, str], J, Optional[str]]:
    """Send `bodies` (numbered from 1) as one call in the prompt file `template_name`, with their framed text in
    the slot `slot`. Returns (the parsed texts by number, the ask result, the error). The reply is parsed between
    delimiters unless `parse(reply, numbers)` is given."""
    framed = "\n\n".join(frame(choices, kind, i, b) for i, b in enumerate(bodies, 1))
    fields = dict(extra)
    fields.update({slot: framed, "count": str(len(bodies)),
                   "begin_example": delim(choices, kind, 1, "begin"), "end_example": delim(choices, kind, 1, "end")})
    prompt = fill(prompt_file(choices, template_name, root), fields)
    res = ask_fn(prompt, template_name)
    if res["error"]:
        return {}, res, res["error"]
    numbers = list(range(1, len(bodies) + 1))
    if parse is not None:
        return parse(res["text"], numbers), res, None
    return parse_framed(choices, res["text"], kind, numbers), res, None


# ------------------------------------------------------------------ a description of the words flow (ideas)

def _lane_steps(wiring: J, lane: str) -> List[J]:
    ids: List[str] = []
    for ln in wiring["plumbing"]["lanes"]:
        if ln["id"] == lane:
            ids = list(ln["steps"])
    by_id = {s["id"]: s for s in wiring["plumbing"]["steps"]}
    return [by_id[i] for i in ids if i in by_id]


def lane_kinds(wiring: J, lane: str) -> List[str]:
    kinds: List[str] = []
    for st in _lane_steps(wiring, lane):
        for k in list(st.get("reads") or []) + ([st["makes"]] if st.get("makes") else []):
            if k not in kinds:
                kinds.append(k)
    return kinds


def describe_flow(wiring: J, choices: J, lane: str = "words") -> str:
    """A plain description of one lane, made from the wiring and D: holds, and nothing else: the steps, the places
    with what each may hold and for how long, the allowed handovers, the deletions, the three rules and the note
    that a log exists. It says nothing of any checker, monitor, review or word list."""
    steps = _lane_steps(wiring, lane)
    kinds = lane_kinds(wiring, lane)
    plumbing = wiring["plumbing"]
    holds = choices["holds"]
    promise = wiring["promise"]["places"]
    say = choices["outside"]["ideas"]
    out: List[str] = [say["intro_flow"]]
    for i, st in enumerate(steps, 1):
        reads = ", ".join(st.get("reads") or []) or "nothing"
        makes = ("makes a new %s" % st["makes"]) if st.get("makes") else "makes nothing new"
        out.append("%d. %s (at the place %s): %s Reads: %s. It %s." % (i, st["id"], st["place"], st.get("says", ""),
                                                                      reads, makes))
    starts = [e for e in plumbing.get("intake", []) if e["kind"] in kinds]
    if starts:
        out.append("")
        out.append("At the start of a visit: " + "; ".join("the %s sits at %s" % (e["kind"], e["place"]) for e in starts) + ".")
    out.append("")
    out.append("Places, and what each may hold (a hold is the longest time a copy may stay there, counted in ticks from its arrival):")
    for p in promise:
        held = {k: v for k, v in p["may_hold"].items() if k in kinds}
        if p["named"] and not held:
            continue
        if not p["named"]:
            out.append("- %s (%s): not named to the patient; it may hold nothing." % (p["id"], p["who"]))
            continue
        parts = []
        for k, h in held.items():
            parts.append("%s (%s)" % (k, "may stay" if h is None else "at most %d ticks" % holds[h]))
        out.append("- %s (%s): named to the patient; may hold %s." % (p["id"], p["who"], "; ".join(parts)))
    step_ids = {s["id"] for s in steps}
    moves = [m for m in plumbing["moves"] if m["step"] in step_ids]
    detours = {d["at"]: d for d in plumbing.get("detours", [])}
    detour_of = {}
    for d in plumbing.get("detours", []):
        for act in d["do"]:
            if "send" in act:
                detour_of.setdefault(act["send"], d)
    out.append("")
    out.append("Handovers that are allowed:")
    for m in moves:
        line = "- %s: after the step %s has run, the %s goes from %s to %s." % (m["id"], m["step"], m["kind"], m["from"], m["to"])
        if m.get("detour_only") and m["id"] in detour_of:
            line += " This one happens only on a rare event: %s" % detour_of[m["id"]]["says"]
        out.append(line)
    place_hold = {p["id"]: p["may_hold"] for p in promise}
    move_by_id = {m["id"]: m for m in plumbing["moves"]}
    out.append("")
    out.append("Deletions that must happen:")
    for d in plumbing["duties"]:
        if d["kind"] not in kinds:
            continue
        hold = place_hold.get(d["place"], {}).get(d["kind"])
        when = ""
        if d.get("after") in move_by_id:
            mv = move_by_id[d["after"]]
            when = "once the handover %s (%s, from %s to %s) has been delivered" % (mv["id"], mv["kind"], mv["from"], mv["to"])
        elif d.get("after_step"):
            when = "once the step %s has run" % d["after_step"]
        limit = "" if hold is None else ", and in any case within %d ticks of its arrival" % holds[hold]
        out.append("- %s: the copy of the %s at %s is deleted %s%s." % (d["id"], d["kind"], d["place"], when, limit))
    out.append("")
    out.append("The three rules")
    out.extend(say["rules"])
    out.append("")
    out.append(say["log_note"])
    return "\n".join(out)


# ------------------------------------------------------------------ the confirming program for rules 4 and 6

def _confirm_cfg(choices: J) -> J:
    return choices["outside"]["confirm"]


def source_ids(text: str, choices: J) -> List[str]:
    """Source-like ids in a text, in order of first appearance, with spaces around the colon taken out."""
    rx = re.compile(_confirm_cfg(choices)["source_id"], re.IGNORECASE)
    seen: List[str] = []
    for m in rx.finditer(text):
        sid = re.sub(r"\s+", "", m.group(0)).lower()
        if sid not in seen:
            seen.append(sid)
    return seen


def _source_segments(text: str, choices: J) -> List[str]:
    cfg = _confirm_cfg(choices)
    rx_b = re.compile(cfg["bracket"])
    rx_id = re.compile(cfg["source_id"], re.IGNORECASE)
    word = cfg["source_word"].lower()
    return [m.group(0) for m in rx_b.finditer(text) if word in m.group(0).lower() or rx_id.search(m.group(0))]


def says_ai_wrote(text: str, choices: J) -> bool:
    cfg = _confirm_cfg(choices)
    low = text.lower()
    if any(w.lower() in low for w in cfg["ai_wording"]):
        return True
    return re.search(cfg["ai_word"], text) is not None


def _squash(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _set_aside(rule_kind: str, honest: str, changed: str, choices: J) -> Tuple[str, str]:
    """Both texts with the segments the change is allowed to touch taken out: for a source change the bracketed
    source segments and the source ids; for a mark change every line that says an AI wrote it, and in the changed
    text every line the honest text did not have."""
    cfg = _confirm_cfg(choices)
    if rule_kind in ("source_removed", "source_wrong"):
        rx_id = re.compile(cfg["source_id"], re.IGNORECASE)

        def strip(t: str) -> str:
            for seg in _source_segments(t, choices):
                t = t.replace(seg, " ")
            return rx_id.sub(" ", t)
        return _squash(strip(honest)), _squash(strip(changed))
    honest_lines = [ln.strip() for ln in honest.splitlines()]
    keep_h = [ln for ln in honest.splitlines() if not says_ai_wrote(ln, choices)]
    keep_c = [ln for ln in changed.splitlines() if not says_ai_wrote(ln, choices) and ln.strip() in honest_lines]
    return _squash("\n".join(keep_h)), _squash("\n".join(keep_c))


def similarity(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def confirm_program(kind: str, honest: str, changed: Optional[str], choices: J) -> Tuple[bool, str]:
    """(confirmed, reason) for a changed text of kind source_removed, source_wrong, mark_removed or mark_replaced."""
    if changed is None or not changed.strip():
        return False, "no changed text"
    if changed.strip() == honest.strip():
        return False, "the text is unchanged"
    cfg = _confirm_cfg(choices)
    honest_ids = source_ids(honest, choices)
    if kind == "source_removed":
        if _source_segments(changed, choices):
            return False, "a bracketed source segment remains"
        left = [i for i in honest_ids if i in source_ids(changed, choices)]
        if left:
            return False, "an honest source id remains"
    elif kind == "source_wrong":
        named = source_ids(changed, choices)
        if not named:
            return False, "no source-like id is named"
        if any(i in named for i in honest_ids):
            return False, "an honest source id remains"
    elif kind in ("mark_removed", "mark_replaced"):
        if says_ai_wrote(changed, choices):
            return False, "wording that says an AI wrote the text remains"
        if kind == "mark_replaced":
            have = {ln.strip() for ln in honest.splitlines()}
            if not any(ln.strip() and ln.strip() not in have for ln in changed.splitlines()):
                return False, "no new line was added"
    else:
        raise OutsideError("the kind %r is not confirmed by the program" % kind)
    a, b = _set_aside(kind, honest, changed, choices)
    sim = similarity(a, b)
    if sim < cfg["min_similarity"]:
        return False, "the rest of the text changed too much (%.2f alike)" % sim
    return True, "ok"


# ------------------------------------------------------------------ the pairs for rule 5

def pair_body(choices: J, honest: str, changed: str, changed_first: bool) -> str:
    lab = _confirm_cfg(choices)["pair_labels"]
    first, second = (changed, honest) if changed_first else (honest, changed)
    return "%s:\n%s\n\n%s:\n%s" % (lab["a"], first.strip("\n"), lab["b"], second.strip("\n"))


def lot_order(seed: Any, plant_id: str) -> bool:
    """True when the changed text is shown first (as Text A), drawn by lot from the seed and the plant id."""
    return random.Random("%s:confirm:%s" % (seed, plant_id)).random() < 0.5


def parse_pair_answers(choices: J, reply: str, numbers: List[int]) -> Dict[int, str]:
    """The answer (A, B or same) of each wanted pair, from lines `PAIR <n>: <answer>`; strict: a pair with no
    line, or with two lines, is left out."""
    rx = re.compile(_confirm_cfg(choices)["answer_line"])
    found: Dict[int, List[str]] = {}
    for line in (reply or "").splitlines():
        m = rx.match(line)
        if m:
            found.setdefault(int(m.group(1)), []).append(m.group(2))
    return {n: found[n][0] for n in numbers if len(found.get(n, [])) == 1}


def pair_matches(direction: str, changed_first: bool, answer: str) -> bool:
    """True when the answer says the changed text is the more (direction "more") or less ("less") certain one."""
    if answer == "same":
        return False
    changed_is = "A" if changed_first else "B"
    says_changed_more = (answer == changed_is)
    return says_changed_more if direction == "more" else not says_changed_more


# ------------------------------------------------------------------ the judge's answers, read by the outside program

_VERDICT = re.compile(r"^verdict\s*:?\s*(kept|broken)$")
_LEVEL = re.compile(r"^level\s*:?\s*([a-z ]+)$")
_BARE = re.compile(r"^(kept|broken|none|no data|very low|low|moderate|high)$")


def read_answer(text: str, levels: Iterable[str] = ()) -> Optional[Tuple[str, str]]:
    """("verdict", kept|broken) or ("level", a level or none) from a judge-style answer, or None when it holds no
    such line or more than one differing. A bare word (the owner's page) counts as well."""
    allowed = (set(levels) | {"none"}) if levels else None
    found: List[Tuple[str, str]] = []
    for line in (text or "").splitlines():
        s = re.sub(r"[*`_]", " ", line)
        s = re.sub(r"\s+", " ", s.replace("-", " ")).strip(" .,;:!").lower()
        m = _VERDICT.match(s)
        if m:
            found.append(("verdict", m.group(1)))
            continue
        m = _LEVEL.match(s)
        if m and (allowed is None or m.group(1).strip() in allowed):
            found.append(("level", m.group(1).strip()))
            continue
        m = _BARE.match(s)
        if m:
            w = m.group(1)
            found.append(("verdict", w) if w in ("kept", "broken") else ("level", w))
    if not found or len(set(found)) > 1:
        return None
    return found[0]


def agreement(first: Dict[str, str], second: Dict[str, str], rule_of: Dict[str, Any],
              levels: Iterable[str] = ()) -> J:
    """How often two judges give the same answer, for each of the judge's questions (by rule).

    `first` and `second` are answers by call id; `rule_of` gives each call id's rule. Only call ids in both are
    compared. An answer that cannot be read counts under `unreadable`, not under `agree`. Returns
    {rule: {"n", "agree", "unreadable", "rate"}} with rate None when n is 0."""
    out: J = {}
    for cid in sorted(set(first) & set(second)):
        rule = str(rule_of.get(cid))
        row = out.setdefault(rule, {"n": 0, "agree": 0, "unreadable": 0, "rate": None})
        a, b = read_answer(first[cid], levels), read_answer(second[cid], levels)
        if a is None or b is None:
            row["unreadable"] += 1
            continue
        row["n"] += 1
        row["agree"] += 1 if a == b else 0
    for row in out.values():
        row["rate"] = (row["agree"] / row["n"]) if row["n"] else None
    return out


# ------------------------------------------------------------------ the judge's prompts, read back

def parse_judge_prompt(prompt: str, choices: J) -> J:
    """The text, the true sources and the rule line of a shown judge prompt, plus its kind of text."""
    cfg = choices["outside"]["judge"]
    lines = prompt.split("\n")
    dash = re.compile(cfg["text_start"])
    idx = [i for i, ln in enumerate(lines) if dash.match(ln.strip())]
    text = ""
    for a in idx:
        for b in idx:
            if b > a and "".join(lines[b + 1:b + 4]).strip().startswith("The true sources"):
                text = "\n".join(lines[a + 1:b])
                break
        if text:
            break
    m = re.search(r"(?m)^The true sources for this advice are these ids:\s*(.*)$", prompt)
    sources = m.group(1).strip() if m else ""
    r = re.search(r"(?ms)^Your question\s*\n(Rule (\d)\..*?)\n\s*\nHow to answer", prompt)
    rule_line = r.group(1).strip() if r else ""
    rule = int(r.group(2)) if r else None
    kind = "answer"
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    for k, word in cfg["kind_of_text"].items():
        if first.upper().startswith(word.upper()):
            kind = k
    return {"text": text, "true_sources": sources, "rule_line": rule_line, "rule": rule, "kind": kind}


def judge_calls(live_dir: Any, choices: J, extra_files: Iterable[Any] = ()) -> List[J]:
    """The judge prompts as shown, read from the live folder: handout/pending_judge.jsonl, its parts, the copy
    the tool keeps in private/judge_calls_kept.jsonl, and any extra file. Each row: call_id, prompt, prompt_fp
    and the parsed fields. A call id that appears twice is one call (the first row wins)."""
    live = Path(str(live_dir))
    files = [live / "handout" / "pending_judge.jsonl"]
    parts = live / "handout" / "pending_judge_parts"
    if parts.exists():
        files += sorted(parts.glob("*.jsonl"))
    files.append(live / "private" / "judge_calls_kept.jsonl")
    files += [Path(str(f)) for f in extra_files]
    seen: Dict[str, J] = {}
    for f in files:
        for row in read_jsonl(f):
            cid = row.get("call_id")
            if isinstance(cid, str) and isinstance(row.get("prompt"), str) and cid not in seen:
                parsed = parse_judge_prompt(row["prompt"], choices)
                seen[cid] = dict(row, **parsed)
    return [seen[k] for k in sorted(seen)]


def keep_judge_calls(live_dir: Any, choices: J) -> int:
    """Copy the judge calls now in the handout into private/judge_calls_kept.jsonl (added to, never shortened),
    because a finished run removes the handout files. Returns the number of calls in the kept file."""
    live = Path(str(live_dir))
    kept_path = live / "private" / "judge_calls_kept.jsonl"
    have = {r["call_id"] for r in read_jsonl(kept_path)}
    files = [live / "handout" / "pending_judge.jsonl"]
    for f in files:
        for row in read_jsonl(f):
            if row.get("call_id") not in have and isinstance(row.get("prompt"), str):
                append_jsonl(kept_path, {k: row[k] for k in ("call_id", "prompt_id", "prompt", "prompt_fp", "expects")
                                         if k in row})
                have.add(row["call_id"])
    return len(have)


def first_answers(live_dir: Any) -> Dict[str, str]:
    """The Claude judge's stored answers, by exported call id (through the private id map to the real ids)."""
    live = Path(str(live_dir))
    stored = {r["call_id"]: r["output"] for r in read_jsonl(live / "answers.jsonl")}
    idmap_path = live / "private" / "id_map.json"
    idmap = json.loads(idmap_path.read_text(encoding="utf-8")) if idmap_path.exists() else {}
    out: Dict[str, str] = {}
    for cid, reals in idmap.items():
        for r in reals:
            if r in stored:
                out[cid] = stored[r]
                break
    for cid, text in stored.items():
        out.setdefault(cid, text)
    return out


def case_of_text(run_dir: Any) -> Dict[str, str]:
    """text -> case id, from a run folder's texts.jsonl (used to keep two texts of one case out of one call)."""
    out: Dict[str, str] = {}
    for row in read_jsonl(Path(str(run_dir)) / "texts.jsonl"):
        item = row.get("item") or {}
        if isinstance(item.get("text"), str) and item.get("visit_id"):
            out.setdefault(item["text"], item["visit_id"])
    return out


def draw_calls(calls: List[J], n: int, seed: Any, case_of: Optional[Dict[str, str]] = None) -> List[J]:
    """N judge calls by lot (seeded), never two with the same text, and each tagged with its case when known."""
    pool = sorted(calls, key=lambda c: c["call_id"])
    rng = random.Random("%s:judge2" % seed)
    rng.shuffle(pool)
    chosen: List[J] = []
    used = set()
    for c in pool:
        if len(chosen) >= n:
            break
        if c["text"] in used:
            continue
        used.add(c["text"])
        c = dict(c)
        c["case"] = (case_of or {}).get(c["text"])
        chosen.append(c)
    return chosen


def make_batches(calls: List[J], size: int) -> List[List[J]]:
    """The calls in parts of at most `size`, never two calls of one known case in one part (a call of unknown case
    is never held back)."""
    left = list(calls)
    parts: List[List[J]] = []
    while left:
        part: List[J] = []
        later: List[J] = []
        used = set()
        for c in left:
            case = c.get("case")
            if len(part) < size and not (case and case in used):
                part.append(c)
                if case:
                    used.add(case)
            else:
                later.append(c)
        parts.append(part)
        left = later
    return parts
