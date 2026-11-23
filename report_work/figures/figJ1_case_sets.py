"""Figure J1: from the public files to the test sets.
Numbers asserted against analysis/data_appendix_numbers.json (as in appendix/J_data.md).
"""
import json
import os
import sys

import style
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt

style.apply()
N = json.load(open(os.path.join(style.HERE, "..", "analysis", "data_appendix_numbers.json")))

# (name, items in the public file, test, practice, not used, why not used)
SETS = [
    ("ACI-Bench", 207, 157, 50, 0, ""),
    ("MedEvidence", 284, 213, 50, 21, "no usable grade"),
    ("Real-POCQi", 620, 200, 36, 384, "not drawn"),
]
a, m, p = N["aci"], N["medevidence"], N["pocqi"]
checks = [
    (a["rows_total"], 207), (a["test"], 157), (a["practice"], 50), (a["left_out"], 0),
    (m["rows"], 284), (m["test"], 213), (m["practice"], 50), (m["left_out_no_grade_other_answer"], 21),
    (p["questions"], 620), (p["test"], 200), (p["practice"], 36), (p["not_drawn_left_out"], 384),
]
for got, want in checks:
    if got != want:
        sys.exit(f"JSON differs from the expected number: {got} vs {want}")
for name, tot, t, pr, out, _ in SETS:
    if t + pr + out != tot:
        sys.exit(f"{name}: parts do not add up")

fig, ax = plt.subplots(figsize=(style.WIDTH_IN, 1.9))
fig.subplots_adjust(left=0.15, right=0.985, top=0.82, bottom=0.25)
H = 0.5
# neutral greys: the blues mean outcomes in the other figures
SEG = [("test set", "#4D4D4D", "white", None),
       ("practice set", "#C8C8C8", "black", None),
       ("not used", "white", style.INK, "////")]
for i, (name, tot, t, pr, out, why) in enumerate(SETS):
    y = len(SETS) - 1 - i
    x = 0
    for (label, face, tcol, hatch), n in zip(SEG, (t, pr, out)):
        if n == 0:
            continue
        ax.add_patch(Rectangle((x, y - H / 2), n, H, facecolor=face,
                               edgecolor=style.GREY if hatch else face, hatch=hatch, linewidth=0.8))
        txt = str(n)
        kw = dict(ha="center", va="center", fontsize=style.LABEL, color=tcol)
        if hatch:
            kw["bbox"] = dict(boxstyle="square,pad=0.05", fc="white", ec="none")
        ax.text(x + n / 2, y, txt, **kw)
        x += n
    if out and name == "MedEvidence":
        ax.text(tot + 8, y, "21 left out for want of a usable grade", va="center", ha="left", fontsize=style.NOTE)
    elif out:
        ax.text(tot + 8, y, "not drawn", va="center", ha="left", fontsize=style.NOTE)
    ax.text(0, y + H / 2 + 0.04, f"{tot} in the public file", va="bottom", ha="left", fontsize=style.NOTE, color=style.GREY)
ax.set_xlim(0, 760)
ax.set_xticks(range(0, 800, 100))
ax.spines["bottom"].set_bounds(0, 700)
ax.set_ylim(-0.5, len(SETS) - 0.3)
ax.set_yticks(range(len(SETS)))
ax.set_yticklabels([s[0] for s in SETS][::-1], fontsize=style.HEAD)
ax.set_xlabel("items", fontsize=style.LABEL)
ax.tick_params(axis="y", length=0)
ax.tick_params(axis="x", labelsize=style.LABEL)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
# legend above
kx = 0.15
for label, face, tcol, hatch in SEG:
    fig.patches.append(Rectangle((kx, 0.905), 0.024, 0.07, transform=fig.transFigure, facecolor=face,
                                 edgecolor=style.GREY if hatch else face, hatch=hatch, linewidth=0.8))
    t = fig.text(kx + 0.031, 0.94, label, va="center", fontsize=style.LABEL)
    kx = t.get_window_extent(fig.canvas.get_renderer()).transformed(fig.transFigure.inverted()).x1 + 0.045
style.save(fig, "figJ1_case_sets")
