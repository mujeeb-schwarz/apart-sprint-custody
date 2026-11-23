#!/usr/bin/env python3
"""The complete list of violations and the draw by lot (Version 3).

    python3 tools/make_plan.py catalogue --experiment 1 --split test --out DIR
    python3 tools/make_plan.py draw      --experiment 1 --split test --out DIR
    python3 tools/make_plan.py faults-exp2 --plan PLAN --confirmed confirmed.jsonl --out FILE

faults-exp2 (version 3): per rule the first planting.per_rule confirmed rows in the plan's order, one fault each
(rewrite, mode set_text, at the row's step); FILE is read by tools/run_advice.py --faults for the parts planted and repeat.

Both write DIR/exp<E>_catalogue.json and DIR/exp<E>_plan.json (the draw also writes the list it drew from, so the
plan can be read with it) and print counts only, never an outcome. Experiment 2 has no list of variants: its
violations (rules 4 to 6) are drawn, so its catalogue file holds an empty list. The split is test or tune (practice).
Exit code: 0 done, 2 a bad input.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import planting, units, visits  # noqa: E402
from custody.core import ContractError, DataError  # noqa: E402


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=False, ensure_ascii=False) + "\n", encoding="utf-8")


def _kind_counts(cat):
    out = {}
    for v in cat:
        key = "apart:%s" % v["kind"] if v["apart"] else "rule%d:%s" % (v["rule"], v["kind"])
        out[key] = out.get(key, 0) + 1
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("what", choices=["catalogue", "draw", "faults-exp2"])
    ap.add_argument("--experiment", type=int, choices=[1, 2], default=None)
    ap.add_argument("--split", choices=["test", "tune"], default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--plan", default=None, help="faults-exp2: the Experiment 2 plan")
    ap.add_argument("--confirmed", default=None, help="faults-exp2: confirmed.jsonl of tools/outside_texts.py confirm")
    ap.add_argument("--root", default=str(ROOT), help="a folder with config/, wiring/ and data/ (for tests)")
    a = ap.parse_args(argv)
    root = Path(a.root)
    if a.what == "faults-exp2":
        try:
            choices = json.loads((root / "config" / "design_choices.json").read_text(encoding="utf-8"))
            if not (a.plan and a.confirmed):
                raise ContractError("faults-exp2 needs --plan and --confirmed")
            plan = units.read_json(a.plan, "the plan")
            rows = [json.loads(ln) for ln in Path(a.confirmed).read_text(encoding="utf-8").splitlines() if ln.strip()]
            doc = units.exp2_faults(plan, rows, choices)
            _write(Path(a.out), doc)
            print("faults for Experiment 2: %s (confirmed rows read %d)" % (
                ", ".join("rule %s %d" % kv for kv in doc["counts"].items()) or "none", len(rows)))
        except (ContractError, DataError, OSError, ValueError) as e:
            print("error: %s: %s" % (type(e).__name__, e), file=sys.stderr)
            return 2
        return 0
    if a.experiment is None or a.split is None:
        print("error: catalogue and draw need --experiment and --split", file=sys.stderr)
        return 2
    try:
        choices = json.loads((root / "config" / "design_choices.json").read_text(encoding="utf-8"))
        wiring = json.loads((root / "wiring" / "wiring.json").read_text(encoding="utf-8"))
        cat = planting.catalogue(wiring, choices, a.experiment)
        out = Path(a.out)
        cat_doc = {"experiment": a.experiment, "seed": choices["seeds"]["faults"], "count": len(cat),
                   "counts": _kind_counts(cat), "variants": cat}
        _write(out / ("exp%d_catalogue.json" % a.experiment), cat_doc)
        print("catalogue experiment %d: %d variants" % (a.experiment, len(cat)))
        for k, n in sorted(cat_doc["counts"].items()):
            print("  %s %d" % (k, n))
        if a.what == "draw":
            cases = visits.read_cases(root / choices["cases"]["files"][str(a.experiment)], a.experiment)
            plan = planting.draw(cases, cat, choices, a.experiment, a.split)
            _write(out / ("exp%d_plan.json" % a.experiment), plan)
            print("plan experiment %d, split %s, seed %s" % (a.experiment, a.split, plan["seed"]))
            print(json.dumps(plan["counts"], indent=1))
    except (ContractError, DataError, KeyError, OSError, ValueError) as e:
        print("error: %s: %s" % (type(e).__name__, e), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
