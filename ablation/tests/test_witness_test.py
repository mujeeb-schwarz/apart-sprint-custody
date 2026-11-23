"""Tests of the witness test: the forgers and checks on a small hand-made record, and the two gates.

    python3 -m unittest ablation/tests/test_witness_test.py
"""
import copy
import json
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "ablation"))

import witness_test as wt  # noqa: E402
from custody import assemble, bench, datasets  # noqa: E402
from custody.journal import record_fingerprint  # noqa: E402
from custody.receipt import build_receipt, check_receipt  # noqa: E402
from custody.witness import ZERO_HEAD, chain_head, mac_for  # noqa: E402

CHOICES = datasets.default_choices()
WIRING = assemble.load_wiring()
KEY = bench._witness_key(CHOICES)


def handover(action, step, frm, to, kind, t, n):
    return {"action": action, "step": step, "from_place": frm, "to_place": to, "kind": kind, "item_ids": ["i%d" % n],
            "handover_id": "h%d" % n, "move_id": None, "run_id": "r", "t": t}


def make_case():
    """Four records (three handovers and the close), chained as Ledger.write chains them, the witness log as
    Witness.submit writes it, and the receipt as bench step 6 builds it."""
    hs = [handover("send", "transcriber", "transcriber", "note_writer", "transcript", 1, 0),
          handover("send", "note_writer", "note_writer", "doctor", "note_draft", 2, 1),
          handover("delete", "note_writer", "note_writer", "note_writer", "transcript", 3, 2),
          handover("close", "close", "bench", "bench", "close", 4, 3)]
    records, witness = [], []
    head = ZERO_HEAD
    for i, h in enumerate(hs):
        rec = {"run_id": "r", "seq": i, "t": h["t"], "handover": h, "labels": [], "verdicts": [],
               "decision": "deliver", "prev_fp": records[-1]["fp"] if records else "", "fp": "", "receipt": None}
        rec["fp"] = record_fingerprint(rec)
        records.append(rec)
        new = chain_head(head, rec["fp"])
        witness.append({"index": i, "record_fp": rec["fp"], "prev_head": head, "head": new, "t": h["t"],
                        "mac": mac_for(KEY, i, rec["fp"], new, h["t"])})
        head = new
    in_memory = [dict(r, receipt=dict(witness[i])) for i, r in enumerate(records)]
    receipt = build_receipt("r", "B", in_memory, dict(bench.NOT_RUN), WIRING, bench.run_choices(CHOICES))
    return records, witness, receipt


def careless(records, mode):
    """The three kinds of planted edit, done by hand the way custody.faults.edit_lines does them."""
    out = copy.deepcopy(records)
    if mode == "entry_removed":
        del out[1]
    elif mode == "entry_changed":
        out[1]["handover"]["to_place"] = "note_writer_cache"
    else:
        before = out[0]
        rec = {"run_id": "r", "seq": 1, "t": before["t"], "handover": handover("send", "x", "x", "y", "note_draft", 1, 9),
               "labels": [], "verdicts": [], "decision": "deliver", "prev_fp": before["fp"], "receipt": None}
        rec["fp"] = record_fingerprint(rec)
        out.insert(1, rec)
    return out


def chain_part(problems):
    return [p for p in problems if wt.is_chain_kind(p)]


class HandMadeRecord(unittest.TestCase):
    def setUp(self):
        self.records, self.witness, self.receipt = make_case()

    def full(self, recs, wit, rec=None):
        return check_receipt(rec or self.receipt, recs, wit, KEY)["problems"]

    def test_clean_record_reports_nothing(self):
        self.assertEqual(wt.chain_alone(self.records), [])
        self.assertEqual(self.full(self.records, self.witness), [])

    def test_careless_chain_alone_matches_frozen_check(self):
        for mode in wt.EDIT_KINDS:
            recs = careless(self.records, mode)
            mine = wt.chain_alone(recs)
            self.assertTrue(mine, mode)
            self.assertEqual(mine, chain_part(self.full(recs, self.witness)), mode)

    def test_careless_kinds(self):
        kinds = {m: {wt.kind_of(p) for p in wt.chain_alone(careless(self.records, m))} for m in wt.EDIT_KINDS}
        self.assertIn("record content does not match its fingerprint", kinds["entry_changed"])
        self.assertIn("record does not link to the record before", kinds["entry_removed"])
        self.assertIn("record does not link to the record before", kinds["entry_added"])

    def test_careful_is_consistent_with_itself_and_caught_by_the_witness(self):
        for mode in wt.EDIT_KINDS:
            edited = careless(self.records, mode)
            forged = wt.careful(self.records, edited)
            self.assertEqual(wt.chain_alone(forged), [], mode)
            self.assertEqual([r["seq"] for r in forged], list(range(len(forged))))
            self.assertTrue(all(r["receipt"] is None for r in forged))
            problems = self.full(forged, self.witness)
            self.assertIn("witness holds no fingerprint for a record", {wt.kind_of(p) for p in problems}, mode)
            self.assertEqual(self.records[0], forged[0])  # the untouched head is kept

    def test_operator_leaves_only_the_receipt_problems(self):
        for mode in wt.EDIT_KINDS:
            forged = wt.careful(self.records, careless(self.records, mode))
            wit = wt.operator_witness(self.witness, self.records, forged, KEY)
            self.assertEqual(len(wit), len(forged))
            self.assertEqual(wit[0], self.witness[0])
            problems = self.full(forged, wit)
            self.assertTrue(problems, mode)
            self.assertEqual({wt.PART_OF_KIND[wt.kind_of(p)] for p in problems}, {"receipt"}, mode)
            again = wt.receipt_rebuilt(self.receipt, forged, wit, "B", WIRING, CHOICES)
            self.assertEqual(self.full(forged, wit, again), [], mode)

    def test_operator_needs_the_key(self):
        forged = wt.careful(self.records, careless(self.records, "entry_changed"))
        wit = wt.operator_witness(self.witness, self.records, forged, b"\x00" * 32)
        kinds = {wt.kind_of(p) for p in self.full(forged, wit)}
        self.assertIn("witness entry mac wrong", kinds)

    def test_every_frozen_problem_has_a_kind(self):
        recs = careless(self.records, "entry_added")
        for p in self.full(recs, self.witness) + self.full(wt.careful(self.records, recs), self.witness):
            self.assertFalse(wt.kind_of(p).startswith("other"), p)


class Gates(unittest.TestCase):
    """The two gates on the real units (stored answers, no AI). Runs the whole experiment into a test folder."""

    @classmethod
    def setUpClass(cls):
        cls.out = ROOT / "ablation" / "out" / "_test_run"
        if cls.out.exists():
            shutil.rmtree(str(cls.out))
        code = wt.main(["--out", str(cls.out)])
        cls.code = code
        cls.res = json.loads((cls.out / "results.json").read_text(encoding="utf-8"))
        cls.rows = [json.loads(ln) for ln in (cls.out / "units.jsonl").read_text(encoding="utf-8").splitlines()]

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(str(cls.out), ignore_errors=True)

    def test_gate1_careless_full_check_reproduces_the_main_run(self):
        g = self.res["gate1"]
        self.assertEqual(self.res["table"]["careless"]["chain_with_witness"]["flagged"], 100)
        self.assertEqual(g["flagged_main_run"], 100)
        self.assertEqual(g["same_flag"], 100)
        self.assertTrue(g["held"])

    def test_gate2_clean_cases_report_nothing(self):
        g = self.res["gate2"]
        self.assertEqual(g["cases"], 157)
        self.assertEqual(g["with_problem"], {"chain_alone": 0, "chain_with_witness": 0})
        self.assertTrue(g["held"])

    def test_chain_alone_matches_frozen_check_on_real_careless_units(self):
        by = {}
        for r in self.rows:
            if r["set"] == "planted" and r["forger"] == "careless":
                by.setdefault(r["unit"], {})[r["check"]] = r["problems"]
        self.assertEqual(len(by), 100)
        for unit, d in by.items():
            self.assertEqual(d["chain_alone"], chain_part(d["chain_with_witness"]), unit)


if __name__ == "__main__":
    unittest.main()
