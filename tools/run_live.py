#!/usr/bin/env python3
"""One command for a live run through the command line: the rounds of tools/run_advice.py with
tools/answer_calls.py answering each round.

    run_advice.py run   ->   while calls are pending:  answer_calls  ->  run_advice.py import  ->  run_advice.py run

It takes the selection options of run_advice.py (--split --name --visits --live-dir --runs-dir --limit
--conditions --batch-size --after-freeze-change --levels --sealed) and passes them through. It prints, per
round, only counts: calls pending by set, answered, failed, refused at import (with the reasons the import
prints) and tokens. It never prints the scores table or any outcome of the experiment: at the end it says where
the results file is. It stops with a message when a round answers nothing, when the import refuses every answer
when the limit of rounds is reached, or when a usage limit is hit.
Exit code: 0 finished, 1 stopped with calls pending, 2 a bad input or 3 wrong-model answers in a row,
5 a usage limit stopped the run (what was answered is saved; run the same command again later),
6 one of the runner's own checks failed (see below).

The runner's own checks (a program, no AI), after every round: every answer imported is gone from the pending
list and the round stored at least one answer; a call whose answer the import refuses is asked again until it has
been asked night.tries_per_call times, then the check fails; too many refused answers in one round
(night.max_refused_share) fail it at once; the model check; the shares of empty answers and refusal candidates;
and, when --expect is given (the plan's "expect" of the stage), calls and tokens per call against it. The
reason of a failed check is printed, written to the stats file and the events file, and the run stops.
--events-out FILE appends one JSON line per round, wait, refusal and failed check (counts and formats only,
never a text of a call), for tools/run_night.py.

With --wait-on-limit a usage-limit stop does not end the run: it waits, makes one tiny call on the cheapest
model every night.probe_minutes until that call answers, and goes on with the same round. Total waiting is capped
by night.max_wait_hours; every wait is logged (start and end) in live/private/terminal_waits.jsonl.
Any option this tool does not know (for example --plan, --part, --rule) is passed unchanged to every run_advice.py
call, so that new selection options need no change here. --stats-out FILE writes the counts of the whole call (rounds, answered by set, tokens and cost field by model,
failures by reason, waits) as JSON, for tools/run_night.py. Counts only.
"""
import argparse
import builtins
import contextlib
import importlib.util
import functools
import io
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from custody import ai_live, datasets  # noqa: E402
from custody.core import CustodyError  # noqa: E402
import answer_calls  # noqa: E402

# every printed line is flushed at once, so that a log file fills while the run works
print = functools.partial(builtins.print, flush=True)  # noqa: A001

CHECK_EXIT = 6


def load_advice():
    spec = importlib.util.spec_from_file_location("run_advice", str(ROOT / "tools" / "run_advice.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def quiet(fn, argv):
    """Call a tool's main with its screen output captured; returns (exit code, output text)."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = fn(argv)
    return code, buf.getvalue()


def pending_by_set(live_dir, choices):
    c = Counter()
    for row in ai_live.read_pending(live_dir).values():
        c[ai_live.set_of(row["prompt_id"], choices["live"]["export_sets"])] += 1
    return {s: c.get(s, 0) for s in answer_calls.SETS}


def selection(a):
    sel = ["--experiment", str(a.experiment), "--split", a.split, "--visits", a.visits, "--live-dir", a.live_dir,
           "--runs-dir", a.runs_dir]
    for flag, val in (("--name", a.name), ("--limit", a.limit), ("--trial", a.trial), ("--conditions", a.conditions),
                      ("--batch-size", a.batch_size), ("--after-freeze-change", a.after_freeze_change),
                      ("--levels", a.levels), ("--filing-dir", a.filing_dir), ("--ai-parts", a.ai_parts)):
        if val not in (None, ""):
            sel += [flag, str(val)]
    if a.sealed:
        sel.append("--sealed")
    return sel


# ------------------------------------------------------------------ the runner's own checks

def stored_files(live_dir):
    return sorted(ai_live.private_dir(live_dir).glob("terminal_answers_*_r*.jsonl"))


def stage_answers(live_dir):
    """(times each call was answered, the last output of each call) over every round file of this live folder."""
    asked, outputs = Counter(), {}
    for f in stored_files(live_dir):
        for row in answer_calls.read_jsonl(f):
            asked[row["call_id"]] += 1
            outputs[row["call_id"]] = row.get("output") or ""
    return asked, outputs


def call_sets(live_dir):
    """call id -> set, and tokens (input plus output) and number of answered calls by set, from the call log."""
    sets, tok, n = {}, Counter(), Counter()
    for row in answer_calls.read_jsonl(ai_live.private_dir(live_dir) / answer_calls.LOG):
        if row.get("answered"):
            sets[row["call_id"]] = row["set"]
            tok[row["set"]] += row.get("input_tokens", 0) + row.get("output_tokens", 0)
            n[row["set"]] += 1
    return sets, tok, n


def finished_cases(run_dir):
    """Cases with a result, not crashed, for every condition of the run (manifest.json, results.jsonl)."""
    run_dir = Path(run_dir)
    try:
        conds = set(json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))["conditions"])
        rows = answer_calls.read_jsonl(run_dir / "results.jsonl")
    except (OSError, ValueError, KeyError):
        return 0
    have = {}
    for r in rows:
        if not r.get("crashed"):
            have.setdefault(r["visit_id"], set()).add(r["condition"])
    return len([v for v, c in have.items() if conds <= c])


def load_expect(text):
    if not text:
        return None
    try:
        data = json.loads(text) if text.lstrip().startswith("{") else json.loads(Path(text).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise CustodyError("--expect is neither JSON nor a readable JSON file")
    if not isinstance(data, dict):
        raise CustodyError("--expect must be a JSON object")
    return data


def check_shares(live_dir, choices):
    """A failed-check reason when empty answers or refusal candidates are too common among the steps answers."""
    n = choices["night"]
    asked, outputs = stage_answers(live_dir)
    sets, _, _ = call_sets(live_dir)
    steps = [outputs[c] for c in outputs if sets.get(c) == "steps"]
    if len(steps) < n["min_answers_for_shares"]:
        return None
    window = choices["live"]["unusable"]["candidate_window"]
    phrases = [x.lower() for x in choices["live"]["unusable"]["refusal_candidates"]]
    empty = sum(1 for o in steps if not o.strip())
    cand = sum(1 for o in steps if any(x in o[:window].lower() for x in phrases))
    if empty / len(steps) >= n["max_empty_share"]:
        return "empty_share (%d of %d step answers are empty)" % (empty, len(steps))
    if cand / len(steps) >= n["max_refusal_candidate_share"]:
        return "refusal_candidate_share (%d of %d step answers)" % (cand, len(steps))
    return None


def check_expect(live_dir, expect, choices, final=False, run_dir=None):
    """A failed-check reason against the stage's expect, or None. During the stage: calls_max and tokens per
    call; at the end also calls_min and the number of finished cases."""
    if not expect:
        return None
    asked, _ = stage_answers(live_dir)
    calls = len(asked)
    if "calls_max" in expect and calls > expect["calls_max"]:
        return "calls_over_max (%d answered, the most expected is %d)" % (calls, expect["calls_max"])
    _, tok, n = call_sets(live_dir)
    for name, top in (expect.get("tokens_per_call_max") or {}).items():
        if n[name] >= choices["night"]["min_calls_for_token_check"] and tok[name] / n[name] > top:
            return "tokens_per_call_over_max (%s: %.0f a call, the most expected is %s)" % (name, tok[name] / n[name], top)
    if final:
        if "calls_min" in expect and calls < expect["calls_min"]:
            return "calls_below_min (%d answered, at least %d expected)" % (calls, expect["calls_min"])
        if "cases" in expect:
            got = finished_cases(run_dir)
            if got != expect["cases"]:
                return "cases_mismatch (%d finished, %d expected)" % (got, expect["cases"])
    return None


def verify_round(live_dir, out, r, refused, pending_after, choices, events):
    """The checks of one round that has been imported and re-run. Returns a reason or None."""
    n = choices["night"]
    rows = answer_calls.read_jsonl(out)
    by_line = {i + 1: row for i, row in enumerate(rows)}
    refused_ids = {by_line[ln]["call_id"] for _, ln, _ in refused if ln in by_line}
    accepted = {row["call_id"] for row in rows} - refused_ids
    if not rows:
        return "no_answer_stored"
    if accepted & set(pending_after):
        return "pending_not_cleared (%d imported answers are still pending)" % len(accepted & set(pending_after))
    asked, _ = stage_answers(live_dir)
    for _, ln, why in refused:
        if ln in by_line:
            cid = by_line[ln]["call_id"]
            events(event="refused", call_id=cid, set=r["set_of"].get(cid, "?"), reason=why[:120],
                   times_asked=asked[cid])
    stuck = [c for c in refused_ids if asked[c] >= n["tries_per_call"]]
    if stuck:
        return "refused_after_%d_tries (%d calls)" % (n["tries_per_call"], len(stuck))
    if len(refused_ids) >= n["min_refused_for_share"] and len(refused_ids) / len(rows) > n["max_refused_share"]:
        return "refused_share (%d of %d answers of this round)" % (len(refused_ids), len(rows))
    return None



def refused_reasons(text):
    """The reasons of the import's 'refused <file> line <n>: <reason>' lines, and the line numbers by file."""
    out = []
    for m in re.finditer(r"^\s+refused (\S+) line (\d+): (.*)$", text, re.M):
        out.append((m.group(1), int(m.group(2)), m.group(3)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("--experiment", type=int, choices=[1, 2], required=True,
                    help="1: transcripts (the words flow), 2: questions (the advice flow); separate cases, run and live folders")
    ap.add_argument("--split", choices=["all", "test", "tune"], default="tune")
    ap.add_argument("--name", default=None)
    ap.add_argument("--cases", "--visits", dest="visits", default=None, help="default data/cases/exp<experiment>.jsonl")
    ap.add_argument("--live-dir", default=None, help="default live_e<experiment>/")
    ap.add_argument("--trial", type=int, default=None, metavar="N",
                    help="N clean practice cases plus the practice violations of the experiment")
    ap.add_argument("--runs-dir", default=str(ROOT / "runs"))
    ap.add_argument("--limit", type=int, default=None, help="only the first n visits of the split")
    ap.add_argument("--conditions", default=None)
    ap.add_argument("--ai-parts", choices=["on", "off"], default="on")
    ap.add_argument("--batch-size", type=int, default=0)
    ap.add_argument("--after-freeze-change", default=None, metavar="REASON")
    ap.add_argument("--filing-dir", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--levels", choices=["reader_first", "judge_all"], default=None)
    ap.add_argument("--sealed", action="store_true")
    ap.add_argument("--max-rounds", type=int, default=12)
    ap.add_argument("--set", choices=list(answer_calls.SETS) + ["all"], default="all", dest="which")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--claude-bin", default="claude")
    ap.add_argument("--model-steps", default=None)
    ap.add_argument("--model-methods", default=None)
    ap.add_argument("--model-judge", default=None)
    ap.add_argument("--effort", default="unset")
    ap.add_argument("--wait-on-limit", action="store_true",
                    help="on a usage-limit stop, wait and probe until calls answer again, then go on")
    ap.add_argument("--probe-minutes", type=float, default=None, help="default D: night.probe_minutes")
    ap.add_argument("--max-wait-hours", type=float, default=None, help="default D: night.max_wait_hours")
    ap.add_argument("--stats-out", default=None, help="write the counts of this call as JSON to FILE")
    ap.add_argument("--transient-waits", default=None, help=argparse.SUPPRESS)
    ap.add_argument("--expect", default=None, help="the stage's expect, as JSON text or a JSON file")
    ap.add_argument("--events-out", default=None, help="append counts of each round, wait and check to FILE")
    a, extra = ap.parse_known_args(argv)
    a.name = a.name or ("advice_%s_e%d" % ("trial" if a.trial else a.split, a.experiment))
    a.visits = a.visits or str(ROOT / "data" / "cases" / ("exp%d.jsonl" % a.experiment))
    a.live_dir = a.live_dir or str(ROOT / ("live_e%d" % a.experiment))
    RA = load_advice()
    sel = selection(a) + list(extra)     # any option this tool does not know is passed on to run_advice.py
    live_dir = Path(a.live_dir)
    choices = datasets.default_choices()
    sets = answer_calls.SETS if a.which == "all" else (a.which,)
    stamp = time.strftime("%Y%m%dT%H%M%S")
    probe_s = 60.0 * (a.probe_minutes if a.probe_minutes is not None else choices["night"]["probe_minutes"])
    max_wait_s = 3600.0 * (a.max_wait_hours if a.max_wait_hours is not None else choices["night"]["max_wait_hours"])
    tw = None if a.transient_waits is None else [float(x) for x in a.transient_waits.split(",") if x != ""]
    expect = load_expect(a.expect)
    S = {"rounds": 0, "answered_by_set": Counter(), "tokens_by_model": {}, "cost_by_model": Counter(),
         "calls_by_model": Counter(), "failures": Counter(), "refused_at_import": 0, "waits": [], "waited_seconds": 0.0,
         "check_failed": None}
    cur = {"round": 0}

    def events(**row):
        if a.events_out:
            row = dict({"time": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "round": cur["round"]}, **row)
            with open(a.events_out, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")
                fh.flush()

    def finish(code, msg=None):
        if msg:
            print(msg)
        if a.stats_out:
            Path(a.stats_out).write_text(json.dumps({
                "exit_code": code, "rounds": S["rounds"], "answered_by_set": dict(S["answered_by_set"]),
                "tokens_by_model": S["tokens_by_model"], "cost_by_model": dict(S["cost_by_model"]),
                "calls_by_model": dict(S["calls_by_model"]), "failures": dict(S["failures"]),
                "refused_at_import": S["refused_at_import"], "waits": S["waits"],
                "waited_seconds": round(S["waited_seconds"], 1), "check_failed": S["check_failed"]},
                indent=1, sort_keys=True) + "\n", encoding="utf-8")
        return code

    def fail_check(reason):
        S["check_failed"] = reason
        events(event="check_failed", reason=reason)
        return finish(CHECK_EXIT, "stopped: a check of the runner failed: %s. The stage is stopped; what was "
                                  "answered is saved." % reason)

    code, text = quiet(RA.main, ["run"] + sel)
    if code == 2:
        return finish(2, "error from run_advice.py: " + text.strip().splitlines()[-1] if text.strip() else "error")
    n = 0
    while code != 0:
        n += 1
        if n > a.max_rounds:
            return finish(1, "stopped: %d rounds were run and calls are still pending" % a.max_rounds)
        S["rounds"] = max(S["rounds"], n)
        cur["round"] = n
        pend = pending_by_set(live_dir, choices)
        print("round %d: pending %s" % (n, ", ".join("%s %d" % kv for kv in pend.items())))
        out = live_dir / "private" / ("terminal_answers_%s_r%02d.jsonl" % (stamp, n))
        try:
            r = answer_calls.answer(live_dir, sets, a.workers, None, a.claude_bin,
                                    {"steps": a.model_steps, "methods": a.model_methods, "judge": a.model_judge},
                                    a.effort, out, False, say=lambda s: None, choices=choices, transient_waits=tw)
        except CustodyError as e:
            return finish(2, "error: %s" % e)
        for m, c in r["by_model"].items():
            S["tokens_by_model"].setdefault(m, Counter()).update(c)
        S["answered_by_set"].update(r["answered_by_set"])
        S["cost_by_model"].update(r["cost_by_model"])
        S["calls_by_model"].update(r["calls_by_model"])
        S["failures"].update(r["failures"])
        tok = {k: sum(c.get(k, 0) for c in r["by_model"].values()) for k in ("in", "cache", "out")}
        print("  answered %d (%s), failed %d; tokens in %d (plus %d cached), out %d" % (
            r["answered"], ", ".join("%s %d" % kv for kv in sorted(r["answered_by_set"].items())) or "none",
            r["failed"], tok["in"], tok["cache"], tok["out"]))
        for m, c in sorted(r["by_model"].items()):
            print("    %s: in %d, cached %d, out %d; cost field %.4f" % (
                m, c.get("in", 0), c.get("cache", 0), c.get("out", 0), r["cost_by_model"].get(m, 0.0)))
        print("    (cost field: %s)" % choices["live"]["terminal"]["cost_label"])
        if r["failures"]:
            print("    failures by reason: %s" % ", ".join("%s %d" % kv for kv in sorted(r["failures"].items())))
        events(event="round_end", answered_by_set=r["answered_by_set"], failed=r["failed"], tokens_by_model=r["by_model"],
               cost_by_model=r["cost_by_model"], failures=r["failures"], limit_hit=r["limit_hit"])
        if r["wrong_model_stop"]:
            _import(RA, sel, out)
            S["check_failed"] = "wrong_model"
            events(event="check_failed", reason="wrong_model")
            return finish(2, "stopped: %d calls in a row were answered by another model than the one asked for "
                             "(wrong_model). Nothing from them was stored."
                          % choices["live"]["terminal"]["wrong_model_stop_after"])
        if r["limit_hit"]:
            _import(RA, sel, out)
            if not a.wait_on_limit:
                return finish(5, "stopped: a usage limit was reached. Answered so far: %s. Run the same command again later." % out)
            events(event="waiting_on_limit")
            ok = wait_for_reset(a, choices, probe_s, max_wait_s, S)
            events(event="resumed" if ok else "wait_cap_reached", waits=S["waits"][-1:])
            if not ok:
                return finish(5, "stopped: a usage limit was reached and the waiting cap (%g hours) is used up. "
                                 "What was answered is saved; run the same command again later." % (max_wait_s / 3600.0))
            code, text = quiet(RA.main, ["run"] + sel)
            if code == 2:
                return finish(2, "error from run_advice.py: " + (text.strip().splitlines()[-1] if text.strip() else ""))
            n -= 1      # the same round goes on
            continue
        if r["answered"] == 0:
            S["check_failed"] = "no_answer_stored"
            events(event="check_failed", reason="no_answer_stored")
            return finish(1, "stopped: this round answered nothing (%d calls failed). Nothing was imported." % r["failed"])
        icode, itext = quiet(RA.main, ["import", str(out)] + sel)
        refused = refused_reasons(itext)
        S["refused_at_import"] += len(refused)
        print("  refused at import: %d" % len(refused))
        for _, ln, why in refused[:10]:
            print("    line %d: %s" % (ln, why))
        if len(refused) > 10:
            print("    and %d more" % (len(refused) - 10))
        code, text = quiet(RA.main, ["run"] + sel)
        if code == 2:
            return finish(2, "error from run_advice.py: " + (text.strip().splitlines()[-1] if text.strip() else ""))
        reason = verify_round(live_dir, out, r, refused, ai_live.read_pending(live_dir).keys(), choices, events)
        reason = reason or check_shares(live_dir, choices) or check_expect(live_dir, expect, choices)
        if reason:
            return fail_check(reason)
    reason = check_expect(live_dir, expect, choices, final=True, run_dir=Path(a.runs_dir) / a.name)
    if reason:
        return fail_check(reason)
    return finish(0, "finished after %d rounds. Nothing is missing. Results: %s (not shown here)" % (
        n, Path(a.runs_dir) / a.name / "scores.json"))


def wait_for_reset(a, choices, probe_s, max_wait_s, S, sleep=time.sleep):
    """Wait after a usage-limit stop: probe now and then every probe_s seconds until a probe answers. Returns
    True when it did, False when the total waiting (S['waited_seconds'], all waits of this call) would pass
    max_wait_s. Each wait is logged with its start and end in live/private/terminal_waits.jsonl."""
    start = time.time()
    stamp = lambda x: time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(x))  # noqa: E731
    probes = 0
    print("  waiting for the usage limit to lift; one tiny call every %g minutes, at most %g hours in all"
          % (probe_s / 60.0, max_wait_s / 3600.0))
    ok = False
    while True:
        left = max_wait_s - S["waited_seconds"] - (time.time() - start)
        if left <= 0:
            break
        sleep(min(probe_s, left))
        probes += 1
        if answer_calls.probe(a.claude_bin, choices):
            ok = True
            break
    end = time.time()
    S["waited_seconds"] += end - start
    rec = {"wait_start": stamp(start), "wait_end": stamp(end), "seconds": round(end - start, 1), "probes": probes,
           "ended_by": "answered" if ok else "cap"}
    S["waits"].append(rec)
    path = ai_live.private_dir(Path(a.live_dir)) / "terminal_waits.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(str(path), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, sort_keys=True) + "\n")
    print("  wait %s to %s: %s after %d probes" % (rec["wait_start"], rec["wait_end"],
                                                   "the limit lifted" if ok else "cap reached", probes))
    return ok


def _import(RA, sel, out):
    if Path(out).exists():
        quiet(RA.main, ["import", str(out)] + sel)


if __name__ == "__main__":
    sys.exit(main())
