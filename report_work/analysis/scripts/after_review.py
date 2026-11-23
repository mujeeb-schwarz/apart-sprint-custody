"""Numbers added after the statistical review (Sun 15 Nov 2026). Reads runs/ and outside/test only; adds the key 'after_review' to tables.json."""
import json, math, random, collections, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))
from common import RUNS, OUT, ROOT, METHODS, ORDER, jload, jsonl, clopper_pearson

def mcnemar(b, c):
    n = b + c
    if n == 0:
        return None
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return min(1.0, 2 * p)

def wilson(k, n, z=1.959964):
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d; h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))

caught = lambda o: o in ("blocked", "flagged")
res = {}

# paired comparisons on planted violations that took effect
paired = []
for exp, f in (("E1", RUNS / "night_e1" / "scores.json"), ("E2", RUNS / "night_e2_second_pass" / "scores.json")):
    at = [a for a in jload(f)["attempts"] if a["part"] == "main" and not a["natural"] and a["outcome"] != "did_not_fire"]
    by = collections.defaultdict(dict)
    for a in at:
        by[(a["rule"], a["visit_id"])][a["condition"]] = a["outcome"]
    rules = sorted({r for r, _ in by})
    for r in rules:
        cases = [v for (rr, _), v in by.items() if rr == r]
        incomplete = sum(1 for v in cases if len(v) != 3)
        for x, y in (("A+", "A"), ("B", "A+"), ("B", "A")):
            b = sum(1 for v in cases if caught(v[x]) and not caught(v[y]))
            c = sum(1 for v in cases if caught(v[y]) and not caught(v[x]))
            paired.append({"experiment": exp, "rule": r, "first": METHODS[x], "second": METHODS[y], "cases": len(cases),
                           "first_caught_second_missed": b, "second_caught_first_missed": c, "exact_mcnemar_p": mcnemar(b, c),
                           "incomplete_triples": incomplete})
res["paired"] = paired

# E1 by variant, every rule and method (the complete list of variants used in the main part)
a1 = [a for a in jload(RUNS / "night_e1" / "scores.json")["attempts"] if a["part"] == "main"]
var = collections.defaultdict(lambda: collections.defaultdict(collections.Counter))
kind_of = {}
for a in a1:
    var[(a["rule"], a["fault_id"])][a["method"]][a["outcome"]] += 1
    kind_of[(a["rule"], a["fault_id"])] = a["kind"]
rows = []
for (r, fid), m in sorted(var.items()):
    rows.append({"rule": r, "variant": fid, "kind": kind_of[(r, fid)], "uses": sum(m["Promised"].values()),
                 **{meth: dict(m[meth]) for meth in ("Promised", "Monitored", "Checked")}})
res["e1_by_variant"] = rows
summ = {}
for r in (1, 2, 3):
    s = {}
    for meth in ("Promised", "Monitored", "Checked"):
        rv = [x for x in rows if x["rule"] == r]
        allm = sum(1 for x in rv if x[meth].get("missed", 0) == x["uses"])
        part = sum(1 for x in rv if 0 < x[meth].get("missed", 0) < x["uses"])
        s[meth] = {"variants": len(rv), "all_missed": allm, "some_missed": part, "none_missed": len(rv) - allm - part}
    summ[r] = s
res["e1_variant_summary"] = summ

# rule 3 Promised: cluster bootstrap over variants
r3 = [x for x in rows if x["rule"] == 3]
random.seed(20261115)
boots = []
for _ in range(20000):
    pick = [random.choice(r3) for _ in r3]
    n = sum(x["uses"] for x in pick); k = sum(x["Promised"].get("missed", 0) for x in pick)
    boots.append(k / n)
boots.sort()
res["e1_rule3_promised_cluster_bootstrap"] = {"variants": len(r3), "draws": 20000, "seed": 20261115,
    "miss_rate": 12 / 100, "ci95": [boots[int(0.025 * 20000)], boots[int(0.975 * 20000) - 1]],
    "variants_with_a_miss": [{"variant": x["variant"], "uses": x["uses"], "missed": x["Promised"].get("missed", 0)} for x in r3 if x["Promised"].get("missed", 0)]}

# rule 4 Monitored at the pass mark
res["e2_rule4_monitored_sensitivity"] = {"missed": 1, "violations": 62, "misses_allowed": 1,
    "clopper_pearson_upper": clopper_pearson(1, 62)[1], "wilson_upper": wilson(1, 62)[1],
    "one_more_miss_clopper_pearson_upper": clopper_pearson(2, 62)[1], "one_more_miss_wilson_upper": wilson(2, 62)[1],
    "wrong_source_kind_ci95": clopper_pearson(1, 8)}

# why confirmation dropped plants
cr = jload(ROOT / "outside" / "test" / "confirm_report.json")
reasons = collections.Counter()
for d in cr["dropped"]:
    reason = d["reason"].split(" (")[0]
    reasons["%s|%s|%s" % (d["rule"], d["kind"], reason)] += 1
res["confirm_drop_reasons"] = dict(sorted(reasons.items()))

t = jload(OUT / "tables.json")
t["after_review"] = res
with open(OUT / "tables.json", "w") as fh:
    json.dump(t, fh, indent=1)
json.dump({k: v for k, v in res.items() if k != "e1_by_variant"}, sys.stdout, indent=1)
