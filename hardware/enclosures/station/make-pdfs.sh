#!/bin/sh
# Print the assembly guide and the tracking sheet to PDF with headless Chrome.
# Run after assembly.py (build.sh does). Skips quietly if Chrome is not installed.
set -e
cd "$(dirname "$0")/docs"
CHROME="${CHROME:-/Applications/Google Chrome.app/Contents/MacOS/Google Chrome}"
if [ ! -x "$CHROME" ]; then
    echo "make-pdfs: no Chrome at $CHROME; PDFs not made (set CHROME=...)" >&2
    exit 0
fi
for pair in "assembly-print.html:forsyth-assembly-guide.pdf" "assembly-sheet.html:forsyth-assembly-record.pdf"; do
    src="${pair%%:*}"; dst="${pair##*:}"
    "$CHROME" --headless=new --disable-gpu --no-pdf-header-footer --run-all-compositor-stages-before-draw \
        --virtual-time-budget=15000 --print-to-pdf="$PWD/$dst" "file://$PWD/$src" >/dev/null 2>&1
    echo "make-pdfs: docs/$dst"
done
