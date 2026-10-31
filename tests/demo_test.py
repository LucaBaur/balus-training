"""Tests fuer die Demo-Instanz (docs/anleitung-funktionen/demo_server.py).

Die Demo laeuft auf dem Server NEBEN der echten App (Port 8201, eigener Ordner,
eigene Datenbank). Damit sie ihr nicht in die Quere kommt, muss gelten:
  - eigener Sitzungs-Cookie (Cookies gelten pro Host, nicht pro Port - sonst wuerde
    eine Anmeldung in der Demo die echte Anmeldung im selben Browser ueberschreiben),
  - Host, Port und Geheimnis kommen aus der Umgebung,
  - das Demo-Team ist erfunden und zeigt die unterscheidbaren Spielzuege.
Jeder Pruefschritt laeuft in einem eigenen Prozess, weil die Module beim Import
Umgebungsvariablen lesen.
Start:  py tests/demo_test.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

BASIS = Path(__file__).resolve().parent.parent


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def lauf(code: str, **env) -> str:
    """Fuehrt `code` in einem frischen Python im Projektordner aus, mit zusaetzlicher Umgebung."""
    umgebung = {k: v for k, v in os.environ.items()
                if k not in ("SESSION_COOKIE", "APP_SECRET", "DEMO_HOST", "DEMO_PORT")}
    umgebung.update(env)
    r = subprocess.run([sys.executable, "-c", code], cwd=BASIS, env=umgebung,
                       capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout[-800:], r.stderr[-1500:])
        sys.exit(1)
    return r.stdout.strip().splitlines()[-1]


# ------------------------------------------------------------- Cookie-Name ----
check(lauf("import auth; print(auth.COOKIE_NAME)") == "sitzung",
      "Echte App: Cookie heisst weiter 'sitzung' (bestehende Anmeldungen bleiben gueltig)")
check(lauf("import auth; print(auth.COOKIE_NAME)", SESSION_COOKIE="sitzung_demo") == "sitzung_demo",
      "SESSION_COOKIE aendert den Cookie-Namen (Demo)")

# ---------------------------------------------------- Einstellungen der Demo ----
EINSTELLUNG = ("import sys; sys.path.insert(0, 'docs/anleitung-funktionen'); import demo_server as d, os; "
               "print(d.HOST, d.PORT, os.environ['APP_SECRET'])")
host, port, geheim = lauf(EINSTELLUNG).split()
check((host, port) == ("127.0.0.1", "8299"), "Demo lokal: nur 127.0.0.1, Port 8299 (wie bisher)")
host, port, geheim = lauf(EINSTELLUNG, DEMO_HOST="0.0.0.0", DEMO_PORT="8201", APP_SECRET="zufall-123").split()
check((host, port, geheim) == ("0.0.0.0", "8201", "zufall-123"),
      "Server: Host, Port und Geheimnis kommen aus der Umgebung")

# --------------------------------------------------------------- Demo-Daten ----
DATEN = r"""
import json, sys
sys.path.insert(0, 'docs/anleitung-funktionen')
import demo_server as d
d.seed()
from fastapi.testclient import TestClient
c = TestClient(d.balu.app)
assert c.post('/api/login', json={'name': 'Trainer', 'pin': '1111'}).status_code == 200
n = c.get('/api/nutzung').json()
u = c.get('/api/szenen-uebersicht').json()['spiele']
zuege = [s for g in u for s in g['szenen'] if s['art'] == 'zug']
lena = next(k for k in n['konten'] if k['name'] == 'Lena')
zustaende = set()
for s in zuege:
    for name in s['beteiligt']:
        g = next((x for x in s['gesehen'] if x['name'] == name), None)
        zustaende.add('offen' if not g else 'komplett' if g['gespielt'] else 'angetippt')
print(json.dumps({
    'spiele': len(u), 'ids': sorted(s['id'] for s in zuege),
    'kreisel': [s['id'] + ' ' + s['zeit'] for s in zuege if s['label'] == 'Spielzug Kreisel'],
    'namen': sorted({s['name'] for s in zuege}), 'zustaende': sorted(zustaende),
    'lena_sek': lena['sekunden_gesamt'], 'lena_offen': lena['offen'],
    'konten': sorted(k['name'] for k in n['konten'])}))
"""
d = json.loads(lauf(DATEN))
check(d["spiele"] == 2, "Demo-Team: zwei Spiele")
check(len(d["ids"]) == len(set(d["ids"])), "Demo-Team: alle Spielzug-IDs sind eindeutig (auch bei gleicher Kennung in zwei Spielen)")
check(len(d["kreisel"]) >= 3 and len({k.split()[0] for k in d["kreisel"]}) == len(d["kreisel"]),
      "Demo-Team: mehrere 'Kreisel' sind per ID unterscheidbar")
check({"Kreisel", "2. Welle"} <= set(d["namen"]), "Demo-Team: Namen zum Filtern ('Kreisel', '2. Welle')")
check(d["zustaende"] == ["angetippt", "komplett", "offen"], "Demo-Team: alle drei Zustaende kommen vor")
check(d["lena_sek"] > 0 and d["lena_offen"] > 0, "Demo-Team: Verweildauer befuellt, Lena hat Offenes")
check("Lena" in d["konten"] and "Trainer" not in d["konten"], "Demo-Team: erfundene Spielerinnen, Trainer zaehlt nicht")

print("\nAlle Tests gruen.")
