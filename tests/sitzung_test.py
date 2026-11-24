"""Tests fuer widerrufbare Sitzungen ("Auf allen Geraeten abmelden").

Das Anmelde-Cookie ist signiert und enthaelt keine Daten vom Server - ein gestohlenes oder verlorenes Handy
blieb deshalb bis zu 60 Tage angemeldet; nur das Wechseln des Geheimschluessels haette es beendet (und dabei
ALLE abgemeldet). Jetzt traegt das Cookie die Sitzungs-Version des Kontos (`sv`). Stimmt sie nicht mehr mit
der in der Datenbank ueberein, ist das Cookie wertlos. Hochgezaehlt wird beim Neusetzen der PIN und bei
"Auf allen Geraeten abmelden". Alte Cookies ohne `sv` gelten als Version 0 und bleiben gueltig, damit
niemand beim Einspielen der neuen Version abgemeldet wird.

Alle Namen sind erfunden. Laeuft gegen eine temporaere Datenbank. Start:  py tests/sitzung_test.py
"""
import base64
import hashlib
import hmac
import json
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
from daten import migrationen  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="sitzung_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
mia = db.spieler_anlegen(conn, "Mia")
trainer_id = db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
mia_id = db.benutzer_anlegen(conn, "Mia", "spieler", auth.hash_pin("2222"), mia)
bea_id = db.benutzer_anlegen(conn, "Bea", "spieler", auth.hash_pin("3333"), None)
conn.close()


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def anmelden(name, pin):
    c = TestClient(balu.app)
    r = c.post("/api/login", json={"name": name, "pin": pin})
    assert r.status_code == 200, (name, r.text)
    return c


def geraet_mit(cookie):
    """Ein zweites Geraet, das denselben Cookie-Wert hat (Kopie)."""
    c = TestClient(balu.app)
    c.cookies.set(auth.COOKIE_NAME, cookie)
    return c


def cookie_von(c):
    return c.cookies.get(auth.COOKIE_NAME)


def version_in_db(bid):
    d = db.verbinde()
    try:
        return d.execute("SELECT sitzung_version FROM benutzer WHERE id = ?", (bid,)).fetchone()[0]
    finally:
        d.close()


def alter_cookie(uid):
    """So sah ein Cookie VOR dieser Aenderung aus: ohne 'sv'."""
    payload = auth._b64e(json.dumps({"uid": uid, "iat": int(time.time())}).encode())
    sig = auth._b64e(hmac.new(auth._SECRET, payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{sig}"


# --- Schema und Migration -------------------------------------------------------------------------------------------
c = db.verbinde()
spalten = {r["name"]: r for r in c.execute("PRAGMA table_info(benutzer)")}
check("sitzung_version" in spalten, "benutzer.sitzung_version existiert")
check(spalten["sitzung_version"]["notnull"] == 1 and spalten["sitzung_version"]["dflt_value"] == "0",
      "NOT NULL DEFAULT 0 (alte Konten starten bei 0)")
c.close()

alt = sqlite3.connect(tmp / "alt.db")
alt.row_factory = sqlite3.Row
alt.execute("CREATE TABLE benutzer (id INTEGER PRIMARY KEY, name TEXT)")
alt.execute("INSERT INTO benutzer (name) VALUES ('alt')")
m = {name: fn for _, name, fn in migrationen.MIGRATIONEN}
check("sitzung_version" in m, "Migration 'sitzung_version' ist eingetragen")
m["sitzung_version"](alt)
check(alt.execute("SELECT sitzung_version FROM benutzer").fetchone()[0] == 0, "die Migration ergaenzt die Spalte in einer alten Datenbank (Wert 0)")
m["sitzung_version"](alt)
check(True, "und ist wiederholbar (zweiter Lauf wirft nichts)")
alt.close()

# --- Normalfall -----------------------------------------------------------------------------------------------------
A = anmelden("Mia", "2222")
check(A.get("/api/me").status_code == 200, "angemeldet: /api/me klappt")
daten = auth.session_daten(cookie_von(A))
check(daten.get("sv") == 0, "das Cookie traegt die Sitzungs-Version (sv = 0)")

# --- Alte Cookies bleiben gueltig ---------------------------------------------------------------------------------
check(geraet_mit(alter_cookie(mia_id)).get("/api/me").status_code == 200, "Cookie von VOR der Aenderung (ohne sv) gilt weiter - niemand fliegt beim Deploy raus")

# --- Auf allen Geraeten abmelden ---------------------------------------------------------------------------------
handy = geraet_mit(cookie_von(A))                       # zweites Geraet derselben Person
tablet = geraet_mit(cookie_von(A))
B = anmelden("Bea", "3333")
check(handy.get("/api/me").status_code == 200, "vorher sind beide Geraete angemeldet")

r = A.post("/api/logout-alle")
check(r.status_code == 200, "POST /api/logout-alle klappt")
check(version_in_db(mia_id) == 1, "die Sitzungs-Version in der Datenbank steht jetzt auf 1")
check(handy.get("/api/me").status_code == 401 and tablet.get("/api/me").status_code == 401,
      "die kopierten Cookies (andere Geraete) sind sofort ungueltig (401)")
check(A.get("/api/me").status_code == 401, "auch dieses Geraet ist abgemeldet (Cookie wird geloescht)")
check(B.get("/api/me").status_code == 200, "eine andere Person bleibt angemeldet")
check(version_in_db(bea_id) == 0, "und deren Version ist unveraendert")

A2 = anmelden("Mia", "2222")
check(auth.session_daten(cookie_von(A2)).get("sv") == 1 and A2.get("/api/me").status_code == 200, "neu anmelden: neues Cookie mit sv = 1 funktioniert")
check(geraet_mit(alter_cookie(mia_id)).get("/api/me").status_code == 401, "ein Cookie ohne sv (= Version 0) ist nach dem Abmelden ebenfalls ungueltig")

# --- Nur eine hoehere/niedrigere Version ist nie gueltig -------------------------------------------------------------
zu_hoch = auth.session_erstellen(mia_id, version=5)
check(geraet_mit(zu_hoch).get("/api/me").status_code == 401, "eine ZU HOHE Version wird ebenfalls abgelehnt (Vergleich auf Gleichheit)")

# --- Abmelden ohne Anmeldung ---------------------------------------------------------------------------------------
check(TestClient(balu.app).post("/api/logout-alle").status_code == 401, "ohne Anmeldung: 401")

# --- Neue PIN beendet alte Sitzungen -----------------------------------------------------------------------------------
C = anmelden("Bea", "3333")
altes_geraet = geraet_mit(cookie_von(C))
d = db.verbinde()
db.benutzer_pin_setzen(d, bea_id, auth.hash_pin("4444"))
d.close()
check(version_in_db(bea_id) == 1, "neue PIN zaehlt die Sitzungs-Version hoch")
check(altes_geraet.get("/api/me").status_code == 401 and C.get("/api/me").status_code == 401,
      "alle Sitzungen mit der alten PIN sind beendet")
check(anmelden("Bea", "4444").get("/api/me").status_code == 200, "mit der neuen PIN geht es weiter")

# --- Trainer: Ansicht als Spielerin ------------------------------------------------------------------------------------
T = anmelden("Trainer", "1111")
check(T.post(f"/api/ansicht/{mia_id}").status_code == 200, "Trainer schaltet auf 'Ansicht als Mia'")
check(T.get("/api/me").json()["ansicht_als"] is True, "die Ansicht-Sitzung funktioniert (Cookie traegt die Version des Trainers)")
check(T.post("/api/logout-alle").status_code == 403, "im Ansicht-Modus ist 'Auf allen Geraeten abmelden' gesperrt (Nur-Lesen), es trifft nie das falsche Konto")
check(version_in_db(trainer_id) == 0 and version_in_db(mia_id) == 1, "keine Version hat sich dabei geaendert")
check(T.post("/api/ansicht/stop").status_code == 200 and T.get("/api/me").json()["ansicht_als"] is False, "zurueck zur eigenen Ansicht")

T_zweit = geraet_mit(cookie_von(T))
check(T.post("/api/logout-alle").status_code == 200, "Trainer meldet sich ueberall ab")
check(T_zweit.get("/api/me").status_code == 401, "auch dessen zweites Geraet ist abgemeldet")
T3 = anmelden("Trainer", "1111")
check(T3.post(f"/api/ansicht/{mia_id}").status_code == 200 and T3.get("/api/me").json()["ansicht_als"] is True,
      "nach neuer Anmeldung funktioniert 'Ansicht als' wieder (Version wird im Ansicht-Cookie mitgefuehrt)")
check(T3.post("/api/logout").status_code == 200, "normales Abmelden (nur dieses Geraet) bleibt moeglich")

print("\nalles ok")
