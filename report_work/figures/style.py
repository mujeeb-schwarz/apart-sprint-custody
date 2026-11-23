"""Shared style for the report's figures.

One fixed colour per method and per outcome (Okabe-Ito palette, safe for
colour-blind readers). Outcomes also differ in grey print: blocked is dark,
flagged is light, missed is white with vermillion hatching.

Text is set in Old Standard TT, the face of the report's text (Apart's
template), from the files in fonts/; a machine without them falls back to
DejaVu Serif. Text sizes follow one scale by role: NOTE, LABEL, HEAD, EMPH.
"""
import os
os.environ.setdefault("MPLCONFIGDIR", os.path.join(os.environ.get("TMPDIR", "/tmp"), "mpl"))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

HERE = os.path.dirname(os.path.abspath(__file__))

FONT_DIR = os.path.join(HERE, "fonts")
for _f in ("OldStandardTT-regular.ttf", "OldStandardTT-bold.ttf", "OldStandardTT-italic.ttf"):
    if os.path.exists(os.path.join(FONT_DIR, _f)):
        font_manager.fontManager.addfont(os.path.join(FONT_DIR, _f))

_names = {f.name for f in font_manager.fontManager.ttflist}
SERIF = "Old Standard TT" if "Old Standard TT" in _names else "DejaVu Serif"

# One scale of text sizes, in points at the printed width, by role
NOTE = 7.5     # notes and small annotations
LABEL = 8.5    # tick labels, cell text, labels, legend entries
HEAD = 9.5     # panel titles, row and column headings, legend headings
EMPH = 10.5    # the largest emphasis (method names in Figure 1's tiles, counts in Figure C2)

MIN_PT = NOTE       # smallest text at final size
WIDTH_IN = 6.5      # printed width on US Letter

# Methods
PROMISED = "#CC79A7"   # reddish purple
MONITORED = "#F0E442"  # yellow
CHECKED = "#009E73"    # bluish green
NONE = "#FFFFFF"       # no method passed
METHOD = {"Promised": PROMISED, "Monitored": MONITORED, "Checked": CHECKED}
METHOD_TEXT = {"Promised": "black", "Monitored": "black", "Checked": "white"}

# Outcomes
BLOCKED = "#0072B2"    # dark blue, white text
FLAGGED = "#56B4E9"    # sky blue, black text
MISSED = "#D55E00"     # vermillion, used as hatch and text on white
OUTCOME_FACE = {"blocked": BLOCKED, "flagged": FLAGGED, "missed": "white"}
OUTCOME_HATCH = {"blocked": None, "flagged": None, "missed": "////"}
OUTCOME_EDGE = {"blocked": BLOCKED, "flagged": FLAGGED, "missed": MISSED}
OUTCOME_TEXT = {"blocked": "white", "flagged": "black", "missed": MISSED}

INK = "#222222"
GREY = "#6E6E6E"
LIGHT = "#BDBDBD"


def apply():
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": [SERIF, "DejaVu Serif"],
        "font.size": LABEL,
        "axes.titlesize": HEAD,
        "axes.labelsize": LABEL,
        "xtick.labelsize": LABEL,
        "ytick.labelsize": LABEL,
        "axes.edgecolor": INK,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": INK,
        "ytick.color": INK,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "savefig.facecolor": "white",
        "hatch.linewidth": 0.8,
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def check(fig):
    """Print the figure's size, the text sizes and faces used, and any text that
    leaves the figure, overlaps other text, or runs past the box it sits in.
    Measures are in points at printed size."""
    from matplotlib.text import Text
    from matplotlib.patches import Rectangle, FancyBboxPatch
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    k = 72.0 / fig.dpi
    w_in, h_in = fig.get_size_inches()
    FW, FH = w_in * 72, h_in * 72
    hidden = set()      # tick labels outside the axis limits are not drawn
    for ax in fig.axes:
        for axis in (ax.xaxis, ax.yaxis):
            lo, hi = sorted(axis.get_view_interval())
            eps = (hi - lo) * 1e-6
            for tk in axis.get_major_ticks() + axis.get_minor_ticks():
                loc = tk.get_loc()
                if loc is not None and not (lo - eps <= loc <= hi + eps):
                    hidden |= {id(tk.label1), id(tk.label2)}
    texts = [t for t in fig.findobj(Text)
             if t.get_visible() and t.get_text().strip() and id(t) not in hidden]
    ext = []
    for t in texts:
        b = t.get_window_extent(r)
        ext.append((t, b.x0 * k, b.y0 * k, b.x1 * k, b.y1 * k))
    sizes = sorted({round(t.get_fontsize(), 2) for t in texts})
    faces = sorted({t.get_fontname() for t in texts})
    print(f"size {w_in:.2f} x {h_in:.2f} in; text sizes {sizes} pt; faces {faces}")

    def nm(t):
        return repr(t.get_text().replace("\n", "/")[:38])
    for t, x0, y0, x1, y1 in ext:
        if x0 < -0.3 or y0 < -0.3 or x1 > FW + 0.3 or y1 > FH + 0.3:
            print(f"  OUTSIDE figure: {nm(t)} x {x0:.1f}..{x1:.1f} y {y0:.1f}..{y1:.1f} of {FW:.0f} x {FH:.0f}")
    for i in range(len(ext)):
        for j in range(i + 1, len(ext)):
            a, b = ext[i], ext[j]
            ow = min(a[3], b[3]) - max(a[1], b[1])
            oh = min(a[4], b[4]) - max(a[2], b[2])
            if ow > 1.0 and oh > 1.0:
                print(f"  OVERLAP {ow:.1f} x {oh:.1f}: {nm(a[0])} and {nm(b[0])}")
    skip = {id(fig.patch)} | {id(ax.patch) for ax in fig.axes}
    skip |= {id(t.get_bbox_patch()) for t in texts if t.get_bbox_patch() is not None}
    boxes = []
    for p in fig.findobj(lambda o: isinstance(o, (Rectangle, FancyBboxPatch))):
        if id(p) in skip or not p.get_visible():
            continue
        b = p.get_window_extent(r)
        if b.width > 1 and b.height > 1:
            boxes.append((b.x0 * k, b.y0 * k, b.x1 * k, b.y1 * k))
    for t, x0, y0, x1, y1 in ext:
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        inside = [bx for bx in boxes if bx[0] <= cx <= bx[2] and bx[1] <= cy <= bx[3]]
        if not inside:
            continue
        bx = min(inside, key=lambda q: (q[2] - q[0]) * (q[3] - q[1]))
        dl, dr = bx[0] - x0, x1 - bx[2]
        if dl > 0.3 or dr > 0.3:
            print(f"  RUNS PAST its box by {max(dl, dr):.1f}: {nm(t)}")
        elif min(x0 - bx[0], bx[2] - x1) < 2.0 and (bx[2] - bx[0]) < FW * 0.6:
            print(f"  TIGHT in its box ({min(x0 - bx[0], bx[2] - x1):.1f} pt to spare): {nm(t)}")
        for q in boxes:
            if q in inside:
                continue
            ow = min(x1, q[2]) - max(x0, q[0])
            oh = min(y1, q[3]) - max(y0, q[1])
            if ow > 1.0 and oh > 1.0:
                print(f"  HITS a box it is not in ({ow:.1f} x {oh:.1f}): {nm(t)}")


def save(fig, name):
    check(fig)
    for ext, kw in (("png", {"dpi": 300}), ("pdf", {})):
        fig.savefig(os.path.join(HERE, f"{name}.{ext}"), **kw)
