#!/usr/bin/env python3
"""Confirm again, as they are, the rule 4 wrong-source texts that round 1's confirming program dropped (15 Nov 2026).

Round 1's program kept a wrong-source text only when it named an id of a known form (pmid:, tool:, doi: ...). The
outside model mostly wrote a source tag that names something else ("Wikipedia", "user-provided text"), and 52 of 60
texts were dropped with the reason "no source-like id is named". An audit read 12 of the 52 by lot: all 12 name a
wrong source inside the source tag. This program applies a corrected rule to those texts, without any model call:

  1. the changed text still has a source tag (a bracketed segment with the word "source") with something in it;
  2. no source id of the honest text remains anywhere in the changed text;
  3. no part of the changed text's source tags equals a part of the honest text's source tags;
  4. apart from the source segments, the text is at least as alike to the honest text as round 1 asked.

It appends the texts that pass to OUT/confirmed.jsonl (the form of tools/outside_texts.py confirm), so that
`round2/round2.py union` and `tools/make_plan.py faults-exp2` take them, and writes OUT/reconfirm_rule4.json.

    python3 round2/reconfirm_rule4.py --out round2/out
"""
import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import outside_texts as ot  # noqa: E402  (frozen)
from custody import outside  # noqa: E402  (frozen)


def tag_parts(text, choices):
    """The parts named inside the source segments of a text, lower case, split at commas and semicolons."""
    parts = []
    for seg in outside._source_segments(text, choices):
        inner = seg.strip()[1:-1]
        inner = re.sub(r"(?i)^\s*sources?\s*:?", "", inner)
        for part in re.split(r"[;,]", inner):
            part = re.sub(r"\s+", " ", part).strip().lower()
            if part:
                parts.append(part)
    return parts


def confirm_again(honest, changed, choices):
    if changed is None or not changed.strip():
        return False, "no changed text"
    if changed.strip() == honest.strip():
        return False, "the text is unchanged"
    new = tag_parts(changed, choices)
    if not new:
        return False, "no source tag with a source in it"
    left = [i for i in outside.source_ids(honest, choices) if i in outside.source_ids(changed, choices)]
    if left:
        return False, "an honest source id remains"
    old = set(tag_parts(honest, choices))
    if any(p in old for p in new):
        return False, "a part of the honest source tag remains"
    a, b = outside._set_aside("source_wrong", honest, changed, choices)
    sim = outside.similarity(a, b)
    if sim < outside._confirm_cfg(choices)["min_similarity"]:
        return False, "the rest of the text changed too much (%.2f alike)" % sim
    return True, "ok"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--first-dir", default=str(ROOT / "outside" / "test"))
    ap.add_argument("--clean-run", default=str(ROOT / "runs" / "night_e2"))
    ap.add_argument("--wiring", default=None)
    ap.add_argument("--config", default=None)
    a = ap.parse_args(argv)
    choices = outside.load_choices(a.config)
    wiring = ot.load_wiring(a)
    out, first = Path(a.out), Path(a.first_dir)
    out.mkdir(parents=True, exist_ok=True)
    report = ot.load_json(first / ot.REPORT, "the round 1 confirm report")
    dropped = [d["plant_id"] for d in report.get("dropped", [])
               if d.get("kind") == "source_wrong" and d.get("reason") == "no source-like id is named"]
    rows = {r["plant_id"]: r for r in outside.read_jsonl(first / ot.CHANGED)}
    have = {r["plant_id"] for r in outside.read_jsonl(out / ot.CONFIRMED)} if (out / ot.CONFIRMED).exists() else set()
    kept, reasons, tags = [], {}, {}
    for pid in dropped:
        r = rows[pid]
        kind = ot.step_kind(wiring, r["step"])
        honest = ot.honest_text(a.clean_run, r["case"], kind) if kind else None
        if honest is None or outside.sha256(honest) != r.get("honest_sha256"):
            reasons["the honest text is not the one round 1 changed"] = reasons.get("the honest text is not the one round 1 changed", 0) + 1
            continue
        ok, why = confirm_again(honest, r.get("changed_text"), choices)
        reasons[why] = reasons.get(why, 0) + 1
        if not ok:
            continue
        for part in tag_parts(r["changed_text"], choices):
            tags[part] = tags.get(part, 0) + 1
        if pid not in have:
            row = dict(r, confirmed_by="program, corrected rule of 15 Nov (round2/reconfirm_rule4.py)", round=1)
            outside.append_jsonl(out / ot.CONFIRMED, row)
        kept.append(pid)
    doc = {"dropped_in_round_1": len(dropped), "confirmed_again": len(kept), "reasons": reasons,
           "wrong_sources_named": dict(sorted(tags.items(), key=lambda kv: -kv[1])), "plant_ids": kept}
    (out / "reconfirm_rule4.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("rule 4 wrong sources dropped in round 1: %d; confirmed again: %d; reasons: %s" % (len(dropped), len(kept), reasons))
    print("named in the changed tags: %s" % dict(list(doc["wrong_sources_named"].items())[:12]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
