#!/usr/bin/env python3
"""The end-to-end run, for both experiments (Version 2): 16 cases of each list (8 practice, 8 test), the development
faults of the lane, four conditions, canned text, scored; then the seven checks of docs/FRAME.md section 12, each
passing only when it passes for Experiment 1 and for Experiment 2."""
import json
import os
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custody import assemble, bench, datasets, faults, receipt, score, store, visits  # noqa: E402
from custody.core import CustodyError, canon, claim_level, has_ai_mark, sources_named  # noqa: E402

RUN_DIRS = {1: ROOT / "runs" / "e2e_e1", 2: ROOT / "runs" / "e2e_e2"}
CONDS = ["A", "A+", "B", "C"]
METHODS = ["A", "A+", "B"]   # check 3 reads the three methods; C stays in the run for check 4
E2E_CLEAN = 4                # clean practice cases of each experiment
TWIN_OF = ("F12", "F6")      # the faults whose case gets a clean twin (a flag that names no handover needs one)


def pick(vs):
    """The first 8 practice cases and the first 8 test cases of one list."""
    return [v for v in vs if v.split == "tune"][:8] + [v for v in vs if v.split == "test"][:8]


def build_and_run(exp, run_dir=None):
    """Steps of D: done. One experiment: 16 cases of its list. Returns (cases, plan, unplaced, scores)."""
    run_dir = run_dir or RUN_DIRS[exp]
    choices = datasets.default_choices()
    choices["conditions"]["order"] = list(CONDS)  # the check keeps the code path of C alive, although the default method has three
    wiring = assemble.load_wiring()
    rchoices = bench.run_choices(choices)  # once
    cases = visits.read_cases(visits.case_path(exp, choices), exp)
    fl = faults.load_faults(choices, ROOT)
    # version 3: practice cases only (no fault is forced onto a test case): four clean cases and each development fault of
    # the lane on a case of its own; the cases of F12 and F6 get a clean twin, so that a flag that names only a rule can be compared
    vs, plan, _clean, unplaced = faults.plan_trial(cases, fl, E2E_CLEAN, choices, wiring)
    for vid in [v for v, f in plan.items() if f and f["fault_id"] in TWIN_OF]:
        case = next(v for v in vs if v.visit_id == vid)
        twin = replace(case, visit_id=vid + "+twin")
        vs = [replace(v, clean_of=twin.visit_id) if v.visit_id == vid else v for v in vs] + [twin]
        plan[twin.visit_id] = None
    if Path(str(run_dir)).exists():
        shutil.rmtree(str(run_dir))
    parts = assemble.make_parts(wiring, rchoices)
    bench.run_all(vs, CONDS, plan, parts, wiring, choices, run_dir)
    counts = visits.case_counts(vs)
    counts["experiment"] = exp
    store.write_manifest(run_dir, "e2e_e%d" % exp, choices["seeds"], CONDS, counts,
                         assemble.manifest_fingerprints(choices, ROOT / "data" / "raw"))
    stand_in_judge(run_dir, choices)
    scores = score.score_run(run_dir, wiring, choices)
    return vs, plan, unplaced, scores


def stand_in_judge(run_dir, choices):
    """A program stands in for the judge (no AI): for each advice text, the readers' verdict on rules 4 and 6 and their level
    for rule 5, 'kept' and the entry's level where a reader cannot tell. Without it the texts of rules 4 to 6 stay unjudged."""
    rows = []
    visits_by = {v["visit_id"]: v for v in store.read_jsonl(Path(str(run_dir)) / "visits.jsonl")}
    seen = set()
    for t in store.read_jsonl(Path(str(run_dir)) / "texts.jsonl"):
        it = t["item"]
        if it["kind"] not in choices["rules"]["advice_kinds"] or it["item_id"] in seen:
            continue
        seen.add(it["item_id"])
        v = visits_by[it["visit_id"]]
        lv = claim_level(it["text"], choices)
        for rule in (4, 5, 6):
            verdict = score.reader_verdict(rule, it["text"], v, choices)
            if verdict is None:  # the program cannot tell: the stand-in judge says what a plain reader would
                verdict = "broken" if (rule == 4 and not sources_named(it["text"], choices)) or \
                    (rule == 6 and not has_ai_mark(it["text"], choices)) else "kept"
            rows.append({"visit_id": it["visit_id"], "item_id": it["item_id"], "rule": rule, "verdict": verdict,
                         "level": lv if lv not in (None, "undecided") else "none"})
    store.write_jsonl(Path(str(run_dir)) / "judge.jsonl", rows)


def fingerprint_tree(run_dir):
    out = {}
    for p in sorted(Path(str(run_dir)).rglob("*")):
        if p.is_file() and p.name != "timing.jsonl":
            out[str(p.relative_to(run_dir))] = assemble.file_fingerprint(p)
    return out


def norm(obj):
    s = canon(obj) if not isinstance(obj, str) else obj
    return re.sub(r"\.(A\+|A|B|C)\.r", ".X.r", s)


def strip(rec):
    return {k: v for k, v in rec.items() if k not in ("fp", "prev_fp", "receipt")}


def check7():
    bad = []
    words = ["hidden/", "truth.jsonl", "plan.jsonl", "custody.world", "custody.faults", "expert_answer",
             "'faults'", '"faults"', "'hidden'", '"hidden"']
    # the separation is by convention plus this static check, not enforced by Python: no way in to a closure,
    # a module table or an attribute chain
    reach = ["__closure__", "__globals__", "__self__", "__dict__", "__code__", "getattr(", "sys.modules"]
    files = [ROOT / "custody" / n for n in
             ("steps.py", "ai.py", "engine.py", "labels.py", "rules.py", "gate.py", "watch.py",
              "journal.py", "witness.py", "receipt.py")] + [ROOT / "tools" / "check_receipt.py"]
    for p in files:
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for w in words + reach:
            if w in text:
                bad.append("%s holds %s" % (p.name, w))
        if p.name in ("labels.py", "rules.py", "gate.py", "watch.py") and ("'plumbing'" in text or '"plumbing"' in text or "plumbing" in text):
            bad.append("%s holds plumbing" % p.name)
    return bad


def check_experiment(exp, expect):
    """Checks 2 to 5 for one experiment, on its run folder. Returns {check number: (ok, note)}."""
    run_dir = RUN_DIRS[exp]
    out = {}
    lane_faults = None
    vs, plan, unplaced, scores = BUILT[exp]
    st = store.read_store(run_dir)
    sig_by_run = defaultdict(list)
    for s in st["signals"]:
        sig_by_run[s["run_id"]].append(s)
    # 2 clean runs: no signal, and the lane's final text produced
    clean = {vid for vid, f in plan.items() if f is None}
    final_kind = {1: "note", 2: "patient_note"}[exp]
    bad2 = []
    for r in st["results"]:
        if r["visit_id"] in clean:
            if sig_by_run[r["run_id"]] or not r["produced"][final_kind] or r["experiment"] != exp:
                bad2.append(r["run_id"])
    placed = sum(1 for f in plan.values() if f)
    out[2] = (not bad2 and len(clean) == len(vs) - placed and len(clean) > 0,
              "e%d: clean cases %d of %d; bad: %s" % (exp, len(clean), len(vs), bad2))
    # 3 outcomes: every development fault of the lane is placed and has the expected outcome
    fid_rule = {f["fault_id"]: f["rule"] for f in plan.values() if f}
    got = defaultdict(dict)
    for a in scores["attempts"]:
        if a["fault_id"] in expect and a["rule"] == fid_rule.get(a["fault_id"]):
            got[a["fault_id"]][a["condition"]] = a["outcome"]
    mism = []
    wiring = assemble.load_wiring()
    lane = {1: "words", 2: "advice"}[exp]
    for fid, exp_row in expect.items():
        fl = [f for f in datasets.default_choices()["faults"]["development"] if f["fault_id"] == fid][0]
        fl_lane = faults.fault_lane(fl, wiring)
        if fl_lane not in (None, lane):
            continue
        for c in METHODS:
            g = got.get(fid, {}).get(c, "missing")
            if g != exp_row[c]:
                mism.append("e%d %s %s: got %s, expected %s" % (exp, fid, c, g, exp_row[c]))
    out[3] = (not mism, "; ".join(mism))
    # 4 B and C agree
    diffs = []
    for vid in sorted(plan):
        b, c = "%s.B.r0" % vid, "%s.C.r0" % vid
        sb = norm([{k: v for k, v in s_.items()} for s_ in sig_by_run[b]])
        sc = norm([{k: v for k, v in s_.items()} for s_ in sig_by_run[c]])
        jb = norm([strip(x) for x in st["journal"].get(b, [])])
        jc = norm([strip(x) for x in st["journal"].get(c, [])])
        if sb != sc:
            diffs.append(vid + " signals")
        if jb != jc:
            diffs.append(vid + " records")
    for fid in got:
        if "C" in got[fid] and got[fid].get("B") != got[fid].get("C"):  # the scorer reads three methods: C has no outcome
            diffs.append(fid + " outcome")
    out[4] = (not diffs, "; ".join("e%d %s" % (exp, d) for d in diffs))
    # 5 receipts
    choices = datasets.default_choices()
    key = bench._witness_key(choices)
    wlog = st["witness"]
    f12 = {vid for vid, f in plan.items() if f and f["fault_id"] == "F12"}
    bad5 = []
    for vid in sorted(plan):
        for c in ("B", "C"):
            rid = "%s.%s.r0" % (vid, c)
            res = receipt.check_receipt(st["receipts"][rid], st["journal"][rid], wlog, key)
            if vid in f12:
                if res["ok"]:
                    bad5.append(rid + " should fail")
            else:
                if not res["ok"]:
                    bad5.append(rid + " fails: %s" % res["problems"][:1])
                else:
                    jr = [dict(x) for x in st["journal"][rid]]
                    if jr:
                        jr[0]["t"] = jr[0]["t"] + 1
                        if receipt.check_receipt(st["receipts"][rid], jr, wlog, key)["ok"]:
                            bad5.append(rid + " passes after an edit")
                    if len(jr) >= 3:
                        gone = [dict(x) for x in jr[:1] + jr[2:]]
                        if receipt.check_receipt(st["receipts"][rid], gone, wlog, key)["ok"]:
                            bad5.append(rid + " passes after record 1 is removed")
                        swapped = [dict(x) for x in jr[:1] + [jr[2], jr[1]] + jr[3:]]
                        if receipt.check_receipt(st["receipts"][rid], swapped, wlog, key)["ok"]:
                            bad5.append(rid + " passes after records 1 and 2 are swapped")
                    # the tail cut off, receipt rebuilt from the shortened records (the receipt file's own
                    # records carry the witness receipts)
                    held = [dict(x) for x in st["receipts"][rid]["records"]]
                    for cut in (1, 2):
                        if len(held) > cut:
                            short = held[:-cut]
                            rebuilt = receipt.build_receipt(rid, c, short, st["receipts"][rid]["proof"],
                                                            assemble.load_wiring(), bench.run_choices(choices))
                            if receipt.check_receipt(rebuilt, [dict(x) for x in jr[:-cut]], wlog, key)["ok"]:
                                bad5.append(rid + " passes with its last %d record(s) cut off" % cut)
    out[5] = (not bad5, "; ".join(bad5))
    return out, [r["run_id"] for r in st["results"] if r["crashed"]], unplaced


BUILT = {}


def run_checks():
    results = []

    def rec(n, ok, note=""):
        results.append({"check": n, "status": "pass" if ok else ("not reached" if ok is None else "fail"), "note": note})

    choices = datasets.default_choices()
    expect = choices["faults"]["expect"]
    try:
        for exp in (1, 2):
            BUILT[exp] = build_and_run(exp)
    except Exception as exc:  # noqa
        rec(1, False, "crash: %s: %s" % (type(exc).__name__, exc))
        for n in range(2, 8):
            rec(n, None)
        return results
    per = {exp: check_experiment(exp, expect) for exp in (1, 2)}
    crashed = [x for exp in per for x in per[exp][1]]
    unplaced = {exp: per[exp][2] for exp in per}
    t = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"], cwd=str(ROOT),
                       capture_output=True, text=True)
    rec(1, not crashed and t.returncode == 0,
        "crashed runs: %s; unplaced: %s; tests exit %d %s" % (crashed, unplaced, t.returncode, t.stderr.strip().splitlines()[-1:]))
    for n in (2, 3, 4, 5):
        rec(n, all(per[exp][0][n][0] for exp in per), "; ".join(x for x in (per[exp][0][n][1] for exp in per) if x))
    # 6 repeat
    first = {exp: fingerprint_tree(RUN_DIRS[exp]) for exp in (1, 2)}
    env = dict(os.environ, PYTHONHASHSEED="12345")
    r = subprocess.run([sys.executable, str(ROOT / "tools" / "run_e2e.py"), "--repeat"], cwd=str(ROOT), env=env,
                       capture_output=True, text=True)
    d6 = []
    for exp in (1, 2):
        second = fingerprint_tree(RUN_DIRS[exp])
        d6 += ["e%d:%s" % (exp, k) for k in sorted(set(first[exp]) | set(second)) if first[exp].get(k) != second.get(k)]
    rec(6, r.returncode == 0 and not d6, "repeat exit %d; differing files: %s %s" % (r.returncode, d6[:5], r.stderr.strip()[-200:]))
    # 7
    b7 = check7()
    rec(7, not b7, "; ".join(b7))
    return results


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    try:
        if "--repeat" in argv:
            for exp in (1, 2):
                build_and_run(exp)
            return 0
        results = run_checks()
    except CustodyError as e:
        print("error: %s" % e)
        return 2
    for r in results:
        print("check %d: %s %s" % (r["check"], r["status"], r["note"]))
    ok = all(r["status"] == "pass" for r in results)
    print("end-to-end: %s" % ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
