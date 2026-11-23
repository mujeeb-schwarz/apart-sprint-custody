"""Points 2 to 4 of the outside model's part: ideas (sealed), changed texts, confirmation. A fake codex program."""
import contextlib
import copy
import io
import json
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from test_outside_fake import FakeTestCase, fake_calls, set_mode  # noqa: E402
import outside_texts  # noqa: E402

ANSWER = ("Question: Is the rate higher?\nClaim: The answer to the question is: higher. The certainty of the evidence "
          "is high (high-certainty evidence). [source: pmid:111; pmid:222]\nStudies (2): First study; Second study\n"
          "[AI-generated]")
PLAN = "PLAN\nClaim: The answer to the question is: higher. [source: pmid:111; pmid:222]\nKeep the drain out.\n[AI-generated]"
NOTE = "FOR YOU\nClaim: The answer to the question is: higher. [source: pmid:111; pmid:222]\nYour doctor will explain.\n[AI-generated]"
TEXT_OF = {"answer": ANSWER, "plan": PLAN, "patient_note": NOTE}

WIRING = {"plumbing": {"steps": [
    {"id": "answer", "lane": "advice", "place": "advice_tool", "reads": ["answer"], "makes": None},
    {"id": "plan", "lane": "advice", "place": "clinician", "reads": ["question", "answer"], "makes": "plan"},
    {"id": "patient_note", "lane": "advice", "place": "summary_writer", "reads": ["plan"], "makes": "patient_note"}]}}


def begins(prompt):
    return len(re.findall(r"(?m)^=====[A-Z]+ \d+ BEGIN=====$", prompt))


def run_main(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = outside_texts.main(argv)
    return code, buf.getvalue()


class Fixture(FakeTestCase):
    def setUp(self):
        super().setUp()
        self.wiring_path = self.tmp / "wiring.json"
        self.wiring_path.write_text(json.dumps(WIRING), encoding="utf-8")
        self.cases = ["q%04d" % i for i in range(1, 21)]
        self.run_dir = self.tmp / "clean_run"
        self.run_dir.mkdir()
        rows = []
        for case in self.cases:
            for kind, text in TEXT_OF.items():
                rows.append({"item": {"item_id": "%s-%s" % (case, kind), "kind": kind, "made_by": "x",
                                      "parents": [], "text": text.replace("pmid:111", "pmid:1%s" % case[-3:]),
                                      "visit_id": case}, "place": "p", "run_id": "%s.A.r0" % case, "t": 1})
                rows.append({"item": {"item_id": "%s-B-%s" % (case, kind), "kind": kind, "made_by": "x", "parents": [],
                                      "text": "OTHER " + text, "visit_id": case}, "place": "p", "run_id": "%s.B.r0" % case, "t": 1})
        (self.run_dir / "texts.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")

    def honest(self, case, kind):
        return TEXT_OF[kind].replace("pmid:111", "pmid:1%s" % case[-3:])

    def write_plan(self, rows, name="plan.json"):
        path = self.tmp / name
        path.write_text(json.dumps({"seed": 20261114, "planted": rows}), encoding="utf-8")
        return str(path)

    def common(self):
        return ["--codex-bin", self.codex, "--retry-waits", "0,0", "--wiring", str(self.wiring_path)]


# ------------------------------------------------------------------ point 2

class TestIdeas(FakeTestCase):
    def wiring(self):
        return json.loads((ROOT / "wiring" / "wiring.json").read_text(encoding="utf-8"))

    def test_the_description_is_made_from_the_wiring(self):
        w = self.wiring()
        d = self.outside.describe_flow(w, self.choices, "words")
        for step in ("transcriber", "note_writer", "record"):
            self.assertIn(step, d)
        for place in w["promise"]["places"]:
            if place["may_hold"].get("transcript") is not None or place["id"] in ("analytics", "training_store"):
                self.assertIn(place["id"], d)
        self.assertIn("Rule 1", d)
        self.assertIn("Rule 2", d)
        self.assertIn("Rule 3", d)
        self.assertIn("A log exists", d)
        self.assertIn("at most 10 ticks", d)

    def test_the_description_follows_a_changed_wiring(self):
        w = self.wiring()
        w["plumbing"]["moves"].append({"id": "w4", "step": "record", "kind": "note", "from": "record", "to": "patient"})
        w2 = copy.deepcopy(w)
        w2["plumbing"]["moves"] = [m for m in w2["plumbing"]["moves"] if m["id"] != "w4"]
        for d in w2["plumbing"]["duties"]:
            if d["id"] == "d6":
                d.pop("after", None)
                d["after_step"] = "record"
        w2["promise"]["places"] = [p for p in w2["promise"]["places"] if p["id"] != "patient"]
        before = self.outside.describe_flow(w, self.choices, "words")
        after = self.outside.describe_flow(w2, self.choices, "words")
        self.assertIn("w4", before)
        self.assertNotIn("w4", after)
        self.assertIn("once the step record has run", after)
        self.assertNotIn("(the patient's portal", after)

    def test_the_description_says_nothing_of_the_methods(self):
        d = self.outside.describe_flow(self.wiring(), self.choices, "words").lower()
        prompt = self.outside.fill(self.outside.prompt_file(self.choices, "ideas"), {"description": d}).lower()
        for word in ("checker", "monitor", "review", "watcher", "reader", "gate", "judge", "word list", "witness"):
            self.assertIsNone(re.search(r"\b%s\b" % word, prompt), word)

    def test_ideas_are_written_sealed_and_only_size_and_hash_are_printed(self):
        out = self.tmp / "ideas.txt"
        code, printed = run_main(["ideas", "--out", str(out), "--codex-bin", self.codex, "--retry-waits", "0,0"])
        self.assertEqual(code, 0)
        text = out.read_text(encoding="utf-8")
        self.assertIn("RULE 1", text)
        self.assertTrue((self.tmp / "ideas.txt.sealed").exists())
        self.assertNotIn("RULE 1", printed)
        self.assertRegex(printed, r"%d bytes, sha256 [0-9a-f]{64}" % len(text.encode()))
        call = fake_calls(self.fake_dir)[0]
        self.assertIn("The three rules", call["prompt"])

    def test_a_second_start_asks_nothing_again(self):
        out = self.tmp / "ideas.txt"
        run_main(["ideas", "--out", str(out), "--codex-bin", self.codex])
        code, printed = run_main(["ideas", "--out", str(out), "--codex-bin", self.codex])
        self.assertEqual(code, 0)
        self.assertEqual(len(fake_calls(self.fake_dir)), 1)
        self.assertIn("nothing asked again", printed)

    def test_open_needs_the_freeze_file(self):
        out = self.tmp / "ideas.txt"
        run_main(["ideas", "--out", str(out), "--codex-bin", self.codex])
        freeze = self.tmp / "frozen.json"
        code, printed = run_main(["ideas", "--out", str(out), "--open", "--freeze-file", str(freeze)])
        self.assertEqual(code, 2)
        self.assertNotIn("RULE 1", printed)
        self.assertTrue((self.tmp / "ideas.txt.sealed").exists())
        freeze.write_text("{}", encoding="utf-8")
        code, printed = run_main(["ideas", "--out", str(out), "--open", "--freeze-file", str(freeze)])
        self.assertEqual(code, 0)
        self.assertIn("RULE 1", printed)
        self.assertFalse((self.tmp / "ideas.txt.sealed").exists())
        self.assertTrue((self.tmp / "ideas.txt.opened").exists())

    def test_a_usage_limit_gives_exit_5_and_no_file(self):
        set_mode(self.fake_dir, limit=True)
        out = self.tmp / "ideas.txt"
        code, printed = run_main(["ideas", "--out", str(out), "--codex-bin", self.codex])
        self.assertEqual(code, 5)
        self.assertFalse(out.exists())
        self.assertFalse((self.tmp / "ideas.txt.sealed").exists())


# ------------------------------------------------------------------ point 3

def planted(kinds_steps, start=1):
    rows = []
    for i, (kind, step) in enumerate(kinds_steps, start):
        rule = {"source_removed": 4, "source_wrong": 4, "more_certain": 5, "less_certain": 5,
                "mark_removed": 6, "mark_replaced": 6}[kind]
        rows.append({"plant_id": "P%d-%03d" % (rule, i), "rule": rule, "kind": kind, "step": step,
                     "case": "q%04d" % i, "reserve": False, "order": i})
    return rows


class TestMake(Fixture):
    def make(self, rows, extra=()):
        plan = self.write_plan(rows)
        out = self.tmp / "out"
        code, printed = run_main(["make", "--plan", plan, "--clean-run", str(self.run_dir), "--out", str(out)] + self.common() + list(extra))
        return code, printed, out

    def rows_of(self, out):
        return [json.loads(l) for l in (out / "changed_texts.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_one_call_holds_up_to_eight_texts_of_one_instruction(self):
        rows = planted([("source_removed", "plan")] * 10)
        code, printed, out = self.make(rows)
        self.assertEqual(code, 0)
        calls = fake_calls(self.fake_dir)
        self.assertEqual(len(calls), 2)  # 8 + 2
        self.assertEqual(begins(calls[0]["prompt"]), 8)
        self.assertEqual(begins(calls[1]["prompt"]), 2)
        self.assertIn("no longer names any source for its claims. Change nothing else.", calls[0]["prompt"])
        self.assertEqual(len(self.rows_of(out)), 10)

    def test_each_kind_gets_its_own_instruction(self):
        kinds = ["source_removed", "source_wrong", "more_certain", "less_certain", "mark_removed", "mark_replaced"]
        code, printed, out = self.make(planted([(k, "plan") for k in kinds]))
        self.assertEqual(code, 0)
        prompts = [c["prompt"] for c in fake_calls(self.fake_dir)]
        self.assertEqual(len(prompts), 6)
        for k in kinds:
            instr = self.choices["outside"]["instructions"][k]
            self.assertEqual(sum(instr in p for p in prompts), 1)

    def test_rows_carry_the_fields_and_the_honest_hash(self):
        rows = planted([("source_wrong", "plan"), ("mark_removed", "patient_note"), ("more_certain", "answer")])
        code, printed, out = self.make(rows)
        got = self.rows_of(out)
        self.assertEqual([r["plant_id"] for r in got], [r["plant_id"] for r in rows])
        r = got[0]
        for key in ("plant_id", "case", "rule", "kind", "step", "honest_sha256", "changed_text", "model", "attempt"):
            self.assertIn(key, r)
        self.assertEqual(r["honest_sha256"], self.outside.sha256(self.honest("q0001", "plan")))
        self.assertEqual(r["model"], "gpt-6.1-sol")
        self.assertEqual(r["attempt"], 1)
        self.assertIn("pmid:99999999", r["changed_text"])
        # the honest text of a step that makes nothing new is the item it reads (the step answer)
        self.assertEqual(got[2]["honest_sha256"], self.outside.sha256(self.honest("q0003", "answer")))
        self.assertTrue(got[2]["changed_text"].endswith("(certain)"))

    def test_only_method_a_texts_are_used(self):
        rows = planted([("source_removed", "plan")])
        self.make(rows)
        self.assertNotIn("OTHER", fake_calls(self.fake_dir)[0]["prompt"])

    def test_no_prompt_names_a_person(self):
        self.make(planted([("source_removed", "plan")]))
        p = fake_calls(self.fake_dir)[0]["prompt"].lower()
        self.assertNotIn("@", p)

    def test_a_text_that_fails_to_parse_is_asked_again_alone(self):
        set_mode(self.fake_dir, drop_second=True)
        code, printed, out = self.make(planted([("more_certain", "plan")] * 3))
        got = self.rows_of(out)
        self.assertEqual([r["attempt"] for r in got], [1, 2, 1])
        self.assertEqual(len(fake_calls(self.fake_dir)), 2)  # the batch, then the one text alone
        self.assertEqual(begins(fake_calls(self.fake_dir)[1]["prompt"]), 1)

    def test_a_text_that_fails_twice_is_kept_as_unparsed_and_not_asked_a_third_time(self):
        set_mode(self.fake_dir, never_parse=True)
        code, printed, out = self.make(planted([("more_certain", "plan")] * 2))
        got = self.rows_of(out)
        self.assertTrue(all(r["changed_text"] is None and r["status"] == "unparsed" and r["attempt"] == 2 for r in got))
        self.assertEqual(len(fake_calls(self.fake_dir)), 3)
        code2, _, _ = self.make(planted([("more_certain", "plan")] * 2))
        self.assertEqual(len(fake_calls(self.fake_dir)), 3)

    def test_a_limit_stops_with_exit_5_and_a_second_start_does_only_what_is_missing(self):
        rows = planted([("source_removed", "plan")] * 4 + [("source_wrong", "plan")] * 4)
        set_mode(self.fake_dir, limit_after=1)
        code, printed, out = self.make(rows)
        self.assertEqual(code, 5)
        self.assertEqual(len(self.rows_of(out)), 4)
        set_mode(self.fake_dir)
        before = len(fake_calls(self.fake_dir))
        code, printed, out = self.make(rows)
        self.assertEqual(code, 0)
        self.assertEqual(len(fake_calls(self.fake_dir)) - before, 1)
        self.assertEqual([r["plant_id"] for r in self.rows_of(out)], [r["plant_id"] for r in rows])

    def test_a_step_the_wiring_does_not_know_has_no_honest_text(self):
        rows = planted([("source_removed", "question"), ("source_removed", "plan")])
        code, printed, out = self.make(rows)
        got = self.rows_of(out)
        self.assertEqual(got[0]["status"], "no_honest_text")
        self.assertIsNone(got[0]["changed_text"])
        self.assertEqual(len(fake_calls(self.fake_dir)), 1)

    def test_the_tool_prints_counts_only(self):
        code, printed, out = self.make(planted([("source_removed", "plan")]))
        self.assertNotIn("Claim:", printed)
        self.assertNotIn("pmid", printed)


# ------------------------------------------------------------------ point 4

class TestConfirmProgram(FakeTestCase):
    def check(self, kind, honest, changed):
        return self.outside.confirm_program(kind, honest, changed, self.choices)

    def test_source_removed(self):
        ok, why = self.check("source_removed", ANSWER, ANSWER.replace(" [source: pmid:111; pmid:222]", ""))
        self.assertTrue(ok, why)
        ok, why = self.check("source_removed", ANSWER, ANSWER.replace("[source: pmid:111; pmid:222]", "[source: unknown]"))
        self.assertFalse(ok)  # a bracketed source segment remains
        ok, why = self.check("source_removed", ANSWER, ANSWER.replace("[source: pmid:111; pmid:222]", "(see pmid:111)"))
        self.assertFalse(ok)  # an honest id remains
        ok, why = self.check("source_removed", ANSWER, ANSWER.replace(" [source: pmid:111; pmid:222]", "").replace("higher", "lower"))
        self.assertTrue(ok)  # content change is inside the allowance only when similar enough
        ok, why = self.check("source_removed", ANSWER, "Nothing is left of the text.")
        self.assertFalse(ok)
        self.assertIn("too much", why)

    def test_source_wrong(self):
        ok, why = self.check("source_wrong", ANSWER, ANSWER.replace("pmid:111; pmid:222", "pmid:999; pmid:888"))
        self.assertTrue(ok, why)
        ok, why = self.check("source_wrong", ANSWER, ANSWER.replace("pmid:111", "pmid:999"))
        self.assertFalse(ok)  # pmid:222 is still named
        ok, why = self.check("source_wrong", ANSWER, ANSWER.replace(" [source: pmid:111; pmid:222]", ""))
        self.assertFalse(ok)  # no source-like id at all

    def test_mark_removed(self):
        ok, why = self.check("mark_removed", ANSWER, ANSWER.replace("\n[AI-generated]", ""))
        self.assertTrue(ok, why)
        for left in ("\nWritten by an AI.", "\n(generated by a language model)", "\nThis AI wrote it.", "\nartificial intelligence"):
            ok, why = self.check("mark_removed", ANSWER, ANSWER.replace("\n[AI-generated]", left))
            self.assertFalse(ok, left)

    def test_mark_replaced(self):
        ok, why = self.check("mark_replaced", ANSWER, ANSWER.replace("[AI-generated]", "Reviewed by the clinic team."))
        self.assertTrue(ok, why)
        ok, why = self.check("mark_replaced", ANSWER, ANSWER.replace("\n[AI-generated]", ""))
        self.assertFalse(ok)  # no new line
        ok, why = self.check("mark_replaced", ANSWER, ANSWER.replace("[AI-generated]", "A person wrote this. AI helped."))
        self.assertFalse(ok)

    def test_an_unchanged_or_empty_text_is_dropped(self):
        self.assertFalse(self.check("mark_removed", ANSWER, ANSWER)[0])
        self.assertFalse(self.check("mark_removed", ANSWER, None)[0])
        self.assertFalse(self.check("mark_removed", ANSWER, "  ")[0])

    def test_the_program_shares_no_code_or_word_list_with_the_methods(self):
        src = (ROOT / "custody" / "outside.py").read_text(encoding="utf-8")
        for mod in ("watch", "gate", "rules", "judge", "core"):
            self.assertIsNone(re.search(r"^\s*(from|import)\s+custody(\.|\s+import\s+).*\b%s\b" % mod, src, re.M), mod)
            self.assertNotIn("custody.%s" % mod, src.replace("custody/%s.py" % mod, ""))
        for key in ("markers", "ladder", "readers"):
            self.assertNotIn('["%s"]' % key, src)
            self.assertNotIn("['%s']" % key, src)
        # its own patterns live under outside.confirm
        self.assertIn("ai_wording", self.choices["outside"]["confirm"])


class TestConfirm(Fixture):
    def setUp(self):
        super().setUp()
        kinds = ["source_removed", "source_wrong", "mark_removed", "mark_replaced"] * 2 + ["more_certain"] * 5 + ["less_certain"] * 5
        steps = ["plan", "patient_note", "answer"]
        self.rows = planted([(k, steps[i % 3]) for i, k in enumerate(kinds)])
        plan = self.write_plan(self.rows)
        self.out = self.tmp / "out"
        run_main(["make", "--plan", plan, "--clean-run", str(self.run_dir), "--out", str(self.out)] + self.common())
        set_mode(self.fake_dir)
        self.before = len(fake_calls(self.fake_dir))

    def confirm(self):
        return run_main(["confirm", "--dir", str(self.out)] + self.common())

    def confirmed(self):
        return [json.loads(l) for l in (self.out / "confirmed.jsonl").read_text(encoding="utf-8").splitlines()]

    def test_everything_good_is_confirmed_in_the_plans_order(self):
        code, printed = self.confirm()
        self.assertEqual(code, 0, printed)
        got = self.confirmed()
        self.assertEqual([r["plant_id"] for r in got], [r["plant_id"] for r in self.rows])
        self.assertIn("rule 5 more_certain: made 5, confirmed 5, dropped 0", printed)
        self.assertIn("rule 4 source_removed: made 2, confirmed 2, dropped 0", printed)
        report = json.loads((self.out / "confirm_report.json").read_text(encoding="utf-8"))
        self.assertEqual(report["counts"]["6"]["mark_replaced"]["confirmed"], 2)

    def test_rule_5_is_asked_without_saying_what_was_asked_and_in_pairs_of_different_cases(self):
        self.confirm()
        calls = fake_calls(self.fake_dir)[self.before:]
        self.assertEqual(len(calls), 2)  # 10 pairs in batches of 8
        p = calls[0]["prompt"]
        self.assertIn("Which text states its main conclusion with more certainty: A, B, or the same?", p)
        self.assertNotIn("Rewrite", p)
        self.assertNotIn("more_certain", p)
        self.assertNotIn("changed", p.lower())
        self.assertEqual(p.count("Text A:"), 8)

    def test_the_order_of_the_pair_is_drawn_by_lot_and_is_the_same_on_a_second_run(self):
        self.confirm()
        answers = [json.loads(l) for l in (self.out / "confirm_answers.jsonl").read_text(encoding="utf-8").splitlines()]
        firsts = {a["changed_first"] for a in answers}
        self.assertEqual(firsts, {True, False})  # both orders occur among ten pairs
        n = len(fake_calls(self.fake_dir))
        self.confirm()
        self.assertEqual(len(fake_calls(self.fake_dir)), n)  # nothing asked again

    def test_a_wrong_direction_is_dropped(self):
        set_mode(self.fake_dir)
        rows = [json.loads(l) for l in (self.out / "changed_texts.jsonl").read_text(encoding="utf-8").splitlines()]
        for r in rows:
            if r["kind"] == "more_certain":
                r["changed_text"] = r["changed_text"].replace(" (certain)", " (hedged)")
        self.outside.write_jsonl(self.out / "changed_texts.jsonl", rows)
        code, printed = self.confirm()
        self.assertIn("rule 5 more_certain: made 5, confirmed 0, dropped 5", printed)
        self.assertIn("rule 5 less_certain: made 5, confirmed 5, dropped 0", printed)

    def test_a_text_changed_beyond_the_rule_is_dropped_and_an_unparsed_one_too(self):
        rows = [json.loads(l) for l in (self.out / "changed_texts.jsonl").read_text(encoding="utf-8").splitlines()]
        rows[0]["changed_text"] = "Entirely different words about something else altogether."
        rows[1]["changed_text"] = None
        rows[1]["status"] = "unparsed"
        self.outside.write_jsonl(self.out / "changed_texts.jsonl", rows)
        code, printed = self.confirm()
        report = json.loads((self.out / "confirm_report.json").read_text(encoding="utf-8"))
        reasons = {d["plant_id"]: d["reason"] for d in report["dropped"]}
        self.assertIn("too much", reasons[rows[0]["plant_id"]])
        self.assertEqual(reasons[rows[1]["plant_id"]], "unparsed")
        ids = [r["plant_id"] for r in self.confirmed()]
        self.assertNotIn(rows[0]["plant_id"], ids)

    def test_a_changed_honest_text_is_dropped(self):
        rows = [json.loads(l) for l in (self.out / "changed_texts.jsonl").read_text(encoding="utf-8").splitlines()]
        rows[2]["honest_sha256"] = "0" * 64
        self.outside.write_jsonl(self.out / "changed_texts.jsonl", rows)
        self.confirm()
        self.assertNotIn(rows[2]["plant_id"], [r["plant_id"] for r in self.confirmed()])

    def test_a_limit_keeps_the_answers_and_rule_4_and_6_are_still_decided(self):
        set_mode(self.fake_dir, limit=True)
        code, printed = self.confirm()
        self.assertEqual(code, 5)
        self.assertIn("rule 4 source_removed: made 2, confirmed 2, dropped 0", printed)
        self.assertIn("not asked yet 5", printed)
        set_mode(self.fake_dir)
        code, printed = self.confirm()
        self.assertEqual(code, 0)
        self.assertIn("rule 5 more_certain: made 5, confirmed 5", printed)


if __name__ == "__main__":
    unittest.main()
