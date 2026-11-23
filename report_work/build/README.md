# Report build: Markdown to Apart's Word template

Four small programs in this folder. Built and tested on a dummy report on Sun 15 Nov 2026; the PDF step was not run (see "Not checked").

## How to run

```sh
cd report_work/build
python3 build_report.py REPORT.md --out REPORT.docx       # 1. Markdown -> Word, on Apart's template
python3 check_docx.py REPORT.docx --md REPORT.md         # 2. optional: re-open the .docx and check it
sh to_pdf.sh REPORT.docx                                 # 3. Word -> PDF (runs LibreOffice)
python3 count_pages.py REPORT.pdf --md REPORT.md         # 4. pages before References, and word count
```

- `build_report.py` uses Apart's template at `report_work/build/template/apart_template.docx` (read only, never changed). The template is Apart Research's and is not included in this repository. `--template` picks another file.
- Any Markdown it does not understand stops the build with the line number and what is wrong. Nothing is guessed.
- `to_pdf.sh` runs `/opt/homebrew/bin/soffice --headless --convert-to pdf --outdir <folder of the docx> <docx>`.
- `count_pages.py` prints total pages, the page where the heading "References" starts, the pages before it (cap: 8), and the Markdown's words before `## References`, with the abstract counted on its own (Apart asks for 150 to 250).
- The test report is `dummy/REPORT.md`; `dummy/make_figures.py` makes its two PNGs.

## Supported Markdown, one example each

| Element | Example |
|---|---|
| Header (required: title, authors, affiliations; optional: event, date) | `---` / `title: Our title` / `authors: A. One; B. Two` / `affiliations: Independent; Uni X` / `event: AI x Epistemics Research Sprint` / `date: November 2026` / `---` |
| Abstract: must come first, one paragraph | `## Abstract` then one paragraph |
| Headings | `## 1. Introduction`, `### Limitations`, `#### 4.1.1 Detail` (numbers are typed by you) |
| Bold, italic, both | `**bold**`, `*italic*`, `***both***` |
| Code | `` `run_id` `` |
| Link (live) | `[Apart](https://apartresearch.com)`; a bare `https://...` is live too |
| Reference mark (plain text) | `[12]`, `[3, 4]` |
| Escaped character | `\*`, `\|`, `\[` |
| Bullet list, one level of nesting | `- item` then `  - nested` (2 to 4 spaces) |
| Numbered list | `1. item`; nested numbers show as (a), (b) |
| Table with caption | `Table 1. Caption text.` on the line directly above `| a | b |` / `|---|---|` / rows |
| Table column widths (percent, add up to 100) | `<!-- widths: 20,30,25,25 -->` directly above the table (or above its caption) |
| Line break and bold inside a cell | `| **Ours** | first<br>second |` |
| Figure | `![Figure 1. Caption that stands alone.](figures/fig1.png)` on its own line; path relative to the .md |
| Figure width (percent of text width) | `<!-- width: 80 -->` directly above the figure |
| Page break | `<!-- pagebreak -->` |
| References | `## References` then entries `1. Author (2025). Title. Venue. https://doi.org/...` or `[1] ...` |
| Appendix | `## Appendix A. Data` after the references |
| Note to ourselves (skipped) | `<!-- any comment without a key: -->` |

Authors: separate with `;` (or `,` if no `;` is used). One affiliation applies to all; otherwise give one per author, separated by `;`.

## Style mapping

The template's look comes from its styles plus direct formatting on every run (Google Docs export). The program copies both. Values below were read from the template unless marked "ours"; all of them are constants at the top of `build_report.py` under "LOOK".

| Markdown | Template style | Formatting |
|---|---|---|
| title | `Title` (the "PROJECT TITLE" paragraph, its footnote mark kept) | template's: bold 20 pt, centred |
| authors, affiliations | the title table's author grid, one cell per author | template's cell format; 11 pt, name, line break, affiliation |
| `## Abstract` paragraph | the paragraph in the template's abstract box | template's: justified, indented 0.375 in, 11 pt; upright (the template's italics marked guidance text) |
| event, date | the title footnote "Research conducted at the ..., ..." | the event keeps its link |
| `##` | `Heading 2` | template's: bold 14 pt, 10 pt before, 1.5 line |
| `###` | `Heading 3` | template's: bold 13 pt, black, 10 pt before |
| `####` | `Heading 4` | ours: bold 12 pt, black (the template uses no H4) |
| paragraph | `Normal` | template's: Old Standard TT 11 pt, line 1.15; 12.65 pt after (the template's blank-line gap as space after) |
| bullet list | `Normal` + template list 3 ("-") | template's indents 0.5 in / 1 in |
| numbered list | `Normal` + template list 5 ("1."), restarting per list | nested numbers use template list 2 ("(a)") |
| table caption, figure caption | `Normal` | ours: 10 pt, "Table N." / "Figure N." in bold; figure captions centred |
| table cells | `Normal` | ours: **9 pt**, single spacing, header row bold; 1 pt black borders as the template's tables |
| figure | `Normal`, centred | width from the directive, else full text width; never taller than 7.5 in |
| reference entry | `Normal` | ours: **10 pt**, hanging indent, label as typed (`1.` or `[1]`), links live |
| `code` | (run formatting) | ours: Courier New 10 pt (the template has no code style) |
| link | (run formatting) | blue 1155CC, underlined, a real Word hyperlink |

Font sizes: body 11 pt, tables 9 pt, captions 10 pt, references 10 pt.

## Behaviour worth knowing

- Kept from the template: page size (US Letter), margins (1 in), embedded Old Standard TT fonts, styles, the title table with "With Apart Research", the abstract box and the title footnote.
- Removed: the instruction box, every sample paragraph, and the link to the evaluation rubric those paragraphs carried.
- Tables: the width is the full text width (6.5 in); without a widths directive, columns share it by their longest text. Rows never split across pages, the header row repeats on a new page, and tables of up to 15 rows are kept on one page with their caption.
- Figures: the picture is kept with its caption, so both land on one page.

## Known limits

- Not supported (stops the build): `#` headings, code blocks, block quotes, horizontal rules, HTML other than `<br>` and comments, nested lists deeper than one level, mixing bullets and numbers at the top level of one list, `_underscore_` emphasis (underscores stay as typed), links to anything but http(s) or mailto, footnotes, maths, images not written as `![Figure N. ...](...)`.
- References keep the label you type; Word does not renumber them. Reference marks in the text are not linked to the list.
- Column alignment markers (`---:`) are accepted and ignored: every cell is left-aligned.
- The author grid is rebuilt with one equal-width cell per author (up to 3 per row) across the template's 5 in title area; the template's own grid cells were 0.48 in wide, which would wrap names letter by letter.
- More than about 15 rows: the table may break across pages (rows still do not split).
- `check_docx.py` checks structure, not looks. Only the PDF shows the page count and how it reads.

## Not checked (PDF step not run in the build session)

The program was tested only as far as the .docx, by code. Not seen: how LibreOffice lays out the title block and author grid, the real page count, whether figures and captions stay together, how the 6-column table wraps, and whether the embedded fonts are used. Run `to_pdf.sh` on `dummy/REPORT.docx` and look at the PDF once before the real report goes through.
