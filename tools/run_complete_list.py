#!/usr/bin/env python3
"""The complete list of violations, run with the AI parts off (version 3).

    python3 tools/run_complete_list.py --experiment 1 --split test --name NAME

Every variant of the list of violations that is not marked apart (rules 1 to 3; custody/planting.catalogue, computed
from the wiring, or --catalogue FILE) is planted on planting.complete_list_cases cases drawn by lot for that variant,
under all three methods, with the stand-in texts and the monitor's and the review's AI parts off: no AI call is made.
The clean twins of the cases used are run too, so that a flag that names only a rule can be compared with a clean run.
The run folder is runs/NAME (--runs-dir): the scorer's files, scores.json and complete_list.json, which says for each
rule, kind and method how many violations were blocked, flagged or missed, and names each kind that a method cannot see
at all (it missed every violation of the kind that took effect). It tests the bench and the three methods' programs, not
the experiment: nothing here uses a real answer. The tool prints counts only. Exit code: 0 done, 2 a bad input.
"""
import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import assemble, bench, datasets, planting, score, score_parts, store, units, visits, watch  # noqa: E402
from custody.core import CustodyError  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--experiment", type=int, choices=[1], default=1, help="1: the words flow (rules 1 to 3)")
    ap.add_argument("--split", choices=["tune", "test"], default="tune")
    ap.add_argument("--name", required=True)
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--visits", default=None, help="the case file (default data/cases/exp1.jsonl)")
    ap.add_argument("--catalogue", default=None, help="the list of variants (default: computed from the wiring)")
    a = ap.parse_args(argv)
    try:
        choices = watch.ai_parts_off(datasets.default_choices())  # the AI parts off: the review and the monitor run their programs only
        wiring = assemble.load_wiring()
        rchoices = bench.run_choices(choices)
        cases = [v for v in visits.read_cases(a.visits or visits.case_path(a.experiment, choices), a.experiment)
                 if v.split == a.split]
        by_id = {v.visit_id: v for v in cases}
        ids = sorted(by_id)
        if a.catalogue:
            cat = units.variants_by_id(units.read_json(a.catalogue, "the list of variants"))
            variants = list(cat.values())
        else:
            variants = planting.catalogue(wiring, choices, a.experiment)
        variants = [v for v in variants if not v["apart"]]
        cfg, want = choices["bench_plan"]["complete_list"], choices["planting"]["complete_list_cases"]
        run_dir = Path(a.runs_dir) / a.name
        if run_dir.exists():
            raise CustodyError("%s exists: use another --name" % run_dir)
        seed = choices["seeds"]["faults"]
        todo, plan, n, used = [], {}, 0, set()
        for v in variants:
            lot = random.Random("%s:%s:%s" % (seed, cfg["sub_seed"], v["variant_id"]))
            for cid in lot.sample(ids, min(want, len(ids))):
                n += 1
                row = {"plant_id": cfg["plant_id"].format(n=n), "rule": v["rule"]}
                uid = units.unit_id(cid, row["plant_id"])
                todo.append(units.make_unit(by_id[cid], uid, "complete_list", row))
                plan[uid] = units.fault_of_variant(v)
                used.add(cid)
        for cid in sorted(used):
            todo.append(by_id[cid])
            plan[cid] = None
        conds = choices["conditions"]["order"]
        parts = dict(assemble.make_parts(wiring, rchoices))
        bench.run_all(todo, conds, plan, parts, wiring, choices, run_dir)
        counts = visits.case_counts(todo)
        counts.update({"experiment": a.experiment, "ai_parts": "off", "faults_planned": n,
                       "variants": len(variants), "complete_list": True})
        store.write_manifest(run_dir, a.name, choices["seeds"], conds, counts,
                             assemble.manifest_fingerprints(choices, ROOT / "data" / "raw"), ai="canned")
        scores = score.score_run(run_dir, wiring, choices)
        table = score_parts.by_kind_table(scores["attempts"], choices, None)
        doc = {"experiment": a.experiment, "split": a.split, "variants": len(variants), "cases_per_variant": want,
               "units": n, "clean_twins": len(used), "ai_parts": "off", "by_kind": table,
               "cannot_see": score_parts.cannot_see(table),
               "note": "the stand-in texts and no AI part: this tests what each method's program can see"}
        store.write_json(run_dir / "complete_list.json", doc)
        cells = [c for k in table.values() for kinds in k.values() for c in kinds.values()]
        print("complete list: %d variants, %d cases each, %d planted units and %d clean twins under %d methods, into %s" % (
            len(variants), want, n, len(used), len(conds), run_dir))
        print("kinds by method: %d cells, %d of them that no violation reached; written to %s" % (
            len(cells), sum(1 for c in cells if c["sees"] == "did not take effect"), run_dir / "complete_list.json"))
    except (CustodyError, OSError, ValueError, KeyError) as e:
        print("error: %s: %s" % (type(e).__name__, e))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
