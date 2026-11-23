"""Figure B1: the two flows and where each method looks.

Steps, handovers and deletions from facts/METHOD_FACTS.md, section 1
(wiring/wiring.json): Experiment 1 transcriber -> note_writer -> record,
handovers w2 (transcript) and w3 (note); deletions d3 (transcript at the
transcriber), d4 and d5 (transcript and draft at the note writer), d6 (draft at
the record). Experiment 2 advice_tool -> clinician (plan, AI) -> summary_writer
(note for the patient, AI) -> patient, handovers a2, a3, a4; deletions d8
(answer at the tool), d9 and d10 (plan and note at the summary writer).
What each method reads: METHOD_FACTS.md section 2 and Table 1 of the report.
Test sets: 157 and 413 clean cases, from analysis/final_numbers.json.
"""
import style
import grades
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle, Circle, FancyArrowPatch

FN = grades.FN
N1 = FN["e1_false_alarms"]["1"]["Checked"]["clean_units"]
N2 = FN["e2_false_alarms"]["6"]["Checked"]["clean_units"]
if (N1, N2) != (157, 413):
    raise SystemExit(f"test sets differ: {N1}, {N2}")

style.apply()
W, H = style.WIDTH_IN, 4.5
fig = plt.figure(figsize=(W, H))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis("off")

INK, GREY = style.INK, style.GREY
P, M, C = style.PROMISED, style.MONITORED, style.CHECKED
VENDOR_FILL = "#F2F2F2"
X0, X1 = 0.10, 6.40
FS = style.LABEL


def box(x, y, w, h, text=None, fc="white", ec=INK, lw=0.9, fs=FS, color=INK, r=0.04, z=2, **kw):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fc, ec=ec, lw=lw, zorder=z))
    if text:
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, color=color,
                zorder=z + 1, linespacing=1.0, **kw)


def arrow(x0, y0, x1, y1, color=INK, lw=1.0, z=3):
    ax.add_patch(FancyArrowPatch((x0, y0), (x1, y1), arrowstyle="-|>", mutation_scale=8,
                                 color=color, lw=lw, zorder=z, shrinkA=0, shrinkB=0))


def monitor_mark(x, y, z=5):
    ax.add_patch(Circle((x, y), 0.048, fc=M, ec=INK, lw=0.7, zorder=z))


def gate_mark(x, y, vertical=True, z=5):
    w, h = (0.052, 0.14) if vertical else (0.14, 0.052)
    ax.add_patch(Rectangle((x - w / 2, y - h / 2), w, h, fc=C, ec=INK, lw=0.5, zorder=z))


def review_mark(x, y, z=5):
    ax.add_patch(Rectangle((x - 0.055, y - 0.055), 0.11, 0.11, fc=P, ec=INK, lw=0.5, zorder=z))


# ---------------------------------------------------------------- key
ky = H - 0.12
items = [(review_mark, "review: reads after the case"),
         (monitor_mark, "monitor: reads every message"),
         (gate_mark, "gate: every handover and deletion")]
kx = X0
for mark, label in items:
    mark(kx + 0.06, ky)
    t = ax.text(kx + 0.16, ky, label, ha="left", va="center", fontsize=FS)
    kx = t.get_window_extent(fig.canvas.get_renderer()).transformed(ax.transData.inverted()).x1 + 0.28
ax.add_patch(Rectangle((X0, ky - 0.27), 0.12, 0.10, fc="white", ec=C, lw=1.3))
ax.text(X0 + 0.16, ky - 0.22, "green outline: the gate's record and the witness that holds its fingerprints",
        ha="left", va="center", fontsize=FS)

VX1 = 4.98          # right edge of the vendor's box
RX = 5.10           # right column: rules and test set


def row(top, title, steps, moves, deletes, review_text, rules, test_set, letters=None):
    ax.text(X0, top, title, ha="left", va="center", fontsize=style.HEAD, fontweight="bold")
    vy1, vy0 = top - 0.13, top - 1.90
    ax.add_patch(FancyBboxPatch((X0, vy0), VX1 - X0, vy1 - vy0,
                                boxstyle="round,pad=0,rounding_size=0.06",
                                fc=VENDOR_FILL, ec=GREY, lw=0.9, ls=(0, (4, 2)), zorder=0))
    ax.text(VX1 - 0.12, vy1, " every place the flow touches ", ha="right", va="center", fontsize=style.NOTE,
            color=GREY, style="italic", zorder=1,
            bbox=dict(boxstyle="square,pad=0.04", fc="white", ec="none"))
    n = len(steps)
    sx0, sx1 = X0 + 0.12, VX1 - 0.12
    sw = 0.95 if n == 3 else 0.86
    gap = (sx1 - sx0 - n * sw) / (n - 1)
    sh, sy = 0.40, top - 0.64
    xs = [sx0 + i * (sw + gap) for i in range(n)]
    for x, t in zip(xs, steps):
        box(x, sy, sw, sh, t, fs=FS)
    cy = sy + sh / 2
    for i, what in enumerate(moves):
        xa, xb = xs[i] + sw, xs[i + 1]
        arrow(xa + 0.02, cy, xb - 0.02, cy)
        L_ = xb - xa
        monitor_mark(xa + 0.30 * L_, cy)
        gate_mark(xa + 0.68 * L_, cy)
        mx = (xa + xb) / 2
        if letters:
            lx = mx - 0.04 * len(what) / 2 - 0.06
            ax.add_patch(Circle((lx, cy - 0.17), 0.06, fc="white", ec=INK, lw=0.8, zorder=5))
            ax.text(lx, cy - 0.175, letters[i], ha="center", va="center", fontsize=style.NOTE,
                    fontweight="bold", zorder=6)
            ax.text(lx + 0.09, cy - 0.17, what, ha="left", va="center", fontsize=style.NOTE, color=GREY)
        else:
            ax.text(mx, cy - 0.17, what, ha="center", va="center", fontsize=style.NOTE, color=GREY)
    # deletions: each passes the gate
    dy = sy - 0.50
    for i, d in enumerate(deletes):
        if not d:
            continue
        x = xs[i] + sw / 2
        ax.plot([x, x], [sy, dy + 0.30], color=INK, lw=0.9, zorder=1)
        gate_mark(x, sy - 0.12, vertical=False)
        tm = ax.text(0, 0, d, fontsize=FS, linespacing=1.0)    # width of the text, to size the box
        dw = max(sw, 1.08, tm.get_window_extent(fig.canvas.get_renderer()).width / fig.dpi + 0.14)
        tm.remove()
        box(max(x - dw / 2, X0 + 0.05), dy, dw, 0.30, d, fs=FS, ec=GREY, lw=0.7, r=0.03)
    # the system's own log and the review
    ly, lh = dy - 0.42, 0.30
    box(xs[0], ly, 1.25, lh, "System's own log", fs=FS)
    rx0 = xs[0] + 1.62
    box(rx0, ly, sx1 - rx0, lh, review_text, fc=P, ec=INK, lw=0.6, fs=FS)
    arrow(rx0 - 0.01, ly + lh / 2, xs[0] + 1.27, ly + lh / 2, lw=0.9)
    # the gate's record and the witness
    gy, gh = vy0 + 0.08, 0.22
    box(xs[0], gy, 2.85, gh, "Gate's record: every handover and deletion", ec=C, lw=1.3, fs=FS)
    wy0 = gy - 0.06
    box(RX, wy0, X1 - RX, gh + 0.30, "Witness, outside\nthe vendor", ec=C, lw=1.3, fs=FS)
    arrow(xs[0] + 2.87, gy + gh / 2, RX - 0.02, gy + gh / 2, color=C, lw=1.3)
    ax.text((xs[0] + 2.87 + VX1) / 2 - 0.05, gy + gh / 2 + 0.035, "fingerprints", ha="center",
            va="bottom", fontsize=style.NOTE, zorder=4)
    # rules tested and test set
    ty = vy1 - 0.02
    ax.text(RX, ty, "Rules tested", ha="left", va="center", fontsize=style.HEAD, fontweight="bold")
    for j, (num, words) in enumerate(rules):
        ax.text(RX, ty - 0.17 * (j + 1), f"{num}  {words}", ha="left", va="center", fontsize=FS)
    ty -= 0.17 * (len(rules) + 1) + 0.08
    ax.text(RX, ty, "Test set", ha="left", va="center", fontsize=style.HEAD, fontweight="bold")
    ax.text(RX, ty - 0.10, test_set, ha="left", va="top", fontsize=FS, linespacing=1.1)


row(3.98, "Experiment 1: the patient's words going out",
    ["Transcribing\nservice", "AI note\nwriter", "Medical\nrecord"],
    ["transcript", "note"],
    ["transcript copy\ndeleted by deadline", "transcript and draft\ndeleted by deadline",
     "draft copy\ndeleted by deadline"],
    "review, after the case: reads\nthe log and the final note",
    [(1, "named places only"), (2, "deleted by deadline"), (3, "record of handovers")],
    f"{N1} mock consultations", letters=["A", "B"])

row(1.98, "Experiment 2: advice coming in",
    ["Evidence tool:\nthe answer", "AI writes\nthe plan", "AI writes the\nnote for the\npatient", "Patient"],
    ["answer", "plan", "note"],
    ["answer copy\ndeleted by deadline", None, "plan and note copies\ndeleted by deadline", None],
    "review, after the case: reads the log,\nthe answer and the final note for the patient",
    [(4, "source named"), (5, "certainty unchanged"), (6, "AI's part marked")],
    f"{N2} questions")

style.save(fig, "figB1_two_flows")
