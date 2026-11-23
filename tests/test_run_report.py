"""Tests for tools/make_run_report.py: a tiny stand-in run folder per experiment, written by hand."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "make_run_report.py"
sys.path.insert(0, str(ROOT / "tools"))
import make_run_report as mrr  # noqa: E402

SECRET_GRADE = "GRADE-MUST-NOT-APPEAR"


def jl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def make_folder(root, experiment, scores=None, scores_name="scores.json", ai="canned"):
    pre = "c" if experiment == 1 else "q"
    d = Path(root) / ("demo_e%d" % experiment)
    ids = [pre + "0001", pre + "0002"]
    rule = 1 if experiment == 1 else 6
    kind = "note_draft" if experiment == 1 else "answer"
    d.mkdir(parents=True)
    (d / "manifest.json").write_text(json.dumps(
        {"ai": ai, "counts": {"experiment": experiment, "cases": 2, "clean_cases": 1, "faults_planned": 1}}))
    jl(d / "visits.jsonl", [{"visit_id": v, "experiment": str(experiment), "expert_certainty": SECRET_GRADE} for v in ids])
    jl(d / "hidden" / "plan.jsonl", [
        {"visit_id": ids[0], "fault": {"fault_id": "PX1", "kind": "step", "rule": rule, "says": "A planted thing happens.",
                                       "ops": [{"op": "rewrite"}], "patch": [], "events": []}},
        {"visit_id": ids[1], "fault": None}])
    results, texts, truth, logs = [], [], [], []
    for v in ids:
        for c in ("A", "A+", "B"):
            rid = "%s.%s.r0" % (v, c)
            results.append({"run_id": rid, "visit_id": v, "condition": c, "rep": 0, "experiment": experiment})
            texts.append({"run_id": rid, "place": "record", "t": 3,
                          "item": {"item_id": "i" + v, "visit_id": v, "kind": kind, "made_by": "x", "text": "word " * 600}})
            truth.append({"run_id": rid, "seq": 1, "t": 2, "kind": "moved", "handover_id": rid + "#1", "place": "a",
                          "to_place": "b", "detail": {"action": "send", "kind": kind}, "fault_id": None})
            if c != "B":
                logs.append({"run_id": rid, "action": "send", "handover_id": rid + "#1", "from": "a", "to": "b", "kind": kind, "t": 2})
    jl(d / "results.jsonl", results)
    jl(d / "texts.jsonl", texts)
    jl(d / "hidden" / "truth.jsonl", truth)
    jl(d / "own_log.jsonl", logs)
    jl(d / "signals.jsonl", [{"run_id": ids[0] + ".B.r0", "by": "gate", "part": "program", "level": "block", "rule": rule,
                              "reason": "because", "t": 2, "handover_id": ids[0] + ".B.r0#1"}])
    jl(d / "ai_calls.jsonl", [{"run_id": ids[0] + ".A.r0", "prompt_id": "reviewer.v1", "call_id": "1", "output": "x"}])
    if scores is not None:
        (d / scores_name).write_text(json.dumps(scores))
    return d, ids


def scores_for(ids, rule):
    att = [{"visit_id": ids[0], "condition": c, "rule": rule, "outcome": o, "run_id": "%s.%s.r0" % (ids[0], c),
            "break_t": 2, "signal_t": 2 if o != "silent" else None} for c, o in (("A", "silent"), ("A+", "silent"), ("B", "blocked"))]
    cell = {"attempts": 1, "silent": 1, "false_alarms": 0, "clean_units": 1, "call": "no call"}
    return {"attempts": att, "table": {str(rule): {"A": cell, "A+": cell, "B": cell}}, "tune_table": {},
            "header": {"stand_in_text": "stand-in text: these numbers measure nothing", "complete": True}}


def with_in_words(sc, rule, main_active):
    cell = {"grade": "inconclusive", "violations": 2, "blocked": 1, "flagged": 0, "missed": 1, "upper": 0.9,
            "false_alarms": 0, "clean_units": 1, "decided_by": "a program", "unjudged": 0}
    tab = {str(rule): {n: dict(cell) for n in ("Promised", "Monitored", "Checked")}}
    tab[str(rule)]["least_enough"] = "Monitored"
    empty = {str(rule): {n: dict(cell, violations=0, clean_units=0) for n in ("Promised", "Monitored", "Checked")}}
    prac = {str(rule): {c: dict(cell) for c in ("A", "A+", "B")}}
    sc = dict(sc)
    sc["in_words"] = {"methods": ["Promised", "Monitored", "Checked"], "table": tab if main_active else empty,
                      "practice_set": {"label": "practice set: never counted", "table": prac, "grades": {}},
                      "by_kind": {str(rule): {}}, "flags_by_part": {str(rule): {"Checked": {"flagged_by": {"ai_only": 1}}}},
                      "unpaired_rows": 2, "cases_left_out": {"visits": 0}}
    sc["attempts"] = [dict(a, unpaired=True) for a in sc["attempts"]]
    return sc


def run_tool(*folders, out):
    return subprocess.run([sys.executable, str(TOOL), *map(str, folders), "--out", str(out)],
                          capture_output=True, text=True, cwd=str(ROOT))


class RunReport(unittest.TestCase):
    def check_page(self, experiment, scores_kind):
        with tempfile.TemporaryDirectory() as tmp:
            rule = 1 if experiment == 1 else 6
            probe_ids = [("c" if experiment == 1 else "q") + "0001", ("c" if experiment == 1 else "q") + "0002"]
            sc, name = None, "scores.json"
            if scores_kind == "full":
                sc = scores_for(probe_ids, rule)
            elif scores_kind == "partial":
                sc, name = scores_for(probe_ids, rule), "scores.partial.json"
            elif scores_kind == "odd":
                sc = {"table": "nonsense", "attempts": [{"visit_id": probe_ids[0]}, 5], "header": []}
            d, ids = make_folder(tmp, experiment, sc, name)
            out = Path(tmp) / "r.html"
            r = run_tool(d, out=out)
            self.assertEqual(r.returncode, 0, r.stderr)
            page = out.read_text(encoding="utf-8")
            for v in ids:
                self.assertIn(v, page)
            self.assertIn(mrr.STAND_IN_BAND, page)
            self.assertNotIn(SECRET_GRADE, page)
            self.assertNotIn("could not be built", page)
            self.assertIn("show all", page)  # the long text is cut
            self.assertIn("<details", page)
            for w in ("Promised", "Monitored", "Checked"):
                self.assertIn(w, page)
            return page

    def test_experiment_1_full_scores(self):
        page = self.check_page(1, "full")
        self.assertIn("stopped at the handover", page)
        self.assertNotIn("scores are partial", page.lower())

    def test_experiment_2_partial_scores_say_so(self):
        page = self.check_page(2, "partial")
        self.assertIn("scores are partial", page.lower())

    def _in_words_page(self, main_active):
        with tempfile.TemporaryDirectory() as tmp:
            ids = ["c0001", "c0002"]
            d, ids = make_folder(tmp, 1, with_in_words(scores_for(ids, 1), 1, main_active))
            out = Path(tmp) / "r.html"
            r = run_tool(d, out=out)
            self.assertEqual(r.returncode, 0, r.stderr)
            return out.read_text(encoding="utf-8")

    def test_in_words_main_table(self):
        page = self._in_words_page(True)
        self.assertIn("The least that is enough", page)
        self.assertIn("How to read this page", page)
        self.assertIn("No clean run of the same case to compare with", page)
        self.assertNotIn("every case in this run is a practice case", page)
        self.assertNotIn("could not be built", page)

    def test_in_words_empty_main_shows_practice_table(self):
        page = self._in_words_page(False)
        self.assertIn("every case in this run is a practice case", page)
        self.assertIn("Practice set: never counted", page)

    def test_missing_scores_file(self):
        page = self.check_page(1, "none")
        self.assertIn("No scores file", page)
        self.assertIn("nothing raised", page)

    def test_odd_scores_file_does_not_crash(self):
        self.check_page(2, "odd")

    def test_two_folders_one_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            d1, ids1 = make_folder(Path(tmp) / "x", 1, None)
            d2, ids2 = make_folder(Path(tmp) / "y", 2, None)
            out = Path(tmp) / "both.html"
            r = run_tool(d1, d2, out=out)
            self.assertEqual(r.returncode, 0, r.stderr)
            page = out.read_text(encoding="utf-8")
            for v in ids1 + ids2:
                self.assertIn(v, page)

    def test_real_ai_manifest_has_no_stand_in_band(self):
        with tempfile.TemporaryDirectory() as tmp:
            d, _ = make_folder(tmp, 1, None, ai="live")
            out = Path(tmp) / "r.html"
            self.assertEqual(run_tool(d, out=out).returncode, 0)
            self.assertNotIn(mrr.STAND_IN_BAND, out.read_text(encoding="utf-8"))

    def test_empty_folder_does_not_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "empty_e1"
            d.mkdir()
            out = Path(tmp) / "r.html"
            self.assertEqual(run_tool(d, out=out).returncode, 0)


if __name__ == "__main__":
    unittest.main()
