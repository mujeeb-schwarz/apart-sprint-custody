"""Figure F1: grades filed before the run beside the results, six rules by three methods.
Source: Table F1 and the text of appendix/F_predictions.md only (hand-copied below).
Table F1 row 4 says "Monitored passed and Checked failed", so Promised came out as filed (fail);
row 5 says "Promised passed; Monitored and Checked failed". The appendix states: of the 17 grades on
which both predictions agreed, 14 came out as filed; the three surprises were Monitored on rule 4,
Checked on rule 4 and Promised on rule 5. The script checks these counts.
"""
import sys

import style
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt

style.apply()
METHODS = ["Promised", "Monitored", "Checked"]
# rule -> {method: (filed, result)}; filed "split" is rule 5 Checked: author pass, assistant fail
FILED = {1: ("fail", "pass", "pass"), 2: ("fail", "fail", "pass"), 3: ("fail", "fail", "pass"),
         4: ("fail", "fail", "pass"), 5: ("fail", "fail", "split"), 6: ("fail", "pass", "pass")}
RESULT = {1: ("fail", "pass", "pass"), 2: ("fail", "fail", "pass"), 3: ("fail", "fail", "pass"),
          4: ("fail", "pass", "fail"), 5: ("pass", "fail", "fail"), 6: ("fail", "pass", "pass")}

agreed = differ = 0
surprises = []
for r in range(1, 7):
    for j, m in enumerate(METHODS):
        f, res = FILED[r][j], RESULT[r][j]
        if f == "split":
            continue
        agreed += 1
        if f != res:
            differ += 1
            surprises.append((r, m))
if (agreed, agreed - differ) != (17, 14):
    sys.exit(f"counts differ from the appendix: {agreed} agreed, {agreed - differ} as filed")
if surprises != [(4, "Monitored"), (4, "Checked"), (5, "Promised")]:
    sys.exit(f"surprises differ from the appendix: {surprises}")

CW, CH = 0.130, 0.20
X0, Y0 = 0.15, 0.885
fig = plt.figure(figsize=(style.WIDTH_IN, 2.0))
for r in range(1, 7):
    fig.text(X0 + (r - 1) * (CW + 0.005) + CW / 2, 0.935, f"Rule {r}", ha="center", va="center", fontsize=style.HEAD)
for j, m in enumerate(METHODS):
    y = Y0 - (j + 1) * (CH + 0.012) + 0.012
    fig.patches.append(Rectangle((0.012, y + CH / 2 - 0.04), 0.02, 0.08, transform=fig.transFigure,
                                 facecolor=style.METHOD[m], edgecolor=style.INK, linewidth=0.5))
    fig.text(0.04, y + CH / 2, m, ha="left", va="center", fontsize=style.HEAD)
    for r in range(1, 7):
        x = X0 + (r - 1) * (CW + 0.005)
        f, res = FILED[r][j], RESULT[r][j]
        diff = f != "split" and f != res
        split = f == "split"
        fig.patches.append(Rectangle((x, y), CW, CH, transform=fig.transFigure,
                                     facecolor="#EDEDED" if split else "white",
                                     edgecolor=style.INK if diff else style.GREY,
                                     linewidth=2.2 if diff else 0.6))
        ftxt = "author: pass\nassistant: fail" if split else f"filed: {f}"
        fig.text(x + CW / 2, y + CH * (0.70 if not split else 0.68), ftxt, ha="center", va="center",
                 fontsize=style.NOTE, color=style.GREY, linespacing=1.0)
        fig.text(x + CW / 2, y + CH * (0.28 if not split else 0.22), f"result: {res}", ha="center", va="center",
                 fontsize=style.LABEL, fontweight="bold", color=style.INK)
# key
for ky, face, edge, lw, text in [
        (0.145, "white", style.INK, 2.2, "result differs from what was filed (3 of the 17 grades on which both predictions agreed)"),
        (0.055, "#EDEDED", style.GREY, 0.6, "filed predictions differed; the grade matches the assistant's")]:
    fig.patches.append(Rectangle((0.15, ky - 0.03), 0.035, 0.06, transform=fig.transFigure,
                                 facecolor=face, edgecolor=edge, linewidth=lw))
    fig.text(0.195, ky, text, va="center", fontsize=style.LABEL)
style.save(fig, "figF1_predictions")
