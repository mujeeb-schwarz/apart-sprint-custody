"""ADVICE's tests: live answers by call id, the import checks, the judge's blindness, and a full round trip
in which canned answers stand in for the helpers. They write only to temporary folders."""
import contextlib
import importlib.util
import io
import json
import os
import re
import sys
import tempfile
import unittest
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("CUSTODY_TESTING", "1")  # H5: --filing-dir and a small --visits file are for tests only

from custody import ai as ai_mod, ai_live, datasets, judge, score, store, visits  # noqa: E402
from custody.core import AICallMissing, ContractError, canon, fingerprint  # noqa: E402
from raw_data_guard import needs_raw_data, needs_retired_cases  # noqa: E402

D = datasets.default_choices()


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, str(ROOT / "tools" / (name + ".py")))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TOOL = load_tool("run_advice")
_real_main = TOOL.main


def _quiet_main(argv=None):
    with contextlib.redirect_stdout(io.StringIO()):
        return _real_main(argv)


TOOL.main = _quiet_main


# ---------------------------------------------------------------- stand-in helpers

def helper_answer(call):
    """What a helper might write for one call. Chosen so that some texts break the markers."""
    pid, prompt = call["prompt_id"], call["prompt"]
    ids = re.findall(r"pmid:\d+|tool:\w+", prompt)
    tag = "[source: %s]" % (ids[0] if ids else "pmid:1")
    if pid.startswith("judge"):
        if call["expects"] == "level":
            return "LEVEL moderate"
        return "VERDICT broken"
    if pid.startswith(("watcher", "reviewer")):
        return "NO FLAGS"
    if pid.startswith("ai_answer"):
        return "Claim: The treatment probably reduces the outcome %s\n[AI-generated]" % tag
    if pid.startswith("plan"):
        return "PLAN\nClaim: The treatment probably reduces the outcome %s" % tag  # no AI mark: rule 6 to the judge
    if pid.startswith("patient_note"):
        return "FOR YOU\nThe treatment helps. [AI-generated]"  # no claim line, no tag: rules 4 and 5 to the judge
    return "stand-in text for %s" % pid


def write_answers(pending_rows, path, fn=helper_answer):
    with open(str(path), "w", encoding="utf-8") as fh:
        for call in pending_rows:
            fh.write(canon({"call_id": call["call_id"], "prompt_fp": call["prompt_fp"], "output": fn(call)}) + "\n")


def legacy_ids(cases):
    """Version 2: the tools run on one list of cases (here Experiment 2). The tests keep their v0001 ... ids."""
    return [replace(v, visit_id="v%04d" % (i + 1)) for i, v in enumerate(cases)]


def small_visits(tmp, tune=2, test=0):
    every = legacy_ids(visits.read_cases(str(ROOT / "data" / "cases" / "exp2.jsonl"), 2))
    keep = [v for v in every if v.split == "tune"][:tune] + [v for v in every if v.split == "test"][:test]
    path = Path(tmp) / "visits.jsonl"
    with open(str(path), "w", encoding="utf-8") as fh:
        for v in keep:
            fh.write(canon(asdict(v)) + "\n")
    return path, keep


def args(tmp, vpath, *more):
    return ["--experiment", "2", "--visits", str(vpath), "--live-dir", str(Path(tmp) / "live"), "--runs-dir", str(Path(tmp) / "runs"),
            "--filing-dir", str(Path(tmp) / "filing")] + list(more)


def file_predictions(tmp):
    """File a stand-in predictions page under tmp/filing, so that a test visit may run (13 Nov, G2)."""
    from custody import filing
    page = Path(tmp) / "predictions.md"
    page.write_text("stand-in predictions\n", encoding="utf-8")
    filing.file_predictions(page, Path(tmp) / "filing")


def round_trip(tmp, vpath, *more, max_rounds=20, seen=None):
    """Run, answer what is missing with the stand-in, import, and repeat. Returns the number of rounds.
    Each round's pending rows are added to `seen` when a list is given."""
    for n in range(max_rounds):
        code = TOOL.main(["run"] + args(tmp, vpath, *more))
        if code == 0:
            return n
        assert code == TOOL.WAITING, code
        pending = ai_live.read_pending(Path(tmp) / "live")
        assert pending, "waiting with nothing pending"
        if seen is not None:
            seen.extend(pending.values())
        out = Path(tmp) / ("answers_%d.jsonl" % n)
        write_answers(list(pending.values()), out)
        assert TOOL.main(["import", str(out)] + args(tmp, vpath, *more)) == 0
    raise AssertionError("no end after %d rounds" % max_rounds)


# ------------------------------------------------------------------ the store

def a_call(text="the prompt", pid="plan.v1"):
    call = ai_live.make_call(fingerprint(["id", text]), pid, text, "text")
    call["call_id"] = call["real"][0]  # these unit tests let the exported id and the real id coincide
    return call


class StoreAndImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = ai_live.AnswerStore(self.tmp.name)

    def test_a_good_answer_is_stored_and_read_back(self):
        call = a_call()
        res = ai_live.import_answers(self.store, {call["call_id"]: call},
                                     [{"call_id": call["call_id"], "prompt_fp": call["prompt_fp"], "output": "hello"}])
        self.assertEqual((res["stored"], res["refused"]), (1, []))
        self.assertEqual(self.store.answers(), {call["call_id"]: "hello"})
        again = ai_live.AnswerStore(self.tmp.name)  # a fresh object reads the file
        self.assertEqual(again.answers(), {call["call_id"]: "hello"})

    def test_a_wrong_fingerprint_is_refused(self):
        call = a_call()
        res = ai_live.import_answers(self.store, {call["call_id"]: call},
                                     [{"call_id": call["call_id"], "prompt_fp": fingerprint("another prompt"),
                                       "output": "hello"}])
        self.assertEqual(res["stored"], 0)
        self.assertIn("prompt_fp", res["refused"][0]["reason"])
        self.assertEqual(self.store.answers(), {})

    def test_an_unknown_call_is_refused(self):
        call = a_call()
        res = ai_live.import_answers(self.store, {call["call_id"]: call},
                                     [{"call_id": "0" * 64, "prompt_fp": call["prompt_fp"], "output": "x"}])
        self.assertEqual(res["stored"], 0)
        self.assertIn("no such call", res["refused"][0]["reason"])

    def test_an_answer_to_the_wrong_prompt_id_is_refused(self):
        call = a_call()
        res = ai_live.import_answers(self.store, {call["call_id"]: call},
                                     [{"call_id": call["call_id"], "prompt_id": "ai_answer.v1",
                                       "prompt_fp": call["prompt_fp"], "output": "x"}])
        self.assertEqual(res["stored"], 0)

    def test_an_edited_pending_prompt_is_refused(self):
        call = a_call()
        edited = dict(call, prompt="a different prompt")  # its fingerprint is now stale
        res = ai_live.import_answers(self.store, {call["call_id"]: edited},
                                     [{"call_id": call["call_id"], "prompt_fp": call["prompt_fp"], "output": "x"}])
        self.assertEqual(res["stored"], 0)
        self.assertIn("edited", res["refused"][0]["reason"])

    def test_empty_and_non_text_answers(self):
        call = a_call()
        pend = {call["call_id"]: call}
        row = {"call_id": call["call_id"], "prompt_fp": call["prompt_fp"]}
        self.assertEqual(ai_live.import_answers(self.store, pend, [dict(row, output="  ")])["stored"], 0)
        self.assertEqual(ai_live.import_answers(self.store, pend, [dict(row, output=5)])["stored"], 0)
        self.assertEqual(ai_live.import_answers(self.store, pend, [dict(row, output="")],
                                                allow_empty=("plan.v1",))["stored"], 1)

    def test_a_conflicting_answer_is_refused_and_the_first_stays(self):
        call = a_call()
        pend = {call["call_id"]: call}
        row = {"call_id": call["call_id"], "prompt_fp": call["prompt_fp"]}
        ai_live.import_answers(self.store, pend, [dict(row, output="first")])
        res = ai_live.import_answers(self.store, pend, [dict(row, output="second")])
        self.assertEqual(res["stored"], 0)
        self.assertEqual(len(res["refused"]), 1)
        self.assertEqual(self.store.answers()[call["call_id"]], "first")
        same = ai_live.import_answers(self.store, pend, [dict(row, output="first")])
        self.assertEqual((same["stored"], same["already"]), (0, 1))

    def test_one_file_that_answers_a_call_twice_differently_is_refused_whole(self):
        call = a_call()
        row = {"call_id": call["call_id"], "prompt_fp": call["prompt_fp"]}
        res = ai_live.import_answers(self.store, {call["call_id"]: call}, [dict(row, output="a"), dict(row, output="b")])
        self.assertEqual(res["stored"], 0)
        self.assertEqual(len(res["refused"]), 2)

    def test_a_bad_line_does_not_stop_the_good_ones(self):
        c1, c2 = a_call("one"), a_call("two")
        pend = {c1["call_id"]: c1, c2["call_id"]: c2}
        res = ai_live.import_answers(self.store, pend, [
            {"call_id": c1["call_id"], "prompt_fp": "bad", "output": "x"},
            {"call_id": c2["call_id"], "prompt_fp": c2["prompt_fp"], "output": "y"}])
        self.assertEqual((res["stored"], len(res["refused"])), (1, 1))

    def test_replay_serves_stored_answers_and_names_a_missing_call(self):
        call = a_call()
        ai_live.import_answers(self.store, {call["call_id"]: call},
                               [{"call_id": call["call_id"], "prompt_fp": call["prompt_fp"], "output": "kept text"}])
        ai = ai_mod.replay_ai(ai_live.replay_rows(self.store))
        # a call the store holds, made by the real call id of a real prompt
        cid = ai_mod.call_id_of("watcher.v1", {"from": "a"})
        self.assertNotEqual(cid, call["call_id"])
        with self.assertRaises(AICallMissing) as ctx:
            ai("watcher.v1", {"from": "a"})
        self.assertEqual(ctx.exception.call_id, cid)

    def test_a_judge_answer_must_have_the_form_asked_for(self):
        check = judge.make_validator(D)
        call = dict(a_call(pid="judge.v1"), expects="verdict")
        check("VERDICT kept", call)
        for bad in ("kept", "LEVEL high", "VERDICT maybe", "I think it is fine"):
            with self.assertRaises(ContractError, msg=bad):
                check(bad, call)
        level_call = dict(call, expects="level")
        check("LEVEL very low", level_call)
        with self.assertRaises(ContractError):
            check("LEVEL medium", level_call)

    def test_the_method_is_masked_in_what_helpers_see_and_one_answer_serves_equal_prompts(self):
        real = "own log: v0001.A+.r0#3 send\nv0001.B.r0#4 delete"
        c1 = ai_live.make_call("1" * 64, "reviewer.v1", real, "text")
        c2 = ai_live.make_call("2" * 64, "reviewer.v1", real.replace("A+", "C").replace(".B.", ".A."), "text")
        self.assertEqual(c1["prompt"], "own log: v0001.X.r0#3 send\nv0001.X.r0#4 delete")
        self.assertEqual(c1["prompt_fp"], fingerprint(c1["prompt"]))
        self.assertEqual(c1["prompt_fp"], c2["prompt_fp"])
        col = ai_live.Collector()
        col.add(c1)
        col.add(c2)
        col.add(ai_live.make_call("3" * 64, "reviewer.v1", "another", "text"))
        self.assertEqual((len(col), col.call_ids()), (2, 3))
        row = col.rows()[0]
        self.assertEqual(row["real"], ["1" * 64, "2" * 64])  # H1: one exported id, both real ids behind it
        self.assertEqual(row["call_id"], c2["call_id"])
        res = ai_live.import_answers(self.store, {r["call_id"]: r for r in col.rows()},
                                     [{"call_id": row["call_id"], "prompt_fp": row["prompt_fp"], "output": "FLAG 6 x"}],
                                     allow_empty=("reviewer.v1",))
        self.assertEqual(res["stored"], 2)
        self.assertEqual(self.store.answers(), {"1" * 64: "FLAG 6 x", "2" * 64: "FLAG 6 x"})

    def test_the_pending_file_is_written_and_removed(self):
        call = a_call()
        path = ai_live.export_missing(self.tmp.name, [call])
        self.assertTrue(path.exists())
        self.assertEqual(list(ai_live.read_pending(self.tmp.name)), [call["call_id"]])
        ai_live.export_missing(self.tmp.name, [])
        self.assertFalse(path.exists())
        self.assertNotIn("fields", call)  # a call carries its prompt and no fields


# --------------------------------------------------------------- the judge

def job_for(rule, text, visit=None):
    visit = visit or {"visit_id": "v0001", "evidence": [{"source_id": "pmid:1", "title": "t", "text": "x"}],
                      "given_answer": None, "given_by": None, "expert_certainty": "moderate", "split": "tune"}
    return judge._job({"visit_id": visit["visit_id"], "item_id": "i" * 16, "text": text}, visit, rule)


class Judge(unittest.TestCase):
    def test_the_prompt_file_is_in_use_and_has_only_known_slots(self):
        self.assertEqual(D["prompts"]["judge"], "judge.v1")
        text = (ROOT / "prompts" / "judge.v1.txt").read_text(encoding="utf-8")
        slots = set(re.findall(r"\{\{(\w+)\}\}", text))
        self.assertTrue(slots <= set(D["prompts"]["fields"]["judge"]) | set(D["prompts"]["fields"]["every_prompt"]))
        for marker in (D["markers"]["claim"], D["markers"]["source_tag"]["open"], D["markers"]["ai"]):
            self.assertNotIn(marker, text)
        self.assertNotIn(chr(0x2014), text)

    def test_the_judge_gets_only_the_allowed_fields_and_no_method_or_label(self):
        job = job_for(4, "The drug helps, says the review.")
        fields = judge.judge_fields(job, D)
        self.assertEqual(set(fields), set(D["prompts"]["fields"]["judge"]) | set(D["prompts"]["fields"]["every_prompt"]))
        prompt = ai_mod.render_prompt("judge.v1", fields)
        for word in ("run_id", "condition", "signal", "label", "record", "watcher", "gate", "witness", "ledger", "receipt"):
            self.assertNotIn(word, prompt.lower(), word)
        self.assertNotRegex(prompt, r"v\d{4}\.(A\+|A|B|C)\.r\d")
        for name in ("item_id", "visit_id"):
            self.assertNotIn(name, fields)

    def test_a_run_id_inside_a_field_is_refused(self):
        job = job_for(6, "text about v0001.A+.r0 here")
        with self.assertRaises(ContractError):
            judge.judge_fields(job, D)
        with self.assertRaises(ContractError):
            judge.blind_check({"text": "x", "true_sources": "", "rule": "", "condition": "B"})

    def test_a_texts_row_with_a_run_id_and_extras_gives_a_job_without_them(self):
        visit = {"visit_id": "v0001", "evidence": [{"source_id": "pmid:1"}], "given_answer": None, "given_by": None,
                 "expert_certainty": "high", "split": "tune"}
        item = {"item_id": "a" * 16, "visit_id": "v0001", "kind": "plan", "text": "PLAN, no marks at all",
                "made_by": "plan", "parents": []}
        row = {"run_id": "v0001.B.r0", "place": "clinician", "t": 3, "item": item, "label": {"source": ["pmid:1"]}}
        jobs = judge.build_jobs([row], {"v0001": visit}, D)
        self.assertEqual({j["rule"] for j in jobs}, {4, 5, 6})
        for j in jobs:
            self.assertEqual(set(j) - {"reader_level"}, {"visit_id", "item_id", "rule", "text", "true_sources", "grade"})
            self.assertNotIn("v0001.B", canon(judge.judge_fields(j, D)))
        # the same item seen in four runs is judged once for each rule
        rows = [dict(row, run_id="v0001.%s.r0" % c) for c in ("A", "A+", "B", "C")]
        self.assertEqual(len(judge.build_jobs(rows, {"v0001": visit}, D)), 3)

    def test_only_unreadable_texts_become_jobs(self):
        visit = {"visit_id": "v0001", "evidence": [{"source_id": "pmid:1"}], "given_answer": None, "given_by": None,
                 "expert_certainty": "moderate", "split": "tune"}
        good = "PLAN\nClaim: X probably reduces Y [source: pmid:1]\n[AI-generated]"
        item = {"item_id": "b" * 16, "visit_id": "v0001", "kind": "plan", "text": good, "made_by": "plan", "parents": []}
        # Version 2, part 3: under rules.key_source "judge" the judge gets every advice text, once for each of rules 4 to 6
        self.assertEqual([j["rule"] for j in judge.build_jobs([{"run_id": "r", "place": "p", "t": 1, "item": item}], {"v0001": visit}, D)], [4, 5, 6])
        note = dict(item, kind="note", item_id="c" * 16, text="no marks")  # a note is not an advice kind
        self.assertEqual(judge.build_jobs([{"run_id": "r", "place": "p", "t": 1, "item": note}], {"v0001": visit}, D), [])

    def test_the_judge_agrees_with_the_scorer_on_which_texts_it_must_read(self):
        visit = {"visit_id": "v1", "evidence": [{"source_id": "pmid:1"}], "given_answer": None, "given_by": None,
                 "expert_certainty": "low"}
        ungraded = dict(visit, expert_certainty=None)
        samples = ["", "Claim: may help", "Claim: may help [source: pmid:1]\n[AI-generated]", "[AI-generated]",
                   "plain words [source: pmid:2]", "Claim: likely [source: x]", "mentions [AI-generated] inline"]
        for v in (visit, ungraded):
            for text in samples:
                for rule in (4, 5, 6):
                    self.assertEqual(judge.needs_judge(rule, text, v, D), score.needs_judge(rule, text, v, D), (rule, text))
                    pv = judge.program_verdict(rule, text, v, D)
                    if pv is not None and not (rule == 5 and v["expert_certainty"] is None):
                        self.assertEqual(pv, score.text_verdict(rule, text, v, D, None), (rule, text))

    def test_verdicts_from_replies(self):
        self.assertEqual(judge.verdict_of(4, "VERDICT kept", None, D), "kept")
        self.assertEqual(judge.verdict_of(6, "verdict: Broken.", None, D), "broken")
        self.assertEqual(judge.verdict_of(5, "LEVEL moderate", "moderate", D), "kept")
        self.assertEqual(judge.verdict_of(5, "LEVEL high", "moderate", D), "broken")
        self.assertEqual(judge.verdict_of(5, "LEVEL none", "moderate", D), "undecided")
        self.assertEqual(judge.verdict_of(5, "extra words\nLEVEL very low", "very low", D), "kept")
        for rule, bad in ((4, "LEVEL high"), (5, "VERDICT kept"), (5, "LEVEL medium"), (6, "maybe")):
            with self.assertRaises(ContractError, msg=(rule, bad)):
                judge.verdict_of(rule, bad, "high", D)

    def test_a_judge_without_an_answer_yields_no_row_when_lenient_and_raises_otherwise(self):
        job = job_for(4, "no marks here")
        self.assertEqual(judge.judge_jobs(lambda p, f: "", [job], D, lenient=True), [])
        with self.assertRaises(ContractError):
            judge.judge_jobs(lambda p, f: "", [job], D)

        def missing(pid, fields):
            raise AICallMissing("c", pid, fields)

        with self.assertRaises(AICallMissing):
            judge.judge_jobs(missing, [job], D, lenient=True)
        rows = judge.judge_jobs(lambda p, f: "VERDICT broken", [job], D)
        self.assertEqual(rows, [{"visit_id": "v0001", "item_id": "i" * 16, "rule": 4, "verdict": "broken",
                                 "judge": "live", "prompt_id": "judge.v1"}])
        self.assertNotIn("run_id", rows[0])

    def test_the_marked_sample_is_test_visits_only_and_repeatable(self):
        def mk(n, split):
            vid = "v%04d" % n
            visit = {"visit_id": vid, "evidence": [{"source_id": "pmid:1"}], "given_answer": None, "given_by": None,
                     "expert_certainty": "high", "split": split}
            item = {"item_id": ("%016x" % n), "visit_id": vid, "kind": "answer", "made_by": "ai_answer", "parents": [],
                    "text": "Claim: X reduces Y [source: pmid:1]\n[AI-generated]"}
            return visit, {"run_id": vid + ".A.r0", "place": "p", "t": 1, "item": item}
        made = [mk(i, "tune" if i < 30 else "test") for i in range(1, 60)]
        vmap = {v["visit_id"]: v for v, _ in made}
        texts = [t for _, t in made]
        s1 = judge.sample_jobs(texts, vmap, D)
        s2 = judge.sample_jobs(list(reversed(texts)), vmap, D)
        self.assertEqual(s1, s2)
        self.assertEqual(len(s1), D["rules"]["judge_marked_sample"])
        self.assertTrue(all(vmap[j["visit_id"]]["split"] == "test" for j in s1))
        self.assertEqual(len(judge.build_jobs(texts, vmap, D)), 59 * 3)  # every advice text, three rules

    def test_compare_reports_where_judge_and_readers_differ(self):
        visit = {"visit_id": "v0001", "evidence": [{"source_id": "pmid:1"}], "given_answer": None, "given_by": None,
                 "expert_certainty": "high", "split": "test"}
        job = job_for(6, "Claim: X [source: pmid:1]\n[AI-generated]", visit)
        row = {"visit_id": "v0001", "item_id": job["item_id"], "rule": 6, "verdict": "broken", "judge": "live",
               "prompt_id": "judge.v1"}
        out = judge.compare_with_readers([row], [job], {"v0001": visit}, D)
        self.assertEqual((out["judged"], out["agree"], out["differ"]), (1, 0, 1))
        self.assertEqual(out["differences"][0]["readers"], "kept")


# ------------------------------------------------- the round trip and the split

class RoundTrip(unittest.TestCase):
    @needs_raw_data
    def test_a_full_round_trip_with_canned_helper_answers(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = small_visits(tmp, tune=2)
            rounds = round_trip(tmp, vpath, "--conditions", "A,A+,B")
            self.assertGreaterEqual(rounds, 4)  # the plan, the note, the monitor, then the judge (version 3: no AI answer step)
            run_dir = Path(tmp) / "runs" / "advice_tune_e2"
            for name in ("results.jsonl", "texts.jsonl", "judge.jsonl", "scores.json", "manifest.json"):
                self.assertTrue((run_dir / name).exists(), name)
            results = store.read_jsonl(run_dir / "results.jsonl")
            self.assertEqual(len(results), len(keep) * 3)
            self.assertFalse(any(r["crashed"] for r in results))
            judged = store.read_jsonl(run_dir / "judge.jsonl")
            self.assertTrue(judged)
            for row in judged:
                self.assertEqual(set(row) - {"level", "reader_level"}, {"visit_id", "item_id", "rule", "verdict", "judge", "prompt_id"})
                self.assertEqual("level" in row, row["rule"] == 5)  # 13 Nov, G7: rule 5 rows carry the reported level
                self.assertIn(row["verdict"], ("kept", "broken", "undecided"))
            # the scorer read the judge file: every text it needed is judged
            scores = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
            cells = [c for rule in ("4", "5", "6") for c in scores["practice"]["table"][rule].values()]
            self.assertTrue(cells)
            self.assertTrue(all(c["unjudged"] == 0 for c in cells), [c["unjudged"] for c in cells])

    @needs_raw_data
    def test_a_finished_run_scores_again_with_no_ai(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = small_visits(tmp, tune=1)
            round_trip(tmp, vpath, "--conditions", "A,B")
            run_dir = Path(tmp) / "runs" / "advice_tune_e2"
            first = (run_dir / "scores.json").read_bytes()
            answers = (Path(tmp) / "live" / "answers.jsonl").read_bytes()
            # a program that cannot call out: the run uses stored answers only
            self.assertEqual(TOOL.main(["run"] + args(tmp, vpath, "--conditions", "A,B")), 0)
            self.assertEqual((run_dir / "scores.json").read_bytes(), first)
            self.assertEqual((Path(tmp) / "live" / "answers.jsonl").read_bytes(), answers)
            self.assertFalse((Path(tmp) / "live" / "pending.jsonl").exists())
            # and scoring alone, from the files, gives the same again
            import json as _json
            wiring = _json.loads((ROOT / "wiring" / "wiring.json").read_text(encoding="utf-8"))
            again = score.score_run(run_dir, wiring, D, str(Path(tmp) / "filing"))  # the run's own filing folder, not the project's
            self.assertEqual(canon(again), canon(_json.loads(first.decode("utf-8"))))

    def test_the_pending_file_holds_prompts_and_never_the_grade_or_the_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = small_visits(tmp, tune=1)
            self.assertEqual(TOOL.main(["run"] + args(tmp, vpath, "--conditions", "A")), TOOL.WAITING)
            pending = ai_live.read_pending(Path(tmp) / "live")
            self.assertEqual({c["prompt_id"] for c in pending.values()}, {"plan.v1"})  # version 3: the advice lane starts at the plan
            for c in pending.values():
                self.assertEqual(set(c) - {"real"}, {"call_id", "also", "prompt_id", "prompt", "prompt_fp", "expects"})
                self.assertEqual(c["prompt_fp"], fingerprint(c["prompt"]))
                # version 3: the answer enters with the experts' conclusion in its words, so the prompt shows it by design
                self.assertNotIn('"grade"', c["prompt"])
        # the plan prompt never holds the expert grade slot
        self.assertNotIn("{{grade}}", ai_mod.prompt_text("plan.v1"))

    def test_a_mismatched_answer_through_the_tool_is_refused_and_the_call_stays_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = small_visits(tmp, tune=1)
            more = ["--conditions", "A"]
            TOOL.main(["run"] + args(tmp, vpath, *more))
            pending = ai_live.read_pending(Path(tmp) / "live")
            out = Path(tmp) / "bad.jsonl"
            call = list(pending.values())[0]
            with open(str(out), "w", encoding="utf-8") as fh:
                fh.write(canon({"call_id": call["call_id"], "prompt_fp": fingerprint("some other prompt"),
                                "output": "text"}) + "\n")
                fh.write(canon({"call_id": "f" * 64, "prompt_fp": call["prompt_fp"], "output": "text"}) + "\n")
            self.assertEqual(TOOL.main(["import", str(out)] + args(tmp, vpath, *more)), 1)
            self.assertEqual(ai_live.AnswerStore(Path(tmp) / "live").answers(), {})
            self.assertEqual(TOOL.main(["run"] + args(tmp, vpath, *more)), TOOL.WAITING)
            self.assertIn(call["call_id"], ai_live.read_pending(Path(tmp) / "live"))

    @needs_raw_data
    def test_no_pending_prompt_shows_a_condition_letter(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = small_visits(tmp, tune=1)
            seen = []
            round_trip(tmp, vpath, "--conditions", "A,A+,B", seen=seen)
            self.assertTrue(any(c["prompt_id"].startswith("reviewer") for c in seen))
            for c in seen:
                self.assertNotRegex(c["prompt"], r"v\d{4}\.(A\+|A|B|C)\.r\d")
            # the three conditions' reviewer prompts show the same text, so one answer serves them
            reviewer = [c for c in seen if c["prompt_id"].startswith("reviewer")]
            # Version 2: the one visit now gets F12 (the first fault of the advice lane it can take), which edits the
            # first line of the own log under A and A+ (the intake line) but not the journal of B: two prompts, three runs
            # Part 3 (13 Nov, builder B1b): Checked does not count the review's signals (conditions.B.signals_counted),
            # so its review's AI part is not asked: one prompt, shared by Promised and Monitored
            self.assertEqual(len(reviewer), 1)
            self.assertEqual(sorted(len(c["real"]) for c in reviewer), [2])

    def test_the_mask_hides_a_condition_word_that_is_not_a_run_id(self):
        for raw in ("cond=A+", "condition: B", "Condition = C", "cond: A"):
            shown = ai_live.mask_method("the log says " + raw + " here")
            self.assertNotRegex(shown, r"(A\+|[=:]\s*[ABC]\b)")
        self.assertNotRegex(ai_live.mask_method("v0001.A+.r0#3 and v0002.C.r1"), r"\.(A|B|C)\.r|A\+")

    @needs_raw_data
    def test_no_pending_prompt_shows_a_condition_word(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = small_visits(tmp, tune=1)
            seen = []
            round_trip(tmp, vpath, "--conditions", "A,A+,B", seen=seen)
            for c in seen:
                self.assertNotIn("A+", c["prompt"])
                self.assertNotRegex(c["prompt"], r"\.(A|B|C)\.r")
                self.assertNotRegex(c["prompt"], r"(?i)cond(ition)?s?\s*[=:]\s*(A|B|C)\b")

    def test_sealed_needs_the_test_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = small_visits(tmp, tune=1)
            self.assertEqual(TOOL.main(["status", "--sealed"] + args(tmp, vpath)), 0)  # status never plans faults
            self.assertEqual(TOOL.main(["export", "--sealed", "--split", "tune"] + args(tmp, vpath)), 2)

    def test_test_runs_freeze_the_prompts(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = small_visits(tmp, tune=0, test=1)
            file_predictions(tmp)
            TOOL.main(["export", "--split", "test", "--conditions", "A"] + args(tmp, vpath))
            fz = Path(tmp) / "live" / "frozen.json"
            self.assertTrue(fz.exists())
            rec = json.loads(fz.read_text(encoding="utf-8"))
            self.assertTrue({"prompt:" + p for p in TOOL.prompt_ids(datasets.default_choices())} <= set(rec["fingerprints"]))
            rec["accepted"] = {k: "0" * 64 for k in rec["accepted"]}
            fz.write_text(json.dumps(rec), encoding="utf-8")
            self.assertEqual(TOOL.main(["export", "--split", "test", "--conditions", "A"] + args(tmp, vpath)), 2)

    @needs_raw_data
    def test_a_judge_answer_of_the_wrong_form_is_refused_through_the_tool(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = small_visits(tmp, tune=1)
            more = ["--conditions", "A"]
            for n in range(20):
                code = TOOL.main(["run"] + args(tmp, vpath, *more))
                pending = ai_live.read_pending(Path(tmp) / "live")
                if any(c["prompt_id"].startswith("judge") for c in pending.values()):
                    break
                out = Path(tmp) / ("a%d.jsonl" % n)
                write_answers(list(pending.values()), out)
                TOOL.main(["import", str(out)] + args(tmp, vpath, *more))
            judge_calls = [c for c in pending.values() if c["prompt_id"].startswith("judge")]
            self.assertTrue(judge_calls, "the round trip never reached the judge")
            out = Path(tmp) / "wrong.jsonl"
            write_answers(judge_calls, out, fn=lambda c: "It reads fine to me.")
            self.assertEqual(TOOL.main(["import", str(out)] + args(tmp, vpath, *more)), 1)
            self.assertTrue(all(c["call_id"] not in ai_live.AnswerStore(Path(tmp) / "live").answers() for c in judge_calls))

    def test_tuning_and_test_visits_are_kept_apart(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, keep = small_visits(tmp, tune=2, test=2)
            every = visits.read_visits(str(vpath))
            self.assertEqual({v.split for v in TOOL.select(every, "tune")}, {"tune"})
            self.assertEqual({v.split for v in TOOL.select(every, "test")}, {"test"})
            self.assertEqual(len(TOOL.select(every, "all")), 4)
            # the default is tuning only: the calls a first pass asks for belong to tuning visits
            self.assertEqual(TOOL.main(["run"] + args(tmp, vpath, "--conditions", "A")), TOOL.WAITING)
            pending = ai_live.read_pending(Path(tmp) / "live")
            tune_visits = {v.visit_id: v for v in keep if v.split == "tune"}
            test_ids = {v.visit_id for v in keep if v.split == "test"}
            self.assertEqual(len(pending), len(tune_visits))
            for call in pending.values():
                self.assertTrue(any(v.question.strip()[:200] in call["prompt"] for v in tune_visits.values()))
                self.assertFalse(any(v.question.strip()[:200] in call["prompt"] for v in keep if v.visit_id in test_ids))
            # a tuning run does not read the test visits and a test run needs --split test
            file_predictions(tmp)
            args_test = args(tmp, vpath, "--split", "test", "--conditions", "A")
            self.assertEqual(TOOL.main(["run"] + args_test), TOOL.WAITING)
            test_pending = ai_live.read_pending(Path(tmp) / "live")
            self.assertEqual(len(test_pending), 2)
            self.assertFalse(set(test_pending) & set(pending))

    @needs_raw_data
    def test_the_run_folders_of_the_two_splits_differ_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = small_visits(tmp, tune=1, test=1)
            file_predictions(tmp)
            round_trip(tmp, vpath, "--conditions", "A")
            round_trip(tmp, vpath, "--split", "test", "--conditions", "A")
            tune_dir, test_dir = Path(tmp) / "runs" / "advice_tune_e2", Path(tmp) / "runs" / "advice_test_e2"
            self.assertEqual({r["split"] for r in store.read_jsonl(tune_dir / "results.jsonl")}, {"tune"})
            self.assertEqual({r["split"] for r in store.read_jsonl(test_dir / "results.jsonl")}, {"test"})
            # the marked sample draws from test visits only, so the tuning run has none
            self.assertTrue((tune_dir / "judge_sample.jsonl").exists())  # 14 Nov (H6): a tuning run gets a marked sample too

    def test_export_writes_only_the_chain_calls_and_changes_no_answer(self):
        with tempfile.TemporaryDirectory() as tmp:
            vpath, _ = small_visits(tmp, tune=1)
            more = ["--conditions", "A"]
            self.assertEqual(TOOL.main(["export"] + args(tmp, vpath, *more)), TOOL.WAITING)
            live = Path(tmp) / "live"
            first = ai_live.read_pending(live)
            self.assertEqual(TOOL.main(["export"] + args(tmp, vpath, *more)), TOOL.WAITING)
            self.assertEqual(ai_live.read_pending(live), first)  # twice gives the same, and invents no answer
            self.assertFalse((live / "answers.jsonl").exists())
            self.assertFalse((Path(tmp) / "runs").exists())  # no bench ran
            self.assertEqual(TOOL.main(["status"] + args(tmp, vpath)), 0)

    def test_batches_split_the_missing_calls(self):
        calls = [a_call(str(i)) for i in range(5)]
        self.assertEqual([len(b) for b in ai_live.split_batches(calls, 2)], [2, 2, 1])
        with self.assertRaises(ContractError):
            ai_live.split_batches(calls, 0)


if __name__ == "__main__":
    unittest.main()
