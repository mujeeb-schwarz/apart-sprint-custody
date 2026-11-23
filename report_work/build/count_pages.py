#!/usr/bin/env python3
"""
count_pages.py: page and word counts against Apart's cap (8 pages before references).

    python3 count_pages.py REPORT.pdf [--md REPORT.md]

Prints the total pages, the page on which the heading "References" starts, how
many pages the body takes before it, and (with --md) the words before
"## References" in the Markdown, with the abstract counted separately.
Uses pdftotext if it is installed, otherwise pypdf.
"""
import argparse
import re
import shutil
import subprocess
import sys

CAP = 8


def pdf_pages(path):
    """Return the text of each page."""
    if shutil.which("pdftotext"):
        out = subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, check=True).stdout
        pages = out.split("\f")
        if pages and not pages[-1].strip():
            pages = pages[:-1]
        return pages, "pdftotext"
    from pypdf import PdfReader
    return [p.extract_text() or "" for p in PdfReader(path).pages], "pypdf"


def md_words(md_path):
    text = open(md_path, encoding="utf-8").read()
    text = re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S)        # header
    text = re.split(r"^## References\s*$", text, flags=re.M)[0]       # stop at references
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.S)                # comments, directives
    text = re.sub(r"^\|[\s|:-]+\|\s*$", " ", text, flags=re.M)         # table separator rows
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)              # figures: keep caption
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)               # links: keep their text
    text = re.sub(r"<br\s*/?>", " ", text)
    m = re.search(r"^## Abstract\s*$(.*?)^#", text, flags=re.M | re.S)
    abstract = m.group(1) if m else ""
    count = lambda s: len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’.\-]*", s.replace("|", " ").replace("#", " ")))
    return count(text), count(abstract)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("--md")
    a = ap.parse_args()
    pages, tool = pdf_pages(a.pdf)
    print(f"total pages: {len(pages)}  (read with {tool})")
    ref_page, at_top = None, False
    for i, page in enumerate(pages, 1):
        lines = [l.strip() for l in page.split("\n") if l.strip()]
        if "References" in lines:
            ref_page = i
            # References at the very top of its page means the body ended on the page before
            at_top = lines.index("References") == 0
            break
    if ref_page is None:
        print("heading 'References' not found in the PDF text")
    else:
        body = ref_page - 1 if at_top else ref_page
        print(f"'References' starts on page {ref_page}"
              + (" (top of the page)" if at_top else " (part way down the page)"))
        print(f"pages before references: {body}"
              + ("" if at_top else f" ({ref_page - 1} full pages plus part of page {ref_page})"))
        print(f"cap is {CAP}: " + ("within the cap" if body <= CAP else f"OVER THE CAP by {body - CAP}"))
    if a.md:
        total, abstract = md_words(a.md)
        print(f"words before References in the Markdown: {total} (of which abstract: {abstract}; "
              f"Apart asks for 150 to 250 in the abstract)")


if __name__ == "__main__":
    sys.exit(main())
