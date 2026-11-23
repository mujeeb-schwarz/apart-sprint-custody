"""Figure G1: from the first download of data to the forger test. Events in order (not to time scale).
Every clock time is one written in appendix/H_before_kickoff.md, appendix/G_changes_after_freeze.md
or night/night_notes.md; the script checks that each time string appears in the file named for the
event, and that the events are in time order. Times are Pacific. Events with no written time are
left out (version 3 of the plan "that evening", the kickoff talk, which is given in UTC only).
"""
import os
import re
import sys

import style
from matplotlib.lines import Line2D
import matplotlib.pyplot as plt

style.apply()
RW = os.path.abspath(os.path.join(style.HERE, ".."))
ROOT = os.path.abspath(os.path.join(RW, ".."))
FILES = {"H": os.path.join(RW, "appendix", "H_before_kickoff.md"),
         "G": os.path.join(RW, "appendix", "G_changes_after_freeze.md"),
         "N": os.path.join(ROOT, "night", "night_notes.md")}
TEXT = {k: open(v, encoding="utf-8").read() for k, v in FILES.items()}

BEFORE, FREEZE, CHANGE, RUN = "before", "freeze", "change", "run"
# (day, clock for the label, kind, text, file, substrings that must appear in that file, sort key hh:mm)
EV = [
    ("Thu 12 Nov", "22:26", BEFORE, "Download of the three public data sets begins (time approximate)", "H", ["Thu 12 Nov 2026 at about 22:26"]),
    ("Thu 12 Nov", "23:01", BEFORE, "First project file written (time approximate)", "H", ["about 23:01"]),
    ("Fri 13 Nov", "14:37", BEFORE, "Author locks the first test plan", "H", ["14:37 Pacific"]),
    ("Fri 13 Nov", "14:43", BEFORE, "Author changes the plan", "H", ["changed it at 14:43"]),
    ("Fri 13 Nov", "16:34", BEFORE, "Version 2 of the plan", "H", ["version 2 followed at 16:34"]),
    ("Fri 13 Nov", "22:33", BEFORE, "Predictions filed", "F", ["Fri 13 Nov at 22:33"]),
    ("Fri 13 Nov", "23:33", FREEZE, "FROZEN: code, settings, prompts, plan, scorer. The test set starts to run", "G", ["Fri 13 Nov, 23:33"]),
    ("Fri 13 Nov", "23:43", RUN, "The runner stops at the usage limit", "N", ["Fri 13 Nov 23:43"]),
    ("Sat 14 Nov", "02:03", RUN, "Runner started again by hand", "N", ["Sat 14 Nov 02:03"]),
    ("Sat 14 Nov", "02:06", CHANGE, "Two shell scripts restart the runner and start the outside model's texts", "G", ["Sat 14 Nov 02:06"]),
    ("Sat 14 Nov", "07:36", CHANGE, "A third script starts the repeat check and the hidden-instruction part", "G", ["07:36 to 07:45"]),
    ("Sat 14 Nov", "07:45", CHANGE, "Sign-in renewed; second pass of the judge for rules 4 and 6 begins", "G", ["from 07:45", "renewed at 07:45"]),
    ("Sun 15 Nov", "13:11", CHANGE, "Program that takes in the monitor's and review's answers changed (to 13:28)", "G", ["13:11 to 13:28"]),
    ("Sun 15 Nov", "13:14", CHANGE, "Second judge, on another maker's model, reads 400 texts (to 13:23)", "G", ["Sun 15 Nov 13:14 to 13:23"]),
    ("Sun 15 Nov", "13:18", CHANGE, "One expression in the Z3 generator changed", "G", ["Sun 15 Nov 13:18"]),
    ("Sun 15 Nov", "13:36", CHANGE, "Round 2 of the planted texts for rule 5; rule 4 sources confirmed again", "G", ["from 13:36"]),
    ("Sun 15 Nov", "15:03", CHANGE, "WITNESS TEST: four forgers, two checks, no AI call (to 15:14)", "G", ["15:03 to 15:14"]),
    ("Sun 15 Nov", "19:32", CHANGE, "FORGER TEST: a program and GPT-6.1 forge the log (to 20:10)", "G", ["Sun 15 Nov 19:32 to 20:10"]),
]
TEXT["F"] = open(os.path.join(RW, "appendix", "F_predictions.md"), encoding="utf-8").read()
DAYS = {"Thu 12 Nov": 0, "Fri 13 Nov": 1, "Sat 14 Nov": 2, "Sun 15 Nov": 3}
prev = -1
for day, clock, kind, text, src, subs in EV:
    for s in subs:
        if s not in TEXT[src]:
            sys.exit(f"time not found in {src}: {s!r} for {text!r}")
    h, m = map(int, clock.split(":"))
    t = DAYS[day] * 1440 + h * 60 + m
    if t < prev:
        sys.exit(f"events out of order at {day} {clock}")
    prev = t
if sum(1 for e in EV if e[2] == FREEZE) != 1:
    sys.exit("exactly one freeze expected")
# the freeze is the 23:33 event and every change comes after it
fi = [i for i, e in enumerate(EV) if e[2] == FREEZE][0]
if any(e[2] in (CHANGE, RUN) for e in EV[:fi]) or any(e[2] == BEFORE for e in EV[fi + 1:]):
    sys.exit("kinds not consistent with the freeze")

# neutral colours for time: blue and vermillion mean outcomes in the other figures
COL = {BEFORE: style.LIGHT, FREEZE: style.INK, CHANGE: "#E69F00", RUN: "white"}
fig = plt.figure(figsize=(style.WIDTH_IN, 2.84))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 1)
ax.set_ylim(0, 1)
ax.axis("off")
n = len(EV)
TOP, ROW = 0.867, 0.048
RAIL = 0.215
xt = 0.19    # right edge of the time labels
ys = [TOP - i * ROW for i in range(n)]
ax.add_line(Line2D([RAIL, RAIL], [ys[0] + 0.02, ys[-1] - 0.02], color=style.LIGHT, lw=1.2, zorder=1))
for (day, clock, kind, text, src, subs), y in zip(EV, ys):
    ax.text(xt, y, f"{day[:3]} {day[4:]}  {clock}", ha="right", va="center", fontsize=style.LABEL, color=style.INK)
    ax.scatter([RAIL], [y], s=34 if kind != FREEZE else 70, marker="o" if kind != FREEZE else "D",
               facecolor=COL[kind], edgecolor=style.INK if kind in (RUN, BEFORE, FREEZE) else COL[kind],
               linewidth=0.8, zorder=3)
    bold = kind == FREEZE or text.startswith(("WITNESS", "FORGER"))
    ax.text(RAIL + 0.02, y, text, ha="left", va="center", fontsize=style.LABEL,
            fontweight="bold" if bold else "normal",
            color=style.INK)
# the freeze: a shaded band from the freeze row down, with a solid line at its top
from matplotlib.patches import Rectangle
yf = ys[fi]
ax.add_patch(Rectangle((0.0, 0.0), 1.0, yf + ROW / 2, facecolor="#FFF3DC", edgecolor="none", zorder=0))
ax.add_line(Line2D([0.0, 1.0], [yf + ROW / 2, yf + ROW / 2], color=style.INK, lw=1.2, zorder=1))
ax.text(0.995, ys[-1], "after the freeze", ha="right", va="center", fontsize=style.NOTE, color=style.GREY)
ax.text(0.995, yf + ROW / 2 + 0.012, "before the freeze", ha="right", va="bottom", fontsize=style.NOTE, color=style.GREY)
# legend row
lx = 0.01
for kind, label in [(BEFORE, "before the freeze"), (FREEZE, "the freeze"),
                    (CHANGE, "change made after the freeze"), (RUN, "run event, no change")]:
    ax.scatter([lx + 0.008], [0.957], s=34 if kind != FREEZE else 60, marker="o" if kind != FREEZE else "D",
               facecolor=COL[kind], edgecolor=style.INK if kind in (RUN, BEFORE, FREEZE) else COL[kind], linewidth=0.8)
    t = ax.text(lx + (0.028 if kind == FREEZE else 0.022), 0.957, label, ha="left", va="center",
                fontsize=style.LABEL)
    lx = t.get_window_extent(fig.canvas.get_renderer()).transformed(ax.transData.inverted()).x1 + 0.035
ax.text(0.01, 0.910, "Events in order, not to time scale. Times are Pacific.", ha="left", va="center",
        fontsize=style.NOTE, color=style.GREY)
style.save(fig, "figG1_timeline")
