"""The joiner's tests: the parts fit, the tools hand out the right choices, and a small run holds."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import assemble, bench, datasets, faults, store, visits  # noqa: E402
from raw_data_guard import needs_raw_data, needs_retired_cases  # noqa: E402


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / "tools" / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Parts(unittest.TestCase):
    def test_parts_keys_and_prove_stand_in(self):
        D = datasets.default_choices()
        parts = assemble.make_parts(assemble.load_wiring(), bench.run_choices(D))
        self.assertEqual(set(parts), {"steps", "ai", "recording_ai", "run_visit", "make_courier", "review",
                                      "make_ledger", "build_receipt", "check_receipt", "prove", "compose_answer"})
        out = parts["prove"](assemble.load_wiring())
        self.assertEqual(out["status"], "not_run")
        self.assertEqual(out["proven_rules"], [])

    @needs_raw_data
    def test_make_parts_gets_choices_without_faults(self):
        e2e = load_tool("run_e2e")
        seen = []
        real = e2e.assemble.make_parts
        e2e.assemble.make_parts = lambda w, c: (seen.append(c), real(w, c))[1]
        try:
            with tempfile.TemporaryDirectory() as tmp:
                e2e.build_and_run(1, Path(tmp) / "e2e")
        finally:
            e2e.assemble.make_parts = real
        self.assertEqual(len(seen), 1)
        self.assertNotIn("faults", seen[0])


class Small(unittest.TestCase):
    def test_clean_visit_all_conditions(self):
        D = datasets.default_choices()
        W = assemble.load_wiring()
        for exp, final in ((1, "note"), (2, "patient_note")):
            vs = visits.read_cases(visits.case_path(exp, D), exp)[:1]
            with tempfile.TemporaryDirectory() as tmp:
                res = bench.run_all(vs, ["A", "A+", "B", "C"], {vs[0].visit_id: None},
                                    assemble.make_parts(W, bench.run_choices(D)), W, D, tmp)
                self.assertEqual(len(res), 4)
                for r in res:
                    self.assertFalse(r.crashed)
                    self.assertEqual(r.signals, 0)
                    self.assertTrue(r.produced[final])
                self.assertTrue(all(r.receipt_ok for r in res if r.condition in ("B", "C")))

    def test_forbidden_words_check(self):
        e2e = load_tool("run_e2e")
        self.assertEqual(e2e.check7(), [])

    @needs_raw_data
    def test_fingerprints_cover_data_and_scorer(self):
        D = datasets.default_choices()
        fp = assemble.manifest_fingerprints(D, ROOT / "data" / "raw")
        self.assertEqual(set(fp), {"wiring", "design_choices", "prompts", "data", "scorer"})
        self.assertTrue(fp["data"] and fp["prompts"])


if __name__ == "__main__":
    unittest.main()


def _walk_closures(obj, seen, depth=0):
    """Every string reachable through function closures and containers, to look for the key."""
    if id(obj) in seen or depth > 6:
        return
    seen.add(id(obj))
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            for x in _walk_closures(k, seen, depth + 1):
                yield x
            for x in _walk_closures(v, seen, depth + 1):
                yield x
    elif isinstance(obj, (list, tuple, set)):
        for v in obj:
            for x in _walk_closures(v, seen, depth + 1):
                yield x
    elif callable(obj) and getattr(obj, "__closure__", None):
        for cell in obj.__closure__:
            for x in _walk_closures(cell.cell_contents, seen, depth + 1):
                yield x


class NoKeyInTheParts(unittest.TestCase):
    def test_the_ai_holds_no_witness_key_even_from_full_choices(self):
        D = datasets.default_choices()
        key = D["witness"]["test_key_hex"]
        for given in (D, bench.run_choices(D)):
            parts = assemble.make_parts(assemble.load_wiring(), given)
            self.assertFalse([x for x in _walk_closures(parts["ai"], set()) if key in x])


class Receipts(unittest.TestCase):
    @needs_raw_data
    def test_a_cut_off_tail_fails_the_check(self):
        from custody import receipt
        D = datasets.default_choices()
        W = assemble.load_wiring()
        vs = visits.build_visits(1, D, ROOT / "data" / "raw")
        with tempfile.TemporaryDirectory() as tmp:
            bench.run_all(vs, ["B"], {vs[0].visit_id: None}, assemble.make_parts(W, bench.run_choices(D)), W, D, tmp)
            rid = vs[0].visit_id + ".B.r0"
            jr = store.read_jsonl(Path(tmp) / "journal" / (rid + ".jsonl"))
            wlog = store.read_jsonl(Path(tmp) / "witness" / "log.jsonl")
            rc = json.loads((Path(tmp) / "receipts" / (rid + ".json")).read_text(encoding="utf-8"))
            key = bench._witness_key(D)
            self.assertTrue(receipt.check_receipt(rc, jr, wlog, key)["ok"])
            for cut in (1, 2):
                rebuilt = receipt.build_receipt(rid, "B", rc["records"][:-cut], rc["proof"], W, bench.run_choices(D))
                res = receipt.check_receipt(rebuilt, jr[:-cut], wlog, key)
                self.assertFalse(res["ok"], cut)
            res = receipt.check_receipt(rebuilt, jr[:-1], wlog, key)
            self.assertTrue(any("close record" in p for p in res["problems"]))


class Calls(unittest.TestCase):
    def test_few_clean_units_never_pass_the_bar(self):
        from custody import score, stats
        D = datasets.default_choices()
        up = stats.upper_bound(0, 40)
        self.assertEqual(score.call_for(40, up, 0.0, D, clean_units=2), "no call: too few clean visits")
        self.assertEqual(score.call_for(40, up, 0.0, D, clean_units=36), "enough")
        self.assertEqual(score.call_for(40, up, 0.0, D, clean_units=40, judged=False), "no call")

    def test_a_tool_cannot_reach_into_a_closure_in_the_checked_files(self):
        e2e = load_tool("run_e2e")
        self.assertEqual(e2e.check7(), [])


class Judging(unittest.TestCase):
    @needs_raw_data
    def test_unjudged_texts_are_counted_until_the_judge_reads_them(self):
        from custody import score
        D = datasets.default_choices()
        W = assemble.load_wiring()
        vs = visits.build_visits(1, D, ROOT / "data" / "raw")
        with tempfile.TemporaryDirectory() as tmp:
            bench.run_all(vs, ["A"], {vs[0].visit_id: None}, assemble.make_parts(W, bench.run_choices(D)), W, D, tmp)
            tp = Path(tmp) / "texts.jsonl"
            rows = store.read_jsonl(tp)
            row = json.loads(json.dumps([r for r in rows if r["item"]["kind"] == "plan"][0]))
            row["item"]["item_id"] = "unmarked-1"
            row["item"]["text"] = "Claim: x\n"
            store.append_jsonl(tp, [row])
            import copy
            DR = copy.deepcopy(D)
            DR["rules"]["key_source"] = "readers"  # the older key: the judge reads only what the readers cannot
            self.assertEqual(score.score_run(tmp, W, DR)["practice"]["table"]["6"]["A"]["unjudged"], 1)
            store.append_jsonl(Path(tmp) / "judge.jsonl", [{"item_id": "unmarked-1", "rule": 6, "verdict": "kept"},
                                                         {"item_id": "unmarked-1", "rule": 4, "verdict": "kept"}])
            self.assertEqual(score.score_run(tmp, W, DR)["practice"]["table"]["6"]["A"]["unjudged"], 0)
