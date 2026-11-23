#!/usr/bin/env python3
"""Files the owner's predictions before any test visit runs on real answers.

    python3 tools/file_predictions.py <path to the predictions page> [--refile]

Copies the page to docs/predictions_as_filed.md and writes config/predictions_filed.json with the sha256 of that
copy, the local date and time with the time zone, and the scorer's fingerprint; prints the three values. If a
filing exists it refuses unless --refile is given; then the earlier json is kept beside it under a numbered name
and the new json records that it is a refiling.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import filing  # noqa: E402
from custody.core import CustodyError  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("page", help="the predictions page")
    ap.add_argument("--refile", action="store_true", help="file again; the earlier filing is kept beside it")
    ap.add_argument("--root", default=None, help=argparse.SUPPRESS)  # tests: another folder than the project's
    a = ap.parse_args(argv)
    try:
        rec = filing.file_predictions(a.page, a.root, a.refile)
    except CustodyError as e:
        print("error: %s" % e)
        return 2
    print("page sha256:         %s" % rec["page_sha256"])
    print("filed at:            %s" % rec["filed_at"])
    print("scorer fingerprint:  %s" % rec["scorer_fingerprint"])
    if rec["refiling"]:
        print("this is a refiling; the earlier filing is kept as %s" % rec["earlier_filing"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
