"""Figure C1: who raised the flags. For each rule and method, the planted violations that the method
caught, split by the part that flagged them (program only, AI only, both), with the missed ones on top.

Source: Table C3 of appendix/C_results.md (hand-copied below), checked against
analysis/final_numbers.json (e1_flags_by_part, e2_flags_by_part). Under Checked, rule 1 is
"program blocked 100". Each bar's caught total is asserted to equal planted minus missed.
"""
import json
import os
import sys

import style
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt

style.apply()
METHODS = ["Promised", "Monitored", "Checked"]
# Table C3: (program only, AI only, both) per rule and method
C3 = {
    1: {"Promised": (0, 0, 33), "Monitored": (0, 0, 100), "Checked": (100, 0, 0)},   # Checked: blocked
    2: {"Promised": (39, 0, 28), "Monitored": (39, 0, 28), "Checked": (100, 0, 0)},
    3: {"Promised": (0, 88, 0), "Monitored": (0, 88, 0), "Checked": (100, 0, 0)},
    4: {"Promised": (70, 0, 20), "Monitored": (13, 0, 86), "Checked": (55, 0, 0)},
    5: {"Promised": (0, 99, 0), "Monitored": (0, 0, 99), "Checked": (97, 0, 0)},
    6: {"Promised": (0, 0, 40), "Monitored": (0, 0, 100), "Checked": (100, 0, 0)},
}
PLANTED = {1: 100, 2: 100, 3: 100, 4: 100, 5: 99, 6: 100}
MISSED = {"Promised": [67, 33, 12, 10, 0, 60], "Monitored": [0, 33, 12, 1, 0, 0],
          "Checked": [0, 0, 0, 45, 2, 0]}

fn = json.load(open(os.path.join(style.HERE, "..", "analysis", "final_numbers.json")))
src = {**fn["e1_flags_by_part"], **fn["e2_flags_by_part"]}
KEY = {"flagged:program_only": 0, "flagged:ai_only": 1, "flagged:both": 2, "blocked:None": 0}
for rule in range(1, 7):
    for m in METHODS:
        got = [0, 0, 0]
        for k, n in src[str(rule)][m].items():
            got[KEY[k]] += n
        if tuple(got) != C3[rule][m]:
            sys.exit(f"rule {rule} {m}: final_numbers.json gives {got}, Table C3 gives {C3[rule][m]}")
        caught = sum(C3[rule][m])
        if caught != PLANTED[rule] - MISSED[m][rule - 1]:
            sys.exit(f"rule {rule} {m}: caught {caught} is not planted {PLANTED[rule]} minus missed {MISSED[m][rule-1]}")

PART = [("program only", "#555555", "white", None),
        ("AI only", "#E69F00", "black", None),
        ("both", "#E69F00", "black", "\\\\\\\\")]
fig = plt.figure(figsize=(style.WIDTH_IN, 3.4))
ax = fig.add_axes([0.075, 0.25, 0.91, 0.58])
BW, GAPG = 0.27, 1.0
for rule in range(1, 7):
    x0 = (rule - 1) * GAPG
    for j, m in enumerate(METHODS):
        x = x0 + (j - 1) * 0.30
        y = 0
        for (name, face, tcol, hatch), n in zip(PART, C3[rule][m]):
            if rule == 1 and m == "Checked" and name == "program only":
                face, tcol = style.BLOCKED, "white"     # blocked, not flagged
            if n:
                ax.add_patch(Rectangle((x - BW / 2, y), BW, n, facecolor=face,
                                       edgecolor="#555555" if hatch else face, hatch=hatch, linewidth=0.6))
                ax.text(x, y + n / 2, str(n), ha="center", va="center", fontsize=style.LABEL, color=tcol,
                        bbox=dict(boxstyle="square,pad=0.08", fc="#E69F00", ec="none") if hatch else None)
                y += n
        miss = MISSED[m][rule - 1]
        if miss:
            ax.add_patch(Rectangle((x - BW / 2, y), BW, miss, facecolor="white", edgecolor=style.MISSED,
                                   hatch="////", linewidth=0.8))
            if miss >= 8:
                ax.text(x, y + miss / 2, str(miss), ha="center", va="center", fontsize=style.LABEL, color=style.MISSED,
                        fontweight="bold", bbox=dict(boxstyle="square,pad=0.08", fc="white", ec="none"))
            else:
                ax.text(x, y + miss + 0.6, str(miss), ha="center", va="bottom", fontsize=style.LABEL, color=style.MISSED,
                        fontweight="bold")
        if rule == 1 and m == "Checked":
            ax.text(x, y + 3, "blocked", ha="center", va="bottom", fontsize=style.NOTE)
        ax.add_patch(Rectangle((x - BW / 2, -9), BW, 5.5, clip_on=False, facecolor=style.METHOD[m],
                               edgecolor=style.INK, linewidth=0.5))
    ax.text(x0, -14, f"Rule {rule}", ha="center", va="top", fontsize=style.HEAD, clip_on=False)
ax.set_xlim(-0.55, 5.55)
ax.set_ylim(0, 105)
ax.set_yticks([0, 25, 50, 75, 100])
ax.tick_params(axis="y", labelsize=style.LABEL)
ax.tick_params(axis="x", bottom=False, labelbottom=False)
ax.set_ylabel("planted violations", fontsize=style.LABEL)
for s in ("top", "right"):
    ax.spines[s].set_visible(False)
# legends
kx, ky = 0.075, 0.955
items = ([("blocked", style.BLOCKED, None, style.BLOCKED)] + [(n, f, h, f if not h else "#555555") for n, f, _, h in PART]
         + [("missed", "white", "////", style.MISSED)])
for name, face, hatch, edge in items:
    fig.patches.append(Rectangle((kx, ky - 0.025), 0.026, 0.05, transform=fig.transFigure, facecolor=face,
                                 edgecolor=edge, hatch=hatch, linewidth=0.8))
    t = fig.text(kx + 0.033, ky, name, va="center", fontsize=style.LABEL)
    kx = t.get_window_extent(fig.canvas.get_renderer()).transformed(fig.transFigure.inverted()).x1 + 0.045
kx, ky = 0.075, 0.035
t = fig.text(kx, ky, "Method under each bar:", va="center", fontsize=style.HEAD)
kx = t.get_window_extent(fig.canvas.get_renderer()).transformed(fig.transFigure.inverted()).x1 + 0.025
for m in METHODS:
    fig.patches.append(Rectangle((kx, ky - 0.022), 0.026, 0.044, transform=fig.transFigure,
                                 facecolor=style.METHOD[m], edgecolor=style.INK, linewidth=0.5))
    t = fig.text(kx + 0.033, ky, m, va="center", fontsize=style.LABEL)
    kx = t.get_window_extent(fig.canvas.get_renderer()).transformed(fig.transFigure.inverted()).x1 + 0.045
style.save(fig, "figC1_who_flagged")
