#!/usr/bin/env bash
# Demo-Instanz von Balu's Training auf dem Homeserver - NEBEN der echten App.
#
#   bash deploy_demo.sh            Code aktualisieren, Demo (neu) starten, pruefen
#   bash deploy_demo.sh --trocken  nur anzeigen, was passieren wuerde
#   bash deploy_demo.sh --entfernen  Dienst, Ordner und Zugangsdaten der Demo wieder loeschen
#
# Die Demo ist die Datei docs/anleitung-funktionen/demo_server.py: erfundene Spielerinnen,
# erfundene Spiele, Nutzungsdaten. Sie startet bei jedem (Neu-)Start mit frischen Daten -
# ein Neustart setzt also alles zurueck (fuer Demovideos).
#
# Warum sie der echten App nicht im Weg steht:
#   * eigener Ordner (~/elo-demo) als KOPIE des Codes - keine Verknuepfung nach ~/elo, damit
#     die App ihren Datenordner nie in ~/elo findet. Ohne elo.db, media/, .env, .session_secret
#     und ohne die Fotos der Spielerinnen. Die Cron-Jobs (erinnerung, push, sync) laufen
#     weiter nur in ~/elo und kennen die Demo nicht.
#   * eigener systemd-Dienst "elo-demo", eigener Port (8201), temporaere Demo-Datenbank.
#   * eigener Sitzungs-Cookie (sitzung_demo): Cookies gelten pro Host, nicht pro Port -
#     sonst wuerde eine Demo-Anmeldung die echte im selben Browser ueberschreiben.
#   * eigenes Zufalls-Geheimnis; keine VAPID-Schluessel (kein Push); SP_SYNC_DIR zeigt auf
#     einen leeren Ordner (kein Zugriff auf die Anytype-Exporte).
#   * KEIN Tailscale-Funnel: erreichbar nur im Heimnetz/Tailnet unter http://<server>:8201.
#
# Server-Daten stehen in deploy.env (wie bei deploy.sh); optional DEMO_DIR, DEMO_SERVICE, DEMO_PORT.
set -euo pipefail
cd "$(dirname "$0")"

TROCKEN=0; ENTFERNEN=0
for a in "$@"; do
  case "$a" in
    --trocken)   TROCKEN=1 ;;
    --entfernen) ENTFERNEN=1 ;;
    *)           echo "Unbekannte Option: $a"; exit 2 ;;
  esac
done

[ -f deploy.env ] || { echo "deploy.env fehlt - Vorlage: deploy.env.example"; exit 1; }
# shellcheck disable=SC1091
source deploy.env
: "${DEPLOY_HOST:?DEPLOY_HOST fehlt in deploy.env}"
PROD_DIR="${DEPLOY_DIR:-elo}"; PROD_SERVICE="${DEPLOY_SERVICE:-elo}"
PROD_URL="${DEPLOY_URL:-http://127.0.0.1:8200}"; PROD_PORT="${PROD_URL##*:}"
DIR="${DEMO_DIR:-elo-demo}"; SERVICE="${DEMO_SERVICE:-elo-demo}"; PORT="${DEMO_PORT:-8201}"

abbruch() { printf '\nABBRUCH: %s\n' "$1"; exit 1; }
schritt() { printf '\n== %s ==\n' "$1"; }
[ "$DIR" != "$PROD_DIR" ]         || abbruch "DEMO_DIR ist derselbe Ordner wie DEPLOY_DIR ($DIR)"
[ "$SERVICE" != "$PROD_SERVICE" ] || abbruch "DEMO_SERVICE ist derselbe Dienst wie DEPLOY_SERVICE ($SERVICE)"
[ "$PORT" != "$PROD_PORT" ]       || abbruch "DEMO_PORT ist derselbe Port wie die echte App ($PORT)"
case "$DIR" in /*|*..*|"") abbruch "DEMO_DIR muss ein einfacher Ordnername im Home sein: $DIR" ;; esac

if command -v py >/dev/null 2>&1; then PY=py; else PY=python3; fi
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=8 "$DEPLOY_HOST")
"${SSH[@]}" true 2>/dev/null || abbruch "Server $DEPLOY_HOST nicht erreichbar (Heimnetz? SSH-Schluessel?)"
SERVERHOME="$("${SSH[@]}" 'echo $HOME')"
SYSD='export XDG_RUNTIME_DIR=/run/user/$(id -u)'

prod_ok() {      # die echte App muss davon unberuehrt bleiben
  local code
  code="$("${SSH[@]}" "$SYSD; systemctl --user is-active $PROD_SERVICE >/dev/null && curl -s --max-time 10 -o /dev/null -w '%{http_code}' '$PROD_URL/'" || true)"
  echo "  Echte App ($PROD_SERVICE, Port $PROD_PORT): HTTP $code"
  [ "$code" = 200 ] || abbruch "Die echte App antwortet nicht mit 200 - bitte pruefen!"
}

# ------------------------------------------------------------------ Entfernen ----
if [ $ENTFERNEN -eq 1 ]; then
  schritt "Demo entfernen ($SERVICE, ~/$DIR)"
  [ $TROCKEN -eq 1 ] && { echo "  Trockenlauf: wuerde Dienst $SERVICE stoppen und ~/$DIR loeschen"; exit 0; }
  "${SSH[@]}" "$SYSD; systemctl --user disable --now $SERVICE 2>/dev/null; rm -f ~/.config/systemd/user/$SERVICE.service; systemctl --user daemon-reload; rm -rf \"\$HOME/$DIR\"; echo '  entfernt'"
  prod_ok
  exit 0
fi

# ---------------------------------------------------------------------- Tests ----
schritt "1/4 Test der Demo"
out="$("$PY" tests/demo_test.py 2>&1)" || { echo "$out" | tail -15; abbruch "tests/demo_test.py fehlgeschlagen"; }
echo "  ok  tests/demo_test.py"

# --------------------------------------------------------------- Vorpruefungen ----
schritt "2/4 Vorpruefung auf dem Server"
"${SSH[@]}" "$SYSD; systemctl --user cat $PROD_SERVICE >/dev/null" || abbruch "Dienst $PROD_SERVICE nicht gefunden"
PYBIN="$("${SSH[@]}" "$SYSD; systemctl --user cat $PROD_SERVICE | sed -n 's/^ExecStart=\\([^ ]*\\) .*/\\1/p' | head -1")"
[ -n "$PYBIN" ] || abbruch "Python-Pfad aus dem Dienst $PROD_SERVICE nicht lesbar"
echo "  Python: $PYBIN"
BELEGT="$("${SSH[@]}" "ss -ltnH 'sport = :$PORT' | wc -l")"
LAEUFT="$("${SSH[@]}" "$SYSD; systemctl --user is-active $SERVICE 2>/dev/null || true")"
if [ "$BELEGT" != 0 ] && [ "$LAEUFT" != active ]; then abbruch "Port $PORT ist auf dem Server schon von etwas anderem belegt"; fi
echo "  Port $PORT: frei oder von $SERVICE belegt; Ordner ~/$DIR, Dienst $SERVICE"
prod_ok
if [ $TROCKEN -eq 1 ]; then printf '\n== Trockenlauf: nichts auf den Server geschrieben ==\n'; exit 0; fi

# -------------------------------------------------------------------- Hochladen ----
schritt "3/4 Code kopieren und Dienst einrichten"
shopt -s nullglob
DATEIEN=(*.py daten routen requirements.txt static docs/anleitung-funktionen/demo_server.py tests/liga_beispiel.json)
shopt -u nullglob
"${SSH[@]}" "mkdir -p \"\$HOME/$DIR\" \"\$HOME/$DIR/leer\""
# Ohne Spielerinnen-Fotos und Sicherungen; den Foto-Index ersetzen wir unten durch eine leere Liste.
tar --exclude='static/portraits/*.jpg' --exclude='*.bak-*' --exclude='__pycache__' -cf - "${DATEIEN[@]}" \
  | "${SSH[@]}" "tar -xf - -C \"\$HOME/$DIR\" --no-same-owner"
"${SSH[@]}" "printf '{\"spieler\": {}}\n' > \"\$HOME/$DIR/static/portraits/index.json\"; \
  rm -f \"\$HOME/$DIR\"/static/portraits/*.jpg"
echo "  Code kopiert (ohne Datenbank, media, .env, Fotos)"

# Zugangsdaten der Demo: nur beim ersten Mal erzeugen, danach unveraendert lassen.
"${SSH[@]}" "cd \"\$HOME/$DIR\" && [ -f demo.env ] || { umask 077; printf 'APP_SECRET=%s\nSESSION_COOKIE=sitzung_demo\nSP_SYNC_DIR=%s\nDEMO_HOST=0.0.0.0\nDEMO_PORT=$PORT\n' \"\$($PYBIN -c 'import secrets; print(secrets.token_hex(32))')\" \"\$HOME/$DIR/leer\" > demo.env; echo '  demo.env neu erzeugt'; }; chmod 600 demo.env"

"${SSH[@]}" "mkdir -p ~/.config/systemd/user && cat > ~/.config/systemd/user/$SERVICE.service" <<UNIT
[Unit]
Description=Balu's Training DEMO (erfundene Daten, getrennt von $PROD_SERVICE)
After=network.target

[Service]
WorkingDirectory=$SERVERHOME/$DIR
EnvironmentFile=$SERVERHOME/$DIR/demo.env
ExecStart=$PYBIN docs/anleitung-funktionen/demo_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
UNIT
"${SSH[@]}" "$SYSD; systemctl --user daemon-reload; systemctl --user enable $SERVICE >/dev/null 2>&1; systemctl --user restart $SERVICE; sleep 8; systemctl --user is-active $SERVICE" \
  | grep -qx active || abbruch "Dienst $SERVICE ist nicht aktiv - Log: journalctl --user -u $SERVICE"
echo "  Dienst $SERVICE laeuft"

# ------------------------------------------------------------------- Pruefung ----
schritt "4/4 Pruefung"
SOLL="$(grep -o 'APP_VERSION = "[^"]*"' static/app.js | cut -d'"' -f2)"
IST="$("${SSH[@]}" "curl -s --max-time 10 'http://127.0.0.1:$PORT/app.js'" | grep -o 'APP_VERSION = "[^"]*"' | cut -d'"' -f2)"
CODE="$("${SSH[@]}" "curl -s --max-time 10 -o /dev/null -w '%{http_code}' 'http://127.0.0.1:$PORT/'")"
echo "  Demo: HTTP $CODE   App-Version: $IST (lokal: $SOLL)"
[ "$CODE" = 200 ] && [ "$IST" = "$SOLL" ] || abbruch "Demo antwortet nicht wie erwartet"
# Cookie-Name der Demo und Anmeldung mit dem Demo-Konto (die Demo kennt keine echten Konten)
COOKIE="$("${SSH[@]}" "curl -s --max-time 10 -D - -o /dev/null -H 'Content-Type: application/json' -d '{\"name\":\"Trainer\",\"pin\":\"1111\"}' 'http://127.0.0.1:$PORT/api/login' | grep -io '^set-cookie: [a-z_]*' | head -1")"
echo "  Anmeldung in der Demo setzt: ${COOKIE:-<kein Cookie>}"
printf '%s' "$COOKIE" | grep -qi 'sitzung_demo' || abbruch "Die Demo setzt nicht den eigenen Cookie sitzung_demo"
# Beim Import legt die App im eigenen Ordner eine LEERE elo.db und leere media/-Ordner an
# (vor dem Umschalten auf die temporaere Demo-Datenbank). Das ist normal; echte Daten waeren es nicht.
ECHT="$("${SSH[@]}" "cd \"\$HOME/$DIR\" && { find media -type f 2>/dev/null; ls .env .session_secret 2>/dev/null; } | wc -l; \
  [ -f elo.db ] && $PYBIN -c \"import sqlite3; c = sqlite3.connect('file:elo.db?mode=ro', uri=True); print(sum(c.execute('select count(*) from '+t).fetchone()[0] for t in ('spieler','benutzer','nutzung')))\" || echo 0" | awk '{s += $1} END {print s + 0}')"
[ "$ECHT" = 0 ] || abbruch "Im Demo-Ordner liegen Daten (Medien, .env oder gefuellte elo.db): $ECHT"
echo "  Demo-Ordner enthaelt keine Daten (elo.db leer, keine Medien, keine .env)"
prod_ok

printf '\n== Fertig: Demo %s laeuft ==\n' "$SOLL"
echo "Adresse (Heimnetz): http://${DEPLOY_HOST#*@}:$PORT      Logins: Trainer / 1111   Lena / 2222"
echo "Zuruecksetzen: ssh $DEPLOY_HOST 'systemctl --user restart $SERVICE'     Entfernen: bash deploy_demo.sh --entfernen"
