"""Skips for the tests that read the public data sets.

The data sets are not part of this repository (see data/raw/README.md). A test that reads them is skipped, with a
message, when data/raw/ holds no data; with the data in place it runs unchanged."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
RETIRED = ROOT / "data" / "retired" / "visits.jsonl"

HAVE_RAW = (RAW / "medEvidence.csv").exists() and (RAW / "real-pocqi").is_dir() and (RAW / "aci-bench").is_dir()

needs_raw_data = unittest.skipUnless(
    HAVE_RAW, "needs the public data sets in data/raw/ (not included; see data/raw/README.md)")
needs_retired_cases = unittest.skipUnless(
    RETIRED.exists(), "needs data/retired/visits.jsonl, an earlier case list not included in this repository")
