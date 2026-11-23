#!/usr/bin/env python3
"""Round 2 of the changed texts of Experiment 2 (15 Nov 2026), for the rows round 1 got wrong.

    select  [--out OUT]           which rows round 2 asks for, and which it skips; counts only, no call
    make    --out OUT             the changed texts: OUT/changed_texts.jsonl and OUT/make_info.json
    union   --dir OUT             after confirm: OUT/confirmed_union.jsonl, round 1's confirmed rule 4 rows plus OUT's
                                  confirmed rule 4 and 5 rows, for faults-exp2
    check   --dir OUT             after `tools/outside_texts.py confirm --dir OUT`: for the rule 5 rows, the level the
                                  bench's reader reads in the honest and in the changed text; counts only

Round 1 (outside/test) had two faults. Rule 5 asked for "more" or "less" certainty, and most changes stayed inside
one level of the ladder, which breaks no rule. Rule 4 source_wrong texts mostly named no source id at all
("no source-like id is named"). Round 2 asks again for exactly these rows: every rule 5 row of the plan (reserve
included), each with a target level, and the rule 4 source_wrong rows the confirming program dropped. All wording
sent is in round2/instructions.json.

OUT has the same form as the folder of `tools/outside_texts.py make`, so the frozen tools work on it unchanged:
    python3 tools/outside_texts.py confirm --dir OUT
    python3 tools/make_plan.py faults-exp2 --plan plans/test/exp2_plan.json --confirmed OUT/confirmed.jsonl --out OUT/exp2_faults.json

It reuses the frozen code of tools/outside_texts.py by import (Session, step_kind, honest_text, plan_rows' checks,
the constants and the common options) and of custody/outside.py (batches, framing, parsing, the call). The loop that
sends a batch and asks again alone for a text the reply did not frame is copied from cmd_make of
tools/outside_texts.py, because it is not a function there; it differs only in that the instruction is per group of
rows (rule 5 rows carry their own target) instead of per kind.
Exit code: 0 everything asked for is done, 4 some is left (a failed call), 5 a usage limit stopped the run, 2 a bad
input. A second start does only what is missing.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import outside_texts as ot  # noqa: E402  (frozen)
from custody import core, outside  # noqa: E402  (frozen)
from custody.outside import LimitStop, OutsideError  # noqa: E402

EXIT_OK, EXIT_LEFT, EXIT_BAD, EXIT_LIMIT = ot.EXIT_OK, ot.EXIT_LEFT, ot.EXIT_BAD, ot.EXIT_LIMIT
SELECT = "round2_select.json"
CHECK = "round2_check.json"
DEFAULT_PLAN = ROOT / "plans" / "test" / "exp2_plan.json"
DEFAULT_CLEAN = ROOT / "runs" / "night_e2"
DEFAULT_FIRST = ROOT / "outside" / "test"
DEFAULT_CASES = ROOT / "data" / "cases" / "exp2.jsonl"
UNION = "confirmed_union.jsonl"


def load_instructions(path=None):
    return ot.load_json(path or HERE / "instructions.json", "the round 2 instructions")


# ------------------------------------------------------------------ levels and targets

def target_level(levels, honest_level, direction, steps, lowest_evidence):
    """The target level, or None when there is none that differs from the honest level in the asked direction."""
    if honest_level not in levels:
        return None
    i = levels.index(honest_level)
    if direction == "more":
        t = min(i + steps, len(levels) - 1)
        return levels[t] if t > i else None
    floor = levels.index(lowest_evidence)
    t = max(i - steps, floor)
    return levels[t] if t < i else None


def level_phrase(text, choices):
    """(level, the phrase on the claim line that decides it) as custody.core.claim_level reads the text, or
    (level, None) when the default or no claim line decides. Copied from the order of claim_level (frozen), which
    returns the level only; it uses core.claim_line and core._has_phrase."""
    line = core.claim_line(text or "", choices)
    level = core.claim_level(text or "", choices)
    if line is None:
        return level, None
    ladder = choices["ladder"]
    sensitive = set(ladder.get("case_sensitive_phrases", []))
    for lv in ladder["levels"]:
        for p in ladder.get("named", {}).get(lv, []):
            if core._has_phrase(line, p, False):
                return level, p.lower()
    for lv in ladder["test_order"]:
        for p in ladder["phrases"][lv]:
            if core._has_phrase(line, p, p in sensitive):
                return level, p.lower()
    for p in ladder.get("undecided_hedges", []):
        if core._has_phrase(line, p, False):
            return level, p.lower()
    for p in ladder.get("undecided_case_sensitive", []):
        if core._has_phrase(line, p, True):
            return level, p
    return level, None


def previous_level(clean, case, kind, choices):
    """The level of the last honest advice text before `kind` in the case that the reader reads (None, 'undecided'
    and texts with no claim line are passed over, as custody/watch.py passes them over), or None."""
    advice = choices["rules"]["advice_kinds"]
    if kind not in advice:
        return None
    for pk in reversed(advice[:advice.index(kind)]):
        lv = core.claim_level(ot.honest_text(clean, case, pk) or "", choices)
        if lv is not None and lv != "undecided":
            return lv
    return None


# ------------------------------------------------------------------ selection

def select(a, choices, instr):
    """(rows to ask, skipped rows, counts). Each row to ask is a plan row with plan_index, honest and instruction
    (rule 5 rows also honest_level and target_level); a row with no honest text comes back with honest None."""
    plan = ot.load_json(a.plan, "the plan")
    wiring = ot.load_wiring(a)
    clean = Path(a.clean_run)
    if not (clean / "texts.jsonl").exists():
        raise OutsideError("the clean run %s has no texts.jsonl" % clean)
    first = Path(a.first_dir)
    report = ot.load_json(first / ot.REPORT, "the round 1 confirm report")
    confirmed1 = {r["plant_id"] for r in outside.read_jsonl(first / ot.CONFIRMED)}
    dropped_wrong = {d["plant_id"] for d in report.get("dropped", []) if d.get("kind") == "source_wrong"}
    ot.plan_rows(plan, choices)  # the frozen check that every kind is known
    cases = Path(getattr(a, "cases", None) or DEFAULT_CASES)
    grades = {v.get("visit_id"): v.get("expert_certainty") for v in outside.read_jsonl(cases)} if cases.exists() else {}
    levels = choices["ladder"]["levels"]
    kinds = choices["outside"]["kinds"]
    steps = int(instr["steps_up_or_down"])
    lowest = instr["lowest_level_stating_evidence"]
    if lowest not in levels:
        raise OutsideError("lowest_level_stating_evidence %r is not a level of the ladder" % lowest)
    ask, skipped = [], []
    counts = {"rule5_rows": 0, "rule4_source_wrong_dropped_in_round1": len(dropped_wrong),
              "rule4_rows": 0, "asked": 0, "no_honest_text": 0, "skipped": {}}
    for i, p in enumerate(plan["planted"]):
        rule5 = p["rule"] == 5
        rule4 = (not getattr(a, "no_rule4", False)) and p["kind"] == "source_wrong" and p["plant_id"] in dropped_wrong \
            and p["plant_id"] not in confirmed1
        if not (rule5 or rule4):
            continue
        counts["rule5_rows" if rule5 else "rule4_rows"] += 1
        kind = ot.step_kind(wiring, p["step"])
        honest = ot.honest_text(clean, p["case"], kind) if kind else None
        row = dict(p, plan_index=i, honest=honest)
        if honest is None:
            counts["no_honest_text"] += 1
            ask.append(row)
            continue
        if rule4:
            row["instruction"] = instr["rule4_source_wrong"]
        else:
            lv = core.claim_level(honest, choices)
            if (lv is None or lv not in levels) and grades.get(p["case"]) in levels:
                # 15 Nov audit: a text the bench's reader cannot read takes the expert grade as its level, so the
                # rows the methods' own reader cannot read are not left out of the selection
                lv, row["honest_level_from"] = grades[p["case"]], "expert_grade"
            if lv is None or lv not in levels:
                why = "honest level not read (%s)" % ("no claim line" if lv is None else lv)
            else:
                way = kinds[p["kind"]]["direction"]
                tgt = target_level(levels, lv, way, steps, lowest)
                why = None if tgt else "no target level %s %s" % ("above" if way == "more" else "below", lv)
                prev = previous_level(clean, p["case"], kind, choices)
                if tgt and tgt == prev:
                    # 15 Nov audit: the monitor's rule 5 compares a text with the advice text before it; a target
                    # equal to that text's level breaks nothing it can see, so one step further, else one nearer
                    far = target_level(levels, lv, way, steps + 1, lowest)
                    near = target_level(levels, lv, way, steps - 1, lowest) if steps > 1 else None
                    tgt = far if far not in (None, tgt, prev) else near if near not in (None, prev) else None
                    why = None if tgt else "target equals the level of the advice text before it (%s)" % prev
            if why:
                skipped.append({"plant_id": p["plant_id"], "kind": p["kind"], "reason": why})
                counts["skipped"][why] = counts["skipped"].get(why, 0) + 1
                continue
            row.update(honest_level=lv, target_level=tgt, instruction=instr["rule5"].format(
                target_phrase=instr["level_phrases"][tgt], current_phrase=instr["level_phrases"][lv]))
        ask.append(row)
        counts["asked"] += 1
    return ask, skipped, counts


def print_counts(counts):
    print("rule 5 rows %d, rule 4 source_wrong rows %d (dropped in round 1 %d); to ask %d, no honest text %d, "
          "skipped %d" % (counts["rule5_rows"], counts["rule4_rows"], counts["rule4_source_wrong_dropped_in_round1"],
                          counts["asked"], counts["no_honest_text"], sum(counts["skipped"].values())))
    for why, n in sorted(counts["skipped"].items()):
        print("  skipped, %s: %d" % (why, n))


def cmd_select(a):
    choices = outside.load_choices(getattr(a, "config", None))
    ask, skipped, counts = select(a, choices, load_instructions(a.instructions))
    by = {}
    for r in ask:
        if r.get("target_level"):
            key = "%s %s -> %s" % (r["kind"], r["honest_level"], r["target_level"])
            by[key] = by.get(key, 0) + 1
    counts["rule5_by_move"] = by
    print_counts(counts)
    for k, n in sorted(by.items()):
        print("  %s: %d" % (k, n))
    if a.out:
        Path(a.out).mkdir(parents=True, exist_ok=True)
        (Path(a.out) / SELECT).write_text(json.dumps({"counts": counts, "skipped": skipped}, indent=1, sort_keys=True)
                                          + "\n", encoding="utf-8")
    return EXIT_OK


# ------------------------------------------------------------------ make

def cmd_make(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    s = ot.Session(a, out, "writer")
    instr = load_instructions(a.instructions)
    plan = ot.load_json(a.plan, "the plan")
    ask, skipped, counts = select(a, s.choices, instr)
    info = {"plan": str(Path(a.plan).resolve()), "clean_run": str(Path(a.clean_run).resolve()),
            "wiring": str(Path(a.wiring).resolve()) if a.wiring else None, "seed": plan.get("seed")}
    info_path = out / ot.MAKE_INFO
    if info_path.exists():
        was = ot.load_json(info_path, "the make info")
        if was != info:
            raise OutsideError("%s was written for another plan, clean run, wiring or seed; use a new folder" % info_path)
    info_path.write_text(json.dumps(info, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / SELECT).write_text(json.dumps({"counts": counts, "skipped": skipped}, indent=1, sort_keys=True) + "\n",
                              encoding="utf-8")
    done = {r["plant_id"]: r for r in outside.read_jsonl(out / ot.CHANGED)}
    already = sum(1 for r in ask if r["plant_id"] in done)
    stats = {"made": 0, "unparsed": 0, "no_honest_text": 0}
    order = {r["plant_id"]: r["plan_index"] for r in ask}

    def save():
        outside.write_jsonl(out / ot.CHANGED, sorted(done.values(), key=lambda r: order.get(r["plant_id"], 10 ** 9)))

    def base(r):
        row = {"plant_id": r["plant_id"], "case": r["case"], "rule": r["rule"], "kind": r["kind"], "step": r["step"],
               "reserve": r.get("reserve", False), "order": r.get("order"), "plan_index": r["plan_index"],
               "round": 2}
        if r.get("target_level"):
            row.update(honest_level=r["honest_level"], target_level=r["target_level"])
        if r.get("honest_level_from"):
            row["honest_level_from"] = r["honest_level_from"]
        return row

    groups = {}  # instruction -> rows, in the plan's order of each group's first row
    for r in ask:
        if r["plant_id"] in done:
            continue
        if r["honest"] is None:
            done[r["plant_id"]] = dict(base(r), honest_sha256=None, changed_text=None, model=None, attempt=0,
                                       status="no_honest_text")
            stats["no_honest_text"] += 1
            continue
        groups.setdefault(r["instruction"], []).append(r)
    save()
    batch = int(s.choices["outside"]["batch"])
    limit_hit = False

    def make_row(r, text, res, attempt, status):
        row = dict(base(r), honest_sha256=outside.sha256(r["honest"]), changed_text=text, model=s.model_name(res),
                   attempt=attempt, instruction_sha256=outside.sha256(r["instruction"]))
        if status:
            row["status"] = status
        done[r["plant_id"]] = row
        stats["made" if text is not None else "unparsed"] += 1

    # copied from cmd_make of tools/outside_texts.py (frozen): one framed call per batch, then each text the reply
    # did not frame asked again alone; the instruction is the group's own
    try:
        for instruction, items in groups.items():
            for part in outside.make_batches([dict(i) for i in items], batch):
                bodies = [i["honest"] for i in part]
                parsed, res, err = outside.ask_framed(s.choices, "make", "texts", "text", bodies,
                                                      {"instruction": instruction}, s.ask_fn)
                if err:
                    continue
                for n, item in enumerate(part, 1):
                    if n in parsed:
                        make_row(item, parsed[n], res, 1, None)
                        continue
                    alone, res2, err2 = outside.ask_framed(s.choices, "make", "texts", "text", [item["honest"]],
                                                           {"instruction": instruction}, s.ask_fn)
                    if err2:
                        continue
                    if 1 in alone:
                        make_row(item, alone[1], res2, 2, None)
                    else:
                        make_row(item, None, res2, 2, "unparsed")
                save()
    except LimitStop:
        limit_hit = True
    save()
    left = sum(len(v) for v in groups.values()) - stats["made"] - stats["unparsed"]
    print_counts(counts)
    print("rows to ask %d: already done %d, made now %d, not parsed after a second try %d, no honest text %d, "
          "left %d. %s" % (len(ask), already, stats["made"], stats["unparsed"], stats["no_honest_text"], left,
                           s.summary()))
    if limit_hit:
        print("STOPPED: a usage limit was reached; what was made is in %s. Run again when it resets." % (out / ot.CHANGED))
        return EXIT_LIMIT
    return EXIT_LEFT if left else EXIT_OK


# ------------------------------------------------------------------ check

def cmd_check(a):
    out = Path(a.dir)
    choices = outside.load_choices(getattr(a, "config", None))
    info = ot.load_json(out / ot.MAKE_INFO, "the make info")
    wiring = ot.load_json(info["wiring"] or ROOT / "wiring" / "wiring.json", "the wiring")
    levels = choices["ladder"]["levels"]
    kinds = choices["outside"]["kinds"]
    made = [r for r in outside.read_jsonl(out / ot.CHANGED) if r.get("rule") == 5]
    confirmed = {r["plant_id"] for r in outside.read_jsonl(out / ot.CONFIRMED)}
    have_confirm = (out / ot.CONFIRMED).exists()
    res = {}
    for r in made:
        k = res.setdefault(r["kind"], {
            "rows": 0, "no_changed_text": 0, "honest_text_changed_since": 0, "honest_level": {}, "changed_level": {},
            "same_level": 0, "moved_as_asked": 0, "reached_target": 0, "past_target": 0, "short_of_target": 0,
            "wrong_way": 0, "changed_level_not_read": 0, "level_phrase_changed": 0, "honest_phrase_still_on_claim_line": 0,
            "confirmed_by_outside_model": 0, "confirmed_and_moved_as_asked": 0, "confirmed_and_same_level": 0,
            "not_confirmed_and_moved_as_asked": 0})
        k["rows"] += 1
        kind = ot.step_kind(wiring, r["step"])
        honest = ot.honest_text(info["clean_run"], r["case"], kind) if kind else None
        if r.get("changed_text") is None:
            k["no_changed_text"] += 1
            continue
        if honest is None or outside.sha256(honest) != r.get("honest_sha256"):
            k["honest_text_changed_since"] += 1
            continue
        hl, hp = level_phrase(honest, choices)
        cl, cp = level_phrase(r["changed_text"], choices)
        if hl not in levels and r.get("honest_level_from") == "expert_grade":
            hl = r.get("honest_level")  # the reader cannot read the honest text; its level was taken from the grade
        k["honest_level"][str(hl)] = k["honest_level"].get(str(hl), 0) + 1
        k["changed_level"][str(cl)] = k["changed_level"].get(str(cl), 0) + 1
        if hp != cp:
            k["level_phrase_changed"] += 1
        line = core.claim_line(r["changed_text"], choices)
        if hp and line is not None and core._has_phrase(line, hp, hp in set(choices["ladder"].get("case_sensitive_phrases", []))):
            k["honest_phrase_still_on_claim_line"] += 1
        conf = r["plant_id"] in confirmed
        k["confirmed_by_outside_model"] += 1 if conf else 0
        moved = False
        if cl not in levels or hl not in levels:
            k["changed_level_not_read"] += 1
        else:
            d = levels.index(cl) - levels.index(hl)
            up = kinds[r["kind"]]["direction"] == "more"
            if d == 0:
                k["same_level"] += 1
                k["confirmed_and_same_level"] += 1 if conf else 0
            elif (d > 0) == up:
                moved = True
                k["moved_as_asked"] += 1
                tgt = r.get("target_level")
                if tgt in levels:
                    gap = (levels.index(cl) - levels.index(tgt)) * (1 if up else -1)
                    k["reached_target" if gap == 0 else "past_target" if gap > 0 else "short_of_target"] += 1
            else:
                k["wrong_way"] += 1
        if moved:
            k["confirmed_and_moved_as_asked" if conf else "not_confirmed_and_moved_as_asked"] += 1
    doc = {"confirm_run": have_confirm, "rule5": res}
    (out / CHECK).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    if not have_confirm:
        print("note: %s does not exist yet; the confirmed counts are 0 (run tools/outside_texts.py confirm --dir %s)" % (
            out / ot.CONFIRMED, out))
    for kind in sorted(res):
        k = res[kind]
        print("rule 5 %s: rows %d, no changed text %d; reader: same level %d, moved as asked %d (target reached %d, "
              "past %d, short %d), wrong way %d, not read %d; level phrase changed %d; confirmed by the outside "
              "model %d (of them moved as asked %d, same level %d)" % (
                  kind, k["rows"], k["no_changed_text"], k["same_level"], k["moved_as_asked"], k["reached_target"],
                  k["past_target"], k["short_of_target"], k["wrong_way"], k["changed_level_not_read"],
                  k["level_phrase_changed"], k["confirmed_by_outside_model"], k["confirmed_and_moved_as_asked"],
                  k["confirmed_and_same_level"]))
    print("counts written to %s" % (out / CHECK))
    return EXIT_OK


# ------------------------------------------------------------------ union

def cmd_union(a):
    """15 Nov audit: the rule 4 set is round 1's confirmed rule 4 rows plus round 2's confirmed rows; the rule 5 set
    is round 2's alone. Writes OUT/confirmed_union.jsonl for tools/make_plan.py faults-exp2, whose cap
    (planting.per_rule) then takes the first rows in the plan's order. Rules other than 4 and 5 are left out."""
    out = Path(a.dir)
    if not (out / ot.CONFIRMED).exists():
        raise OutsideError("%s does not exist (run tools/outside_texts.py confirm --dir %s first)" % (out / ot.CONFIRMED, out))
    second = [r for r in outside.read_jsonl(out / ot.CONFIRMED) if r.get("rule") in (4, 5)]
    have = {r["plant_id"] for r in second}
    first = [r for r in outside.read_jsonl(Path(a.first_dir) / ot.CONFIRMED)
             if r.get("rule") == 4 and r["plant_id"] not in have]
    rows = sorted(first + second, key=lambda r: r.get("plan_index", 10 ** 9))
    outside.write_jsonl(out / UNION, rows)
    print("union: rule 4 from round 1 %d, rule 4 from round 2 %d, rule 5 from round 2 %d; written to %s" % (
        len(first), sum(1 for r in second if r["rule"] == 4), sum(1 for r in second if r["rule"] == 5), out / UNION))
    return EXIT_OK


# ------------------------------------------------------------------ main

def add_select(p):
    p.add_argument("--plan", default=str(DEFAULT_PLAN))
    p.add_argument("--clean-run", default=str(DEFAULT_CLEAN))
    p.add_argument("--first-dir", default=str(DEFAULT_FIRST), help="round 1's folder (confirm_report.json, confirmed.jsonl)")
    p.add_argument("--instructions", default=None, help="default round2/instructions.json")
    p.add_argument("--cases", default=None, help="default data/cases/exp2.jsonl (the expert grades)")
    p.add_argument("--no-rule4", action="store_true",
                   help="make no new rule 4 text (15 Nov: the dropped round 1 texts are confirmed again as they are)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="command", required=True)
    p = sub.add_parser("select")
    add_select(p)
    p.add_argument("--out", default=None)
    p.add_argument("--wiring", default=None)
    p.add_argument("--config", default=None, help=argparse.SUPPRESS)
    p = sub.add_parser("make")
    add_select(p)
    p.add_argument("--out", required=True)
    ot.add_common(p)
    p = sub.add_parser("union")
    p.add_argument("--dir", required=True)
    p.add_argument("--first-dir", default=str(DEFAULT_FIRST))
    p = sub.add_parser("check")
    p.add_argument("--dir", required=True)
    p.add_argument("--config", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    try:
        return {"select": cmd_select, "make": cmd_make, "union": cmd_union, "check": cmd_check}[a.command](a)
    except OutsideError as exc:
        print("error: %s" % exc)
        return EXIT_BAD


if __name__ == "__main__":
    sys.exit(main())
