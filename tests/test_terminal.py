"""Tests for the answers through the command line (13 Nov): tools/answer_calls.py and tools/run_live.py.
The real claude program is never run: a stand-in executable (a small Python script written into a temporary
folder) records its arguments, working folder and environment and prints a JSON result. Temporary folders only."""
import contextlib
import re
import importlib.util
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("CUSTODY_TESTING", "1")

import test_advice as TA  # noqa: E402
import answer_calls  # noqa: E402
from custody import ai_live, datasets  # noqa: E402
from raw_data_guard import needs_raw_data, needs_retired_cases  # noqa: E402

D = datasets.default_choices()

SECRET_EMAIL = "secret.person@example.invalid"
SECRET_ORG = "SecretOrgName"

STAND_IN = r'''#!%(py)s
import json, os, sys, time, uuid
here = os.path.dirname(os.path.abspath(__file__))
cfg = json.load(open(os.path.join(here, "mode.json")))
args = sys.argv[1:]
if args[:2] == ["auth", "status"]:
    if cfg.get("logged_out"):
        print(json.dumps({"loggedIn": False}))
        sys.exit(1)
    print(json.dumps({"loggedIn": True, "authMethod": "claude.ai", "email": "%(email)s", "orgName": "%(org)s"}))
    sys.exit(0)
if args == ["--version"]:
    print("9.9.9 (Claude Code)")
    sys.exit(0)
prompt = sys.stdin.read()
rec = {"args": args, "cwd": os.getcwd(), "listing": sorted(os.listdir(os.getcwd())), "prompt": prompt,
       "has_key": "ANTHROPIC_API_KEY" in os.environ,
       "mds": os.environ.get("CLAUDE_CODE_DISABLE_CLAUDE_MDS"), "mem": os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY"),
       "telemetry": os.environ.get("DISABLE_TELEMETRY"), "traffic": os.environ.get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC")}
os.makedirs(os.path.join(here, "records"), exist_ok=True)
json.dump(rec, open(os.path.join(here, "records", "%%020d_" %% time.time_ns() + uuid.uuid4().hex + ".json"), "w"))
fail = cfg.get("fail")
model = args[args.index("--model") + 1] if "--model" in args else "none"
if cfg.get("limit_n"):
    cf = os.path.join(here, "limit_count")
    k = int(open(cf).read()) if os.path.exists(cf) else 0
    if k < cfg["limit_n"]:
        open(cf, "w").write(str(k + 1))
        print(json.dumps({"is_error": True, "subtype": "error_during_execution", "result": "You've hit your session limit"}))
        sys.exit(1)
if cfg.get("limit_after") is not None:
    cf = os.path.join(here, "ok_count")
    k = int(open(cf).read()) if os.path.exists(cf) else 0
    if k >= cfg["limit_after"]:
        print(json.dumps({"is_error": True, "subtype": "error_during_execution", "result": "You've hit your weekly limit"}))
        sys.exit(1)
    open(cf, "w").write(str(k + 1))
if fail == "transient":
    key = os.path.join(here, "t_" + __import__("hashlib").sha256(prompt.encode()).hexdigest()[:16])
    k = int(open(key).read()) if os.path.exists(key) else 0
    if k < cfg.get("transient_n", 1):
        open(key, "w").write(str(k + 1))
        print(json.dumps({"is_error": True, "subtype": "error_during_execution", "result": "API Error: 529 overloaded_error"}))
        sys.exit(1)
if fail == "limit":
    print(json.dumps({"is_error": True, "subtype": "error_during_execution", "result": "You've hit your session limit"}))
    sys.exit(1)
if fail == "all":
    print(json.dumps({"is_error": True, "subtype": "error_during_execution", "result": "boom"}))
    sys.exit(1)
if fail == "first":
    marker = os.path.join(here, "seen_" + str(abs(hash(prompt) %% 10**9)) + str(len(prompt)))
    key = os.path.join(here, "m_" + __import__("hashlib").sha256(prompt.encode()).hexdigest()[:16])
    if not os.path.exists(key):
        open(key, "w").close()
        sys.exit(3)
if fail == "badjson":
    print("not json")
    sys.exit(0)
# find the pending call that shows this prompt, and answer it the way the test helper does
sys.path.insert(0, cfg["tests"])
import test_advice as TA
live = cfg["live"]
call = None
for name in ("steps", "methods", "judge"):
    p = os.path.join(live, "handout", "pending_%%s.jsonl" %% name)
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            row = json.loads(line)
            if row["prompt"] == prompt:
                call = row
reply = TA.helper_answer(call) if call else "stand-in text"
if cfg.get("refuse_first_of") and call and call["prompt_id"].startswith(tuple(cfg["refuse_first_of"])):
    rf = os.path.join(here, "refused_id")
    if not os.path.exists(rf):
        open(rf, "w").write(call["call_id"])
    if open(rf).read() == call["call_id"]:
        reply = ""
if cfg.get("refuse_all"):
    reply = ""
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": reply + "\n", "session_id": "x",
                  "duration_ms": 12, "num_turns": 1, "total_cost_usd": 0.25,
                  "usage": {"input_tokens": 10, "output_tokens": 5, "cache_creation_input_tokens": 2, "cache_read_input_tokens": 3},
                  "modelUsage": dict((m, {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 3, "cacheCreationInputTokens": 2})
                                     for m in cfg.get("answering_models") or [model])}))
'''


def quiet(fn, *a, **k):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(*a, **k)
    return code, buf.getvalue()


class Setup:
    """A temporary project area: a small visit list, a first round of pending calls, a stand-in claude."""

    def __init__(self, tmp, tune=2, mode=None):
        self.tmp = Path(tmp)
        self.vpath, _ = TA.small_visits(tmp, tune=tune)
        self.live = self.tmp / "live"
        self.bin_dir = self.tmp / "bin"
        self.bin_dir.mkdir()
        self.bin = self.bin_dir / "claude"
        self.bin.write_text(STAND_IN % {"py": sys.executable, "email": SECRET_EMAIL, "org": SECRET_ORG}, encoding="utf-8")
        self.bin.chmod(self.bin.stat().st_mode | stat.S_IXUSR)
        self.mode(**(mode or {}))

    def mode(self, **m):
        m.update({"tests": str(ROOT / "tests"), "live": str(self.live)})
        (self.bin_dir / "mode.json").write_text(json.dumps(m), encoding="utf-8")

    def args(self, *more):
        return TA.args(self.tmp, self.vpath, *more)

    def first_round(self, *more):
        assert TA.TOOL.main(["run"] + self.args(*more)) == 3
        return ai_live.read_pending(self.live)

    def records(self):
        d = self.bin_dir / "records"
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(d.glob("*.json"))] if d.exists() else []

    def log(self):
        return answer_calls.read_jsonl(ai_live.private_dir(self.live) / answer_calls.LOG)

    def answer(self, *more):
        return quiet(answer_calls.main, ["--live-dir", str(self.live), "--claude-bin", str(self.bin)] + list(more))


class TheCall(unittest.TestCase):
    def test_every_flag_stdin_cwd_and_environment(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-test-not-real"}):
            s = Setup(tmp)
            pending = s.first_round()
            code, text = s.answer("--limit", "3", "--workers", "1")
            self.assertEqual(code, 0, text)
            self.assertIn("ANTHROPIC_API_KEY is set in the environment: it is ignored", text)
            recs = s.records()
            self.assertEqual(len(recs), 3)
            t = D["live"]["terminal"]
            prompts = {c["prompt"] for c in pending.values()}
            for r in recs:
                a = r["args"]
                model = a[a.index("--model") + 1]
                self.assertIn(model, set(t["models"].values()))
                self.assertEqual(a, ["-p", "--safe-mode", "--system-prompt", t["system_prompt"], "--tools", "",
                                     "--disallowedTools", "*", "--strict-mcp-config", "--model", model,
                                     "--output-format", "json", "--no-session-persistence"])
                self.assertIn(r["prompt"], prompts)          # on standard input ...
                self.assertFalse(any(r["prompt"][:40] in x for x in a))  # ... and not among the arguments
                self.assertEqual(r["listing"], [])            # an empty folder
                self.assertFalse(r["has_key"])
                self.assertEqual((r["mds"], r["mem"]), ("1", "1"))
                self.assertEqual((r["telemetry"], r["traffic"]), ("1", "1"))
            self.assertEqual(len({r["cwd"] for r in recs}), 3)  # a different folder per call
            self.assertFalse(any(Path(r["cwd"]).exists() for r in recs))  # removed afterwards

    def test_effort_flag_only_when_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp)
            s.first_round()
            s.answer("--limit", "1")
            self.assertNotIn("--effort", s.records()[0]["args"])
            s.answer("--limit", "1", "--effort", "low", "--out", str(Path(tmp) / "other.jsonl"))
            self.assertEqual(s.records()[-1]["args"][-2:], ["--effort", "low"])

    def test_dry_run_prints_the_command_without_the_prompt_and_calls_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp)
            pending = s.first_round()
            code, text = s.answer("--dry-run")
            self.assertEqual(code, 0)
            self.assertIn("--no-session-persistence", text)
            self.assertEqual(s.records(), [])
            for c in pending.values():
                self.assertNotIn(c["prompt"][:60], text)


class TheAnswers(unittest.TestCase):
    def test_file_is_accepted_by_import_and_a_second_run_asks_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp)
            pending = s.first_round()
            code, text = s.answer("--workers", "3")
            self.assertEqual(code, 0, text)
            out = ai_live.private_dir(s.live) / answer_calls.DEFAULT_OUT
            rows = answer_calls.read_jsonl(out)
            self.assertEqual(len(rows), len(pending))
            n = len(s.records())
            code, text = s.answer()
            self.assertEqual((code, len(s.records())), (0, n))   # nothing asked the second time
            self.assertIn("nothing to answer", text)
            self.assertEqual(TA.TOOL.main(["import", str(out)] + s.args()), 0)
            st = ai_live.AnswerStore(s.live)
            by = {r["call_id"]: r for r in rows}
            for cid, call in pending.items():
                self.assertEqual(st.answers()[call["real"][0]], TA.helper_answer(call))  # kept as returned, no newline
                self.assertEqual(by[cid]["prompt_fp"], call["prompt_fp"])

    def test_log_and_conditions_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp)
            s.first_round()
            code, text = s.answer("--limit", "2")
            log = s.log()
            self.assertEqual(len(log), 2)
            for row in log:
                self.assertEqual(row["models_answered"], [row["model_asked"]])
                self.assertEqual(row["cost_usd_estimate"], 0.25)
                self.assertEqual(row["claude_version"], "9.9.9 (Claude Code)")
                self.assertRegex(row["time"], r"^\d{4}-\d\d-\d\dT")
                self.assertEqual((row["input_tokens"], row["output_tokens"]), (10, 5))
                self.assertEqual((row["exit_code"], row["subtype"], row["retry"]), (0, "success", False))
                self.assertNotIn("prompt", row)
                self.assertNotIn("output", row)
            cond = json.loads((ai_live.private_dir(s.live) / answer_calls.CONDITIONS).read_text(encoding="utf-8"))
            self.assertEqual(cond["claude_version"], "9.9.9 (Claude Code)")
            self.assertEqual(cond["system_prompt"], D["live"]["terminal"]["system_prompt"])
            self.assertIn("models", cond)

    def test_a_failing_call_is_retried_once_then_left_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"fail": "all"})
            s.first_round()
            code, text = s.answer("--limit", "1")
            self.assertEqual(code, 4, text)
            log = s.log()
            self.assertEqual([r["retry"] for r in log], [False, True])
            self.assertEqual(len(s.records()), 2)
            self.assertFalse((ai_live.private_dir(s.live) / answer_calls.DEFAULT_OUT).exists()
                             and answer_calls.read_jsonl(ai_live.private_dir(s.live) / answer_calls.DEFAULT_OUT))
            self.assertIn("1 calls are still pending", text)

    def test_a_call_that_fails_once_is_answered_on_the_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"fail": "first"})
            s.first_round()
            code, text = s.answer("--limit", "2", "--workers", "1")
            self.assertEqual(code, 0, text)
            self.assertEqual([r["retry"] for r in s.log()], [False, True, False, True])
            self.assertEqual(len(answer_calls.read_jsonl(ai_live.private_dir(s.live) / answer_calls.DEFAULT_OUT)), 2)

    def test_unreadable_output_is_a_failed_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"fail": "badjson"})
            s.first_round()
            code, text = s.answer("--limit", "1")
            self.assertEqual(code, 4)
            self.assertEqual(len(s.log()), 2)

    def test_a_limit_phrase_stops_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"fail": "limit"})
            pending = s.first_round()
            self.assertGreater(len(pending), 2)
            code, text = s.answer("--workers", "1")
            self.assertEqual(code, 5, text)
            self.assertEqual(len(s.records()), 1)       # no retry, no further call
            self.assertIn("usage limit", text)

    def test_nothing_of_auth_status_beyond_the_method_is_kept_or_shown(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp)
            s.first_round()
            code, text = s.answer("--limit", "1")
            self.assertIn("method: claude.ai", text)
            blob = text
            for p in Path(s.live).rglob("*"):
                if p.is_file() and p.parent.name != "handout":
                    blob += p.read_text(encoding="utf-8", errors="ignore")
            for secret in (SECRET_EMAIL, SECRET_ORG):
                self.assertNotIn(secret, blob)

    def test_not_logged_in_stops_before_any_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"logged_out": True})
            s.first_round()
            code, text = s.answer()
            self.assertEqual(code, 2)
            self.assertEqual(s.records(), [])


class RunLive(unittest.TestCase):
    @needs_raw_data
    def test_a_tuning_selection_finishes_and_prints_no_scores(self):
        run_live = TA.load_tool("run_live")
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp)
            argv = ["--claude-bin", str(s.bin), "--workers", "4", "--conditions", "A,B"] + s.args()
            code, text = quiet(run_live.main, argv)
            self.assertEqual(code, 0, text)
            self.assertIn("finished", text)
            self.assertIn("round 1", text)
            run_dir = Path(tmp) / "runs" / "advice_tune_e2"
            self.assertTrue((run_dir / "scores.json").exists())
            scores = (run_dir / "scores.json").read_text(encoding="utf-8")
            self.assertIn(str(run_dir / "scores.json"), text)
            low = text.lower()
            for word in ("| condition", "precision", "recall", "false_alarm", "table", "scores:"):
                self.assertNotIn(word, low)
            self.assertLess(len(text), 3000)
            self.assertTrue(scores)

    def test_stops_when_a_round_answers_nothing(self):
        run_live = TA.load_tool("run_live")
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"fail": "all"})
            argv = ["--claude-bin", str(s.bin), "--conditions", "A", "--workers", "2"] + s.args()
            code, text = quiet(run_live.main, argv)
            self.assertEqual(code, 1)
            self.assertIn("answered nothing", text)


class TheModelCheck(unittest.TestCase):
    def test_a_wrong_model_is_not_stored_and_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"answering_models": ["claude-haiku-4-5-20251001"]})
            s.first_round()
            code, text = s.answer("--limit", "1")
            self.assertEqual(code, 4, text)
            self.assertEqual(len(s.records()), 1)
            row = s.log()[0]
            self.assertEqual((row["answered"], row["reason"]), (False, "wrong_model"))
            self.assertEqual(row["models_answered"], ["claude-haiku-4-5-20251001"])
            out = ai_live.private_dir(s.live) / answer_calls.DEFAULT_OUT
            self.assertEqual(answer_calls.read_jsonl(out), [])
            self.assertIn("wrong_model 1", text)

    def test_two_models_answering_is_wrong_too(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"answering_models": ["claude-haiku-5-5", "claude-sonnet-5-5"]})
            s.first_round()
            code, text = s.answer("--limit", "1")
            self.assertEqual(s.log()[0]["reason"], "wrong_model")

    def test_three_in_a_row_stop_the_run_with_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, tune=4, mode={"answering_models": ["other-model"]})
            pending = s.first_round()
            self.assertGreater(len(pending), 3)
            code, text = s.answer("--workers", "1")
            self.assertEqual(code, 2, text)
            self.assertEqual(len(s.records()), 3)
            self.assertIn("another model", text)

    def test_the_right_model_is_stored_and_the_per_set_counts_print(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp)
            s.first_round()
            code, text = s.answer("--workers", "2")
            self.assertEqual(code, 0, text)
            self.assertIn("answered by set:", text)
            self.assertIn("the program's own estimate; nothing is charged on a subscription", text)
            for row in s.log():
                self.assertEqual(row["models_answered"], [row["model_asked"]])


class TransientErrors(unittest.TestCase):
    def test_a_transient_error_is_retried_up_to_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"fail": "transient", "transient_n": 2})
            s.first_round()
            code, text = s.answer("--limit", "1", "--transient-waits", "0,0")
            self.assertEqual(code, 0, text)
            self.assertEqual([(r["retry"], r["reason"]) for r in s.log()],
                             [(False, "transient"), (True, "transient"), (True, None)])

    def test_after_two_retries_the_call_counts_as_failed(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"fail": "transient", "transient_n": 9})
            s.first_round()
            code, text = s.answer("--limit", "1", "--transient-waits", "0,0")
            self.assertEqual(code, 4, text)
            self.assertEqual(len(s.records()), 3)

    def test_the_waits_come_from_the_config(self):
        self.assertEqual(D["live"]["terminal"]["transient_waits_seconds"], [20, 60])
        self.assertEqual(answer_calls.settings(D)["wrong_model_stop_after"], 3)

    def test_a_timeout_is_transient(self):
        self.assertTrue(answer_calls.is_transient("timeout", "", []))
        self.assertTrue(answer_calls.is_transient(1, "api error: 503", D["live"]["terminal"]["transient_phrases"]))
        self.assertFalse(answer_calls.is_transient(1, "boom", D["live"]["terminal"]["transient_phrases"]))


class TheLimit(unittest.TestCase):
    def test_a_limit_stop_saves_what_was_answered_and_a_second_start_does_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"limit_after": 2})
            pending = s.first_round()
            code, text = s.answer("--workers", "1")
            self.assertEqual(code, 5, text)
            out = ai_live.private_dir(s.live) / answer_calls.DEFAULT_OUT
            self.assertEqual(len(answer_calls.read_jsonl(out)), 2)
            s.mode()      # the limit lifts
            code, text = s.answer("--workers", "2")
            self.assertEqual(code, 0, text)
            self.assertEqual(len(answer_calls.read_jsonl(out)), len(pending))
            self.assertEqual(len(s.log()), 2 + 1 + (len(pending) - 2))   # nothing answered twice

    def test_run_live_without_waiting_exits_5(self):
        run_live = TA.load_tool("run_live")
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"limit_n": 99})
            code, text = quiet(run_live.main, ["--claude-bin", str(s.bin), "--workers", "1", "--conditions", "A"] + s.args())
            self.assertEqual(code, 5, text)
            self.assertIn("usage limit", text)

    @needs_raw_data
    def test_wait_on_limit_probes_and_goes_on_with_the_same_round(self):
        run_live = TA.load_tool("run_live")
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"limit_n": 2})
            stats = Path(tmp) / "stats.json"
            argv = ["--claude-bin", str(s.bin), "--workers", "1", "--conditions", "A,B", "--wait-on-limit",
                    "--probe-minutes", "0.0001", "--stats-out", str(stats)] + s.args()
            code, text = quiet(run_live.main, argv)
            self.assertEqual(code, 0, text)
            self.assertIn("finished", text)
            self.assertIn("waiting for the usage limit", text)
            st = json.loads(stats.read_text(encoding="utf-8"))
            self.assertEqual(len(st["waits"]), 1)
            self.assertEqual((st["waits"][0]["probes"], st["waits"][0]["ended_by"]), (2, "answered"))
            waits = answer_calls.read_jsonl(ai_live.private_dir(s.live) / "terminal_waits.jsonl")
            self.assertEqual(len(waits), 1)
            self.assertIn("wait_start", waits[0])
            self.assertIn("wait_end", waits[0])
            self.assertEqual(st["exit_code"], 0)
            self.assertTrue(st["answered_by_set"])
            self.assertTrue((Path(tmp) / "runs" / "advice_tune_e2" / "scores.json").exists())

    def test_the_waiting_cap_ends_the_run_with_exit_5(self):
        run_live = TA.load_tool("run_live")
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"limit_n": 999})
            argv = ["--claude-bin", str(s.bin), "--workers", "1", "--conditions", "A", "--wait-on-limit",
                    "--probe-minutes", "0.0001", "--max-wait-hours", "0.00003"] + s.args()
            code, text = quiet(run_live.main, argv)
            self.assertEqual(code, 5, text)
            self.assertIn("waiting cap", text)

    def test_run_live_exits_2_on_wrong_models(self):
        run_live = TA.load_tool("run_live")
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, tune=4, mode={"answering_models": ["other"]})
            code, text = quiet(run_live.main, ["--claude-bin", str(s.bin), "--workers", "1", "--conditions", "A"] + s.args())
            self.assertEqual(code, 2, text)
            self.assertIn("wrong_model", text)



class TheRunnersChecks(unittest.TestCase):
    def run_live(self, s, *more):
        run_live = TA.load_tool("run_live")
        return quiet(run_live.main, ["--claude-bin", str(s.bin), "--workers", "1", "--conditions", "A"] + s.args() + list(more))

    def test_unknown_selection_options_are_passed_to_run_advice(self):
        run_live = TA.load_tool("run_live")
        seen = []

        class Fake:
            @staticmethod
            def main(argv):
                seen.append(list(argv))
                return 0
        run_live.load_advice = lambda: Fake
        with tempfile.TemporaryDirectory() as tmp:
            code, text = quiet(run_live.main, ["--experiment", "2", "--plan", "P.json", "--rule", "4", "--part", "x"])
        self.assertEqual(code, 0)
        self.assertEqual(seen[0][0], "run")
        self.assertEqual(seen[0][-6:], ["--plan", "P.json", "--rule", "4", "--part", "x"])

    def test_a_refused_answer_is_asked_again_and_the_stage_fails_after_the_third_refusal(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp)
            s.first_round()
            s.mode(refuse_first_of=["watcher", "reviewer"])
            stats = Path(tmp) / "stats.json"
            events = Path(tmp) / "events.jsonl"
            code, text = self.run_live(s, "--stats-out", str(stats), "--events-out", str(events))
            self.assertEqual(code, 6, text)
            self.assertIn("refused_after_3_tries", text)
            rows = [r for r in answer_calls.read_jsonl(events)]
            self.assertEqual(len([r for r in rows if r["event"] == "refused"]), 3)   # each refusal logged
            self.assertGreaterEqual(len([r for r in rows if r["event"] == "round_end"]), 3)
            self.assertTrue(all("prompt" not in r and "output" not in r for r in rows))
            st = json.loads(stats.read_text(encoding="utf-8"))
            self.assertIn("refused_after_3_tries", st["check_failed"])
            rid = (s.bin_dir / "refused_id").read_text()
            self.assertEqual(len([r for r in s.log() if r["call_id"] == rid]), 3)

    def test_too_many_refused_in_one_round_fail_at_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, tune=4, mode={"refuse_all": True})
            code, text = self.run_live(s)
            self.assertEqual(code, 6, text)
            self.assertIn("refused_share", text)

    @needs_raw_data
    def test_a_wrong_number_of_finished_cases_fails_the_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp)
            code, text = self.run_live(s, "--expect", json.dumps({"cases": 99}))
            self.assertEqual(code, 6, text)
            self.assertIn("cases_mismatch", text)
            got = int(re.search(r"cases_mismatch \((\d+) finished", text).group(1))
            self.assertGreater(got, 0)
            code, text = self.run_live(s, "--expect", json.dumps({"cases": got, "calls_min": 1}))
            self.assertEqual(code, 0, text)

    @needs_raw_data
    def test_calls_above_the_most_expected_stop_the_stage_during_the_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, tune=3)
            code, text = self.run_live(s, "--expect", json.dumps({"calls_max": 1}))
            self.assertEqual(code, 6, text)
            self.assertIn("calls_over_max", text)
            code, text = self.run_live(s)     # no expect: the stage can go on from where it stopped
            self.assertEqual(code, 0, text)

    def test_tokens_per_call_and_the_shares_from_the_call_log(self):
        run_live = TA.load_tool("run_live")
        with tempfile.TemporaryDirectory() as tmp:
            live = Path(tmp) / "live"
            priv = ai_live.private_dir(live)
            priv.mkdir(parents=True)
            with open(priv / answer_calls.LOG, "w", encoding="utf-8") as fh:
                for i in range(25):
                    fh.write(json.dumps({"call_id": "c%d" % i, "set": "steps", "answered": True,
                                         "input_tokens": 100, "output_tokens": 50}) + "\n")
            with open(priv / "terminal_answers_x_r01.jsonl", "w", encoding="utf-8") as fh:
                for i in range(25):
                    fh.write(json.dumps({"call_id": "c%d" % i, "output": "" if i < 2 else "fine"}) + "\n")
            self.assertIn("tokens_per_call_over_max", run_live.check_expect(live, {"tokens_per_call_max": {"steps": 100}}, D))
            self.assertIsNone(run_live.check_expect(live, {"tokens_per_call_max": {"steps": 150}}, D))
            self.assertIsNone(run_live.check_shares(live, D))        # fewer than 50 step answers: no share yet
            D2 = json.loads(json.dumps(D))
            D2["night"]["min_answers_for_shares"] = 20
            self.assertIn("empty_share", run_live.check_shares(live, D2))    # 2 of 25 empty is 8 percent



class KeptCalls(unittest.TestCase):
    def test_every_call_is_kept_as_exported_once_per_call_id_before_it_is_made(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = Setup(tmp, mode={"fail": "all"})       # the calls fail: they are kept all the same
            pending = s.first_round()
            exported = {}
            for name in ("steps", "methods", "judge"):
                p = s.live / "handout" / ("pending_%s.jsonl" % name)
                if p.exists():
                    for row in answer_calls.read_jsonl(p):
                        exported[row["call_id"]] = row
            s.answer("--workers", "1")
            s.answer("--workers", "1")                 # a second start adds nothing
            kept = {}
            for name in ("steps", "methods", "judge"):
                p = ai_live.private_dir(s.live) / ("calls_kept_%s.jsonl" % name)
                if p.exists():
                    rows = answer_calls.read_jsonl(p)
                    ids = [r["call_id"] for r in rows]
                    self.assertEqual(len(ids), len(set(ids)))
                    for r in rows:
                        kept[r["call_id"]] = r
            self.assertEqual(kept, exported)
            self.assertEqual(len(kept), len(pending))
            self.assertTrue(all(r["prompt"] for r in kept.values()))
            self.assertTrue((ai_live.private_dir(s.live) / "calls_kept_steps.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
