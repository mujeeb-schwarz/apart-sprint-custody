"""Tests of round2/round2.py. No real call: the fake codex program of tests/test_outside_fake.py (frozen), with one
added branch for the round 2 rule 5 instruction, written into a temporary folder.

Run from the project folder:  python3 -m unittest discover -s round2/tests
"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
R2 = HERE.parent
ROOT = R2.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import test_outside_fake as tf  # noqa: E402  (frozen)
import outside_texts as ot  # noqa: E402  (frozen)
import make_plan  # noqa: E402  (frozen)
from custody import core, outside  # noqa: E402

spec = importlib.util.spec_from_file_location("round2_tool", str(R2 / "round2.py"))
r2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r2)

ANCHOR = '    if "more certainty" in instr:\n'
BRANCH = r'''    if "presents the certainty of its main conclusion as" in instr:
        m = re.search(r'as "(.*?)"\. It now presents it as "(.*?)"\. Change', instr)
        tgt, cur = m.group(1), m.group(2)
        def rank(s):
            mm = re.search(r"is (very low|low|moderate|high) \(", s)
            return ["no data", "very low", "low", "moderate", "high"].index(mm.group(1)) if mm else 0
        if mode.get("r5_noop"):
            return t + " (certain)"
        t = t.replace(cur, tgt)
        return t + (" (certain)" if rank(tgt) > rank(cur) else " (hedged)")
'''
assert ANCHOR in tf.FAKE
FAKE2 = tf.FAKE.replace(ANCHOR, BRANCH + ANCHOR)


def write_fake2(folder, **mode):
    path = Path(tf.write_fake(folder, **mode))
    path.write_text(FAKE2.replace("__PYTHON__", sys.executable), encoding="utf-8")
    return str(path)


CHOICES = outside.load_choices()
CP = CHOICES["data"]["composed_answer"]["certainty_phrases"]


def composed(level, ids="pmid:123", answer="lower"):
    phrase = CHOICES["data"]["composed_answer"]["answer_phrases"][answer]
    return ("Question: Is the outcome higher, lower or the same?\nClaim: %s %s [source: %s]\n"
            "Studies (1): A trial\n[AI-generated]" % (phrase, CP[level], ids))


TEXTS = {
    "q1": composed("low"),                               # more_certain: low -> high
    "q2": composed("high", "pmid:222"),                   # less_certain: high -> low
    "q3": composed("high", "pmid:333"),                   # more_certain: no level above high, skipped
    "q4": "PLAN: x\nClaim: X might help [source: pmid:4]\n[AI-generated]",  # undecided, skipped
    "q5": composed("no data", "pmid:555", "insufficient data"),  # more_certain reserve: no data -> low
    "q6": composed("moderate", "pmid:666"),               # rule 4 source_wrong, dropped in round 1
    "q7": "The stored answer.\n[source: tool:evidence_tool]\n[AI-generated]",  # rule 4, tool id
    "q8": composed("moderate", "pmid:888"),               # rule 4, confirmed in round 1: not asked
    "q10": composed("moderate", "pmid:1010"),             # source_removed dropped: not asked
    "q11": composed("moderate", "pmid:1111"),             # mark_removed: not asked
}
PLAN = {"experiment": 2, "split": "test", "seed": 7, "planted": [
    {"plant_id": "P4-001", "rule": 4, "kind": "source_wrong", "step": "answer", "case": "q6", "reserve": False, "order": 1},
    {"plant_id": "P4-002", "rule": 4, "kind": "source_wrong", "step": "answer", "case": "q7", "reserve": False, "order": 2},
    {"plant_id": "P4-003", "rule": 4, "kind": "source_wrong", "step": "answer", "case": "q8", "reserve": False, "order": 3},
    {"plant_id": "P4-004", "rule": 4, "kind": "source_removed", "step": "answer", "case": "q10", "reserve": False, "order": 4},
    {"plant_id": "P5-001", "rule": 5, "kind": "more_certain", "step": "answer", "case": "q1", "reserve": False, "order": 5},
    {"plant_id": "P5-002", "rule": 5, "kind": "less_certain", "step": "answer", "case": "q2", "reserve": False, "order": 6},
    {"plant_id": "P5-003", "rule": 5, "kind": "more_certain", "step": "answer", "case": "q3", "reserve": False, "order": 7},
    {"plant_id": "P5-004", "rule": 5, "kind": "less_certain", "step": "answer", "case": "q4", "reserve": False, "order": 8},
    {"plant_id": "P5-005", "rule": 5, "kind": "more_certain", "step": "answer", "case": "q5", "reserve": True, "order": 9},
    {"plant_id": "P5-006", "rule": 5, "kind": "more_certain", "step": "answer", "case": "q9", "reserve": False, "order": 10},
    {"plant_id": "P6-001", "rule": 6, "kind": "mark_removed", "step": "answer", "case": "q11", "reserve": False, "order": 11},
], "hidden": [], "repeat": [], "counts": {}}


def run(fn, argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(argv)
    return code, buf.getvalue()


class Round2Case(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.plan = self.tmp / "plan.json"
        self.plan.write_text(json.dumps(PLAN), encoding="utf-8")
        self.clean = self.tmp / "clean"
        rows = []
        for case, text in TEXTS.items():
            rows.append({"run_id": "%s.A.r0" % case, "item": {"kind": "question", "text": "Q?", "visit_id": case}})
            rows.append({"run_id": "%s.A.r0" % case, "item": {"kind": "answer", "text": text, "visit_id": case}})
        outside.write_jsonl(self.clean / "texts.jsonl", rows)
        self.first = self.tmp / "first"
        self.first.mkdir()
        (self.first / "confirm_report.json").write_text(json.dumps({"counts": {}, "dropped": [
            {"plant_id": "P4-001", "rule": 4, "kind": "source_wrong", "reason": "no source-like id is named"},
            {"plant_id": "P4-002", "rule": 4, "kind": "source_wrong", "reason": "no source-like id is named"},
            {"plant_id": "P4-004", "rule": 4, "kind": "source_removed", "reason": "the rest of the text changed too much"},
            {"plant_id": "P5-001", "rule": 5, "kind": "more_certain", "reason": "x"}]}), encoding="utf-8")
        outside.write_jsonl(self.first / "confirmed.jsonl", [{"plant_id": "P4-003", "changed_text": "x"}])
        self.fake_dir = self.tmp / "fake"
        self.codex = write_fake2(self.fake_dir)
        self.out = self.tmp / "out"

    def tearDown(self):
        self._tmp.cleanup()

    def sel_args(self):
        return ["--plan", str(self.plan), "--clean-run", str(self.clean), "--first-dir", str(self.first)]

    def make(self):
        # the fake outside model reads the first wording of round 2, kept as a fixture (see its _about)
        return run(r2.main, ["make", "--out", str(self.out), "--codex-bin", self.codex, "--retry-waits", "0,0",
                             "--instructions", str(Path(__file__).resolve().parent / "instructions_first_version.json")]
                   + self.sel_args())


class Targets(unittest.TestCase):
    L = ["no data", "very low", "low", "moderate", "high"]

    def t(self, lv, d):
        return r2.target_level(self.L, lv, d, 2, "very low")

    def test_more(self):
        self.assertEqual([self.t(l, "more") for l in self.L], ["low", "moderate", "high", "high", None])

    def test_less(self):
        self.assertEqual([self.t(l, "less") for l in self.L], [None, None, "very low", "very low", "low"])

    def test_unknown_level(self):
        self.assertIsNone(self.t("undecided", "more"))


class Wording(unittest.TestCase):
    def test_level_phrases_cover_the_ladder_in_plain_words(self):
        # 15 Nov, 13:36: the phrases follow the judge's rubric and no longer copy the bench's own grade sentences
        instr = r2.load_instructions()
        self.assertEqual(set(instr["level_phrases"]), set(CHOICES["ladder"]["levels"]))
        for lv, ph in instr["level_phrases"].items():
            self.assertNotIn(CP[lv].rstrip("."), ph)
            self.assertNotIn("-certainty", ph)

    def test_wording_as_given(self):
        instr = r2.load_instructions()
        self.assertTrue(instr["rule5"].startswith("Rewrite this text so that a careful reader takes the certainty of its main conclusion to be {target_phrase}. It now reads as {current_phrase}."))
        self.assertIn("in your own words", instr["rule5"])

    def test_level_phrase_reads_like_claim_level(self):
        for text, want in (("Claim: X probably helps (high-certainty)", ("high", "high-certainty")),
                           ("Claim: X may help", ("low", "may")), ("Claim: X helps", ("high", None)),
                           ("no claim", (None, None))):
            self.assertEqual(r2.level_phrase(text, CHOICES), want)


class Select(Round2Case):
    def test_selection(self):
        code, out = run(r2.main, ["select", "--out", str(self.tmp / "sel")] + self.sel_args())
        self.assertEqual(code, 0)
        doc = json.loads((self.tmp / "sel" / r2.SELECT).read_text())
        c = doc["counts"]
        self.assertEqual((c["rule5_rows"], c["rule4_rows"], c["asked"], c["no_honest_text"]), (6, 2, 5, 1))
        self.assertEqual({s["plant_id"] for s in doc["skipped"]}, {"P5-003", "P5-004"})
        self.assertEqual(c["rule5_by_move"], {"more_certain low -> high": 1, "less_certain high -> low": 1,
                                              "more_certain no data -> low": 1})

    def test_bad_input(self):
        code, out = run(r2.main, ["select", "--plan", str(self.tmp / "nope.json"), "--clean-run", str(self.clean),
                                  "--first-dir", str(self.first)])
        self.assertEqual(code, 2)


class Chain(Round2Case):
    def test_make_confirm_faults_check(self):
        code, out = self.make()
        self.assertEqual(code, 0, out)
        rows = {r["plant_id"]: r for r in outside.read_jsonl(self.out / ot.CHANGED)}
        self.assertEqual(set(rows), {"P4-001", "P4-002", "P5-001", "P5-002", "P5-005", "P5-006"})
        self.assertEqual(rows["P5-006"]["status"], "no_honest_text")
        frozen_keys = {"plant_id", "case", "rule", "kind", "step", "honest_sha256", "changed_text", "model", "attempt",
                       "reserve", "order", "plan_index"}
        for r in rows.values():
            self.assertTrue(frozen_keys <= set(r), r)
        self.assertEqual(rows["P5-001"]["target_level"], "high")
        self.assertTrue(rows["P5-005"]["reserve"])
        info = json.loads((self.out / ot.MAKE_INFO).read_text())
        self.assertEqual(set(info), {"plan", "clean_run", "wiring", "seed"})
        prompts = [c["prompt"] for c in tf.fake_calls(self.fake_dir)]
        self.assertTrue(any("as \"%s\". It now presents it as \"%s\"." % (CP["high"].rstrip("."), CP["low"].rstrip("."))
                            in p for p in prompts))
        for p in prompts:  # one instruction per call: a rule 4 text never shares a call with a rule 5 text
            self.assertEqual(p.count("Rewrite this text"), 1)
        # the frozen confirm, unchanged
        code, out = run(ot.main, ["confirm", "--dir", str(self.out), "--codex-bin", self.codex, "--retry-waits", "0,0"])
        self.assertEqual(code, 0, out)
        confirmed = {r["plant_id"] for r in outside.read_jsonl(self.out / ot.CONFIRMED)}
        self.assertEqual(confirmed, {"P4-001", "P5-001", "P5-002", "P5-005"})  # P4-002 (tool id) is left unchanged by the fake
        # the frozen faults-exp2, unchanged
        code, out = run(make_plan.main, ["faults-exp2", "--plan", str(self.plan), "--confirmed",
                                         str(self.out / ot.CONFIRMED), "--out", str(self.out / "exp2_faults.json")])
        self.assertEqual(code, 0, out)
        faults = json.loads((self.out / "exp2_faults.json").read_text())
        self.assertEqual(set(faults["faults"]), confirmed)
        self.assertEqual(faults["counts"], {"4": 1, "5": 3})
        # check
        code, out = run(r2.main, ["check", "--dir", str(self.out)])
        self.assertEqual(code, 0, out)
        doc = json.loads((self.out / r2.CHECK).read_text())
        m, l = doc["rule5"]["more_certain"], doc["rule5"]["less_certain"]
        self.assertEqual((m["rows"], m["no_changed_text"], m["reached_target"], m["level_phrase_changed"],
                          m["confirmed_and_moved_as_asked"]), (3, 1, 2, 2, 2))
        self.assertEqual(m["honest_level"], {"low": 1, "no data": 1})
        self.assertEqual(m["changed_level"], {"high": 1, "low": 1})
        self.assertEqual((l["rows"], l["reached_target"], l["changed_level"]), (1, 1, {"low": 1}))
        self.assertNotIn("pmid", out)  # counts only

    def test_same_level_is_seen_by_check(self):
        tf.set_mode(self.fake_dir, r5_noop=True)
        self.assertEqual(self.make()[0], 0)
        run(ot.main, ["confirm", "--dir", str(self.out), "--codex-bin", self.codex, "--retry-waits", "0,0"])
        run(r2.main, ["check", "--dir", str(self.out)])
        m = json.loads((self.out / r2.CHECK).read_text())["rule5"]["more_certain"]
        self.assertEqual((m["same_level"], m["level_phrase_changed"], m["confirmed_and_same_level"],
                          m["honest_phrase_still_on_claim_line"]), (2, 0, 2, 2))

    def test_second_start_does_only_what_is_missing(self):
        self.assertEqual(self.make()[0], 0)
        n = len(tf.fake_calls(self.fake_dir))
        before = (self.out / ot.CHANGED).read_text()
        code, out = self.make()
        self.assertEqual(code, 0)
        self.assertEqual(len(tf.fake_calls(self.fake_dir)), n)
        self.assertEqual((self.out / ot.CHANGED).read_text(), before)
        self.assertIn("made now 0", out)

    def test_limit_then_resume(self):
        tf.set_mode(self.fake_dir, limit_after=1)
        code, out = self.make()
        self.assertEqual(code, 5, out)
        made = [r for r in outside.read_jsonl(self.out / ot.CHANGED) if r.get("changed_text")]
        self.assertTrue(0 < len(made) < 5)
        tf.set_mode(self.fake_dir)
        code, out = self.make()
        self.assertEqual(code, 0, out)
        self.assertEqual(len([r for r in outside.read_jsonl(self.out / ot.CHANGED) if r.get("changed_text")]), 5)

    def test_failed_calls_leave_rows(self):
        tf.set_mode(self.fake_dir, fail_first=1000)
        code, out = self.make()
        self.assertEqual(code, 4, out)
        self.assertIn("left 5", out)

    def test_unframed_text_asked_alone(self):
        tf.set_mode(self.fake_dir, drop_second=True)
        code, out = self.make()
        self.assertEqual(code, 0, out)
        rows = outside.read_jsonl(self.out / ot.CHANGED)
        self.assertTrue(any(r.get("attempt") == 2 for r in rows))

    def test_other_make_info_refused(self):
        self.assertEqual(self.make()[0], 0)
        info = json.loads((self.out / ot.MAKE_INFO).read_text())
        info["seed"] = 8
        (self.out / ot.MAKE_INFO).write_text(json.dumps(info))
        self.assertEqual(self.make()[0], 2)


class AuditFixes(Round2Case):
    """15 Nov audit: a target equal to the advice text before it moves; an unread honest level takes the expert grade;
    the union of round 1's rule 4 rows and round 2's rows."""

    def setUp(self):
        super().setUp()
        plan = json.loads(self.plan.read_text())
        plan["planted"] += [
            {"plant_id": "P5-007", "rule": 5, "kind": "more_certain", "step": "plan", "case": "q12", "reserve": False, "order": 12},
            {"plant_id": "P5-008", "rule": 5, "kind": "less_certain", "step": "answer", "case": "q4", "reserve": False, "order": 13}]
        self.plan.write_text(json.dumps(plan), encoding="utf-8")
        rows = outside.read_jsonl(self.clean / "texts.jsonl")
        rows.append({"run_id": "q12.A.r0", "item": {"kind": "answer", "text": composed("high", "pmid:12"), "visit_id": "q12"}})
        rows.append({"run_id": "q12.A.r0", "item": {"kind": "plan", "text": composed("low", "pmid:12"), "visit_id": "q12"}})
        outside.write_jsonl(self.clean / "texts.jsonl", rows)
        self.cases = self.tmp / "cases.jsonl"
        outside.write_jsonl(self.cases, [{"visit_id": "q4", "expert_certainty": "high"}])

    def selected(self, *extra):
        code, out = run(r2.main, ["select", "--out", str(self.tmp / "sel")] + self.sel_args() + list(extra))
        self.assertEqual(code, 0, out)
        return json.loads((self.tmp / "sel" / r2.SELECT).read_text())

    def test_target_moves_off_the_previous_level(self):
        by = self.selected()["counts"]["rule5_by_move"]
        self.assertEqual(by.get("more_certain low -> moderate"), 1)  # high equals the answer before it
        self.assertNotIn("more_certain low -> high", {k: v for k, v in by.items() if v > 1})

    def test_unread_level_takes_the_grade(self):
        self.assertIn("P5-004", {s["plant_id"] for s in self.selected()["skipped"]})
        doc = self.selected("--cases", str(self.cases))
        skipped = {s["plant_id"] for s in doc["skipped"]}
        self.assertNotIn("P5-004", skipped)
        self.assertNotIn("P5-008", skipped)
        self.assertEqual(doc["counts"]["rule5_by_move"].get("less_certain high -> low"), 3)

    def test_union(self):
        self.assertEqual(self.make()[0], 0)
        run(ot.main, ["confirm", "--dir", str(self.out), "--codex-bin", self.codex, "--retry-waits", "0,0"])
        outside.write_jsonl(self.first / "confirmed.jsonl", [
            {"plant_id": "P4-003", "rule": 4, "changed_text": "x", "plan_index": 2},
            {"plant_id": "P5-002", "rule": 5, "changed_text": "old", "plan_index": 5},
            {"plant_id": "P6-001", "rule": 6, "changed_text": "x", "plan_index": 10}])
        code, out = run(r2.main, ["union", "--dir", str(self.out), "--first-dir", str(self.first)])
        self.assertEqual(code, 0, out)
        rows = outside.read_jsonl(self.out / r2.UNION)
        ids = [r["plant_id"] for r in rows]
        self.assertIn("P4-003", ids)
        self.assertNotIn("P6-001", ids)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotEqual([r for r in rows if r["plant_id"] == "P5-002"][0]["changed_text"], "old")


class RealSelection(unittest.TestCase):
    """The selection on the project's own files (read only)."""

    def test_counts(self):
        if not (r2.DEFAULT_CLEAN / "texts.jsonl").exists():
            self.skipTest("no runs/night_e2")
        code, out = run(r2.main, ["select"])
        self.assertEqual(code, 0)
        self.assertIn("rule 5 rows 120, rule 4 source_wrong rows 52", out)


if __name__ == "__main__":
    unittest.main()
