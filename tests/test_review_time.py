"""The review's time stamp (13 Nov, version 3).

The review reads the log after the case has closed. Its flag on a copy that is never deleted therefore comes at or
after the violation, and the scorer counts it. Before this change the stamp was the largest t in the log plus 1,
which lies before the deadline once the first flow ends in the chart, and the scorer read such a flag as a warning
that came before the violation.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import json  # noqa: E402

from custody import assemble, bench, datasets, score, store, visits, watch  # noqa: E402
from custody.core import Handover, Item  # noqa: E402

D = datasets.default_choices()
W = assemble.load_wiring()
CASE = [v for v in visits.read_cases(ROOT / "data" / "cases" / "exp1.jsonl", 1) if v.split == "tune"][0]

# All four deletions of the first flow. For d3, d4 and d6 the log shows the copy arriving (by intake or by a send).
# The note service's own draft (d5) is made at its place and has no arrival line; since 13 Nov the review's program
# part takes the logged send of the draft as proof that the note service held it (config key review.checks, rule 2).
ARRIVING = ("d3", "d4", "d5", "d6")


def fault(op, duty):
    return {"fault_id": "T-%s-%s" % (op, duty), "kind": "step", "rule": 2, "says": "x", "patch": [], "events": [],
            "needs": {}, "ops": [{"op": op, "duty": duty}]}


def run_scored(planted, cond):
    with tempfile.TemporaryDirectory() as tmp:
        parts = assemble.make_parts(W, bench.run_choices(D))
        bench.run_one(CASE, cond, planted, parts, W, D, tmp)
        st = store.read_store(tmp)
        res = score.score_run(tmp, W, D)
    return st, [a for a in res["attempts"] if a["rule"] == 2]


class TheReviewComesAfterTheCase(unittest.TestCase):
    def test_the_stamp_counts_as_the_engine_does_when_it_closes_a_case(self):
        # a deletion carried out only at close is logged one tick after the engine's closing time
        st, _ = run_scored(fault("late_delete", "d4"), "A")
        last = max(x["t"] for x in st["own_log"])
        late = [x for x in st["own_log"] if x["t"] == last]
        self.assertEqual([x["action"] for x in late], ["delete"])
        before = [x for x in st["own_log"] if x["t"] < last]
        self.assertEqual(watch.closing_time(before, D) + 1, last)

    def test_the_stamp_of_an_empty_log_counts_from_zero(self):
        self.assertEqual(watch.closing_time([], D), D["holds"]["in_visit"] + 2)

    def test_a_copy_that_is_never_deleted_is_flagged_by_the_review_and_the_flag_counts(self):
        for duty in ARRIVING:
            for cond in ("A", "A+"):
                st, attempts = run_scored(fault("skip_delete", duty), cond)
                flags = [s for s in st["signals"] if s["by"] == "review" and s["rule"] == 2
                         and s.get("part") == "program"]
                self.assertTrue(flags, (duty, cond))
                self.assertEqual([a["outcome"] for a in attempts], ["flagged"], (duty, cond))
                self.assertGreaterEqual(attempts[0]["signal_t"], attempts[0]["break_t"], (duty, cond))

    def test_a_deletion_after_its_deadline_is_flagged_by_the_review_and_the_flag_counts(self):
        for duty in ARRIVING:
            for cond in ("A", "A+"):
                _, attempts = run_scored(fault("late_delete", duty), cond)
                self.assertEqual([a["outcome"] for a in attempts], ["flagged"], (duty, cond))

    def test_the_note_services_own_draft_is_seen_through_the_send_and_flagged_once(self):
        st, attempts = run_scored(fault("skip_delete", "d5"), "A")
        flags = [s for s in st["signals"] if s["by"] == "review" and s["rule"] == 2 and s.get("part") == "program"]
        self.assertEqual(len(flags), 1)
        self.assertIn("sent on from note_writer", flags[0]["reason"])
        # a copy whose arrival the log shows is checked once, from its arrival, and not a second time from its send
        st, _ = run_scored(fault("skip_delete", "d3"), "A")
        flags = [s for s in st["signals"] if s["by"] == "review" and s["rule"] == 2 and s.get("part") == "program"]
        self.assertEqual(len(flags), 1)
        self.assertIn("arrived at transcriber", flags[0]["reason"])

    def test_a_clean_case_of_the_second_flow_gets_no_rule_2_flag_from_the_review(self):
        case2 = [v for v in visits.read_cases(ROOT / "data" / "cases" / "exp2.jsonl", 2) if v.split == "tune"][0]
        with tempfile.TemporaryDirectory() as tmp:
            parts = assemble.make_parts(W, bench.run_choices(D))
            bench.run_one(case2, "A", None, parts, W, D, tmp)
            st = store.read_store(tmp)
        self.assertFalse([s for s in st["signals"] if s["by"] == "review" and s["rule"] == 2])

    def test_a_clean_case_gets_no_rule_2_flag_from_the_review(self):
        st, attempts = run_scored(None, "A")
        self.assertFalse([s for s in st["signals"] if s["by"] == "review" and s["rule"] == 2])
        self.assertEqual(attempts, [])


class TheMonitorReadsRule4AsTheKeyDoes(unittest.TestCase):
    """13 Nov, after the audit of the flows: the composed answers list every study, and a plan that cites fewer of
    them breaks no rule (rules.rule4_all_sources_required false). The monitor flags a text that names no source, or
    a source that no earlier advice text of the run named."""

    def advice(self, ids):
        m = D["markers"]
        tag = m["source_tag"]
        named = (" %s %s%s" % (tag["open"], (tag["separator"] + " ").join(ids), tag["close"])) if ids else ""
        return "%s The treatment may help.%s\n%s" % (m["claim"], named, m["ai"])

    def rule4(self, w, n, ids, kind="plan", to="summary_writer"):
        h = Handover("r#%d" % n, "r", n, "send", "s", "clinician", to, kind, ["i%d" % n], None)
        return [s for s in w.look(h, [Item("i%d" % n, "q0001", kind, self.advice(ids), "ai", [])]) if s.rule == 4]

    def monitor(self, choices=None):
        return watch.Watcher(W, watch.ai_parts_off(choices or D), lambda prompt_id, fields: "", "r")

    def test_the_helper_text_is_read_as_meant(self):
        self.assertEqual(sorted(watch.sources_named(self.advice(["pmid:1", "pmid:2"]), D)), ["pmid:1", "pmid:2"])
        self.assertFalse(watch.sources_named(self.advice([]), D))

    def test_fewer_sources_than_before_is_no_flag(self):
        w = self.monitor()
        self.assertEqual(self.rule4(w, 1, ["pmid:1", "pmid:2", "pmid:3"], kind="answer", to="clinician"), [])
        self.assertEqual(self.rule4(w, 2, ["pmid:1"]), [])
        # a source that came with the case and was left out in between is still no new source
        self.assertEqual(self.rule4(w, 3, ["pmid:2", "pmid:3"], kind="patient_note", to="patient"), [])

    def test_a_source_that_was_not_there_before_is_flagged_and_named(self):
        w = self.monitor()
        self.rule4(w, 1, ["pmid:1", "pmid:2"], kind="answer", to="clinician")
        flags = self.rule4(w, 2, ["pmid:1", "pmid:9"])
        self.assertEqual(len(flags), 1)
        self.assertIn("pmid:9", flags[0].reason)
        self.assertNotIn("pmid:1,", flags[0].reason)

    def test_no_source_at_all_is_flagged(self):
        w = self.monitor()
        self.rule4(w, 1, ["pmid:1"], kind="answer", to="clinician")
        self.assertEqual(len(self.rule4(w, 2, [])), 1)

    def test_the_first_advice_text_has_nothing_to_be_compared_with(self):
        self.assertEqual(self.rule4(self.monitor(), 1, ["pmid:7"], kind="answer", to="clinician"), [])

    def test_with_the_switch_on_a_dropped_source_is_flagged_too(self):
        strict = json.loads(json.dumps(D))
        strict["rules"]["rule4_all_sources_required"] = True
        w = self.monitor(strict)
        self.rule4(w, 1, ["pmid:1", "pmid:2"], kind="answer", to="clinician")
        self.assertEqual(len(self.rule4(w, 2, ["pmid:1"])), 1)


if __name__ == "__main__":
    unittest.main()
