#!/usr/bin/env bash
# deploy.sh — ship the Forsyth cloud stack.
#
#   ./deploy.sh            deploy to the production droplet (git pull + rebuild)
#   ./deploy.sh --test     run the full stack locally on this machine
#   ./deploy.sh --down     stop the local test stack
#
# Config via env (defaults suit the current droplet — see memory/deploy.md):
#   FORSYTH_HOST   ssh target        default root@165.232.191.72
#   FORSYTH_PATH   repo dir on host  default /home/forsyth/forsyth
#   FORSYTH_URL    url to smoke-test default https://live.forsyth.starstucklab.com
set -euo pipefail

HOST="${FORSYTH_HOST:-root@165.232.191.72}"
RPATH="${FORSYTH_PATH:-/home/forsyth/forsyth}"
URL="${FORSYTH_URL:-https://live.forsyth.starstucklab.com}"
CLOUD="$(cd "$(dirname "$0")" && pwd)/cloud"

# docker compose build occasionally trips over a transient Docker Hub 500 on
# the base-image manifest check — retry a couple of times before giving up.
build_up() {  # args: extra compose flags (profiles)
  local n=1
  until docker compose "$@" up -d --build; do
    (( n >= 3 )) && { echo "✗ build failed after $n attempts" >&2; return 1; }
    echo "  … build hiccup (often a transient registry 500); retry $((++n)) in 15s"
    sleep 15
  done
}

case "${1:-}" in
  --test|test|-t)
    echo "▶ local test — full sim stack"
    cd "$CLOUD"
    if [[ ! -f .env ]]; then
      echo "  no .env — writing a throwaway one for local testing"
      cat > .env <<EOF
DB_PASSWORD=devpass
ADMIN_KEY=dev-admin-key-not-secret
PUBLIC_BASE_URL=http://localhost:8080
EOF
    fi
    build_up --profile sim
    echo "✓ up → http://localhost:8080   (stop: ./deploy.sh --down)"
    ;;

  --down|down)
    echo "▶ stopping local test stack"
    cd "$CLOUD"
    docker compose --profile sim down
    ;;

  ""|--prod|prod)
    echo "▶ production deploy → $HOST"
    # pull + rebuild on the droplet; retry the build the same way remotely
    ssh "$HOST" "cd '$RPATH' && git pull --ff-only && cd cloud && \
      for i in 1 2 3; do \
        docker compose --profile sim --profile prod up -d --build && break; \
        [ \$i -eq 3 ] && { echo 'build failed' >&2; exit 1; }; \
        echo '  build hiccup; retry in 15s'; sleep 15; \
      done"
    echo "✓ deployed — smoke-testing $URL"
    # the api container takes a few seconds to come up behind Caddy; a 502 on
    # the first probe is a race, not a failure — retry before crying wolf
    for i in 1 2 3 4 5; do
      code="$(curl -s -o /dev/null -w '%{http_code}' "$URL/api/v1/health" || echo 000)"
      [ "$code" = "200" ] && { echo "  health → HTTP 200"; break; }
      [ "$i" = 5 ] && { echo "  ⚠ still HTTP $code after retries — inspect on the droplet"; break; }
      sleep 4
    done
    ;;

  -h|--help|help)
    sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
    ;;

  *)
    echo "unknown option: $1" >&2
    echo "usage: $0 [--test | --down | --prod]" >&2
    exit 1 ;;
esac
