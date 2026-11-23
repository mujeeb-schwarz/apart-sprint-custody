#!/usr/bin/env python3
"""A second judge for rules 4 and 6, on the questions of the judge's second pass.

Written Sun 15 Nov 2026, after the freeze; it reads the second pass and writes new files only.

The first judge (Claude) answered every prompt of a second-pass folder (pending.jsonl, answers.jsonl,
index.jsonl). This program draws, by lot and for each rule, up to N prompts the first judge answered "broken"
and up to N it answered "kept", sends the same prompts to the outside model, and writes how often the two
judges agree, as a table of first answer against second answer.

    python3 rejudge/second_judge.py --pass-dir rejudge/night_e2_pass --out rejudge/night_e2_pass/second_judge.jsonl

Run it again to go on after a stop: answered prompts are kept, the draw is kept.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from custody import outside  # noqa: E402
from custody.outside import LimitStop  # noqa: E402
import outside_texts  # noqa: E402  (for its Session: the settings, the call log)


def rows(path):
    return outside.read_jsonl(path)


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--pass-dir", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--per-class", type=int, default=100)
    p.add_argument("--rules", default="4,6")
    p.add_argument("--seed", default="20261116")
    p.add_argument("--config")
    p.add_argument("--codex-bin")
    p.add_argument("--model")
    p.add_argument("--effort")
    p.add_argument("--retry-waits")
    a = p.parse_args(argv)

    pass_dir = Path(a.pass_dir)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    s = outside_texts.Session(a, out.parent, "judge2")

    prompts = {r["call_id"]: r["prompt"] for r in rows(pass_dir / "pending.jsonl")}
    first = {r["call_id"]: r["output"] for r in rows(pass_dir / "answers.jsonl")}
    rule_of, case_of = {}, {}
    for r in rows(pass_dir / "index.jsonl"):
        rule_of.setdefault(r["call_id"], int(r["rule"]))
        case_of.setdefault(r["call_id"], r.get("visit_id"))
    rules = [int(x) for x in a.rules.split(",")]

    draw_path = out.with_name(out.name + ".draw.json")
    if draw_path.exists():
        drawn = json.loads(draw_path.read_text(encoding="utf-8"))["call_ids"]
    else:
        drawn = []
        for rule in rules:
            for word in ("broken", "kept"):
                pool = sorted(c for c in prompts if rule_of.get(c) == rule and c in first
                              and outside.read_answer(first[c]) == ("verdict", word))
                rng = random.Random("%s:second_judge:%d:%s" % (a.seed, rule, word))
                rng.shuffle(pool)
                drawn.extend(pool[:a.per_class])
        draw_path.write_text(json.dumps({"seed": a.seed, "per_class": a.per_class, "rules": rules,
                                         "call_ids": drawn}, indent=1) + "\n", encoding="utf-8")

    have = {r["call_id"]: r for r in rows(out)} if out.exists() else {}
    todo = [{"call_id": c, "prompt": prompts[c], "case": case_of.get(c)} for c in drawn if c not in have]
    batch = int(s.choices["outside"]["judge_batch"])
    left = 0
    limit_hit = False

    def put(c, text, res, attempt):
        row = {"call_id": c["call_id"], "rule": rule_of[c["call_id"]], "output": text,
               "model": s.model_name(res), "attempt": attempt}
        outside.append_jsonl(out, row)
        have[c["call_id"]] = row

    try:
        for part in outside.make_batches(todo, batch):
            parsed, res, err = outside.ask_framed(s.choices, "judge_batch", "tasks", "task",
                                                  [c["prompt"] for c in part], {}, s.ask_fn)
            if err:
                left += len(part)
                continue
            for n, c in enumerate(part, 1):
                if n in parsed:
                    put(c, parsed[n], res, 1)
                    continue
                alone, res2, err2 = outside.ask_framed(s.choices, "judge_batch", "tasks", "task",
                                                       [c["prompt"]], {}, s.ask_fn)
                if not err2 and 1 in alone:
                    put(c, alone[1], res2, 2)
                else:
                    left += 1
    except LimitStop:
        limit_hit = True

    table = {}
    disagreements = []
    for c in drawn:
        if c not in have:
            continue
        rule = str(rule_of[c])
        t = table.setdefault(rule, {"n": 0, "agree": 0, "unreadable": 0, "first_broken": {"broken": 0, "kept": 0},
                                    "first_kept": {"broken": 0, "kept": 0}})
        x, y = outside.read_answer(first[c]), outside.read_answer(have[c]["output"])
        if x is None or y is None or x[0] != "verdict" or y[0] != "verdict":
            t["unreadable"] += 1
            continue
        t["n"] += 1
        t["agree"] += 1 if x == y else 0
        t["first_" + x[1]][y[1]] += 1
        if x != y:
            disagreements.append({"call_id": c, "rule": int(rule), "case": case_of.get(c), "first": x[1], "second": y[1]})
    for t in table.values():
        t["rate"] = (t["agree"] / t["n"]) if t["n"] else None
    report = {"drawn": len(drawn), "answered": len(have), "left": len(drawn) - len(have), "by_rule": table,
              "disagreements": disagreements, "second_model": sorted({str(r.get("model")) for r in have.values()})}
    rep_path = out.with_name(out.name + ".agreement.json")
    rep_path.write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("second judge, rules %s: %d drawn, %d answered, %d left. %s" % (a.rules, len(drawn), len(have),
                                                                          len(drawn) - len(have), s.summary()))
    print(json.dumps(table, sort_keys=True))
    print("report: %s" % rep_path)
    if limit_hit:
        print("STOPPED: a usage limit was reached; run again when it resets.")
        return 5
    return 4 if len(have) < len(drawn) else 0


if __name__ == "__main__":
    sys.exit(main())
