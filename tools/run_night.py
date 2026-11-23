#!/usr/bin/env python3
"""Run a whole night plan: stages in order, each a live run or a plain command.

    python3 tools/run_night.py PLAN.json            run the stages not done yet
    python3 tools/run_night.py PLAN.json --status   print the state and stop
    python3 tools/run_night.py PLAN.json --dry-run  print the command of every stage and stop

The plan is JSON: {"stages": [STAGE, ...]} (a bare list works too). A stage has a unique "name" and either
    {"name": "e1 live", "live": [arguments for tools/run_live.py], "retries": 2, "optional": false}
or  {"name": "report", "cmd": ["python3", "tools/make_run_report.py", ...]}        (an argv, run from the folder
that holds tools/, i.e. ROOT).
A stage is done when its program exits 0. A live stage that stops with calls pending (run_live.py exit code 1 or
5) is tried again up to its "retries" (default D: night.stage_retries); a live stage that stops on a bad input or
on wrong-model answers (exit code 2) is not tried again, because nothing would change. When a stage is not done,
the night stops with exit code 1, unless the stage has "optional": true: then the night logs it and goes on.
(Put --wait-on-limit into a live stage's arguments to wait out a usage limit inside the stage.)

State: night_state.json beside the plan (the names of the stages done); a second start skips them.
Log: night_log.jsonl beside the plan, one line per event (night start and end, each stage attempt: times, exit
code, rounds, calls by set and by model, tokens, the cost field, failures by reason, waits). Counts only; the
tools it runs print no outcome of the experiment and this one prints none either.
Exit code: 0 every stage done (or an optional one skipped), 1 the night stopped at a stage, 2 a bad plan.

A live stage may carry "expect": {"cases": N, "calls_min": A, "calls_max": B, "tokens_per_call_max":
{"steps": X, "methods": Y, "judge": Z}}; it is passed to run_live.py, which checks it with the runner's other
checks after every round (see tools/run_live.py). A stage whose check failed (run_live.py exit code 6) is not tried
again: the night stops there, or goes on if the stage is optional.

Supervision:
  night_checkpoints.jsonl   one JSON line after the first round of each stage and at the end of each stage, at
                            every stop and at the start and end of each wait on the usage limit (events
                            first_round, stage_done, stopped, waiting_on_limit, resumed, night_done): counts only.
  night_heartbeat.json      rewritten every night.heartbeat_seconds (at most 60) while a stage works or waits.
  --wait-checkpoint PLAN --after N [--timeout-minutes M]
                            blocks until the checkpoints file has more than N lines, prints the new lines, exit 0;
                            exit 3 after M minutes without one; exit 4 when the heartbeat is older than
                            night.stale_minutes while the state says a stage is running (the runner died or the
                            machine slept).
  --morning-page PLAN --out PAGE.md
                            writes the night in plain words from the log (stages, calls, tokens, stops, waits, the
                            text of night_notes.md beside the plan, what is left to run). Counts only.
"""
import argparse
import json
import os
import shlex
import functools
import builtins
import subprocess
import sys
import tempfile
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import datasets  # noqa: E402

STATE = "night_state.json"
LOG = "night_log.jsonl"
CHECKPOINTS = "night_checkpoints.jsonl"
HEARTBEAT = "night_heartbeat.json"
NOTES = "night_notes.md"
NO_RETRY_EXIT = (2, 6)

print = functools.partial(builtins.print, flush=True)  # noqa: A001


class PlanError(Exception):
    pass


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def load_plan(path, choices):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise PlanError("cannot read the plan %s: %s" % (path, e.__class__.__name__))
    stages = data.get("stages") if isinstance(data, dict) else data
    if not isinstance(stages, list) or not stages:
        raise PlanError("the plan holds no stages")
    seen = set()
    out = []
    for i, st in enumerate(stages, 1):
        if not isinstance(st, dict) or not isinstance(st.get("name"), str) or not st["name"]:
            raise PlanError("stage %d has no name" % i)
        if st["name"] in seen:
            raise PlanError("two stages are named %r" % st["name"])
        seen.add(st["name"])
        kinds = [k for k in ("live", "cmd") if k in st]
        if len(kinds) != 1:
            raise PlanError("stage %r must have exactly one of 'live' and 'cmd'" % st["name"])
        arr = st[kinds[0]]
        if not isinstance(arr, list) or not arr or not all(isinstance(x, str) for x in arr):
            raise PlanError("stage %r: '%s' must be a non-empty list of strings" % (st["name"], kinds[0]))
        retries = st.get("retries", choices["night"]["stage_retries"])
        if not isinstance(retries, int) or isinstance(retries, bool) or retries < 0:
            raise PlanError("stage %r: retries must be a whole number, 0 or more" % st["name"])
        expect = st.get("expect")
        if expect is not None and (kinds[0] != "live" or not isinstance(expect, dict)):
            raise PlanError("stage %r: 'expect' is an object and belongs to a live stage" % st["name"])
        out.append({"name": st["name"], "kind": kinds[0], "args": arr, "retries": retries,
                    "optional": bool(st.get("optional", False)), "expect": expect})
    return out


def argv_of(stage, stats_file=None):
    if stage["kind"] == "live":
        argv = [sys.executable, "-u", str(ROOT / "tools" / "run_live.py")] + stage["args"]
        if stage.get("expect"):
            argv += ["--expect", json.dumps(stage["expect"], sort_keys=True)]
        if stats_file:
            argv += ["--stats-out", stats_file, "--events-out", stats_file + ".events"]
        return argv
    argv = list(stage["args"])
    if argv[0] in ("python", "python3"):
        argv[0] = sys.executable
    return argv


def read_state(path):
    if Path(path).exists():
        try:
            d = json.loads(Path(path).read_text(encoding="utf-8"))
            if isinstance(d, dict):
                d.setdefault("done", {})
                d.setdefault("failed_optional", {})
                return d
        except ValueError:
            pass
    return {"done": {}, "failed_optional": {}}


def write_state(path, state):
    tmp = str(path) + ".tmp"
    Path(tmp).write_text(json.dumps(state, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, str(path))


def log(path, **row):
    row = dict({"time": now()}, **row)
    with open(str(path), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True) + "\n")


def read_stats(path):
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def merge_counts(into, add):
    for k in ("answered_by_set", "failures"):
        for name, v in (add.get(k) or {}).items():
            into[k][name] = into[k].get(name, 0) + v
    for m, c in (add.get("tokens_by_model") or {}).items():
        d = into["tokens_by_model"].setdefault(m, {})
        for kk, v in c.items():
            d[kk] = d.get(kk, 0) + v


class Night:
    """The files of one plan and what is written to them."""

    def __init__(self, plan, choices, say=print):
        self.plan = Path(plan).resolve()
        self.dir = self.plan.parent
        self.choices = choices
        self.say = say
        self.state_path = self.dir / STATE
        self.log_path = self.dir / LOG
        self.cp_path = self.dir / CHECKPOINTS
        self.hb_path = self.dir / HEARTBEAT
        self.state = read_state(self.state_path)
        self.hb = {"stage": None, "round": 0, "status": "idle"}
        self.hb_due = 0.0

    def heartbeat(self, force=False, **kw):
        self.hb.update(kw)
        gap = min(60.0, float(self.choices["night"]["heartbeat_seconds"]))
        if force or time.time() >= self.hb_due:
            self.hb_due = time.time() + gap
            rec = dict(self.hb, time=now(), pid=os.getpid())
            tmp = str(self.hb_path) + ".tmp"
            Path(tmp).write_text(json.dumps(rec, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(tmp, str(self.hb_path))

    def checkpoint(self, event, stage=None, counts=None, failed_check=None, **extra):
        row = {"time": now(), "stage": stage, "event": event}
        c = counts or {}
        row["calls_by_set"] = c.get("answered_by_set", {})
        row["calls_by_model"] = c.get("calls_by_model", {})
        row["tokens_by_model"] = c.get("tokens_by_model", {})
        row["failures"] = c.get("failures", {})
        row["failed_check"] = failed_check
        row.update(extra)
        with open(str(self.cp_path), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
            fh.flush()

    def save(self):
        write_state(self.state_path, self.state)

    def run_stage(self, stage):
        """Run one stage with its retries. Returns (done, failed check or None)."""
        tries = 1 + (stage["retries"] if stage["kind"] == "live" else 0)
        failed_check = None
        for attempt in range(1, tries + 1):
            fd, stats_file = tempfile.mkstemp(prefix="night_stats_", suffix=".json")
            os.close(fd)
            os.unlink(stats_file)
            events_file = stats_file + ".events"
            argv = argv_of(stage, stats_file if stage["kind"] == "live" else None)
            t0 = time.time()
            log(self.log_path, event="stage_start", stage=stage["name"], attempt=attempt)
            self.say("stage %r, attempt %d of %d" % (stage["name"], attempt, tries))
            self.state["running"] = stage["name"]
            self.save()
            self.heartbeat(True, stage=stage["name"], round=0, status="running")
            out_fd, out_path = tempfile.mkstemp(prefix="night_out_", suffix=".txt")
            os.close(out_fd)
            seen = 0
            counts = {"answered_by_set": {}, "failures": {}, "tokens_by_model": {}}
            first_done = False
            try:
                with open(out_path, "w", encoding="utf-8") as fh:
                    proc = subprocess.Popen(argv, cwd=str(ROOT), stdout=fh, stderr=subprocess.STDOUT, text=True)
                    while True:
                        done = proc.poll() is not None
                        seen, evs = read_events(events_file, seen)
                        for ev in evs:
                            self.on_event(stage, ev, counts, first_done)
                            if ev.get("event") == "round_end":
                                first_done = True
                        if done:
                            break
                        self.heartbeat(False)
                        time.sleep(0.2)
                    code = proc.returncode
            except OSError as e:
                code = 127
                Path(out_path).write_text("could not start the program: %s" % e.__class__.__name__, encoding="utf-8")
            text = Path(out_path).read_text(encoding="utf-8", errors="replace")
            stats = read_stats(stats_file)
            for f in (stats_file, events_file, out_path):
                try:
                    os.unlink(f)
                except OSError:
                    pass
            tail = [ln for ln in text.strip().splitlines() if ln.strip()][-3:]
            failed_check = stats.get("check_failed")
            row = {"event": "stage_end", "stage": stage["name"], "attempt": attempt, "exit_code": code,
                   "seconds": round(time.time() - t0, 1), "done": code == 0, "last_lines": tail,
                   "check_failed": failed_check}
            for k in ("rounds", "answered_by_set", "calls_by_model", "tokens_by_model", "cost_by_model", "failures",
                      "refused_at_import", "waits", "waited_seconds"):
                if k in stats:
                    row[k] = stats[k]
            if stats.get("cost_by_model"):
                row["cost_note"] = "the program's own estimate; nothing is charged on a subscription"
            log(self.log_path, **row)
            for ln in tail:
                self.say("    " + ln)
            self.say("  exit code %d" % code)
            self.state["running"] = None
            if code == 0:
                self.state["done"][stage["name"]] = {"finished_at": now(), "attempts": attempt}
                self.state["failed_optional"].pop(stage["name"], None)
                self.save()
                self.checkpoint("stage_done", stage["name"], stats or counts, attempt=attempt)
                self.heartbeat(True, stage=None, status="between stages")
                return True, None
            self.save()
            if code in NO_RETRY_EXIT or failed_check:
                break
        return False, failed_check

    def on_event(self, stage, ev, counts, first_done):
        kind = ev.get("event")
        if kind == "round_end":
            merge_counts(counts, ev)
            self.heartbeat(True, round=ev.get("round", 0))
            if not first_done:
                self.checkpoint("first_round", stage["name"], counts)
        elif kind in ("waiting_on_limit", "resumed", "wait_cap_reached"):
            self.checkpoint("waiting_on_limit" if kind == "waiting_on_limit" else "resumed", stage["name"], counts,
                            note=None if kind != "wait_cap_reached" else "the waiting cap was reached")
            self.heartbeat(True, status="waiting" if kind == "waiting_on_limit" else "running")
        elif kind == "refused":
            log(self.log_path, event="refusal", stage=stage["name"], round=ev.get("round"), set=ev.get("set"),
                reason=ev.get("reason"), times_asked=ev.get("times_asked"))
        elif kind == "check_failed":
            log(self.log_path, event="check_failed", stage=stage["name"], reason=ev.get("reason"))


def read_events(path, offset):
    """(new offset, new complete JSON lines) of the events file written by run_live.py."""
    try:
        with open(path, "rb") as fh:
            fh.seek(offset)
            data = fh.read()
    except OSError:
        return offset, []
    end = data.rfind(b"\n")
    if end < 0:
        return offset, []
    rows = []
    for line in data[:end].decode("utf-8", "replace").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            pass
    return offset + end + 1, rows


# ------------------------------------------------------------------ waiting for a checkpoint

def count_lines(path):
    try:
        return len([x for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()])
    except OSError:
        return 0


def wait_checkpoint(plan, after, timeout_minutes, choices, poll=5.0, say=print):
    """Block until night_checkpoints.jsonl has more than `after` lines (0), time runs out (3), or the heartbeat
    is stale while a stage is running (4)."""
    d = Path(plan).resolve().parent
    cp, hb = d / CHECKPOINTS, d / HEARTBEAT
    stale_s = 60.0 * choices["night"]["stale_minutes"]
    t0 = time.time()
    while True:
        lines = [x for x in (cp.read_text(encoding="utf-8").splitlines() if cp.exists() else []) if x.strip()]
        if len(lines) > after:
            for ln in lines[after:]:
                say(ln)
            return 0
        state = read_state(d / STATE)
        if state.get("running"):
            age = time.time() - hb.stat().st_mtime if hb.exists() else float("inf")
            if age > stale_s:
                say("the heartbeat is stale (%s old) while stage %r is running: the runner died or the machine slept"
                    % ("no file" if age == float("inf") else "%.0f minutes" % (age / 60), state["running"]))
                return 4
        if timeout_minutes is not None and time.time() - t0 >= 60.0 * timeout_minutes:
            say("no new checkpoint line within %g minutes" % timeout_minutes)
            return 3
        time.sleep(poll)


# ------------------------------------------------------------------ the morning page

def fmt_counts(d):
    return ", ".join("%s %d" % (k, v) for k, v in sorted((d or {}).items())) or "none"


def morning_page(plan, choices):
    stages = load_plan(plan, choices)
    d = Path(plan).resolve().parent
    state = read_state(d / STATE)
    rows = [json.loads(x) for x in (d / LOG).read_text(encoding="utf-8").splitlines() if x.strip()] \
        if (d / LOG).exists() else []
    out = ["# The night, from the log", ""]
    starts = [r for r in rows if r["event"] == "night_start"]
    ends = [r for r in rows if r["event"] in ("night_end", "night_stop")]
    if starts:
        out.append("Started %s." % starts[0]["time"])
    if ends:
        out.append("Last stop of the runner: %s (%s)." % (ends[-1]["time"], "the night finished"
                                                         if ends[-1]["event"] == "night_end" else
                                                         "stopped at stage %s" % ends[-1].get("stage")))
    out += ["", "## Stages", ""]
    total_calls, total_tok = Counter(), Counter()
    open_start = {}
    stops, waits, refusals = [], [], Counter()
    for r in rows:
        ev = r["event"]
        if ev == "stage_start":
            open_start[r["stage"]] = r["time"]
        elif ev == "refusal":
            refusals[r["stage"]] += 1
        elif ev == "stage_end":
            out.append("- **%s**, attempt %d: %s to %s (%.0f seconds), %s." % (
                r["stage"], r["attempt"], open_start.get(r["stage"], "?"), r["time"], r["seconds"],
                "done" if r["done"] else "not done (exit code %d)" % r["exit_code"]))
            if r.get("answered_by_set") or r.get("calls_by_model"):
                out.append("  Calls answered by set: %s. By model: %s." % (fmt_counts(r.get("answered_by_set")),
                                                                         fmt_counts(r.get("calls_by_model"))))
                toks = {m: c.get("in", 0) + c.get("out", 0) for m, c in (r.get("tokens_by_model") or {}).items()}
                out.append("  Tokens (in plus out) by model: %s. Rounds: %s. Failures by reason: %s." % (
                    fmt_counts(toks), r.get("rounds", "-"), fmt_counts(r.get("failures"))))
                if r.get("cost_by_model"):
                    out.append("  Cost field by model: %s (%s)." % (
                        ", ".join("%s %.4f" % kv for kv in sorted(r["cost_by_model"].items())), r.get("cost_note")))
                total_calls.update(r.get("calls_by_model") or {})
                total_tok.update(toks)
            if not r["done"]:
                stops.append(r)
            for w in r.get("waits") or []:
                waits.append((r["stage"], w))
    out += ["", "## Totals", "", "Calls by model: %s. Tokens (in plus out) by model: %s." % (
        fmt_counts(total_calls), fmt_counts(total_tok))]
    if refusals:
        out.append("Answers refused at import, by stage: %s." % fmt_counts(refusals))
    out += ["", "## Stops", ""]
    if not stops:
        out.append("No stage stopped.")
    for r in stops:
        why = ("a check of the runner failed: %s" % r["check_failed"]) if r.get("check_failed") else (
            "calls were still pending, exit code %d" % r["exit_code"])
        out.append("- %s, attempt %d, at %s: %s." % (r["stage"], r["attempt"], r["time"], why))
    out += ["", "## Waits on the usage limit", ""]
    if not waits:
        out.append("None.")
    for name, w in waits:
        out.append("- %s: from %s to %s (%.0f seconds, %d probes), ended by %s." % (
            name, w.get("wait_start"), w.get("wait_end"), w.get("seconds", 0), w.get("probes", 0), w.get("ended_by")))
    notes = d / NOTES
    out += ["", "## What was done about it", ""]
    out.append(notes.read_text(encoding="utf-8").strip() if notes.exists() and notes.read_text(encoding="utf-8").strip()
               else "Nothing was written to %s." % NOTES)
    out += ["", "## Left to run", ""]
    left = [st for st in stages if st["name"] not in state["done"]]
    if not left:
        out.append("Nothing: every stage is done.")
    for st in left:
        out.append("- %s%s" % (st["name"], " (optional)" if st["optional"] else ""))
    return "\n".join(out) + "\n"


# ------------------------------------------------------------------ main

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plan", nargs="?")
    ap.add_argument("--status", action="store_true", help="print the state of the plan and stop")
    ap.add_argument("--dry-run", action="store_true", help="print the command of every stage and stop")
    ap.add_argument("--wait-checkpoint", metavar="PLAN", default=None)
    ap.add_argument("--after", type=int, default=0, help="with --wait-checkpoint: the number of lines already seen")
    ap.add_argument("--timeout-minutes", type=float, default=None)
    ap.add_argument("--poll-seconds", type=float, default=5.0, help=argparse.SUPPRESS)
    ap.add_argument("--morning-page", metavar="PLAN", default=None)
    ap.add_argument("--out", default=None, help="with --morning-page: the page to write")
    a = ap.parse_args(argv)
    choices = datasets.default_choices()
    if a.wait_checkpoint:
        return wait_checkpoint(a.wait_checkpoint, a.after, a.timeout_minutes, choices, a.poll_seconds)
    if a.morning_page:
        if not a.out:
            print("error: --morning-page needs --out PAGE.md")
            return 2
        try:
            page = morning_page(a.morning_page, choices)
        except PlanError as e:
            print("error: %s" % e)
            return 2
        Path(a.out).write_text(page, encoding="utf-8")
        print("wrote %s (%d lines)" % (a.out, len(page.splitlines())))
        return 0
    if not a.plan:
        print("error: give a plan file")
        return 2
    try:
        stages = load_plan(a.plan, choices)
    except PlanError as e:
        print("error: %s" % e)
        return 2
    night = Night(a.plan, choices)
    state = night.state
    if a.status:
        for st in stages:
            d = state["done"].get(st["name"])
            mark = "done at %s" % d["finished_at"] if d else (
                "failed (optional), not done" if st["name"] in state["failed_optional"] else "not done")
            print("%-30s %s%s" % (st["name"], mark, "  [optional]" if st["optional"] else ""))
        print("%d of %d stages done" % (len([s for s in stages if s["name"] in state["done"]]), len(stages)))
        if state.get("running"):
            print("state says stage %r is running" % state["running"])
        return 0
    if a.dry_run:
        for st in stages:
            skip = " (done: would be skipped)" if st["name"] in state["done"] else ""
            extra = "  [retries %d]" % st["retries"] if st["kind"] == "live" else ""
            print("%s%s%s%s\n  %s" % (st["name"], skip, "  [optional]" if st["optional"] else "", extra,
                                      shlex.join(argv_of(st, "<stats file>" if st["kind"] == "live" else None))))
        return 0
    log_path = night.log_path
    state["running"] = None
    log(log_path, event="night_start", plan=night.plan.name, stages=len(stages), done_already=len(state["done"]))
    stopped = None
    for st in stages:
        if st["name"] in state["done"]:
            log(log_path, event="stage_skipped_done", stage=st["name"])
            print("stage %r: done earlier, skipped" % st["name"])
            continue
        done, failed_check = night.run_stage(st)
        if done:
            continue
        night.checkpoint("stopped", st["name"], None, failed_check=failed_check, optional=st["optional"])
        if st["optional"]:
            state["failed_optional"][st["name"]] = now()
            night.save()
            log(log_path, event="stage_failed_optional_continuing", stage=st["name"])
            print("stage %r failed; it is optional, so the night goes on" % st["name"])
            continue
        stopped = st["name"]
        log(log_path, event="night_stop", stage=stopped)
        print("the night stopped at stage %r. Start the same command again to go on from there." % stopped)
        break
    night.heartbeat(True, stage=None, status="stopped" if stopped else "finished")
    if stopped:
        return 1
    log(log_path, event="night_end", done=len(state["done"]), optional_failed=len(state["failed_optional"]))
    night.checkpoint("night_done", None, None, done=len(state["done"]), optional_failed=len(state["failed_optional"]))
    print("the night is finished: %d of %d stages done%s" % (
        len([s for s in stages if s["name"] in state["done"]]), len(stages),
        ", %d optional failed" % len(state["failed_optional"]) if state["failed_optional"] else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
