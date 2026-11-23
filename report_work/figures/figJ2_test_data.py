"""Figure J2: what the test set looks like. Per-item values are computed with the same loaders as
analysis/data_appendix.py (config/design_choices.json -> the case files), and every count and median
is asserted against analysis/data_appendix_numbers.json.
"""
import json
import os
import statistics
import sys
from collections import Counter

import style
import matplotlib.pyplot as plt

style.apply()
MID = "#8C8C8C"   # neutral: the blues mean outcomes in the other figures
ROOT = os.path.abspath(os.path.join(style.HERE, "..", ".."))
cfg = json.load(open(os.path.join(ROOT, "config/design_choices.json"), encoding="utf-8"))
N = json.load(open(os.path.join(style.HERE, "..", "analysis", "data_appendix_numbers.json")))


def jl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


exp1 = jl(os.path.join(ROOT, cfg["cases"]["files"]["1"]))
exp2 = jl(os.path.join(ROOT, cfg["cases"]["files"]["2"]))
words = lambda t: len(str(t).split())

tw = [words(v["conversation"]) for v in exp1 if v["split"] == "test"]
graded_test = [v for v in exp2 if v["meta"]["case_kind"] == "graded" and v["split"] == "test"]
stored_test = [v for v in exp2 if v["meta"]["case_kind"] == "stored" and v["split"] == "test"]
grades = Counter(str(v["expert_certainty"]) for v in graded_test)
aw = [words(v["given_answer"]) for v in stored_test]
spec = Counter(v["meta"]["specialty"] for v in stored_test)
top5 = spec.most_common(5)
other = len(stored_test) - sum(c for _, c in top5)

def need(cond, msg):
    if not cond:
        sys.exit("assertion failed: " + msg)

need(len(tw) == N["aci"]["test_words"]["n"] == 157, "157 transcripts")
need(statistics.median(tw) == N["aci"]["test_words"]["median"] == 1239, "median transcript words")
need((min(tw), max(tw)) == (N["aci"]["test_words"]["min"], N["aci"]["test_words"]["max"]), "transcript range")
need(len(graded_test) == N["medevidence"]["test"] == 213, "213 graded")
need(dict(grades) == N["medevidence"]["test_grade_levels"], "grade counts")
need(len(aw) == N["pocqi"]["test_answer_words"]["n"] == 200, "200 answers")
need(statistics.median(aw) == N["pocqi"]["test_answer_words"]["median"] == 475.5, "median answer words")
need((min(aw), max(aw)) == (N["pocqi"]["test_answer_words"]["min"], N["pocqi"]["test_answer_words"]["max"]), "answer range")
need([list(t) for t in top5] == N["pocqi"]["test_specialties_top5"], "top 5 specialties")
need(other == N["pocqi"]["test_specialties_other"] == 124, "other specialties")
need(len(spec) - 5 == 24, "24 other specialties")

fig = plt.figure(figsize=(style.WIDTH_IN, 3.7))
pos = {(0, 0): [0.085, 0.625, 0.36, 0.29], (0, 1): [0.58, 0.625, 0.40, 0.29],
       (1, 0): [0.085, 0.125, 0.36, 0.29], (1, 1): [0.70, 0.125, 0.28, 0.29]}
import numpy as np
axs = np.empty((2, 2), dtype=object)
for k, v in pos.items():
    axs[k] = fig.add_axes(v)


def tidy(ax):
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.tick_params(labelsize=style.LABEL)

def hist(ax, vals, med, bins, xlabel, label):
    ax.hist(vals, bins=bins, color=MID, edgecolor="white", linewidth=0.5)
    top = ax.get_ylim()[1]
    ax.set_ylim(0, top * 1.3)
    ax.axvline(med, color=style.INK, lw=1.2, ls="--")
    ax.text(med, top * 1.3, f" median {med:,g}", ha="left", va="top", fontsize=style.NOTE)
    ax.set_xlabel(xlabel, fontsize=style.LABEL)
    ax.set_ylabel("cases", fontsize=style.LABEL)
    ax.set_title(label, fontsize=style.HEAD, loc="left", pad=3)
    tidy(ax)

hist(axs[0, 0], tw, 1239, 14, "words per transcript", "(a) 157 mock consultations")
axs[0, 0].set_xticks([500, 1000, 1500, 2000, 2500])
ax = axs[0, 1]
order = ["high", "moderate", "low", "very low", "no data"]
vals = [grades[g] for g in order]
bars = ax.bar(range(5), vals, color=MID, width=0.65)
for b, v in zip(bars, vals):
    ax.text(b.get_x() + b.get_width() / 2, v + 1, str(v), ha="center", va="bottom", fontsize=style.LABEL)
ax.set_xticks(range(5))
ax.set_xticklabels(["high", "mod-\nerate", "low", "very\nlow", "no\ndata"], fontsize=style.LABEL)
ax.set_ylim(0, 66)
ax.set_ylabel("questions", fontsize=style.LABEL)
ax.set_xlabel("expert grade", fontsize=style.LABEL)
ax.set_title("(b) 213 review questions", fontsize=style.HEAD, loc="left", pad=3)
tidy(ax)
hist(axs[1, 0], aw, 475.5, 14, "words per stored answer", "(c) 200 stored answers")
ax = axs[1, 1]
labels = [k for k, _ in top5] + ["other\n(24 specialties)"]
vals = [c for _, c in top5] + [other]
ys = range(len(vals))[::-1]
bars = ax.barh(list(ys), vals, color=MID, height=0.65)
for y, v in zip(ys, vals):
    ax.text(v + 2, y, str(v), va="center", fontsize=style.LABEL)
ax.set_yticks(list(ys))
ax.set_yticklabels(labels, fontsize=style.LABEL)
ax.set_xlim(0, 160)
ax.set_xticks([0, 50, 100, 150])
ax.set_xlabel("questions", fontsize=style.LABEL)
ax.set_title("(d) specialty, 200 questions", fontsize=style.HEAD, loc="left", pad=3)
tidy(ax)
style.save(fig, "figJ2_test_data")
