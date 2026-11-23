#!/usr/bin/env python3
"""Scores the parts of a run folder that stand apart from the graded 100 (custody/score_parts.py) and writes
runs/<name>/scores_parts.json: the hidden instruction (obeyed, flagged on the hidden line, blocked / flagged / missed),
the repeat check (the same outcome as the first run) and the by-kind table with the kinds a method cannot see.
Prints counts only; the file holds the tables. A run folder is scored again from its files, with no AI.

    python3 tools/score_parts.py RUN_DIR
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import datasets, score, score_parts, store  # noqa: E402
from custody.core import CustodyError  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("run_dir")
    a = ap.parse_args(argv)
    try:
        wiring = json.loads((ROOT / "wiring" / "wiring.json").read_text(encoding="utf-8"))
        choices = datasets.default_choices()
        scores = score.score_run(a.run_dir, wiring, choices, None, None)
        parts = score_parts.score_parts(a.run_dir, scores, choices)
        parts["by_kind_all_parts"] = score_parts.by_kind_table(scores["attempts"], choices, None)
        parts["cannot_see"] = score_parts.cannot_see(parts["by_kind_all_parts"])
        store.write_json(Path(a.run_dir) / "scores_parts.json", parts)
        print(score_parts.counts_line(parts))
        print("written to %s" % (Path(a.run_dir) / "scores_parts.json"))
    except (CustodyError, OSError, ValueError) as e:
        print("error: %s" % e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
