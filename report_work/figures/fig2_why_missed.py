"""Figure 2: why a method misses. All six rules, the planted violations of each
split by kind; for each method, what happened to each kind, and its grade.

Counts, false alarms and grades come from grades.py, which reads
analysis/final_numbers.json and stops if any number differs from the values
it holds (Table 2 of draft/REPORT.src.md for the grades).
"""
import style
import grades
from grades import DATA, METHODS, OUTCOMES, GRADE, FA5
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt

style.apply()
INK, GREY, WARN = style.INK, style.GREY, style.MISSED

# rule: (panel title, [kind labels in drawing order], [label x-offsets in units])
PANELS = {
    1: ("Rule 1: words sent to\na place that is not named", ["logged", "not\nlogged", "log says\nharmless"]),
    2: ("Rule 2: a copy not\ndeleted by its deadline", ["skipped", "late", "log says\ndeleted"]),
    3: ("Rule 3: the record of\nhandovers edited", ["entry\nremoved", "entry\nadded", "entry\nchanged"]),
    4: ("Rule 4: a source\nremoved or wrong", ["removed", "wrong,\nin words", "wrong, as\nidentifier"]),
    5: ("Rule 5: certainty\nchanged", ["less\ncertain", "more\ncertain"]),
    6: ("Rule 6: the AI mark\nremoved or replaced", ["in the\nfinal note", "earlier"]),
}

BAR_H = 0.56
NARROW = 4          # segments narrower than this get their number above, with a leader
XMAX = 140
TAG_X = 104         # pass or fail, after the bar
FA_X = 109          # rule 5: false alarms column
FS_NUM, FS_KIND, FS_TAG = style.LABEL, style.LABEL, style.LABEL

fig = plt.figure(figsize=(style.WIDTH_IN, 3.95))
L, R, GAP = 0.118, 0.995, 0.012
PW = (R - L - 2 * GAP) / 3
ROWS = {0: (0.565, 0.222), 1: (0.112, 0.222)}   # (bottom, height) in figure fractions
axes = {}
for idx, rule in enumerate(PANELS):
    row, col = divmod(idx, 3)
    b, h = ROWS[row]
    axes[rule] = fig.add_axes([L + col * (PW + GAP), b, PW, h])

for rule, (title, kinds) in PANELS.items():
    ax = axes[rule]
    tag_x = FA_X + 9 if rule == 5 else TAG_X
    for i, m in enumerate(METHODS):
        y = len(METHODS) - 1 - i
        x = 0
        total = sum(sum(c) for c in DATA[rule][m])
        for counts in DATA[rule][m]:
            for o, n in zip(OUTCOMES, counts):
                if n == 0:
                    continue
                ax.add_patch(Rectangle(
                    (x, y - BAR_H / 2), n, BAR_H,
                    facecolor=style.OUTCOME_FACE[o], edgecolor=style.OUTCOME_EDGE[o],
                    hatch=style.OUTCOME_HATCH[o], linewidth=0.8))
                kw = dict(fontsize=FS_NUM, color=style.OUTCOME_TEXT[o],
                          fontweight="bold" if o == "missed" else "normal")
                if n < NARROW:   # number above the segment, with a short leader
                    cx = x + n / 2
                    d = -1 if cx > 90 else 1
                    ax.plot([cx, cx + 3 * d], [y + BAR_H / 2, y + BAR_H / 2 + 0.17],
                            color=INK, lw=0.6, clip_on=False, zorder=4)
                    ax.text(cx + 3.6 * d, y + BAR_H / 2 + 0.15, str(n),
                            ha="left" if d > 0 else "right", va="center",
                            clip_on=False, **kw)
                else:
                    ax.text(x + n / 2, y, str(n), ha="center", va="center",
                            bbox=dict(boxstyle="square,pad=0.1", fc="white", ec="none")
                            if o == "missed" else None, **kw)
                x += n
            if x >= total:
                continue
            ax.plot([x, x], [y - BAR_H / 2, y + BAR_H / 2], color="white", lw=2.2,
                    solid_capstyle="butt", zorder=3)
            ks = DATA[rule][m]
            j = [sum(sum(c) for c in ks[:k + 1]) for k in range(len(ks))].index(x)
            if counts[2] and ks[j + 1][0] == ks[j + 1][1] == 0:   # missed kind meets missed kind: an edge each
                for dx in (-1.2, 1.2):
                    ax.plot([x + dx, x + dx], [y - BAR_H / 2, y + BAR_H / 2],
                            color=style.OUTCOME_EDGE["missed"], lw=0.8, zorder=3.5)
        if rule == 5:   # false alarms on clean questions, in their own column
            a, c = FA5[m]
            ax.text(FA_X, y, str(a), ha="center", va="center", fontsize=FS_NUM,
                    color=WARN if a else INK, fontweight="bold" if a else "normal")
        g = GRADE[rule, m]
        ax.text(tag_x, y, g, ha="left", va="center", fontsize=FS_TAG,
                color=INK if g == "pass" else GREY,
                fontweight="bold" if g == "pass" else "normal")
    if rule == 5:
        ax.text(FA_X, len(METHODS) - 1 + BAR_H / 2 + 0.12, "false alarms,\nof 207 clean\n(pass: under 5%)",
                ha="center", va="bottom", fontsize=style.NOTE, color=WARN, linespacing=1.0)
    # kinds named once under the panel, with brackets, all on one line
    x = 0
    yb = -0.5
    sizes = [sum(c) for c in DATA[rule]["Checked"]]
    for j, (short, n) in enumerate(zip(kinds, sizes)):
        ax.plot([x + 1.0, x + 1.0, x + n - 1.0, x + n - 1.0],
                [yb + 0.1, yb, yb, yb + 0.1], color=GREY, lw=0.8, clip_on=False)
        if n < 15:   # narrow kind: label to the right of its bracket, past the bar's end
            ax.text(x + n + 1.5, yb - 0.12, short, ha="left", va="top", fontsize=FS_KIND,
                    color=INK, linespacing=1.0, clip_on=False)
        else:
            ax.text(x + n / 2, yb - 0.12, short, ha="center", va="top", fontsize=FS_KIND,
                    color=INK, linespacing=1.0)
        x += n
    ax.set_xlim(-0.6, XMAX)
    ax.set_ylim(-0.4, len(METHODS) - 0.38)
    ax.set_title(title, fontsize=style.HEAD, loc="left", pad=3, linespacing=1.05)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.tick_params(axis="x", bottom=False, labelbottom=False)
    ax.tick_params(axis="y", left=False, labelleft=False)
    ax.set_yticks(range(len(METHODS)))

# method names on the left of each row
for rule in (1, 4):
    ax = axes[rule]
    ax.tick_params(axis="y", labelleft=True, pad=4)
    ax.set_yticklabels(METHODS[::-1], fontsize=style.HEAD)

# key for the outcomes, one row at the top
kx, ky = L, 0.972
for o in OUTCOMES:
    fig.patches.append(Rectangle((kx, ky - 0.017), 0.028, 0.034, transform=fig.transFigure,
                                 facecolor=style.OUTCOME_FACE[o], edgecolor=style.OUTCOME_EDGE[o],
                                 hatch=style.OUTCOME_HATCH[o], linewidth=0.8))
    fig.text(kx + 0.036, ky, o, va="center", fontsize=style.LABEL)
    kx += 0.125
fig.text(L, ky - 0.052, "Each bar: the planted violations of one rule, split by kind. "
         "Right of each bar: pass or fail.",
         ha="left", va="center", fontsize=style.NOTE, color=GREY)

style.save(fig, "fig2_why_missed")
