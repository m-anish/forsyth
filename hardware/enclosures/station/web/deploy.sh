#!/bin/sh
# Publish build.forsyth.starstucklab.com (Cloudflare Pages project "forsyth-build"):
#   /               public landing page        /assembly.html, *.pdf   public guide
#   /app/           the tracker (Cloudflare Access sign-in)   /api/*   its API (same)
# Run ../build.sh first so docs/ is current.
#
#   ./deploy.sh            assemble dist/ and deploy it
#   ./deploy.sh --dist     only assemble dist/
#   ./deploy.sh --local    assemble dist/ and serve it on http://localhost:8788,
#                          signed in as $DEV_USER_EMAIL (default you@example.com)
set -e
cd "$(dirname "$0")"
DOCS=../docs
rm -rf dist && mkdir -p dist/assembly dist/app
cp $DOCS/build-landing.html dist/index.html
cp $DOCS/assembly-app.html dist/app/index.html
cp $DOCS/assembly.html $DOCS/forsyth-assembly-guide.pdf $DOCS/forsyth-assembly-record.pdf dist/
cp $DOCS/assembly/*.png dist/assembly/
cp ../../../../site/assets/mark.svg dist/favicon.svg
cp ../../../../site/assets/mark.svg dist/app/favicon.svg
cat > dist/_redirects <<'R'
/app /app/ 301
/app/assembly/* /assembly/:splat 200
R
cat > dist/_headers <<'H'
/*
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  X-Frame-Options: DENY
/app/*
  Cache-Control: no-cache
/assembly/*
  Cache-Control: public, max-age=3600
H
if [ "$1" = "--dist" ]; then
    exit 0
fi
if [ "$1" = "--local" ]; then
    wrangler d1 execute forsyth-build --local --file=schema.sql >/dev/null
    exec wrangler pages dev dist --port 8788 --binding DEV_USER_EMAIL="${DEV_USER_EMAIL:-you@example.com}"
fi
wrangler pages deploy dist --project-name forsyth-build --branch main --commit-dirty=true
