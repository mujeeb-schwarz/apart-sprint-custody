"""Figure 1: one visit on the test bench, with real words.

The concept figure (the flow, where each method looks, who notices, the least
method per rule) with a tangible example: words spoken in a mock consultation
(ACI-Bench, D2N155), the line the AI note writer made of them (the run's stored
output), and two planted violations drawn on the flow.

Every quotation is asserted below against the file it comes from, and every
verdict against analysis/final_numbers.json through grades.py, so the figure
stops if it drifts from the data.
"""
import json
import os

import style
import grades
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle, Polygon, FancyArrowPatch

ROOT = os.path.abspath(os.path.join(style.HERE, "..", ".."))   # apart-sprint-custody/
CASES1 = os.path.join(ROOT, "data", "cases", "exp1.jsonl")
AI1 = os.path.join(ROOT, "runs", "night_e1", "ai_calls.jsonl")


# ---------------------------------------------------------------- the data, asserted
def spoken(q, who):
    """q, if a line of the mock consultation D2N155 spoken by `who` holds it."""
    for line in open(CASES1, encoding="utf-8"):
        if '"aci:D2N155"' in line:
            talk = json.loads(line)["conversation"].split("\n")
            if any(t.startswith(f"[{who}]") and q in t for t in talk):
                return q
    raise SystemExit(f"NOT AS STORED: {who}: {q!r}")


def noted(q):
    """q, if the AI note writer's stored note for this consultation holds it."""
    for line in open(AI1, encoding="utf-8"):
        if '"c0155+P2-069.A.r0"' in line:
            r = json.loads(line)
            if r["prompt_id"] == "note_writer.v1" and q in r["output"]:
                return q
    raise SystemExit(f"NOT AS STORED in the AI's note: {q!r}")


D1 = spoken("you have a nonhealing foot ulcer", "doctor")
D2 = spoken("you've got type two diabetes", "doctor")
P1 = spoken("it did get a little bit red and infected", "patient")
P2 = spoken("my last a1c was about ten", "patient")
NOTE_LINE = noted("Last A1c was about 10, per patient.")


def verdict(rule, kind):
    """The one outcome each method had on every case of this planted kind."""
    out = {}
    for m in grades.METHODS:
        cell = grades.FN["e1_by_kind"][rule][kind][m]
        if len(cell) != 1:
            raise SystemExit(f"rule {rule}, {kind}, {m}: mixed outcomes {cell}")
        out[m] = next(iter(cell))
    return out


KEPT = verdict("2", "deletion skipped, log says it happened")   # column 1
SENT = verdict("1", "extra send, not logged")                   # column 2
if KEPT != {"Promised": "missed", "Monitored": "missed", "Checked": "flagged"}:
    raise SystemExit(f"kept copy: {KEPT}")
if SENT != {"Promised": "missed", "Monitored": "flagged", "Checked": "blocked"}:
    raise SystemExit(f"unnamed send: {SENT}")

TILES = [(1, "named places"), (2, "deleted by deadline"), (3, "record of handovers"),
         (4, "source named"), (5, "certainty unchanged"), (6, "AI's part marked")]   # as in Table 2

ROWS = [  # method, what it reads, why it does or does not see the two violations
    ("Promised", ["A review reads the system's own log and the final texts."],
     "The log says “deleted” and leaves the send out."),
    ("Monitored", ["Adds a monitor that reads every message as it is sent."],
     "A kept copy sends no message; the send is read as it leaves."),
    ("Checked", ["A gate on every handover and deletion keeps its own record,",
                 "with fingerprints at a witness."],
     "Its record holds no deletion for this copy; it stops the send."),
]

style.apply()
W, H = style.WIDTH_IN, 4.50
fig = plt.figure(figsize=(W, H))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")

INK, GREY = style.INK, style.GREY
P, M, C = style.PROMISED, style.MONITORED, style.CHECKED
VER = style.MISSED
FS = style.LABEL
VENDOR_FILL = "#F2F2F2"
COPY_TINT = "#FBE1CF"
X0, X1 = 0.10, 6.40     # outer margins


def box(x, y, w, h, text=None, fc="white", ec=INK, lw=0.9, fs=FS, color=INK, r=0.04, z=2,
        ha="center", ls="-", **kw):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw, ls=ls, zorder=z))
    if text:
        tx = x + w / 2 if ha == "center" else x + 0.07
        return ax.text(tx, y + h / 2, text, ha=ha, va="center", fontsize=fs, color=color,
                       zorder=z + 1, linespacing=1.0, **kw)


def arrow(x0, y0, x1, y1, color=INK, lw=1.0, z=3):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=8,
                                 color=color, lw=lw, zorder=z, shrinkA=0, shrinkB=0))


def monitor_mark(x, y, z=5):
    ax.add_patch(Circle((x, y), 0.052, fc=M, ec=INK, lw=0.7, zorder=z))


def gate_mark(x, y, z=5):
    ax.add_patch(Rectangle((x - 0.028, y - 0.075), 0.056, 0.15, fc=C, ec=INK, lw=0.5, zorder=z))


def review_mark(x, y, z=5):
    ax.add_patch(Rectangle((x - 0.06, y - 0.06), 0.12, 0.12, fc=P, ec=INK, lw=0.5, zorder=z))


MARK = {"Promised": review_mark, "Monitored": monitor_mark, "Checked": gate_mark}


def number(x, y, n, z=9):
    """A numbered marker for a planted violation."""
    ax.add_patch(Circle((x, y), 0.075, fc=VER, ec=VER, lw=0.5, zorder=z))
    ax.text(x, y - 0.004, str(n), ha="center", va="center", fontsize=style.NOTE,
            fontweight="bold", color="white", zorder=z + 1)


def left_edge(t):
    """The left edge of a drawn text, in inches on the figure."""
    fig.canvas.draw()
    bb = t.get_window_extent(fig.canvas.get_renderer())
    return ax.transData.inverted().transform((bb.x0, bb.y0))[0]


def kept_copy(x, y, r=0.105):
    ax.add_patch(Circle((x, y), r, fc=COPY_TINT, ec=VER, lw=2.2, zorder=6))
    w, h, f = 0.075, 0.105, 0.026
    pts = [(x - w / 2, y - h / 2), (x + w / 2, y - h / 2), (x + w / 2, y + h / 2 - f),
           (x + w / 2 - f, y + h / 2), (x - w / 2, y + h / 2)]
    ax.add_patch(Polygon(pts, closed=True, fc="white", ec=VER, lw=0.9, zorder=7))
    for k in range(3):
        yy = y + 0.021 - k * 0.024
        ax.plot([x - 0.022, x + 0.022], [yy, yy], color=VER, lw=0.6, zorder=8)


# ---------------------------------------------------------------- the words in the room
QY0, QY1 = 4.07, 4.45
box(X0, QY0, 4.60, QY1 - QY0, ec=GREY, lw=0.8, r=0.05)
for yy, who, words in ((4.35, "Doctor:", f"“… {D1} … {D2} …”"),
                       (4.17, "Patient:", f"“… {P1} … {P2}”")):
    t = ax.text(X0 + 0.09, yy, who, ha="left", va="center", fontsize=FS, fontweight="bold",
                zorder=4)
    ax.annotate(" " + words, xy=(1, 0.5), xycoords=t, ha="left", va="center", fontsize=FS,
                style="italic", zorder=4)
ax.text(4.86, 4.26, "In the room: words from\na mock consultation", ha="left", va="center",
        fontsize=style.NOTE, color=GREY, style="italic", linespacing=1.0)

# ---------------------------------------------------------------- band a: the flow
VX0, VX1, VY0, VY1 = X0, 4.70, 2.40, 3.98
ax.add_patch(FancyBboxPatch((VX0, VY0), VX1 - VX0, VY1 - VY0,
                            boxstyle="round,pad=0,rounding_size=0.06",
                            fc=VENDOR_FILL, ec=GREY, lw=0.9, ls=(0, (4, 2)), zorder=0))
ax.text(0.92, VY1, " the vendor's system and the medical record ", ha="left", va="center", fontsize=style.NOTE,
        color=GREY, style="italic", zorder=1,
        bbox=dict(boxstyle="square,pad=0.05", fc="white", ec="none"))

SW, SH, SY = 0.95, 0.34, 3.40
STEPS = [0.24, 1.98, 3.62]
for x, t in zip(STEPS, ["Transcribing\nservice", "AI note\nwriter", "Medical\nrecord"]):
    box(x, SY, SW, SH, t)
arrow(STEPS[0] + SW / 2, QY0, STEPS[0] + SW / 2, SY + SH + 0.015)   # the words enter
cy = SY + SH / 2
for (xa, xb, c, what) in ((STEPS[0] + SW, STEPS[1], "A", "transcript"),
                          (STEPS[1] + SW, STEPS[2], "B", "note")):
    arrow(xa + 0.02, cy, xb - 0.02, cy)
    L_ = xb - xa
    monitor_mark(xa + 0.32 * L_, cy)
    gate_mark(xa + 0.66 * L_, cy)
    mx = (xa + xb) / 2
    lx = mx - (0.27 if c == "A" else 0.14)
    ax.add_patch(Circle((lx, cy - 0.17), 0.065, fc="white", ec=INK, lw=0.8, zorder=5))
    ax.text(lx, cy - 0.175, c, ha="center", va="center", fontsize=style.NOTE,
            fontweight="bold", zorder=6)
    ax.text(lx + 0.09, cy - 0.17, what, ha="left", va="center", fontsize=style.NOTE,
            color=GREY)
# what the AI wrote from the patient's words
ax.text(2.66, 3.275, "the AI's note, from those words:", ha="left", va="center",
        fontsize=style.NOTE, color=GREY, style="italic", zorder=4)
ax.text(2.66, 3.150, f"“{NOTE_LINE}”", ha="left", va="center", fontsize=style.NOTE,
        style="italic", zorder=4)

# violation 1: the kept copy at the AI note writer
kx, ky = STEPS[1] + SW / 2, 3.10
ax.plot([kx, kx], [SY, ky + 0.105], color=VER, lw=1.3, zorder=5)
kept_copy(kx, ky)
t1 = ax.text(kx - 0.17, ky, "a copy of the transcript,\nkept past its deadline", ha="right",
             va="center", fontsize=FS, color=VER, fontweight="bold", linespacing=1.0)
number(left_edge(t1) - 0.12, ky, 1)

# violation 2: the transcript also goes to a place nobody named
sx, sy = STEPS[1] + 0.80, 3.86
ax.plot([sx, sx, 4.80], [SY + SH, sy, sy], color=VER, lw=1.3, ls=(0, (3, 2)), zorder=4)
arrow(4.78, sy, 4.94, sy, color=VER, lw=1.3)
number(sx + 0.20, sy, 2)
monitor_mark(sx + 0.44, sy)
gate_mark(sx + 0.64, sy)
box(4.95, sy - 0.16, X1 - 4.95, 0.32, "a place nobody named", ec=VER, lw=1.2, ls=(0, (3, 2)),
    color=VER, fontweight="bold")

# the system's own log, read by the review
LY, LH = 2.76, 0.2
box(0.24, LY, 2.62, LH)
t = ax.text(0.31, LY + LH / 2, "System's own log: transcript copy ", ha="left", va="center",
            fontsize=FS, zorder=4)
ax.annotate("“deleted”", xy=(1, 0.5), xycoords=t, ha="left", va="center", fontsize=FS,
            fontweight="bold", color=VER, zorder=4)
box(3.22, LY - 0.01, 1.35, LH + 0.02, "review, after the case", fc=P, ec=INK, lw=0.6, fs=FS)
arrow(3.21, LY + LH / 2, 2.88, LY + LH / 2, lw=0.9)

# the gate's record, fingerprinted to the witness
GY, GH = 2.48, 0.2
box(0.24, GY, 3.55, GH, None, ec=C, lw=1.3)
ax.text(0.31, GY + GH / 2, "Gate's record: handovers A and B; no deletion of this copy",
        ha="left", va="center", fontsize=FS, zorder=4)
WX0 = 4.98
box(WX0, GY - 0.08, X1 - WX0, GH + 0.16, "Witness, outside\nthe vendor", ec=C, lw=1.3, fs=FS)
arrow(3.81, GY + GH / 2, WX0 - 0.02, GY + GH / 2, color=C, lw=1.3)
ax.text(4.25, GY + GH / 2 + 0.04, "fingerprints", ha="center", va="bottom", fontsize=style.NOTE,
        color=INK, zorder=4)

# key to the marks: where each method looks
kx0, ky0 = 4.86, 3.50
ax.text(kx0, ky0, "Where each method looks", ha="left", va="center", fontsize=style.HEAD,
        fontweight="bold")
for j, (mark, label) in enumerate(((review_mark, "review: log, final texts"),
                                   (monitor_mark, "monitor: every message"),
                                   (gate_mark, "gate: handovers, deletions"))):
    yy = ky0 - 0.20 - j * 0.175
    mark(kx0 + 0.07, yy)
    ax.text(kx0 + 0.18, yy, label, ha="left", va="center", fontsize=FS)

# ---------------------------------------------------------------- band b: who notices
BT = 2.20
ax.text(X0, BT, "Who notices?", ha="left", va="center", fontsize=style.HEAD, fontweight="bold")
TEXT_X, CHIP_W = 1.08, 0.80
COLS = ((4.72, 1, "copy kept, log\nsays “deleted”", KEPT),
        (5.88, 2, "transcript sent to\nan unnamed place", SENT))
for cx, n, head, _ in COLS:
    th_ = ax.text(cx + 0.07, BT + 0.005, head, ha="center", va="center", fontsize=style.NOTE,
                  color=VER, linespacing=1.0)
    number(left_edge(th_) - 0.10, BT + 0.005, n)
y = BT - 0.15
for m, reads, why in ROWS:
    nl = len(reads) + 1
    rh = 0.06 + nl * 0.135
    yc = y - rh / 2
    ax.plot([X0, X1], [y, y], color=style.LIGHT, lw=0.6)
    MARK[m](X0 + 0.065, yc)
    ax.text(X0 + 0.19, yc, m, ha="left", va="center", fontsize=style.HEAD, fontweight="bold")
    ty = y - 0.03 - 0.0675
    for line in reads:
        ax.text(TEXT_X, ty, line, ha="left", va="center", fontsize=FS)
        ty -= 0.135
    ax.text(TEXT_X, ty, why, ha="left", va="center", fontsize=FS, style="italic")
    for cx, _, _, col in COLS:
        v = col[m]
        ax.add_patch(Rectangle((cx - CHIP_W / 2, yc - 0.09), CHIP_W, 0.18,
                               fc=style.OUTCOME_FACE[v], ec=style.OUTCOME_EDGE[v],
                               hatch=style.OUTCOME_HATCH[v], lw=0.9))
        ax.text(cx, yc, v, ha="center", va="center", fontsize=FS,
                color=style.OUTCOME_TEXT[v], fontweight="bold",
                bbox=dict(boxstyle="square,pad=0.08", fc="white", ec="none")
                if v == "missed" else None)
    y -= rh
ax.plot([X0, X1], [y, y], color=style.LIGHT, lw=0.6)

# ---------------------------------------------------------------- band c: tiles
CT = y - 0.16
tc_ = ax.text(X0, CT, "The first method to pass each rule", ha="left", va="center",
              fontsize=style.HEAD, fontweight="bold")
ax.annotate("  (no method passed all six; Checked failed rules 4 and 5)", xy=(1, 0.5), xycoords=tc_,
            ha="left", va="center", fontsize=FS)
n, gap = len(TILES), 0.07
tw = (X1 - X0 - gap * (n - 1)) / n
th = CT - 0.12 - 0.08
for i, ((r, short), m) in enumerate(zip(TILES, grades.LEAST)):
    x = X0 + i * (tw + gap)
    fc, tc = style.METHOD[m], style.METHOD_TEXT[m]
    ax.add_patch(Rectangle((x, 0.08), tw, th, fc=fc, ec=fc, lw=0.9, zorder=1))
    for frac, txt, fs, bold in ((0.78, f"Rule {r}", style.HEAD, True), (0.5, short, style.NOTE, False),
                                (0.2, m, style.EMPH, True)):
        ax.text(x + tw / 2, 0.08 + frac * th, txt, ha="center", va="center", fontsize=fs,
                color=tc, fontweight="bold" if bold else "normal", zorder=3)

style.save(fig, "fig1_visit_example")
print("quotations checked against the stored files:", [D1, D2, P1, P2, NOTE_LINE])
