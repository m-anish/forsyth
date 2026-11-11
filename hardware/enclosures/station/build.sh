#!/bin/sh
# Regenerate all station parts from params.py. Needs FreeCAD 1.x.
set -e
cd "$(dirname "$0")"
FREECADCMD="${FREECADCMD:-/Applications/FreeCAD.app/Contents/Resources/bin/freecadcmd}"
# The STEP writer and the recompute progress bar are chatty; keep only our own lines.
ESC="$(printf '\033')"
STATION_DIR="$(pwd)" "$FREECADCMD" build.py 2>&1 \
    | sed -e "s/${ESC}\[[0-9;]*m//g" \
    | grep -v -E 'Transfer|Statistics|WorkSession|Step File Name|\*\*\*\*|3DconnexionNavlib|Recompute|\(100 %\)|^[[:space:]]*$' \
    || true
if [ -f out/BUILD_FAILED ] || [ -f BUILD_FAILED ]; then
    echo "build reported failed checks (see above)" >&2
    exit 1
fi
