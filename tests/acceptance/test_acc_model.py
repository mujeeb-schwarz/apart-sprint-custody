"""Acceptance tests for MODEL: the check of the wiring before any visit runs.

Written from docs/FRAME.md (sections 4, 6, 8), config/design_choices.json (D: model,
exports.JOINER, wiring.prove) and wiring/wiring.json (W). Only these public signatures
are used:

  custody.prove.prove(wiring) -> J  with the keys of D: model.result_format
  custody.receipt.build_receipt(run_id, condition, records, proof, wiring, choices) -> J

D gives no signature for the tools in model/ (gen_tla, gen_z3), for a cross-check
function, or for a command-line tool of MODEL. So every behaviour is tested through
prove(wiring), and the cross-check test looks for a public callable of custody.prove
whose name holds "cross" (see test_cross_check_never_marks_a_line_proven for what
happens when there is none). A test fails with a clear message when the part is
missing or wrong; none is skipped.
"""
import copy
import importlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custody import core  # noqa: E402

D = json.loads((ROOT / "config" / "design_choices.json").read_text(encoding="utf-8"))
W = json.loads((ROOT / "wiring" / "wiring.json").read_text(encoding="utf-8"))
RESULT_KEYS = {"status", "proven_rules", "counterexample", "states"}
STATUSES = {"not_run", "passed", "counterexample"}


def need_prove():
    try:
        mod = importlib.import_module("custody.prove")
    except Exception as e:  # missing part: fail with a clear message
        raise AssertionError("MODEL is missing: cannot import custody.prove (%s: %s)" % (type(e).__name__, e))
    if not callable(getattr(mod, "prove", None)):
        raise AssertionError("MODEL is wrong: custody.prove has no callable prove(wiring)")
    return mod


def run_prove(wiring):
    mod = need_prove()
    try:
        return mod.prove(copy.deepcopy(wiring))
    except Exception as e:
        raise AssertionError("prove(wiring) raised %s: %s" % (type(e).__name__, e))


def patched(fn):
    w = copy.deepcopy(W)
    fn(w["plumbing"])
    return w


def detour(plumbing, did):
    return next(d for d in plumbing["detours"] if d["id"] == did)


def move(plumbing, mid):
    return next(m for m in plumbing["moves"] if m["id"] == mid)


def expect_counterexample(test, wiring, rule, what):
    r = run_prove(wiring)
    test.assertEqual(r.get("status"), "counterexample",
                     "%s: prove must report a counterexample, got %r" % (what, r))
    ce = r.get("counterexample")
    test.assertIsInstance(ce, dict, "%s: counterexample must be an object {rule, property, trace}" % what)
    test.assertEqual(set(ce), {"rule", "property", "trace"}, "%s: counterexample keys" % what)
    test.assertEqual(ce["rule"], rule, "%s: the broken rule" % what)
    test.assertTrue(ce["property"], "%s: the property must be named" % what)
    test.assertIsInstance(ce["trace"], list, "%s: trace must be a list of events" % what)
    test.assertGreaterEqual(len(ce["trace"]), 1, "%s: trace must hold at least one event" % what)
    test.assertNotIn(rule, r.get("proven_rules", []), "%s: the broken rule must not be listed as proven" % what)
    return r


class CleanWiring(unittest.TestCase):
    def test_module_and_function_exist(self):
        need_prove()

    def test_result_has_exactly_the_documented_keys(self):
        r = run_prove(W)
        self.assertIsInstance(r, dict)
        self.assertEqual(set(r), RESULT_KEYS, "keys of D: model.result_format")
        self.assertIn(r["status"], STATUSES)

    def test_clean_wiring_passes(self):
        r = run_prove(W)
        self.assertEqual(r["status"], "passed", "the clean wiring must pass the check, got %r" % (r,))
        self.assertIsNone(r["counterexample"], "a pass carries no counterexample")

    def test_clean_wiring_proves_rules_1_to_3(self):
        r = run_prove(W)
        self.assertEqual(sorted(r["proven_rules"]), [1, 2, 3],
                         "W: prove lists properties for rules 1, 2 and 3; got %r" % (r["proven_rules"],))
        for x in r["proven_rules"]:
            self.assertIs(type(x), int, "a rule number is an int (FRAME section 11)")

    def test_prove_does_not_change_the_wiring_it_is_given(self):
        mod = need_prove()
        w = copy.deepcopy(W)
        mod.prove(w)
        self.assertEqual(core.canon(w), core.canon(W), "prove must leave its argument as it was")

    def test_notes_in_the_wiring_do_not_change_the_result(self):
        a = run_prove(W)
        w = copy.deepcopy(W)
        w["plumbing"]["_moves_note"] = "changed words"
        w["promise"]["_basis"] = "changed words"
        self.assertEqual(core.canon(a), core.canon(run_prove(w)), "only the structure of the wiring may matter")


class StatesAndRepeat(unittest.TestCase):
    def test_states_is_a_positive_whole_number_on_a_pass(self):
        r = run_prove(W)
        self.assertIs(type(r["states"]), int, "states is the number of situations tried; got %r" % (r["states"],))
        self.assertGreater(r["states"], 0)

    def test_two_calls_give_the_same_result(self):
        self.assertEqual(core.canon(run_prove(W)), core.canon(run_prove(W)), "the number of situations repeats")

    def test_repeat_in_a_fresh_process_with_another_hash_seed(self):
        need_prove()
        code = ("import json,sys\n"
                "sys.path.insert(0, %r)\n"
                "from custody.prove import prove\n"
                "from custody.core import canon\n"
                "w = json.load(open(%r, encoding='utf-8'))\n"
                "print(canon(prove(w)))\n") % (str(ROOT), str(ROOT / "wiring" / "wiring.json"))
        outs = []
        for seed in ("1", "98765"):
            env = dict(os.environ, PYTHONHASHSEED=seed)
            p = subprocess.run([sys.executable, "-c", code], env=env, cwd=str(ROOT), capture_output=True,
                               text=True, timeout=300)
            self.assertEqual(p.returncode, 0, "prove crashed in a fresh process: %s" % p.stderr[-500:])
            outs.append(p.stdout.strip())
        self.assertEqual(outs[0], outs[1], "result and states must not depend on PYTHONHASHSEED")

    def test_a_failing_wiring_repeats_too(self):
        w = patched(lambda p: detour(p, "r1")["do"].pop())
        self.assertEqual(core.canon(run_prove(w)), core.canon(run_prove(w)), "the same trace every time")


class RarePathFaults(unittest.TestCase):
    """A fault that lives only on a rare path: a check at each ordinary handover cannot see it."""

    def test_queue_never_cleared_after_a_timeout_fails_rule_2(self):
        w = patched(lambda p: detour(p, "r1")["do"].pop())  # drops the delete of the queued copy
        r = expect_counterexample(self, w, 2, "r1 keeps the queued recording")
        self.assertIn("timeout", json.dumps(r["counterexample"]["trace"]),
                      "the fault fires only on a timeout, so the trace must show that event")

    def test_cache_never_cleared_after_a_resume_fails_rule_2(self):
        w = patched(lambda p: detour(p, "r2")["do"].pop())
        r = expect_counterexample(self, w, 2, "r2 keeps the cached transcript")
        self.assertIn("resume", json.dumps(r["counterexample"]["trace"]))

    def test_crash_detour_that_deletes_nothing_fails_rule_2(self):
        w = patched(lambda p: detour(p, "r3").__setitem__("do", []))
        r = expect_counterexample(self, w, 2, "r3 does not delete after a crash")
        self.assertIn("crash", json.dumps(r["counterexample"]["trace"]))

    def test_overlap_detour_that_deletes_nothing_fails_rule_2(self):
        w = patched(lambda p: detour(p, "r4").__setitem__("do", []))
        r = expect_counterexample(self, w, 2, "r4 does not delete after an overlap")
        self.assertIn("overlap", json.dumps(r["counterexample"]["trace"]))

    def test_detour_that_sends_to_a_place_not_named_fails_rule_1(self):
        w = patched(lambda p: move(p, "w2c").__setitem__("to", "analytics"))
        r = expect_counterexample(self, w, 1, "the cache copy goes to an unnamed place")
        self.assertIn("resume", json.dumps(r["counterexample"]["trace"]))

    def test_detour_that_sends_a_kind_the_place_may_not_hold_fails_rule_1(self):
        # the retry queue may hold a note draft only; make the detour put the transcript there
        w = patched(lambda p: move(p, "w3q").__setitem__("kind", "transcript"))
        expect_counterexample(self, w, 1, "a kind sent to a place that may not hold it")

    def test_detour_move_that_skips_the_gate_fails_rule_3(self):
        w = patched(lambda p: move(p, "w2c").__setitem__("via_gate", False))
        r = expect_counterexample(self, w, 3, "a rare-path move that skips the gate")
        self.assertIn("resume", json.dumps(r["counterexample"]["trace"]))

    def test_main_move_that_skips_the_gate_fails_rule_3(self):
        w = patched(lambda p: move(p, "w2").__setitem__("via_gate", False))
        expect_counterexample(self, w, 3, "an ordinary move that skips the gate")

    def test_duty_removed_fails_rule_2_even_with_no_rare_event(self):
        w = patched(lambda p: p["duties"].remove(next(d for d in p["duties"] if d["id"] == "d5")))
        expect_counterexample(self, w, 2, "the note draft copy is never deleted at the note writer")

    def test_the_counterexample_is_a_list_of_readable_events(self):
        w = patched(lambda p: detour(p, "r1")["do"].pop())
        ce = run_prove(w)["counterexample"]
        json.dumps(ce)  # must be plain JSON
        self.assertGreater(len(json.dumps(ce["trace"])), 2, "the trace is the sequence of events, not an empty list")

    def test_a_broken_wiring_has_not_passed_so_it_proves_no_rule_it_broke(self):
        w = patched(lambda p: detour(p, "r1")["do"].pop())
        r = run_prove(w)
        self.assertNotEqual(r["status"], "passed")
        self.assertNotIn(2, r["proven_rules"])

    def test_a_clean_wiring_with_the_rare_events_switched_off_still_passes(self):
        w = copy.deepcopy(W)
        w["plumbing"]["detours"] = []
        w2 = copy.deepcopy(w)
        r = run_prove(w2)
        self.assertEqual(r["status"], "passed", "no detours means no rare path: got %r" % (r,))


class CrossCheckNeverProves(unittest.TestCase):
    def _receipt_levels(self, proof):
        from custody import receipt
        rc = receipt.build_receipt("v0001.C.r0", "C", [], proof, W, D)
        return [ln["level"] for ln in rc["lines"]]

    def test_cross_check_never_marks_a_receipt_line_as_proven(self):
        """FRAME: nothing lets tonight's cross-check mark a receipt line as proven.

        D names no cross-check function. The test looks in custody.prove for public
        callables whose name holds 'cross'; each one is called with the clean wiring and
        its result is given to build_receipt as the proof. No line may read 'proven'.
        If there is no such callable, the test falls back to the weaker check that
        prove() returns a legal status, and its message says the strong check could not run.
        """
        mod = need_prove()
        names = [n for n in dir(mod) if "cross" in n.lower() and not n.startswith("_") and callable(getattr(mod, n))]
        for n in names:
            res = getattr(mod, n)(copy.deepcopy(W))
            self.assertIsInstance(res, dict, "%s must return a result object" % n)
            self.assertNotIn("proven", self._receipt_levels(res),
                             "%s: a receipt line is 'proven' on a cross-check result: %r" % (n, res))
        if not names:
            self.assertIn(run_prove(W)["status"], STATUSES,
                          "no public cross-check callable found in custody.prove (D names none), so only the "
                          "legal-status check ran")

    def test_a_not_run_proof_gives_no_proven_line(self):
        proof = {"status": "not_run", "proven_rules": [], "counterexample": None, "states": None}
        self.assertNotIn("proven", self._receipt_levels(proof))

    def test_a_counterexample_proof_gives_no_proven_line(self):
        w = patched(lambda p: detour(p, "r1")["do"].pop())
        r = run_prove(w)
        self.assertNotIn("proven", self._receipt_levels(r), "a failed proof covers no rule")


if __name__ == "__main__":
    unittest.main()
