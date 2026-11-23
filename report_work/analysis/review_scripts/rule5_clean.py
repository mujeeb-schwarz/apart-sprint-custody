"""Rule 5 false alarms on clean graded cases, recomputed from signals (reviewer's own code)."""
import json, collections, sys
from pathlib import Path
D = Path(__file__).resolve().parents[3] / "runs" / "night_e2_second_pass"
R = lambda p: [json.loads(l) for l in open(p) if l.strip()]
vis = {v["visit_id"]: v for v in R(D / "visits.jsonl")}
s = json.load(open(D / "scores.json"))
clean = [v for v in vis if "+" not in v]
graded = {v for v in clean if vis[v].get("expert_certainty")}
nat = {a["visit_id"] for a in s["attempts"] if a["natural"] and a["rule"] == 5}
COUNTED = {"A": {"review"}, "A+": {"review", "watcher"}, "B": {"gate", "ledger"}}
cases = collections.defaultdict(set); parts = collections.defaultdict(lambda: collections.defaultdict(set))
for x in R(D / "signals.jsonl"):
    vid, cond = x["run_id"].split(".")[0], x["run_id"].split(".")[1]
    if "+" in vid or x["rule"] != 5 or x["by"] not in COUNTED[cond]:
        continue
    cases[(cond, vid in graded, vid in nat)].add(vid)
    parts[cond][vid].add(x["part"])
out = {"graded_clean": len(graded), "natural_rule5": len(nat), "denominator": len(graded - nat)}
for k, v in sorted(cases.items()):
    out["%s graded=%s natural=%s" % k] = len(v)
for cond in COUNTED:
    fa = [v for v in parts[cond] if v in graded and v not in nat]
    out["FA_" + cond] = len(fa)
    out["FA_parts_" + cond] = dict(collections.Counter("both" if len(parts[cond][v]) > 1 else next(iter(parts[cond][v])) for v in fa))
json.dump(out, sys.stdout, indent=1)
