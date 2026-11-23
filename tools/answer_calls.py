#!/usr/bin/env python3
"""Answer the pending AI calls of one live folder through the Claude Code command-line program.

Each pending call becomes one plain, separate model call:

    claude -p --safe-mode --system-prompt "<system_prompt>" --tools "" --disallowedTools "*"
           --strict-mcp-config --model <model> --output-format json --no-session-persistence

with the prompt on standard input, in a new empty temporary folder, with ANTHROPIC_API_KEY removed and
the variables of live.terminal.environment set (the two that switch off instructions files and memory, and
two that switch off telemetry and non-essential traffic). The model gets one text, has no
tools, sees no files and keeps nothing between calls. The calls use the command-line program's own sign-in.

The answers go to an answers file in the format `tools/run_advice.py import FILE` reads. The reply text is
kept as returned (one trailing newline removed); the import checks decide what an answer is. A second run
answers only what the answers file does not hold yet. Settings: D: live.terminal. After each call the model that answered
(the keys of modelUsage) must be exactly the id asked for; otherwise the reply is not stored (reason wrong_model).
Transient errors are retried after the waits of live.terminal.transient_waits_seconds. Exit code: 0 every call
asked for is answered, 4 some are left pending, 5 a usage limit stopped the run, 2 a bad input, no login, or
3 wrong-model answers in a row.
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import ai_live, datasets  # noqa: E402
from custody.core import CustodyError, canon  # noqa: E402

SETS = ("steps", "methods", "judge")
LOG = "terminal_calls.jsonl"
CONDITIONS = "terminal_conditions.json"
DEFAULT_OUT = "terminal_answers.jsonl"
WRONG_MODEL = "wrong_model"


# ------------------------------------------------------------------ pieces

def settings(choices):
    t = dict(choices["live"]["terminal"])
    t["models"] = dict(t["models"])
    t["environment"] = dict(t["environment"])
    return t


def build_command(claude_bin, system_prompt, model, effort):
    cmd = [claude_bin, "-p", "--safe-mode", "--system-prompt", system_prompt, "--tools", "",
           "--disallowedTools", "*", "--strict-mcp-config", "--model", model, "--output-format", "json",
           "--no-session-persistence"]
    if effort:
        cmd += ["--effort", str(effort)]
    return cmd


def clean_env(extra=None):
    """The environment of a call: the machine's, without the API key, plus live.terminal.environment."""
    if extra is None:
        extra = settings(datasets.default_choices())["environment"]
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)
    env.update(extra)
    return env


def read_jsonl(path):
    out = []
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if line.strip():
                out.append(json.loads(line))
    return out


def check_login(claude_bin):
    """Run `auth status` and read only whether the login works and the field authMethod. Nothing else
    of its output is kept, printed or stored. Returns the method (a short plain word) or raises."""
    try:
        p = subprocess.run([claude_bin, "auth", "status"], capture_output=True, text=True, timeout=60,
                           env=clean_env(), stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        raise CustodyError("could not run '%s auth status'; check --claude-bin" % claude_bin)
    try:
        data = json.loads(p.stdout)
    except ValueError:
        data = None
    if not isinstance(data, dict):
        raise CustodyError("'%s auth status' gave no readable answer: not logged in? Log in with the claude "
                           "program first." % claude_bin)
    logged = data.get("loggedIn")
    method = data.get("authMethod")
    ok = (logged is True) if "loggedIn" in data else (p.returncode == 0 and bool(method))
    if p.returncode != 0 and logged is not True:
        ok = False
    if not ok:
        raise CustodyError("the claude program is not logged in; log in with it first, then run this again")
    word = "".join(ch for ch in str(method) if ch.isalnum() or ch in "_.-")[:40] if method else "unknown"
    return word


def program_version(claude_bin):
    try:
        p = subprocess.run([claude_bin, "--version"], capture_output=True, text=True, timeout=60,
                           env=clean_env(), stdin=subprocess.DEVNULL)
        return (p.stdout.strip().splitlines() or ["unknown"])[0][:80]
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def write_conditions(live_dir, record):
    """live/private/terminal_conditions.json: what the answers were made under (to go with the manifest)."""
    path = ai_live.private_dir(live_dir) / CONDITIONS
    path.parent.mkdir(parents=True, exist_ok=True)
    key = {k: record[k] for k in ("system_prompt", "models", "effort", "claude_version")}
    earlier = []
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            earlier = old.get("earlier", [])
            if {k: old.get(k) for k in key} != key:
                earlier.append({k: old.get(k) for k in list(key) + ["written_at"]})
        except ValueError:
            pass
    record = dict(record, earlier=earlier)
    path.write_text(json.dumps(record, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def ints(d, *names):
    for n in names:
        v = d.get(n) if isinstance(d, dict) else None
        if isinstance(v, int) and not isinstance(v, bool):
            return v
    return 0


def parse_result(stdout):
    """(reply text or None, info dict, failure reason or None) from the program's printed JSON."""
    try:
        data = json.loads(stdout)
    except ValueError:
        return None, {}, "output is not JSON"
    if not isinstance(data, dict):
        return None, {}, "output is not a JSON object"
    sub = data.get("subtype")
    usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
    mu = data.get("modelUsage") if isinstance(data.get("modelUsage"), dict) else {}
    info = {"subtype": sub if isinstance(sub, str) else None,
            "models_answered": sorted(mu.keys()),
            "input_tokens": ints(usage, "input_tokens"), "output_tokens": ints(usage, "output_tokens"),
            "cache_creation_input_tokens": ints(usage, "cache_creation_input_tokens"),
            "cache_read_input_tokens": ints(usage, "cache_read_input_tokens"),
            "duration_ms": data.get("duration_ms") if isinstance(data.get("duration_ms"), (int, float)) else None,
            "cost": data.get("total_cost_usd") if isinstance(data.get("total_cost_usd"), (int, float))
            and not isinstance(data.get("total_cost_usd"), bool) else None,
            "by_model": {str(m): {"in": ints(v, "inputTokens", "input_tokens"),
                                  "cache": ints(v, "cacheReadInputTokens", "cache_read_input_tokens")
                                  + ints(v, "cacheCreationInputTokens", "cache_creation_input_tokens"),
                                  "out": ints(v, "outputTokens", "output_tokens")}
                         for m, v in mu.items()}}
    if sub is not None and sub != "success":
        return None, info, "subtype %s" % sub
    if data.get("is_error") is True:
        return None, info, "is_error true"
    res = data.get("result")
    if not isinstance(res, str):
        return None, info, "result is not text"
    return res, info, None


def one_attempt(cmd, prompt, timeout, env=None):
    """Run the program once in a new empty folder. Returns (exit code, stdout, stderr, wall seconds, cwd seen)."""
    work = tempfile.mkdtemp(prefix="custody_call_")
    t0 = time.time()
    try:
        try:
            p = subprocess.run(cmd, input=prompt, capture_output=True, text=True, cwd=work, env=clean_env(env),
                               timeout=timeout)
            return p.returncode, p.stdout, p.stderr, time.time() - t0
        except subprocess.TimeoutExpired:
            return "timeout", "", "", time.time() - t0
        except OSError as e:
            return "oserror", "", str(e.__class__.__name__), time.time() - t0
    finally:
        shutil.rmtree(work, ignore_errors=True)


def keep_calls(live_dir, calls, export_sets):
    """Keep every call exactly as it was exported (the fields of the handout row, prompt included) in
    live/private/calls_kept_<set>.jsonl, once per call id, before the call is made. A finished run deletes the
    handout files; the second judge and the owner's own review need the prompts afterwards. Nothing reads these
    files during the run and they are never exported."""
    priv = ai_live.private_dir(live_dir)
    priv.mkdir(parents=True, exist_ok=True)
    have = {}
    by_set = defaultdict(list)
    for c in calls:
        by_set[ai_live.set_of(c["prompt_id"], export_sets)].append(c)
    for set_name, rows in by_set.items():
        path = priv / ("calls_kept_%s.jsonl" % set_name)
        have = {r.get("call_id") for r in read_jsonl(path)}
        with open(str(path), "a", encoding="utf-8") as fh:
            for c in rows:
                if c["call_id"] in have:
                    continue
                have.add(c["call_id"])
                fh.write(canon({k: v for k, v in c.items() if k != "real"}) + "\n")
            fh.flush()


def is_transient(code, text, phrases):
    """A timeout, a failure to start, or a reply that names an overloaded server, a 5xx or a network error."""
    if code in ("timeout", "oserror"):
        return True
    low = text.lower()
    return any(p.lower() in low for p in phrases)


def probe(claude_bin, choices=None, timeout=None):
    """One tiny call on the cheapest model (the steps model). True when it answers. Used to see whether a
    usage limit has lifted."""
    choices = choices or datasets.default_choices()
    t = settings(choices)
    model = t["models"]["steps"]
    cmd = build_command(claude_bin, t["system_prompt"], model, t["effort"])
    code, so, se, _ = one_attempt(cmd, t["probe_prompt"], timeout or t["timeout_seconds"], t["environment"])
    if code != 0:
        return False
    res, info, why = parse_result(so)
    return why is None and info.get("models_answered") == [model]


# ------------------------------------------------------------------ the work

def answer(live_dir, sets=SETS, workers=None, limit=None, claude_bin="claude", models=None, effort="unset",
           out=None, dry_run=False, say=print, choices=None, check_auth=True, transient_waits=None):
    """Answer the pending calls of the chosen sets. Returns a dict of counts (see the keys at the end).
    transient_waits overrides live.terminal.transient_waits_seconds (tests)."""
    choices = choices or datasets.default_choices()
    t = settings(choices)
    if models:
        t["models"].update({k: v for k, v in models.items() if v})
    if effort != "unset":
        t["effort"] = effort
    waits = list(t["transient_waits_seconds"] if transient_waits is None else transient_waits)
    workers = workers or t["workers"]
    export_sets = choices["live"]["export_sets"]
    live_dir = Path(live_dir)
    out = Path(out) if out else ai_live.private_dir(live_dir) / DEFAULT_OUT
    pending = list(ai_live.read_pending(live_dir).values())
    pending = [c for c in pending if ai_live.set_of(c["prompt_id"], export_sets) in sets]
    done = {r.get("call_id") for r in read_jsonl(out)}
    todo = [c for c in pending if c["call_id"] not in done]
    if limit:
        todo = todo[:limit]
    result = {"answered": 0, "failed": 0, "left_pending": 0, "limit_hit": False, "out": str(out),
              "pending": len(pending), "already": len(pending) - len([c for c in pending if c["call_id"] not in done]),
              "by_model": {}, "wall": 0.0, "set_of": {}, "asked": len(todo), "wrong_model_stop": False,
              "answered_by_set": {}, "failures": {}, "cost_by_model": {}, "calls_by_model": {}}
    if not todo:
        say("nothing to answer: %d pending calls in the chosen sets, %d already in %s" % (len(pending), result["already"], out))
        return result
    first = todo[0]
    first_set = ai_live.set_of(first["prompt_id"], export_sets)
    if dry_run:
        cmd = build_command(claude_bin, t["system_prompt"], t["models"][first_set], t["effort"])
        say("dry run: %d calls would be asked. For the first (%s set) the command is, with the prompt on "
            "standard input and left out here:" % (len(todo), first_set))
        say("  " + shlex.join(cmd))
        say("  working folder: a new empty temporary folder; ANTHROPIC_API_KEY removed; %s"
            % " ".join("%s=%s" % kv for kv in sorted(t["environment"].items())))
        return result
    if os.environ.get("ANTHROPIC_API_KEY"):
        say("ANTHROPIC_API_KEY is set in the environment: it is ignored. The calls use the command-line program's own sign-in.")
    method = check_login(claude_bin) if check_auth else "not checked"
    say("login works (method: %s)" % method)
    version = program_version(claude_bin)
    write_conditions(live_dir, {"system_prompt": t["system_prompt"], "models": t["models"], "effort": t["effort"],
                                "claude_version": version, "auth_method": method,
                                "timeout_seconds": t["timeout_seconds"], "workers": workers,
                                "written_at": time.strftime("%Y-%m-%dT%H:%M:%S%z")})
    log_path = ai_live.private_dir(live_dir) / LOG
    out.parent.mkdir(parents=True, exist_ok=True)
    keep_calls(live_dir, todo, export_sets)
    lock = threading.Lock()
    stop = threading.Event()
    phrases = [p.lower() for p in t["limit_phrases"]]
    by_model = defaultdict(lambda: Counter())
    cost = defaultdict(float)
    calls_model = Counter()
    answered_set = Counter()
    failures = Counter()
    stats = Counter()
    wrong_row = [0]
    t0 = time.time()

    def record(call, set_name, model, retry, code, wall, info, ok, reply, reason):
        row = {"call_id": call["call_id"], "set": set_name, "prompt_id": call["prompt_id"], "model_asked": model,
               "models_answered": info.get("models_answered", []),
               "input_tokens": info.get("input_tokens", 0), "output_tokens": info.get("output_tokens", 0),
               "cache_creation_input_tokens": info.get("cache_creation_input_tokens", 0),
               "cache_read_input_tokens": info.get("cache_read_input_tokens", 0),
               "cost_usd_estimate": info.get("cost"),
               "duration_ms": info.get("duration_ms"), "wall_seconds": round(wall, 2), "exit_code": code,
               "subtype": info.get("subtype"), "retry": retry, "answered": ok, "reason": reason,
               "claude_version": version, "time": time.strftime("%Y-%m-%dT%H:%M:%S%z")}
        with lock:
            with open(str(log_path), "a", encoding="utf-8") as fh:
                fh.write(canon(row) + "\n")
                fh.flush()
            calls_model[model] += 1
            if info.get("cost") is not None:
                cost[model] += info["cost"]
            if ok:
                with open(str(out), "a", encoding="utf-8") as fh:
                    fh.write(canon({"call_id": call["call_id"], "prompt_fp": call["prompt_fp"],
                                    "output": reply}) + "\n")
                    fh.flush()
                for m, v in (info.get("by_model") or {model: {"in": row["input_tokens"],
                                                               "cache": row["cache_creation_input_tokens"] + row["cache_read_input_tokens"],
                                                               "out": row["output_tokens"]}}).items():
                    by_model[m].update(v)

    def work(call):
        if stop.is_set():
            return
        set_name = ai_live.set_of(call["prompt_id"], export_sets)
        model = t["models"][set_name]
        cmd = build_command(claude_bin, t["system_prompt"], model, t["effort"])
        attempt = 0
        n_transient = 0
        n_other = 0
        while True:
            if stop.is_set():
                return
            code, so, se, wall = one_attempt(cmd, call["prompt"], t["timeout_seconds"], t["environment"])
            reply, info, why = (None, {}, "exit code %s" % code) if code != 0 else parse_result(so)
            if code != 0:
                _, info, _ = parse_result(so)
            ok = why is None
            reason = None
            if ok and info.get("models_answered") != [model]:
                ok = False
                reason = WRONG_MODEL
            if ok and reply.endswith("\n"):
                reply = reply[:-1]
            shown = (so + "\n" + se).lower()
            limit_now = (not ok) and reason is None and any(p in shown for p in phrases)
            trans = (not ok) and reason is None and not limit_now and is_transient(code, shown, t["transient_phrases"])
            if not ok and reason is None:
                reason = "limit" if limit_now else ("transient" if trans else "other")
            record(call, set_name, model, bool(attempt), code, wall, info, ok, reply, reason)
            attempt += 1
            if ok:
                with lock:
                    stats["answered"] += 1
                    answered_set[set_name] += 1
                    wrong_row[0] = 0
                return
            if reason == WRONG_MODEL:
                with lock:
                    failures[WRONG_MODEL] += 1
                    stats["failed"] += 1
                    wrong_row[0] += 1
                    if wrong_row[0] >= t["wrong_model_stop_after"]:
                        stats["wrong_model_stop"] = 1
                        stop.set()
                return
            if limit_now:
                stop.set()
                with lock:
                    stats["limit"] += 1
                    failures["limit"] += 1
                return
            if trans and n_transient < len(waits):
                with lock:
                    failures["transient"] += 1
                stop.wait(waits[n_transient])
                n_transient += 1
                continue
            if not trans and n_other < 1:
                with lock:
                    failures["other"] += 1
                n_other += 1
                continue
            with lock:
                failures[reason] += 1
                stats["failed"] += 1
            return

    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        list(ex.map(work, todo))
    result["answered"] = stats["answered"]
    result["failed"] = stats["failed"]
    result["limit_hit"] = bool(stats["limit"])
    result["wrong_model_stop"] = bool(stats["wrong_model_stop"])
    result["left_pending"] = len(todo) - stats["answered"]
    result["wall"] = time.time() - t0
    result["by_model"] = {m: dict(c) for m, c in by_model.items()}
    result["answered_by_set"] = dict(answered_set)
    result["failures"] = dict(failures)
    result["cost_by_model"] = {m: round(v, 6) for m, v in cost.items()}
    result["calls_by_model"] = dict(calls_model)
    result["set_of"] = {c["call_id"]: ai_live.set_of(c["prompt_id"], export_sets) for c in todo}
    say("answered %d, failed %d, left pending %d (of %d asked); wall time %.1f s" % (
        result["answered"], result["failed"], result["left_pending"], len(todo), result["wall"]))
    say("  answered by set: %s" % (", ".join("%s %d" % kv for kv in sorted(answered_set.items())) or "none"))
    for m, c in sorted(result["by_model"].items()):
        say("  %s: tokens in %d (plus %d cached), out %d" % (m, c.get("in", 0), c.get("cache", 0), c.get("out", 0)))
    for m, v in sorted(result["cost_by_model"].items()):
        say("  %s: cost field %.4f (%s)" % (m, v, t["cost_label"]))
    if result["failures"]:
        say("  failures by reason: %s" % ", ".join("%s %d" % kv for kv in sorted(result["failures"].items())))
    if result["wrong_model_stop"]:
        say("STOPPED: %d calls in a row were answered by another model than the one asked for (reason wrong_model). "
            "Nothing from them was stored. Check the model ids in live.terminal.models and the claude program."
            % t["wrong_model_stop_after"])
    elif result["limit_hit"]:
        say("STOPPED: a usage limit was reached. What was answered is in %s. Run again when the limit resets; "
            "the run picks up where it stopped." % out)
    elif result["left_pending"]:
        say("%d calls are still pending; run this again to retry them" % result["left_pending"])
    say("answers: %s (import with: python3 tools/run_advice.py import %s ...)" % (out, out))
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live-dir", default=str(ROOT / "live"))
    ap.add_argument("--set", choices=list(SETS) + ["all"], default="all", dest="which")
    ap.add_argument("--workers", type=int, default=None, help="calls side by side (default D: live.terminal.workers)")
    ap.add_argument("--limit", type=int, default=None, help="answer at most this many calls")
    ap.add_argument("--dry-run", action="store_true", help="print the command for the first pending call and stop")
    ap.add_argument("--claude-bin", default="claude")
    ap.add_argument("--model-steps", default=None)
    ap.add_argument("--model-methods", default=None)
    ap.add_argument("--model-judge", default=None)
    ap.add_argument("--effort", default="unset", help="effort level; default D: live.terminal.effort (null: no flag)")
    ap.add_argument("--out", default=None, help="the answers file (default live/private/terminal_answers.jsonl)")
    ap.add_argument("--transient-waits", default=None, help=argparse.SUPPRESS)
    a = ap.parse_args(argv)
    sets = SETS if a.which == "all" else (a.which,)
    tw = None if a.transient_waits is None else [float(x) for x in a.transient_waits.split(",") if x != ""]
    try:
        r = answer(a.live_dir, sets, a.workers, a.limit, a.claude_bin,
                   {"steps": a.model_steps, "methods": a.model_methods, "judge": a.model_judge},
                   a.effort, a.out, a.dry_run, transient_waits=tw)
    except CustodyError as e:
        print("error: %s" % e)
        return 2
    if r["wrong_model_stop"]:
        return 2
    if r["limit_hit"]:
        return 5
    return 4 if r["left_pending"] else 0


if __name__ == "__main__":
    sys.exit(main())
