import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import core  # noqa: E402

D = json.load(open(str(ROOT / "config" / "design_choices.json"), encoding="utf-8"))
W = json.load(open(str(ROOT / "wiring" / "wiring.json"), encoding="utf-8"))


class Readers(unittest.TestCase):
    def test_every_ladder_example(self):
        for ex in D["ladder"]["examples"]:
            self.assertEqual(core.claim_level(ex["text"], D), ex["level"], ex["text"])
            self.assertEqual(core.sources_named(ex["text"], D), ex["sources"], ex["text"])
            self.assertEqual(core.has_ai_mark(ex["text"], D), ex["ai_mark"], ex["text"])


class Lookups(unittest.TestCase):
    def test_named_and_unnamed(self):
        self.assertTrue(core.is_named(W, "transcriber"))
        self.assertFalse(core.is_named(W, "analytics"))

    def test_place_missing_from_the_wiring(self):
        self.assertFalse(core.is_named(W, "nowhere"))
        self.assertFalse(core.may_hold(W, "nowhere", "transcript"))
        self.assertIsNone(core.hold_ticks(W, D, "nowhere", "transcript"))

    def test_kind_that_may_stay(self):
        self.assertTrue(core.may_hold(W, "record", "note"))
        self.assertIsNone(core.hold_ticks(W, D, "record", "note"))

    def test_kind_with_a_hold(self):
        self.assertEqual(core.hold_ticks(W, D, "transcriber", "transcript"), D["holds"]["in_visit"])
        self.assertEqual(core.hold_ticks(W, D, "note_writer_queue", "note_draft"), D["holds"]["side_store"])

    def test_kind_a_place_may_not_hold(self):
        self.assertFalse(core.may_hold(W, "transcriber", "note"))
        self.assertIsNone(core.hold_ticks(W, D, "transcriber", "note"))


class Ids(unittest.TestCase):
    def test_fingerprint_and_item_id_are_stable(self):
        self.assertEqual(core.fingerprint({"b": 1, "a": 2}), core.fingerprint({"a": 2, "b": 1}))
        self.assertEqual(len(core.make_item_id("v0001", "transcript", "intake", "x")), 16)


if __name__ == "__main__":
    unittest.main()
