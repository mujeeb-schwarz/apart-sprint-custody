#!/usr/bin/env python3
"""
build_report.py: turn a Markdown report into a Word file on Apart's template.

    python3 build_report.py REPORT.md --out REPORT.docx [--template T.docx]

The template is opened as the starting document, so page size, margins, fonts,
styles, footnote and title block are Apart's. The program:
  1. fills the title block (title, authors and affiliations, abstract, and the
     event/date in the title footnote) from the header at the top of the .md;
  2. deletes the instruction box and all of the template's sample text;
  3. appends the report body, written with the template's own styles and the
     same direct formatting the template uses (Old Standard TT, 11 pt body).

Anything in the Markdown that the program does not understand stops the build
with an error that names the line. Nothing is guessed.

To adjust the look, change the constants in the block "LOOK" below.
"""

import argparse
import copy
import math
import os
import re
import sys

import docx
from docx.enum.text import WD_BREAK
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Emu, Inches

HERE = os.path.dirname(os.path.abspath(__file__))
# The template is Apart Research's own and is not included in this repository; put a copy at the path below or pass --template.
DEFAULT_TEMPLATE = os.path.join(HERE, "template", "apart_template.docx")

# ----------------------------------------------------------------------------
# LOOK. Every value here was read from the template unless marked "ours".
# Sizes are in points; spacing values are in twips (1 pt = 20 twips).
# ----------------------------------------------------------------------------
FONT = "Old Standard TT"          # template: every run sets this font directly
BODY_PT = 11                      # template: document default size (sz 22)
TEXT_WIDTH_TWIPS = 9360           # 8.5 in page - 2 x 1 in margins = 6.5 in
PARA_AFTER = 40                  # ours since 15 Nov 13:50: 7 pt, to fit the page cap. The template separates paragraphs with one empty
                                  # 11 pt line (11 x 1.15 = 12.65 pt); we use the
                                  # same gap as space-after instead of empty lines

# Markdown heading level -> (template style id, size, bold, colour, before, after, line)
HEADINGS = {
    2: ("Heading2", 14, True, None, 120, 0, 360),     # template "1. Introduction"
    3: ("Heading3", 13, True, "000000", 110, 50, None),  # template "Limitations"
    4: ("Heading4", 12, True, "000000", 160, 40, None),  # ours: template has no H4 in use;
                                                         # one step down from H3
}

TABLE_PT = 9                      # ours: table cells, two points under the body
TABLE_BORDER_SZ = 8               # template: its own tables use 1 pt black lines
TABLE_INNER_COLOR = "BFBFBF"      # ours: light lines between rows
SHADE_PASS, SHADE_FAIL = "DDEFD3", "FBE5D6"   # ours: light green for pass, light orange for fail
TABLE_KEEP_TOGETHER_MAX_ROWS = 8  # ours: tables up to this many rows never split
CAPTION_PT = 10                   # ours: "Table N." / "Figure N." captions
REF_PT = 10                       # ours: references, one point under the body
REF_IND_LEFT, REF_HANGING = 900, 540  # label starts 360 in, as the template's list
CODE_FONT, CODE_PT = "Courier New", 10   # ours: the template has no code style
LINK_COLOR = "1155CC"             # Google Docs' link blue, as in the template's exports
FIGURE_MAX_HEIGHT_IN = 7.5        # ours: a figure never gets taller than this

# Numbering definitions that exist in the template's numbering.xml
NUM_BULLET = "3"          # numId 3 -> abstractNum 3: "-" bullets, nested "-" at level 1
ABS_DECIMAL = "5"         # abstractNum 5: "1." at level 0, "-" at level 1
ABS_LETTER = "2"          # abstractNum 2: "(a)"; used for a numbered list nested in a list
LIST_IND = {0: (720, 360), 1: (1440, 360)}   # template: left and hanging per level


class ReportError(Exception):
    pass


# ----------------------------------------------------------------------------
# Small XML helpers
# ----------------------------------------------------------------------------
def el(tag, **attrs):
    """Make an OOXML element: el('w:sz', val='22')."""
    e = OxmlElement(tag)
    for k, v in attrs.items():
        e.set(qn("w:" + k), str(v))
    return e


def fonts_el(name):
    return el("w:rFonts", ascii=name, hAnsi=name, cs=name, eastAsia=name)


def run_props(size, bold=False, italic=False, code=False, color=None, underline=False):
    """rPr for one run, children in schema order."""
    rpr = OxmlElement("w:rPr")
    rpr.append(fonts_el(CODE_FONT if code else FONT))
    if bold:
        rpr.append(el("w:b", val="1")); rpr.append(el("w:bCs", val="1"))
    if italic:
        rpr.append(el("w:i", val="1")); rpr.append(el("w:iCs", val="1"))
    if color:
        rpr.append(el("w:color", val=color))
    sz = CODE_PT if code and size >= BODY_PT else size
    rpr.append(el("w:sz", val=int(sz * 2))); rpr.append(el("w:szCs", val=int(sz * 2)))
    if underline:
        rpr.append(el("w:u", val="single"))
    return rpr


def make_run(text, size, **fmt):
    """A w:r element. Newlines in text become line breaks."""
    r = OxmlElement("w:r")
    r.append(run_props(size, **fmt))
    for i, piece in enumerate(text.split("\n")):
        if i:
            r.append(OxmlElement("w:br"))
        if piece:
            t = OxmlElement("w:t")
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
            t.text = piece
            r.append(t)
    return r


def set_para_props(p, style=None, keep_next=False, num=None, before=None, after=None,
                   line=None, ind=None, jc=None, size=BODY_PT, bold_mark=False):
    """Write pPr for paragraph p (python-docx Paragraph), children in schema order."""
    old = p._p.pPr
    if old is not None:
        p._p.remove(old)
    ppr = OxmlElement("w:pPr")
    if style:
        ppr.append(el("w:pStyle", val=style))
    if keep_next:
        ppr.append(el("w:keepNext", val="1"))
    if num:
        numpr = OxmlElement("w:numPr")
        numpr.append(el("w:ilvl", val=num[1])); numpr.append(el("w:numId", val=num[0]))
        ppr.append(numpr)
    if before is not None or after is not None or line is not None:
        sp = OxmlElement("w:spacing")
        if after is not None: sp.set(qn("w:after"), str(after))
        if before is not None: sp.set(qn("w:before"), str(before))
        if line is not None:
            sp.set(qn("w:line"), str(line)); sp.set(qn("w:lineRule"), "auto")
        ppr.append(sp)
    if ind:
        ppr.append(el("w:ind", left=ind[0], hanging=ind[1]))
    if jc:
        ppr.append(el("w:jc", val=jc))
    ppr.append(run_props(size, bold=bold_mark))   # paragraph-mark formatting
    p._p.insert(0, ppr)


# ----------------------------------------------------------------------------
# Inline Markdown: **bold**, *italic*, `code`, [text](url), bare URLs, <br>
# ----------------------------------------------------------------------------
ESCAPES = {"\\*": "", "\\_": "", "\\[": "", "\\]": "",
           "\\`": "", "\\|": "", "\\<": ""}
UNESCAPE = {v: k[1] for k, v in ESCAPES.items()}

INLINE = re.compile(r"""
   (?P<code>`[^`]+`)
 | (?P<link>\[(?P<ltext>[^\]]+)\]\((?P<lurl>[^)\s]+)\))
 | (?P<bi>\*\*\*(?P<bitext>.+?)\*\*\*)
 | (?P<bold>\*\*(?P<btext>.+?)\*\*)
 | (?P<ital>(?<!\*)\*(?P<itext>[^*\s](?:[^*]*?[^*\s])?)\*(?!\*))
 | (?P<br><br\s*/?>)
 | <(?P<aurl>https?://[^>\s]+)>
 | (?P<url>https?://[^\s<>]*[^\s<>.,;:)\]])
 | (?P<html></?[A-Za-z][^>]*>)
""", re.X)


def escape(text):
    for k, v in ESCAPES.items():
        text = text.replace(k, v)
    return text


def unescape(text):
    for k, v in UNESCAPE.items():
        text = text.replace(k, v)
    return text


def parse_inline(text, where, bold=False, italic=False):
    """Return a list of pieces: dict(text, bold, italic, code, url)."""
    out, pos = [], 0
    for m in INLINE.finditer(text):
        if m.start() > pos:
            out.append(dict(text=text[pos:m.start()], bold=bold, italic=italic, code=False, url=None))
        if m.group("code"):
            out.append(dict(text=m.group("code")[1:-1], bold=bold, italic=italic, code=True, url=None))
        elif m.group("link"):
            url = unescape(m.group("lurl"))
            if not re.match(r"(https?://|mailto:)", url):
                raise ReportError(f"{where}: link target must start with http(s):// or mailto: -> {url}")
            for piece in parse_inline(m.group("ltext"), where, bold, italic):
                piece["url"] = url
                out.append(piece)
        elif m.group("bi"):
            out += parse_inline(m.group("bitext"), where, True, True)
        elif m.group("bold"):
            out += parse_inline(m.group("btext"), where, True, italic)
        elif m.group("ital"):
            out += parse_inline(m.group("itext"), where, bold, True)
        elif m.group("br"):
            out.append(dict(text="\n", bold=bold, italic=italic, code=False, url=None))
        elif m.group("aurl") or m.group("url"):
            u = m.group("aurl") or m.group("url")
            out.append(dict(text=u, bold=bold, italic=italic, code=False, url=u))
        elif m.group("html"):
            raise ReportError(f"{where}: HTML tag not supported: {m.group('html')}")
        pos = m.end()
    if pos < len(text):
        out.append(dict(text=text[pos:], bold=bold, italic=italic, code=False, url=None))
    for piece in out:
        if "**" in piece["text"] or "`" in piece["text"]:
            raise ReportError(f"{where}: unbalanced ** or ` in: {text.strip()[:60]}")
        piece["text"] = unescape(piece["text"])
    return out


def add_inline(doc, p, text, where, size=BODY_PT, bold=False, italic=False):
    """Append the inline Markdown `text` to paragraph p as runs and hyperlinks."""
    for piece in parse_inline(escape(text), where, bold, italic):
        fmt = dict(bold=piece["bold"], italic=piece["italic"], code=piece["code"])
        if piece["url"]:
            r_id = doc.part.relate_to(piece["url"], RT.HYPERLINK, is_external=True)
            h = OxmlElement("w:hyperlink")
            h.set(qn("r:id"), r_id)
            h.append(make_run(piece["text"], size, color=LINK_COLOR, underline=True, **fmt))
            p._p.append(h)
        else:
            p._p.append(make_run(piece["text"], size, **fmt))


# ----------------------------------------------------------------------------
# Block parser: Markdown lines -> list of blocks
# ----------------------------------------------------------------------------
LIST_ITEM = re.compile(r"^( *)([-*+]|\d+\.)\s+(.*)$")
HEADING = re.compile(r"^(#+)\s+(.*?)\s*#*\s*$")
FIGURE = re.compile(r"^!\[(?P<alt>.*)\]\((?P<path>[^)]+)\)\s*$")
DIRECTIVE = re.compile(r"^<!--\s*([A-Za-z]+)\s*:?\s*(.*?)\s*-->\s*$")
REF_ENTRY = re.compile(r"^(\[\d+\]|\d+\.)\s+(.*)$")


def parse_header(lines):
    if not lines or lines[0].strip() != "---":
        raise ReportError("line 1: the file must start with a header between two lines of ---")
    meta, i = {}, 1
    while i < len(lines) and lines[i].strip() != "---":
        line = lines[i]
        if line.strip():
            m = re.match(r"^([A-Za-z_]+)\s*:\s*(.*)$", line)
            if not m:
                raise ReportError(f"line {i+1}: header lines must read 'key: value'")
            meta[m.group(1).lower()] = m.group(2).strip().strip('"').strip("'")
        i += 1
    if i == len(lines):
        raise ReportError("header: no closing --- line")
    for key in ("title", "authors", "affiliations"):
        if not meta.get(key):
            raise ReportError(f"header: '{key}' is required")
    allowed = {"title", "authors", "affiliations", "event", "date"}
    extra = set(meta) - allowed
    if extra:
        raise ReportError(f"header: unknown keys {sorted(extra)}; allowed: {sorted(allowed)}")
    return meta, i + 1


def parse_blocks(lines, start):
    """Each block is a dict with 'kind' and a 'line' number for error messages."""
    blocks, i, n = [], start, len(lines)
    in_refs = False

    def is_block_start(s):
        return (not s.strip() or HEADING.match(s) or s.lstrip().startswith("|")
                or FIGURE.match(s.strip()) or s.strip().startswith("<!--")
                or LIST_ITEM.match(s))

    while i < n:
        raw = lines[i]
        s = raw.strip()
        ln = i + 1
        if not s:
            i += 1; continue

        # comments and directives (a comment may run over several lines)
        if s.startswith("<!--"):
            j = i
            while "-->" not in lines[j]:
                j += 1
                if j == n:
                    raise ReportError(f"line {ln}: comment never closed with -->")
            text = " ".join(l.strip() for l in lines[i:j + 1])
            m = DIRECTIVE.match(text)
            key = m.group(1).lower() if m else ""
            if key == "pagebreak":
                blocks.append(dict(kind="pagebreak", line=ln))
            elif key == "widths":
                try:
                    w = [float(x) for x in m.group(2).split(",")]
                except ValueError:
                    raise ReportError(f"line {ln}: widths must be numbers, e.g. <!-- widths: 20,30,50 -->")
                blocks.append(dict(kind="widths", values=w, line=ln))
            elif key == "width":
                try:
                    w = float(m.group(2))
                except ValueError:
                    raise ReportError(f"line {ln}: width must be a number, e.g. <!-- width: 80 -->")
                if not 10 <= w <= 100:
                    raise ReportError(f"line {ln}: figure width must be 10 to 100 (percent)")
                blocks.append(dict(kind="width", value=w, line=ln))
            elif m and re.match(r"^<!--\s*[A-Za-z]+\s*:", text):
                raise ReportError(f"line {ln}: unknown directive '{key}' (known: pagebreak, widths, width)")
            # any other comment is a note to ourselves and is skipped
            i = j + 1; continue

        m = HEADING.match(s)
        if m:
            level = len(m.group(1))
            if level not in HEADINGS:
                raise ReportError(f"line {ln}: only ##, ### and #### headings are allowed (the title goes in the header)")
            title = m.group(2)
            if level == 2:
                in_refs = title.strip().lower() == "references"
            blocks.append(dict(kind="heading", level=level, text=title, line=ln))
            i += 1; continue

        if s.startswith("```") or s.startswith(">") or re.match(r"^(-{3,}|\*{3,}|_{3,})$", s):
            raise ReportError(f"line {ln}: code blocks, block quotes and horizontal rules are not supported")

        if s.startswith("|"):
            rows = []
            while i < n and lines[i].strip().startswith("|"):
                rows.append((i + 1, lines[i].strip())); i += 1
            blocks.append(dict(kind="table", rows=rows, line=ln))
            continue

        if s.startswith("!["):
            m = FIGURE.match(s)
            if not m:
                raise ReportError(f"line {ln}: a figure must read ![Figure N. caption](path.png) on its own line")
            blocks.append(dict(kind="figure", alt=m.group("alt"), path=m.group("path").strip(), line=ln))
            i += 1; continue

        if in_refs:
            m = REF_ENTRY.match(s)
            if not m:
                raise ReportError(f"line {ln}: each reference must start with '1.' or '[1]'")
            text = m.group(2); i += 1
            while i < n and lines[i].strip() and not REF_ENTRY.match(lines[i].strip()) \
                    and not is_block_start(lines[i]):
                text += " " + lines[i].strip(); i += 1
            blocks.append(dict(kind="ref", label=m.group(1), text=text, line=ln))
            continue

        if LIST_ITEM.match(raw):
            items = []
            while i < n and (LIST_ITEM.match(lines[i]) or
                             (lines[i].strip() and lines[i].startswith(" ") and items)):
                mm = LIST_ITEM.match(lines[i])
                if mm:
                    indent = len(mm.group(1))
                    if indent == 0:
                        level = 0
                    elif 2 <= indent <= 4:
                        level = 1
                    else:
                        raise ReportError(f"line {i+1}: lists allow one level of nesting (indent 2 to 4 spaces)")
                    if level == 1 and not items:
                        raise ReportError(f"line {i+1}: a list cannot start indented")
                    ordered = mm.group(2)[0].isdigit()
                    items.append(dict(level=level, ordered=ordered, text=mm.group(3), line=i + 1))
                else:  # continuation line of the previous item
                    items[-1]["text"] += " " + lines[i].strip()
                i += 1
            blocks.append(dict(kind="list", items=items, line=ln))
            continue

        # paragraph: consecutive lines up to the next blank line or block start
        text = s; i += 1
        while i < n and not is_block_start(lines[i]):
            text += " " + lines[i].strip(); i += 1
        blocks.append(dict(kind="para", text=text, line=ln))
    return blocks


# ----------------------------------------------------------------------------
# Template surgery: title block, footnote, instruction box
# ----------------------------------------------------------------------------
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def text_of(e):
    return "".join(t.text or "" for t in e.iter(W + "t"))


def fill_title_block(doc, meta, abstract_text):
    body = doc.element.body
    tables = [c for c in body if c.tag == W + "tbl"]
    if len(tables) < 2:
        raise ReportError("template: expected the title table and the instruction box")
    title_tbl, box_tbl = tables[0], tables[1]

    # 1. Title: replace the text "PROJECT TITLE", keep the footnote mark after it
    t_nodes = [t for t in title_tbl.iter(W + "t") if t.text == "PROJECT TITLE"]
    if not t_nodes:
        raise ReportError("template: 'PROJECT TITLE' not found in the title table")
    t_nodes[0].text = meta["title"]

    # 2. Authors: the template holds a nested 3 x 2 grid of "Author name N / Affiliation".
    #    We rebuild that grid with one cell per author, centred, same cell formatting.
    authors = split_list(meta["authors"])
    affils = [a.strip() for a in meta["affiliations"].split(";") if a.strip()]
    if len(affils) == 1:
        affils = affils * len(authors)
    if len(affils) != len(authors):
        raise ReportError(f"header: {len(authors)} authors but {len(affils)} affiliations "
                          "(give one affiliation for all, or one per author separated by ;)")
    grid = [t for t in title_tbl.iter(W + "tbl") if "Author name 1" in text_of(t)][-1]
    proto_tc = copy.deepcopy(grid.find(W + "tr").find(W + "tc"))
    proto_tr = copy.deepcopy(grid.find(W + "tr"))
    for tr in grid.findall(W + "tr"):
        grid.remove(tr)
    cols = len(authors) if len(authors) <= 3 else (2 if len(authors) == 4 else 3)
    width = 7185  # template: the width of the cell that holds the grid
    tblw = grid.find(W + "tblPr").find(W + "tblW")
    tblw.set(qn("w:w"), str(width))
    tgrid = grid.find(W + "tblGrid")
    for g in list(tgrid):
        tgrid.remove(g)
    for _ in range(cols):
        tgrid.append(el("w:gridCol", w=width // cols))
    for r in range(math.ceil(len(authors) / cols)):
        tr = copy.deepcopy(proto_tr)
        for tc in tr.findall(W + "tc"):
            tr.remove(tc)
        for c in range(cols):
            k = r * cols + c
            tc = copy.deepcopy(proto_tc)
            tcpr = tc.find(W + "tcPr")
            for old in tcpr.findall(W + "tcW"):
                tcpr.remove(old)
            tcpr.insert(0, el("w:tcW", w=width // cols, type="dxa"))
            p = tc.find(W + "p")
            for run in p.findall(W + "r"):
                p.remove(run)
            if k < len(authors):
                p.append(make_run(authors[k] + "\n" + affils[k], BODY_PT))
            tr.append(tc)
        grid.append(tr)

    # 3. Abstract: the justified, indented paragraph in the box under "Abstract".
    #    The template sets its guidance text in italics; the real abstract is upright.
    abs_p = [p for p in title_tbl.iter(W + "p") if text_of(p).startswith("Summarize your project")]
    if not abs_p:
        raise ReportError("template: abstract placeholder not found")
    abs_p = abs_p[0]
    for child in list(abs_p):
        if child.tag != W + "pPr":
            abs_p.remove(child)
    for u in abs_p.iter(W + "u"):          # the placeholder's paragraph mark is underlined
        u.getparent().remove(u)
    from docx.text.paragraph import Paragraph
    add_inline(doc, Paragraph(abs_p, doc._body), abstract_text, "abstract")

    # 4. Remove the instruction box and every sample paragraph after it.
    for child in list(body):
        if child is title_tbl or child.tag == W + "sectPr":
            continue
        if body.index(child) > body.index(title_tbl):
            body.remove(child)
    # ...and the links those deleted paragraphs pointed to (the evaluation rubric).
    used = {h.get(qn("r:id")) for h in body.iter(W + "hyperlink")}
    for r_id, rel in list(doc.part.rels.items()):
        if rel.reltype == RT.HYPERLINK and r_id not in used:
            doc.part.rels.pop(r_id)


def split_list(s):
    """Authors on one line, separated by ';' (or by ',' if there is no ';')."""
    sep = ";" if ";" in s else ","
    return [a.strip() for a in s.split(sep) if a.strip()]


def fill_footnote(doc, meta):
    """The title footnote reads 'Research conducted at the <event>, <date>'.
    Header keys 'event' and 'date' replace those two pieces; the event keeps its link."""
    if not (meta.get("event") or meta.get("date")):
        return
    from lxml import etree
    for rel in doc.part.rels.values():
        if rel.reltype.endswith("/footnotes"):
            part = rel.target_part
            root = part.element if hasattr(part, "element") else etree.fromstring(part.blob)
            for t in root.iter(W + "t"):
                if meta.get("event") and t.text == "AI x Epistemics Research Sprint":
                    t.text = meta["event"]
                if meta.get("date") and t.text == ", November 2026":
                    t.text = ", " + meta["date"]
            if not hasattr(part, "element"):
                part._blob = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            return
    raise ReportError("template: footnotes part not found")


# ----------------------------------------------------------------------------
# Writers for each block kind
# ----------------------------------------------------------------------------
class Writer:
    def __init__(self, doc, md_dir):
        self.doc, self.md_dir = doc, md_dir
        numbering = doc.part.numbering_part.element
        self.numbering = numbering
        self.next_num = max(int(n.get(qn("w:numId"))) for n in numbering.findall(qn("w:num"))) + 1

    def new_num(self, abstract_id):
        """A fresh w:num so that each numbered list starts again at 1."""
        num = el("w:num", numId=self.next_num)
        num.append(el("w:abstractNumId", val=abstract_id))
        lo = el("w:lvlOverride", ilvl=0)
        lo.append(el("w:startOverride", val=1))
        num.append(lo)
        self.numbering.append(num)
        self.next_num += 1
        return str(self.next_num - 1)

    def heading(self, b, page_break=False):
        style, size, bold, color, before, after, line = HEADINGS[b["level"]]
        p = self.doc.add_paragraph()
        set_para_props(p, style=style, keep_next=True, before=before, after=after,
                       line=line, size=size, bold_mark=bold)
        if page_break:
            p._p.pPr.insert(2, el("w:pageBreakBefore", val="1"))
        for piece in parse_inline(escape(b["text"]), f"line {b['line']}", bold=bold):
            p._p.append(make_run(piece["text"], size, bold=piece["bold"], italic=piece["italic"],
                                 code=piece["code"], color=color))

    def para(self, b, keep_next=False):
        p = self.doc.add_paragraph()
        set_para_props(p, after=PARA_AFTER, keep_next=keep_next)   # a lead-in line stays with its list
        add_inline(self.doc, p, b["text"], f"line {b['line']}")

    def pagebreak(self, b):
        p = self.doc.add_paragraph()
        set_para_props(p, after=0)
        p.add_run().add_break(WD_BREAK.PAGE)

    def list(self, b):
        top_num = NUM_BULLET if not b["items"][0]["ordered"] else self.new_num(ABS_DECIMAL)
        sub_num = None
        for k, item in enumerate(b["items"]):
            last = k == len(b["items"]) - 1
            if item["level"] == 0:
                if item["ordered"] != b["items"][0]["ordered"]:
                    raise ReportError(f"line {item['line']}: a list mixes bullets and numbers at the top level")
                num, ind, sub_num = (top_num, "0"), LIST_IND[0], None
            elif item["ordered"]:      # numbered list inside a list: (a), (b), ...
                if sub_num is None:
                    sub_num = self.new_num(ABS_LETTER)
                num, ind = (sub_num, "0"), LIST_IND[1]
            else:                      # bullets inside a list: the template's level-1 "-"
                num, ind = (top_num, "1"), LIST_IND[1]
            p = self.doc.add_paragraph()
            set_para_props(p, num=num, ind=ind, after=PARA_AFTER if last else 0)
            add_inline(self.doc, p, item["text"], f"line {item['line']}")

    def caption(self, text, where, center=False, keep_next=False, before=120, after=80):
        m = re.match(r"^((?:Table|Figure) [A-Z]?\d+\.)\s*(.*)$", text)
        p = self.doc.add_paragraph()
        set_para_props(p, keep_next=keep_next, before=before, after=after, line=240,
                       jc="center" if center else None, size=CAPTION_PT)
        p._p.append(make_run(m.group(1) + " ", CAPTION_PT, bold=True))
        add_inline(self.doc, p, m.group(2), where, size=CAPTION_PT)

    def table(self, b, caption=None, widths=None):
        where = f"line {b['line']}"
        rows = [split_row(t, f"line {ln}") for ln, t in b["rows"]]
        if len(rows) < 2 or not all(re.match(r"^:?-{3,}:?$", c.strip()) for c in rows[1]):
            raise ReportError(f"{where}: a table needs a header row, then a |---|---| row")
        header, body_rows = rows[0], rows[2:]
        ncols = len(header)
        for (ln, _), r in zip(b["rows"][2:], body_rows):
            if len(r) != ncols:
                raise ReportError(f"line {ln}: row has {len(r)} cells, header has {ncols}")
        if not body_rows:
            raise ReportError(f"{where}: a table needs at least one row under the header")

        if widths:
            if len(widths) != ncols:
                raise ReportError(f"{where}: widths directive has {len(widths)} values for {ncols} columns")
            if not 98 <= sum(widths) <= 102:
                raise ReportError(f"{where}: widths must add up to 100 (they add up to {sum(widths):g})")
            pct = widths
        else:  # ours: share the width by the longest text in each column, within limits
            longest = [max(min(len(r[c]), 40) for r in [header] + body_rows) for c in range(ncols)]
            longest = [max(x, 6) for x in longest]
            pct = [100 * x / sum(longest) for x in longest]
        twips = [int(TEXT_WIDTH_TWIPS * x / 100) for x in pct]

        if caption:
            self.caption(caption, where, keep_next=True)

        tbl = self.doc.add_table(rows=len(body_rows) + 1, cols=ncols)
        tblpr = tbl._tbl.tblPr
        for old in tblpr.findall(qn("w:tblW")):
            tblpr.remove(old)
        tblpr.append(el("w:tblW", w=sum(twips), type="dxa"))
        tblpr.append(el("w:jc", val="center"))
        borders = OxmlElement("w:tblBorders")
        # ours since 15 Nov 16:30: rules above and below, light lines between rows, no vertical lines
        for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
            if side in ("top", "bottom"):
                borders.append(el("w:" + side, val="single", sz=TABLE_BORDER_SZ, space=0, color="000000"))
            elif side == "insideH":
                borders.append(el("w:" + side, val="single", sz=4, space=0, color=TABLE_INNER_COLOR))
            else:
                borders.append(el("w:" + side, val="nil"))
        tblpr.append(borders)
        tblpr.append(el("w:tblLayout", type="fixed"))
        mar = OxmlElement("w:tblCellMar")
        for side, v in (("top", 40), ("left", 80), ("bottom", 40), ("right", 80)):
            mar.append(el("w:" + side, w=v, type="dxa"))
        tblpr.append(mar)
        # schema order inside tblPr: tblStyle, ..., tblW, jc, ..., tblBorders, ..., tblLayout, tblCellMar, tblLook
        look = tblpr.find(qn("w:tblLook"))
        if look is not None:
            tblpr.remove(look); tblpr.append(look)
        for g, w in zip(tbl._tbl.tblGrid.findall(qn("w:gridCol")), twips):
            g.set(qn("w:w"), str(w))

        keep = len(body_rows) + 1 <= TABLE_KEEP_TOGETHER_MAX_ROWS
        for r_i, (row, cells) in enumerate(zip(tbl.rows, [header] + body_rows)):
            trpr = row._tr.get_or_add_trPr()
            trpr.append(el("w:cantSplit", val="1"))      # a row never breaks across pages
            if r_i == 0:
                trpr.append(el("w:tblHeader", val="1"))  # header row repeats on a new page
            last_row = r_i == len(body_rows)
            for c_i, (cell, text) in enumerate(zip(row.cells, cells)):
                cell.width = Emu(twips[c_i] * 635)
                tcpr = cell._tc.get_or_add_tcPr()
                if r_i == 0:                                 # a black rule under the header row
                    tcb = OxmlElement("w:tcBorders")
                    tcb.append(el("w:bottom", val="single", sz=6, space=0, color="000000"))
                    tcpr.append(tcb)
                plain = text.strip()
                fill = None                                  # ours: a results cell that opens with its grade is tinted
                if plain.startswith("**pass**"):
                    fill = SHADE_PASS
                elif plain == "fail" or plain.startswith("fail<br>"):
                    fill = SHADE_FAIL
                if fill:
                    tcpr.append(el("w:shd", val="clear", color="auto", fill=fill))
                p = cell.paragraphs[0]
                set_para_props(p, keep_next=keep and not last_row, before=0, after=0,
                               line=240, size=TABLE_PT)
                add_inline(self.doc, p, text.strip(), f"line {b['rows'][r_i if r_i == 0 else r_i + 1][0]}",
                           size=TABLE_PT, bold=(r_i == 0))
        spacer = self.doc.add_paragraph()      # a small gap under the table
        set_para_props(spacer, before=0, after=120, line=240, size=6)

    def figure(self, b, width_pct=None):
        where = f"line {b['line']}"
        m = re.match(r"^Figure [A-Z]?\d+\.\s+\S", b["alt"])
        if not m:
            raise ReportError(f"{where}: figure text must start 'Figure N. ' and a caption")
        path = b["path"]
        if not os.path.isabs(path):
            path = os.path.join(self.md_dir, path)
        if not os.path.isfile(path):
            raise ReportError(f"{where}: image not found: {path}")
        from docx.image.image import Image
        img = Image.from_file(path)
        width_in = 6.5 * (width_pct or 100) / 100
        height_in = width_in * img.px_height / img.px_width
        if height_in > FIGURE_MAX_HEIGHT_IN:
            width_in *= FIGURE_MAX_HEIGHT_IN / height_in
        p = self.doc.add_paragraph()
        set_para_props(p, keep_next=True, before=120, after=0, line=240, jc="center")
        p.add_run().add_picture(path, width=Inches(width_in))
        inline = p._p.find(".//" + qn("wp:inline"))
        if inline is not None:                 # no extra distance, so that figures line up with the text block
            for a in ("distT", "distB", "distL", "distR"):
                inline.set(a, "0")
        self.caption(b["alt"], where, center=False, before=60, after=120)

    def ref(self, b):
        p = self.doc.add_paragraph()
        set_para_props(p, ind=(REF_IND_LEFT, REF_HANGING), before=0, after=40, size=REF_PT)
        p._p.append(make_run(b["label"], REF_PT))
        p._p.append(make_run("", REF_PT)); p._p[-1].append(OxmlElement("w:tab"))
        add_inline(self.doc, p, b["text"], f"line {b['line']}", size=REF_PT)



def add_page_numbers(doc):
    """Ours since 15 Nov 20:00: 'Page N of M' centred in the footer of every page."""
    def fld(code):
        f = OxmlElement("w:fldSimple")
        f.set(qn("w:instr"), " %s " % code)
        f.append(make_run("1", REF_PT))
        return f
    for section in doc.sections:
        footer = section.footer
        footer.is_linked_to_previous = False
        par = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        for child in list(par._p):
            if child.tag != qn("w:pPr"):
                par._p.remove(child)
        set_para_props(par, before=0, after=0, jc="center", size=REF_PT)
        par._p.append(make_run("Page ", REF_PT))
        par._p.append(fld("PAGE"))
        par._p.append(make_run(" of ", REF_PT))
        par._p.append(fld("NUMPAGES"))


def split_row(line, where):
    """Split '| a | b |' into ['a', 'b'], respecting escaped \\|."""
    line = escape(line.strip())
    if not line.endswith("|"):
        raise ReportError(f"{where}: table rows must start and end with |")
    # put the escaped pipe back as "\|" so that add_inline later shows it as "|"
    return [c.strip().replace("", "\\|") for c in line[1:-1].split("|")]


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def build(md_path, out_path, template):
    with open(md_path, encoding="utf-8") as f:
        lines = f.read().split("\n")
    meta, start = parse_header(lines)
    blocks = parse_blocks(lines, start)

    # The abstract: the first block must be '## Abstract' with exactly one paragraph.
    if not blocks or blocks[0]["kind"] != "heading" or blocks[0]["text"].strip().lower() != "abstract" \
            or blocks[0]["level"] != 2:
        raise ReportError("the body must start with '## Abstract'")
    if len(blocks) < 2 or blocks[1]["kind"] != "para":
        raise ReportError(f"line {blocks[0]['line']}: '## Abstract' must be followed by one paragraph")
    if len(blocks) > 2 and blocks[2]["kind"] not in ("heading", "pagebreak"):
        raise ReportError(f"line {blocks[2]['line']}: the abstract is one paragraph; "
                          "the next thing must be a heading")
    abstract, blocks = blocks[1]["text"], blocks[2:]

    doc = docx.Document(template)
    dd = doc.styles.element.find(qn("w:docDefaults"))   # the template's default font is Arial; the footnote number fell back to it
    if dd is not None:
        for rf in dd.iter(qn("w:rFonts")):
            for a in ("ascii", "hAnsi", "cs", "eastAsia"):
                rf.set(qn("w:" + a), FONT)
    fill_title_block(doc, meta, abstract)
    fill_footnote(doc, meta)

    w = Writer(doc, os.path.dirname(os.path.abspath(md_path)))
    pending_caption = pending_widths = pending_width = None
    seen_refs = False
    for k, b in enumerate(blocks):
        nxt = blocks[k + 1] if k + 1 < len(blocks) else None
        kind = b["kind"]
        # A "Table N." paragraph directly above a table (a widths line may sit between) is its caption.
        if kind == "para" and re.match(r"^Table [A-Z]?\d+\.\s", b["text"]):
            after = blocks[k + 2] if nxt and nxt["kind"] == "widths" and k + 2 < len(blocks) else nxt
            if after and after["kind"] == "table":
                pending_caption = b["text"]; continue
        if pending_widths is not None and kind != "table":
            raise ReportError(f"line {b['line']}: a widths directive must sit directly above a table")
        if pending_width is not None and kind != "figure":
            raise ReportError(f"line {b['line']}: a width directive must sit directly above a figure")
        if pending_caption and kind not in ("table", "widths"):
            raise ReportError(f"line {b['line']}: caption is not followed by a table")

        if kind == "widths":
            pending_widths = b["values"]
        elif kind == "width":
            pending_width = b["value"]
        elif kind == "table":
            w.table(b, pending_caption, pending_widths)
            pending_caption = pending_widths = None
        elif kind == "figure":
            w.figure(b, pending_width)
            pending_width = None
        elif kind == "heading":
            if b["level"] == 2 and b["text"].strip().lower() == "references":
                seen_refs = True
            if b["level"] == 2 and b["text"].lower().startswith("appendix") and not seen_refs:
                raise ReportError(f"line {b['line']}: appendices come after ## References")
            w.heading(b)
        elif kind == "para":
            w.para(b, keep_next=bool(nxt and nxt["kind"] == "list"))
        elif kind == "list":
            w.list(b)
        elif kind == "pagebreak":
            w.pagebreak(b)
        elif kind == "ref":
            w.ref(b)
    if pending_caption or pending_widths or pending_width:
        raise ReportError("end of file: a caption or directive has nothing under it")

    add_page_numbers(doc)
    doc.save(out_path)
    return doc


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("markdown")
    ap.add_argument("--out", required=True, help="the .docx to write")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    a = ap.parse_args()
    try:
        build(a.markdown, a.out, a.template)
    except ReportError as e:
        sys.exit(f"build_report: {a.markdown}: {e}")
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
