"""Version 2, part 2: two lists of cases, one flow per case, the intake log line and the trial selection."""
import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import assemble, bench, datasets, faults, score, store, visits  # noqa: E402
from custody.core import ContractError, DataError  # noqa: E402
from raw_data_guard import needs_raw_data, needs_retired_cases  # noqa: E402

D = datasets.default_choices()
W = assemble.load_wiring()
RAW = ROOT / "data" / "raw"
E1 = visits.read_cases(ROOT / "data" / "cases" / "exp1.jsonl", 1)
E2 = visits.read_cases(ROOT / "data" / "cases" / "exp2.jsonl", 2)


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / "tools" / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TheTwoLists(unittest.TestCase):
    def test_experiment_1_counts_and_ids(self):
        self.assertEqual(len(E1), 207)
        self.assertEqual(Counter(v.split for v in E1), {"tune": 50, "test": 157})
        self.assertEqual([v.visit_id for v in E1][:2] + [E1[-1].visit_id], ["c0001", "c0002", "c0207"])
        self.assertEqual(len({v.conversation_id for v in E1}), 207)

    def test_experiment_2_counts_and_ids(self):
        self.assertEqual(len(E2), 499)
        kinds = Counter((v.split, v.meta["case_kind"]) for v in E2)
        self.assertEqual(kinds, {("tune", "graded"): 50, ("tune", "stored"): 36, ("test", "graded"): 213,
                                 ("test", "stored"): 200})
        self.assertEqual([E2[0].visit_id, E2[-1].visit_id], ["q0001", "q0499"])
        self.assertEqual(len({v.question_id for v in E2}), 499)

    def test_a_case_holds_the_fields_of_its_experiment_only(self):
        for v in E1:
            self.assertEqual((v.experiment, v.question_id, v.question, v.evidence, v.given_answer, v.expert_certainty),
                             (1, "", "", [], None, None))
            self.assertTrue(v.conversation and v.conversation_id)
        for v in E2:
            self.assertEqual((v.experiment, v.conversation_id, v.conversation), (2, "", ""))
            self.assertTrue(v.question and v.question_id)
            if v.meta["case_kind"] == "graded":
                self.assertTrue(v.evidence and v.expert_certainty is not None and v.given_answer is None)
            else:
                self.assertTrue(v.given_answer and not v.evidence and v.expert_certainty is None)

    def test_no_case_is_in_both_splits_and_the_two_lists_share_no_id(self):
        for lst, key in ((E1, "conversation_id"), (E2, "question_id")):
            tune = {getattr(v, key) for v in lst if v.split == "tune"}
            test = {getattr(v, key) for v in lst if v.split == "test"}
            self.assertFalse(tune & test)
        self.assertFalse({v.visit_id for v in E1} & {v.visit_id for v in E2})

    @needs_raw_data
    @needs_retired_cases
    def test_nothing_moves_between_practice_and_test(self):
        retired = ROOT / "data" / "retired" / "visits.jsonl"
        old = visits.read_visits(retired)
        self.assertEqual(len(old), 400)
        tune_conv = {v.conversation_id for v in old if v.split == "tune"}
        tune_q = {v.question_id for v in old if v.split == "tune"}
        self.assertEqual({v.conversation_id for v in E1 if v.split == "tune"}, tune_conv)
        self.assertEqual({v.question_id for v in E2 if v.split == "tune"}, tune_q)
        # a case that was in a test visit before is not in practice now
        old_test_q = {v.question_id for v in old if v.split == "test"}
        self.assertFalse(old_test_q & {v.question_id for v in E2 if v.split == "tune"})

    @needs_raw_data
    def test_the_draw_is_the_same_on_every_run_and_is_the_saved_file(self):
        a = visits.build_cases(D, RAW)
        b = visits.build_cases(D, RAW)
        self.assertEqual(a, b)
        self.assertEqual(a[1], E1)
        self.assertEqual(a[2], E2)
        # the draw uses the new seed: another seed gives other test questions, the same practice ones
        other = json.loads(json.dumps(D))
        other["seeds"]["cases"] = D["seeds"]["cases"] + 1
        c = visits.build_cases(other, RAW)[2]
        self.assertNotEqual({v.question_id for v in c}, {v.question_id for v in E2})
        self.assertEqual({v.question_id for v in c if v.split == "tune"}, {v.question_id for v in E2 if v.split == "tune"})

    @needs_raw_data
    def test_the_draw_comes_from_the_584_outside_the_practice_set(self):
        pr = visits.practice_sets(D, RAW)
        self.assertEqual((len(pr["conversations"]), len(pr["graded"]), len(pr["stored"])), (50, 50, 36))
        self.assertEqual(sum(1 for v in E2 if v.meta["case_kind"] == "stored") - 36, 200)
        self.assertEqual(620 - 36, 584)

    def test_a_file_of_the_wrong_experiment_is_refused(self):
        with self.assertRaises(DataError):
            visits.read_cases(ROOT / "data" / "cases" / "exp1.jsonl", 2)

    def test_the_old_matching_is_gone(self):
        self.assertFalse((ROOT / "config" / "pairing.json").exists())
        self.assertFalse((ROOT / "data" / "visits_trial").exists())
        self.assertFalse(hasattr(visits, "build_visits_matching"))
        self.assertNotIn("matching_mode", D["visits"])
        self.assertNotIn("matching", D["seeds"])


def mini_run(cases, fault=None, cond="A"):
    with tempfile.TemporaryDirectory() as tmp:
        rch = bench.run_choices(D)
        parts = assemble.make_parts(W, rch)
        res = []
        for v in cases:
            res.append(bench.run_one(v, cond, fault, parts, W, D, tmp))
        st = store.read_store(tmp)
    return res, st


class OneFlowPerCase(unittest.TestCase):
    def test_experiment_1_runs_only_the_words_lane(self):
        v = E1[0]
        for cond in ("A", "B"):
            (r,), st = mini_run([v], cond=cond)
            self.assertEqual(r.experiment, 1)
            self.assertFalse(r.crashed)
            self.assertEqual(r.produced, {"note": True, "patient_note": False})
            moved = {e["detail"].get("kind") for e in st["truth"] if e["kind"] == "moved"}
            self.assertEqual(moved, {"transcript", "note_draft"})  # version 3: the note ends in the chart
            steps = {x["step"] for x in st["own_log"]}
            self.assertEqual(steps, {"intake", "transcriber", "note_writer", "janitor"})
            self.assertEqual({x["kind"] for x in st["own_log"] if x["action"] == "intake"}, {"transcript"})

    def test_experiment_2_runs_only_the_advice_lane(self):
        for v in (E2[0], [q for q in E2 if q.meta["case_kind"] == "stored"][0]):
            (r,), st = mini_run([v])
            self.assertEqual(r.experiment, 2)
            self.assertFalse(r.crashed)
            self.assertEqual(r.produced, {"note": False, "patient_note": True})
            moved = {e["detail"].get("kind") for e in st["truth"] if e["kind"] == "moved"}
            self.assertEqual(moved, {"answer", "plan", "patient_note"})  # version 3: the question never moves
            self.assertEqual({x["step"] for x in st["own_log"]},
                             {"intake", "answer", "plan", "patient_note", "janitor"})
            self.assertEqual({x["kind"] for x in st["own_log"] if x["action"] == "intake"}, {"question", "answer"})

    def test_an_event_of_the_other_lane_does_not_fire(self):
        fault = {"fault_id": "T1", "kind": "wiring", "rule": 2, "says": "x", "ops": [], "patch": [], "needs": {},
                 "events": [{"on": "timeout", "at": "w3"}]}  # a words-lane detour
        (r,), st = mini_run([E2[0]], fault=fault)
        self.assertFalse(r.crashed)
        self.assertFalse([e for e in st["truth"] if e["kind"] == "event" and (e.get("detail") or {}).get("detour")])

    def test_the_intake_line_records_time_kind_place_and_item(self):
        (r,), st = mini_run([E1[0]])
        lines = [x for x in st["own_log"] if x["action"] == "intake"]
        self.assertEqual(len(lines), 1)
        self.assertEqual(set(lines[0]), {"run_id", "t", "step", "action", "kind", "place", "item"})
        self.assertEqual((lines[0]["t"], lines[0]["kind"], lines[0]["place"]), (0, "transcript", "transcriber"))
        items = {t["item"]["item_id"] for t in st["texts"]}
        self.assertIn(lines[0]["item"], items)

    def test_a_transcript_never_deleted_at_the_scribe_service_is_flagged_by_the_reviews_program_part(self):
        fault = {"fault_id": "T2", "kind": "step", "rule": 2, "says": "x", "patch": [], "events": [], "needs": {},
                 "ops": [{"op": "skip_delete", "duty": "d3"}]}
        for cond in ("A", "A+"):
            (r,), st = mini_run([E1[0]], fault=fault, cond=cond)
            flags = [s for s in st["signals"] if s["by"] == "review" and s["rule"] == 2 and s.get("part") == "program"]
            self.assertTrue(flags, cond)
            # and it is the transcript that arrived by intake: its only log line is the intake line
            self.assertTrue(any(x["action"] == "intake" for x in st["own_log"]))
        (r,), st = mini_run([E1[0]], cond="A")  # a clean case: no such flag
        self.assertFalse([s for s in st["signals"] if s["by"] == "review" and s["rule"] == 2])

    def test_a_legacy_visit_without_an_experiment_still_runs_both_lanes(self):
        both = replace(E2[0], experiment=0, conversation="[doctor] Hello.", conversation_id="aci:X")
        (r,), _ = mini_run([both])
        self.assertEqual(r.produced, {"note": True, "patient_note": True})

    def test_scoring_follows_the_experiment(self):
        self.assertEqual(score.rules_of([{"experiment": 1}]), [1, 2, 3])
        self.assertEqual(score.rules_of([{"experiment": 2}, {"experiment": 2}]), [4, 5, 6])
        self.assertEqual(score.rules_of([{"experiment": 1}, {"experiment": 2}]), [1, 2, 3, 4, 5, 6])

    def test_faults_of_the_other_lane_are_not_planted(self):
        fl = faults.load_faults(D, ROOT)
        pick = lambda cs: [v for v in cs if v.split == "tune"][:8] + [v for v in cs if v.split == "test"][:8]
        plan1, un1 = faults.plan_faults_report(pick(E1), fl, D, W)
        plan2, un2 = faults.plan_faults_report(pick(E2), fl, D, W)
        self.assertEqual((un1, un2), ([], []))
        ids1 = {f["fault_id"] for f in plan1.values() if f}
        ids2 = {f["fault_id"] for f in plan2.values() if f}
        self.assertFalse(ids1 & {"F4", "F5", "F6"})
        self.assertFalse(ids2 & {"F1", "F2", "F3", "F7", "F8", "F9", "F10", "F11"})
        self.assertTrue({"F4", "F5", "F6"} <= ids2)
        self.assertTrue({"F1", "F2", "F3", "F7"} <= ids1)


class TheTrialSelection(unittest.TestCase):
    def trial(self, exp, n):
        cases = E1 if exp == 1 else E2
        fl = faults.load_practice_faults(exp, D)
        return faults.plan_trial(cases, fl, n, D, W)

    def test_clean_and_planted_cases_are_different_practice_cases(self):
        for exp in (1, 2):
            chosen, plan, clean, unplaced = self.trial(exp, 5)
            planted = [k for k, f in plan.items() if f]
            self.assertEqual(len(clean), 5)
            self.assertFalse(set(clean) & set(planted))
            self.assertEqual(len(planted), len(set(planted)))
            self.assertEqual({v.split for v in chosen}, {"tune"})
            self.assertEqual(len(chosen), 5 + len(planted))
            self.assertEqual(unplaced, [])

    def test_counts_per_experiment(self):
        self.assertEqual(len([f for f in self.trial(1, 3)[1].values() if f]), 15)  # the words-lane practice faults
        self.assertEqual(len([f for f in self.trial(2, 3)[1].values() if f]), 13)

    def test_the_selection_is_the_same_every_time(self):
        a, b = self.trial(2, 4), self.trial(2, 4)
        self.assertEqual([v.visit_id for v in a[0]], [v.visit_id for v in b[0]])
        self.assertEqual({k: (f or {}).get("fault_id") for k, f in a[1].items()},
                         {k: (f or {}).get("fault_id") for k, f in b[1].items()})

    def test_the_advice_faults_are_two_of_each_kind_with_the_needs_of_a_graded_case(self):
        fl = faults.load_practice_faults(2, D)
        self.assertEqual(len(fl), 13)  # PA01 to PA12, and PA13: the hidden instruction in the answer (version 3)
        self.assertEqual(Counter(f["rule"] for f in fl), {4: 4, 5: 5, 6: 4})
        self.assertEqual([f["ops"][0]["kind"] for f in fl if f["ops"][0]["op"] == "inject"], ["answer"])
        fl = [f for f in fl if f["ops"][0]["op"] == "rewrite"]
        modes = Counter((f["ops"][0]["mode"], f["ops"][0].get("level")) for f in fl)
        self.assertEqual(modes, {("drop_source", None): 2, ("wrong_source", None): 2, ("set_level", "high"): 2,
                                 ("set_level", "very low"): 2, ("drop_ai_mark", None): 2, ("replace", None): 2})
        for f in fl:
            faults.check_fault(f, W, D)
            step = f["ops"][0]["step"]
            self.assertIn(step, ("patient_note", "plan") if f["rule"] == 5 else ("answer", "plan", "patient_note"))
            if f["rule"] == 5:
                self.assertIn("expert_certainty_in", f["needs"])
        # no rule 5 violation is planted on a case without a grade
        chosen, plan, _, _ = self.trial(2, 4)
        for v in chosen:
            f = plan[v.visit_id]
            if f and f["rule"] == 5:
                self.assertIn(v.expert_certainty, f["needs"]["expert_certainty_in"])

    def test_the_words_faults_all_name_the_words_lane(self):
        for f in self.trial(1, 2)[1].values():
            if f:
                self.assertIn(faults.fault_lane(f, W), ("words", None))


class TheTools(unittest.TestCase):
    def quiet(self, tool, argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = tool.main(argv)
        return code, buf.getvalue()

    def test_the_experiment_is_required_and_a_trial_takes_the_practice_set_alone(self):
        rb = load_tool("run_bench")
        with self.assertRaises(SystemExit):
            with contextlib.redirect_stderr(io.StringIO()):
                rb.main(["--trial", "1"])
        code, text = self.quiet(rb, ["--experiment", "1", "--trial", "1", "--split", "test"])
        self.assertEqual(code, 2)
        self.assertIn("practice set by itself", text)

    @needs_raw_data
    def test_a_trial_of_each_experiment_with_the_stand_in_ai_plants_and_fires_every_violation(self):
        rb = load_tool("run_bench")
        for exp, planted in ((1, 15), (2, 13)):
            name = "unittest_trial"
            code, text = self.quiet(rb, ["--experiment", str(exp), "--trial", "2", "--name", name])
            run_dir = ROOT / "runs" / ("%s_e%d" % (name, exp))
            try:
                self.assertEqual(code, 0, text)
                self.assertIn("trial: 2 clean, %d planted" % planted, text)
                self.assertIn("did not take effect: none", text)
                res = store.read_jsonl(run_dir / "results.jsonl")
                self.assertEqual(len(res), (2 + planted) * len(D["conditions"]["order"]))
                self.assertEqual({r["experiment"] for r in res}, {exp})
                self.assertFalse([r for r in res if r["crashed"]])
            finally:
                import shutil
                shutil.rmtree(str(run_dir), ignore_errors=True)

    @needs_raw_data
    def test_ai_parts_off_is_recorded_and_the_default_has_three_conditions(self):
        self.assertEqual(D["conditions"]["order"], ["A", "A+", "B"])
        rb = load_tool("run_bench")
        code, _ = self.quiet(rb, ["--experiment", "2", "--split", "tune", "--limit", "1", "--name", "unittest_off",
                                  "--ai-parts", "off", "--conditions", "A,C"])
        run_dir = ROOT / "runs" / "unittest_off_e2"
        try:
            self.assertEqual(code, 0)
            man = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(man["counts"]["ai_parts"], "off")
            self.assertEqual({r["condition"] for r in store.read_jsonl(run_dir / "results.jsonl")}, {"A", "C"})
        finally:
            import shutil
            shutil.rmtree(str(run_dir), ignore_errors=True)

    def test_the_final_texts_carry_the_answer_for_the_review(self):
        from custody import engine
        from custody.core import Visit
        seen = {}
        real = assemble.make_parts(W, bench.run_choices(D))
        def review(own_log, final, view, rchoices, ai, run_id):
            seen[run_id] = dict(final)
            return []
        parts = dict(real, review=review)
        with tempfile.TemporaryDirectory() as tmp:
            bench.run_one(E2[0], "A", None, parts, W, D, tmp)
            bench.run_one(E1[0], "A", None, parts, W, D, tmp)
        a, w = seen["q0001.A.r0"], seen["c0001.A.r0"]
        self.assertTrue(a["ai_answer"] and a["patient_note"])
        self.assertIsNone(w["ai_answer"])

    def test_run_and_live_folders_are_separate_per_experiment(self):
        ra, rl = load_tool("run_advice"), load_tool("run_live")
        for tool in (ra,):
            with self.assertRaises(SystemExit):
                with contextlib.redirect_stderr(io.StringIO()):
                    tool.main(["status"])
        self.assertEqual(str(visits.case_path(1, D)), str(ROOT / "data" / "cases" / "exp1.jsonl"))
        self.assertEqual(str(visits.case_path(2, D)), str(ROOT / "data" / "cases" / "exp2.jsonl"))
        with tempfile.TemporaryDirectory() as tmp:
            for exp in (1, 2):
                code, text = self.quiet(ra, ["status", "--experiment", str(exp), "--live-dir", str(Path(tmp) / ("l%d" % exp))])
                self.assertEqual(code, 0, text)
        self.assertIn("live_e", Path(ROOT / "tools" / "run_advice.py").read_text(encoding="utf-8"))
        self.assertIn("live_e", Path(ROOT / "tools" / "run_live.py").read_text(encoding="utf-8"))

    @needs_raw_data
    def test_the_score_tool_takes_the_experiment_through_the_run_folder(self):
        rb = load_tool("run_bench")
        code, _ = self.quiet(rb, ["--experiment", "1", "--split", "tune", "--limit", "2", "--name", "unittest_score"])
        run_dir = ROOT / "runs" / "unittest_score_e1"
        try:
            self.assertEqual(code, 0)
            sc = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(sc["table"]), ["1", "2", "3"])
        finally:
            import shutil
            shutil.rmtree(str(run_dir), ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
