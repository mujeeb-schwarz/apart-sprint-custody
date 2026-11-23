"""Tests for fixes G1 to G7 (13 Nov, after the live-path audit): G1 one answer line from the judge, G2 the wall
around the test visits, G3 live or canned in the manifest, G4 opaque visit tokens, G5 partial scores,
G6 unusable_visits.json required, G7 the judge's level for rule 5. They write only to temporary folders."""
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_advice as TA  # noqa: E402
import test_score as TS  # noqa: E402
from custody import ai_live, datasets, filing, judge, score, store  # noqa: E402
from custody.core import ContractError, CustodyError, DataError, fingerprint  # noqa: E402

sys.path.insert(0, str(ROOT / "tools"))
import file_predictions as FP  # noqa: E402
from raw_data_guard import needs_raw_data, needs_retired_cases  # noqa: E402

TOOL = TA.TOOL

D = datasets.default_choices()
W = TS.W


# ------------------------------------------------------------------- G1

class JudgeOneLine(unittest.TestCase):
    def check(self, output, expects):
        call = {"expects": expects}
        judge.make_validator(D)(output, call)

    def test_lenient_forms_are_read(self):
        for out, want in (("VERDICT kept", ("verdict", "kept")), ("**VERDICT** broken.", ("verdict", "broken")),
                          ("- verdict: Kept", ("verdict", "kept")), ("1. `VERDICT broken`", ("verdict", "broken")),
                          ("Some reasoning.\nVERDICT kept", ("verdict", "kept")),
                          ("LEVEL very-low", ("level", "very low")), ("level: Very_Low.", ("level", "very low")),
                          ("**LEVEL** moderate", ("level", "moderate")), ("LEVEL none", ("level", "none"))):
            self.assertEqual(judge.parse_answer(out), want, out)

    def test_two_answer_lines_are_refused(self):
        for out, expects in (("VERDICT kept\nVERDICT broken", "verdict"), ("VERDICT kept\nverdict: kept", "verdict"),
                             ("LEVEL low\nLEVEL high", "level"), ("- LEVEL low\n**LEVEL** low", "level")):
            with self.assertRaises(ContractError, msg=out):
                self.check(out, expects)

    def test_no_answer_line_is_refused(self):
        for out, expects in (("I think it is kept", "verdict"), ("", "verdict"), ("LEVEL high", "verdict"),
                             ("VERDICT kept", "level"), ("LEVEL medium", "level")):
            with self.assertRaises(ContractError, msg=out):
                self.check(out, expects)

    def test_a_line_of_the_other_kind_is_ignored(self):
        self.check("VERDICT kept\nLEVEL high", "verdict")
        self.assertEqual(judge.verdict_of(6, "LEVEL high\nVERDICT broken", None, D), "broken")

    def test_the_import_refuses_it_and_the_call_stays_pending(self):
        job = {"visit_id": "v1", "item_id": "i" * 16, "rule": 4, "text": "t", "true_sources": ["pmid:1"], "grade": None}
        call = ai_live.make_call("c" * 16, "judge.v1", "p", "verdict")
        store = ai_live.AnswerStore(tempfile.mkdtemp())
        row = {"call_id": call["call_id"], "prompt_fp": call["prompt_fp"], "output": "VERDICT kept\nVERDICT broken"}
        res = ai_live.import_answers(store, {call["call_id"]: call}, [row],
                                     validators={"judge.v1": judge.make_validator(D)})
        self.assertEqual(res["stored"], 0)
        self.assertIn("exactly one", res["refused"][0]["reason"])
        self.assertEqual(store.answers(), {})


# ------------------------------------------------------------------- G7

READ = "Claim: The treatment may reduce the outcome. [source: pmid:1]\n[AI-generated]"  # the reader reads "low"
UNREAD = "The treatment helps a little. [source: pmid:1]\n[AI-generated]"
VISIT = {"visit_id": "v1", "expert_certainty": "low", "given_answer": None, "given_by": None,
         "evidence": [{"source_id": "pmid:1"}]}


def rows(parent_text, child_text, parent="answer", child="plan"):
    return [{"run_id": "v1.A.r0", "t": 10, "item": {"item_id": "p" * 16, "visit_id": "v1", "kind": parent,
                                                      "text": parent_text, "made_by": "s", "parents": []}},
            {"run_id": "v1.A.r0", "t": 11, "item": {"item_id": "q" * 16, "visit_id": "v1", "kind": child,
                                                      "text": child_text, "made_by": "s", "parents": ["p" * 16]}}]


class JudgeLevelRule5(unittest.TestCase):
    def facts(self, level, verdict):
        return score.text_facts(rows(READ, UNREAD), VISIT, D, {("q" * 16, 5): verdict}, {("q" * 16, 5): level})[5]

    def test_reader_low_then_unreadable_child(self):
        f = self.facts("high", "broken")
        self.assertTrue(f["broken"])
        f = self.facts("low", "kept")
        self.assertFalse(f["broken"])
        self.assertFalse(f["unknown"])
        f = self.facts("none", "undecided")
        self.assertFalse(f["broken"])
        self.assertTrue(f["unknown"])

    def test_the_old_row_without_a_level_still_works(self):
        f = score.text_facts(rows(READ, UNREAD), VISIT, D, {("q" * 16, 5): "kept"}, None)[5]
        self.assertFalse(f["broken"])
        f = score.text_facts(rows(READ, UNREAD), VISIT, D, {("q" * 16, 5): "broken"}, None)[5]
        self.assertTrue(f["broken"])  # not:low after a parent of low: an old row still reads as a change

    def test_judge_rows_carry_the_level(self):
        job = {"visit_id": "v1", "item_id": "i" * 16, "rule": 5, "text": "t", "true_sources": [], "grade": "low"}
        out = judge.judge_jobs(lambda p, f: "**LEVEL** very-low", [job], D)
        self.assertEqual((out[0]["level"], out[0]["verdict"]), ("very low", "broken"))
        out = judge.judge_jobs(lambda p, f: "VERDICT kept", [dict(job, rule=6)], D)
        self.assertNotIn("level", out[0])

    def test_the_entry_comparison_uses_the_judge_level(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TS.Store(tmp)
            s.visit("v1", "c1", "test", grade="low")
            s.run("v1", "c1", "test", "A", texts=[("answer", UNREAD), ("plan", READ)])
            s.write()
            iid = s.rows["texts"][0]["item"]["item_id"]
            (Path(tmp) / "judge.jsonl").write_text(json.dumps(
                {"visit_id": "v1", "item_id": iid, "rule": 5, "verdict": "broken", "judge": "live",
                 "prompt_id": "judge.v1", "level": "high"}) + "\n", encoding="utf-8")
            res = score.score_run(tmp, W, D)
            ent = res["certainty_change_test"]["A"]["entry_error"]
            self.assertEqual(ent["hardened"], 1)
            self.assertEqual(ent["undecided"], 0)


# ------------------------------------------------------------------- G2

def export(tmp, vpath, *more):
    return TOOL.main(["export", "--conditions", "A"] + TA.args(tmp, vpath, *more))


class Wall(unittest.TestCase):
    def test_a_tuning_only_selection_needs_no_filing(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = TA.small_visits(tmp, tune=1)
            self.assertEqual(export(tmp, vpath), TOOL.WAITING)
            self.assertFalse((Path(tmp) / "live" / "frozen.json").exists())  # tuning runs freeze nothing

    def test_a_test_visit_is_refused_without_a_filing_and_passes_with_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = TA.small_visits(tmp, tune=0, test=1)
            self.assertEqual(export(tmp, vpath, "--split", "test"), 2)
            self.assertEqual(TOOL.main(["run", "--split", "test"] + TA.args(tmp, vpath)), 2)
            self.assertEqual(TOOL.main(["import", str(Path(tmp) / "x.jsonl")] + TA.args(tmp, vpath, "--split", "test")), 2)
            TA.file_predictions(tmp)
            self.assertEqual(export(tmp, vpath, "--split", "test"), TOOL.WAITING)

    def test_split_all_counts_as_holding_test_visits(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = TA.small_visits(tmp, tune=1, test=1)
            self.assertEqual(export(tmp, vpath, "--split", "all"), 2)
            TA.file_predictions(tmp)
            self.assertEqual(export(tmp, vpath, "--split", "all"), TOOL.WAITING)

    def test_an_edited_copy_of_the_filed_page_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = TA.small_visits(tmp, tune=0, test=1)
            TA.file_predictions(tmp)
            copy = Path(tmp) / "filing" / "docs" / "predictions_as_filed.md"
            copy.write_text(copy.read_text(encoding="utf-8") + "one more prediction\n", encoding="utf-8")
            self.assertEqual(export(tmp, vpath, "--split", "test"), 2)

    def test_the_tool_files_refuses_and_refiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            page = Path(tmp) / "page.md"
            page.write_text("p1\n", encoding="utf-8")
            self.assertEqual(FP.main([str(page), "--root", tmp]), 0)
            rec = json.loads((Path(tmp) / "config" / "predictions_filed.json").read_text(encoding="utf-8"))
            self.assertEqual(rec["page_sha256"], fingerprint(page.read_text(encoding="utf-8")))
            self.assertEqual(rec["scorer_fingerprint"], filing.scorer_fp())
            self.assertRegex(rec["filed_at"], r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d$")
            self.assertFalse(rec["refiling"])
            self.assertEqual(FP.main([str(page), "--root", tmp]), 2)  # refused
            page.write_text("p2\n", encoding="utf-8")
            self.assertEqual(FP.main([str(page), "--root", tmp, "--refile"]), 0)
            new = json.loads((Path(tmp) / "config" / "predictions_filed.json").read_text(encoding="utf-8"))
            self.assertTrue(new["refiling"])
            kept = json.loads((Path(tmp) / "config" / new["earlier_filing"]).read_text(encoding="utf-8"))
            self.assertEqual(kept["page_sha256"], rec["page_sha256"])
            self.assertNotEqual(new["page_sha256"], rec["page_sha256"])

    def test_a_prompt_changed_after_the_freeze_is_refused_named_and_passes_with_a_reason(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "project"
            shutil.copytree(str(ROOT / "prompts"), str(fake / "prompts"))
            (fake / "config").mkdir()
            shutil.copy(str(ROOT / "config" / "design_choices.json"), str(fake / "config"))
            live = Path(tmp) / "live"
            with mock.patch.object(filing, "ROOT", fake):
                filing.check_freeze(live, D)
                rec = json.loads((live / "frozen.json").read_text(encoding="utf-8"))
                self.assertIn("prompt:reminders.v2", rec["fingerprints"])  # the step prompts and reminders too
                self.assertIn("prompt:note_writer.v1", rec["fingerprints"])
                self.assertIn("design_choices", rec["fingerprints"])
                self.assertIn("scorer", rec["fingerprints"])
                filing.check_freeze(live, D)  # unchanged: passes
                f = fake / "prompts" / "note_writer.v1.txt"
                f.write_text(f.read_text(encoding="utf-8") + "\nchanged\n", encoding="utf-8")
                with self.assertRaises(CustodyError) as cm:
                    filing.check_freeze(live, D)
                self.assertIn("prompt:note_writer.v1", str(cm.exception))
                filing.check_freeze(live, D, "typo in the note writer prompt")
                rec = json.loads((live / "frozen.json").read_text(encoding="utf-8"))
                self.assertEqual(rec["changes_after_freeze"][0]["changed"], ["prompt:note_writer.v1"])
                self.assertEqual(rec["changes_after_freeze"][0]["reason"], "typo in the note writer prompt")
                filing.check_freeze(live, D)  # the change is accepted now, and not listed twice
                self.assertEqual(len(json.loads((live / "frozen.json").read_text(encoding="utf-8"))["changes_after_freeze"]), 1)

    def test_the_scorer_says_whether_it_is_the_filed_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TS.Store(Path(tmp) / "run")
            s.visit("v1", "c1", "tune")
            s.run("v1", "c1", "tune", "A")
            (Path(tmp) / "run").mkdir(exist_ok=True)
            s.write()
            h = score.score_run(Path(tmp) / "run", W, D, Path(tmp) / "none")["header"]
            self.assertFalse(h["predictions_filed"])
            self.assertIsNone(h["scorer_equals_filed"])
            page = Path(tmp) / "p.md"
            page.write_text("x", encoding="utf-8")
            filing.file_predictions(page, Path(tmp) / "f")
            h = score.score_run(Path(tmp) / "run", W, D, Path(tmp) / "f")["header"]
            self.assertTrue(h["predictions_filed"])
            self.assertTrue(h["scorer_equals_filed"])
            jp = Path(tmp) / "f" / "config" / "predictions_filed.json"
            rec = json.loads(jp.read_text(encoding="utf-8"))
            rec["scorer_fingerprint"] = "0" * 64
            jp.write_text(json.dumps(rec), encoding="utf-8")
            h = score.score_run(Path(tmp) / "run", W, D, Path(tmp) / "f")["header"]
            self.assertFalse(h["scorer_equals_filed"])


# ------------------------------------------------------------ G3, G5, G6

def hand_run(tmp, text=TS.GOOD):
    s = TS.Store(tmp)
    s.visit("v1", "c1", "tune")
    s.run("v1", "c1", "tune", "A", texts=[("patient_note", text)])
    s.write()
    return s


class ManifestAndPartial(unittest.TestCase):
    def manifest(self, tmp, ai, **kw):
        store.write_manifest(tmp, "t", {"s": 1}, ["A"], {"visits": 1}, {"scorer": "x"}, ai=ai, **kw)

    def test_canned_runs_carry_the_stand_in_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            hand_run(tmp)
            self.manifest(tmp, "canned")
            res = score.score_run(tmp, W, TS.DR)
            self.assertEqual(res["header"]["ai"], "canned")
            self.assertIn("stand-in text: these numbers measure nothing", res["header"]["stand_in_text"])
            self.assertIn("stand-in text: these numbers measure nothing", score.render_header(res["header"]))
            self.assertEqual(json.loads((Path(tmp) / "scores.json").read_text(encoding="utf-8"))["header"]["ai"], "canned")

    def test_a_live_manifest_needs_an_answers_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                self.manifest(tmp, "live")

    @needs_raw_data
    def test_a_live_run_names_its_answers_in_the_manifest_and_the_scorer_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = TA.small_visits(tmp, tune=1)
            TA.round_trip(tmp, vpath, "--conditions", "A")
            man = store.read_json(Path(tmp) / "runs" / "advice_tune_e2" / "manifest.json")
            answers = (Path(tmp) / "live" / "answers.jsonl").read_text(encoding="utf-8")
            self.assertEqual((man["ai"], man["answers_fingerprint"]), ("live", fingerprint(answers)))
            sc = store.read_json(Path(tmp) / "runs" / "advice_tune_e2" / "scores.json")
            self.assertEqual((sc["header"]["ai"], sc["header"]["answers_fingerprint"]), ("live", fingerprint(answers)))
            self.assertIsNone(sc["header"]["stand_in_text"])

    def test_the_canned_bench_says_canned(self):
        man = store.read_json(ROOT / "runs" / "e2e" / "manifest.json") if (ROOT / "runs" / "e2e" / "manifest.json").exists() else None
        if man is not None:
            self.assertEqual(man["ai"], "canned")

    def test_g6_a_live_run_without_unusable_visits_is_not_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            hand_run(tmp)
            self.manifest(tmp, "live", answers_fingerprint="a" * 64)
            with self.assertRaises(DataError) as cm:
                score.score_run(tmp, W, D)
            self.assertIn("unusable_visits.json", str(cm.exception))
            self.assertIn("run_advice", str(cm.exception))
            (Path(tmp) / "unusable_visits.json").write_text("[]\n", encoding="utf-8")
            self.assertEqual(score.score_run(tmp, W, D)["header"]["ai"], "live")

    def test_g5_partial_until_the_judge_has_read_everything(self):
        with tempfile.TemporaryDirectory() as tmp:
            hand_run(tmp, TS.NOMARK)  # no AI mark: rule 6 goes to the judge
            stale = Path(tmp) / "scores.json"
            stale.write_text('{"old": true}\n', encoding="utf-8")
            res = score.score_run(tmp, W, TS.DR)
            self.assertFalse(res["header"]["complete"])
            self.assertFalse(stale.exists())
            self.assertTrue((Path(tmp) / "scores.partial.json").exists())
            self.assertTrue((Path(tmp) / "scores.stale_before_judge_complete.json").exists())
            iid = "v1.A.r0-patient_note"
            (Path(tmp) / "judge.jsonl").write_text(json.dumps(
                {"visit_id": "v1", "item_id": iid, "rule": 6, "verdict": "kept", "judge": "live", "prompt_id": "judge.v1"}) + "\n",
                encoding="utf-8")
            res = score.score_run(tmp, W, TS.DR)
            self.assertTrue(res["header"]["complete"])
            self.assertTrue(stale.exists())
            self.assertFalse((Path(tmp) / "scores.partial.json").exists())


# ------------------------------------------------------------------- G4

class OpaqueTokens(unittest.TestCase):
    @needs_raw_data
    def test_checker_prompts_show_no_visit_id_and_the_salt_stays_home(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = TA.small_visits(tmp, tune=2)
            seen = []
            TA.round_trip(tmp, vpath, "--conditions", "A,A+", seen=seen)
            checkers = [c for c in seen if c["prompt_id"].split(".")[0] in ("watcher", "reviewer", "judge")]
            self.assertTrue(any(c["prompt_id"].startswith("reviewer") for c in checkers))
            live = Path(tmp) / "live"
            salt = (live / "private" / ai_live.SALT_FILE).read_text(encoding="utf-8").strip()
            mapping = json.loads((live / "private" / ai_live.TOKENS_FILE).read_text(encoding="utf-8"))
            self.assertEqual(set(mapping.values()) <= {v.visit_id for v in keep}, True)
            for c in seen:
                self.assertNotIn(salt, json.dumps(c))
            for c in checkers:
                self.assertIsNone(re.search(r"\bv\d{4}\b", c["prompt"]), c["prompt_id"])
            reviewer = [c for c in checkers if c["prompt_id"].startswith("reviewer")]
            self.assertTrue(any(tok in c["prompt"] for c in reviewer for tok in mapping))
            for p in (live / "handout").rglob("*"):  # the private files are not among the exports
                if p.is_file():
                    self.assertNotIn(salt, p.read_text(encoding="utf-8"))
            self.assertEqual(sorted(x.name for x in live.iterdir() if x.name != "answers.jsonl"), ["handout", "private"])

    def test_the_token_is_stable_and_depends_on_the_salt(self):
        with tempfile.TemporaryDirectory() as t1, tempfile.TemporaryDirectory() as t2:
            a1, a2, b = (ai_live.VisitTokens(t1, ["reviewer.v1"]), ai_live.VisitTokens(t1, ["reviewer.v1"]),
                         ai_live.VisitTokens(t2, ["reviewer.v1"]))
            self.assertEqual(a1.token_of("v0001"), a2.token_of("v0001"))
            self.assertNotEqual(a1.token_of("v0001"), b.token_of("v0001"))

    def test_a_step_prompt_is_left_alone(self):
        with tempfile.TemporaryDirectory() as t:
            tk = ai_live.VisitTokens(t, ["reviewer.v1"])
            self.assertEqual(tk.mask("note_writer.v1", "see v0001"), "see v0001")
            self.assertNotIn("v0001", tk.mask("reviewer.v1", "see v0001"))


if __name__ == "__main__":
    unittest.main()
