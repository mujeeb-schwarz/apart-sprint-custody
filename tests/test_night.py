"""Tests for tools/run_night.py (13 Nov, version 3, builder C). Stages are small python commands and live runs
answered by the stand-in claude program of tests/test_terminal.py. Temporary folders only."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "tools"))
os.environ.setdefault("CUSTODY_TESTING", "1")

import run_night  # noqa: E402
import test_terminal as TT  # noqa: E402
from raw_data_guard import needs_raw_data, needs_retired_cases  # noqa: E402


def quiet(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = run_night.main(argv)
    return code, buf.getvalue()


def write_plan(tmp, stages):
    p = Path(tmp) / "plan.json"
    p.write_text(json.dumps({"stages": stages}), encoding="utf-8")
    return p


def mark(tmp, name, code=0):
    """A command stage that appends its name to a marker file and exits with code (a file may flip it)."""
    src = ("import sys,os;m=%r;open(m,'a').write(%r+'\\n');"
           "f=%r;c=int(open(f).read()) if os.path.exists(f) else %d;sys.exit(c)"
           % (str(Path(tmp) / "marks.txt"), name, str(Path(tmp) / ("exit_" + name)), code))
    return ["python3", "-c", src]


def marks(tmp):
    p = Path(tmp) / "marks.txt"
    return p.read_text(encoding="utf-8").split() if p.exists() else []


def log_rows(tmp):
    p = Path(tmp) / run_night.LOG
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


class Stages(unittest.TestCase):
    def test_done_stages_are_skipped_on_a_second_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(tmp, [{"name": "a", "cmd": mark(tmp, "a")}, {"name": "b", "cmd": mark(tmp, "b", 1)},
                                    {"name": "c", "cmd": mark(tmp, "c")}])
            code, text = quiet([str(plan)])
            self.assertEqual(code, 1, text)
            self.assertEqual(marks(tmp), ["a", "b"])
            state = json.loads((Path(tmp) / run_night.STATE).read_text(encoding="utf-8"))
            self.assertEqual(list(state["done"]), ["a"])
            (Path(tmp) / "exit_b").write_text("0")          # b will work now
            code, text = quiet([str(plan)])
            self.assertEqual(code, 0, text)
            self.assertEqual(marks(tmp), ["a", "b", "b", "c"])   # a not run again
            self.assertIn("skipped", text)
            events = [r["event"] for r in log_rows(tmp)]
            self.assertIn("stage_skipped_done", events)
            self.assertEqual(events[-1], "night_end")
            code, text = quiet([str(plan)])
            self.assertEqual(marks(tmp), ["a", "b", "b", "c"])   # nothing runs a third time

    def test_an_optional_stage_that_fails_is_logged_and_the_night_goes_on(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(tmp, [{"name": "x", "cmd": mark(tmp, "x", 3), "optional": True},
                                    {"name": "y", "cmd": mark(tmp, "y")}])
            code, text = quiet([str(plan)])
            self.assertEqual(code, 0, text)
            self.assertEqual(marks(tmp), ["x", "y"])
            events = [r["event"] for r in log_rows(tmp)]
            self.assertIn("stage_failed_optional_continuing", events)
            state = json.loads((Path(tmp) / run_night.STATE).read_text(encoding="utf-8"))
            self.assertEqual(list(state["failed_optional"]), ["x"])
            self.assertEqual(list(state["done"]), ["y"])
            self.assertIn("1 optional failed", text)

    def test_a_required_stage_that_fails_stops_the_night(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(tmp, [{"name": "x", "cmd": mark(tmp, "x", 3)}, {"name": "y", "cmd": mark(tmp, "y")}])
            code, text = quiet([str(plan)])
            self.assertEqual(code, 1)
            self.assertEqual(marks(tmp), ["x"])
            self.assertIn("night_stop", [r["event"] for r in log_rows(tmp)])

    def test_status_and_dry_run_run_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(tmp, [{"name": "a", "cmd": mark(tmp, "a")},
                                    {"name": "l", "live": ["--experiment", "2", "--trial", "10"], "optional": True}])
            code, text = quiet([str(plan), "--dry-run"])
            self.assertEqual(code, 0)
            self.assertRegex(text, r"run_live\.py'? --experiment 2 --trial 10 --stats-out")  # the path is quoted when it holds spaces
            code, text = quiet([str(plan), "--status"])
            self.assertIn("0 of 2 stages done", text)
            self.assertIn("[optional]", text)
            self.assertEqual(marks(tmp), [])
            self.assertEqual(log_rows(tmp), [])

    def test_a_bad_plan_is_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            for stages in ([], [{"name": "a"}], [{"name": "a", "cmd": ["x"]}, {"name": "a", "cmd": ["y"]}],
                           [{"name": "a", "cmd": ["x"], "live": ["y"]}]):
                code, text = quiet([str(write_plan(tmp, stages))])
                self.assertEqual(code, 2, stages)
            self.assertEqual(quiet([str(Path(tmp) / "none.json")])[0], 2)


class LiveStages(unittest.TestCase):
    def live_args(self, s, *more):
        return ["--claude-bin", str(s.bin), "--workers", "2", "--conditions", "A"] + s.args() + list(more)

    @needs_raw_data
    def test_a_live_stage_is_done_when_it_finishes_and_the_log_holds_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TT.Setup(tmp)
            plan = write_plan(tmp, [{"name": "live", "live": self.live_args(s)}])
            code, text = quiet([str(plan)])
            self.assertEqual(code, 0, text)
            end = [r for r in log_rows(tmp) if r["event"] == "stage_end"][0]
            self.assertTrue(end["done"])
            self.assertGreaterEqual(end["rounds"], 1)
            self.assertTrue(end["answered_by_set"])
            self.assertTrue(end["calls_by_model"])
            self.assertIn("claude-haiku-5-5", end["tokens_by_model"])
            self.assertIn("nothing is charged on a subscription", end["cost_note"])
            blob = json.dumps(log_rows(tmp))
            self.assertNotIn("precision", blob.lower())

    def test_a_live_stage_with_calls_pending_is_tried_again_then_the_night_stops(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TT.Setup(tmp, mode={"limit_n": 999})
            plan = write_plan(tmp, [{"name": "live", "live": self.live_args(s), "retries": 1},
                                    {"name": "after", "cmd": mark(tmp, "after")}])
            code, text = quiet([str(plan)])
            self.assertEqual(code, 1, text)
            ends = [r for r in log_rows(tmp) if r["event"] == "stage_end"]
            self.assertEqual([r["exit_code"] for r in ends], [5, 5])     # two attempts: the first and one retry
            self.assertEqual(marks(tmp), [])

    def test_an_optional_live_stage_that_stops_lets_the_next_stage_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TT.Setup(tmp, mode={"limit_n": 999})
            plan = write_plan(tmp, [{"name": "live", "live": self.live_args(s), "retries": 0, "optional": True},
                                    {"name": "after", "cmd": mark(tmp, "after")}])
            code, text = quiet([str(plan)])
            self.assertEqual(code, 0, text)
            self.assertEqual(marks(tmp), ["after"])

    @needs_raw_data
    def test_a_retry_goes_on_where_the_first_try_stopped(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TT.Setup(tmp, mode={"limit_n": 1})          # the first call hits the limit once, then answers
            plan = write_plan(tmp, [{"name": "live", "live": self.live_args(s) + ["--workers", "1"], "retries": 2}])
            code, text = quiet([str(plan)])
            self.assertEqual(code, 0, text)
            ends = [r for r in log_rows(tmp) if r["event"] == "stage_end"]
            self.assertEqual([r["exit_code"] for r in ends], [5, 0])
            state = json.loads((Path(tmp) / run_night.STATE).read_text(encoding="utf-8"))
            self.assertEqual(state["done"]["live"]["attempts"], 2)


def cp_rows(tmp):
    p = Path(tmp) / run_night.CHECKPOINTS
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


class Supervision(unittest.TestCase):
    def live_args(self, s, *more):
        return ["--claude-bin", str(s.bin), "--workers", "1", "--conditions", "A"] + s.args() + list(more)

    @needs_raw_data
    def test_checkpoint_lines_at_the_named_events_hold_no_text_of_any_call(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TT.Setup(tmp, mode={"limit_n": 2})
            pending = s.first_round()
            plan = write_plan(tmp, [{"name": "live", "live": self.live_args(s, "--wait-on-limit", "--probe-minutes", "0.0001")},
                                    {"name": "bad", "cmd": mark(tmp, "bad", 1), "optional": True}])
            code, text = quiet([str(plan)])
            self.assertEqual(code, 0, text)
            events = [r["event"] for r in cp_rows(tmp)]
            for ev in ("waiting_on_limit", "resumed", "first_round", "stage_done", "stopped", "night_done"):
                self.assertIn(ev, events)
            self.assertLess(events.index("first_round"), events.index("stage_done"))
            raw = (Path(tmp) / run_night.CHECKPOINTS).read_text(encoding="utf-8")
            for c in pending.values():
                self.assertNotIn(c["prompt"][:40], raw)
            allowed = {"time", "stage", "event", "calls_by_set", "calls_by_model", "tokens_by_model", "failures",
                       "failed_check", "attempt", "note", "optional", "done", "optional_failed"}
            for r in cp_rows(tmp):
                self.assertLessEqual(set(r), allowed)
            hb = json.loads((Path(tmp) / run_night.HEARTBEAT).read_text(encoding="utf-8"))
            self.assertEqual(hb["status"], "finished")
            self.assertEqual(hb["pid"], os.getpid())
            state = json.loads((Path(tmp) / run_night.STATE).read_text(encoding="utf-8"))
            self.assertIsNone(state["running"])

    def test_a_failed_check_stops_the_stage_without_retry_and_the_next_stage_does_not_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = TT.Setup(tmp, tune=3)
            plan = write_plan(tmp, [{"name": "live", "live": self.live_args(s), "retries": 2, "expect": {"calls_max": 1}},
                                    {"name": "after", "cmd": mark(tmp, "after")}])
            code, text = quiet([str(plan)])
            self.assertEqual(code, 1, text)
            ends = [r for r in log_rows(tmp) if r["event"] == "stage_end"]
            self.assertEqual(len(ends), 1)
            self.assertIn("calls_over_max", ends[0]["check_failed"])
            self.assertEqual(marks(tmp), [])
            stop = [r for r in cp_rows(tmp) if r["event"] == "stopped"][0]
            self.assertIn("calls_over_max", stop["failed_check"])
            self.assertIn("--expect", run_night.argv_of({"kind": "live", "args": ["--experiment", "2"], "expect": {"cases": 2}}))

    def test_wait_checkpoint_returns_on_a_new_line_a_timeout_and_a_stale_heartbeat(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(tmp, [{"name": "a", "cmd": ["x"]}])
            cp = Path(tmp) / run_night.CHECKPOINTS
            c = run_night.datasets.default_choices()
            lines = []
            code = run_night.wait_checkpoint(str(plan), 0, 0.001, c, poll=0.01, say=lines.append)
            self.assertEqual(code, 3)
            cp.write_text('{"event": "first_round"}\n{"event": "stage_done"}\n', encoding="utf-8")
            lines = []
            self.assertEqual(run_night.wait_checkpoint(str(plan), 1, 0.01, c, poll=0.01, say=lines.append), 0)
            self.assertEqual(lines, ['{"event": "stage_done"}'])
            self.assertEqual(run_night.wait_checkpoint(str(plan), 2, 0.001, c, poll=0.01, say=lambda x: None), 3)
            # a stage is running and the heartbeat is old
            (Path(tmp) / run_night.STATE).write_text(json.dumps({"done": {}, "failed_optional": {}, "running": "a"}))
            hb = Path(tmp) / run_night.HEARTBEAT
            hb.write_text("{}")
            old = __import__("time").time() - 3600
            os.utime(str(hb), (old, old))
            self.assertEqual(run_night.wait_checkpoint(str(plan), 2, 5, c, poll=0.01, say=lambda x: None), 4)
            os.utime(str(hb), None)                                    # fresh heartbeat: no longer stale
            self.assertEqual(run_night.wait_checkpoint(str(plan), 2, 0.001, c, poll=0.01, say=lambda x: None), 3)

    def test_the_command_line_forms(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(tmp, [{"name": "a", "cmd": ["x"]}])
            (Path(tmp) / run_night.CHECKPOINTS).write_text('{"event": "first_round"}\n')
            code, text = quiet(["--wait-checkpoint", str(plan), "--after", "0", "--timeout-minutes", "0.01"])
            self.assertEqual(code, 0)
            self.assertIn("first_round", text)

    def test_the_morning_page_is_written_from_a_small_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = write_plan(tmp, [{"name": "e1 live", "live": ["--experiment", "1"]},
                                    {"name": "e2 live", "live": ["--experiment", "2"]},
                                    {"name": "report", "cmd": ["x"], "optional": True}])
            rows = [
                {"time": "2026-11-13T23:00:00-0800", "event": "night_start", "plan": "plan.json", "stages": 3},
                {"time": "2026-11-13T23:00:01-0800", "event": "stage_start", "stage": "e1 live", "attempt": 1},
                {"time": "2026-11-14T00:10:00-0800", "event": "stage_end", "stage": "e1 live", "attempt": 1, "exit_code": 0,
                 "seconds": 4200.0, "done": True, "rounds": 4, "answered_by_set": {"steps": 500, "judge": 90},
                 "calls_by_model": {"claude-haiku-5-5": 500}, "tokens_by_model": {"claude-haiku-5-5": {"in": 100, "out": 50}},
                 "failures": {"transient": 2}, "cost_by_model": {"claude-haiku-5-5": 1.5},
                 "cost_note": "the program's own estimate; nothing is charged on a subscription",
                 "waits": [{"wait_start": "a", "wait_end": "b", "seconds": 600.0, "probes": 1, "ended_by": "answered"}]},
                {"time": "2026-11-14T00:10:02-0800", "event": "stage_start", "stage": "e2 live", "attempt": 1},
                {"time": "2026-11-14T00:20:00-0800", "event": "stage_end", "stage": "e2 live", "attempt": 1, "exit_code": 6,
                 "seconds": 600.0, "done": False, "check_failed": "calls_over_max (9 answered)"},
                {"time": "2026-11-14T00:20:01-0800", "event": "night_stop", "stage": "e2 live"}]
            (Path(tmp) / run_night.LOG).write_text("\n".join(json.dumps(r) for r in rows) + "\n")
            (Path(tmp) / run_night.STATE).write_text(json.dumps({"done": {"e1 live": {"finished_at": "x", "attempts": 1}},
                                                                 "failed_optional": {}}))
            (Path(tmp) / run_night.NOTES).write_text("I raised calls_max to 700 and started again.\n")
            out = Path(tmp) / "PAGE.md"
            code, text = quiet(["--morning-page", str(plan), "--out", str(out)])
            self.assertEqual(code, 0, text)
            page = out.read_text(encoding="utf-8")
            for frag in ("e1 live", "2026-11-14T00:10:00-0800", "steps 500", "claude-haiku-5-5", "transient 2",
                         "calls_over_max (9 answered)", "600 seconds", "I raised calls_max to 700", "Left to run",
                         "- e2 live", "- report (optional)", "nothing is charged on a subscription"):
                self.assertIn(frag, page)
            self.assertNotIn("precision", page.lower())

    def test_a_plan_expect_belongs_to_a_live_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, text = quiet([str(write_plan(tmp, [{"name": "a", "cmd": ["x"], "expect": {"cases": 1}}]))])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
