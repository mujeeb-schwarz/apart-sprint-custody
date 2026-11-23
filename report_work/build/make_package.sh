#!/bin/sh
# Rebuild the report from main_v10.md and back_v10.md, check it, and refresh the submission package.
# Run outside the sandbox: the PDF step uses LibreOffice. Usage: sh make_package.sh "<Submission folder>"
set -e
HERE="$(cd "$(dirname "$0")" && pwd)"; W="$(dirname "$HERE")"; S="$1"
cd "$W/draft"
python3 - <<'PY'
m = open('main_v10.md', encoding='utf-8').read(); b = open('back_v10.md', encoding='utf-8').read()
open('REPORT.src.md', 'w', encoding='utf-8').write(m.rstrip('\n') + '\n\n' + b)
import re
ab = re.search(r'## Abstract\n\n(.*?)\n\n## 1\.', m, re.S).group(1)
n = len(ab.split()); print('abstract words:', n); assert 150 <= n <= 250, 'abstract outside 150 to 250 words'
PY
python3 assemble.py REPORT.src.md REPORT.md | tail -1
python3 ../build/build_report.py REPORT.md --out REPORT.docx >/dev/null
sh ../build/to_pdf.sh REPORT.docx >/dev/null 2>&1
python3 ../build/count_pages.py REPORT.pdf --md REPORT.md | sed -n 1,4p
python3 ../build/count_pages.py REPORT.pdf --md REPORT.md | grep -q "within the cap"
python3 ../build/audit_refs.py REPORT.md "${TMPDIR:-/tmp}/report_urls.txt" | grep "PROBLEMS"
python3 ../build/audit_refs.py REPORT.md "${TMPDIR:-/tmp}/report_urls.txt" | grep -q "PROBLEMS: 0"
if [ -n "$S" ]; then
  mkdir -p "$S/Final package (submit these)" "$S/Draft"
  python3 ../build/make_reference_check.py REPORT.md "$S/Reference check/Reference check - every citation with its source (15 Nov).md" "$(date '+%a %d %b, %H:%M')"
  cp REPORT.pdf "$S/Final package (submit these)/Report - Is an AI system's own log enough.pdf"
  cp ../figures/fig1_visit_example.png "$S/Final package (submit these)/Project image (Figure 1).png"
  cp REPORT.docx "$S/Draft/Report - Word version of the final.docx"
  echo "package refreshed at $(date '+%H:%M')"
fi
