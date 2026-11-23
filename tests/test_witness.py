import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody.core import LedgerError, Record, canon  # noqa: E402
from custody.journal import make_ledger  # noqa: E402
from custody.receipt import build_receipt, check_receipt  # noqa: E402
from custody.witness import Witness, ZERO_HEAD, chain_head, mac_for  # noqa: E402

D = json.load(open(ROOT / "config" / "design_choices.json", encoding="utf-8"))
W = json.load(open(ROOT / "wiring" / "wiring.json", encoding="utf-8"))
KEY = bytes.fromhex(D["witness"]["test_key_hex"])
D_NO_WITNESS = copy.deepcopy(D)
D_NO_WITNESS["guards"]["witness"] = False


def hand(t, action, kind, frm, to, decision="deliver", verdicts=None):
    h = {"handover_id": "x#%d" % t, "run_id": "x", "t": t, "action": action, "step": "s",
         "from_place": frm, "to_place": to, "kind": kind, "item_ids": ["i"], "move_id": "m"}
    return Record(seq=0, run_id="x", t=t, handover=h, labels=[], verdicts=verdicts or [],
                  decision=decision, prev_fp="", fp="", receipt=None)


def close_record(t, verdicts=None):
    return Record(seq=0, run_id="x", t=t, handover={"action": "close", "t": t}, labels=[],
                  verdicts=verdicts or [], decision="deliver", prev_fp="", fp="", receipt=None)


def verdict(rule, v):
    return {"rule": rule, "verdict": v, "reason": ""}


def write_run(folder, run_id, choices=D):
    led = make_ledger(folder, run_id, choices)
    led.write(hand(1, "send", "transcript", "transcriber", "note_writer"))
    led.write(hand(2, "send", "transcript", "transcriber", "analytics", "block",
                   [verdict(1, "broken"), verdict(2, "kept")]))
    led.write(hand(3, "delete", "transcript", "transcriber", None, "flag", [verdict(2, "broken")]))
    led.write(hand(4, "send", "transcript", "transcriber", "note_writer"))
    led.write(close_record(9, [verdict(2, "broken")]))
    return led


def read_lines(path):
    return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]


class Folder(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def files(self, run_id):
        return (read_lines(self.dir / "journal" / ("%s.jsonl" % run_id)),
                read_lines(self.dir / "witness" / "log.jsonl"))

    def receipt(self, led, run_id="x", cond="B", proof=None):
        proof = proof or D["model"]["result_format"] and {
            "status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
        return build_receipt(run_id, cond, [asdict(r) for r in led.records()], proof, W, D)


class TestWitness(Folder):
    def test_chain_and_mac(self):
        w = Witness(KEY, self.dir / "log.jsonl")
        a = w.submit("aa", 1)
        b = w.submit("bb", 2)
        self.assertEqual(a.prev_head, ZERO_HEAD)
        self.assertEqual(a.head, chain_head(ZERO_HEAD, "aa"))
        self.assertEqual(b.prev_head, a.head)
        self.assertEqual((a.index, b.index), (0, 1))
        self.assertEqual(a.mac, mac_for(KEY, 0, "aa", a.head, 1))
        self.assertTrue(w.check(a) and w.check(b))
        self.assertFalse(w.check(type(a)(0, "aa", ZERO_HEAD, a.head, 1, "00")))
        self.assertEqual(len(w.entries()), 2)

    def test_second_witness_continues_the_log(self):
        Witness(KEY, self.dir / "log.jsonl").submit("aa", 1)
        w2 = Witness(KEY, self.dir / "log.jsonl")
        r = w2.submit("bb", 1)
        self.assertEqual(r.index, 1)
        self.assertEqual(r.prev_head, chain_head(ZERO_HEAD, "aa"))

    def test_witness_never_holds_more_than_fingerprints(self):
        w = Witness(KEY, self.dir / "log.jsonl")
        w.submit("aa", 1)
        row = read_lines(self.dir / "log.jsonl")[0]
        self.assertEqual(sorted(row), ["head", "index", "mac", "prev_head", "record_fp", "t"])


class TestLedger(Folder):
    def test_fills_four_fields_and_journal_has_null_receipt(self):
        led = write_run(self.dir, "x")
        recs = led.records()
        self.assertEqual([r.seq for r in recs], [0, 1, 2, 3, 4])
        self.assertEqual(recs[0].prev_fp, "")
        self.assertEqual(recs[1].prev_fp, recs[0].fp)
        self.assertTrue(all(r.receipt for r in recs))
        journal, log = self.files("x")
        self.assertEqual([j["fp"] for j in journal], [r.fp for r in recs])
        self.assertTrue(all(j["receipt"] is None for j in journal))
        self.assertEqual([e["record_fp"] for e in log], [r.fp for r in recs])

    def test_witness_guard_off_sends_nothing(self):
        led = write_run(self.dir, "x", D_NO_WITNESS)
        self.assertTrue(all(r.receipt is None for r in led.records()))
        self.assertEqual(self.files("x")[1], [])

    def test_unwritable_journal_raises(self):
        (self.dir / "journal").write_text("a file", encoding="utf-8")
        with self.assertRaises(LedgerError):
            make_ledger(self.dir, "x", D)


class TestCheck(Folder):
    def setUp(self):
        super().setUp()
        self.led = write_run(self.dir, "x")
        self.rcpt = self.receipt(self.led)
        self.journal, self.log = self.files("x")

    def check(self, rcpt=None, journal=None, log=None, key=KEY):
        return check_receipt(rcpt or self.rcpt, journal or self.journal, log or self.log, key)

    def test_untouched_passes(self):
        res = self.check()
        self.assertEqual(res, {"ok": True, "problems": []})
        self.assertTrue(self.check(key=None)["ok"])

    def test_changed_record_fails(self):
        j = copy.deepcopy(self.journal)
        j[1]["decision"] = "deliver"
        self.assertFalse(self.check(journal=j)["ok"])

    def test_removed_record_fails(self):
        for drop in (0, 2, 4):
            j = copy.deepcopy(self.journal)
            del j[drop]
            self.assertFalse(self.check(journal=j)["ok"], drop)

    def test_reordered_records_fail(self):
        j = copy.deepcopy(self.journal)
        j[1], j[2] = j[2], j[1]
        self.assertFalse(self.check(journal=j)["ok"])

    def test_wrong_mac_fails_only_with_key(self):
        log = copy.deepcopy(self.log)
        log[2]["mac"] = "0" * 64
        self.assertFalse(self.check(log=log)["ok"])
        self.assertTrue(self.check(log=log, key=None)["ok"])

    def test_wrong_key_fails(self):
        self.assertFalse(self.check(key=b"x" * 32)["ok"])

    def test_witness_log_tampering_fails(self):
        log = copy.deepcopy(self.log)
        log[1]["head"] = "f" * 64
        self.assertFalse(self.check(log=log, key=None)["ok"])
        log = copy.deepcopy(self.log)
        del log[1]
        self.assertFalse(self.check(log=log, key=None)["ok"])

    def test_receipt_heads_and_lines_must_follow(self):
        for field, value in (("journal_head", "0" * 64), ("witness_head", "0" * 64)):
            r = copy.deepcopy(self.rcpt)
            r[field] = value
            self.assertFalse(self.check(rcpt=r)["ok"], field)
        r = copy.deepcopy(self.rcpt)
        r["lines"][0]["status"] = "kept"
        self.assertFalse(self.check(rcpt=r)["ok"])
        r = copy.deepcopy(self.rcpt)
        r["trail"][0]["went"].append("analytics")
        self.assertFalse(self.check(rcpt=r)["ok"])
        r = copy.deepcopy(self.rcpt)
        r["lines"][1]["level"] = "proven"
        self.assertFalse(self.check(rcpt=r)["ok"])

    def test_witness_off_reports_one_line(self):
        led = write_run(self.dir / "off", "x", D_NO_WITNESS)
        recs = [asdict(r) for r in led.records()]
        proof = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
        r = build_receipt("x", "B", recs, proof, W, D)
        journal = read_lines(self.dir / "off" / "journal" / "x.jsonl")
        res = check_receipt(r, journal, [], KEY)
        self.assertIn("witness off", res["problems"])
        self.assertFalse(res["ok"])

    def test_two_runs_in_one_folder_both_pass(self):
        write_run(self.dir, "y")
        self.led2 = None
        for run_id in ("x", "y"):
            journal, log = self.files(run_id)
            self.assertEqual(len(log), 10)
            led_recs = journal
            # rebuild the receipt from the filled records of that run
            filled = [dict(j) for j in led_recs]
            for j in filled:
                e = next(e for e in log if e["record_fp"] == j["fp"])
                j["receipt"] = e
            proof = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
            r = build_receipt(run_id, "B", filled, proof, W, D)
            self.assertTrue(check_receipt(r, journal, log, KEY)["ok"], run_id)

    def test_a_with_no_records(self):
        proof = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
        r = build_receipt("x", "A", [], proof, W, D)
        self.assertTrue(check_receipt(r, [], [], KEY)["ok"])


class TestReceipt(Folder):
    def test_hand_made_receipt_equals_one_written_by_hand(self):
        recs = [
            {"seq": 0, "run_id": "x", "t": 1,
             "handover": {"action": "send", "t": 1, "kind": "transcript", "from_place": "transcriber",
                          "to_place": "note_writer"},
             "verdicts": [verdict(1, "kept"), verdict(2, "kept")], "decision": "deliver",
             "labels": [], "prev_fp": "", "fp": "a", "receipt": None},
            {"seq": 1, "run_id": "x", "t": 2,
             "handover": {"action": "send", "t": 2, "kind": "transcript", "from_place": "transcriber",
                          "to_place": "analytics"},
             "verdicts": [verdict(1, "broken")], "decision": "block",
             "labels": [], "prev_fp": "a", "fp": "b", "receipt": None},
            {"seq": 2, "run_id": "x", "t": 3,
             "handover": {"action": "delete", "t": 3, "kind": "transcript", "from_place": "transcriber",
                          "to_place": None},
             "verdicts": [verdict(2, "broken")], "decision": "flag",
             "labels": [], "prev_fp": "b", "fp": "c", "receipt": None},
            {"seq": 3, "run_id": "x", "t": 9, "handover": {"action": "close", "t": 9},
             "verdicts": [verdict(2, "broken"), verdict(6, "broken")], "decision": "flag",
             "labels": [], "prev_fp": "c", "fp": "d", "receipt": None},
        ]
        proof = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
        got = build_receipt("x", "B", recs, proof, W, D)
        want_lines = [
            {"rule": 1, "says": D["receipt"]["says"]["1"], "level": "checked", "status": "blocked", "records": [1]},
            {"rule": 2, "says": D["receipt"]["says"]["2"], "level": "checked", "status": "flagged", "records": [2]},
            {"rule": 3, "says": D["receipt"]["says"]["3"], "level": "checked", "status": "kept", "records": []},
            {"rule": 4, "says": D["receipt"]["says"]["4"], "level": "checked", "status": "kept", "records": []},
            {"rule": 5, "says": D["receipt"]["says"]["5"], "level": "checked", "status": "kept", "records": []},
            {"rule": 6, "says": D["receipt"]["says"]["6"], "level": "checked", "status": "kept", "records": []},
        ]
        self.assertEqual(got["lines"], want_lines)
        self.assertEqual(got["trail"], [
            {"kind": "transcript", "went": ["transcriber", "note_writer"], "deleted": {"transcriber": 3}},
        ])
        self.assertEqual([p["place"] for p in got["named_places"]],
                         [p["id"] for p in W["promise"]["places"] if p["named"]])
        self.assertEqual(got["named_places"][0], {"place": "transcriber", "who": "the scribe service, which holds the transcript"})
        self.assertEqual(got["journal_head"], "d")
        self.assertEqual(got["proof"], proof)

    def test_levels_under_every_condition_and_proof(self):
        proof = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
        for cond in ("A", "A+"):
            r = build_receipt("x", cond, [], proof, W, D)
            self.assertEqual({l["level"] for l in r["lines"]}, {"promised only"})
            self.assertEqual({l["status"] for l in r["lines"]}, {"not checked"})
            self.assertEqual(len(r["named_places"]), 9)
        passed = {"status": "passed", "proven_rules": [1, 2], "counterexample": None, "states": 5}
        r = build_receipt("x", "C", [], passed, W, D)
        self.assertEqual([l["level"] for l in r["lines"]], ["proven", "proven"] + ["checked"] * 4)
        cex = {"status": "counterexample", "proven_rules": [1], "counterexample": {}, "states": 5}
        r = build_receipt("x", "C", [], cex, W, D)
        self.assertEqual({l["level"] for l in r["lines"]}, {"checked"})

    def test_close_record_raises_nothing_in_lines(self):
        led = write_run(self.dir, "x")
        recs = [asdict(r) for r in led.records()]
        proof = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
        r = build_receipt("x", "B", recs, proof, W, D)
        self.assertNotIn(4, r["lines"][1]["records"])
        self.assertEqual(r["journal_head"], recs[-1]["fp"])
        self.assertEqual(r["witness_head"], recs[-1]["receipt"]["head"])

    def test_rule_outside_rules_checked_is_not_checked(self):
        ch = copy.deepcopy(D)
        ch["guards"]["rules_checked"] = [1, 2, 3]
        proof = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
        r = build_receipt("x", "B", [], proof, W, ch)
        self.assertEqual([l["status"] for l in r["lines"]], ["kept"] * 3 + ["not checked"] * 3)


class TestTool(Folder):
    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(ROOT / "tools" / "check_receipt.py")] + list(args),
                              capture_output=True, text=True)

    def test_exit_codes(self):
        led = write_run(self.dir, "x")
        proof = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
        r = build_receipt("x", "B", [asdict(x) for x in led.records()], proof, W, D)
        rpath = self.dir / "receipt.json"
        rpath.write_text(json.dumps(r), encoding="utf-8")
        jpath = self.dir / "journal" / "x.jsonl"
        wpath = self.dir / "witness" / "log.jsonl"
        kpath = self.dir / "key.hex"
        kpath.write_text(D["witness"]["test_key_hex"], encoding="utf-8")
        ok = self.run_tool(str(rpath), "--journal", str(jpath), "--witness-log", str(wpath),
                           "--key-file", str(kpath))
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        self.assertTrue(json.loads(ok.stdout)["ok"])
        lines = jpath.read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[1])
        row["decision"] = "deliver"
        lines[1] = canon(row)
        jpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
        bad = self.run_tool(str(rpath), "--journal", str(jpath), "--witness-log", str(wpath))
        self.assertEqual(bad.returncode, 1)
        self.assertFalse(json.loads(bad.stdout)["ok"])
        missing = self.run_tool(str(rpath), "--journal", str(self.dir / "none"), "--witness-log", str(wpath))
        self.assertEqual(missing.returncode, 2)
        self.assertEqual(self.run_tool().returncode, 2)


if __name__ == "__main__":
    unittest.main()
