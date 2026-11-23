#!/usr/bin/env python3
"""Prints scores.json for a run folder (and writes it there), or the scorer's fingerprint."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody.core import CustodyError  # noqa: E402
from custody import datasets, score  # noqa: E402


def scorer_fingerprint() -> str:
    h = hashlib.sha256()
    for name in ("core.py", "stats.py", "score.py"):
        h.update((ROOT / "custody" / name).read_bytes())
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir", nargs="?")
    ap.add_argument("--fingerprint", action="store_true")
    ap.add_argument("--text", action="store_true",
                    help="print the results as plain text in the words of the method: rules down, methods across (Promised, "
                         "Monitored, Checked), the least that is enough, then the tables below it")
    ap.add_argument("--experiment", type=int, choices=[1, 2], default=None,
                    help="1 or 2: refuse a run folder whose cases are not of this experiment (a name without a path is read as runs/<name>_e<N>). "
                         "Scoring follows the experiment of the folder either way: 1 gives rules 1 to 3, 2 gives rules 4 to 6")
    ap.add_argument("--levels", choices=["reader_first", "judge_all"], default=None,
                    help="where certainty levels come from (default: the run's manifest, else the design choices)")
    a = ap.parse_args()
    if a.fingerprint:
        print(scorer_fingerprint())
        return 0
    if not a.run_dir:
        print("error: give a run folder or --fingerprint")
        return 2
    try:
        with open(str(ROOT / "wiring" / "wiring.json"), encoding="utf-8") as f:
            wiring = json.load(f)
        if a.experiment:
            if not Path(a.run_dir).exists() and (ROOT / "runs" / ("%s_e%d" % (a.run_dir, a.experiment))).exists():
                a.run_dir = str(ROOT / "runs" / ("%s_e%d" % (a.run_dir, a.experiment)))
            from custody import store
            exps = {v.get("experiment", 0) for v in store.read_jsonl(Path(a.run_dir) / "visits.jsonl")}
            if exps != {a.experiment}:
                print("error: %s holds cases of experiment %s, not %d" % (a.run_dir, sorted(exps) or "none", a.experiment))
                return 2
        res = score.score_run(a.run_dir, wiring, datasets.default_choices(), None, a.levels)
        # the header goes to stderr so that stdout stays plain JSON
        print(score.render_header(res["header"]), file=sys.stderr)
        print(score.render_text(res) if a.text else json.dumps(res, sort_keys=True, indent=1))
    except (CustodyError, OSError, ValueError) as e:
        print("error: %s" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
