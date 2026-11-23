#!/usr/bin/env python3
"""The full bench for one experiment (Version 2): the cases of data/cases/exp<N>.jsonl, faults planned, all four
conditions run into runs/<name>_e<N>/, the manifest written and the scorer run.

--experiment 1|2 is required: 1 runs the words flow on transcripts (rules 1 to 3), 2 the advice flow on questions
(rules 4 to 6). --trial N selects N clean practice cases plus the practice violations of that experiment, each on a
different practice case that is not among the clean ones."""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import assemble, bench, datasets, faults, score, store, visits, watch  # noqa: E402
from custody.core import CustodyError  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--experiment", type=int, choices=[1, 2], required=True, help="1: transcripts, rules 1 to 3; 2: questions, rules 4 to 6")
    ap.add_argument("--name", default="bench", help="the run folder is runs/<name>_e<experiment>")
    ap.add_argument("--cases", "--visits", dest="cases", default=None,
                    help="the case file (default data/cases/exp<experiment>.jsonl)")
    ap.add_argument("--split", choices=["tune", "test", "all"], default="all")
    ap.add_argument("--sealed", action="store_true", help="add the sealed faults after the development ones")
    ap.add_argument("--limit", type=int, default=None, help="run only the first n cases of the split")
    ap.add_argument("--conditions", default=None, help="comma list, for example A,B (default: A,A+,B; C is still available)")
    ap.add_argument("--ai-parts", choices=["on", "off"], default="on",
                    help="off: the review and the monitor run their program parts only (no AI call for them)")
    ap.add_argument("--trial", type=int, default=None, metavar="N",
                    help="N clean practice cases plus the practice violations, each on a different practice case")
    a = ap.parse_args(argv)
    try:
        exp = a.experiment
        choices = datasets.default_choices()
        if a.ai_parts == "off":
            choices = watch.ai_parts_off(choices)
        wiring = assemble.load_wiring()
        rchoices = bench.run_choices(choices)  # once; goes to make_parts and run_all
        every = visits.read_cases(a.cases or str(visits.case_path(exp, choices)), exp)
        clean_ids = None
        if a.trial:
            if a.split != "all" or a.limit or a.sealed:
                raise CustodyError("--trial takes the practice set by itself: leave out --split, --limit and --sealed")
            vs, plan, clean_ids, unplaced = faults.plan_trial(
                every, faults.load_practice_faults(exp, choices), a.trial, choices, wiring)
        else:
            vs = [v for v in every if a.split == "all" or v.split == a.split]
            if a.limit:
                vs = vs[:a.limit]
            fl = faults.load_faults(choices, ROOT, include_sealed=a.sealed)
            plan, unplaced = faults.plan_faults_report(vs, fl, choices, wiring)
        run_dir = ROOT / "runs" / ("%s_e%d" % (a.name, exp))
        if run_dir.exists():
            shutil.rmtree(str(run_dir))
        parts = assemble.make_parts(wiring, rchoices)
        conds = a.conditions.split(",") if a.conditions else choices["conditions"]["order"]
        bench.run_all(vs, conds, plan, parts, wiring, choices, run_dir)  # run_one needs the fault settings and strips them itself
        counts = visits.case_counts(vs)
        counts["experiment"] = exp
        counts["ai_parts"] = a.ai_parts
        counts["faults_planned"] = sum(1 for f in plan.values() if f)
        counts["faults_unplaced"] = unplaced
        if clean_ids is not None:
            counts["clean_cases"] = len(clean_ids)
        store.write_manifest(run_dir, "%s_e%d" % (a.name, exp), choices["seeds"], conds, counts,
                             assemble.manifest_fingerprints(choices, ROOT / "data" / "raw"))
        sc_choices = dict(choices, conditions=dict(choices["conditions"], order=list(conds)))  # a named C is scored too
        scores = score.score_run(run_dir, wiring, sc_choices)
        print("experiment %d: ran %d cases under %d conditions into %s" % (exp, len(vs), len(conds), run_dir))
        if a.trial:
            print("trial: %d clean, %d planted (%s)" % (len(clean_ids), counts["faults_planned"],
                  ", ".join(sorted(f["fault_id"] for f in plan.values() if f))))
            print("planted violations that did not take effect: %s" % (
                ", ".join(sorted({x["fault_id"] for x in scores["did_not_fire"]})) or "none"))
        if not scores["header"].get("complete"):
            print("scores are partial (scores.partial.json): the judge has not read every advice text the program cannot read")
        if unplaced:
            print("faults no case could take: %s" % ", ".join(unplaced))
    except CustodyError as e:
        print("error: %s" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
