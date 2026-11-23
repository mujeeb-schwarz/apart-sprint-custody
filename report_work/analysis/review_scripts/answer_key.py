"""Frozen vs second-pass answer key on clean texts, rules 4 and 6 (reviewer's own code)."""
import json, collections, sys
from pathlib import Path
RUNS = Path(__file__).resolve().parents[3] / "runs"
R = lambda p: [json.loads(l) for l in open(p) if l.strip()]
out = {}
for name in ("night_e2", "night_e2_second_pass"):
    c = collections.Counter(); allc = collections.Counter()
    for j in R(RUNS / name / "judge.jsonl"):
        allc[(j["rule"], j["verdict"])] += 1
        if "+" not in j["visit_id"]:
            c[(j["rule"], j["verdict"])] += 1
    out[name] = {"clean_texts": {"%s|%s" % k: n for k, n in sorted(c.items())},
                 "all_texts": {"%s|%s" % k: n for k, n in sorted(allc.items())}}
# clean cases with at least one broken text, per rule, per key
for name in ("night_e2", "night_e2_second_pass"):
    cases = collections.defaultdict(set); allcases = collections.defaultdict(set)
    for j in R(RUNS / name / "judge.jsonl"):
        if "+" not in j["visit_id"]:
            allcases[j["rule"]].add(j["visit_id"])
            if j["verdict"] == "broken":
                cases[j["rule"]].add(j["visit_id"])
    out[name]["clean_cases_with_a_broken_text"] = {r: len(cases[r]) for r in (4, 5, 6)}
    out[name]["clean_cases"] = {r: len(allcases[r]) for r in (4, 5, 6)}
json.dump(out, sys.stdout, indent=1)
