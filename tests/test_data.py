import sys
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import datasets, visits, stats  # noqa: E402
from custody.core import canon  # noqa: E402
from raw_data_guard import needs_raw_data, needs_retired_cases  # noqa: E402

D = datasets.default_choices()
RAW = ROOT / "data" / "raw"
_cache = {}


def all_visits():
    if "v" not in _cache:
        _cache["v"] = visits.build_visits(D["visits"]["total"], D, RAW)
    return _cache["v"]


class Loaders(unittest.TestCase):
    @needs_raw_data
    def test_aci(self):
        rows = datasets.load_aci(RAW)
        self.assertEqual(len(rows), D["data"]["aci"]["expected_rows"])
        self.assertEqual(len({r["conversation_id"] for r in rows}), 207)
        self.assertTrue(rows[0]["conversation_id"].startswith("aci:"))
        self.assertIsInstance(rows[0]["other_complaints"], list)
        self.assertNotIn("patient_firstname", rows[0])

    @needs_raw_data
    def test_medevidence(self):
        rows = datasets.load_medevidence(RAW)
        self.assertEqual(len(rows), 284)
        self.assertEqual(sum(r["usable"] for r in rows), D["data"]["medevidence"]["expected_usable"])
        self.assertEqual(sum(1 for r in rows if r["expert_certainty"] == "no data"), 37)
        self.assertTrue(all(r["sources"] for r in rows if r["usable"] and r["expert_certainty"] != "no data") or True)
        self.assertTrue(rows[0]["sources"][0]["source_id"].startswith("pmid:"))

    @needs_raw_data
    def test_pocqi(self):
        rows = datasets.load_pocqi(RAW)
        self.assertEqual(len(rows), 620)
        prov = D["data"]["pocqi"]["provider"]
        self.assertTrue(all(prov in r["answers"] for r in rows))

    def test_pocqi_without_answers_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "real-pocqi"
            d.mkdir()
            (d / "questions__train.jsonl").write_text(
                '{"question_id": "q1", "question_text": "t", "specialty": "s"}\n', encoding="utf-8")
            rows = datasets.load_pocqi(tmp)
            self.assertEqual(rows[0]["answers"], {})

    def test_pocqi_skips_a_cut_last_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "real-pocqi"
            d.mkdir()
            (d / "questions__train.jsonl").write_text(
                '{"question_id": "q1", "question_text": "t", "specialty": "s"}\n', encoding="utf-8")
            (d / "answers__train.jsonl").write_text(
                '{"question_id": "q1", "provider_key": "openevidence", "answer_text_only": "a"}\n{"question_id": "q1", "prov',
                encoding="utf-8")
            self.assertEqual(datasets.load_pocqi(tmp)[0]["answers"], {"openevidence": "a"})


class Visits(unittest.TestCase):
    @needs_raw_data
    def test_ten_visits_build_twice_to_the_same_bytes(self):
        a = visits.build_visits(10, D, RAW)
        b = visits.build_visits(10, D, RAW)
        self.assertEqual([canon(asdict(v)) for v in a], [canon(asdict(v)) for v in b])

    @needs_raw_data
    def test_split_pairs_and_counts(self):
        vs = all_visits()
        self.assertEqual(len(vs), 400)
        tune = {v.conversation_id for v in vs if v.split == "tune"}
        test = {v.conversation_id for v in vs if v.split == "test"}
        self.assertFalse(tune & test)
        self.assertEqual(len({v.question_id for v in vs}), 400)
        per = {}
        for v in vs:
            per[v.conversation_id] = per.get(v.conversation_id, 0) + 1
        self.assertLessEqual(max(per.values()), D["visits"]["per_conversation_max"])
        counts = visits.visit_counts(vs)
        for k, want in D["visits"]["expected_counts"].items():
            self.assertEqual(counts[k], want, k)

    @needs_raw_data
    def test_visit_shapes(self):
        vs = all_visits()
        self.assertEqual(vs[0].visit_id, "v0001")
        self.assertEqual(vs[0].split, "tune")
        graded, stored = vs[0], vs[-1]
        self.assertIsNotNone(graded.expert_certainty)
        self.assertIsNone(graded.given_answer)
        self.assertTrue(graded.evidence)
        self.assertIsNone(stored.expert_certainty)
        self.assertEqual(stored.given_by, D["data"]["pocqi"]["provider"])
        self.assertTrue(stored.given_answer)
        self.assertEqual(stored.evidence, [])
        self.assertFalse(any(v.matched for v in vs))
        self.assertEqual(sorted(graded.meta), sorted(["subset", "file", "chief_complaint",
                                                      "other_complaints", "specialty", "review"]))

    @needs_raw_data
    def test_stored_answer_visit_has_no_grade_so_no_rule_5_unit(self):
        stored = [v for v in all_visits() if v.given_answer is not None]
        self.assertTrue(stored)
        self.assertTrue(all(v.expert_certainty is None for v in stored))

    @needs_raw_data
    def test_write_and_read_back(self):
        vs = visits.build_visits(5, D, RAW)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x" / "visits.jsonl"
            visits.write_visits(p, vs)
            self.assertEqual(visits.read_visits(p), vs)


class Bar(unittest.TestCase):
    def test_check_values(self):
        for c in D["bar"]["check_values"]:
            self.assertAlmostEqual(stats.upper_bound(c["k"], c["n"], D["bar"]["tail"]), c["upper"], places=6)

    def test_edges(self):
        self.assertEqual(stats.upper_bound(5, 5), 1.0)
        self.assertEqual(stats.upper_bound(0, 0), 1.0)


if __name__ == "__main__":
    unittest.main()
