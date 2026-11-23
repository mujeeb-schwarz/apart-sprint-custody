"""Piece 1, parts (a) and (b): every connection mistake (wiring fault) the bench knows, run through
(a) the bench's own search (custody/prove.py) and (b) Z3 (the script model/gen_z3.py writes, for the patched wiring).
The wiring file is never changed: patches are applied to deep copies in memory.
Run from the artefact root:  PYTHONDONTWRITEBYTECODE=1 python3 night/proof/proof_list.py
"""
import copy, json, os, subprocess, sys, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "model"))
from custody import faults as F
from custody.prove import build_program, cross_check, load_choices, load_wiring
import gen_z3

def collect(choices):
    out = []
    for f in choices["faults"]["development"]:
        if f["kind"] == "wiring": out.append(("config/design_choices.json", f, False))
    for p in ("faults/practice/practice_faults.json", "faults/practice/practice_advice_faults.json"):
        d = json.load(open(ROOT / p))
        for f in d["faults"]:
            if f["kind"] == "wiring": out.append((p, f, False))
        for f in d.get("clean_cases", []):
            if f["kind"] == "wiring": out.append((p + " (clean_cases)", f, True))
    return out

def z3_run(wiring, choices, tmp):
    text = gen_z3.generate(wiring, choices)
    # One repair of the generated text (model/gen_z3.py itself is not edited): the template reads st.arr[key] for a place
    # that a delete created without an arrival tick (a delete aimed at a place no move fills, as when a patch sends the
    # retry copy elsewhere). A place that never held a copy has no arrival; the default 0 is never used because its
    # presence term is False.
    text = text.replace("st.t > st.arr[key] + hold", "st.t > st.arr.get(key, IntVal(0)) + hold")
    p = Path(tmp) / "z3_script.py"; p.write_text(text)
    r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, timeout=300)
    return (r.stdout + r.stderr).strip()

def main():
    choices = load_choices(); base = load_wiring()
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        base_own = cross_check(base, choices)
        base_z3 = z3_run(base, choices, tmp)
        print("== clean wiring: own search ok=%s states=%s | Z3: %s" % (base_own["ok"], base_own["states"], base_z3))
        for src, f, control in collect(choices):
            row = {"id": f["fault_id"], "source": src, "control": control, "rule": f["rule"], "says": f["says"],
                   "patch": f.get("patch"), "events": f.get("events"), "lane": F.fault_lane(f, base)}
            try:
                w = F.apply_patch(base, f.get("patch") or [])
                rep = cross_check(w, choices)
                ce = rep["counterexample"]
                row["own"] = {"found": not rep["ok"], "violated": rep["violated"], "states": rep["states"],
                              "property": ce and ce["property"], "why": ce and ce["why"],
                              "events_in_path": [l for l in (ce["trace"] if ce else []) if l.startswith("-- rare event")],
                              "trace": ce and ce["trace"]}
                row["z3"] = z3_run(w, choices, tmp)
            except Exception as e:
                row["error"] = "%s: %s" % (type(e).__name__, e)
            rows.append(row)
            print("== %s (%s) rule %s\n   says: %s\n   patch: %s events: %s" % (row["id"], src, f["rule"], f["says"], f.get("patch"), f.get("events")))
            if "error" in row: print("   ERROR", row["error"]); continue
            o = row["own"]
            print("   own search: found=%s property=%s violated=%s states=%s" % (o["found"], o["property"], o["violated"], o["states"]))
            print("   own why: %s | rare events on path: %s" % (o["why"], o["events_in_path"]))
            print("   Z3: %s" % row["z3"].replace("\n", "\n       "))
    json.dump({"clean": {"own_ok": base_own["ok"], "z3": base_z3}, "rows": rows}, open(ROOT / "night/proof/proof_rows.json", "w"), indent=1)

main()
