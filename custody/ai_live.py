"""Live AI answers made by helpers outside the program.

The program holds no key and calls no model. A live answer comes in three moves:

1. The program works out which calls it needs and writes the missing ones to three
   files (`pending_steps.jsonl`, `pending_methods.jsonl`, `pending_judge.jsonl`; see
   SETS), each with its call id and its full prompt, each in a seeded shuffle. Then it stops.
2. Helpers answer them and write the answers to a file, one JSON object per line:
   {"call_id", "prompt_fp", "output"}.
3. The program checks each answer against the pending call it claims to answer
   and stores it in `answers.jsonl`. It then carries on and repeats until no
   call is missing.

Every stored answer is kept for good, so a run can be scored again with no AI.
The fingerprint of an answer's prompt (`prompt_fp`) is the sha256 of the full
prompt text as it was shown to the helper. An answer whose fingerprint differs,
whose call id was never asked for, or that contradicts an earlier answer, is
refused and nothing of the file is lost: the other lines are still taken.

This module imports the standard library and custody.core only. What it needs
from the chain (how a prompt is rendered, how a call id is made) arrives as an
argument, as the frame asks.
"""
import json
import random
import re
import shutil
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from custody.core import AICallMissing, ContractError, DataError, J, SALT_FIELD, canon, fingerprint, strip_lead, strip_line

ANSWERS = "answers.jsonl"
LEGACY_PENDING = "pending.jsonl"  # no longer written (13 Nov): one file mixed steps and methods
SETS = ("steps", "methods", "judge")  # step calls, watcher and reviewer calls, judge calls
HANDOUT = "handout"  # what helpers are given (14 Nov, H1): the three pending sets and their parts, nothing else
PRIVATE = "private"  # what stays with the program: the salt, the token map, the id map
ID_MAP = "id_map.json"  # exported call id -> the real call ids it stands for

Render = Callable[[str, Dict[str, str]], str]  # (prompt_id, fields) -> the full prompt text
CallId = Callable[[str, Dict[str, str]], str]  # (prompt_id, fields) -> call id
Validator = Callable[[str, J], None]  # (output, pending call) -> raises ContractError


# ------------------------------------------------------------------ files

def _read_jsonl(path: Path) -> List[J]:
    if not path.exists():
        return []
    out = []
    try:
        with open(str(path), encoding="utf-8") as fh:
            for number, line in enumerate(fh, 1):
                if line.strip():
                    row = json.loads(line)
                    if not isinstance(row, dict):
                        raise ValueError("line %d is not an object" % number)
                    out.append(row)
    except (OSError, ValueError) as exc:
        raise DataError("cannot read %s: %s" % (path, exc))
    return out


def _write_jsonl(path: Path, rows: Iterable[J]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "w", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(canon(row) + "\n")


def _append_jsonl(path: Path, rows: Iterable[J]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "a", encoding="utf-8", newline="\n") as fh:
        for row in rows:
            fh.write(canon(row) + "\n")


# --------------------------------------------------------- the answer store

class AnswerStore:
    """Live answers by call id, in `<directory>/answers.jsonl`. Appended to, never rewritten."""

    def __init__(self, directory: Any):
        self.dir = Path(str(directory))
        self.path = self.dir / ANSWERS

    def rows(self) -> List[J]:
        return _read_jsonl(self.path)

    def answers(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for row in self.rows():
            out[row["call_id"]] = row["output"]
        return out

    def unusable(self) -> Dict[str, str]:
        """call id -> reason, for the stored answers marked unusable (kept as given, never asked again)."""
        return {r["call_id"]: r.get("reason", "") for r in self.rows() if r.get("usable") is False}

    def add(self, rows: List[J]) -> None:
        known = self.answers()
        fresh = []
        for row in rows:
            if row["call_id"] in known:
                if known[row["call_id"]] != row["output"]:
                    raise ContractError("call %s already has a different stored answer" % row["call_id"])
                continue
            known[row["call_id"]] = row["output"]
            new = {"call_id": row["call_id"], "prompt_id": row["prompt_id"],
                   "prompt_fp": row["prompt_fp"], "output": row["output"]}
            if row.get("usable") is False:
                new["usable"] = False
                new["reason"] = row.get("reason", "")
            if row.get("extra_lines"):
                new["extra_lines"] = list(row["extra_lines"])  # 15 Nov: lines of a monitor or review answer kept apart
            fresh.append(new)
        if fresh:
            _append_jsonl(self.path, fresh)


# ------------------------------------------------------- missing calls

# a case id (c0001, q0001, or v0001 of the retired joined list), and a unit of a plan: the case id with '+<plant id>'
# and '+r<n>' after it (custody/units.py, version 3). Neither the method letter nor a plant id may reach a helper.
_ID = r"[cqv]\d{4}(?:\+[A-Za-z0-9-]+)*"
_RUN_ID = re.compile(r"(%s\.)(A\+|A|B|C)(\.r\d+)" % _ID)
_COND_WORD = re.compile(r"\b(cond(?:ition)?s?\s*[=:]\s*)(A\+|A|B|C)(?![\w+])", re.IGNORECASE)


def mask_method(text: str) -> str:
    """The condition letter of a run id or handover id, replaced by X.

    Some prompts carry the steps' own log, whose lines hold the run id (for example v0001.A+.r0#3).
    A helper must not learn the method from it, so the prompt written to the pending file shows X.
    The call id is made from the real prompt and is unchanged; the fingerprint is over what is shown.
    """
    return _COND_WORD.sub(r"\1X", _RUN_ID.sub(r"\1X\3", text))


_VISIT_ID = re.compile(r"\b%s(?![\w+-])" % _ID)
SALT_FILE = "salt.private"
TOKENS_FILE = "visit_tokens.private.json"


def case_of(unit_id: str) -> str:
    """The case a unit was made from: the id up to the first '+' (a case's own id is returned as it is)."""
    return unit_id.split("+", 1)[0]


def handout_dir(live_dir: Any) -> Path:
    return Path(str(live_dir)) / HANDOUT


def private_dir(live_dir: Any) -> Path:
    return Path(str(live_dir)) / PRIVATE


def read_idmap(live_dir: Any) -> Dict[str, List[str]]:
    """The private map from each exported call id to the real call ids it stands for (empty when none)."""
    path = private_dir(live_dir) / ID_MAP
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def save_idmap(live_dir: Any, calls: Iterable[J]) -> None:
    """Add the `real` ids of the calls being exported to the private id map (merged, never shortened)."""
    mp = read_idmap(live_dir)
    for c in calls:
        have = mp.setdefault(c["call_id"], [])
        for r in c.get("real") or []:
            if r not in have:
                have.append(r)
    private_dir(live_dir).mkdir(parents=True, exist_ok=True)
    (private_dir(live_dir) / ID_MAP).write_text(canon(mp) + "\n", encoding="utf-8")


def exported_id(prompt_id: str, template_fp: str, shown: str) -> str:
    """The call id a helper sees: made only from what the helper is shown (the prompt id, the template's
    fingerprint and the prompt text as shown, with its opaque tokens). It carries nothing of the visit or
    the condition, so it cannot be worked out back to them (14 Nov, H1)."""
    return fingerprint([prompt_id, template_fp, shown])


class VisitTokens:
    """Opaque stand-ins for visit ids in the prompts of the checkers (watcher, reviewer, judge) (13 Nov, G4).

    A token is derived from the visit id and a random salt that is created once for the run folder and kept in a
    private file (`salt.private`) that is never exported; the same visit always gets the same token, so a prompt
    keeps its fingerprint from round to round. The program keeps the mapping (`visit_tokens.private.json`)."""

    def __init__(self, live_dir: Any, prompt_ids: Iterable[str]) -> None:
        import secrets
        self.dir = private_dir(live_dir)
        self.prompt_ids = set(prompt_ids)
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / SALT_FILE
        if not path.exists():
            path.write_text(secrets.token_hex(16) + "\n", encoding="utf-8")
        self.salt = path.read_text(encoding="utf-8").strip()
        mp = self.dir / TOKENS_FILE
        self.mapping: Dict[str, str] = json.loads(mp.read_text(encoding="utf-8")) if mp.exists() else {}

    def token_of(self, visit_id: str) -> str:
        token = "k" + fingerprint("%s|%s" % (self.salt, visit_id))[:9]
        self.mapping[token] = visit_id
        return token

    def mask(self, prompt_id: str, prompt: str) -> str:
        """mask_method, and for a checker's prompt every visit id replaced by its token."""
        text = mask_method(prompt)
        if prompt_id in self.prompt_ids:
            text = _VISIT_ID.sub(lambda m: self.token_of(m.group(0)), text)
        return text

    def save(self) -> None:
        (self.dir / TOKENS_FILE).write_text(canon(self.mapping) + "\n", encoding="utf-8")


def make_call(call_id: str, prompt_id: str, prompt: str, expects: str,
              mask: Optional[Callable[[str, str], str]] = None, template_fp: str = "",
              cases: Optional[Iterable[str]] = None, salt: Optional[str] = None) -> J:
    """One missing call as helpers see it: its id, its prompt (masked) and the kind of answer wanted.
    The exported id is made from what is shown (exported_id); the real call id goes in `real`, which is
    written to the private id map and never to the handout. The fields of the call are not written, only
    the finished prompt. Calls that show one prompt are one row, one answer serves all their real ids.

    `cases` names the case(s) the call belongs to (Version 2, part 3): the ones the caller announced, and any
    visit id found in the unmasked prompt. They are kept in the private `cases` list of the row (never handed
    out) so that export_sets can keep two calls of one case out of the same part."""
    shown = mask(prompt_id, prompt) if mask else mask_method(prompt)
    found = sorted(set(case_of(c) for c in list(cases or []) + _VISIT_ID.findall(prompt)))
    call = {"call_id": exported_id(prompt_id, template_fp, shown), "also": [], "real": [call_id],
            "prompt_id": prompt_id, "prompt": shown, "prompt_fp": fingerprint(shown), "expects": expects}
    if salt:  # version 3, the repeat check: the same prompt asked again is a call of its own (the salt is never handed out)
        call["salt"] = salt
        call["call_id"] = fingerprint([call["call_id"], salt])
    if found:
        call["cases"] = found
    return call


class Collector:
    """The calls found missing so far, in the order they were first found. Calls that show helpers
    the same prompt are one row, with the other ids under `also`."""

    def __init__(self) -> None:
        self.calls: Dict[Tuple[str, str], J] = {}

    def add(self, call: J) -> None:
        key = (call["prompt_id"], call["prompt_fp"], call.get("salt"))
        have = self.calls.get(key)
        if have is None:
            self.calls[key] = call
            return
        if call["call_id"] != have["call_id"] and call["call_id"] not in have["also"]:
            have["also"].append(call["call_id"])
        for r in call.get("real") or []:
            if r not in have.setdefault("real", []):
                have["real"].append(r)
        for k in call.get("cases") or []:
            if k not in have.setdefault("cases", []):
                have["cases"].append(k)

    def __len__(self) -> int:
        return len(self.calls)

    def call_ids(self) -> int:
        return sum(len(c.get("real") or [c["call_id"]]) + len(c["also"]) for c in self.calls.values())

    def rows(self) -> List[J]:
        return list(self.calls.values())


def discovering_ai(answers: Dict[str, str], collector: Collector, render: Render, call_id_of: CallId,
                   placeholder_for: Optional[Dict[str, str]] = None,
                   expects_of: Optional[Callable[[str, Dict[str, str]], str]] = None,
                   mask: Optional[Callable[[str, str], str]] = None,
                   template_fp_of: Optional[Callable[[str], str]] = None) -> Callable[[str, Dict[str, str]], str]:
    """An AI that returns a stored answer, and for a call with none writes it into the collector.

    A missing call raises AICallMissing, so that a run stops at the first text it cannot make.
    A prompt id in `placeholder_for` is different: its answer feeds no later call (a watcher or a
    reviewer only flags), so the call is collected and the stated placeholder returned, and the
    run goes on to find more missing calls in the same pass.
    """
    placeholder_for = placeholder_for or {}
    current: Dict[str, Optional[str]] = {"case": None}

    def ai(prompt_id: str, fields: Dict[str, str]) -> str:
        cid = call_id_of(prompt_id, fields)
        if cid in answers:
            return answers[cid]
        expects = expects_of(prompt_id, fields) if expects_of else "text"
        collector.add(make_call(cid, prompt_id, render(prompt_id, fields), expects, mask,
                                template_fp_of(prompt_id) if template_fp_of else "",
                                [current["case"]] if current["case"] else None, fields.get(SALT_FIELD)))
        if prompt_id in placeholder_for:
            return placeholder_for[prompt_id]
        raise AICallMissing(cid, prompt_id, dict(fields))

    def set_case(case: Optional[str]) -> None:
        """Say which case the next calls belong to (None for none). The caller that runs one case at a time
        announces it before the case runs; judge_jobs announces each job's case."""
        current["case"] = case

    ai.set_case = set_case  # type: ignore[attr-defined]
    return ai


def pending_name(set_name: str) -> str:
    return "pending_%s.jsonl" % set_name


def parts_name(set_name: str) -> str:
    return "pending_%s_parts" % set_name


def set_of(prompt_id: str, export_sets: Dict[str, List[str]]) -> str:
    """Which of the three sets a prompt id belongs to, from D: live.export_sets (names without the version)."""
    name = prompt_id.rsplit(".v", 1)[0]
    for set_name, names in export_sets.items():
        if name in names:
            return set_name
    raise ContractError("prompt %s belongs to no export set" % prompt_id)


def legacy_pending(directory: Any) -> Optional[Path]:
    """The old single pending file, when a run folder still holds one."""
    path = Path(str(directory)) / LEGACY_PENDING
    return path if path.exists() else None


def shuffled(calls: List[J], seed: Any, set_name: str) -> List[J]:
    """The calls in a seeded shuffle, the same for the same calls, seed and set, so that neighbours
    come from different visits and the three questions on one text do not sit side by side."""
    out = list(calls)
    random.Random("%s:%s" % (seed, set_name)).shuffle(out)
    return out


def export_missing(directory: Any, calls: List[J], set_name: str = "steps") -> Path:
    """Write one set's missing calls to `<directory>/pending_<set>.jsonl`, or remove that file when none is missing."""
    path = handout_dir(directory) / pending_name(set_name)
    if not calls:
        if path.exists():
            path.unlink()
        return path
    save_idmap(directory, calls)
    _write_jsonl(path, [_handed(c) for c in calls])
    return path


def _handed(call: J) -> J:
    """A call as a helper gets it: without the private `real` ids."""
    return {k: v for k, v in call.items() if k not in ("real", "cases", "salt")}


def export_sets(directory: Any, by_set: Dict[str, List[J]], seed: Any, batch_size: int = 0,
                part_key: Optional[Dict[str, Callable[[J], Any]]] = None) -> Dict[str, Path]:
    """Write all three sets: each set's calls (shuffled by seed) to its file and, with batch_size, its parts
    folder. A set with no missing call has no file and no parts folder. Returns the path of each set's file.
    With `part_key` naming a set (the judge's, by rule: 14 Nov, H7), the parts of that set are made per key: one
    part holds calls of one key only, in the seeded order, and is named part_<key>_<n>.jsonl."""
    base = handout_dir(directory)
    paths: Dict[str, Path] = {}
    for set_name in SETS:
        calls = shuffled(by_set.get(set_name, []), seed, set_name)
        paths[set_name] = export_missing(directory, calls, set_name)
        parts_dir = base / parts_name(set_name)
        if parts_dir.exists():
            shutil.rmtree(str(parts_dir))
        if calls and batch_size:
            key = (part_key or {}).get(set_name)
            groups = [("", calls)]
            if key is not None:
                by_key: Dict[Any, List[J]] = {}
                for c in calls:
                    by_key.setdefault(key(c), []).append(c)
                groups = [("%s_" % k, by_key[k]) for k in sorted(by_key, key=str)]
            for label, group in groups:
                for n, batch in enumerate(split_parts(group, batch_size), 1):
                    _write_jsonl(parts_dir / ("part_%s%03d.jsonl" % (label, n)), [_handed(c) for c in batch])
    return paths


def read_pending(directory: Any) -> Dict[str, J]:
    """Every pending call of the three sets (in the handout folder), by exported call id. Each row also gets
    `real`, the real call ids from the private id map (the exported id itself when the map has none)."""
    out: Dict[str, J] = {}
    idmap = read_idmap(directory)
    for set_name in SETS:
        for row in _read_jsonl(handout_dir(directory) / pending_name(set_name)):
            row["real"] = list(idmap.get(row["call_id"]) or [row["call_id"]])
            out[row["call_id"]] = row
    return out


def split_parts(calls: List[J], size: int) -> List[List[J]]:
    """The calls cut into parts of at most `size`, in their given (seeded) order, so that no part holds two calls
    of the same case (a call's private `cases`; Version 2, part 3). A call that would meet a call of its case in
    the part being filled waits for the next part, so a part may be smaller than `size`. Calls with no known case
    are never held back. The order of the calls is kept inside each part and, as far as the rule allows, across."""
    if size < 1:
        raise ContractError("a part holds at least one call")
    left = list(calls)
    parts: List[List[J]] = []
    while left:
        part: List[J] = []
        used = set()
        later: List[J] = []
        for c in left:
            cs = set(c.get("cases") or [])
            if len(part) < size and not (cs & used):
                part.append(c)
                used |= cs
            else:
                later.append(c)
        parts.append(part)
        left = later
    return parts


def split_batches(calls: List[J], size: int) -> List[List[J]]:
    if size < 1:
        raise ContractError("a batch holds at least one call")
    return [calls[i:i + size] for i in range(0, len(calls), size)]


# ------------------------------------------------------------ import

def read_answer_file(path: Any) -> List[J]:
    return _read_jsonl(Path(str(path)))


def check_answer(row: J, call: Optional[J], allow_empty: Iterable[str] = (),
                 validators: Optional[Dict[str, Validator]] = None) -> Optional[str]:
    """None when the answer fits the pending call it claims, otherwise the reason it is refused."""
    if not isinstance(row.get("call_id"), str):
        return "no call_id"
    if call is None:
        return "no such call is pending"
    if fingerprint(call["prompt"]) != call["prompt_fp"]:
        return "the pending file was edited: its prompt no longer matches its own fingerprint"
    if row.get("prompt_fp") != call["prompt_fp"]:
        return "prompt_fp does not match the prompt of this call"
    if "prompt_id" in row and row["prompt_id"] != call["prompt_id"]:
        return "prompt_id does not match this call"
    output = row.get("output")
    if not isinstance(output, str):
        return "output is not text"
    check = (validators or {}).get(call["prompt_id"])
    if not output.strip() and call["prompt_id"] not in set(allow_empty) and check is None:
        return "output is empty"
    if check is not None:
        try:
            check(output, call)
        except ContractError as exc:
            return "output has the wrong form: %s" % exc
    return None


def import_answers(store: AnswerStore, pending: Dict[str, J], rows: List[J], allow_empty: Iterable[str] = (),
                   validators: Optional[Dict[str, Validator]] = None,
                   classifiers: Optional[Dict[str, Callable[[str, J], Optional[str]]]] = None,
                   idmap: Optional[Dict[str, List[str]]] = None,
                   extras: Optional[Dict[str, Callable[[str], List[str]]]] = None) -> J:
    """Check each answer against its pending call and store the good ones.

    An answer may name any of the call ids of a pending row; it is stored for all of them. Returns
    {"stored": n, "already": n, "refused": [{"line", "call_id", "reason"}]}, where n counts call ids.
    A classifier (by prompt id) returns a reason when an accepted answer is unusable; the answer is then stored
    as given with usable false and the reason, and is not refused and not asked again.
    A refused line stops nothing else. Two lines that answer one pending row differently are both refused.
    """
    by_id: Dict[str, J] = {}
    for row in pending.values():
        for cid in [row["call_id"]] + list(row.get("also", [])):
            by_id[cid] = row
    idmap = idmap or {}
    known = store.answers()
    seen: Dict[str, str] = {}
    clash = set()
    for row in rows:
        cid, out = row.get("call_id"), row.get("output")
        if isinstance(cid, str) and isinstance(out, str) and cid in by_id:
            key = by_id[cid]["call_id"]
            if key in seen and seen[key] != out:
                clash.add(key)
            seen.setdefault(key, out)
    good: List[J] = []
    refused: List[J] = []
    stored = already = 0
    for number, row in enumerate(rows, 1):
        cid = row.get("call_id")
        cid = cid if isinstance(cid, str) else None
        call = by_id.get(cid) if cid else None
        if call is not None and call["call_id"] in clash:
            refused.append({"line": number, "call_id": cid, "reason": "the file answers this call twice, differently"})
            continue
        if call is None and cid in idmap and all(known.get(r) == row.get("output") for r in idmap[cid]):
            already += len(idmap[cid])  # an answer sent again after its call left the pending file
            continue
        if call is None and cid in known and row.get("output") == known[cid]:
            already += 1
            continue
        reason = check_answer(row, call, allow_empty, validators)
        if reason is not None:
            refused.append({"line": number, "call_id": cid, "reason": reason})
            continue
        unusable = None
        classify = (classifiers or {}).get(call["prompt_id"])
        if classify is not None:
            unusable = classify(row["output"], call)
        extra_of = (extras or {}).get(call["prompt_id"])  # 15 Nov: lines kept apart (by prompt id), stored as extra_lines
        extra = extra_of(row["output"]) if extra_of is not None else []
        for one in list(call.get("real") or [call["call_id"]]) + list(call.get("also", [])):
            if one in known:
                if known[one] == row["output"]:
                    already += 1
                else:
                    refused.append({"line": number, "call_id": one, "reason": "call is stored with a different answer"})
                continue
            known[one] = row["output"]
            stored += 1
            entry = {"call_id": one, "prompt_id": call["prompt_id"], "prompt_fp": call["prompt_fp"],
                     "output": row["output"]}
            if unusable is not None:
                entry["usable"] = False
                entry["reason"] = unusable
            if extra:
                entry["extra_lines"] = extra
            good.append(entry)
    store.add(good)
    return {"stored": stored, "already": already, "refused": refused}


def replay_rows(store: AnswerStore) -> List[J]:
    """The stored answers in the form custody.ai.replay_ai takes: rows with call_id and output."""
    return [{"call_id": r["call_id"], "output": r["output"]} for r in store.rows()]


# ---------------------------------------------------------- unusable step answers

def _plain(text: str) -> str:
    return strip_lead(text.strip()).replace("\u2019", "'").replace("\u2018", "'").casefold()


def _norm(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'").casefold()


def without_first_line(output: str, step: str, first_lines: Dict[str, str]) -> str:
    """The answer without the step's required first line (VISIT NOTE (draft), PLAN, FOR YOU), when it is there."""
    want = first_lines.get(step)
    lines = output.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    if want and i < len(lines) and strip_line(lines[i]).casefold() == want.casefold():
        return "\n".join(lines[i + 1:])
    return output


def make_step_classifier(choices: J) -> Callable[[str, J], Optional[str]]:
    """The test for an unusable step answer (D: live.unusable). Returns the reason or None.

    Only an empty answer is unusable automatically. A refusal phrase never makes an answer unusable by itself: it
    makes it a candidate (make_candidate_test), and a person confirms a candidate by listing its call id in
    live/private/unusable_confirmed.json (J1, 14 Nov). A missing or doubled claim line, a missing tag or AI mark
    are for the readers and the judge."""

    def classify(output: str, call: J) -> Optional[str]:
        if not output.strip():
            return "empty answer"
        return None

    return classify


def make_candidate_test(choices: J) -> Callable[[str], Optional[str]]:
    """Returns the refusal phrase found anywhere in the first candidate_window characters of an answer, or None.
    Used on answers that are not empty, so that a person can look at them (refusal_candidates.json)."""
    cfg = choices["live"]["unusable"]
    phrases = [_norm(s) for s in cfg["refusal_candidates"]]
    window = int(cfg.get("candidate_window", 200))

    def test(output: str) -> Optional[str]:
        head = _norm(output)[:window]
        hits = [(head.index(ph), ph) for ph in phrases if ph in head]
        return min(hits)[1] if hits else None

    return test


CONFIRMED = "unusable_confirmed.json"


def read_confirmed(live_dir: Any) -> List[str]:
    """The call ids a person confirmed as refusals (live/private/unusable_confirmed.json). The file is created as an
    empty list when it is missing; it is never rewritten or reordered by the program (J1). An entry is a call id,
    or an object with a "call_id"."""
    path = private_dir(live_dir) / CONFIRMED
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[]\n", encoding="utf-8")
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise DataError("cannot read %s: %s" % (path, exc))
    if not isinstance(data, list):
        raise DataError("%s must hold a list of call ids" % path)
    out = []
    for x in data:
        cid = x.get("call_id") if isinstance(x, dict) else x
        if not isinstance(cid, str):
            raise DataError("%s: every entry must be a call id or an object with a call_id" % path)
        out.append(cid)
    return out
