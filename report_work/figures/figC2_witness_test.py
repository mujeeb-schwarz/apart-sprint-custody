"""Figure C2: the witness test. For each of four forgers, how many of the 100 edited records each
safeguard reported (units_with_a_problem_of_part in ablation/out/results.json, table -> forger ->
chain_with_witness; the thorough operator from ablation/out/results_forger4.json, flagged 0 by the
full check, hence no part reports a problem).
The script stops if a count differs from the recount: careless 100/33/100, careful 0/100/100,
operator 0/0/100, thorough operator 0/0/0.
"""
import json
import os
import sys

import style
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt

style.apply()
ABL = os.path.join(style.HERE, "..", "..", "ablation", "out")
r1 = json.load(open(os.path.join(ABL, "results.json")))
r4 = json.load(open(os.path.join(ABL, "results_forger4.json")))
PARTS = ["chain", "witness", "receipt"]
FORGERS = ["careless", "careful", "operator"]
GRID = {}
for f in FORGERS:
    up = r1["table"][f]["chain_with_witness"]["units_with_a_problem_of_part"]
    GRID[f] = [up.get(p, 0) for p in PARTS]
f4 = r4["forger4_operator_and_receipt"]["chain_with_witness"]
if r1["units_planted"] != 100 or r4["units_planted"] != 100 or f4["flagged"] != 100 - f4["missed"] or f4["flagged"] != 0:
    sys.exit("forger 4 is not 0 flagged of 100")
if f4["problem_kinds"]:
    sys.exit("forger 4 has problems")
GRID["thorough"] = [0, 0, 0]
WANT = {"careless": [100, 33, 100], "careful": [0, 100, 100], "operator": [0, 0, 100], "thorough": [0, 0, 0]}
if GRID != WANT:
    sys.exit(f"counts differ from the recount: {GRID}")

ROWS = [("careless", "Careless forger", "edits the record only"),
        ("careful", "Careful forger", "also recomputes the fingerprints"),
        ("operator", "Operator", "also rewrites the witness's log"),
        ("thorough", "Thorough operator", "also rebuilds the receipt")]
COLS = ["the record's chain\nof fingerprints", "the witness's saved\nfingerprints", "the receipt"]

fig = plt.figure(figsize=(style.WIDTH_IN, 1.8))
X0, CW, CH = 0.33, 0.21, 0.16
Y0 = 0.82
for j, c in enumerate(COLS):
    fig.text(X0 + j * (CW + 0.006) + CW / 2, 0.91, c, ha="center", va="center", fontsize=style.HEAD, linespacing=1.0)
for i, (key, name, how) in enumerate(ROWS):
    y = Y0 - (i + 1) * (CH + 0.006) + 0.006
    fig.text(0.01, y + CH * 0.68, name, ha="left", va="center", fontsize=style.HEAD)
    fig.text(0.01, y + CH * 0.22, how, ha="left", va="center", fontsize=style.NOTE, color=style.GREY)
    for j, n in enumerate(GRID[key]):
        x = X0 + j * (CW + 0.006)
        a = n / 100
        import matplotlib.colors as mc
        base = mc.to_rgb(style.FLAGGED)
        face = tuple(1 - a * (1 - b) for b in base)
        fig.patches.append(Rectangle((x, y), CW, CH, transform=fig.transFigure, facecolor=face,
                                     edgecolor=style.GREY, linewidth=0.6))
        lum = 0.299 * face[0] + 0.587 * face[1] + 0.114 * face[2]
        fig.text(x + CW / 2, y + CH / 2, str(n), ha="center", va="center", fontsize=style.EMPH,
                 fontweight="bold", color="white" if lum < 0.5 else style.INK)
fig.text(0.01, 0.04, "Each cell: how many of the 100 edits of the record (rule 3, method Checked) that safeguard reported. Darker is more.",
         ha="left", va="center", fontsize=style.NOTE, color=style.GREY)
style.save(fig, "figC2_witness_test")
