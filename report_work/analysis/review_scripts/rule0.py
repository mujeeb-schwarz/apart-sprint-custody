"""Monitor's 'reads like an instruction to an AI' (rule 0) warnings on clean cases, both experiments (reviewer's own code)."""
import json, sys
from pathlib import Path
RUNS = Path(__file__).resolve().parents[3] / "runs"
out = {}
for name in ("night_e1", "night_e2_second_pass"):
    ids = set(); clean = set()
    for l in open(RUNS / name / "results.jsonl"):
        r = json.loads(l)
        if "+" not in r["visit_id"]:
            clean.add(r["visit_id"])
    for l in open(RUNS / name / "signals.jsonl"):
        s = json.loads(l)
        vid, cond = s["run_id"].split(".")[:2]
        if s["rule"] == 0 and cond == "A+" and vid in clean:
            ids.add(vid)
    out[name] = {"clean": len(clean), "monitored_rule0_cases": len(ids)}
json.dump(out, sys.stdout)
