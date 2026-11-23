"""Per-variant outcomes for AI-decided cells and overlap of rule-5 false alarms (reviewer's own code)."""
import json, collections, sys
from pathlib import Path
RUNS = Path(__file__).resolve().parents[3] / "runs"
out = {}
a1 = json.load(open(RUNS / "night_e1" / "scores.json"))["attempts"]
for rule in (3,):
    g = collections.defaultdict(collections.Counter)
    for a in a1:
        if a["part"] == "main" and a["rule"] == rule and a["condition"] == "A":
            g[a["fault_id"]][a["outcome"]] += 1
    out["e1_rule3_promised_by_variant"] = {k: dict(v) for k, v in sorted(g.items(), key=lambda kv: -kv[1]["missed"])}
# rule 1 Promised: missed per kind recomputed is constant per variant (deterministic program)
D = RUNS / "night_e2_second_pass"
R = lambda p: [json.loads(l) for l in open(p) if l.strip()]
s = json.load(open(D / "scores.json"))
nat = {a["visit_id"] for a in s["attempts"] if a["natural"] and a["rule"] == 5}
vis = {v["visit_id"]: v for v in R(D / "visits.jsonl")}
graded = {v for v in vis if "+" not in v and vis[v].get("expert_certainty")}
fa = collections.defaultdict(set)
for x in R(D / "signals.jsonl"):
    vid, cond = x["run_id"].split(".")[:2]
    if x["rule"] == 5 and vid in graded and vid not in nat and x["part"] == "program" and x["by"] in ("watcher", "gate"):
        fa[cond].add(vid)
out["rule5_fa_overlap_Monitored_Checked"] = len(fa["A+"] & fa["B"])
out["rule5_fa_sizes"] = {k: len(v) for k, v in fa.items()}
# rule 4 planted by kind x set x step
g = collections.Counter()
for a in s["attempts"]:
    if a["part"] == "main" and not a["natural"] and a["rule"] in (4, 6) and a["condition"] == "A+":
        st = "graded" if a["visit_id"].split("+")[0] in graded or vis.get(a["visit_id"], {}).get("expert_certainty") else "stored"
        g["%s|%s|%s" % (a["rule"], a["kind"], st)] += 1
out["e2_planted_rule4_6_by_kind_set"] = dict(sorted(g.items()))
json.dump(out, sys.stdout, indent=1)
