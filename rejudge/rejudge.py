#!/usr/bin/env python3
"""Second pass of the judge for rules 4 and 6, with corrected questions, written into new files only.

    python3 rejudge/rejudge.py build   --run RUN_DIR --out DIR [--rules 4,6] [--only-split tune|test]
    python3 rejudge/rejudge.py answer  --dir DIR [--workers 8] [--model claude-opus-5-5] [--claude-bin PATH]
    python3 rejudge/rejudge.py collect --dir DIR --run RUN_DIR --copy COPY_DIR [--force]
    python3 rejudge/rejudge.py score   --copy COPY_DIR

The bench is imported, never edited and never written to. Nothing is written into RUN_DIR.
Tools print counts only.
"""
import argparse
import copy
import hashlib
import json
import os
import shutil
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from custody import ai, ai_live, datasets, judge, score  # noqa: E402
from custody.core import ContractError, CustodyError, canon, fingerprint  # noqa: E402

PROMPT_ID = "judge.v1"
SECOND_PASS_ID = "judge.v1+second_pass"
ALLOWED_RULES = (4, 6)
# What the replies must say. The parser (judge.parse_answer) wants one line "VERDICT kept" or "VERDICT broken".
# The bench's own form text defines kept and broken through "the prose", which contradicts the new questions,
# so these two forms define them through the answer to the question instead. The reply line is the same.
FORM = ("Reply with one line, either VERDICT kept (the answer to the question is yes) or VERDICT broken "
        "(the answer to the question is no).")
# Files and folders of a run folder that score_run opens (custody/score.py, score_run).
COPIED = ("manifest.json", "results.jsonl", "unusable_visits.json", "signals.jsonl", "texts.jsonl",
          "own_log.jsonl", "visits.jsonl", "hidden", "journal")


# ------------------------------------------------------------------ files

def read_jsonl(path):
    out = []
    p = Path(path)
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def write_jsonl(path, rows):
    with open(str(path), "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(canon(r) + "\n")


def questions():
    q = json.loads((HERE / "questions.json").read_text(encoding="utf-8"))
    return {int(k): v for k, v in q.items()}


def judge_model(choices):
    return choices["live"]["terminal"]["models"]["judge"]


def call_id_of(model, prompt):
    return hashlib.sha256((model + "\n" + prompt).encode("utf-8")).hexdigest()[:32]


# ------------------------------------------------------------------ build

def second_pass_prompt(item, visit, rule, choices, qs):
    """The judge's prompt as the bench builds it (judge_fields, render_prompt), with the question of
    questions.json in place of rules.left_to_judge, and the form above in place of the bench's form."""
    c = copy.deepcopy(choices)
    c["rules"]["left_to_judge"][str(rule)] = qs[rule]
    job = {"visit_id": item["visit_id"], "item_id": item["item_id"], "rule": rule, "text": item["text"],
           "true_sources": score.true_sources(visit)}
    fields = judge.judge_fields(job, c)
    fields["rule"] = "Rule %d. %s %s" % (rule, qs[rule], FORM)
    judge.blind_check(fields)
    return ai.render_prompt(choices["prompts"]["judge"], fields)


def cmd_build(a):
    rules = [int(x) for x in a.rules.split(",") if x]
    if not rules or any(r not in ALLOWED_RULES for r in rules):
        print("error: --rules takes 4 and/or 6")
        return 2
    run, out = Path(a.run), Path(a.out)
    choices = datasets.default_choices()
    qs = questions()
    if choices["prompts"]["judge"] != PROMPT_ID:
        print("error: the bench's judge prompt is %s, not %s" % (choices["prompts"]["judge"], PROMPT_ID))
        return 2
    model = a.model or judge_model(choices)
    visits = {v["visit_id"]: v for v in read_jsonl(run / "visits.jsonl")}
    texts = read_jsonl(run / "texts.jsonl")
    kinds = choices["rules"]["advice_kinds"]
    out.mkdir(parents=True, exist_ok=True)
    tokens = ai_live.VisitTokens(out / "live", [PROMPT_ID])
    seen = {}
    for row in texts:
        it = row["item"]
        if it["kind"] not in kinds:
            continue
        v = visits[it["visit_id"]]
        if a.only_split and v.get("split") != a.only_split:
            continue
        seen.setdefault((it["visit_id"], it["item_id"]), it)
    pending, index = {}, []
    per_rule = Counter()
    for (vid, iid) in sorted(seen):
        it, v = seen[(vid, iid)], visits[vid]
        for rule in rules:
            shown = tokens.mask(PROMPT_ID, second_pass_prompt(it, v, rule, choices, qs))
            cid = call_id_of(model, shown)
            pending.setdefault(cid, {"call_id": cid, "also": [], "prompt_id": PROMPT_ID, "prompt": shown,
                                     "prompt_fp": fingerprint(shown), "expects": "verdict"})
            index.append({"visit_id": vid, "item_id": iid, "rule": rule, "call_id": cid, "kind": it["kind"],
                          "case_kind": (v.get("meta") or {}).get("case_kind"), "split": v.get("split")})
            per_rule[rule] += 1
    tokens.save()
    write_jsonl(out / "pending.jsonl", pending.values())
    write_jsonl(out / "index.jsonl", index)
    (out / "build.json").write_text(json.dumps({"run": str(run), "model": model, "rules": rules,
                                                "only_split": a.only_split}, indent=1) + "\n", encoding="utf-8")
    print("texts %d; prompts %s; distinct prompts %d" % (
        len(seen), ", ".join("rule %d: %d" % (r, per_rule[r]) for r in rules), len(pending)))
    return 0


# ------------------------------------------------------------------ answer

def cmd_answer(a):
    import answer_calls
    d = Path(a.dir)
    rows = read_jsonl(d / "pending.jsonl")
    if not rows:
        print("error: %s has no pending.jsonl rows; run build first" % d)
        return 2
    live = d / "live"
    handed = rows
    # the bench's tool reads pending_judge.jsonl of a live folder; the one here is a staging copy
    (live / "handout").mkdir(parents=True, exist_ok=True)
    write_jsonl(live / "handout" / "pending_judge.jsonl", handed)
    out = d / "answers.jsonl"
    before = {r["call_id"] for r in read_jsonl(out)}
    tw = None if a.transient_waits is None else [float(x) for x in a.transient_waits.split(",") if x != ""]
    try:
        r = answer_calls.answer(live, ("judge",), a.workers, None, a.claude_bin, {"judge": a.model}, "unset",
                                out, False, print, None, True, tw)
    except CustodyError as e:
        print("error: %s" % e)
        return 2
    have = {x["call_id"] for x in read_jsonl(out)}
    left = len({x["call_id"] for x in rows} - have)
    print("pending %d; stored now %d (new %d); left %d" % (len(rows), len(have & {x["call_id"] for x in rows}),
                                                          len(have - before), left))
    if r["wrong_model_stop"]:
        return 2
    if r["limit_hit"] or (r["asked"] and r["answered"] == 0 and r["failed"] > 0):
        return 5
    return 1 if left else 0


# ------------------------------------------------------------------ collect

def cmd_collect(a):
    d, run, copy_dir = Path(a.dir), Path(a.run), Path(a.copy)
    if copy_dir.resolve() == run.resolve() or run.resolve() in copy_dir.resolve().parents:
        print("error: the copy must not be the run folder or inside it")
        return 2
    if copy_dir.exists() and any(copy_dir.iterdir()) and not a.force:
        print("error: %s exists and is not empty; use --force" % copy_dir)
        return 2
    choices = datasets.default_choices()
    build = json.loads((d / "build.json").read_text(encoding="utf-8"))
    rules = build["rules"]
    index = read_jsonl(d / "index.jsonl")
    answers = {r["call_id"]: r["output"] for r in read_jsonl(d / "answers.jsonl")}
    missing = [r for r in index if r["call_id"] not in answers]
    if missing and not a.partial:
        print("error: %d of %d rows have no stored answer; answer them first or use --partial" % (len(missing), len(index)))
        return 1
    rows, unreadable = [], []
    for r in index:
        if r["call_id"] not in answers:
            continue
        out = answers[r["call_id"]]
        try:
            verdict = judge.verdict_of(r["rule"], out, None, choices)
        except ContractError as e:
            verdict = "undecided"
            unreadable.append({"visit_id": r["visit_id"], "item_id": r["item_id"], "rule": r["rule"],
                               "call_id": r["call_id"], "why": str(e)[:200], "reply": out[:300]})
        rows.append({"visit_id": r["visit_id"], "item_id": r["item_id"], "rule": r["rule"], "verdict": verdict,
                     "judge": judge.JUDGE_NAME, "prompt_id": SECOND_PASS_ID})
    write_jsonl(d / "judge_second_pass.jsonl", rows)
    write_jsonl(d / "unreadable.jsonl", unreadable)
    # the copy
    if copy_dir.exists() and a.force:
        shutil.rmtree(str(copy_dir))
    copy_dir.mkdir(parents=True, exist_ok=True)
    for name in COPIED:
        src = run / name
        if src.is_dir():
            shutil.copytree(str(src), str(copy_dir / name))
        elif src.exists():
            shutil.copy2(str(src), str(copy_dir / name))
    new = {(r["visit_id"], r["item_id"], r["rule"]): r for r in rows}
    merged, used = [], set()
    for o in read_jsonl(run / "judge.jsonl"):
        k = (o["visit_id"], o["item_id"], int(o["rule"]))
        if k in new:
            merged.append(new[k])
            used.add(k)
        else:
            merged.append(o)
    merged.extend(r for k, r in new.items() if k not in used)
    write_jsonl(copy_dir / "judge.jsonl", merged)
    (copy_dir / "COPY_NOTE.json").write_text(json.dumps({
        "made_from": str(run), "second_pass_rules": rules, "prompt_id": SECOND_PASS_ID,
        "left_out": ["ai_calls.jsonl", "judge_agreement.json", "judge_sample.jsonl", "receipts/", "witness/",
                     "timing.jsonl", "refusal_candidates.json", "scores*.json"]}, indent=1) + "\n", encoding="utf-8")
    # counts for the clean units
    meta = {(r["visit_id"], r["item_id"], r["rule"]): r for r in index}
    tab = Counter()
    for r in rows:
        if "+" in r["visit_id"]:
            continue
        m = meta[(r["visit_id"], r["item_id"], r["rule"])]
        tab[(r["rule"], m["case_kind"], m["kind"], r["verdict"])] += 1
    print("second-pass rows %d; unreadable (undecided) %d; missing %d; copy rows %d" % (
        len(rows), len(unreadable), len(missing), len(merged)))
    for title, pos in (("by rule", (0,)), ("by case kind", (0, 1)), ("by kind of text", (0, 2))):
        agg = Counter()
        for k, n in tab.items():
            agg[tuple(k[i] for i in pos) + (k[3],)] += n
        print("clean units, verdicts %s:" % title)
        for key in sorted(agg, key=str):
            print("  " + " ".join(str(x) for x in key) + ": %d" % agg[key])
    return 0


# ------------------------------------------------------------------ score

def cmd_score(a):
    c = Path(a.copy)
    choices = datasets.default_choices()
    with open(str(ROOT / "wiring" / "wiring.json"), encoding="utf-8") as fh:
        wiring = json.load(fh)
    try:
        res = score.score_run(c, wiring, choices, None, None)
    except (CustodyError, OSError, ValueError) as e:
        print("error: %s" % e)
        return 2
    text = score.render_text(res)
    (c / "scores_second_pass.json").write_text(json.dumps(res, sort_keys=True, indent=1) + "\n", encoding="utf-8")
    (c / "scores_second_pass.txt").write_text(text + "\n", encoding="utf-8")
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.startswith("GRADES")), 0)
    end = next((i for i, ln in enumerate(lines) if ln.startswith("ENTRY ERRORS")), len(lines))
    print("\n".join(lines[start:end]))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("--run", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--rules", default="4,6")
    b.add_argument("--only-split", choices=["tune", "test"], default=None)
    b.add_argument("--model", default=None, help="model named in the call ids (default: live.terminal.models.judge)")
    n = sub.add_parser("answer")
    n.add_argument("--dir", required=True)
    n.add_argument("--workers", type=int, default=8)
    n.add_argument("--model", default="claude-opus-5-5")
    n.add_argument("--claude-bin", default="claude")
    n.add_argument("--transient-waits", default=None, help=argparse.SUPPRESS)
    c = sub.add_parser("collect")
    c.add_argument("--dir", required=True)
    c.add_argument("--run", required=True)
    c.add_argument("--copy", required=True)
    c.add_argument("--force", action="store_true")
    c.add_argument("--partial", action="store_true", help="collect what is answered; missing rows keep the original verdict")
    s = sub.add_parser("score")
    s.add_argument("--copy", required=True)
    a = ap.parse_args(argv)
    return {"build": cmd_build, "answer": cmd_answer, "collect": cmd_collect, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
