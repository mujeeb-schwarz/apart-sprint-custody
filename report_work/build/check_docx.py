#!/usr/bin/env python3
"""
check_docx.py: re-open a built .docx and check it against the template.

    python3 check_docx.py REPORT.docx [--md REPORT.md] [--template T.docx]

Checks: page size and margins equal the template's; every paragraph (body and
table cells) uses a style that exists in the template; the instruction box and
the sample text are gone; the title block holds the title from the .md header;
figures are embedded; each Markdown table has the same rows and columns in the
.docx; hyperlinks exist (and, with --md, one per link in the Markdown).
Prints PASS/FAIL per check and exits 1 if any check fails.
"""
import argparse
import re
import sys

import docx
from docx.oxml.ns import qn

sys.path.insert(0, __import__("os").path.dirname(__file__))
from build_report import DEFAULT_TEMPLATE, parse_blocks, parse_header, INLINE, escape  # noqa: E402

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("docx")
    ap.add_argument("--md")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE)
    a = ap.parse_args()
    d, t = docx.Document(a.docx), docx.Document(a.template)
    results = []

    def check(name, ok, detail=""):
        results.append(ok)
        print(("PASS " if ok else "FAIL ") + name + (f"  ({detail})" if detail else ""))

    # 1. page size and margins
    ds, ts = d.sections[0], t.sections[0]
    attrs = ["page_width", "page_height", "left_margin", "right_margin", "top_margin", "bottom_margin"]
    diff = [x for x in attrs if getattr(ds, x) != getattr(ts, x)]
    check("page size and margins equal the template's", not diff and len(d.sections) == 1,
          f"{ds.page_width.inches} x {ds.page_height.inches} in, margins {ds.left_margin.inches} in" if not diff else str(diff))

    # 2. styles
    template_ids = {s.style_id for s in t.styles}
    used = set()
    for p in d.element.body.iter(W + "p"):
        ps = p.find(f"{W}pPr/{W}pStyle")
        used.add(ps.get(qn("w:val")) if ps is not None else "Normal")
    check("every paragraph uses a template style", used <= template_ids,
          f"used {sorted(used)}" if used <= template_ids else f"missing {sorted(used - template_ids)}")

    # 3. instruction box and sample text gone
    text = "\n".join(x.text or "" for x in d.element.body.iter(W + "t"))
    leftovers = [s for s in ["How to use this template", "How your submission will be evaluated",
                             "Recommended length", "Summarize your project", "PROJECT TITLE",
                             "Author name", "[Reference 1]", "What problem are you addressing"]
                 if s in text]
    check("instruction box and sample text removed", not leftovers, ", ".join(leftovers))

    # 4. title block
    first_tbl = d.element.body.find(W + "tbl")
    title_text = "".join(x.text or "" for x in first_tbl.iter(W + "t"))
    if a.md:
        meta, start = parse_header(open(a.md, encoding="utf-8").read().split("\n"))
        check("title block holds the title", meta["title"] in title_text, meta["title"])
        authors = [x.strip() for x in re.split(";" if ";" in meta["authors"] else ",", meta["authors"])]
        check("title block holds every author", all(x in title_text for x in authors), ", ".join(authors))
    check("title block keeps 'With Apart Research' and the abstract box",
          "Apart Research" in title_text and "Abstract" in title_text)

    # 5. figures
    blips = list(d.element.body.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"))
    images = [r for r in d.part.rels.values() if r.reltype.endswith("/image")]
    n_fig = None
    if a.md:
        lines = open(a.md, encoding="utf-8").read().split("\n")
        blocks = parse_blocks(lines, parse_header(lines)[1])
        n_fig = sum(b["kind"] == "figure" for b in blocks)
    check("figures embedded", len(blips) > 0 and len(images) >= (n_fig or 1) and (n_fig is None or len(blips) == n_fig),
          f"{len(blips)} pictures, {len(images)} image parts" + (f", {n_fig} in the .md" if n_fig is not None else ""))

    # 6. tables: everything after the title table, compared with the Markdown
    tables = d.tables[1:]
    shapes = [(len(x.rows), len(x.columns)) for x in tables]
    if a.md:
        want = [(len(b["rows"]) - 1, len(b["rows"][0][1].strip().strip("|").split("|")))
                for b in blocks if b["kind"] == "table"]
        check("tables have the right rows and columns", shapes == want, f"docx {shapes}, md {want}")
    widths_ok = all(sum(int(g.get(qn("w:w"))) for g in x._tbl.tblGrid.findall(qn("w:gridCol"))) <= 9360
                    for x in tables)
    check("tables fit the text width (6.5 in)", widths_ok)

    # 7. hyperlinks
    links = list(d.element.body.iter(W + "hyperlink"))
    targets = {r.rId: r.target_ref for r in d.part.rels.values() if r.reltype.endswith("/hyperlink")}
    ok = links and all(h.get(qn("r:id")) in targets for h in links)
    detail = f"{len(links)} hyperlinks"
    if a.md:
        body = "\n".join(l for l in lines[parse_header(lines)[1]:]
                         if not l.strip().startswith("!["))   # figure lines are not links
        n_md = sum(1 for m in INLINE.finditer(escape(body)) if m.group("link") or m.group("url") or m.group("aurl"))
        detail += f", {n_md} links in the .md (a link's text split into runs counts once per run)"
        ok = ok and len(links) >= n_md
    check("hyperlinks exist and point to real targets", bool(ok), detail)

    print("ALL PASS" if all(results) else "SOME CHECKS FAILED")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
