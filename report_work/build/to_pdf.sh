#!/bin/sh
# to_pdf.sh: turn the built .docx into a PDF with LibreOffice.
# LibreOffice hangs inside Claude's sandbox, so run this OUTSIDE it (one approval).
#
#   sh to_pdf.sh REPORT.docx          -> writes REPORT.pdf next to it
#
# The exact command, if you prefer to type it:
#   /opt/homebrew/bin/soffice --headless --convert-to pdf --outdir "<folder of the docx>" "<the docx>"
set -e
DOCX="${1:?usage: sh to_pdf.sh REPORT.docx}"
OUTDIR="$(cd "$(dirname "$DOCX")" && pwd)"
/opt/homebrew/bin/soffice --headless --convert-to pdf --outdir "$OUTDIR" "$DOCX"
echo "wrote $OUTDIR/$(basename "${DOCX%.*}").pdf"
