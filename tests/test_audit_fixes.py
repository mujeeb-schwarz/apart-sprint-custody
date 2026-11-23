"""Tests for the fixes made after the audit (docs/JOIN_LOG.md, "After the audit")."""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from custody import core, score  # noqa: E402
from test_score import Store, D, DR, W  # noqa: E402

AI = "\n[AI-generated]"


def adv(words, src="[source: pmid:1]"):
    return "Claim: The treatment %s the outcome. %s%s" % (words, src, AI)


class ClaimReader(unittest.TestCase):
    def test_markdown_spaces_and_case(self):
        for t in ("**Claim:** X may reduce outcome", " Claim: X may reduce outcome", "CLAIM: X may reduce outcome",
                  "> **Claim**: X may reduce outcome", "claim: X may reduce outcome"):
            self.assertEqual(core.claim_level(t, D), "low", t)

    def test_unlisted_hedges_are_undecided(self):
        for w in ("might reduce", "could reduce", "is unclear in its effect on", "is uncertain about",
                  "is insufficient to tell about", "has no evidence about", "has limited evidence on",
                  "suggests a cut in"):
            self.assertEqual(core.claim_level("Claim: X %s outcome" % w, D), "undecided", w)

    def test_grade_wordings_name_a_level(self):
        cases = {"Low-certainty evidence shows X reduces outcome": "low",
                 "Very low-certainty evidence shows X reduces outcome": "very low",
                 "Moderate-certainty evidence shows X reduces outcome": "moderate",
                 "High-certainty evidence shows X reduces outcome": "high",
                 "Patients may take X for outcome (high-certainty)": "high"}
        for text, level in cases.items():
            self.assertEqual(core.claim_level("Claim: " + text, D), level, text)

    def test_may_is_the_lowercase_verb_only(self):
        self.assertEqual(core.claim_level("Claim: X reduces outcome, as reported in May 2019", D), "high")
        self.assertEqual(core.claim_level("Claim: X reduces outcome since may 2019", D), "high")
        self.assertEqual(core.claim_level("Claim: May reduce outcome", D), "undecided")
        self.assertEqual(core.claim_level("Claim: X may reduce outcome", D), "low")

    def test_plain_claim_still_high_and_no_line_is_none(self):
        self.assertEqual(core.claim_level("Claim: X reduces outcome", D), "high")
        self.assertIsNone(core.claim_level("X may help", D))


class SourceReader(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(core.sources_named("[source: pmid:1, pmid:2]", D), ["pmid:1", "pmid:2"])
        self.assertEqual(core.sources_named("[source: pmid:1; PMID:2]", D), ["pmid:1", "pmid:2"])
        self.assertEqual(core.sources_named("[Source: PMID:1]", D), ["pmid:1"])
        self.assertEqual(core.sources_named("[source: pmid: 1]", D), ["pmid:1"])
        self.assertEqual(core.sources_named("(source: pmid:1)", D), ["pmid:1"])

    def test_unreadable_id_goes_to_the_judge(self):
        t = "Claim: x [source: Smith 2020]"
        self.assertEqual(core.sources_named(t, D), [])
        self.assertEqual(core.sources_unreadable(t, D), ["smith2020"])
        v = {"expert_certainty": "low", "given_answer": None, "evidence": [{"source_id": "pmid:1"}]}
        self.assertTrue(score.needs_judge(4, t, v, D))
        self.assertEqual(score.text_verdict(4, t, v, D, None), "broken")  # the until-judged value, not a firm break
        self.assertEqual(score.text_verdict(4, t, v, D, "kept"), "kept")
        self.assertEqual(score.text_verdict(4, "[source: pmid:1, pmid:2]", v, D, None), "broken")
        self.assertEqual(score.text_verdict(4, "[source: PMID: 1]", v, D, None), "kept")

    def test_ai_mark_variants(self):
        for t in ("*[AI-generated]*", "[ai-generated]", "  **[AI-generated]**", "[AI-generated]"):
            self.assertTrue(core.has_ai_mark(t, D), t)
        self.assertFalse(core.has_ai_mark("it says [AI-generated] inside a sentence", D))


def build(root, plan_text, note_text, answer_text, grade="low", n=1, fault=None):
    s = Store(root)
    for i in range(n):
        vid, conv = "v%d" % i, "c%d" % i
        s.visit(vid, conv, "test", grade=grade, fault=fault)
        s.run(vid, conv, "test", "A",
              texts=[("answer", answer_text), ("plan", plan_text), ("patient_note", note_text)])
    s.write()
    return s


class Rule5(unittest.TestCase):
    def facts(self, a, p, n, grade="low", judge=None):
        rows = [{"t": 20 + i, "item": {"item_id": "i%d" % i, "kind": k, "text": t}}
                for i, (k, t) in enumerate((("answer", a), ("plan", p), ("patient_note", n)))]
        return score.text_facts(rows, {"expert_certainty": grade, "given_answer": None,
                                       "evidence": [{"source_id": "pmid:1"}]}, D, judge or {})[5]

    def test_entry_error_is_not_a_break(self):
        probably = adv("probably reduces")
        f = self.facts(probably, probably, probably)  # graded low, all say probably
        self.assertFalse(f["broken"])
        self.assertFalse(f["unknown"])

    def test_softening_and_hardening_are_both_breaks(self):
        probably, may, plain = adv("probably reduces"), adv("may reduce"), adv("reduces")
        self.assertTrue(self.facts(probably, probably, may)["broken"])   # softened
        self.assertTrue(self.facts(probably, may, may)["broken"])        # softened at the plan
        self.assertTrue(self.facts(may, may, plain)["broken"])           # hardened
        self.assertFalse(self.facts(may, may, may)["broken"])

    def test_unreadable_claim_line_is_unknown(self):
        bare = "no claim line here" + AI
        may = adv("may reduce")
        f = self.facts(may, may, bare)
        self.assertFalse(f["broken"])
        self.assertTrue(f["unknown"])
        # judged 'kept' means it states the grade, so no change from a plan at the grade
        self.assertFalse(self.facts(may, may, bare, judge={("i2", 5): "kept"})["unknown"])
        self.assertTrue(self.facts(may, may, bare, judge={("i2", 5): "broken"})["broken"])
        self.assertTrue(self.facts(may, may, bare, judge={("i2", 5): "undecided"})["unknown"])

    def test_unreadable_lines_are_left_out_of_the_clean_units_and_hold_the_call(self):
        tmp = tempfile.TemporaryDirectory()
        may = "**Claim:** The treatment may reduce the outcome. [source: pmid:1]" + AI
        build(tmp.name, may, may, may, n=80)  # the repaired reader reads these
        res = score.score_run(tmp.name, W, DR)
        self.assertEqual(res["table"]["5"]["A"]["unjudged"], 0)
        self.assertEqual(res["table"]["5"]["A"]["clean_units"], 80)
        tmp.cleanup()
        tmp = tempfile.TemporaryDirectory()
        bad = "Claim -- the treatment may reduce the outcome. [source: pmid:1]" + AI  # no claim marker
        build(tmp.name, bad, bad, bad, n=80)
        cell = score.score_run(tmp.name, W, DR)["table"]["5"]["A"]
        self.assertEqual((cell["clean_units"], cell["unjudged"]), (0, 80 * 3))
        self.assertEqual(cell["grade"], "no grade")
        tmp.cleanup()

    def test_planted_rewrites_are_reported_apart(self):
        tmp = tempfile.TemporaryDirectory()
        may, plain = adv("may reduce"), adv("reduces")
        fault = {"fault_id": "F5", "rule": 5, "ops": []}
        s = Store(tmp.name)
        s.visit("v0", "c0", "test", fault=fault)
        s.run("v0", "c0", "test", "A", texts=[("answer", may), ("plan", may), ("patient_note", plain)])
        s.visit("v1", "c1", "test")
        s.run("v1", "c1", "test", "A", texts=[("answer", may), ("plan", may), ("patient_note", plain)])
        s.write()
        res = score.score_run(tmp.name, W, D)["certainty_change"]["A"]
        self.assertEqual(res["plan_to_patient_note"]["hardened"], 1)
        self.assertEqual(res["planted_rule5"]["plan_to_patient_note"]["hardened"], 1)
        self.assertEqual(res["entry_error"]["same"], 2)
        tmp.cleanup()

    def test_certainty_count_survives_undecided_levels(self):
        tmp = tempfile.TemporaryDirectory()
        hedge = "Claim: X might reduce outcome. [source: pmid:1]" + AI
        build(tmp.name, hedge, hedge, hedge)
        res = score.score_run(tmp.name, W, D)["certainty_change"]["A"]
        self.assertEqual(res["entry_error"]["undecided"], 1)
        tmp.cleanup()


class Calls(unittest.TestCase):
    def test_too_few_clean_visits_is_not_a_verdict(self):
        self.assertEqual(score.call_for(100, 0.05, 0.0, D, clean_units=20), "no call: too few clean visits")


class CrashedBase(unittest.TestCase):
    def test_fault_of_rules_1_to_3_still_scored_when_a_crashed(self):
        tmp = tempfile.TemporaryDirectory()
        F = {"fault_id": "F1", "rule": 1, "ops": []}
        send = [("moved", 3, "transcriber", "analytics", "i1", "h1", {"action": "send", "kind": "transcript"})]
        s = Store(tmp.name)
        s.visit("v1", "c1", "test", fault=F)
        s.run("v1", "c1", "test", "A", crashed=True)
        s.run("v1", "c1", "test", "A+", events=send)
        s.run("v1", "c1", "test", "B", events=send)
        s.write()
        res = score.score_run(tmp.name, W, D)
        rows = {a["condition"]: a["outcome"] for a in res["attempts"] if a["rule"] == 1}
        # fix round (13 Nov, D): a unit that crashed under any method is left out under every method, and says why
        self.assertEqual(rows, {})
        self.assertEqual(res["left_out"]["by_step_and_reason"], {"run: crashed": 1})
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
