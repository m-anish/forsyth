#!/usr/bin/env bash
# install.sh — upload the coordinator firmware to an ESP32-S3 running MicroPython.
#
# Usage:
#   ./install.sh                      # auto-detect the serial port
#   ./install.sh --port /dev/tty.usbmodemXXX
#   ./install.sh --force-config       # overwrite the ON-DEVICE config.py
#
# Safe by default: the device's config.py (with real WiFi/MQTT credentials) is
# NEVER overwritten unless --force-config is passed. Everything else is
# replaced wholesale — code lives in git, config lives on the device.
#
# Prereq: pip install mpremote   (and MicroPython already flashed — README §Install)
set -euo pipefail
cd "$(dirname "$0")"

PORT_ARGS=()
FORCE_CONFIG=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --force-config) FORCE_CONFIG=1; shift ;;
    --port)         PORT_ARGS=(connect "$2"); shift 2 ;;
    *) echo "usage: $0 [--port /dev/tty...] [--force-config]" >&2; exit 1 ;;
  esac
done

command -v mpremote >/dev/null 2>&1 || {
  echo "mpremote not found — run: pip install mpremote" >&2; exit 1; }

echo "== dependency: umqtt.simple"
mpremote "${PORT_ARGS[@]+"${PORT_ARGS[@]}"}" mip install umqtt.simple
mpremote "${PORT_ARGS[@]+"${PORT_ARGS[@]}"}" mip install ssd1306

echo "== code"
for f in protocol.py e220.py net.py uplink.py display.py boot.py main.py; do
  echo "   $f"
  mpremote "${PORT_ARGS[@]+"${PORT_ARGS[@]}"}" cp "src/$f" ":$f"
done

echo "== config"
if [[ $FORCE_CONFIG -eq 1 ]] || \
   ! mpremote "${PORT_ARGS[@]+"${PORT_ARGS[@]}"}" fs cat :config.py >/dev/null 2>&1; then
  mpremote "${PORT_ARGS[@]+"${PORT_ARGS[@]}"}" cp src/config.py :config.py
  echo "   config.py uploaded — now set credentials:  mpremote edit config.py"
else
  echo "   device config.py kept (pass --force-config to overwrite)"
fi

echo "== reset"
mpremote "${PORT_ARGS[@]+"${PORT_ARGS[@]}"}" reset
echo "done. watch it run:  mpremote repl"
