"""Tests for Version 2, part 3 (13 Nov): the review asked about six rules, the monitor shown the previous advice,
the switch for the AI parts, the part on every signal, the judge on every advice text, parts with no two calls of
one case, and the models. No model is called; they write only to temporary folders."""
import json
import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import ai as ai_mod, ai_live, judge, watch  # noqa: E402
from custody.core import Handover, Item, Signal  # noqa: E402

D = json.loads((ROOT / "config" / "design_choices.json").read_text(encoding="utf-8"))
W = json.loads((ROOT / "wiring" / "wiring.json").read_text(encoding="utf-8"))
HOLD = D["holds"]["in_visit"]
ADVICE = "Claim: X probably reduces Y [source: pmid:1]\n[AI-generated]"


class Recorder:
    """An AI that records every call and answers with a fixed reply."""

    def __init__(self, reply="NO FLAGS"):
        self.calls, self.reply = [], reply

    def __call__(self, prompt_id, fields):
        self.calls.append((prompt_id, dict(fields)))
        return self.reply


def line(t, action, **kw):
    base = {"t": t, "step": "s", "action": action, "kind": "transcript", "from": None, "to": None,
            "item_ids": ["i1"], "handover_id": "v0001.A.r0#%d" % t}
    base.update(kw)
    return base


class Review(unittest.TestCase):
    def test_prompt_asks_about_all_six_rules_and_has_the_new_field(self):
        text = ai_mod.prompt_text(D["prompts"]["reviewer"])
        self.assertEqual(watch.prompt_rules(text), {1, 2, 3, 4, 5, 6})
        self.assertIn("{{ai_answer}}", text)
        self.assertIn("{{note}}", text)
        self.assertIn("contradicts itself", text)
        self.assertIn("another certainty than the evidence tool's answer", text)
        self.assertIn("ai_answer", D["prompts"]["fields"]["reviewer"])

    def test_the_ai_gets_the_answer_and_empty_fields_read_none_in_this_flow(self):
        ai = Recorder()
        watch.review([line(1, "send", to="note_writer", **{"from": "transcriber"})],
                     {"note": "VISIT NOTE", "patient_note": None}, W, D, ai, "v0001.A.r0")
        fields = ai.calls[0][1]
        self.assertEqual(fields["ai_answer"], "(none in this flow)")
        self.assertEqual(fields["patient_note"], "(none in this flow)")
        self.assertEqual(fields["note"], "VISIT NOTE")
        ai = Recorder()
        watch.review([], {"note": None, "patient_note": ADVICE, "ai_answer": "THE ANSWER"}, W, D, ai, "v0001.A.r0")
        fields = ai.calls[0][1]
        self.assertEqual((fields["note"], fields["ai_answer"]), ("(none in this flow)", "THE ANSWER"))
        # every slot of the prompt can be filled
        ai_mod.render_prompt(D["prompts"]["reviewer"], fields)

    def test_the_ai_part_may_flag_rules_one_to_six_and_says_so(self):
        ai = Recorder("FLAG 3 the log contradicts the note\nFLAG 5 the note is surer than the answer\nFLAG 1 odd")
        sigs = watch.review([], {"note": None, "patient_note": ADVICE}, W, D, ai, "v0001.A.r0")
        ai_sigs = [s for s in sigs if s.part == "ai"]
        self.assertEqual(sorted(s.rule for s in ai_sigs), [1, 3, 5])
        self.assertTrue(all(s.by == "review" for s in ai_sigs))

    def test_program_flags_say_program(self):
        sigs = watch.review([], {"note": None, "patient_note": "no tag, no mark"}, W, D, Recorder(), "v0001.A.r0")
        self.assertEqual(sorted(s.rule for s in sigs), [4, 6])
        self.assertTrue(all(s.part == "program" for s in sigs))

    def test_an_intake_entry_is_an_arrival_in_the_rule_2_scan(self):
        intake = {"t": 0, "action": "intake", "kind": "transcript", "place": "transcriber", "item": "i1"}
        sigs = watch.review([intake], {}, W, D, Recorder(), "v0001.A.r0")
        self.assertEqual([(s.rule, s.item_ids, s.part) for s in sigs if s.rule == 2], [(2, ["i1"], "program")])
        late = line(HOLD + 1, "delete", **{"from": "transcriber"})
        self.assertEqual(len([s for s in watch.review([intake, late], {}, W, D, Recorder(), "r") if s.rule == 2]), 1)
        ok = line(HOLD, "delete", **{"from": "transcriber"})
        self.assertEqual([s for s in watch.review([intake, ok], {}, W, D, Recorder(), "r") if s.rule == 2], [])
        # an intake carrying item_ids works too, and an intake to a place with no hold flags nothing
        two = {"t": 0, "action": "intake", "kind": "transcript", "place": "transcriber", "item_ids": ["a", "b"]}
        self.assertEqual([s.item_ids for s in watch.review([two], {}, W, D, Recorder(), "r") if s.rule == 2], [["a", "b"]])

    def test_a_log_without_intake_entries_still_works(self):
        log = [line(1, "send", to="note_writer", **{"from": "transcriber"})]
        sigs = watch.review(log, {}, W, D, Recorder(), "v0001.A.r0")
        # two copies with no logged delete: the one sent to the note service and, since 13 Nov, the sender's own
        # copy at the transcriber, whose arrival this log does not show
        self.assertEqual([s.rule for s in sigs if s.rule == 2], [2, 2])


class SwitchAndPart(unittest.TestCase):
    def test_default_is_on_and_off_makes_no_ai_call(self):
        self.assertTrue(watch.ai_parts_on(D))
        off = watch.ai_parts_off(D)
        self.assertFalse(watch.ai_parts_on(off))
        self.assertTrue(watch.ai_parts_on(D), "the original choices are unchanged")
        ai = Recorder("FLAG 1 x")
        sigs = watch.review([line(1, "send", to="note_writer", **{"from": "transcriber"})],
                            {"note": "n", "patient_note": "no tag"}, W, off, ai, "r")
        self.assertEqual(ai.calls, [])
        self.assertTrue(sigs and all(s.part == "program" for s in sigs))

    def test_the_signal_keeps_its_part_and_old_rows_still_load(self):
        s = Signal("r", 1, 1, "flag", "gate", None, [], "x")
        self.assertEqual(s.part, "program")
        row = asdict(Signal("r", 1, 1, "flag", "review", None, [], "x", part="ai"))
        self.assertEqual(row["part"], "ai")
        old = {k: v for k, v in row.items() if k != "part"}
        self.assertEqual(Signal(**old).part, "program")


class Monitor(unittest.TestCase):
    def handover(self, n, kind="answer", to="analytics"):
        return Handover("r#%d" % n, "r", n, "send", "s", "a", to, kind, ["i%d" % n], None)

    def item(self, n, text):
        return Item("i%d" % n, "v0001", "answer", text, "ai", [])

    def test_the_second_advice_text_is_shown_the_first(self):
        ai = Recorder()
        w = watch.Watcher(W, D, ai, "r")
        w.look(self.handover(1), [self.item(1, ADVICE)])
        w.look(self.handover(2), [self.item(2, ADVICE + "\nmore")])
        self.assertEqual(ai.calls[0][1]["previous_advice"], "(none: this is the first advice text)")
        self.assertEqual(ai.calls[1][1]["previous_advice"], ADVICE)
        ai_mod.render_prompt(D["prompts"]["watcher"], ai.calls[1][1])

    def test_watcher_flags_say_which_part(self):
        ai = Recorder("FLAG 5 the certainty moved")
        w = watch.Watcher(W, D, ai, "r")
        sigs = w.look(self.handover(1), [self.item(1, "plain text")])
        self.assertEqual({(s.rule, s.part) for s in sigs}, {(1, "program"), (4, "program"), (6, "program"), (5, "ai")})
        off = watch.Watcher(W, watch.ai_parts_off(D), Recorder("FLAG 5 x"), "r")
        sigs = off.look(self.handover(1), [self.item(1, "plain text")])
        self.assertTrue(sigs and all(s.part == "program" for s in sigs))

    def test_the_prompt_no_longer_speaks_of_advice_never_shown(self):
        text = ai_mod.prompt_text(D["prompts"]["watcher"])
        self.assertNotIn("you saw before", text)
        self.assertIn("{{previous_advice}}", text)


class JudgeKey(unittest.TestCase):
    def setup_rows(self):
        visit = {"visit_id": "v0001", "split": "test", "expert_certainty": "moderate", "evidence": [
            {"source_id": "pmid:1"}], "given_answer": None}
        texts = [{"item": {"visit_id": "v0001", "item_id": "i%d" % n, "kind": k, "text": ADVICE}}
                 for n, k in enumerate(("answer", "plan", "patient_note"))]
        texts.append({"item": {"visit_id": "v0001", "item_id": "n0", "kind": "note", "text": "a visit note"}})
        return texts, {"v0001": visit}

    def test_default_is_judge_and_every_advice_text_gets_all_three_rules(self):
        self.assertEqual(D["rules"]["key_source"], "judge")
        texts, vmap = self.setup_rows()
        jobs = judge.build_jobs(texts, vmap, D)
        self.assertEqual(sorted((j["item_id"], j["rule"]) for j in jobs),
                         sorted((i, r) for i in ("i0", "i1", "i2") for r in (4, 5, 6)))
        self.assertEqual(judge.build_jobs(texts, vmap, D, key_source="readers"), [], "the readers read these texts")

    def test_level_source_still_works(self):
        texts, vmap = self.setup_rows()
        jobs = judge.build_jobs(texts, vmap, D, level_source="judge_all", key_source="readers")
        self.assertEqual({j["rule"] for j in jobs}, {5})

    def test_an_ungraded_case_is_still_asked_for_rule_5(self):
        texts, vmap = self.setup_rows()
        vmap["v0001"]["expert_certainty"] = None
        jobs = judge.build_jobs(texts, vmap, D)
        self.assertEqual(len([j for j in jobs if j["rule"] == 5]), 3)

    def test_the_prompt_does_not_say_why_the_text_was_handed_over(self):
        text = ai_mod.prompt_text(D["prompts"]["judge"])
        self.assertNotIn("handed to you", text)
        self.assertNotIn("may not follow", text)
        for rule in (4, 5, 6):
            q = judge.rule_text(rule, D)
            for hint in ("with no source tag", "with no claim line", "with no AI mark"):
                self.assertNotIn(hint, q)
        texts, vmap = self.setup_rows()
        job = judge.build_jobs(texts, vmap, D)[0]
        ai_mod.render_prompt(D["prompts"]["judge"], judge.judge_fields(job, D))

    def test_judge_rows_are_made_and_the_case_is_announced(self):
        texts, vmap = self.setup_rows()
        jobs = judge.build_jobs(texts, vmap, D)
        seen = []

        def ai(prompt_id, fields):
            m = fields["rule"][5]
            return {"4": "VERDICT kept", "5": "LEVEL moderate", "6": "VERDICT kept"}[m]
        ai.set_case = seen.append
        rows = judge.judge_jobs(ai, jobs, D)
        self.assertEqual(len(rows), 9)
        self.assertEqual(set(seen), {"v0001", None})

    def test_the_judge_model_is_opus(self):
        self.assertEqual(D["live"]["terminal"]["models"], {"steps": "claude-haiku-5-5", "methods": "claude-sonnet-5-5",
                                                                "judge": "claude-opus-5-5"})


class Parts(unittest.TestCase):
    def calls(self):
        out = []
        for n in range(12):
            out.append({"call_id": "c%02d" % n, "also": [], "real": ["r%02d" % n], "prompt_id": "judge.v1",
                        "prompt": "p%d" % n, "prompt_fp": "f%d" % n, "expects": "verdict", "cases": ["v%04d" % (n % 4)]})
        return out

    def test_no_part_holds_two_calls_of_one_case_and_the_order_is_kept(self):
        parts = ai_live.split_parts(self.calls(), 5)
        for part in parts:
            cases = [c["cases"][0] for c in part]
            self.assertEqual(len(cases), len(set(cases)))
            self.assertLessEqual(len(part), 5)
        flat = [c["call_id"] for p in parts for c in p]
        self.assertEqual(sorted(flat), ["c%02d" % n for n in range(12)])
        self.assertEqual([c["call_id"] for c in parts[0]], ["c00", "c01", "c02", "c03"])  # smaller than 5

    def test_calls_with_no_known_case_are_not_held_back(self):
        calls = [{"call_id": str(n)} for n in range(7)]
        self.assertEqual([len(p) for p in ai_live.split_parts(calls, 3)], [3, 3, 1])

    def test_export_sets_applies_it_to_all_three_sets_and_hides_cases(self):
        by_set = {s: [dict(c, call_id="%s%s" % (s[0], c["call_id"]), prompt_id=s) for c in self.calls()] for s in ai_live.SETS}
        with tempfile.TemporaryDirectory() as tmp:
            ai_live.export_sets(tmp, by_set, 7, 6)
            for s in ai_live.SETS:
                files = sorted((Path(tmp) / "handout" / ai_live.parts_name(s)).glob("part_*.jsonl"))
                self.assertTrue(files)
                n = 0
                for f in files:
                    rows = ai_live._read_jsonl(f)
                    n += len(rows)
                    self.assertTrue(all("cases" not in r and "real" not in r for r in rows))
                    prompts = [r["prompt"] for r in rows]
                    cases = [int(p[1:]) % 4 for p in prompts]
                    self.assertEqual(len(cases), len(set(cases)), f.name)
                self.assertEqual(n, 12)

    def test_the_case_is_taken_from_the_announcement_and_from_a_visit_id_in_the_prompt(self):
        col = ai_live.Collector()
        ai = ai_live.discovering_ai({}, col, lambda pid, f: "prompt %s" % f["x"], lambda pid, f: "id" + f["x"],
                                    placeholder_for={"p": ""})
        ai.set_case("v0007")
        ai("p", {"x": "a"})
        ai.set_case(None)
        ai("p", {"x": "log v0009.A.r0#3"})
        rows = {c["prompt"]: c for c in col.rows()}
        self.assertEqual(rows["prompt a"]["cases"], ["v0007"])
        self.assertEqual(rows["prompt log v0009.X.r0#3"]["cases"], ["v0009"])


if __name__ == "__main__":
    unittest.main()
