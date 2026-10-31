"""Tests: Playbook-Seiten (Spielzuege) werden beim Loeschen ARCHIVIERT.

Der Name bleibt erhalten, Text und Ansicht werden entfernt; Spielerinnen koennen nichts
loeschen; alte Spiele zeigen den Spielzug weiter richtig an (der Name ist dort kopiert).
Alle anderen Kategorien (Gegner, Notizen ...) werden wie bisher wirklich geloescht.
Start:  py tests/playbook_test.py
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="playbook_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)
gruppe = db.seite_anlegen(conn, "Allgemeine Spielzuege", "playbook", None, "Unsere Standards.")
kreisel = db.seite_anlegen(conn, "Kreisel", "playbook", gruppe, "Mitte spielt auf Halblinks.")
welle = db.seite_anlegen(conn, "2te Welle", "playbook", gruppe, "Schnell nach vorne.")
gegner = db.seite_anlegen(conn, "HSG Beispiel", "gegner", None, "Steht tief.")
# Ein altes Spiel, in dem "Kreisel" gespielt wurde (der Name steht als Kopie im Spiel)
aid = db.analyse_speichern(
    conn, "ext-alt", "HSG", "2026-09-14", "Liga", [],
    [{"name": "Kreisel", "t_start": 100.0, "t_ende": 112.0, "ampel": "gruen", "key": "z1",
      "spieler_ids": [anna]}], None)
db.szene_clip_speichern(conn, aid, "z1", "z1.mp4", 90.0, 120.0)
conn.close()


def client(name=None, pin=None):
    c = TestClient(balu.app)
    if name:
        assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def zeile(sid):
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    r = c.execute("SELECT * FROM seiten WHERE id = ?", (sid,)).fetchone()
    c.close()
    return r


def titel(c, kategorie="playbook"):
    return [s["titel"] for s in c.get(f"/api/seiten?kategorie={kategorie}").json()]


T, A, ANON = client("Trainer", "1111"), client("Anna", "2222"), client()

# --- Rechte: nur der Trainer darf loeschen
check(A.post(f"/api/seiten/{kreisel}/loeschen").status_code == 403, "Spielerin darf keinen Spielzug loeschen")
check(ANON.post(f"/api/seiten/{kreisel}/loeschen").status_code == 401, "Ohne Anmeldung: 401")
check("Kreisel" in titel(A), "Nach dem Versuch ist der Spielzug unveraendert da")

# --- Loeschen = Archivieren
check(T.post(f"/api/seiten/{kreisel}/loeschen").status_code == 200, "Trainer loescht den Spielzug")
r = zeile(kreisel)
check(r is not None and r["titel"] == "Kreisel", "Der Name bleibt in der Datenbank erhalten")
check(r["markdown"] is None, "Text und Ansicht sind entfernt")
check(r["kategorie"] == "archiv" and r["parent_id"] is None, "Die Seite liegt im Archiv")
check("Kreisel" not in titel(T) and "Kreisel" not in titel(A), "Aus dem Playbook ist er fuer alle verschwunden")
check("2te Welle" in titel(A), "Andere Spielzuege bleiben")
check(T.get(f"/api/seiten/{kreisel}").status_code == 404 and A.get(f"/api/seiten/{kreisel}").status_code == 404,
      "Die archivierte Seite ist weder aufruf- noch lesbar (wie geloescht)")
check(T.post(f"/api/seiten/{kreisel}", json={"markdown": "neu"}).status_code == 404,
      "Eine archivierte Seite laesst sich nicht mehr bearbeiten")
check(zeile(kreisel)["markdown"] is None, "... und der Text bleibt weg")
check("Kreisel" in titel(T, "archiv"), "Der Trainer sieht den archivierten Namen unter Kategorie 'archiv'")
check(A.get("/api/seiten?kategorie=archiv").status_code == 403, "Das Archiv ist fuer Spielerinnen gesperrt")
check("Kreisel" not in [s["titel"] for s in T.get("/api/seiten").json()],
      "Die ungefilterte Liste zeigt keine archivierten Seiten")
check(T.post(f"/api/seiten/{kreisel}/loeschen").status_code == 200 and zeile(kreisel)["kategorie"] == "archiv",
      "Nochmal loeschen (Outbox-Wiederholung) ist harmlos")

# --- Alte Spiele zeigen den Namen weiter
sz = T.get("/api/szenen-uebersicht").json()["spiele"][0]["szenen"][0]
check(sz["label"] == "Spielzug Kreisel" and sz["name"] == "Kreisel",
      "Altes Spiel: Der Spielzug heisst weiter 'Kreisel', auch nach dem Archivieren")

# --- Gruppe archivieren: Unterseiten ruecken hoch und bleiben sichtbar
check(T.post(f"/api/seiten/{gruppe}/loeschen").status_code == 200, "Gruppe loeschen")
check(zeile(gruppe)["kategorie"] == "archiv" and zeile(welle)["parent_id"] is None
      and zeile(welle)["kategorie"] == "playbook" and zeile(welle)["markdown"] == "Schnell nach vorne.",
      "Unterseiten bleiben mit Text erhalten und ruecken eine Ebene hoch")
check("2te Welle" in titel(A) and "Allgemeine Spielzuege" not in titel(A), "Nur die Gruppe verschwindet")

# --- Andere Kategorien werden wirklich geloescht
check(T.post(f"/api/seiten/{gegner}/loeschen").status_code == 200 and zeile(gegner) is None,
      "Gegner-Seiten werden wie bisher richtig geloescht")

# --- Neuer Spielzug mit demselben Namen
r = T.post("/api/seiten", json={"titel": "Kreisel", "kategorie": "playbook", "markdown": "Neue Variante"})
check(r.status_code == 200, "Ein neuer 'Kreisel' laesst sich anlegen")
check(titel(A).count("Kreisel") == 1 and titel(T, "archiv").count("Kreisel") == 1,
      "Es gibt einen aktiven Kreisel und den alten im Archiv - ohne Verwechslung")

print("\nAlle Tests gruen.")
