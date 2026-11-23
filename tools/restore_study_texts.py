#!/usr/bin/env python3
"""Put the MedEvidence study texts back into the files of this repository.

On Sun 22 Nov 2026, a week after the sprint's report was submitted, the study texts of the MedEvidence
cases (Experiment 2) were withheld from this public copy. The data set is under the MIT licence, and the
articles it quotes stay under their publishers' licences. Each text was replaced by a marker that names
its question and its source, for example

    [study text withheld: medev:0 pmid:17466514]

A marker that ends in "first 20000" stands for the first 20,000 characters of the text, where an early
version of the chain cut each study at that length (runs/e2e). data/cases/withheld_study_texts.json lists
every file that held a marker, with the sha256 the file had before and after. This program reads the data
set's own file (data/raw/medEvidence.csv; data/raw/README.md says where to get it) and puts each text back
where its marker stands. It writes a file only when the restored bytes have the sha256 the file had before
the texts were withheld, and it writes through a temporary file, so a file is never left half restored.

    python3 tools/restore_study_texts.py                   restore every listed file
    python3 tools/restore_study_texts.py --check           only report each listed file's state
    python3 tools/restore_study_texts.py --raw-dir DIR     read medEvidence.csv from DIR

States in --check: "whole" (the sha256 from before the texts were withheld), "withheld" (the sha256 after),
"changed" (neither).

Exit code: 0 every listed file restored, or already whole (with --check: no file "changed"); 1 a file
would not match after restoring, or a marker names a text the data set does not hold, or (with --check) a
file is "changed"; 2 the data set's file, the list or a listed file is missing or unreadable.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import datasets  # noqa: E402

LIST = "data/cases/withheld_study_texts.json"
MARKER = re.compile(r"\[study text withheld: (medev:[^ \]]+) ([a-z]+:[^ \]]+)(?: first (\d+))?\]")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inside(root: Path, rel: str) -> Path:
    """The listed file, which must lie inside the repository folder."""
    p = (root / rel).resolve()
    if root.resolve() not in p.parents:
        raise ValueError("listed path leaves the repository: %s" % rel)
    return p


def write_atomic(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(prefix=".restore-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Put the MedEvidence study texts back.")
    ap.add_argument("--raw-dir", default=str(ROOT / "data" / "raw"), help="the folder that holds medEvidence.csv")
    ap.add_argument("--root", default=str(ROOT), help="the repository folder (default: this one)")
    ap.add_argument("--check", action="store_true", help="report only, change nothing")
    args = ap.parse_args(argv)
    root = Path(args.root)

    try:
        listing = json.loads((root / LIST).read_text(encoding="utf-8"))
        files = [(f, inside(root, f["path"])) for f in listing["files"]]
        current = {f["path"]: p.read_bytes() for f, p in files}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("cannot read %s or a file it lists: %s" % (LIST, exc))
        return 2

    if args.check:
        changed = 0
        for f, _ in files:
            now = sha256_bytes(current[f["path"]])
            state = "whole" if now == f["sha256_with_texts"] else ("withheld" if now == f["sha256_withheld"] else "changed")
            changed += state == "changed"
            print("%-9s %s" % (state, f["path"]))
        return 1 if changed else 0

    raw = Path(args.raw_dir) / "medEvidence.csv"
    if not raw.exists():
        print("the data set's file is missing: %s (see data/raw/README.md)" % raw)
        return 2
    texts = {}
    for q in datasets.load_medevidence(args.raw_dir):
        for s in q["sources"]:
            texts[(q["question_id"], s["source_id"])] = s["text"]

    bad = 0
    for f, p in files:
        data = current[f["path"]]
        if sha256_bytes(data) == f["sha256_with_texts"]:
            print("whole     %s" % f["path"])
            continue
        unknown = []

        def put_back(m):
            key = (m.group(1), m.group(2))
            if key not in texts:
                unknown.append("%s %s" % key)
                return m.group(0)
            text = texts[key] if m.group(3) is None else texts[key][:int(m.group(3))]
            return json.dumps(text, ensure_ascii=f["ensure_ascii"])[1:-1]

        restored = MARKER.sub(put_back, data.decode("utf-8")).encode("utf-8")
        if unknown:
            print("unknown   %s: %d markers name no text in the data set, e.g. %s; file left as it was"
                  % (f["path"], len(unknown), unknown[0]))
            bad += 1
        elif sha256_bytes(restored) != f["sha256_with_texts"]:
            print("MISMATCH  %s: the restored bytes do not have the listed sha256; file left as it was" % f["path"])
            bad += 1
        else:
            write_atomic(p, restored)
            print("restored  %s" % f["path"])
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
