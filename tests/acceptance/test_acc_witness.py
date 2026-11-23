"""Acceptance tests for WITNESS: the witness, the ledger (journal), the visit receipt and
the program that checks a receipt.

Written from docs/FRAME.md section 8, config/design_choices.json (D: receipt, witness,
guards, exports) and the frame addendum. Only custody/core.py and the public signatures
of D: exports are used. A test fails with a clear message when the part is missing;
none is skipped.
"""
import copy
import dataclasses
import hashlib
import hmac
import importlib
import json
import subprocess
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custody import core
from custody.core import Handover, LedgerError, Record, WitnessReceipt, canon, fingerprint

D = json.loads((ROOT / "config" / "design_choices.json").read_text(encoding="utf-8"))
W = json.loads((ROOT / "wiring" / "wiring.json").read_text(encoding="utf-8"))
KEY = bytes.fromhex(D["witness"]["test_key_hex"])
NOT_RUN = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
RUN = "v0001.B.r0"
ZERO = "0" * 64


def run_choices():
    c = copy.deepcopy(D)
    c.pop("faults", None)
    return c


def need(modname, *attrs):
    try:
        mod = importlib.import_module(modname)
    except Exception as e:
        raise AssertionError("part missing or broken: cannot import %s (%s: %s)" % (modname, type(e).__name__, e))
    out = []
    for a in attrs:
        if not hasattr(mod, a):
            raise AssertionError("part wrong: %s has no attribute %s" % (modname, a))
        out.append(getattr(mod, a))
    return out[0] if len(out) == 1 else tuple(out)


def as_dict(x):
    return asdict(x) if dataclasses.is_dataclass(x) else dict(x)


def read_jsonl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(ln) for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]


def mk(run_id, t, action, step, frm, to, kind, item_ids, move_id, n, decision="deliver", broken=()):
    h = asdict(Handover("%s#%d" % (run_id, n), run_id, t, action, step, frm, to, kind, item_ids, move_id))
    verdicts = [{"rule": r, "verdict": "broken" if r in broken else "kept", "reason": "x"} for r in range(1, 7)]
    return Record(0, run_id, t, h, [], verdicts, decision, "", "", None)


def close_record(run_id, t=38, broken=()):
    verdicts = [{"rule": r, "verdict": "broken" if r in broken else "kept", "reason": "x"} for r in range(1, 7)]
    return Record(0, run_id, t, {"action": "close", "t": t}, [], verdicts, "deliver", "", "", None)


def scenario(run_id=RUN, close_broken=()):
    """A hand-made journal: a delivered send, a delete, a blocked send, a flagged send, a close."""
    return [
        mk(run_id, 2, "send", "transcriber", "transcriber", "note_writer", "transcript", ["i1"], "w2", 1),
        mk(run_id, 3, "delete", "janitor", "transcriber", None, "transcript", ["i1"], "d3", 2),
        mk(run_id, 5, "send", "transcriber", "transcriber", "analytics", "transcript", ["i1"], None, 3,
           decision="block", broken=(1,)),
        mk(run_id, 18, "send", "ai_answer", "advice_tool", "clinician", "answer", ["i2"], "a2", 4,
           decision="flag", broken=(6,)),
        close_record(run_id, 38, close_broken),
    ]


def write_run(run_dir, run_id=RUN, cond="B", choices=None, proof=NOT_RUN, records=None):
    make_ledger, build_receipt = need("custody.journal", "make_ledger"), need("custody.receipt", "build_receipt")
    choices = choices if choices is not None else run_choices()
    ledger = make_ledger(Path(run_dir), run_id, choices)
    for r in (records if records is not None else scenario(run_id)):
        ledger.write(r)
    recs = ledger.records()
    receipt = build_receipt(run_id, cond, [asdict(r) for r in recs], proof, copy.deepcopy(W), choices)
    journal = read_jsonl(Path(run_dir) / "journal" / ("%s.jsonl" % run_id))
    wlog = read_jsonl(Path(run_dir) / "witness" / "log.jsonl")
    return ledger, recs, receipt, journal, wlog


# ------------------------------------------------------------------ the witness

class TestWitness(unittest.TestCase):
    def setUp(self):
        self.Witness = need("custody.witness", "Witness")
        self.tmp = tempfile.TemporaryDirectory()
        self.log = Path(self.tmp.name) / "log.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def test_submit_builds_the_fingerprint_chain_and_the_mac(self):
        w = self.Witness(KEY, self.log)
        fps = [fingerprint("record %d" % i) for i in range(4)]
        got = [as_dict(w.submit(fp, 10 + i)) for i, fp in enumerate(fps)]
        prev = ZERO
        for i, (fp, r) in enumerate(zip(fps, got)):
            head = hashlib.sha256((prev + fp).encode("utf-8")).hexdigest()
            self.assertEqual(r["record_fp"], fp)
            self.assertEqual(r["prev_head"], prev, "entry %d must link to the head before it" % i)
            self.assertEqual(r["head"], head, "head = sha256(prev_head + record_fp)")
            self.assertEqual(r["t"], 10 + i)
            msg = "%s|%s|%s|%s" % (r["index"], fp, head, 10 + i)
            self.assertEqual(r["mac"], hmac.new(KEY, msg.encode("utf-8"), hashlib.sha256).hexdigest(),
                             "mac = hmac_sha256(key, 'index|record_fp|head|t')")
            prev = head
        self.assertEqual([r["index"] for r in got], list(range(got[0]["index"], got[0]["index"] + 4)))
        self.assertIn(got[0]["index"], (0, 1))

    def test_entries_check_and_the_log_file(self):
        w = self.Witness(KEY, self.log)
        rs = [w.submit(fingerprint("r%d" % i), i) for i in range(3)]
        self.assertEqual([as_dict(e) for e in w.entries()], [as_dict(r) for r in rs])
        self.assertEqual(read_jsonl(self.log), [as_dict(r) for r in rs], "the log file holds one entry for each submit")
        for r in rs:
            self.assertTrue(w.check(r))
        r0 = as_dict(rs[0])
        for field, value in (("mac", ZERO), ("record_fp", fingerprint("other")), ("head", ZERO), ("index", r0["index"] + 7)):
            bad = dict(r0, **{field: value})
            bad = WitnessReceipt(**bad)
            self.assertFalse(w.check(bad), "a receipt with a changed %s must fail" % field)

    def test_a_new_witness_on_the_same_log_continues_the_chain(self):
        w = self.Witness(KEY, self.log)
        last = as_dict([w.submit(fingerprint("r%d" % i), i) for i in range(3)][-1])
        w2 = self.Witness(KEY, self.log)
        self.assertEqual(len(w2.entries()), 3)
        nxt = as_dict(w2.submit(fingerprint("r3"), 3))
        self.assertEqual(nxt["prev_head"], last["head"])
        self.assertEqual(nxt["index"], last["index"] + 1)
        self.assertEqual(len(read_jsonl(self.log)), 4)


# ------------------------------------------------------------------ the ledger

class TestLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_write_fills_seq_prev_fp_fp_and_receipt(self):
        ledger, recs, receipt, journal, wlog = write_run(self.dir)
        self.assertEqual(len(recs), 5)
        self.assertEqual([r.seq for r in recs], list(range(recs[0].seq, recs[0].seq + 5)))
        self.assertIn(recs[0].seq, (0, 1))
        self.assertEqual(recs[0].prev_fp, "")
        for a, b in zip(recs, recs[1:]):
            self.assertEqual(b.prev_fp, a.fp, "each record links to the one before")
        for r in recs:
            body = {k: v for k, v in asdict(r).items() if k not in ("fp", "receipt")}
            self.assertEqual(r.fp, fingerprint(body), "fp is the fingerprint of the record without fp and receipt")
            self.assertTrue(r.receipt, "the in-memory record holds its witness receipt")
        self.assertEqual([as_dict(r.receipt) for r in recs], wlog, "the receipts equal the witness log")
        self.assertEqual([e["record_fp"] for e in wlog], [r.fp for r in recs])

    def test_the_journal_line_is_written_once_with_a_null_receipt(self):
        ledger, recs, receipt, journal, wlog = write_run(self.dir)
        self.assertEqual(len(journal), 5)
        for line, r in zip(journal, recs):
            want = asdict(r)
            want["receipt"] = None
            self.assertEqual(line, want)

    def test_equal_inputs_give_equal_bytes(self):
        with tempfile.TemporaryDirectory() as other:
            write_run(self.dir)
            write_run(Path(other))
            for rel in ("journal/%s.jsonl" % RUN, "witness/log.jsonl"):
                self.assertEqual((self.dir / rel).read_bytes(), (Path(other) / rel).read_bytes(), rel)

    def test_two_runs_written_in_turn_into_one_folder_both_pass(self):
        check_receipt = need("custody.receipt", "check_receipt")
        _, recs1, rc1, j1, _ = write_run(self.dir, run_id="v0001.B.r0")
        _, recs2, rc2, j2, wlog = write_run(self.dir, run_id="v0002.B.r0")
        self.assertEqual(len(wlog), 10, "one witness log for the whole folder")
        self.assertEqual(wlog[5]["prev_head"], wlog[4]["head"], "the chain runs on across runs")
        for rc, j in ((rc1, j1), (rc2, j2)):
            res = check_receipt(rc, j, wlog, key=KEY)
            self.assertEqual(res["problems"], [])
            self.assertTrue(res["ok"])

    def test_a_failure_raises_ledger_error(self):
        make_ledger = need("custody.journal", "make_ledger")
        blocker = self.dir / "journal"
        blocker.mkdir()
        (blocker / ("%s.jsonl" % RUN)).mkdir()  # the journal file cannot be a folder
        with self.assertRaises(LedgerError):
            ledger = make_ledger(self.dir, RUN, run_choices())
            ledger.write(scenario()[0])

    def test_guard_witness_off_sends_nothing_to_the_witness(self):
        ch = run_choices()
        ch["guards"]["witness"] = False
        ledger, recs, receipt, journal, wlog = write_run(self.dir, choices=ch)
        self.assertEqual(wlog, [])
        self.assertTrue(all(r.receipt is None for r in recs))
        self.assertEqual(len(journal), 5)
        check_receipt = need("custody.receipt", "check_receipt")
        res = check_receipt(receipt, journal, [], key=None)
        self.assertEqual(res["problems"], ["witness off"], "with the witness guard off the check reports one line")


# ------------------------------------------------------------------ the receipt

class TestBuildReceipt(unittest.TestCase):
    def setUp(self):
        self.build_receipt = need("custody.receipt", "build_receipt")
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.named = [{"place": p["id"], "who": p["who"]} for p in W["promise"]["places"] if p["named"]]
        self.says = D["receipt"]["says"]

    def tearDown(self):
        self.tmp.cleanup()

    def lines(self, level, statuses, records):
        out = []
        for rule in range(1, 7):
            out.append({"rule": rule, "says": self.says[str(rule)], "level": level[rule] if isinstance(level, dict) else level,
                        "status": statuses.get(rule, "kept"), "records": records.get(rule, [])})
        return out

    def test_a_hand_made_journal_gives_the_hand_written_receipt(self):
        ledger, recs, receipt, journal, wlog = write_run(self.dir)
        s = [r.seq for r in recs]
        self.assertEqual(receipt["run_id"], RUN)
        self.assertEqual(receipt["condition"], "B")
        self.assertEqual(receipt["proof"], NOT_RUN)
        self.assertEqual(receipt["named_places"], self.named, "named places, in file order")
        self.assertEqual(receipt["lines"], self.lines("checked", {1: "blocked", 6: "flagged"}, {1: [s[2]], 6: [s[3]]}))
        self.assertEqual(receipt["trail"], [
            {"kind": "transcript", "went": ["transcriber", "note_writer"], "deleted": {"transcriber": 3}},
            {"kind": "answer", "went": ["advice_tool", "clinician"], "deleted": {}},
        ])
        self.assertEqual(receipt["journal_head"], recs[-1].fp, "the close record counts in journal_head")
        self.assertEqual(receipt["witness_head"], as_dict(recs[-1].receipt)["head"])
        for key in ("run_id", "condition", "records", "journal_head", "witness_head", "proof", "named_places", "lines", "trail"):
            self.assertIn(key, receipt)

    def test_a_close_record_is_left_out_of_the_trail_and_of_every_records_list(self):
        ledger, recs, receipt, journal, wlog = write_run(self.dir, records=scenario(close_broken=(2,)))
        close_seq = recs[-1].seq
        for line in receipt["lines"]:
            self.assertNotIn(close_seq, line["records"], "rule %s lists the close record" % line["rule"])
        self.assertEqual([t["kind"] for t in receipt["trail"]], ["transcript", "answer"])
        self.assertEqual(receipt["journal_head"], recs[-1].fp)

    def test_a_proof_covers_rules_only_when_it_has_passed(self):
        passed = {"status": "passed", "proven_rules": [1, 2, 3], "counterexample": None, "states": 12}
        _, recs, receipt, _, _ = write_run(self.dir, run_id="v0001.C.r0", cond="C", proof=passed)
        self.assertEqual(receipt["proof"], passed)
        self.assertEqual({l["rule"]: l["level"] for l in receipt["lines"]},
                         {1: "proven", 2: "proven", 3: "proven", 4: "checked", 5: "checked", 6: "checked"})
        for status in ("counterexample", "not_run"):
            bad = {"status": status, "proven_rules": [1, 2], "counterexample": None, "states": None}
            with tempfile.TemporaryDirectory() as d2:
                _, _, receipt, _, _ = write_run(Path(d2), run_id="v0001.C.r0", cond="C", proof=bad)
            self.assertEqual({l["level"] for l in receipt["lines"]}, {"checked"}, "a proof that %s covers no rule" % status)

    def test_a_proof_missing_keys_is_never_indexed(self):
        _, _, receipt, _, _ = write_run(self.dir, run_id="v0001.C.r0", cond="C", proof={"status": "not_run"})
        self.assertEqual({l["level"] for l in receipt["lines"]}, {"checked"})

    def test_a_rule_outside_rules_checked_is_not_checked(self):
        ch = run_choices()
        ch["guards"]["rules_checked"] = [1, 2, 3]
        _, recs, receipt, _, _ = write_run(self.dir, choices=ch)
        by = {l["rule"]: l["status"] for l in receipt["lines"]}
        self.assertEqual((by[4], by[5], by[6]), ("not checked",) * 3)
        self.assertEqual(by[1], "blocked")

    def test_under_a_and_a_plus_every_line_is_promised_only_and_not_checked(self):
        for cond in ("A", "A+"):
            r = self.build_receipt("v0001.%s.r0" % cond, cond, [], NOT_RUN, copy.deepcopy(W), run_choices())
            self.assertEqual(r["condition"], cond)
            self.assertEqual(r["named_places"], self.named, "the promise is shown under every condition")
            self.assertEqual(r["lines"], self.lines("promised only", {i: "not checked" for i in range(1, 7)}, {}))
            self.assertEqual(r["trail"], [])
            self.assertEqual(r["proof"], NOT_RUN)


# ------------------------------------------------------------------ the check

class TestCheckReceipt(unittest.TestCase):
    def setUp(self):
        self.check = need("custody.receipt", "check_receipt")
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ledger, self.recs, self.receipt, self.journal, self.wlog = write_run(self.dir)

    def tearDown(self):
        self.tmp.cleanup()

    def run_check(self, receipt=None, journal=None, wlog=None, key=KEY):
        return self.check(copy.deepcopy(receipt if receipt is not None else self.receipt),
                          copy.deepcopy(journal if journal is not None else self.journal),
                          copy.deepcopy(wlog if wlog is not None else self.wlog), key=key)

    def assertFails(self, res, why):
        self.assertFalse(res["ok"], why + ": the check must fail")
        self.assertTrue(res["problems"], why + ": the check must say why")

    def test_an_untouched_journal_passes_with_and_without_the_key(self):
        for key in (None, KEY):
            res = self.run_check(key=key)
            self.assertEqual(res["problems"], [])
            self.assertTrue(res["ok"])

    def test_a_changed_record_fails(self):
        for i, change in ((1, lambda r: r["handover"].__setitem__("t", 99)),
                          (2, lambda r: r.__setitem__("decision", "deliver")),
                          (0, lambda r: r["verdicts"][0].__setitem__("verdict", "broken"))):
            j = copy.deepcopy(self.journal)
            change(j[i])
            self.assertFails(self.run_check(journal=j), "a changed record at %d" % i)

    def test_a_removed_record_fails(self):
        for i in (0, 1, 3, 4):
            j = copy.deepcopy(self.journal)
            del j[i]
            self.assertFails(self.run_check(journal=j), "record %d removed" % i)

    def test_a_reordered_record_fails(self):
        j = copy.deepcopy(self.journal)
        j[1], j[2] = j[2], j[1]
        self.assertFails(self.run_check(journal=j), "two records swapped")

    def test_an_added_record_fails(self):
        j = copy.deepcopy(self.journal)
        j.append(copy.deepcopy(j[-1]))
        self.assertFails(self.run_check(journal=j), "a record repeated at the end")

    def test_a_receipt_line_that_does_not_follow_from_the_records_fails(self):
        rc = copy.deepcopy(self.receipt)
        rc["lines"][0]["status"] = "kept"
        self.assertFails(self.run_check(receipt=rc), "a blocked line shown as kept")

    def test_a_wrong_head_in_the_receipt_fails(self):
        for key in ("journal_head", "witness_head"):
            rc = copy.deepcopy(self.receipt)
            rc[key] = ZERO
            self.assertFails(self.run_check(receipt=rc), "wrong %s" % key)

    def test_a_tampered_witness_log_fails(self):
        w = copy.deepcopy(self.wlog)
        w[1]["record_fp"] = ZERO
        self.assertFails(self.run_check(wlog=w), "a changed fingerprint in the witness log")
        w = copy.deepcopy(self.wlog)
        del w[2]
        self.assertFails(self.run_check(wlog=w), "an entry missing from the witness log")
        w = copy.deepcopy(self.wlog)
        w[2]["head"] = ZERO
        self.assertFails(self.run_check(wlog=w), "a broken head chain")

    def test_a_wrong_mac_fails_when_the_key_is_given(self):
        w = copy.deepcopy(self.wlog)
        w[0]["mac"] = ZERO
        self.assertFails(self.run_check(wlog=w, key=KEY), "a wrong mac")
        self.assertFails(self.run_check(key=b"\x01" * 32), "a mac made with another key")

    def test_a_close_record_raises_no_signal_in_the_lines(self):
        ledger, recs, rc, j, w = write_run(Path(tempfile.mkdtemp(dir=self.tmp.name)), run_id="v0009.B.r0",
                                           records=scenario("v0009.B.r0", close_broken=(2,)))
        res = self.check(rc, j, w, key=KEY)
        self.assertEqual(res["problems"], [])


# ------------------------------------------------------------------ the tool

class TestCheckReceiptTool(unittest.TestCase):
    TOOL = ROOT / "tools" / "check_receipt.py"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ledger, self.recs, self.receipt, self.journal, self.wlog = write_run(self.dir)
        self.receipt_path = self.dir / "receipt.json"
        self.receipt_path.write_text(json.dumps(self.receipt), encoding="utf-8")
        self.journal_path = self.dir / "journal" / ("%s.jsonl" % RUN)
        self.wlog_path = self.dir / "witness" / "log.jsonl"
        self.key_path = self.dir / "key.hex"
        self.key_path.write_text(D["witness"]["test_key_hex"], encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, receipt=None, journal=None, wlog=None, key=None):
        self.assertTrue(self.TOOL.exists(), "tools/check_receipt.py is missing")
        cmd = [sys.executable, str(self.TOOL), str(receipt or self.receipt_path), "--journal", str(journal or self.journal_path),
               "--witness-log", str(wlog or self.wlog_path)]
        if key:
            cmd += ["--key-file", str(key)]
        return subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=60)

    def test_untouched_exits_0_and_prints_the_object(self):
        for key in (None, self.key_path):
            p = self.cli(key=key)
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            out = json.loads(p.stdout)
            self.assertTrue(out["ok"])
            self.assertEqual(out["problems"], [])

    def test_a_changed_journal_exits_1(self):
        lines = self.journal_path.read_text(encoding="utf-8").splitlines()
        row = json.loads(lines[1])
        row["handover"]["t"] = 99
        lines[1] = canon(row)
        bad = self.dir / "bad.jsonl"
        bad.write_text("\n".join(lines) + "\n", encoding="utf-8")
        p = self.cli(journal=bad)
        self.assertEqual(p.returncode, 1, p.stdout + p.stderr)
        out = json.loads(p.stdout)
        self.assertFalse(out["ok"])
        self.assertTrue(out["problems"])

    def test_a_removed_and_a_reordered_line_exit_1(self):
        lines = self.journal_path.read_text(encoding="utf-8").splitlines()
        removed = self.dir / "removed.jsonl"
        removed.write_text("\n".join(lines[:1] + lines[2:]) + "\n", encoding="utf-8")
        self.assertEqual(self.cli(journal=removed).returncode, 1)
        swapped = self.dir / "swapped.jsonl"
        swapped.write_text("\n".join([lines[0], lines[2], lines[1]] + lines[3:]) + "\n", encoding="utf-8")
        self.assertEqual(self.cli(journal=swapped).returncode, 1)

    def test_a_wrong_key_file_exits_1(self):
        other = self.dir / "other.hex"
        other.write_text("01" * 32, encoding="utf-8")
        self.assertEqual(self.cli(key=other).returncode, 1)

    def test_bad_input_exits_2(self):
        p = self.cli(receipt=self.dir / "no_such_receipt.json")
        self.assertEqual(p.returncode, 2, p.stdout + p.stderr)
        broken = self.dir / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        self.assertEqual(self.cli(receipt=broken).returncode, 2)
        self.assertEqual(self.cli(journal=self.dir / "no_such.jsonl").returncode, 2)


if __name__ == "__main__":
    unittest.main()
