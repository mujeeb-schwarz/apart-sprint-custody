"""Tests for custody/prove.py (our own cross-check) and the two model writers.

No formal tool has run: none of these tests proves anything in the formal sense.
"""
import ast
import copy
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custody import prove as P  # noqa: E402


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


WIRING = P.load_wiring()
CHOICES = P.load_choices()
D_WIRING_FAULTS = [f for f in CHOICES["faults"]["development"] if f["kind"] == "wiring"]
with open(str(ROOT / "faults" / "practice" / "practice_faults.json"), encoding="utf-8") as _f:
    PRACTICE_WIRING_FAULTS = [f for f in json.load(_f)["faults"] if f["kind"] == "wiring"]


class CleanWiring(unittest.TestCase):
    def test_clean_wiring_has_no_counterexample(self):
        rep = P.cross_check(WIRING, CHOICES)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["violated"], [])
        self.assertIsNone(rep["counterexample"])

    def test_number_of_situations_is_reported(self):
        rep = P.cross_check(WIRING, CHOICES)
        self.assertIsInstance(rep["states"], int)
        self.assertGreater(rep["states"], 100)
        self.assertEqual(rep["states"], 183)  # version 3 (13 Nov); 210 in version 2, 236 before the recording went
        self.assertEqual(rep["scenarios"], 5)
        # no event, plus one run for each of the four rare events
        self.assertEqual(rep["scenarios"], 5)
        self.assertEqual(rep["bounds"]["events"], ["crash@d3", "overlap@d4", "resume@w2", "timeout@w3"])

    def test_second_run_gives_the_same_result(self):
        a = json.dumps(P.cross_check(WIRING, CHOICES), sort_keys=True)
        b = json.dumps(P.cross_check(copy.deepcopy(WIRING), copy.deepcopy(CHOICES)), sort_keys=True)
        self.assertEqual(a, b)

    def test_proven_level_stays_unavailable(self):
        out = P.prove(WIRING, CHOICES)
        self.assertEqual(out["status"], "not_run")
        self.assertEqual(out["proven_rules"], [])
        self.assertIsNone(out["counterexample"])
        self.assertIsNone(out["states"])
        self.assertEqual(set(out), {"status", "proven_rules", "counterexample", "states"})

    def test_prove_loads_the_choices_when_none_are_given(self):
        self.assertEqual(P.prove(WIRING), P.prove(WIRING, CHOICES))

    def test_the_trace_of_a_clean_visit_matches_the_frame(self):
        prog = P.build_program(WIRING, CHOICES)
        # 2 intakes (one for each lane) + 6 steps + 5 moves + 7 duties + 1 close
        # (version 3: no w4, no a1, no d7, no question or ai_answer step; each lane takes in its own inputs)
        self.assertEqual(len(prog["points"]), 21)
        self.assertEqual(prog["close_advance"], 11)


class WiringFaults(unittest.TestCase):
    def _check(self, fault):
        wiring = P.apply_patch(WIRING, fault["patch"])
        rep = P.cross_check(wiring, CHOICES)
        self.assertFalse(rep["ok"], fault["fault_id"])
        ce = rep["counterexample"]
        self.assertEqual(ce["rule"], fault["rule"], fault["fault_id"])
        self.assertGreater(len(ce["trace"]), 3, fault["fault_id"])
        self.assertTrue(ce["trace"][-1].startswith("BREAK "), fault["fault_id"])
        self.assertGreater(rep["states"], 0)
        out = P.prove(wiring, CHOICES)
        self.assertEqual(out["status"], "counterexample")
        self.assertEqual(out["proven_rules"], [])
        self.assertEqual(out["counterexample"]["rule"], fault["rule"])
        self.assertEqual(out["states"], rep["states"])

    def test_d_defines_two_wiring_faults(self):
        self.assertEqual([f["fault_id"] for f in D_WIRING_FAULTS], ["F2", "F3"])

    def test_each_wiring_fault_of_d_fails(self):
        for f in D_WIRING_FAULTS:
            with self.subTest(f["fault_id"]):
                self._check(f)

    def test_each_practice_wiring_fault_fails(self):
        self.assertEqual([f["fault_id"] for f in PRACTICE_WIRING_FAULTS],
                         ["PF06", "PF07", "PF10", "PF11", "PF12", "PF14", "PF16", "PF17", "PF18"])
        for f in PRACTICE_WIRING_FAULTS:
            with self.subTest(f["fault_id"]):
                self._check(f)

    def test_a_failing_sequence_is_step_by_step_and_repeatable(self):
        f = D_WIRING_FAULTS[0]
        wiring = P.apply_patch(WIRING, f["patch"])
        one = P.cross_check(wiring, CHOICES)["counterexample"]["trace"]
        two = P.cross_check(wiring, CHOICES)["counterexample"]["trace"]
        self.assertEqual(one, two)
        self.assertTrue(any("rare event timeout@w3" in line for line in one))
        self.assertTrue(any("record" in line for line in one))

    def test_fault_that_needs_an_event_passes_when_no_event_is_allowed(self):
        f = D_WIRING_FAULTS[0]  # F2 lives on the timeout detour
        wiring = P.apply_patch(WIRING, f["patch"])
        choices = copy.deepcopy(CHOICES)
        choices["model"]["max_events_per_visit"] = 0
        self.assertTrue(P.cross_check(wiring, choices)["ok"])

    def test_the_fault_is_not_found_when_its_event_is_left_out_of_the_bounds(self):
        f = D_WIRING_FAULTS[0]
        wiring = P.apply_patch(WIRING, f["patch"])
        choices = copy.deepcopy(CHOICES)
        choices["model"]["events"] = ["resume", "crash", "overlap"]
        self.assertTrue(P.cross_check(wiring, choices)["ok"])

    def test_extra_wiring_faults(self):
        cases = {
            "send to an unnamed place": ([{"op": "replace", "path": "/plumbing/moves/w3/to", "value": "analytics"}], 1),
            "send of a kind the place may not hold": ([{"op": "replace", "path": "/plumbing/moves/w3/to", "value": "patient"}], 1),
            "a duty removed": ([{"op": "remove", "path": "/plumbing/duties/d5"}], 2),
            "a duty tied to a move that never exists": ([{"op": "replace", "path": "/plumbing/duties/d5/after", "value": "w9"}], 2),
            "a duty tied to a step that never exists": ([{"op": "replace", "path": "/plumbing/duties/d6/after_step", "value": "nostep"}], 2),
        }
        for name, (patch, rule) in cases.items():
            with self.subTest(name):
                rep = P.cross_check(P.apply_patch(WIRING, patch), CHOICES)
                self.assertFalse(rep["ok"])
                self.assertEqual(rep["counterexample"]["rule"], rule)

    def test_a_patch_to_the_promise_is_refused(self):
        with self.assertRaises(P.ContractError):
            P.apply_patch(WIRING, [{"op": "replace", "path": "/promise/places/0/named", "value": False}])

    def test_an_unknown_move_in_a_detour_raises(self):
        bad = P.apply_patch(WIRING, [{"op": "replace", "path": "/plumbing/detours/r1/do/0", "value": {"send": "nope"}}])
        with self.assertRaises(P.ContractError):
            P.cross_check(bad, CHOICES)

    def test_a_move_that_no_lane_step_runs_is_refused(self):
        import copy as _c
        bad = _c.deepcopy(WIRING)
        bad["plumbing"]["moves"].append({"id": "wx", "step": "nostep", "kind": "transcript", "from": "transcriber",
                                         "to": "elsewhere", "via_gate": False})
        with self.assertRaises(P.ContractError):
            P.cross_check(bad, CHOICES)

    def test_a_detour_on_an_event_outside_the_model_is_listed_as_ignored(self):
        import copy as _c
        bad = _c.deepcopy(WIRING)
        det = _c.deepcopy(bad["plumbing"]["detours"][0])
        det["id"], det["on"] = "rx", "disk_full"
        bad["plumbing"]["detours"].append(det)
        rep = P.cross_check(bad, CHOICES)
        self.assertEqual(rep["ignored_detours"], [{"detour": "rx", "on": "disk_full"}])
        self.assertEqual(P.prove(bad, CHOICES)["ignored_detours"], rep["ignored_detours"])
        self.assertEqual(P.cross_check(WIRING, CHOICES)["ignored_detours"], [])

    def test_a_detour_at_an_unknown_position_is_refused(self):
        import copy as _c
        bad = _c.deepcopy(WIRING)
        det = _c.deepcopy(bad["plumbing"]["detours"][0])
        det["id"], det["at"] = "rx", "w9"
        bad["plumbing"]["detours"].append(det)
        with self.assertRaises(P.ContractError):
            P.cross_check(bad, CHOICES)


class Writers(unittest.TestCase):
    def test_tla_file_matches_the_generator_and_says_it_is_unchecked(self):
        gen = _load("gen_tla", "model/gen_tla.py")
        text = gen.generate(WIRING, CHOICES)
        with open(str(ROOT / "model" / "Custody.tla"), encoding="utf-8") as f:
            self.assertEqual(f.read(), text)
        head = text[:900]
        self.assertIn("NOT YET CHECKED", head)
        self.assertIn("never been parsed or run", head)
        self.assertNotIn(chr(0x2014), text)
        for name in ("P1", "P2", "P3", "P4", "Spec", "Next", "MaxEvents == 1"):
            self.assertIn(name, text)
        for place in WIRING["promise"]["places"]:
            if place["named"]:
                self.assertIn('"%s"' % place["id"], text)
        self.assertEqual(text.count("---- MODULE Custody ----"), 1)

    def test_tla_generator_is_repeatable_and_follows_the_wiring(self):
        gen = _load("gen_tla2", "model/gen_tla.py")
        self.assertEqual(gen.generate(WIRING, CHOICES), gen.generate(WIRING, CHOICES))
        faulted = P.apply_patch(WIRING, D_WIRING_FAULTS[1]["patch"])
        self.assertIn('gated |-> FALSE', gen.generate(faulted, CHOICES))
        self.assertNotIn('gated |-> FALSE', gen.generate(WIRING, CHOICES))

    def test_z3_script_is_valid_python_and_says_it_is_untested(self):
        gen = _load("gen_z3", "model/gen_z3.py")
        text = gen.generate(WIRING, CHOICES)
        ast.parse(text)
        self.assertIn("NOT YET RUN", text[:300])
        self.assertEqual(text, gen.generate(WIRING, CHOICES))
        self.assertIn("MAX_EVENTS", text)

    def test_writers_write_to_the_given_path_only(self):
        gen = _load("gen_z3b", "model/gen_z3.py")
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "z.py"
            self.assertEqual(gen.main(["x", str(out)]), 0)
            ast.parse(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
