"""Tests fuer die versionierten Schema-Migrationen (daten/migrationen.py).

Laeuft gegen temporaere Datenbanken - die echte elo.db bleibt unberuehrt.
Start:  py tests/migration_test.py
"""
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402
from daten import migrationen  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="migration_test_"))


def neue_db(name: str) -> sqlite3.Connection:
    return db.verbinde(tmp / name)


def spalten(conn, tabelle):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({tabelle})")}


def version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


# ------------------------------------------------------------ Grundregeln ----
nummern = [nr for nr, _, _ in migrationen.MIGRATIONEN]
assert nummern == list(range(1, len(nummern) + 1)), "Nummern fortlaufend ab 1, ohne Luecken"
assert migrationen.letzte_version() == len(nummern)
print("ok Nummern fortlaufend")

# ------------------------------------------------------ frische Datenbank ----
c = neue_db("frisch.db")
assert version(c) == 0
db.init_db(c)
assert version(c) == migrationen.letzte_version(), "frische DB steht auf der letzten Version"
assert {"portrait_v", "portrait_modus", "position_angriff"} <= spalten(c, "spieler")
assert {"art", "gegner", "heim", "abfahrt"} <= spalten(c, "trainings")
print("ok frische Datenbank")

# ------------------------------------------------- Wiederholen ist harmlos ----
sid = db.spieler_anlegen(c, "Anna")
assert db.init_db(c) is None
assert version(c) == migrationen.letzte_version()
assert c.execute("SELECT COUNT(*) FROM spieler").fetchone()[0] == 1, "Daten bleiben"
assert migrationen.migriere(c) == [], "zweiter Lauf: nichts zu tun"
print("ok idempotent, Daten bleiben")

# ---------- Bestands-DB (wie der Server vor v0.70.1: user_version 0, alles da) ----
c.execute("PRAGMA user_version = 0")
db.init_db(c)
assert version(c) == migrationen.letzte_version(), "Bestands-DB holt die Version nach"
assert c.execute("SELECT name FROM spieler WHERE id = ?", (sid,)).fetchone()["name"] == "Anna"
print("ok Bestands-DB ohne Version")

# --------------------------- aeltere DB: Spalten fehlen noch, werden ergaenzt ----
if sqlite3.sqlite_version_info >= (3, 35):          # DROP COLUMN gibt es erst ab 3.35
    c.execute("ALTER TABLE trainings DROP COLUMN abfahrt")
    c.execute("ALTER TABLE spieler DROP COLUMN portrait_v")
    c.execute("PRAGMA user_version = 0")
    c.commit()
    assert "abfahrt" not in spalten(c, "trainings")
    db.init_db(c)
    assert "abfahrt" in spalten(c, "trainings") and "portrait_v" in spalten(c, "spieler")
    assert version(c) == migrationen.letzte_version()
    print("ok fehlende Spalten werden nachgezogen")
else:
    print("uebersprungen: SQLite zu alt fuer DROP COLUMN")

# -------------------------------------------------- Fehlschlag rollt zurueck ----
vorher = list(migrationen.MIGRATIONEN)


def kaputt(conn):
    conn.execute("ALTER TABLE spieler ADD COLUMN halbfertig TEXT")
    raise ValueError("absichtlich")


def gut(conn):
    conn.execute("ALTER TABLE spieler ADD COLUMN neu_gut TEXT")
    conn.execute("UPDATE spieler SET neu_gut = 'ja'")


start = migrationen.letzte_version()
migrationen.MIGRATIONEN = vorher + [(start + 1, "kaputt", kaputt)]
try:
    try:
        migrationen.migriere(c)
        raise AssertionError("haette fehlschlagen muessen")
    except RuntimeError as e:
        assert "Migration %03d" % (start + 1) in str(e) and "kaputt" in str(e), str(e)
    assert version(c) == start, "Version bleibt auf dem alten Stand"
    assert "halbfertig" not in spalten(c, "spieler"), "auch die DDL-Aenderung ist zurueckgerollt"
    assert not c.in_transaction, "keine offene Transaktion zurueckgelassen"
    print("ok Fehlschlag: Version und Schema unveraendert")

    # Danach geht es mit einer funktionierenden Migration an derselben Stelle weiter.
    migrationen.MIGRATIONEN = vorher + [(start + 1, "gut", gut)]
    assert migrationen.migriere(c) == [start + 1]
    assert version(c) == start + 1
    assert c.execute("SELECT neu_gut FROM spieler").fetchone()[0] == "ja"
    print("ok nach Fehlschlag laeuft die naechste Fassung durch")

    # Datenbank neuer als der Code (z. B. nach einem Rollback des Codes): nichts anfassen.
    migrationen.MIGRATIONEN = vorher
    assert version(c) == start + 1 > migrationen.letzte_version()
    assert migrationen.migriere(c) == []
    assert version(c) == start + 1, "keine Herabstufung"
    db.init_db(c)
    print("ok neuere Datenbank bleibt unangetastet")
finally:
    migrationen.MIGRATIONEN = vorher

# ------------------------------- zwei Verbindungen: nur einer wendet an ----
a, b = neue_db("zwei.db"), neue_db("zwei.db")
db.init_db(a)
assert version(b) == migrationen.letzte_version()
assert migrationen.migriere(b) == []
print("ok zweite Verbindung sieht den Stand der ersten")

print("alle Migrationstests ok")
