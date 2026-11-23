"""Tests for the repairs after the live-path audit (13 Nov): F1 the grade never reaches an export, F2 three
separate pending sets, F3 flag lines and NO FLAGS, F4 formatted send lines, F5 unusable step answers,
F6 missing prompt files. They write only to temporary folders."""
import copy
import json
import re
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

import test_advice as TA  # noqa: E402
from custody import ai as ai_mod, ai_live, datasets, judge, steps, visits, watch  # noqa: E402
from custody.core import ContractError, action_near_misses, canon  # noqa: E402
from raw_data_guard import needs_raw_data, needs_retired_cases  # noqa: E402

D = datasets.default_choices()
TOOL = TA.TOOL
args = TA.args


def graded_file(tmp, n=3, regrade=None):
    every = TA.legacy_ids(visits.read_cases(str(ROOT / "data" / "cases" / "exp2.jsonl"), 2))
    keep = [v for v in every if v.split == "tune" and v.expert_certainty and v.given_answer is None][:n]
    if regrade:
        keep = [replace(v, expert_certainty=regrade[v.expert_certainty]) for v in keep]
    path = Path(tmp) / "visits.jsonl"
    path.write_text("".join(canon(asdict(v)) + "\n" for v in keep), encoding="utf-8")
    return path, keep


def drive(tmp, vpath, fn=TA.helper_answer, *more, max_rounds=25):
    """Run, answer what is missing, import, repeat. Returns every pending row seen."""
    seen = []
    for n in range(max_rounds):
        if TOOL.main(["run"] + args(tmp, vpath, *more)) == 0:
            return seen
        pending = ai_live.read_pending(Path(tmp) / "live")
        seen.extend(pending.values())
        out = Path(tmp) / ("ans_%d.jsonl" % n)
        TA.write_answers(list(pending.values()), out, fn)
        TOOL.main(["import", str(out)] + args(tmp, vpath, *more))
    raise AssertionError("no end")


def ids_of(rows):
    return sorted({i for r in rows for i in r["real"]})  # the real call ids (H1: the exported ones differ by salt)


# ------------------------------------------------------------------- F1

class GradeNeverExported(unittest.TestCase):
    @needs_raw_data
    def test_no_exported_record_carries_the_grade(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = graded_file(tmp, 3)
            seen = drive(tmp, vpath, TA.helper_answer, "--conditions", "A,B")
            self.assertTrue(any(r["prompt_id"].startswith("plan") for r in seen))
            self.assertTrue(any(r["prompt_id"].startswith("judge") for r in seen))
            allowed = " ".join(ai_mod.prompt_text(p) for p in {r["prompt_id"] for r in seen}).lower()
            allowed += " ".join(judge.rule_text(r, D) for r in (4, 5, 6)).lower()  # the rules' own words
            allowed += " ".join(v.conversation + " " + v.question + " " + " ".join(e["text"] + e["title"] for e in v.evidence)
                                for v in keep).lower()
            # version 3: the answer enters with its grade written into its words, by a program
            allowed += " ".join(visits.compose_answer(v, D) or "" for v in keep).lower()
            for row in seen:
                text = canon(row).lower()
                self.assertNotIn('"grade"', text)
                for level in D["ladder"]["levels"]:
                    pat = r"(?<![a-z])%s(?![a-z])" % re.escape(level)
                    self.assertLessEqual(len(re.findall(pat, text)), len(re.findall(pat, allowed)), (row["prompt_id"], level))

    @needs_raw_data
    def test_changing_a_grade_changes_no_call_id(self):
        swap = {"high": "low", "moderate": "very low", "low": "high", "very low": "moderate", "no data": "high"}
        runs = []
        for regrade in (None, swap):
            with tempfile.TemporaryDirectory() as tmp:
                vpath, keep = graded_file(tmp, 3, regrade)
                seen = drive(tmp, vpath, TA.helper_answer, "--conditions", "A,B")
                runs.append((ids_of(seen), [v.expert_certainty for v in keep]))
        self.assertNotEqual(runs[0][1], runs[1][1])
        # version 3: the answer enters with its grade written into its words, so a changed grade changes the
        # prompt that shows the answer; what stays true is that no field carries a grade (test above)
        self.assertNotEqual(runs[0][0], runs[1][0])

    def test_the_step_and_the_judge_pass_no_grade_field(self):
        fields_seen = []

        def spy(prompt_id, fields):
            fields_seen.append(dict(fields))
            return "x"
        job = {"visit_id": "v1", "item_id": "i" * 16, "rule": 5, "text": "t", "true_sources": ["pmid:1"], "grade": "low"}
        self.assertNotIn("grade", judge.judge_fields(job, D))
        self.assertEqual(ai_mod.call_id_of("judge.v1", judge.judge_fields(job, D)),
                         ai_mod.call_id_of("judge.v1", judge.judge_fields(dict(job, grade="high"), D)))
        self.assertNotIn("{{grade}}", ai_mod.prompt_text("judge.v1"))
        self.assertNotIn("grade", " ".join(D["rules"]["judge_sees"]))

    def test_rule_5_compares_the_reported_level_with_the_grade_in_the_program(self):
        self.assertEqual(judge.verdict_of(5, "LEVEL low", "low", D), "kept")
        self.assertEqual(judge.verdict_of(5, "LEVEL high", "low", D), "broken")
        self.assertEqual(judge.verdict_of(5, "LEVEL none", "low", D), "undecided")


# ------------------------------------------------------------------- F2

class ThreeSets(unittest.TestCase):
    def test_first_round_writes_steps_and_methods_apart_and_no_old_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = graded_file(tmp, 4)
            self.assertEqual(TOOL.main(["run"] + args(tmp, vpath, "--conditions", "A,A+", "--batch-size", "2")), TOOL.WAITING)
            live = Path(tmp) / "live"
            self.assertFalse((live / "pending.jsonl").exists())
            live = live / "handout"
            self.assertFalse((live / "pending_judge.jsonl").exists())
            steps_rows = ai_live._read_jsonl(live / "pending_steps.jsonl")
            method_rows = ai_live._read_jsonl(live / "pending_methods.jsonl")
            self.assertTrue(steps_rows and method_rows)
            self.assertEqual({r["prompt_id"] for r in steps_rows}, {"plan.v1"})  # version 3: the advice lane starts at the plan
            self.assertEqual({r["prompt_id"] for r in method_rows}, {"watcher.v1"})
            self.assertTrue((live / "pending_steps_parts" / "part_001.jsonl").exists())
            self.assertTrue((live / "pending_methods_parts" / "part_001.jsonl").exists())
            self.assertFalse((live / "pending_parts").exists())

    @needs_raw_data
    def test_the_judge_set_is_its_own_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = graded_file(tmp, 2)
            for n in range(25):
                TOOL.main(["run"] + args(tmp, vpath, "--conditions", "A"))
                live = Path(tmp) / "live" / "handout"
                if (live / "pending_judge.jsonl").exists():
                    break
                pending = ai_live.read_pending(Path(tmp) / "live")
                out = Path(tmp) / ("a%d.jsonl" % n)
                TA.write_answers(list(pending.values()), out)
                TOOL.main(["import", str(out)] + args(tmp, vpath, "--conditions", "A"))
            rows = ai_live._read_jsonl(live / "pending_judge.jsonl")
            self.assertTrue(rows)
            self.assertTrue(all(r["prompt_id"].startswith("judge") for r in rows))
            self.assertFalse((live / "pending_steps.jsonl").exists())
            self.assertFalse((live / "pending_methods.jsonl").exists())

    def test_the_shuffle_is_seeded_and_mixes_the_order(self):
        calls = [{"call_id": "%03d" % i} for i in range(30)]
        seed = D["seeds"]["export_order"]
        a, b = ai_live.shuffled(calls, seed, "steps"), ai_live.shuffled(calls, seed, "steps")
        self.assertEqual(a, b)
        self.assertEqual(sorted(c["call_id"] for c in a), [c["call_id"] for c in calls])
        self.assertNotEqual(a, calls)
        self.assertNotEqual(a, ai_live.shuffled(calls, seed + 1, "steps"))

    def test_an_old_pending_file_is_said_plainly(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = graded_file(tmp, 1)
            live = Path(tmp) / "live"
            live.mkdir()
            (live / "pending.jsonl").write_text("{}\n", encoding="utf-8")
            self.assertEqual(TOOL.main(["import", str(live / "pending.jsonl")] + args(tmp, vpath)), 2)
            self.assertEqual(TOOL.main(["status"] + args(tmp, vpath)), 2)
            self.assertEqual(TOOL.main(["export"] + args(tmp, vpath, "--conditions", "A")), TOOL.WAITING)
            self.assertFalse((live / "pending.jsonl").exists())
            self.assertTrue((live / "handout" / "pending_steps.jsonl").exists())


# ------------------------------------------------------------------- F3

class FlagLines(unittest.TestCase):
    def test_six_shapes_parse(self):
        for line in ("FLAG 6 no mark", "**FLAG 6** no mark", "- FLAG 6 no mark", "1. FLAG 6 no mark",
                     "`FLAG 6` no mark", "Flag 6: no mark", "FLAG 6 - no mark", "> **Flag 6**: no mark"):
            self.assertEqual(watch.parse_flags(line, {6}), [(6, "no mark")], line)
        self.assertEqual(watch.parse_flags("NO FLAGS", {6}), [])

    def validate(self, text):
        call = ai_live.make_call("c" * 16, "watcher.v1", "p", "text")
        store = ai_live.AnswerStore(tempfile.mkdtemp())
        pending = {call["call_id"]: call}
        row = {"call_id": call["call_id"], "prompt_fp": call["prompt_fp"], "output": text}
        res = ai_live.import_answers(store, pending, [row], validators={"watcher.v1": watch.validate_flags_answer})
        return res, store

    def test_good_answers_are_stored(self):
        for text in ("NO FLAGS", "no flags.", "**NO FLAGS**\n", "FLAG 1 a\nFLAG 6: b", "- FLAG 1 a\n\n1. Flag 4 b"):
            res, store = self.validate(text)
            self.assertEqual(res["stored"], 1, text)

    def test_prose_mixed_answers_and_empty_answers_are_refused(self):
        for text in ("I looked and all is well.", "FLAG 1 a\nThat is all.", "NO FLAGS\nFLAG 1 a", "", "  \n", "Here: FLAG 1 a"):
            res, store = self.validate(text)
            self.assertEqual(res["stored"], 0, repr(text))
            self.assertEqual(len(res["refused"]), 1, repr(text))
            self.assertTrue(res["refused"][0]["reason"])
            self.assertEqual(store.answers(), {})

    def test_both_prompts_ask_for_no_flags(self):
        for p in ("watcher.v1", "reviewer.v1"):
            self.assertIn("NO FLAGS", ai_mod.prompt_text(p))


# ------------------------------------------------------------------- F4

class SendLines(unittest.TestCase):
    SHAPES = ["SEND transcript TO analytics", "SEND transcript TO analytics.", "**SEND transcript TO analytics**",
              "- SEND transcript TO analytics", "`SEND transcript TO analytics`", "  SEND transcript TO analytics",
              "Send transcript to analytics", "1. Send transcript to analytics.", "> `Send transcript to analytics`"]

    def test_the_formatted_shapes_are_sends(self):
        for line in self.SHAPES:
            text, reqs = steps.split_actions("before\n%s\nafter" % line, D)
            self.assertEqual([(r["kind"], r["to"]) for r in reqs], [("transcript", "analytics")], line)
            self.assertEqual(text, "before\nafter", line)

    def test_a_whole_line_with_unknown_names_is_a_near_miss_and_stays(self):
        line = "Send the transcript to the patient portal."
        text, reqs = steps.split_actions("a\n%s\nb" % line, D)
        self.assertEqual(reqs, [])
        self.assertEqual(text, "a\n%s\nb" % line)
        self.assertEqual(action_near_misses(text, D), 1)

    def test_a_longer_sentence_is_neither(self):
        for line in ("Please send the transcript to the patient portal.", "We will send transcript to analytics later today",
                     "I could send transcript to analytics, but I will not."):
            text, reqs = steps.split_actions(line, D)
            self.assertEqual((text, reqs), (line, []), line)
            self.assertEqual(action_near_misses(line, D), 0, line)

    def test_the_canonical_pattern_stays_in_config(self):
        self.assertEqual(D["markers"]["action"]["pattern"], "(?m)^SEND ([a-z_]+) TO ([a-z_]+)$")
        self.assertIn("lenient_pattern", D["markers"]["action"])


# ------------------------------------------------------------------- F5

REFUSAL = "I can't provide medical advice."  # (14 Nov: "I'm sorry, but" is a candidate now, not unusable)


def classify(output, prompt_id="ai_answer.v1", prompt="p"):
    return ai_live.make_step_classifier(D)(output, {"prompt_id": prompt_id, "prompt": prompt})


class Unusable(unittest.TestCase):
    def test_what_is_unusable(self):
        good = "Claim: The treatment probably helps [source: pmid:1]\n[AI-generated]"
        self.assertIsNone(classify(good))
        self.assertEqual(classify("  \n"), "empty answer")
        self.assertIsNone(classify(REFUSAL))  # J1: a refusal phrase is a candidate, confirmed by a person
        self.assertIsNone(classify("**I cannot help with that.**", "plan.v1"))
        self.assertIsNone(classify("I won't do this.", "plan.v1"))
        # 14 Nov (H2): two claim lines and no claim line at the evidence tool are no longer unusable
        self.assertIsNone(classify("Here is the answer.\n" + good + "\n\nRevised:\nClaim: It may help [source: pmid:1]"))
        self.assertIsNone(classify("The treatment helps. [source: pmid:1] [AI-generated]"))

    def test_later_steps_and_tool_breaks_are_not_unusable(self):
        self.assertIsNone(classify("FOR YOU\nThe treatment helps.", "patient_note.v1"))
        self.assertIsNone(classify("PLAN\nwith no claim line at all", "plan.v1"))
        self.assertIsNone(classify("Claim: The treatment helps.", "ai_answer.v1"))  # no tag, no mark: the tool's own break
        self.assertIsNone(classify("I can't breathe at night, doctor.", "note_writer.v1",
                                   prompt="TRANSCRIPT\nI can't breathe at night, doctor.\n"))
        self.assertIsNone(classify("I cannot stress enough: " + "word " * 200, "note_writer.v1"))

    def test_an_unusable_answer_is_stored_as_given_with_a_reason_and_not_refused(self):
        call = ai_live.make_call("d" * 16, "ai_answer.v1", "prompt", "text")
        store = ai_live.AnswerStore(tempfile.mkdtemp())
        row = {"call_id": call["call_id"], "prompt_fp": call["prompt_fp"], "output": REFUSAL}
        res = ai_live.import_answers(store, {call["call_id"]: call}, [row], allow_empty=["ai_answer.v1"],
                                     classifiers={"ai_answer.v1": ai_live.make_step_classifier(D)})
        self.assertEqual((res["stored"], res["refused"]), (1, []))
        self.assertEqual(store.answers()[call["real"][0]], REFUSAL)
        self.assertEqual(store.unusable(), {})  # J1: a refusal phrase alone does not mark an answer unusable
        self.assertNotIn("usable", store.rows()[0])
        empty = {"call_id": call["call_id"][::-1], "prompt_fp": call["prompt_fp"], "output": ""}
        call2 = ai_live.make_call("e" * 16, "ai_answer.v1", "prompt", "text")
        res = ai_live.import_answers(store, {call2["call_id"]: call2},
                                     [{"call_id": call2["call_id"], "prompt_fp": call2["prompt_fp"], "output": " "}],
                                     allow_empty=["ai_answer.v1"], classifiers={"ai_answer.v1": ai_live.make_step_classifier(D)})
        self.assertEqual(res["stored"], 1)
        self.assertEqual(store.unusable()[call2["real"][0]], "empty answer")
        self.assertIs(store.rows()[-1]["usable"], False)


class UnusableThroughTheRun(unittest.TestCase):
    CONDS = ("--conditions", "A,A+,B")

    @needs_raw_data
    def test_a_refusal_at_the_evidence_tool_drops_the_visit_only_when_confirmed(self):
        def fn(call):
            return REFUSAL if call["prompt_id"].startswith("plan") else TA.helper_answer(call)
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = graded_file(tmp, 2)
            drive(tmp, vpath, fn, *self.CONDS)
            run_dir = Path(tmp) / "runs" / "advice_tune_e2"
            self.assertEqual(json.loads((run_dir / "unusable_visits.json").read_text(encoding="utf-8")), [])
            cands = json.loads((run_dir / "refusal_candidates.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(x["visit_id"] for x in cands if x["step"] == "plan"),
                             sorted(v.visit_id for v in keep))
            conf = Path(tmp) / "live" / "private" / "unusable_confirmed.json"
            self.assertEqual(json.loads(conf.read_text(encoding="utf-8")), [])  # created empty
            self.assertTrue(json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))["attempts"])
            conf.write_text(json.dumps([x["call_id"] for x in cands if x["step"] == "plan"]), encoding="utf-8")
            drive(tmp, vpath, fn, *self.CONDS)
            listed = json.loads((run_dir / "unusable_visits.json").read_text(encoding="utf-8"))
            self.assertEqual(sorted(x["visit_id"] for x in listed), sorted(v.visit_id for v in keep))
            self.assertEqual({(x["step"], x["reason"]) for x in listed}, {("plan", "refusal")})
            self.assertTrue(all(x["confirmed"] for x in json.loads(
                (run_dir / "refusal_candidates.json").read_text(encoding="utf-8")) if x["step"] == "plan"))
            scores = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
            self.assertEqual(scores["left_out"]["visits"], 2)
            self.assertEqual(scores["left_out"]["by_step_and_reason"], {"plan: refusal": 2})
            self.assertEqual(scores["attempts"], [])
            self.assertTrue(all(v is None for v in scores["output_kept"].values()))

    @needs_raw_data
    def test_j1_a_clinical_sentence_stays_usable_is_listed_once_and_the_confirmed_file_is_never_rewritten(self):
        text = "FOR YOU\nI can't promise this will work, but the evidence suggests it may help. [AI-generated]"

        def fn(call):
            return text if call["prompt_id"].startswith("patient_note") else TA.helper_answer(call)
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = graded_file(tmp, 1)
            drive(tmp, vpath, fn, *self.CONDS)
            run_dir = Path(tmp) / "runs" / "advice_tune_e2"
            self.assertEqual(json.loads((run_dir / "unusable_visits.json").read_text(encoding="utf-8")), [])
            cands = json.loads((run_dir / "refusal_candidates.json").read_text(encoding="utf-8"))
            self.assertEqual([(x["step"], x["confirmed"]) for x in cands], [("patient_note", False)])
            self.assertEqual(set(cands[0]), {"visit_id", "step", "call_id", "reason", "first_300", "confirmed"})
            conf = Path(tmp) / "live" / "private" / "unusable_confirmed.json"
            conf.write_text('[\n  "zzz",   "%s"\n]' % cands[0]["call_id"], encoding="utf-8")
            before = conf.read_bytes()
            self.assertEqual(TOOL.main(["run"] + args(tmp, vpath, *self.CONDS)), 0)
            self.assertEqual(conf.read_bytes(), before)
            self.assertEqual(TOOL.main(["run"] + args(tmp, vpath, *self.CONDS)), 0)
            self.assertEqual(conf.read_bytes(), before)
            listed = json.loads((run_dir / "unusable_visits.json").read_text(encoding="utf-8"))
            self.assertEqual([x["visit_id"] for x in listed], [keep[0].visit_id])
            scores = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
            self.assertEqual(scores["attempts"], [])
            self.assertEqual(scores["left_out"]["visits"], 1)

    @needs_raw_data
    def test_a_patient_note_with_no_claim_line_is_still_scored(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = graded_file(tmp, 2)
            drive(tmp, vpath, TA.helper_answer, *self.CONDS)  # its patient notes have no claim line and no tag
            run_dir = Path(tmp) / "runs" / "advice_tune_e2"
            self.assertEqual(json.loads((run_dir / "unusable_visits.json").read_text(encoding="utf-8")), [])
            scores = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
            self.assertEqual(scores["left_out"]["visits"], 0)
            self.assertTrue(scores["attempts"])
            self.assertEqual(ai_live.AnswerStore(Path(tmp) / "live").unusable(), {})

    @needs_raw_data
    def test_two_claim_lines_at_the_evidence_tool_are_no_longer_unusable(self):
        def fn(call):
            if call["prompt_id"].startswith("ai_answer"):
                return ("Claim: It probably helps [source: pmid:1]\n[AI-generated]\nClaim: It may help [source: pmid:1]")
            return TA.helper_answer(call)
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = graded_file(tmp, 1)
            drive(tmp, vpath, fn, "--conditions", "A,A+,B")
            run_dir = Path(tmp) / "runs" / "advice_tune_e2"
            self.assertEqual(json.loads((run_dir / "unusable_visits.json").read_text(encoding="utf-8")), [])


# ------------------------------------------------------------------- F6

class MissingPromptFiles(unittest.TestCase):
    def test_missing_files_raise(self):
        was = ai_mod.ROOT
        try:
            with tempfile.TemporaryDirectory() as tmp:
                (Path(tmp) / "prompts").mkdir()
                ai_mod.ROOT = Path(tmp)
                with self.assertRaises(ContractError):
                    ai_mod.prompt_text("plan.v1")
                (Path(tmp) / "prompts" / "plan.v1.txt").write_text("PLAN {{answer}}", encoding="utf-8")
                with self.assertRaises(ContractError):  # a step prompt needs the reminders file
                    ai_mod.prompt_text("plan.v1")
                (Path(tmp) / "prompts" / "watcher.v1.txt").write_text("W", encoding="utf-8")
                self.assertEqual(ai_mod.prompt_text("watcher.v1"), "W")
        finally:
            ai_mod.ROOT = was


if __name__ == "__main__":
    unittest.main()
