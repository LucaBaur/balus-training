#!/usr/bin/env bash
# Deploy von Balu's Trainings App -> Homeserver ~/elo/static.
# Testet ERST (Syntax + Offline-Tests) und laedt nur bei gruen hoch.
set -euo pipefail
cd "$(dirname "$0")"

ZIEL="luca@192.168.8.125:~/elo/static/"
STATIC=(static/local-db.js static/sync.js static/teams-local.js static/app.js static/sw.js static/index.html static/style.css static/manifest.webmanifest static/tvg-logo.png)

echo "== 1/3 Syntax-Check =="
for f in static/local-db.js static/sync.js static/teams-local.js static/app.js static/sw.js; do
  node --check "$f" && echo "  ok $f"
done

echo "== 2/3 Offline- & Team-Tests =="
node tests/offline.test.mjs
node tests/teams.test.mjs

echo "== 3/3 Deploy nach ~/elo =="
scp "${STATIC[@]}" "$ZIEL"

echo "== Fertig: deployt =="
