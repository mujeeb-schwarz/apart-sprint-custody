"""Piece 1, part 3: each connection mistake replayed as a real case (no AI: stand-in texts) under A, A+ and B
(Promised, Monitored, Checked), on ONE practice case (split "tune"), in a temporary run folder. Reads the scorer's outcome.
Run from the artefact root:  PYTHONDONTWRITEBYTECODE=1 python3 night/proof/replay.py
"""
import json, sys, tempfile, shutil, importlib.util
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "tools"))
from custody import assemble, bench, datasets, faults, score, store, visits
import run_e2e  # only its stand_in_judge is used
sys.path.insert(0, str(Path(__file__).parent))
spec = importlib.util.spec_from_file_location("proof_list", str(Path(__file__).parent / "proof_list.py"))
src = open(spec.origin).read().replace("\nmain()\n", "\n")   # reuse collect() without running it
ns = {"__file__": spec.origin}; exec(compile(src, spec.origin, "exec"), ns)
METHODS = ["A", "A+", "B"]
NAMES = {"A": "Promised", "A+": "Monitored", "B": "Checked"}

def main():
    choices = datasets.default_choices()
    choices["conditions"]["order"] = list(METHODS)
    wiring = assemble.load_wiring()
    rch = bench.run_choices(choices)
    out = []
    for src_, f, control in ns["collect"](choices):
        lane = faults.fault_lane(f, wiring)
        exp = 2 if lane == "advice" else 1
        cases = visits.read_cases(visits.case_path(exp, choices), exp)
        needs = faults._needs_of(f); needs.pop("split", None)
        case = next(v for v in cases if v.split == "tune" and faults._meets(v, needs))
        assert case.split == "tune"
        run_dir = Path(tempfile.mkdtemp())
        try:
            parts = assemble.make_parts(wiring, rch)
            res = bench.run_all([case], METHODS, {case.visit_id: f}, parts, wiring, choices, run_dir)
            store.write_manifest(run_dir, "night_proof", choices["seeds"], METHODS,
                                 dict(visits.case_counts([case]), experiment=exp),
                                 assemble.manifest_fingerprints(choices, ROOT / "data" / "raw"))
            run_e2e.stand_in_judge(run_dir, choices)
            sc = score.score_run(run_dir, wiring, choices)
            att = [a for a in sc["attempts"] if a["fault_id"] == f["fault_id"]]
            row = {"id": f["fault_id"], "control": control, "experiment": exp, "case": case.visit_id, "split": case.split,
                   "crashed": [r.crashed for r in res],
                   "attempts": [{k: a.get(k) for k in ("condition", "rule", "outcome", "break_t", "signal_t", "flag_part", "part", "kind", "natural") if k in a} for a in att],
                   "keys": sorted(att[0].keys()) if att else None,
                   "outcome": {a["condition"]: a["outcome"] for a in att if a["rule"] == f["rule"]}}
            if control:
                row["signals"] = [(s["run_id"], s.get("rule")) for s in store.read_store(run_dir)["signals"]]
        finally:
            shutil.rmtree(str(run_dir), ignore_errors=True)
        out.append(row)
        print(f["fault_id"], "exp", exp, case.visit_id, "->", {NAMES[k]: v for k, v in row["outcome"].items()}, "| attempts rows:", len(att), "| crashed:", row["crashed"])
        if control: print("   control signals:", row["signals"])
    json.dump(out, open(ROOT / "night/proof/replay_rows.json", "w"), indent=1, default=str)

main()
