#!/usr/bin/env python3
"""Check a visit receipt against its journal and the witness log.

usage: check_receipt.py RECEIPT --journal FILE --witness-log FILE [--key-file FILE]
Prints {"ok", "problems"}. Exit 0 when it passes, 1 when the check fails,
2 for bad input.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody.core import CustodyError, DataError, canon  # noqa: E402
from custody.receipt import check_receipt  # noqa: E402


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise DataError("cannot read %s: %s" % (path, exc))


def read_lines(path):
    rows = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if line.strip():
                    rows.append(json.loads(line))
    except (OSError, ValueError) as exc:
        raise DataError("cannot read %s: %s" % (path, exc))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument("receipt")
    parser.add_argument("--journal", required=True)
    parser.add_argument("--witness-log", required=True)
    parser.add_argument("--key-file")
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code not in (0, None) else 0
    try:
        receipt = read_json(args.receipt)
        records = read_lines(args.journal)
        entries = read_lines(args.witness_log)
        key = None
        if args.key_file:
            try:
                key = bytes.fromhex(Path(args.key_file).read_text(encoding="utf-8").strip())
            except (OSError, ValueError) as exc:
                raise DataError("cannot read the key file: %s" % exc)
        if not isinstance(receipt, dict):
            raise DataError("the receipt is not an object")
        result = check_receipt(receipt, records, entries, key)
    except CustodyError as exc:
        print("error: %s" % exc)
        return 2
    print(canon(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
