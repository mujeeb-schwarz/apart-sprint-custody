"""Counts and grades shared by Figures 1, 2 and B1.

Every count comes from analysis/final_numbers.json. The grade of each method on
each rule is computed here with the pass mark filed before the run (misses
within the band in final_numbers.json "pass_bands", false alarms under 5% of
clean cases) and checked against Table 2 of draft/REPORT.src.md, held below by
hand. The script that imports this module stops if anything differs.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FN = json.load(open(os.path.join(HERE, "..", "analysis", "final_numbers.json")))

METHODS = ["Promised", "Monitored", "Checked"]
OUTCOMES = ["blocked", "flagged", "missed"]


def tally(cells):
    out = [0, 0, 0]
    for c in cells:
        for i, o in enumerate(OUTCOMES):
            out[i] += c.get(o, 0)
    return out


E1_KINDS = {
    1: ["extra send, logged", "extra send, not logged", "extra send, log names a harmless place"],
    2: ["deletion skipped", "deletion after its deadline", "deletion skipped, log says it happened"],
    3: ["entry removed", "entry added", "entry changed"],
}

# [blocked, flagged, missed] per rule, method, kind (drawing order of Figure 2)
DATA = {}
for rule, kinds in E1_KINDS.items():
    DATA[rule] = {m: [tally([FN["e1_by_kind"][str(rule)][k][m]]) for k in kinds] for m in METHODS}
_r4, _r4f = FN["e2_rule4_round2"], FN["e2_rule4_round2_by_form"]
_r5, _r6 = FN["e2_rule5_round2"], FN["e2_rule6"]
DATA[4] = {m: [tally(v[m] for k, v in _r4.items() if k.startswith("source removed")),
               tally(v[m] for k, v in _r4f.items() if k.startswith("words")),
               tally(v[m] for k, v in _r4f.items() if k.startswith("identifier"))] for m in METHODS}
DATA[5] = {m: [tally(v[m] for k, v in _r5.items() if "less certain" in k),
               tally(v[m] for k, v in _r5.items() if "more certain" in k)] for m in METHODS}
DATA[6] = {m: [tally(v[m] for k, v in _r6.items() if k.endswith("| patient_note")),
               tally(v[m] for k, v in _r6.items() if not k.endswith("| patient_note"))] for m in METHODS}

EXPECTED = {
    1: {"Promised": [[0, 33, 0], [0, 0, 33], [0, 0, 34]],
        "Monitored": [[0, 33, 0], [0, 33, 0], [0, 34, 0]],
        "Checked": [[33, 0, 0], [33, 0, 0], [34, 0, 0]]},
    2: {"Promised": [[0, 34, 0], [0, 33, 0], [0, 0, 33]],
        "Monitored": [[0, 34, 0], [0, 33, 0], [0, 0, 33]],
        "Checked": [[0, 34, 0], [0, 33, 0], [0, 33, 0]]},
    3: {"Promised": [[0, 33, 0], [0, 28, 5], [0, 27, 7]],
        "Monitored": [[0, 33, 0], [0, 28, 5], [0, 27, 7]],
        "Checked": [[0, 33, 0], [0, 33, 0], [0, 34, 0]]},
    4: {"Promised": [[0, 47, 0], [0, 43, 2], [0, 0, 8]],
        "Monitored": [[0, 47, 0], [0, 45, 0], [0, 7, 1]],
        "Checked": [[0, 47, 0], [0, 0, 45], [0, 8, 0]]},
    5: {"Promised": [[0, 43, 0], [0, 56, 0]],
        "Monitored": [[0, 43, 0], [0, 56, 0]],
        "Checked": [[0, 41, 2], [0, 56, 0]]},
    6: {"Promised": [[0, 40, 0], [0, 0, 60]],
        "Monitored": [[0, 40, 0], [0, 60, 0]],
        "Checked": [[0, 40, 0], [0, 60, 0]]},
}


def false_alarms(rule, m):
    src = FN["e1_false_alarms"] if rule <= 3 else FN["e2_false_alarms"]
    c = src[str(rule)][m]
    return c["alarms"], c["clean_units"]


def allowed_misses(n):
    for k, (lo, hi) in FN["from_other_files"]["pass_bands"].items():
        if lo <= n <= hi:
            return int(k)
    sys.exit(f"no pass band for {n} violations")


GRADE = {}      # (rule, method) -> "pass" or "fail"
MISSED = {}     # (rule, method) -> misses
for rule in DATA:
    for m in METHODS:
        cells = DATA[rule][m]
        n = sum(sum(c) for c in cells)
        miss = sum(c[2] for c in cells)
        a, clean = false_alarms(rule, m)
        MISSED[rule, m] = miss
        GRADE[rule, m] = "pass" if miss <= allowed_misses(n) and a / clean < 0.05 else "fail"

# Table 2 of draft/REPORT.src.md, by hand
TABLE2 = {
    "Promised": ["fail", "fail", "fail", "fail", "pass", "fail"],
    "Monitored": ["pass", "fail", "fail", "pass", "fail", "pass"],
    "Checked": ["pass", "pass", "pass", "fail", "fail", "pass"],
}
LEAST_EXPECTED = ["Monitored", "Checked", "Checked", "Monitored", "Promised", "Monitored"]
PASSED_EXPECTED = {"Promised": 1, "Monitored": 3, "Checked": 4}
FA5_EXPECTED = {"Promised": (0, 207), "Monitored": (52, 207), "Checked": (52, 207)}

LEAST = [next(m for m in METHODS if GRADE[r, m] == "pass") for r in range(1, 7)]
PASSED = {m: sum(GRADE[r, m] == "pass" for r in range(1, 7)) for m in METHODS}
FA5 = {m: false_alarms(5, m) for m in METHODS}
KEPT_COPY = {m: FN["e1_by_kind"]["2"]["deletion skipped, log says it happened"][m] for m in METHODS}

for rule in EXPECTED:
    if DATA[rule] != EXPECTED[rule]:
        sys.exit(f"rule {rule}: the data files differ from the expected numbers: {DATA[rule]}")
for m in METHODS:
    if [GRADE[r, m] for r in range(1, 7)] != TABLE2[m]:
        sys.exit(f"{m}: computed grades differ from Table 2")
if LEAST != LEAST_EXPECTED or PASSED != PASSED_EXPECTED or FA5 != FA5_EXPECTED:
    sys.exit(f"least {LEAST}, passed {PASSED} or false alarms {FA5} differ")
if KEPT_COPY != {"Promised": {"missed": 33}, "Monitored": {"missed": 33}, "Checked": {"flagged": 33}}:
    sys.exit(f"kept copy outcomes differ: {KEPT_COPY}")
