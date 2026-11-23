#!/usr/bin/env python3
"""The outside model's work for Version 3, through the Codex command-line program (custody/outside.py).

    ideas   --out FILE            ask for ways to break rules 1 to 3 in Experiment 1; the reply goes to FILE, sealed
    ideas   --out FILE --open     open the sealed file (only when the freeze file of the live folder exists)
    make    --plan PLAN --clean-run RUN --out DIR
                                  changed texts for Experiment 2 (rules 4 to 6): DIR/changed_texts.jsonl
    confirm --dir DIR             confirm the changed texts: DIR/confirmed.jsonl and DIR/confirm_report.json
    judge2  --live-dir LIVE --sample N --out FILE
                                  a second judge on N judge calls drawn by lot from the live folder
    keep-judge-calls --live-dir LIVE
                                  keep a copy of the judge calls now in the handout (a finished run removes them)
    export40 --live-dir LIVE --out PAGE.md
                                  40 advice texts for the owner to read, with the judge's questions and empty boxes
    score40 PAGE.md               compare the filled page with the judge's answers

Every call runs `codex exec` in a new empty folder, with the model, effort, batch sizes, time limit, retries and
limit phrases of D: outside; the prompt goes on standard input. Tools print counts only. A usage-limit reply stops
the tool with exit code 5 and loses nothing: a second start does only what is missing. Exit code: 0 everything
asked for is done, 4 some is left (a failed call), 5 a usage limit stopped the run, 2 a bad input.
The private log of the calls (no prompt text, no reply text) is outside_calls.jsonl beside the output.
"""
import argparse
import hashlib
import json
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import outside  # noqa: E402
from custody.outside import LimitStop, OutsideError  # noqa: E402

LOG = "outside_calls.jsonl"
MAKE_INFO = "make_info.json"
CHANGED = "changed_texts.jsonl"
CONFIRM_ANSWERS = "confirm_answers.jsonl"
CONFIRMED = "confirmed.jsonl"
REPORT = "confirm_report.json"
EXIT_OK, EXIT_LEFT, EXIT_BAD, EXIT_LIMIT = 0, 4, 2, 5


class Session:
    """The settings, the call counts and the private log of one run of the tool."""

    def __init__(self, a, log_dir, role=None):
        self.role = role
        self.choices = outside.load_choices(getattr(a, "config", None))
        self.codex = getattr(a, "codex_bin", None)
        self.model = getattr(a, "model", None)
        self.effort = getattr(a, "effort", None)
        waits = getattr(a, "retry_waits", None)
        self.waits = [float(x) for x in waits.split(",")] if waits else None
        self.log_path = Path(log_dir) / LOG
        self.calls = 0
        self.tokens = 0
        self.errors = 0

    def log(self, row):
        row = dict(row, at=time.strftime("%Y-%m-%dT%H:%M:%S%z"))
        outside.append_jsonl(self.log_path, row)

    def ask_fn(self, prompt, purpose, role=None):
        res = outside.ask(prompt, self.choices, model=self.model, effort=self.effort, codex_bin=self.codex,
                          waits=self.waits, log=lambda r: self.log(r), purpose=purpose, role=role or self.role)
        self.calls += 1
        self.tokens += res["tokens"] or 0
        if res["limit"]:
            raise LimitStop()
        if res["error"]:
            self.errors += 1
        return res

    def model_name(self, res):
        return res.get("model")  # the model the program's own output names (None when it names none)

    def summary(self):
        return "calls %d, tokens used %d, failed calls %d" % (self.calls, self.tokens, self.errors)


def load_json(path, what):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise OutsideError("cannot read %s %s: %s" % (what, path, exc))


def load_wiring(a):
    return load_json(getattr(a, "wiring", None) or ROOT / "wiring" / "wiring.json", "the wiring")


# ------------------------------------------------------------------ 2. ideas, sealed

def freeze_file(a):
    if getattr(a, "freeze_file", None):
        return Path(a.freeze_file)
    root = Path(getattr(a, "root", None) or ROOT)
    for name in ("live_e1", "live"):
        if (root / name / "frozen.json").exists():
            return root / name / "frozen.json"
    return root / "live_e1" / "frozen.json"


def cmd_ideas(a):
    out = Path(a.out)
    seal = out.with_name(out.name + ".sealed")
    if a.open:
        ff = freeze_file(a)
        if not ff.exists():
            print("error: the freeze file %s does not exist yet; the ideas stay sealed until the first test run has "
                  "frozen the prompts and the design choices" % ff)
            return EXIT_BAD
        if not out.exists():
            print("error: %s does not exist" % out)
            return EXIT_BAD
        if seal.exists():
            seal.replace(out.with_name(out.name + ".opened"))
        sys.stdout.write(out.read_text(encoding="utf-8"))
        return EXIT_OK
    if out.exists():
        data = out.read_bytes()
        print("%s exists (%d bytes, sha256 %s); nothing asked again" % (out, len(data), hashlib.sha256(data).hexdigest()))
        return EXIT_OK
    s = Session(a, out.parent, "ideas")
    wiring = load_wiring(a)
    description = outside.describe_flow(wiring, s.choices, "words")
    prompt = outside.fill(outside.prompt_file(s.choices, "ideas"), {"description": description})
    try:
        res = s.ask_fn(prompt, "ideas")
    except LimitStop:
        print("STOPPED: a usage limit was reached; nothing was lost. Run again when it resets.")
        return EXIT_LIMIT
    if res["error"]:
        print("the call failed (%s); run again to retry. %s" % (res["error"], s.summary()))
        return EXIT_LEFT
    out.parent.mkdir(parents=True, exist_ok=True)
    text = res["text"] if res["text"].endswith("\n") else res["text"] + "\n"
    out.write_text(text, encoding="utf-8")
    seal.write_text("sealed %s\n" % time.strftime("%Y-%m-%dT%H:%M:%S%z"), encoding="utf-8")
    data = text.encode("utf-8")
    print("ideas written to %s: %d bytes, sha256 %s; sealed (%s). %s" % (
        out, len(data), hashlib.sha256(data).hexdigest(), seal.name, s.summary()))
    return EXIT_OK


# ------------------------------------------------------------------ 3. changed texts

def step_kind(wiring, step_id):
    """The kind of the item a step handles: what it makes, or, for a step that makes nothing new, what it reads."""
    for st in wiring["plumbing"]["steps"]:
        if st["id"] == step_id:
            return st.get("makes") or (st.get("reads") or [None])[0]
    return None


def honest_text(run_dir, case, kind, cond="A"):
    """The text of the first item of `kind` in the clean run of the case under method A, or None."""
    prefix = "%s.%s." % (case, cond)
    for row in outside.read_jsonl(Path(run_dir) / "texts.jsonl"):
        item = row.get("item") or {}
        if str(row.get("run_id", "")).startswith(prefix) and item.get("kind") == kind and item.get("visit_id", case) == case:
            return item.get("text")
    return None


def plan_rows(plan, choices):
    rows = []
    for i, p in enumerate(plan["planted"]):
        if p["kind"] not in choices["outside"]["instructions"]:
            raise OutsideError("the plan row %s has the kind %r, which D: outside.instructions does not know" % (p.get("plant_id"), p["kind"]))
        rows.append(dict(p, plan_index=i))
    return rows


def cmd_make(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    s = Session(a, out, "writer")
    plan = load_json(a.plan, "the plan")
    wiring = load_wiring(a)
    clean = Path(a.clean_run)
    if not (clean / "texts.jsonl").exists():
        raise OutsideError("the clean run %s has no texts.jsonl" % clean)
    rows = plan_rows(plan, s.choices)
    info = {"plan": str(Path(a.plan).resolve()), "clean_run": str(clean.resolve()),
            "wiring": str(Path(a.wiring).resolve()) if a.wiring else None, "seed": plan.get("seed")}
    (out / MAKE_INFO).write_text(json.dumps(info, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    done = {r["plant_id"]: r for r in outside.read_jsonl(out / CHANGED)}
    stats = {"rows_in_plan": len(rows), "already": len(done), "made": 0, "unparsed": 0, "no_honest_text": 0, "left": 0}

    def save():
        order = {r["plant_id"]: r["plan_index"] for r in rows}
        outside.write_jsonl(out / CHANGED, sorted(done.values(), key=lambda r: order.get(r["plant_id"], 10 ** 9)))

    todo_by_kind = {}
    for r in rows:
        if r["plant_id"] in done:
            continue
        kind = step_kind(wiring, r["step"])
        text = honest_text(clean, r["case"], kind) if kind else None
        if text is None:
            done[r["plant_id"]] = {"plant_id": r["plant_id"], "case": r["case"], "rule": r["rule"], "kind": r["kind"],
                                   "step": r["step"], "honest_sha256": None, "changed_text": None, "model": None,
                                   "attempt": 0, "reserve": r.get("reserve", False), "order": r.get("order"),
                                   "plan_index": r["plan_index"], "status": "no_honest_text"}
            stats["no_honest_text"] += 1
            continue
        todo_by_kind.setdefault(r["kind"], []).append(dict(r, honest=text))
    save()
    batch = int(s.choices["outside"]["batch"])
    limit_hit = False

    def make_row(r, text, res, attempt, status):
        row = {"plant_id": r["plant_id"], "case": r["case"], "rule": r["rule"], "kind": r["kind"], "step": r["step"],
               "honest_sha256": outside.sha256(r["honest"]), "changed_text": text, "model": s.model_name(res),
               "attempt": attempt, "reserve": r.get("reserve", False), "order": r.get("order"),
               "plan_index": r["plan_index"]}
        if status:
            row["status"] = status
        done[r["plant_id"]] = row
        stats["made" if text is not None else "unparsed"] += 1

    try:
        for kind, items in todo_by_kind.items():
            instruction = s.choices["outside"]["instructions"][kind]
            for part in outside.make_batches([dict(i) for i in items], batch):
                bodies = [i["honest"] for i in part]
                parsed, res, err = outside.ask_framed(s.choices, "make", "texts", "text", bodies,
                                                      {"instruction": instruction}, s.ask_fn)
                if err:
                    stats["left"] += len(part)
                    continue
                for n, item in enumerate(part, 1):
                    if n in parsed:
                        make_row(item, parsed[n], res, 1, None)
                        continue
                    alone, res2, err2 = outside.ask_framed(s.choices, "make", "texts", "text", [item["honest"]],
                                                           {"instruction": instruction}, s.ask_fn)
                    if err2:
                        stats["left"] += 1
                    elif 1 in alone:
                        make_row(item, alone[1], res2, 2, None)
                    else:
                        make_row(item, None, res2, 2, "unparsed")
                save()
    except LimitStop:
        limit_hit = True
    save()
    left = sum(len(v) for v in todo_by_kind.values()) - stats["made"] - stats["unparsed"]
    print("plan rows %d: already done %d, made now %d, not parsed after a second try %d, no honest text %d, left %d. %s" % (
        stats["rows_in_plan"], stats["already"], stats["made"], stats["unparsed"], stats["no_honest_text"], left, s.summary()))
    if limit_hit:
        print("STOPPED: a usage limit was reached; what was made is in %s. Run again when it resets." % (out / CHANGED))
        return EXIT_LIMIT
    return EXIT_LEFT if left else EXIT_OK


# ------------------------------------------------------------------ 4. confirmation

def cmd_confirm(a):
    out = Path(a.dir)
    info = load_json(out / MAKE_INFO, "the make info")
    s = Session(a, out, "confirmer")
    plan = load_json(info["plan"], "the plan")
    wiring = load_json(info["wiring"] or ROOT / "wiring" / "wiring.json", "the wiring")
    kinds = s.choices["outside"]["kinds"]
    made = outside.read_jsonl(out / CHANGED)
    plan_row = {r["plant_id"]: r for r in plan["planted"]}
    made.sort(key=lambda r: r.get("plan_index", 0))
    verdict = {}   # plant_id -> (confirmed, reason, by)
    pending = []   # rule 5 rows needing the outside model
    honest_of = {}
    for r in made:
        pid = r["plant_id"]
        kind = step_kind(wiring, r["step"])
        honest = honest_text(info["clean_run"], r["case"], kind) if kind else None
        honest_of[pid] = honest
        if r.get("changed_text") is None:
            verdict[pid] = (False, r.get("status") or "no changed text", None)
        elif honest is None or outside.sha256(honest) != r.get("honest_sha256"):
            verdict[pid] = (False, "the honest text of the clean run changed since the text was made", None)
        elif kinds[r["kind"]]["rule"] in (4, 6):
            ok, why = outside.confirm_program(r["kind"], honest, r["changed_text"], s.choices)
            verdict[pid] = (ok, why, "program")
        else:
            pending.append(r)
    answers = {x["plant_id"]: x for x in outside.read_jsonl(out / CONFIRM_ANSWERS)}
    seed = info.get("seed")
    cfg = s.choices["outside"]["confirm"]
    todo = [dict(r, case=r["case"]) for r in pending if r["plant_id"] not in answers]
    limit_hit = False
    left = 0
    try:
        for part in outside.make_batches(todo, int(cfg["batch"])):
            firsts = [outside.lot_order(seed, r["plant_id"]) for r in part]
            bodies = [outside.pair_body(s.choices, honest_of[r["plant_id"]], r["changed_text"], f)
                      for r, f in zip(part, firsts)]
            parse = lambda text, nums: outside.parse_pair_answers(s.choices, text, nums)  # noqa: E731
            parsed, res, err = outside.ask_framed(s.choices, "confirm", "pairs", "pair", bodies, {}, s.ask_fn, parse=parse)
            if err:
                left += len(part)
                continue
            for n, (r, first) in enumerate(zip(part, firsts), 1):
                attempt, rr, ans = 1, res, parsed.get(n)
                if ans is None:
                    alone, rr, err2 = outside.ask_framed(s.choices, "confirm", "pairs", "pair", [bodies[n - 1]], {},
                                                         s.ask_fn, parse=parse)
                    attempt = 2
                    if err2:
                        left += 1
                        continue
                    ans = alone.get(1)
                row = {"plant_id": r["plant_id"], "answer": ans, "changed_first": first, "model": s.model_name(rr),
                       "attempt": attempt}
                answers[r["plant_id"]] = row
                outside.append_jsonl(out / CONFIRM_ANSWERS, row)
    except LimitStop:
        limit_hit = True
    for r in pending:
        pid = r["plant_id"]
        row = answers.get(pid)
        if row is None:
            continue  # not asked yet: neither confirmed nor dropped
        if row["answer"] is None:
            verdict[pid] = (False, "the outside model's answer could not be read", "outside model")
        else:
            ok = outside.pair_matches(kinds[r["kind"]]["direction"], row["changed_first"], row["answer"])
            verdict[pid] = (ok, "ok" if ok else "the outside model did not read the direction asked", "outside model")
    counts, dropped, confirmed_rows = {}, [], []
    for r in made:
        pid = r["plant_id"]
        c = counts.setdefault(str(r["rule"]), {}).setdefault(r["kind"], {"made": 0, "confirmed": 0, "dropped": 0, "not_asked": 0})
        c["made"] += 1
        if pid not in verdict:
            c["not_asked"] += 1
            continue
        ok, why, by = verdict[pid]
        if ok:
            c["confirmed"] += 1
            confirmed_rows.append(dict(r, confirmed_by=by))
        else:
            c["dropped"] += 1
            dropped.append({"plant_id": pid, "rule": r["rule"], "kind": r["kind"], "reason": why})
    outside.write_jsonl(out / CONFIRMED, confirmed_rows)
    (out / REPORT).write_text(json.dumps({"counts": counts, "dropped": dropped}, indent=1, sort_keys=True) + "\n",
                              encoding="utf-8")
    for rule in sorted(counts):
        for kind in sorted(counts[rule]):
            c = counts[rule][kind]
            print("rule %s %s: made %d, confirmed %d, dropped %d%s" % (
                rule, kind, c["made"], c["confirmed"], c["dropped"], (", not asked yet %d" % c["not_asked"]) if c["not_asked"] else ""))
    print("confirmed texts: %s (%d rows, in the plan's order). %s" % (out / CONFIRMED, len(confirmed_rows), s.summary()))
    if limit_hit:
        print("STOPPED: a usage limit was reached; the answers so far are kept. Run again when it resets.")
        return EXIT_LIMIT
    return EXIT_LEFT if left else EXIT_OK


# ------------------------------------------------------------------ 5. the second judge

def read_calls(a, choices):
    calls = outside.judge_calls(a.live_dir, choices, getattr(a, "calls", None) or [])
    if not calls:
        raise OutsideError("no judge prompts were found under %s (handout/pending_judge.jsonl, its parts, "
                           "private/judge_calls_kept.jsonl). A finished run removes the handout files: run "
                           "`tools/outside_texts.py keep-judge-calls --live-dir %s` while they are there, or give "
                           "--calls FILE" % (a.live_dir, a.live_dir))
    return calls


def cmd_keep(a):
    choices = outside.load_choices(getattr(a, "config", None))
    n = outside.keep_judge_calls(a.live_dir, choices)
    print("judge calls kept in %s: %d" % (Path(a.live_dir) / "private" / "judge_calls_kept.jsonl", n))
    return EXIT_OK


def cmd_judge2(a):
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    s = Session(a, out.parent, "judge2")
    calls = read_calls(a, s.choices)
    case_of = outside.case_of_text(a.run) if a.run else None
    draw_path = out.with_name(out.name + ".draw.json")
    by_id = {c["call_id"]: c for c in calls}
    if draw_path.exists():
        drawn = [dict(by_id[i], case=(case_of or {}).get(by_id[i]["text"])) for i in load_json(draw_path, "the draw")["call_ids"]
                 if i in by_id]
    else:
        drawn = outside.draw_calls(calls, a.sample, s.choices["seeds"]["judge"], case_of)
        draw_path.write_text(json.dumps({"seed": s.choices["seeds"]["judge"], "call_ids": [c["call_id"] for c in drawn]},
                                        indent=1) + "\n", encoding="utf-8")
    have = {r["call_id"]: r for r in outside.read_jsonl(out)}
    todo = [c for c in drawn if c["call_id"] not in have]
    batch = int(s.choices["outside"]["judge_batch"])
    limit_hit = False
    left = 0
    new = 0

    def put(c, text, res, attempt):
        nonlocal new
        row = {"call_id": c["call_id"], "rule": c["rule"], "output": text, "prompt_fp": c.get("prompt_fp"),
               "model": s.model_name(res), "attempt": attempt}
        outside.append_jsonl(out, row)
        have[c["call_id"]] = row
        new += 1

    try:
        for part in outside.make_batches(todo, batch):
            parsed, res, err = outside.ask_framed(s.choices, "judge_batch", "tasks", "task", [c["prompt"] for c in part], {}, s.ask_fn)
            if err:
                left += len(part)
                continue
            for n, c in enumerate(part, 1):
                if n in parsed:
                    put(c, parsed[n], res, 1)
                    continue
                alone, res2, err2 = outside.ask_framed(s.choices, "judge_batch", "tasks", "task", [c["prompt"]], {}, s.ask_fn)
                if err2:
                    left += 1
                elif 1 in alone:
                    put(c, alone[1], res2, 2)
                else:
                    left += 1
    except LimitStop:
        limit_hit = True
    first = outside.first_answers(a.live_dir)
    second = {cid: r["output"] for cid, r in have.items()}
    agree = outside.agreement({k: v for k, v in first.items() if k in second}, second,
                              {c["call_id"]: c["rule"] for c in drawn}, s.choices["ladder"]["levels"])
    agree_path = out.with_name(out.name + ".agreement.json")
    agree_path.write_text(json.dumps(agree, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    unknown_case = sum(1 for c in drawn if not c.get("case"))
    print("second judge: %d calls drawn, %d answered (%d now), %d left; cases known for %d of them. %s" % (
        len(drawn), len(have), new, len(drawn) - len(have), len(drawn) - unknown_case, s.summary()))
    print("agreement table written to %s" % agree_path)
    if limit_hit:
        print("STOPPED: a usage limit was reached; what was answered is in %s. Run again when it resets." % out)
        return EXIT_LIMIT
    return EXIT_LEFT if len(have) < len(drawn) else EXIT_OK


# ------------------------------------------------------------------ 6. the owner's 40 texts

def texts_of(calls):
    """The calls grouped by text: [{text, kind, true_sources, calls: {rule: call}}], in a stable order."""
    groups = {}
    for c in sorted(calls, key=lambda c: c["call_id"]):
        if c.get("rule") is None:
            continue
        g = groups.setdefault(c["text"], {"text": c["text"], "kind": c["kind"], "true_sources": c["true_sources"], "calls": {}})
        g["calls"].setdefault(str(c["rule"]), c)
    return sorted(groups.values(), key=lambda g: outside.sha256(g["text"]))


def spread(counts_available, n, rng, kinds):
    """How many texts to take of each kind: n split evenly (the kinds that get an extra one drawn by lot), a kind
    with too few texts giving its surplus to the others."""
    want = {k: n // len(kinds) for k in kinds}
    extra = list(kinds)
    rng.shuffle(extra)
    for k in extra[:n - sum(want.values())]:
        want[k] += 1
    for _ in range(len(kinds)):
        surplus = 0
        for k in kinds:
            if want[k] > counts_available.get(k, 0):
                surplus += want[k] - counts_available.get(k, 0)
                want[k] = counts_available.get(k, 0)
        if not surplus:
            break
        for k in kinds:
            room = counts_available.get(k, 0) - want[k]
            give = min(room, surplus)
            want[k] += give
            surplus -= give
    return want


def cmd_export40(a):
    out = Path(a.out)
    key_path = out.with_name(out.stem + ".key.json")
    if out.exists():
        print("%s exists; nothing drawn again (the key file %s stays with it)" % (out, key_path.name))
        return EXIT_OK
    choices = outside.load_choices(getattr(a, "config", None))
    cfg = choices["outside"]["export40"]
    calls = read_calls(a, choices)
    groups = [g for g in texts_of(calls) if g["calls"]]
    rng = random.Random("%s:export40" % choices["seeds"]["judge"])
    by_kind = {k: [g for g in groups if g["kind"] == k] for k in cfg["kinds"]}
    want = spread({k: len(v) for k, v in by_kind.items()}, int(cfg["count"]), rng, list(cfg["kinds"]))
    chosen = []
    for k in cfg["kinds"]:
        pool = list(by_kind[k])
        rng.shuffle(pool)
        chosen += pool[:want[k]]
    rng.shuffle(chosen)
    lines = ["# %s" % cfg["title"], "", cfg["intro"], ""]
    key = {"live_dir": str(Path(a.live_dir).resolve()), "seed": choices["seeds"]["judge"], "texts": {}}
    for i, g in enumerate(chosen, 1):
        num = "%02d" % i
        lines += ["## Text %s" % num, "", "```text", g["text"].strip("\n"), "```", ""]
        if g["true_sources"]:
            lines += ["True sources for this advice: %s" % g["true_sources"], ""]
        key["texts"][num] = {"kind": g["kind"], "calls": {}}
        for rule in sorted(g["calls"]):
            c = g["calls"][rule]
            lines += ["Question %s. %s" % (rule, c["rule_line"]), "", "A%s.%s = " % (num, rule), ""]
            key["texts"][num]["calls"][rule] = c["call_id"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    key_path.write_text(json.dumps(key, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    by = {}
    for g in chosen:
        by[g["kind"]] = by.get(g["kind"], 0) + 1
    print("page written to %s: %d texts (%s); key file %s" % (
        out, len(chosen), ", ".join("%s %d" % kv for kv in sorted(by.items())), key_path))
    return EXIT_OK


def cmd_score40(a):
    page = Path(a.page)
    key_path = page.with_name(page.stem + ".key.json")
    key = load_json(key_path, "the key file")
    choices = outside.load_choices(getattr(a, "config", None))
    levels = choices["ladder"]["levels"]
    live = a.live_dir or key["live_dir"]
    judge = outside.first_answers(live)
    rx = re.compile(r"^A(\d+)\.(\d+)\s*=\s*(.*)$")
    owner = {}
    for line in page.read_text(encoding="utf-8").splitlines():
        m = rx.match(line.strip())
        if m:
            owner[(m.group(1).zfill(2), m.group(2))] = m.group(3).strip()
    table, kinds = {}, {}
    for num, t in sorted(key["texts"].items()):
        for rule, cid in sorted(t["calls"].items()):
            row = table.setdefault(rule, {"asked": 0, "answered": 0, "unreadable": 0, "no_judge_answer": 0, "agree": 0})
            row["asked"] += 1
            mine = owner.get((num, rule), "")
            if not mine:
                continue
            row["answered"] += 1
            theirs = outside.read_answer(judge.get(cid, ""), levels) if cid in judge else None
            if cid not in judge:
                row["no_judge_answer"] += 1
                continue
            mine_r = outside.read_answer(mine, levels)
            if mine_r is None or theirs is None:
                row["unreadable"] += 1
                continue
            same = mine_r == theirs
            row["agree"] += 1 if same else 0
            k = kinds.setdefault(t["kind"], {"compared": 0, "agree": 0})
            k["compared"] += 1
            k["agree"] += 1 if same else 0
    res = {"by_rule": table, "by_kind": kinds}
    page.with_name(page.stem + ".scored.json").write_text(json.dumps(res, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for rule in sorted(table):
        r = table[rule]
        print("question %s: asked %d, answered %d, unreadable %d, no judge answer %d, same as the judge %d" % (
            rule, r["asked"], r["answered"], r["unreadable"], r["no_judge_answer"], r["agree"]))
    return EXIT_OK


# ------------------------------------------------------------------ main

def add_common(p):
    p.add_argument("--codex-bin", default=None, help="the codex program (default D: outside.codex_bin)")
    p.add_argument("--model", default=None)
    p.add_argument("--effort", default=None)
    p.add_argument("--retry-waits", default=None, help="seconds before each retry, comma separated (default D: outside.retry_wait_seconds)")
    p.add_argument("--config", default=None, help=argparse.SUPPRESS)
    p.add_argument("--wiring", default=None, help="the wiring file (default wiring/wiring.json)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("ideas")
    p.add_argument("--out", required=True)
    p.add_argument("--open", action="store_true", help="open the sealed file; only when the freeze file exists")
    p.add_argument("--root", default=None, help=argparse.SUPPRESS)
    p.add_argument("--freeze-file", default=None, help="the freeze file to look for (default live_e1/frozen.json under the project)")
    add_common(p)
    p = sub.add_parser("make")
    p.add_argument("--plan", required=True)
    p.add_argument("--clean-run", required=True)
    p.add_argument("--out", required=True)
    add_common(p)
    p = sub.add_parser("confirm")
    p.add_argument("--dir", required=True)
    add_common(p)
    p = sub.add_parser("judge2")
    p.add_argument("--live-dir", required=True)
    p.add_argument("--sample", type=int, required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--run", default=None, help="a run folder, to learn each text's case (keeps one case out of one call)")
    p.add_argument("--calls", action="append", help="an extra file of judge calls (call_id, prompt)")
    add_common(p)
    p = sub.add_parser("keep-judge-calls")
    p.add_argument("--live-dir", required=True)
    p.add_argument("--config", default=None, help=argparse.SUPPRESS)
    p = sub.add_parser("export40")
    p.add_argument("--live-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--calls", action="append")
    p.add_argument("--config", default=None, help=argparse.SUPPRESS)
    p = sub.add_parser("score40")
    p.add_argument("page")
    p.add_argument("--live-dir", default=None)
    p.add_argument("--config", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    fn = {"ideas": cmd_ideas, "make": cmd_make, "confirm": cmd_confirm, "judge2": cmd_judge2,
          "keep-judge-calls": cmd_keep, "export40": cmd_export40, "score40": cmd_score40}[a.command]
    try:
        return fn(a)
    except OutsideError as exc:
        print("error: %s" % exc)
        return EXIT_BAD


if __name__ == "__main__":
    sys.exit(main())
