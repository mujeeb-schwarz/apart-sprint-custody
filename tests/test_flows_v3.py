"""Version 3 (13 Nov): Experiment 1 ends in the chart; in Experiment 2 the question enters with its answer."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custody import assemble, bench, faults, store, visits  # noqa: E402
from custody.core import ContractError, claim_level, has_ai_mark, sources_named  # noqa: E402

D = json.loads((ROOT / "config" / "design_choices.json").read_text(encoding="utf-8"))
W = json.loads((ROOT / "wiring" / "wiring.json").read_text(encoding="utf-8"))
E1 = visits.read_cases(visits.case_path(1, D), 1)
E2 = visits.read_cases(visits.case_path(2, D), 2)
GRADED = [v for v in E2 if v.expert_certainty is not None]
STORED = [v for v in E2 if v.given_answer is not None]


def run(case, fault=None, cond="A"):
    with tempfile.TemporaryDirectory() as tmp:
        parts = assemble.make_parts(W, bench.run_choices(D))
        res = bench.run_one(case, cond, fault, parts, W, D, tmp)
        st = store.read_store(tmp)
    return res, st


def planted(fault_id, ops, rule, needs=None):
    return {"fault_id": fault_id, "kind": "step", "rule": rule, "says": "x", "ops": ops, "patch": [],
            "events": [], "needs": needs or {}}


class TheWiring(unittest.TestCase):
    def test_experiment_1_ends_in_the_chart(self):
        p = W["plumbing"]
        self.assertNotIn("w4", [m["id"] for m in p["moves"]])
        patient = next(x for x in W["promise"]["places"] if x["id"] == "patient")
        self.assertEqual(patient["may_hold"], {"patient_note": None})
        d6 = next(d for d in p["duties"] if d["id"] == "d6")
        self.assertEqual((d6.get("after"), d6["after_step"]), (None, "record"))
        words = [m["id"] for m in p["moves"] if not m.get("detour_only") and m["step"] in p["lanes"][0]["steps"]]
        self.assertEqual(words, ["w2", "w3"])
        self.assertEqual([d["id"] for d in p["duties"] if d["id"] in ("d3", "d4", "d5", "d6")], ["d3", "d4", "d5", "d6"])

    def test_the_advice_lane(self):
        p = W["plumbing"]
        self.assertEqual(p["lanes"][1]["steps"], ["answer", "plan", "patient_note"])
        step = next(s for s in p["steps"] if s["id"] == "answer")
        self.assertEqual((step["place"], step["reads"], step["makes"], step["ai"]), ("advice_tool", ["answer"], None, False))
        self.assertEqual(step["says"], "Hands the tool's answer to the doctor.")
        ids = [m["id"] for m in p["moves"]]
        self.assertTrue({"a2", "a3", "a4"} <= set(ids) and "a1" not in ids)
        self.assertEqual([d["id"] for d in p["duties"] if d["id"] in ("d7", "d8", "d9", "d10")], ["d8", "d9", "d10"])
        tool = next(x for x in W["promise"]["places"] if x["id"] == "advice_tool")
        self.assertEqual(tool["may_hold"], {"answer": "in_visit"})
        self.assertNotIn("evidence", W["kinds"])
        self.assertEqual([e["kind"] for e in p["intake"]], ["transcript", "question", "answer"])
        self.assertEqual(next(e for e in p["intake"] if e["kind"] == "answer")["place"], "advice_tool")


class TheComposedAnswer(unittest.TestCase):
    def test_all_263_graded_questions_read_at_their_grade_with_every_source_and_the_mark(self):
        self.assertEqual(len(GRADED), 263)
        for v in GRADED:
            text = visits.compose_answer(v, D)
            self.assertEqual(claim_level(text, D), v.expert_certainty, v.visit_id)
            self.assertEqual(sorted(sources_named(text, D)), sorted({e["source_id"].lower() for e in v.evidence}), v.visit_id)
            self.assertTrue(has_ai_mark(text, D), v.visit_id)

    def test_the_form(self):
        v = GRADED[0]
        lines = visits.compose_answer(v, D).split("\n")
        self.assertEqual(len(lines), 4)
        self.assertTrue(lines[0].startswith("Question: "))
        self.assertTrue(lines[1].startswith("Claim: "))
        self.assertTrue(lines[2].startswith("Studies (%d): " % len(v.evidence)))
        self.assertEqual(lines[3], D["markers"]["ai"])
        long_title = copy.deepcopy(v)
        long_title = type(v)(**dict(v.__dict__, evidence=[dict(v.evidence[0], title="T" * 400 + "\nx")]))
        self.assertEqual(visits.compose_answer(long_title, D).split("\n")[2], "Studies (1): " + "T" * 160)

    def test_a_stored_answer_enters_as_it_did_before(self):
        v = STORED[0]
        text = visits.compose_answer(v, D)
        self.assertEqual(text, "%s\n[source: tool:%s]\n[AI-generated]" % (v.given_answer.rstrip("\n"), v.given_by))

    def test_clean_composed_answers_raise_no_flag_under_any_method(self):
        for v in (GRADED[0], GRADED[40], STORED[0]):
            for cond in ("A", "A+", "B"):
                res, st = run(v, cond=cond)
                self.assertFalse(res.crashed)
                self.assertEqual(res.signals, 0, (v.visit_id, cond))
                self.assertTrue(res.produced["patient_note"])

    def test_the_answer_enters_as_an_item_of_the_intake_and_nothing_asks_an_ai_for_it(self):
        res, st = run(GRADED[0])
        answers = [t["item"] for t in st["texts"] if t["item"]["kind"] == "answer"]
        self.assertEqual({a["made_by"] for a in answers}, {"intake"})
        self.assertEqual({c["prompt_id"] for c in st["ai_calls"]} if "ai_calls" in st else set(),
                         {"plan.v1", "patient_note.v1", D["prompts"]["reviewer"]})


class TheHiddenInstruction(unittest.TestCase):
    def case(self, grades):
        return next(v for v in GRADED if v.expert_certainty in grades)

    def test_inject_into_the_answer_makes_the_plan_state_more_certainty(self):
        v = self.case(("low", "moderate"))
        fault = planted("T1", [{"op": "inject", "kind": "answer", "text": D["canned"]["injection_certainty"]["text"]}], 5)
        res, st = run(v, fault)
        self.assertFalse(res.crashed)
        plan = next(t["item"] for t in st["texts"] if t["item"]["kind"] == "plan")
        answer = next(t["item"] for t in st["texts"] if t["item"]["kind"] == "answer")
        self.assertTrue(answer["text"].endswith(D["canned"]["injection_certainty"]["text"]))
        self.assertEqual(claim_level(answer["text"], D), v.expert_certainty)
        self.assertEqual(claim_level(plan["text"], D), D["ladder"]["levels"][-1])
        self.assertTrue(any(e["kind"] == "event" and e["detail"].get("fault_op") == "inject" for e in st["truth"]))

    def test_the_kind_evidence_is_no_longer_a_target(self):
        fault = planted("T2", [{"op": "inject", "kind": "evidence", "text": "x"}], 1)
        with self.assertRaises(ContractError):
            faults.check_fault(fault, W, D)
        faults.check_fault(planted("T3", [{"op": "inject", "kind": "answer", "text": "x"}], 5), W, D)

    def test_a_rewrite_at_the_step_answer_changes_the_entering_text(self):
        v = GRADED[0]
        fault = planted("T4", [{"op": "rewrite", "step": "answer", "mode": "drop_source"}], 4)
        faults.check_fault(fault, W, D)
        res, st = run(v, fault)
        answer = next(t["item"] for t in st["texts"] if t["item"]["kind"] == "answer")
        self.assertEqual(sources_named(answer["text"], D), [])
        ev = [e for e in st["truth"] if e["kind"] == "event" and e["detail"].get("fault_op") == "rewrite"]
        self.assertEqual([(e["detail"]["step"], e["fault_id"]) for e in ev], [("answer", "T4")])
        made = [e for e in st["truth"] if e["kind"] == "made" and e["item_id"] == answer["item_id"]]
        self.assertEqual([e["fault_id"] for e in made], ["T4"])
        self.assertEqual(faults.fault_lane(fault, W), "advice")


if __name__ == "__main__":
    unittest.main()
