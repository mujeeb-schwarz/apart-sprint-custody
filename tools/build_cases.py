#!/usr/bin/env python3
"""Builds the two lists of cases (Version 2) and writes data/cases/exp1.jsonl and data/cases/exp2.jsonl; prints the counts.

Experiment 1: the 207 transcripts. Experiment 2: the graded questions plus the stored-answer questions (the practice
ones and a draw by lot for the test set, seeds.cases). Splits are read from the retired joined list, so nothing
moves between practice and test."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody.core import CustodyError  # noqa: E402
from custody import datasets, visits  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--out-dir", default=str(ROOT / "data" / "cases"))
    a = ap.parse_args(argv)
    try:
        choices = datasets.default_choices()
        lists = visits.build_cases(choices, a.raw)
        for exp in (1, 2):
            path = Path(a.out_dir) / ("exp%d.jsonl" % exp)
            visits.write_visits(path, lists[exp])
            print("experiment %d: %s %s" % (exp, path, json.dumps(visits.case_counts(lists[exp]), sort_keys=True)))
    except CustodyError as e:
        print("error: %s" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
