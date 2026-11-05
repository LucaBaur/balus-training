#!/usr/bin/env bash
# Deploy von Balu's Training -> Homeserver.
#
#   bash deploy.sh [Beschreibung]    testen, sichern, hochladen, neu starten, pruefen
#   bash deploy.sh --trocken         nur testen und anzeigen, was hochgeladen wuerde
#   bash deploy.sh --neustart        Dienst auch dann neu starten, wenn nur static/ neu ist
#
# "Beschreibung" (z. B. "kommentare") steht danach im Namen der Backups:
#   datei.bak-<Datum>-<Uhrzeit>-vor-<Beschreibung>
#
# Ablauf: 1 Tests (nur bei Gruen weiter) -> 2 Vergleich mit dem Server (nur Geaendertes) ->
#         3 Backup auf dem Server (bei Backend-Aenderung auch elo.db) -> 4 Hochladen ->
#         5 Neustart + Pruefung. Schlaegt nach dem Hochladen etwas fehl, werden die
#         gesicherten Dateien automatisch zurueckgespielt.
#
# Server-Daten stehen in deploy.env (nicht im Repo, Vorlage: deploy.env.example).
# Die Datenbank (elo.db), media/ und .env werden nie hochgeladen.
set -euo pipefail
cd "$(dirname "$0")"

TROCKEN=0; NEUSTART=0; LABEL="deploy"
for a in "$@"; do
  case "$a" in
    --trocken)  TROCKEN=1 ;;
    --neustart) NEUSTART=1 ;;
    -*)         echo "Unbekannte Option: $a"; exit 2 ;;
    *)          LABEL="$(printf '%s' "$a" | tr -c 'A-Za-z0-9_-' '-')" ;;
  esac
done

if [ ! -f deploy.env ]; then
  echo "deploy.env fehlt - Vorlage: cp deploy.env.example deploy.env und ausfuellen."
  exit 1
fi
# shellcheck disable=SC1091
source deploy.env
: "${DEPLOY_HOST:?DEPLOY_HOST fehlt in deploy.env}"
DIR="${DEPLOY_DIR:-elo}"                       # relativ zum Home-Verzeichnis auf dem Server
SERVICE="${DEPLOY_SERVICE:-elo}"
URL="${DEPLOY_URL:-http://127.0.0.1:8200}"     # wird auf dem Server selbst abgefragt

if command -v py >/dev/null 2>&1; then PY=py; else PY=python3; fi
STAMP="$(date +%Y%m%d-%H%M)-vor-$LABEL"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=8 "$DEPLOY_HOST")

schritt() { printf '\n== %s ==\n' "$1"; }
abbruch() { printf '\nABBRUCH: %s\n' "$1"; exit 1; }

# ------------------------------------------------------------------ 1 Tests ----
schritt "1/5 Tests"
for f in static/*.js; do
  node --check "$f" || abbruch "Syntaxfehler in $f"
done
echo "  ok  JavaScript-Syntax"
for t in tests/*.test.mjs; do
  out="$(node "$t" 2>&1)" || { echo "$out"; abbruch "Test fehlgeschlagen: $t"; }
  echo "  ok  $t"
done
for t in tests/*_test.py; do
  out="$("$PY" "$t" 2>&1)" || { echo "$out" | tail -15; abbruch "Test fehlgeschlagen: $t"; }
  echo "  ok  $t"
done

# --------------------------------------------------- 2 Vergleich mit dem Server ----
schritt "2/5 Vergleich mit dem Server"
"${SSH[@]}" true 2>/dev/null || abbruch "Server $DEPLOY_HOST nicht erreichbar (Heimnetz? SSH-Schluessel?)"

shopt -s nullglob
DATEIEN=(*.py daten/*.py routen/*.py requirements.txt CHANGELOG.md README.md
         static/*.js static/*.css static/*.html static/*.webmanifest static/*.png static/*.svg static/portraits/*)
shopt -u nullglob

normal() { sed 's/^\([0-9a-f]\{32\}\) [ *]/\1 /'; }       # "hash *name" / "hash  name" -> "hash name"
declare -A LOKAL REMOTE
while read -r h n; do LOKAL["$n"]="$h"; done < <(md5sum -- "${DATEIEN[@]}" | normal)
while read -r h n; do REMOTE["$n"]="$h"; done < <("${SSH[@]}" "cd '$DIR' && md5sum -- ${DATEIEN[*]} 2>/dev/null" | normal)

NEU=(); GEAENDERT=(); BACKEND=0
for f in "${DATEIEN[@]}"; do
  if [ -z "${REMOTE[$f]:-}" ]; then
    NEU+=("$f")
  elif [ "${LOKAL[$f]}" != "${REMOTE[$f]}" ]; then
    GEAENDERT+=("$f")
  else
    continue
  fi
  case "$f" in *.py|requirements.txt) BACKEND=1 ;; esac
done
ZU_LADEN=("${GEAENDERT[@]}" "${NEU[@]}")

if [ ${#ZU_LADEN[@]} -eq 0 ]; then
  echo "  Server und lokaler Stand sind identisch - nichts zu tun."
  exit 0
fi
for f in "${GEAENDERT[@]}"; do echo "  geaendert  $f"; done
for f in "${NEU[@]}";       do echo "  neu        $f"; done
[ $BACKEND -eq 1 ] && echo "  -> Backend-Code dabei: Datenbank wird gesichert, Dienst startet neu."
for f in "${ZU_LADEN[@]}"; do
  [ "$f" = requirements.txt ] && echo "  HINWEIS: requirements.txt hat sich geaendert - neue Pakete auf dem Server selbst installieren."
done

if [ $TROCKEN -eq 1 ]; then
  printf '\n== Trockenlauf: nichts auf den Server geschrieben ==\n'
  exit 0
fi

# ------------------------------------------------------------------ 3 Backup ----
schritt "3/5 Backup auf dem Server ($STAMP)"
if [ ${#GEAENDERT[@]} -gt 0 ]; then
  "${SSH[@]}" "cd '$DIR' && for f in ${GEAENDERT[*]}; do cp -p \"\$f\" \"\$f.bak-$STAMP\"; done"
  echo "  ${#GEAENDERT[@]} Datei(en) gesichert"
fi
if [ $BACKEND -eq 1 ]; then
  "${SSH[@]}" "cd '$DIR' && python3 -" <<PYEOF
import sqlite3
s = sqlite3.connect("elo.db"); d = sqlite3.connect("elo.db.bak-$STAMP")
s.backup(d); d.close(); s.close()
r = sqlite3.connect("elo.db.bak-$STAMP").execute("pragma integrity_check").fetchone()[0]
assert r == "ok", r
print("  elo.db gesichert (integrity_check: ok)")
PYEOF
fi

# ------------------------------------------------- Rueckspielen bei Fehlern ----
zurueck() {
  trap - ERR
  set +e
  printf '\n!! Fehler nach dem Hochladen - spiele die gesicherten Dateien zurueck.\n'
  if [ ${#GEAENDERT[@]} -gt 0 ]; then
    "${SSH[@]}" "cd '$DIR' && for f in ${GEAENDERT[*]}; do cp -p \"\$f.bak-$STAMP\" \"\$f\"; done"
  fi
  if [ $BACKEND -eq 1 ] || [ $NEUSTART -eq 1 ]; then
    "${SSH[@]}" "export XDG_RUNTIME_DIR=/run/user/\$(id -u); systemctl --user restart $SERVICE; sleep 3; systemctl --user is-active $SERVICE"
  fi
  [ ${#NEU[@]} -gt 0 ] && echo "   Neu angelegte Dateien bleiben liegen (harmlos): ${NEU[*]}"
  echo "   Zurueckgespielt."
  [ $BACKEND -eq 1 ] && echo "   Datenbank-Backup dieses Laufs (falls noetig): $DIR/elo.db.bak-$STAMP"
  exit 1
}
trap zurueck ERR

# ---------------------------------------------------------------- 4 Hochladen ----
schritt "4/5 Hochladen"
# static/ zuerst, Backend zuletzt: der Neustart kommt erst, wenn alles Passende da ist.
"${SSH[@]}" "cd '$DIR' && mkdir -p daten routen"      # Pakete db (daten/) und app (routen/) beim ersten Mal anlegen
for f in "${ZU_LADEN[@]}"; do case "$f" in static/*) scp -qp "$f" "$DEPLOY_HOST:$DIR/$f"; echo "  hoch  $f" ;; esac; done
for f in "${ZU_LADEN[@]}"; do case "$f" in static/*) ;; *) scp -qp "$f" "$DEPLOY_HOST:$DIR/$f"; echo "  hoch  $f" ;; esac; done

while read -r h n; do
  [ "${LOKAL[$n]}" = "$h" ] || { echo "  Pruefsumme stimmt nicht: $n"; false; }
done < <("${SSH[@]}" "cd '$DIR' && md5sum -- ${ZU_LADEN[*]}" | normal)
echo "  ${#ZU_LADEN[@]} Datei(en) angekommen, Pruefsummen stimmen"

# ----------------------------------------------------- 5 Neustart + Pruefung ----
schritt "5/5 Neustart und Pruefung"
if [ $BACKEND -eq 1 ] || [ $NEUSTART -eq 1 ]; then
  STATUS="$("${SSH[@]}" "export XDG_RUNTIME_DIR=/run/user/\$(id -u); systemctl --user restart $SERVICE; sleep 3; systemctl --user is-active $SERVICE" || true)"
  if [ "$STATUS" != active ]; then echo "  Dienst $SERVICE ist nicht aktiv (Status: $STATUS)"; false; fi
  echo "  Dienst $SERVICE laeuft"
else
  echo "  nur static/ - kein Neustart noetig"
fi

SOLL="$(grep -o 'APP_VERSION = "[^"]*"' static/app.js | cut -d'"' -f2)"
IST="$("${SSH[@]}" "curl -s --max-time 10 '$URL/app.js'" | grep -o 'APP_VERSION = "[^"]*"' | cut -d'"' -f2)"
CODE="$("${SSH[@]}" "curl -s --max-time 10 -o /dev/null -w '%{http_code}' '$URL/'")"
[ "${DEPLOY_SIMULIERE_FEHLER:-}" = 1 ] && IST="simulierter-fehler"      # nur zum Testen des Rueckspielens
echo "  Startseite: HTTP $CODE   App-Version ausgeliefert: $IST (lokal: $SOLL)"
if [ "$CODE" != 200 ] || [ "$IST" != "$SOLL" ]; then echo "  Pruefung fehlgeschlagen"; false; fi   # false -> ERR-Trap -> zurueck

trap - ERR
printf '\n== Fertig: %s deployt ==\n' "$SOLL"
echo "Zurueckrollen: ssh $DEPLOY_HOST \"cd $DIR && cp -p <datei>.bak-$STAMP <datei>\" und Dienst neu starten."
echo "Backups auf dem Server: $("${SSH[@]}" "cd '$DIR' && ls *.bak-* static/*.bak-* 2>/dev/null | wc -l") Dateien (werden nicht automatisch geloescht)."
echo "Falls es eine Demo-Instanz gibt: die hat noch den alten Code - mit  bash deploy_demo.sh  nachziehen."
