"""Tests for fixes H1 to H7 (14 Nov, third helper, after the re-check of the live path): H1 exported call ids
from the shown prompt, H2 narrow unusable answers, H3 send lines, H4 flag checks at import, H5 the wall,
H6 the certainty level of a text, H7 the judge's parts per rule. They write only to temporary folders."""
import json
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

os.environ["CUSTODY_TESTING"] = "1"  # H5: the tests may point the tool at a stand-in filing and a small visit list

import test_advice as TA  # noqa: E402
import test_live_path as TL  # noqa: E402
import test_score as TS  # noqa: E402
from custody import ai as ai_mod, ai_live, core, datasets, judge, score, steps, store, watch  # noqa: E402
from custody.core import ContractError, canon  # noqa: E402
from raw_data_guard import needs_raw_data, needs_retired_cases  # noqa: E402

D = datasets.default_choices()
W = TS.W
TOOL = TA.TOOL


# ------------------------------------------------------------------- H1

class ExportedIds(unittest.TestCase):
    @needs_raw_data
    def test_no_exported_id_comes_back_to_a_visit_or_a_condition(self):
        record = []
        orig = ai_mod.call_id_of

        def spy(prompt_id, fields):
            cid = orig(prompt_id, fields)
            record.append((prompt_id, dict(fields), cid))
            return cid

        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = TA.small_visits(tmp, tune=3)
            seen = []
            with mock.patch.object(ai_mod, "call_id_of", spy):
                TA.round_trip(tmp, vpath, "--conditions", "A,A+,B", seen=seen)
            exported = {c["call_id"] for c in seen}
            real = {cid for _, _, cid in record}
            self.assertTrue(exported)
            self.assertFalse(exported & real)  # no exported id is a real call id
            reviewer = [(p, f) for p, f, _ in record if p.startswith("reviewer")]
            self.assertTrue(reviewer)
            visit_ids = [v.visit_id for v in keep] + ["v%04d" % n for n in range(1, 401)]
            hit = 0
            for prompt_id, fields in reviewer:  # the re-check's attack: every visit id and every condition
                for vid in visit_ids:
                    for cond in ("A", "A+", "B", "C"):
                        guess = dict(fields, own_log=re.sub(r"v\d{4}\.(?:A\+|A|B|C)\.r", "%s.%s.r" % (vid, cond),
                                                            fields["own_log"]))
                        if orig(prompt_id, guess) in exported:
                            hit += 1
            self.assertEqual(hit, 0)
            idmap = ai_live.read_idmap(Path(tmp) / "live")
            self.assertTrue(set(idmap) >= exported)
            self.assertTrue({r for v in idmap.values() for r in v} <= real)

    def test_the_exported_id_depends_on_the_shown_prompt_only(self):
        a = ai_live.make_call("1" * 64, "reviewer.v1", "own log: v0001.A.r0#3", "text", template_fp="t")
        b = ai_live.make_call("2" * 64, "reviewer.v1", "own log: v0001.C.r0#3", "text", template_fp="t")
        c = ai_live.make_call("3" * 64, "reviewer.v1", "own log: v0001.C.r0#3", "text", template_fp="u")
        self.assertEqual(a["call_id"], b["call_id"])
        self.assertNotEqual(b["call_id"], c["call_id"])
        self.assertEqual(a["call_id"], ai_live.exported_id("reviewer.v1", "t", a["prompt"]))

    def test_the_handout_holds_the_pending_sets_and_the_private_folder_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = TA.small_visits(tmp, tune=2)
            self.assertEqual(TOOL.main(["run"] + TA.args(tmp, vpath, "--conditions", "A,A+", "--batch-size", "2")), TOOL.WAITING)
            live = Path(tmp) / "live"
            names = {p.name for p in (live / "handout").iterdir()}
            self.assertTrue(names <= {"pending_steps.jsonl", "pending_methods.jsonl", "pending_judge.jsonl",
                                      "pending_steps_parts", "pending_methods_parts", "pending_judge_parts"})
            self.assertTrue({"salt.private", "visit_tokens.private.json", "id_map.json"} <= {p.name for p in (live / "private").iterdir()})
            for p in (live / "handout").rglob("*.jsonl"):
                for row in ai_live._read_jsonl(p):
                    self.assertNotIn("real", row)

    def test_an_answer_by_the_exported_id_is_stored_for_every_real_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = TA.small_visits(tmp, tune=1)
            more = ["--conditions", "A,A+,B"]
            TOOL.main(["run"] + TA.args(tmp, vpath, *more))
            live = Path(tmp) / "live"
            pending = ai_live.read_pending(live)
            call = [c for c in pending.values() if c["prompt_id"].startswith("watcher")][0] if any(
                c["prompt_id"].startswith("watcher") for c in pending.values()) else list(pending.values())[0]
            out = Path(tmp) / "a.jsonl"
            TA.write_answers([call], out)
            self.assertEqual(TOOL.main(["import", str(out)] + TA.args(tmp, vpath, *more)), 0)
            self.assertEqual(set(ai_live.AnswerStore(live).answers()), set(call["real"]))


# ------------------------------------------------------------------- H2

def classify(output, prompt_id, prompt="p"):
    return ai_live.make_step_classifier(D)(output, {"prompt_id": prompt_id, "prompt": prompt})


class NarrowUnusable(unittest.TestCase):
    def test_the_rechecks_examples(self):
        ok = "FOR YOU\nI'm sorry, but the evidence is thin. The treatment may help you."
        self.assertIsNone(classify(ok, "patient_note.v1"))
        self.assertEqual(ai_live.make_candidate_test(D)(ok), "i'm sorry, but")
        self.assertIsNone(classify("**Conclusion:** Drug X probably helps [source: a:1]\n[AI-generated]", "ai_answer.v1"))
        # J1: a refusal phrase at the start makes a candidate, never an unusable answer by itself
        cand = ai_live.make_candidate_test(D)
        for text, step in (("I'm not able to write a treatment plan", "plan.v1"), ("PLAN\nI'm not able to write a treatment plan", "plan.v1"),
                           ("As an AI language model, I must decline.", "plan.v1"), ("I must decline to answer.", "ai_answer.v1")):
            self.assertIsNone(classify(text, step))
            self.assertIsNotNone(cand(text))
        self.assertEqual(classify(" ", "plan.v1"), "empty answer")
        # in the middle of a text it is not a refusal, but it is a candidate
        mid = "PLAN\nStart drug X. Unfortunately, writing more is outside what I can do."
        self.assertIsNone(classify(mid, "plan.v1"))
        self.assertEqual(ai_live.make_candidate_test(D)(mid), "outside what i can do")
        self.assertIsNone(ai_live.make_candidate_test(D)("PLAN\n" + "word " * 60 + "I cannot"))  # past 200 characters

    @needs_raw_data
    def test_through_the_run_the_files_hold_the_first_300_characters(self):
        long_refusal = "I'm not able to write this plan. " + "x" * 400

        def fn(call):
            if call["prompt_id"].startswith("plan"):
                return long_refusal
            if call["prompt_id"].startswith("patient_note"):
                return "FOR YOU\nI'm sorry, but the evidence is thin. [AI-generated]"
            return TA.helper_answer(call)

        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = TL.graded_file(tmp, 2)
            TL.drive(tmp, vpath, fn, "--conditions", "A,A+,B")
            run_dir = Path(tmp) / "runs" / "advice_tune_e2"
            # J1: nothing is unusable until a person confirms; the candidates hold the first 300 characters
            self.assertEqual(json.loads((run_dir / "unusable_visits.json").read_text(encoding="utf-8")), [])
            cands = json.loads((run_dir / "refusal_candidates.json").read_text(encoding="utf-8"))
            self.assertTrue(cands)
            self.assertTrue(all(len(x["first_300"]) == 300 for x in cands if x["step"] == "plan"))
            self.assertTrue(all(x["first_300"].startswith("FOR YOU") for x in cands if x["step"] == "patient_note"))
            self.assertTrue({x["step"] for x in cands} <= {"plan", "patient_note"})
            self.assertFalse(any(x["confirmed"] for x in cands))
            scores = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
            self.assertEqual(scores["left_out"]["visits"], 0)

    @needs_raw_data
    def test_a_visit_is_scored_only_with_all_four_conditions_in_the_run_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = TL.graded_file(tmp, 2)
            TL.drive(tmp, vpath, TA.helper_answer, "--conditions", "A,B")
            run_dir = Path(tmp) / "runs" / "advice_tune_e2"
            scores = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
            self.assertEqual(scores["left_out"]["visits"], 2)
            self.assertEqual(scores["left_out"]["by_step_and_reason"], {"run: not all methods in this run folder": 2})
            self.assertEqual(scores["attempts"], [])


# ------------------------------------------------------------------- H3

class SendLinesH3(unittest.TestCase):
    def split(self, line):
        text, reqs = steps.split_actions("a\n%s\nb" % line, D)
        return text, reqs, core.action_near_misses(text, D)

    def test_the_rechecks_examples(self):
        text, reqs, near = self.split("Send transcript to cardiology")
        self.assertEqual((text, reqs, near), ("a\nSend transcript to cardiology\nb", [], 1))
        text, reqs, near = self.split("- Send results to cardiology.")
        self.assertEqual((text, reqs, near), ("a\n- Send results to cardiology.\nb", [], 1))
        text, reqs, near = self.split("**SEND transcript TO analytics**")
        self.assertEqual((text, [(r["kind"], r["to"]) for r in reqs], near), ("a\nb", [("transcript", "analytics")], 0))
        text, reqs, near = self.split("Please send the transcript to analytics.")
        self.assertEqual((text, reqs, near), ("a\nPlease send the transcript to analytics.\nb", [], 0))

    def test_case_and_the_wiring_decide(self):
        kinds, places = core.wiring_names(D)
        self.assertIn("transcript", kinds)
        self.assertIn("analytics", places)
        self.assertEqual(core.action_line("Send Transcript to Analytics.", D), ("send", "transcript", "analytics"))
        self.assertEqual(core.action_line("send note to patient", D), ("send", "note", "patient"))
        self.assertEqual(core.action_line("SEND transcript TO nowhere", D), ("send", "transcript", "nowhere"))  # canonical: kind decides
        self.assertEqual(core.action_line("SEND results TO analytics", D)[0], "near")  # canonical, unknown kind
        self.assertEqual(core.action_line("Send transcript to cardiology", D)[0], "near")  # other case, unknown place
        text, reqs = steps.split_actions("SEND results TO analytics\nSEND transcript TO analytics", D)
        self.assertEqual((text, len(reqs)), ("SEND results TO analytics", 1))  # only the send is cut


# ------------------------------------------------------------------- H4

class FlagImport(unittest.TestCase):
    def call(self, pid):
        return {"prompt_id": pid, "prompt": ai_mod.prompt_text(pid)}

    def test_rules_the_prompt_does_not_list_and_two_flags_on_a_line_are_refused(self):
        w, r = self.call("watcher.v1"), self.call("reviewer.v1")
        self.assertEqual(watch.prompt_rules(w["prompt"]), {0, 1, 4, 5, 6})
        self.assertEqual(watch.prompt_rules(r["prompt"]), {1, 2, 3, 4, 5, 6})  # Version 2, part 3: rules 1 to 6
        watch.validate_flags_answer("FLAG 4 no tag\n- **Flag 6** no mark", w)
        watch.validate_flags_answer("NO FLAGS", r)
        for bad, call in (("FLAG 9 something", w), ("FLAG 3 record", w), ("FLAG 7 level", r),
                          ("FLAG 1, FLAG 4 leak", w), ("FLAG 1 leak; FLAG 4 no tag", w)):
            with self.assertRaises(ContractError, msg=bad):
                watch.validate_flags_answer(bad, call)

    def test_the_import_leaves_the_call_pending(self):
        call = ai_live.make_call("1" * 64, "watcher.v1", ai_mod.prompt_text("watcher.v1"), "text")
        with tempfile.TemporaryDirectory() as tmp:
            st = ai_live.AnswerStore(tmp)
            res = ai_live.import_answers(st, {call["call_id"]: call},
                                         [{"call_id": call["call_id"], "prompt_fp": call["prompt_fp"], "output": "FLAG 9 x"}],
                                         validators={"watcher.v1": watch.validate_flags_answer})
            self.assertEqual((res["stored"], len(res["refused"])), (0, 1))
            self.assertIn("does not list", res["refused"][0]["reason"])


# ------------------------------------------------------------------- H5

class WallH5(unittest.TestCase):
    def test_filing_dir_and_a_changed_visit_list_need_the_testing_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = TA.small_visits(tmp, tune=1, test=1)
            TA.file_predictions(tmp)
            more = ["--split", "all", "--conditions", "A"]
            with mock.patch.dict(os.environ):
                os.environ.pop("CUSTODY_TESTING", None)
                self.assertEqual(TOOL.main(["export"] + TA.args(tmp, vpath, *more)), 2)  # --filing-dir refused
                no_filing = [x for x in TA.args(tmp, vpath, *more) if "filing" not in x]
                i = no_filing.index("--live-dir")
                self.assertEqual(TOOL.main(["export"] + no_filing), 2)  # a visit list that is not the project's own
                self.assertFalse((Path(tmp) / "live" / "frozen.json").exists())
            self.assertEqual(TOOL.main(["export"] + TA.args(tmp, vpath, *more)), TOOL.WAITING)  # flag set: allowed

    def test_the_freeze_records_the_visit_list_and_refuses_a_changed_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = TA.small_visits(tmp, tune=1, test=1)
            TA.file_predictions(tmp)
            more = ["--split", "all", "--conditions", "A"]
            self.assertEqual(TOOL.main(["export"] + TA.args(tmp, vpath, *more)), TOOL.WAITING)
            fz = json.loads((Path(tmp) / "live" / "frozen.json").read_text(encoding="utf-8"))
            self.assertIn("visits", fz["fingerprints"])
            vpath.write_text(vpath.read_text(encoding="utf-8") + "\n", encoding="utf-8")  # the list changed
            self.assertEqual(TOOL.main(["export"] + TA.args(tmp, vpath, *more)), 2)
            self.assertEqual(TOOL.main(["export"] + TA.args(tmp, vpath, *more, "--after-freeze-change", "list rebuilt")), TOOL.WAITING)
            fz = json.loads((Path(tmp) / "live" / "frozen.json").read_text(encoding="utf-8"))
            self.assertEqual(fz["changes_after_freeze"][-1]["changed"], ["visits"])


# ------------------------------------------------------------------- H6

def two_texts(a, b, grade="low"):
    visit = {"visit_id": "v1", "expert_certainty": grade, "given_answer": None, "given_by": None,
             "evidence": [{"source_id": "pmid:1"}]}
    rows = [{"run_id": "v1.A.r0", "t": 10, "item": {"item_id": "p" * 16, "visit_id": "v1", "kind": "answer", "text": a,
                                                      "made_by": "s", "parents": []}},
            {"run_id": "v1.A.r0", "t": 11, "item": {"item_id": "q" * 16, "visit_id": "v1", "kind": "plan", "text": b,
                                                      "made_by": "s", "parents": ["p" * 16]}}]
    return rows, visit


HIGH_TEXT = "Claim: The treatment reduces the outcome. [source: pmid:1]\n[AI-generated]"
LOW_TEXT = "Claim: The treatment may reduce the outcome. [source: pmid:1]\n[AI-generated]"
NO_CLAIM = "The treatment helps a little. [source: pmid:1]\n[AI-generated]"


class CertaintyLevels(unittest.TestCase):
    def test_a_claim_line_behind_a_list_number_or_bullet_is_read(self):
        for line in ("1. **Claim**: X may help.", "2) Claim: X may help.", "- 3. **Claim:** X may help.",
                     "• Claim: X may help."):
            self.assertEqual(core.claim_line(line, D).strip(" *"), "X may help.", line)
            self.assertEqual(core.claim_level(line, D), "low", line)
        self.assertIsNone(core.claim_line("Our claim: X may help.", D))
        self.assertEqual(core.claim_line_count("1. Claim: a\n2. Claim: b", D), 2)

    def test_under_judge_all_one_instrument_reads_both_texts_of_a_pair(self):
        rows, visit = two_texts(HIGH_TEXT, LOW_TEXT)  # the reader reads high, then low
        self.assertEqual((core.claim_level(HIGH_TEXT, D), core.claim_level(LOW_TEXT, D)), ("high", "low"))
        same = {("p" * 16, 5): "low", ("q" * 16, 5): "low"}
        diff = {("p" * 16, 5): "low", ("q" * 16, 5): "high"}
        f = score.text_facts(rows, visit, D, {}, same, "reader_first")[5]
        self.assertTrue(f["broken"])  # the reader's own levels differ
        f = score.text_facts(rows, visit, D, {}, same, "judge_all")[5]
        self.assertEqual((f["broken"], f["unknown"]), (False, False))  # kept: the judge reads both as low
        f = score.text_facts(rows, visit, D, {}, diff, "judge_all")[5]
        self.assertTrue(f["broken"])
        f = score.text_facts(rows, visit, D, {}, {("p" * 16, 5): "low"}, "judge_all")[5]
        self.assertEqual((f["broken"], f["unknown"]), (False, True))  # no judge row for the child: unknown

    def test_the_comparison_table_counts_a_planted_disagreement(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TS.Store(tmp)
            s.visit("v1", "c1", "tune", grade="low")
            s.run("v1", "c1", "tune", "A", texts=[("answer", HIGH_TEXT), ("plan", LOW_TEXT), ("patient_note", NO_CLAIM)])
            s.write()
            judge_rows = [{"visit_id": "v1", "item_id": "v1.A.r0-%s" % k, "rule": 5, "verdict": "kept", "judge": "live",
                           "prompt_id": "judge.v1", "level": lv}
                          for k, lv in (("answer", "low"), ("plan", "low"), ("patient_note", "moderate"))]
            judge_rows += [{"visit_id": "v1", "item_id": "v1.A.r0-patient_note", "rule": 4, "verdict": "kept",
                            "judge": "live", "prompt_id": "judge.v1"}]
            (Path(tmp) / "judge.jsonl").write_text("".join(canon(r) + "\n" for r in judge_rows), encoding="utf-8")
            for source in ("reader_first", "judge_all"):
                res = score.score_run(tmp, W, D, None, source)
                t = res["reader_vs_judge"]
                self.assertEqual(t["answer"], {"same": 0, "reader_higher": 1, "reader_lower": 0,
                                               "reader_could_not_read": 0, "judge_none": 0}, source)
                self.assertEqual(t["plan"]["same"], 1)
                self.assertEqual(t["patient_note"]["reader_could_not_read"], 1)
                self.assertEqual(res["level_source"], source)
                self.assertEqual(res["header"]["level_source"], source)

    def test_the_entry_comparison_uses_the_judge_level_under_judge_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TS.Store(tmp)
            s.visit("v1", "c1", "test", grade="low")
            s.run("v1", "c1", "test", "A", texts=[("answer", HIGH_TEXT), ("plan", LOW_TEXT)])
            s.write()
            judge_rows = [{"visit_id": "v1", "item_id": "v1.A.r0-%s" % k, "rule": 5, "verdict": "kept", "judge": "live",
                           "prompt_id": "judge.v1", "level": "low"} for k in ("answer", "plan")]
            (Path(tmp) / "judge.jsonl").write_text("".join(canon(r) + "\n" for r in judge_rows), encoding="utf-8")
            ent = score.score_run(tmp, W, D, None, "reader_first")["certainty_change_test"]["A"]["entry_error"]
            self.assertEqual(ent["hardened"], 1)  # the reader says high against the grade low
            ent = score.score_run(tmp, W, D, None, "judge_all")["certainty_change_test"]["A"]["entry_error"]
            self.assertEqual((ent["same"], ent["hardened"]), (1, 0))

    def test_the_manifest_records_the_choice_and_the_scorer_follows_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TS.Store(tmp)
            s.visit("v1", "c1", "tune", grade="low")
            s.run("v1", "c1", "tune", "A", texts=[("answer", HIGH_TEXT)])
            s.write()
            store.write_manifest(tmp, "x", {}, ["A"], {}, {}, level_source="judge_all")
            self.assertEqual(json.loads((Path(tmp) / "manifest.json").read_text(encoding="utf-8"))["level_source"], "judge_all")
            self.assertEqual(score.score_run(tmp, W, D)["level_source"], "judge_all")
            with self.assertRaises(ValueError):
                store.write_manifest(tmp, "x", {}, ["A"], {}, {}, level_source="both")

    @needs_raw_data
    def test_the_tool_under_judge_all_asks_for_every_advice_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = TL.graded_file(tmp, 2)
            TA.round_trip(tmp, vpath, "--conditions", "A,A+,B", "--levels", "judge_all")
            run_dir = Path(tmp) / "runs" / "advice_tune_e2"
            man = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(man["level_source"], "judge_all")
            texts = store.read_jsonl(run_dir / "texts.jsonl")
            advice = {t["item"]["item_id"] for t in texts if t["item"]["kind"] in D["rules"]["advice_kinds"]}
            jrows = store.read_jsonl(run_dir / "judge.jsonl")
            rule5 = {r["item_id"] for r in jrows if r["rule"] == 5}
            self.assertEqual(rule5, advice)
            self.assertTrue(all("reader_level" in r for r in jrows if r["rule"] == 5))
            scores = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
            self.assertEqual(scores["header"]["level_source"], "judge_all")
            self.assertTrue((run_dir / "judge_sample.jsonl").exists() or not advice)  # a tuning run has a sample


# ------------------------------------------------------------------- H7

class JudgePartsPerRule(unittest.TestCase):
    @needs_raw_data
    def test_one_part_holds_one_rule_only_and_the_seeded_order_stays_inside_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = TL.graded_file(tmp, 4)
            more = ["--conditions", "A", "--batch-size", "3"]
            for n in range(25):
                if TOOL.main(["run"] + TA.args(tmp, vpath, *more)) == 0:
                    break
                live = Path(tmp) / "live"
                if (live / "handout" / "pending_judge.jsonl").exists():
                    break
                pending = ai_live.read_pending(live)
                out = Path(tmp) / ("a%d.jsonl" % n)
                TA.write_answers(list(pending.values()), out)
                TOOL.main(["import", str(out)] + TA.args(tmp, vpath, *more))
            parts = sorted((live / "handout" / "pending_judge_parts").glob("part_*.jsonl"))
            self.assertTrue(parts)
            whole = [r["call_id"] for r in ai_live._read_jsonl(live / "handout" / "pending_judge.jsonl")]
            seen_rules, in_parts = set(), []
            for p in parts:
                rows = ai_live._read_jsonl(p)
                rules = {judge.rule_of_prompt(r["prompt"], D) for r in rows}
                self.assertEqual(len(rules), 1, p.name)
                self.assertIn("_r%d_" % rules.copy().pop(), "_%s_" % p.stem.split("_")[1])
                seen_rules |= rules
                in_parts += [r["call_id"] for r in rows]
            self.assertTrue(len(seen_rules) >= 2)
            self.assertEqual(sorted(in_parts), sorted(whole))
            for rule in seen_rules:  # inside a rule the parts keep the order of the seeded file
                rows = [c for c in whole if c in {r for p in parts if "_r%d_" % rule in p.name
                                                 for r in [x["call_id"] for x in ai_live._read_jsonl(p)]}]
                flat = [x["call_id"] for p in parts if "_r%d_" % rule in p.name for x in ai_live._read_jsonl(p)]
                self.assertEqual(sorted(rows), sorted(flat))  # a part holds no two calls of one case, so the order may shift
