"""Acceptance tests for ADVICE: live AI answers by hand-off, the judge, and scoring again.

Written from docs/FRAME.md (sections 5, 7, 10), config/design_choices.json (D: prompts,
rules, store, exports, scoring) and the stored-run layout of D: store.

WHAT D DOES NOT SAY. D gives no signature for custody/ai_live.py, custody/judge.py or
tools/run_advice.py, and no command line for the tool. The tests therefore go through
the command-line tool, and every assumption about it sits in one block below
(ADVICE_CLI). If the real tool differs, change that block and nothing else; a test
that cannot reach the tool fails with a message that says which assumption broke.

  export  RUN_DIR --out FILE    writes one JSON line for every call that has no stored answer
                                (chain calls and judge calls): call_id, prompt_id, fields, prompt
  import  RUN_DIR --answers FILE reads lines of call_id, prompt_id, fields, output, prompt_fp
                                and stores them; a line whose prompt_fp is not the fingerprint
                                of the exported prompt is refused (exit code 1 or 2, no traceback)

Fixed by the contract, not assumed: call_id = fingerprint([prompt_id, fingerprint(prompt text),
fields]) (FRAME section 5); the judge's fields (D: prompts.fields.judge); judge.jsonl rows
(D: store.files); tools/score.py RUN_DIR; tuning and test visits (D: scoring).
"""
import copy
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from custody import core  # noqa: E402
from custody.core import canon, fingerprint  # noqa: E402

D = json.loads((ROOT / "config" / "design_choices.json").read_text(encoding="utf-8"))
W = json.loads((ROOT / "wiring" / "wiring.json").read_text(encoding="utf-8"))
TOOL = ROOT / "tools" / "run_advice.py"
SCORE_TOOL = ROOT / "tools" / "score.py"

# ---- ADVICE_CLI: the assumptions about the tool, in one place -------------------------
VERB_EXPORT = "export"
VERB_IMPORT = "import"
OPT_OUT = "--out"
OPT_ANSWERS = "--answers"
K_PROMPT = "prompt"          # key of the full prompt text in an exported line
K_PROMPT_FP = "prompt_fp"    # key of the prompt fingerprint in an answer line
# ----------------------------------------------------------------------------------------

JUDGE_ID = D["prompts"]["judge"]
JUDGE_FIELDS = set(D["prompts"]["fields"]["judge"])
EVERY = set(D["prompts"]["fields"]["every_prompt"])
JUDGE_ROW_KEYS = {"visit_id", "item_id", "rule", "verdict", "judge", "prompt_id"}

GUARD = '''
import socket, sys, os, importlib.abc
def _no(*a, **k):
    raise RuntimeError("NETWORK CALL ATTEMPTED: the program must never call a model itself")
socket.socket.connect = _no
socket.socket.connect_ex = _no
socket.create_connection = _no
socket.getaddrinfo = _no
_BLOCK = set(filter(None, os.environ.get("ACC_BLOCK_IMPORTS", "").split(",")))
_CLIENTS = {"anthropic", "openai", "requests", "httpx", "urllib3", "aiohttp"}
class _B(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name in _BLOCK or name.split(".")[0] in _CLIENTS:
            raise ImportError("blocked by the acceptance guard: " + name)
        return None
sys.meta_path.insert(0, _B())
'''

_STATE = {}


def setUpModule():
    """Build one small stored run (conditions A and B, no faults) with the public pipeline."""
    tmp = tempfile.mkdtemp(prefix="acc_advice_")
    _STATE["tmp"] = tmp
    guard = Path(tmp) / "guard"
    guard.mkdir()
    (guard / "sitecustomize.py").write_text(GUARD, encoding="utf-8")
    try:
        from custody import assemble, bench, datasets, store, visits
        choices = datasets.default_choices()
        wiring = assemble.load_wiring()
        rchoices = bench.run_choices(choices)
        keep = {"v0001", "v0002", "v0051", "v0052"}
        vs = [v for v in visits.build_visits(58, choices, ROOT / "data" / "raw") if v.visit_id in keep]
        plan = {v.visit_id: None for v in vs}
        run = Path(tmp) / "base"
        parts = assemble.make_parts(wiring, rchoices)
        bench.run_all(vs, ["A", "B"], plan, parts, wiring, choices, run)
        store.write_manifest(run, "acc", choices["seeds"], ["A", "B"], visits.visit_counts(vs),
                             assemble.manifest_fingerprints(choices, ROOT / "data" / "raw"))
        _STATE.update(run=run, choices=choices, wiring=wiring, visits=vs)
    except Exception as e:
        _STATE["error"] = "%s: %s" % (type(e).__name__, e)


def tearDownModule():
    shutil.rmtree(_STATE.get("tmp", ""), ignore_errors=True)


def jl(path):
    p = Path(path)
    if not p.exists():
        return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def write_jl(path, rows):
    Path(path).write_text("".join(canon(r) + "\n" for r in rows), encoding="utf-8")


class Base(unittest.TestCase):
    def setUp(self):
        if "error" in _STATE:
            self.fail("could not build the stored run the tests start from: %s" % _STATE["error"])
        self.work = Path(tempfile.mkdtemp(dir=_STATE["tmp"]))
        self.run_dir = self.work / "run"
        shutil.copytree(str(_STATE["run"]), str(self.run_dir))

    def tool(self, *args, script=TOOL, block=""):
        if not script.exists():
            self.fail("ADVICE is missing: %s does not exist" % script.relative_to(ROOT))
        env = dict(os.environ)
        env["PYTHONPATH"] = str(Path(_STATE["tmp"]) / "guard") + os.pathsep + env.get("PYTHONPATH", "")
        env["ACC_BLOCK_IMPORTS"] = block
        return subprocess.run([sys.executable, str(script)] + [str(a) for a in args], cwd=str(self.work), env=env,
                              capture_output=True, text=True, timeout=300)

    def export(self, name="out.jsonl"):
        out = self.work / name
        p = self.tool(VERB_EXPORT, self.run_dir, OPT_OUT, out)
        self.assertEqual(p.returncode, 0, "export failed (assumed command: %s %s RUN_DIR %s FILE): %s"
                         % (TOOL.name, VERB_EXPORT, OPT_OUT, (p.stderr or p.stdout)[-600:]))
        return jl(out)

    def edit_texts(self, fn):
        path = self.run_dir / "texts.jsonl"
        rows = jl(path)
        for r in rows:
            fn(r)
        write_jl(path, rows)

    def strip_patient_note(self, visit_ids, drop_mark=True, drop_tag=False):
        mark, tag = D["markers"]["ai"], D["markers"]["source_tag"]["open"]

        def fn(r):
            it = r["item"]
            if it["kind"] == "patient_note" and it["visit_id"] in visit_ids:
                lines = it["text"].splitlines()
                if drop_mark:
                    lines = [x for x in lines if x.strip() != mark]
                if drop_tag:
                    lines = [x.split(tag)[0].rstrip() for x in lines]
                it["text"] = "\n".join(lines)
        self.edit_texts(fn)

    def strip_chain_answers(self):
        (self.run_dir / "ai_calls.jsonl").write_text("", encoding="utf-8")


class ModulesAndPrompt(unittest.TestCase):
    def test_parts_exist(self):
        for rel in ("custody/ai_live.py", "custody/judge.py", "tools/run_advice.py", "prompts/judge.v1.txt"):
            self.assertTrue((ROOT / rel).exists(), "ADVICE is missing: %s" % rel)

    def test_judge_prompt_id_is_judge_v1_and_file_matches(self):
        self.assertEqual(JUDGE_ID, "judge.v1")
        self.assertTrue((ROOT / "prompts" / (JUDGE_ID + ".txt")).exists(), "the judge prompt file is missing")

    def test_judge_prompt_slots_are_the_judge_fields_only(self):
        import re
        text = (ROOT / "prompts" / "judge.v1.txt").read_text(encoding="utf-8")
        slots = set(re.findall(r"\{\{\s*([A-Za-z_]+)\s*\}\}", text))
        self.assertTrue(slots, "the judge prompt has no slots")
        extra = slots - JUDGE_FIELDS - EVERY
        self.assertEqual(extra, set(), "the judge prompt names fields it is not given: %s" % sorted(extra))
        self.assertIn("text", slots, "the judge must be shown the text")
        self.assertIn("rule", slots, "the judge must be told the rule")

    def test_judge_prompt_holds_no_marker_as_literal_text(self):
        text = (ROOT / "prompts" / "judge.v1.txt").read_text(encoding="utf-8")
        for m in (D["markers"]["claim"], D["markers"]["source_tag"]["open"], D["markers"]["ai"]):
            self.assertNotIn(m, text, "D: prompts says no prompt holds the marker %r as literal text" % m)

    def test_judge_prompt_never_names_what_it_must_not_see(self):
        text = (ROOT / "prompts" / "judge.v1.txt").read_text(encoding="utf-8").lower()
        for w in ("run_id", "condition", "signal", "journal", "{{label", "{{method", "{{record"):
            self.assertNotIn(w, text, "the judge prompt mentions %r" % w)

    def test_earlier_step_prompts_are_untouched_new_versions_are_new_files(self):
        for step in ("note_writer", "ai_answer", "plan", "patient_note"):
            self.assertTrue((ROOT / "prompts" / ("%s.v1.txt" % step)).exists(), "%s.v1.txt was removed" % step)
            self.assertEqual(D["prompts"][step], step + ".v1", "D still names version 1 of %s" % step)


class NeverCallsAModel(Base):
    def test_no_network_or_model_client_is_imported(self):
        banned = {"socket", "ssl", "http", "urllib", "urllib3", "requests", "httpx", "aiohttp", "anthropic",
                  "openai", "subprocess", "ftplib", "smtplib", "xmlrpc", "asyncio"}
        for rel in ("custody/ai_live.py", "custody/judge.py", "tools/run_advice.py"):
            p = ROOT / rel
            self.assertTrue(p.exists(), "ADVICE is missing: %s" % rel)
            tree = ast.parse(p.read_text(encoding="utf-8"))
            names = set()
            for n in ast.walk(tree):
                if isinstance(n, ast.Import):
                    names |= {a.name.split(".")[0] for a in n.names}
                elif isinstance(n, ast.ImportFrom) and n.module:
                    names.add(n.module.split(".")[0])
            self.assertEqual(names & banned, set(), "%s imports %s" % (rel, sorted(names & banned)))

    def test_export_runs_with_every_network_call_and_client_blocked(self):
        self.strip_chain_answers()
        rows = self.export()  # the guard raises on any connection; a crash shows as a failed export
        self.assertGreater(len(rows), 0)

    def test_help_exits_cleanly_and_names_both_verbs(self):
        p = self.tool("--help")
        self.assertEqual(p.returncode, 0, "run_advice.py --help failed: %s" % p.stderr[-300:])
        for v in (VERB_EXPORT, VERB_IMPORT):
            self.assertIn(v, p.stdout, "assumption ADVICE_CLI broke: the help does not name the verb %r" % v)


class MissingCallsExported(Base):
    def test_a_run_with_no_stored_answers_exports_chain_calls(self):
        self.strip_chain_answers()
        rows = self.export()
        ids = {r["prompt_id"] for r in rows}
        self.assertIn("note_writer.v1", ids, "the first call of the words lane must be exported; got %s" % sorted(ids))

    def test_every_exported_line_has_its_full_prompt_with_no_open_slot(self):
        self.strip_chain_answers()
        for r in self.export():
            self.assertIn(K_PROMPT, r, "assumption ADVICE_CLI broke: no key %r in %s" % (K_PROMPT, sorted(r)))
            self.assertIsInstance(r[K_PROMPT], str)
            self.assertGreater(len(r[K_PROMPT]), 40, "the prompt text is empty or cut")
            self.assertNotIn("{{", r[K_PROMPT], "a slot was left unfilled in %s" % r["prompt_id"])

    def test_the_prompt_holds_the_visits_own_words(self):
        self.strip_chain_answers()
        conv = {v.conversation for v in _STATE["visits"]}
        got = [r for r in self.export() if r["prompt_id"] == "note_writer.v1"]
        self.assertTrue(got)
        for r in got:
            self.assertIn(r["fields"]["transcript"], conv)
            self.assertIn(r["fields"]["transcript"][:80], r[K_PROMPT], "the field does not reach the prompt text")

    def test_call_id_is_the_fingerprint_of_prompt_id_prompt_fingerprint_and_fields(self):
        self.strip_chain_answers()
        for r in self.export():
            want = fingerprint([r["prompt_id"], fingerprint(r[K_PROMPT]), r["fields"]])
            self.assertEqual(r["call_id"], want, "call_id of %s breaks FRAME section 5" % r["prompt_id"])

    def test_the_same_call_is_exported_once(self):
        self.strip_chain_answers()
        ids = [r["call_id"] for r in self.export()]
        self.assertEqual(len(ids), len(set(ids)), "one stored text serves all four conditions: no duplicate calls")

    def test_the_every_prompt_fields_are_filled_by_the_caller(self):
        self.strip_chain_answers()
        for r in self.export():
            self.assertTrue(EVERY <= set(r["fields"]), "%s lacks %s" % (r["prompt_id"], sorted(EVERY - set(r["fields"]))))

    def test_answered_calls_are_not_exported_again(self):
        rows = self.export("before.jsonl")
        self.assertEqual([r for r in rows if r["prompt_id"] != JUDGE_ID], [],
                         "the stored run holds every chain answer, so no chain call may be missing")


class ImportAndFingerprint(Base):
    def _answers(self, rows, **over):
        out = []
        for r in rows:
            a = {"call_id": r["call_id"], "prompt_id": r["prompt_id"], "fields": r["fields"], "output": "ok text",
                 K_PROMPT_FP: fingerprint(r[K_PROMPT])}
            a.update(over)
            out.append(a)
        return out

    def _import(self, answers):
        f = self.work / "answers.jsonl"
        write_jl(f, answers)
        return self.tool(VERB_IMPORT, self.run_dir, OPT_ANSWERS, f)

    def test_an_answer_with_the_right_fingerprint_is_accepted_and_no_longer_missing(self):
        self.strip_chain_answers()
        rows = self.export("a.jsonl")
        first = [r for r in rows if r["prompt_id"] == "note_writer.v1"][:1]
        p = self._import(self._answers(first))
        self.assertEqual(p.returncode, 0, "import refused a good answer: %s" % (p.stderr or p.stdout)[-400:])
        left = {r["call_id"] for r in self.export("b.jsonl")}
        self.assertNotIn(first[0]["call_id"], left, "an accepted answer must stop the call being missing")

    def test_an_answer_whose_prompt_fingerprint_does_not_match_is_refused(self):
        self.strip_chain_answers()
        rows = self.export("a.jsonl")
        first = [r for r in rows if r["prompt_id"] == "note_writer.v1"][:1]
        p = self._import(self._answers(first, **{K_PROMPT_FP: "0" * 64}))
        self.assertIn(p.returncode, (1, 2), "a bad fingerprint must give exit code 1 or 2, got %s" % p.returncode)
        self.assertNotIn("Traceback", p.stderr, "refuse with one line, not a crash (FRAME section 11)")
        left = {r["call_id"] for r in self.export("b.jsonl")}
        self.assertIn(first[0]["call_id"], left, "a refused answer must leave the call missing")

    def test_an_answer_for_a_prompt_that_has_since_changed_is_refused(self):
        self.strip_chain_answers()
        rows = self.export("a.jsonl")
        first = [r for r in rows if r["prompt_id"] == "note_writer.v1"][:1]
        p = self._import(self._answers(first, **{K_PROMPT_FP: fingerprint(first[0][K_PROMPT] + " changed")}))
        self.assertIn(p.returncode, (1, 2))

    def test_one_bad_line_stores_none_of_the_batch(self):
        self.strip_chain_answers()
        rows = self.export("a.jsonl")
        some = rows[:2]
        self.assertGreaterEqual(len(some), 2, "need two missing calls for this test")
        ans = self._answers(some)
        ans[1][K_PROMPT_FP] = "f" * 64
        p = self._import(ans)
        self.assertIn(p.returncode, (1, 2))
        left = {r["call_id"] for r in self.export("b.jsonl")}
        self.assertIn(some[0]["call_id"], left, "a batch with a bad line must store nothing")

    def test_a_missing_call_is_never_filled_by_the_program(self):
        self.strip_chain_answers()
        a = {r["call_id"] for r in self.export("a.jsonl")}
        b = {r["call_id"] for r in self.export("b.jsonl")}
        self.assertEqual(a, b, "exporting twice must change nothing and invent no answer")
        self.assertEqual(jl(self.run_dir / "ai_calls.jsonl"), [], "export must not write answers")


class JudgeIsBlind(Base):
    def _judge_rows(self):
        return [r for r in self.export() if r["prompt_id"] == JUDGE_ID]

    def setUp(self):
        super().setUp()
        self.strip_patient_note({"v0051", "v0052"}, drop_mark=True)
        self.strip_patient_note({"v0052"}, drop_mark=False, drop_tag=True)

    def test_texts_the_program_cannot_read_are_exported_as_judge_calls(self):
        rows = self._judge_rows()
        self.assertGreater(len(rows), 0, "a patient note with no AI mark is left to the judge (D: rules.left_to_judge)")
        self.assertTrue({"4", "6"} <= {str(r["fields"]["rule"]).strip()[:1] for r in rows} or
                        {4, 6} <= {r["fields"]["rule"] for r in rows} or len(rows) >= 2,
                        "rules 4 and 6 both have a text with no tag or no mark")

    def test_judge_fields_are_exactly_the_documented_ones(self):
        for r in self._judge_rows():
            self.assertTrue(JUDGE_FIELDS <= set(r["fields"]), "missing %s" % sorted(JUDGE_FIELDS - set(r["fields"])))
            self.assertTrue(set(r["fields"]) <= JUDGE_FIELDS | EVERY,
                            "the judge is given more than text, true sources, grade and rule: %s"
                            % sorted(set(r["fields"]) - JUDGE_FIELDS - EVERY))

    def test_no_method_name_run_id_or_label_reaches_the_judge(self):
        run_ids = {r["run_id"] for r in jl(self.run_dir / "results.jsonl")}
        self.assertTrue(run_ids)
        for r in self._judge_rows():
            blob = json.dumps(r, ensure_ascii=False)
            for rid in run_ids:
                self.assertNotIn(rid, blob, "a run id reaches the judge")
            self.assertNotIn("run_id", r, "the judge line must carry no run_id")
            self.assertNotIn("condition", r)
            for word in ("delete_by", '"allowed"', "\"ai_made\"", "witness", "journal"):
                self.assertNotIn(word, blob, "%s reaches the judge: labels and records are never shown" % word)

    def test_the_judge_is_given_the_true_sources_and_grade_of_the_visit(self):
        ev = {v.visit_id: [e["source_id"] for e in v.evidence] for v in _STATE["visits"]}
        allsrc = {s for xs in ev.values() for s in xs}
        for r in self._judge_rows():
            ts = r["fields"]["true_sources"]
            ts = ts if isinstance(ts, list) else [x.strip() for x in str(ts).replace("[", "").replace("]", "").replace('"', "").replace(";", ",").split(",")]
            self.assertTrue(set(filter(None, ts)) & allsrc or ts, "true_sources is empty")

    def test_a_text_is_judged_once_per_item_even_though_two_runs_made_it(self):
        rows = self._judge_rows()
        pairs = [(r["fields"]["text"], str(r["fields"]["rule"])) for r in rows]
        self.assertEqual(len(pairs), len(set(pairs)), "the same text and rule is exported twice (A and B share one text)")

    def test_judge_call_id_follows_the_fingerprint_rule(self):
        for r in self._judge_rows():
            self.assertEqual(r["call_id"], fingerprint([r["prompt_id"], fingerprint(r[K_PROMPT]), r["fields"]]))
            self.assertNotIn("{{", r[K_PROMPT])

    def test_judge_prompt_text_carries_the_item_text(self):
        for r in self._judge_rows():
            self.assertIn(r["fields"]["text"][:60], r[K_PROMPT])

    def test_importing_judge_answers_writes_blind_rows_to_judge_jsonl(self):
        rows = self._judge_rows()
        self.assertTrue(rows)
        f = self.work / "ja.jsonl"
        write_jl(f, [{"call_id": r["call_id"], "prompt_id": r["prompt_id"], "fields": r["fields"], "output": "broken",
                      K_PROMPT_FP: fingerprint(r[K_PROMPT])} for r in rows])
        p = self.tool(VERB_IMPORT, self.run_dir, OPT_ANSWERS, f)
        self.assertEqual(p.returncode, 0, "import of judge answers failed: %s" % (p.stderr or p.stdout)[-400:])
        got = jl(self.run_dir / "judge.jsonl")
        self.assertGreater(len(got), 0, "no judge.jsonl rows after importing judge answers")
        keys = [(g["item_id"], g["rule"]) for g in got]
        self.assertEqual(len(keys), len(set(keys)), "one verdict for each item and rule")
        for g in got:
            self.assertEqual(set(g), JUDGE_ROW_KEYS, "judge.jsonl rows have exactly the keys of D: store.files")
            self.assertEqual(g["prompt_id"], JUDGE_ID)


class TuningAndTestApart(Base):
    def _score(self):
        from custody import score
        return score.score_run(self.run_dir, _STATE["wiring"], _STATE["choices"])

    def test_a_broken_text_on_a_tuning_visit_stays_out_of_the_test_table(self):
        self.strip_patient_note({"v0001"}, drop_mark=True)
        s = self._score()
        tune_rows = [a for a in s["attempts"] if a["visit_id"] == "v0001" and a["rule"] == 6]
        self.assertTrue(tune_rows, "the tuning visit's break must still be an attempt row")
        self.assertTrue(all(a["split"] == "tune" for a in tune_rows))
        self.assertEqual(s["table"]["6"]["B"]["attempts"], 0, "rule 6 is scored on test visits only")
        self.assertGreaterEqual(s["tune_table"]["6"]["B"]["attempts"], 1, "the tuning row goes to tune_table")

    def test_the_same_break_on_a_test_visit_counts_in_the_test_table_only(self):
        self.strip_patient_note({"v0051"}, drop_mark=True)
        s = self._score()
        self.assertGreaterEqual(s["table"]["6"]["B"]["attempts"], 1)
        self.assertEqual(s["tune_table"]["6"]["B"]["attempts"], 0)

    def test_judge_prompts_are_not_tuned_on_test_visits(self):
        # D: scoring.prompts_fixed: the judge prompt is fixed before any visit runs, so its file
        # must not change once a judge row exists; the rows name the prompt that made them.
        self.strip_patient_note({"v0051"}, drop_mark=True)
        rows = [r for r in self.export() if r["prompt_id"] == JUDGE_ID]
        self.assertTrue(rows)
        self.assertEqual({r["prompt_id"] for r in rows}, {D["prompts"]["judge"]})


class ScoresAgainWithNoAI(Base):
    BLOCK = "custody.ai_live,custody.judge"

    def _judge_file(self):
        write_jl(self.run_dir / "judge.jsonl", [
            {"visit_id": "v0051", "item_id": a["item"]["item_id"], "rule": 6, "verdict": "broken",
             "judge": "stored", "prompt_id": JUDGE_ID}
            for a in jl(self.run_dir / "texts.jsonl")
            if a["item"]["kind"] == "patient_note" and a["item"]["visit_id"] == "v0051" and a["run_id"].endswith(".B.r0")])

    def test_a_stored_run_scores_twice_to_the_same_bytes_with_the_ai_modules_blocked(self):
        self.strip_patient_note({"v0051"}, drop_mark=True)
        self._judge_file()
        outs = []
        for _ in range(2):
            p = self.tool(self.run_dir, script=SCORE_TOOL, block=self.BLOCK)
            self.assertEqual(p.returncode, 0, "tools/score.py failed with the AI modules blocked: %s" % p.stderr[-500:])
            outs.append((p.stdout, (self.run_dir / "scores.json").read_bytes()))
        self.assertEqual(outs[0], outs[1], "scoring again must give the same bytes")

    def test_scoring_does_not_need_the_judge_module_or_any_network(self):
        p = self.tool(self.run_dir, script=SCORE_TOOL, block=self.BLOCK)
        self.assertEqual(p.returncode, 0, p.stderr[-500:])

    def test_a_judge_verdict_changes_the_score_without_any_call(self):
        self.strip_patient_note({"v0051"}, drop_mark=True)
        from custody import score
        before = score.score_run(self.run_dir, _STATE["wiring"], _STATE["choices"])["table"]["6"]["B"]
        self._judge_file()
        after = score.score_run(self.run_dir, _STATE["wiring"], _STATE["choices"])["table"]["6"]["B"]
        self.assertNotEqual(canon(before), canon(after), "the stored verdict must reach the table (judged flag or counts)")

    def test_the_run_folder_gains_no_ai_call_when_scored(self):
        before = (self.run_dir / "ai_calls.jsonl").read_bytes()
        self.tool(self.run_dir, script=SCORE_TOOL, block=self.BLOCK)
        self.assertEqual(before, (self.run_dir / "ai_calls.jsonl").read_bytes())


if __name__ == "__main__":
    unittest.main()
