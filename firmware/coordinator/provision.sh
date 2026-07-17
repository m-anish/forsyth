#!/usr/bin/env bash
# provision.sh — give a coordinator board its secrets, once.
#
#   ./provision.sh --port /dev/cu.usbmodemXXXX --ssid "Anish’s iPhone" --pass "…"
#
# What it does, in order:
#   1. mints a fresh MQTT password for this device and sets it on the broker
#      (rotating is safer than trying to recover the old one, and nothing else
#      uses the coordinator credential yet)
#   2. records it back into the droplet's .env for future reference
#   3. registers the bench station in the cloud (is_simulated — the bench
#      invents its numbers and the dashboard should say so)
#   4. writes config.py onto the board with the real credentials
#
# Secrets travel droplet → your shell → the board. They are never printed, and
# the repo's config.py keeps its placeholders (device config is .gitignored by
# virtue of living only on the device).
#
# Env overrides: FORSYTH_HOST, FORSYTH_PATH, MQTT_USER, BENCH_SLUG
set -euo pipefail

HOST="${FORSYTH_HOST:-root@165.232.191.72}"
RPATH="${FORSYTH_PATH:-/home/forsyth/forsyth}"
MQTT_USER="${MQTT_USER:-coordinator-01}"
BENCH_SLUG="${BENCH_SLUG:-bench}"
PORT=""; SSID=""; WPASS=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --port) PORT="$2"; shift 2 ;;
    --ssid) SSID="$2"; shift 2 ;;
    --pass) WPASS="$2"; shift 2 ;;
    -h|--help) sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done

[[ -z "$PORT" ]] && PORT="$(ls /dev/cu.usbmodem* 2>/dev/null | head -1 || true)"
[[ -z "$PORT" ]] && { echo "no board found; pass --port" >&2; exit 1; }
[[ -z "$SSID" ]] && { echo "--ssid is required" >&2; exit 1; }
command -v mpremote >/dev/null || { echo "pip install mpremote" >&2; exit 1; }

echo "▶ board: $PORT"
echo "▶ minting a fresh MQTT password for $MQTT_USER"
MQTT_PW="$(openssl rand -hex 20)"

ssh "$HOST" "cd '$RPATH/cloud' && \
  docker compose exec -T mosquitto mosquitto_passwd -b /mosquitto/passwd/passwd '$MQTT_USER' '$MQTT_PW' && \
  docker compose restart mosquitto >/dev/null && \
  sed -i '/^# $MQTT_USER MQTT password/d' .env && \
  echo '# $MQTT_USER MQTT password: $MQTT_PW' >> .env" >/dev/null
echo "  ✓ broker credential rotated + recorded in .env"

echo "▶ registering station '$BENCH_SLUG' (is_simulated)"
# runs on the droplet so ADMIN_KEY never leaves it.
# NOTE: the lat/lon/elev below are the ONE intentional hardcoded coordinate in
# the system — this is the fake bench/demo station. REAL stations are located
# via the admin console map picker or the coordinator's /location page, never by
# hardcoding here. (Elevation would otherwise auto-fill server-side.)
ssh "$HOST" "cd '$RPATH/cloud' && set -a && . ./.env && set +a && \
  curl -sS -o /dev/null -w '  http %{http_code}\n' -X POST \
    http://localhost:8080/api/v1/stations \
    -H \"Authorization: Bearer \$ADMIN_KEY\" \
    -H 'Content-Type: application/json' \
    -d '{\"slug\":\"$BENCH_SLUG\",\"name\":\"Bench\",\"lat\":29.4459,\"lon\":79.6128,\"elevation_m\":1950,\"is_simulated\":true}'"

echo "▶ writing config.py onto the board"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
python3 - "$TMP/config.py" "$SSID" "$WPASS" "$MQTT_USER" "$MQTT_PW" "$BENCH_SLUG" <<'PY'
import sys, pathlib
out, ssid, wpass, muser, mpw, slug = sys.argv[1:7]
src = pathlib.Path(__file__).parent  # unused; kept for clarity
tpl = pathlib.Path("src/config.py").read_text()
def setval(t, key, val):
    import re
    return re.sub(r'^%s = .*$' % key, '%s = %r' % (key, val), t, count=1, flags=re.M)
tpl = setval(tpl, "WIFI_SSID", ssid)
tpl = setval(tpl, "WIFI_PASSWORD", wpass)
tpl = setval(tpl, "MQTT_PASSWORD", mpw)
tpl = setval(tpl, "COORDINATOR_ID", muser)
tpl = tpl.replace('"slug": "bench"', '"slug": %r' % slug)
pathlib.Path(out).write_text(tpl)
print("  ✓ config rendered (%d bytes)" % len(tpl))
PY

mpremote connect "$PORT" cp "$TMP/config.py" :config.py
echo "  ✓ config.py on device"
echo
echo "✓ provisioned. Now install the code:  ./install.sh --port $PORT"
