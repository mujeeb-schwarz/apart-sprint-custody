"""Runs every group B idea (as the fault definition ideas_compare.py builds) the way tools/run_complete_list.py runs the complete
list: AI parts off, stand-in texts, 3 cases drawn by lot per fault (fixed seed), the clean twin of each case, under A, A+ and B, in a
temporary run folder; then the frozen scorer. No model is called. Run from the artefact root.
"""
import copy, json, random, shutil, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
sys.path.insert(0, str(ROOT))
from custody import assemble, bench, datasets, planting, score, store, units, visits, watch, faults

# --- reuse ideas_compare.classify (its main() is not run); record which definition each idea uses
src = (HERE / "ideas_compare.py").read_text().replace("\nmain()\n", "\n")
ns = {"__file__": str(HERE / "ideas_compare.py")}
exec(compile(src, "ideas_compare.py", "exec"), ns)
last = {}
orig_add = ns["add_def"]
def rec_add(key, f):
    last["key"] = key
    return orig_add(key, f)
ns["add_def"] = rec_add
lines = [l for l in (HERE / "ideas_opened_output.txt").read_text().splitlines() if l.strip()]
ideas = []
for i, l in enumerate(lines, 1):
    last.clear()
    g, why = ns["classify"](i, l)
    if g == "B":
        p = [x.strip() for x in l.split("|")]
        ideas.append({"n": i, "rule": int(p[0].split()[1]), "words": "%s; %s; log: %s" % (p[1].split(": ", 1)[1], p[2].split(": ", 1)[1], p[3].split(": ", 1)[1]),
                      "key": last["key"], "why": why})
defs = ns["defs"]

FIELD = {"t": "handover.t", "from": "handover.from_place", "to": "handover.to_place", "kind": "handover.kind"}
OWN = {("transcriber", "transcript"): 1, ("note_writer", "note_draft"): 3}   # own-log position of the first matching send line

def record_fault(f):
    """The operation against the checker's record (version 3: under Checked a rule 3 violation is done to the record). Journal
    position = own-log position - 1 (clean_journal_output.txt). None when no such operation exists."""
    ops, out = f["ops"], []
    for op in ops:
        if op["op"] == "edit_record":
            o = dict(op); o["position"] = op["position"] - 1
            if "field" in o: o["field"] = FIELD[o["field"]]
            out.append(o)
        elif op["op"] == "false_log" and op.get("mode") is None:
            pos = OWN[(op["step"], op["kind"])] - 1
            if op["change"] is None: out.append({"op": "edit_record", "mode": "drop", "position": pos})
            else:
                (k, v), = op["change"].items()
                out.append({"op": "edit_record", "position": pos, "field": FIELD[k], "value": v})
        elif op["op"] == "false_log" and op.get("mode") == "add":
            o = {k: op[k] for k in ("step", "kind", "from", "to")}
            o.update({"op": "edit_record", "mode": "add", "position": op["position"] - 1}); out.append(o)
        else:
            return None
    if not out: return None
    r = copy.deepcopy(f); r["ops"] = out
    return r

def main():
    choices = watch.ai_parts_off(datasets.default_choices()); wiring = assemble.load_wiring(); rch = bench.run_choices(choices)
    cases = [v for v in visits.read_cases(visits.case_path(1, choices), 1) if v.split == "test"]
    by_id = {v.visit_id: v for v in cases}; ids = sorted(by_id)
    # idea 127 has its own definition (the added duty is skipped and its deletion claimed)
    d99 = {"op": "add", "path": "/plumbing/duties/-", "value": {"id": "d99", "kind": "note", "place": "record", "after_step": "record"}}
    defs["r3_note_duty_claim"] = {"fault_id": "IDEA.r3.note_duty_claimed", "kind": "wiring", "rule": 3,
        "says": "A duty that deletes the note at the record is added and skipped, and the log says the deletion happened.",
        "ops": [{"op": "skip_delete", "duty": "d99"}, {"op": "false_log", "mode": "claim_delete", "duty": "d99"}], "patch": [d99], "events": [], "needs": {}}
    for it in ideas:
        if it["n"] == 127: it["key"] = "r3_note_duty_claim"
    cfg, want = choices["bench_plan"]["complete_list"], choices["planting"]["complete_list_cases"]
    seed = choices["seeds"]["faults"]
    run_dir = Path(tempfile.mkdtemp(prefix="ideas_run_"))
    todo, plan, n, used, unit_of, not_run = [], {}, 0, set(), {}, []
    for it in ideas:
        f = copy.deepcopy(defs[it["key"]]); f["fault_id"] = "IDEA%03d" % it["n"]
        if it["rule"] == 3 and it["key"] != "r3_note_duty_claim":
            fr = record_fault(f)
            if fr: f["fault_record"] = fr
        try:
            faults.check_fault(f, wiring, choices)
        except Exception as e:
            not_run.append((it["n"], "%s: %s" % (type(e).__name__, e))); continue
        it["has_fault_record"] = "fault_record" in f
        lot = random.Random("%s:%s:%s" % (seed, cfg["sub_seed"], f["fault_id"]))
        it["units"] = []
        for cid in lot.sample(ids, min(want, len(ids))):
            n += 1
            row = {"plant_id": cfg["plant_id"].format(n=n), "rule": it["rule"]}
            uid = units.unit_id(cid, row["plant_id"])
            todo.append(units.make_unit(by_id[cid], uid, "complete_list", row)); plan[uid] = f; used.add(cid)
            it["units"].append(uid); unit_of[uid] = it["n"]
    for cid in sorted(used):
        todo.append(by_id[cid]); plan[cid] = None
    conds = choices["conditions"]["order"]
    bench.run_all(todo, conds, plan, dict(assemble.make_parts(wiring, rch)), wiring, choices, run_dir)
    counts = visits.case_counts(todo); counts.update({"experiment": 1, "ai_parts": "off", "faults_planned": n, "complete_list": True})
    store.write_manifest(run_dir, "ideas_run", choices["seeds"], conds, counts, assemble.manifest_fingerprints(choices, ROOT / "data" / "raw"), ai="canned")
    scores = score.score_run(run_dir, wiring, choices)
    st = store.read_store(run_dir)
    sig = {}
    for s in st["signals"]: sig.setdefault(s["run_id"], []).append(s)
    names = choices["scoring"]["method_names"]
    out = []
    for it in ideas:
        if "units" not in it: continue
        row = {k: it[k] for k in ("n", "rule", "words", "key", "has_fault_record", "units")}
        row["outcomes"] = {}; row["other_rules"] = {}
        for a in scores["attempts"]:
            if a["visit_id"] in it["units"] and a["rule"] == it["rule"]:
                row["outcomes"].setdefault(names[a["condition"]], []).append(a["outcome"])
        for uid in it["units"]:
            twin = units.case_of(uid)
            for c in conds:
                got = {s["rule"] for s in sig.get("%s.%s.r0" % (uid, c), [])}
                base = {s["rule"] for s in sig.get("%s.%s.r0" % (twin, c), [])}
                extra = sorted(got - base - {it["rule"]})
                if extra: row["other_rules"].setdefault(names[c], []).append([uid, extra])
        out.append(row)
    json.dump({"ideas": out, "not_run": not_run, "units": n, "twins": len(used)}, open(HERE / "ideas_run_rows.json", "w"), indent=1, default=str)
    json.dump(scores["attempts"], open(HERE / "ideas_run_attempts.json", "w"), indent=1, default=str)
    print("ideas run: %d, units %d, twins %d, not run %s" % (len(out), n, len(used), not_run))
    shutil.rmtree(str(run_dir), ignore_errors=True)

main()
