"""Tests fuer den SpielerPlus-Import und das Wochenmuster (ohne Netz).

Prueft vor allem die Source-of-Truth-Regel: Eingaben aus der App/vom Trainer
werden vom Import nie ueberschrieben. Temporaere DB, die echte elo.db bleibt unberuehrt.
Start:  py tests/sp_import_test.py
"""
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
import sp_import  # noqa: E402
import trainings_termine  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="sp_import_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna", spielerplus_id="101")
bea = db.spieler_anlegen(conn, "Bea", spielerplus_id="102")
cleo = db.spieler_anlegen(conn, "Cleo", spielerplus_id="103")
dora = db.spieler_anlegen(conn, "Dora", spielerplus_id="104")
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)


def status(tid, sid):
    r = conn.execute("SELECT status, quelle FROM training_teilnahme "
                     "WHERE training_id=? AND spieler_id=?", (tid, sid)).fetchone()
    return (r["status"], r["quelle"]) if r else None


def termin(event_id="900", datum="2026-10-26", **gruppen):
    g = {k: [] for k in ("zugesagt", "abgesagt", "unsicher", "offen", "nicht_nominiert")}
    for k, v in gruppen.items():
        g[k] = [{"name": f"U{u}", "user_id": u} for u in v]
    return {"event_id": event_id, "datum": datum, "beginn": "20:00", "treffen": "19:45",
            "titel": "Training", "gruppen": g}


# --- Wochenmuster ----------------------------------------------------------
assert sorted(trainings_termine.REGELN) == [0, 3], "nur Montag und Donnerstag"
e = trainings_termine.anlegen(conn, date(2026, 10, 23), date(2026, 10, 30))   # Fr..Fr
assert [x["datum"] for x in e] == ["2026-10-26", "2026-10-29"], e
assert all(x["aktion"] == "neu" for x in e)
conn.commit()
mo = conn.execute("SELECT id FROM trainings WHERE datum='2026-10-26'").fetchone()["id"]
conn.execute("UPDATE trainings SET titel='Sondertraining', uhrzeit='19:00' WHERE id=?", (mo,))
e = trainings_termine.anlegen(conn, date(2026, 10, 26), date(2026, 10, 26))
assert e[0]["aktion"] == "akt"
r = conn.execute("SELECT titel, uhrzeit, ort FROM trainings WHERE id=?", (mo,)).fetchone()
assert (r["titel"], r["uhrzeit"], r["ort"]) == ("Sondertraining", "19:00", "Gerhausen"), dict(r)
assert conn.execute("SELECT COUNT(*) c FROM trainings").fetchone()["c"] == 2     # kein Duplikat
print("ok Wochenmuster")

# --- Import: Verknuepfung per Datum + Spiegeln --------------------------------
s = sp_import.uebernehme(conn, [termin(zugesagt=[101, 102, 999], abgesagt=[103], offen=[104])])
assert s["verknuepft"] == 1 and s["trainings_neu"] == 0, s
assert conn.execute("SELECT spielerplus_event_id e FROM trainings WHERE id=?", (mo,)).fetchone()["e"] == "900"
assert status(mo, anna) == ("anwesend", "spielerplus")
assert status(mo, cleo) == ("abgesagt", "spielerplus")
assert status(mo, dora) is None
assert s["eingetragen"] == 3 and s["unbekannt"] == ["U999"], s
print("ok Spiegeln + Verknuepfen")

# --- Source of Truth: App/Trainer gewinnen -----------------------------------
db.teilnahme_setzen(conn, mo, bea, "abgesagt", "krank", quelle="app")
db.teilnahme_setzen(conn, mo, dora, "anwesend", None, quelle="trainer")
s = sp_import.uebernehme(conn, [termin(zugesagt=[101, 102, 104], abgesagt=[103])])
assert status(mo, bea) == ("abgesagt", "app"), "App-Antwort darf nicht ueberschrieben werden"
assert status(mo, dora) == ("anwesend", "trainer")
assert s["manuell_behalten"] == 2, s
print("ok App/Trainer bleiben")

# --- SpielerPlus-Aenderung wird gespiegelt, 'offen' entfernt nur Gespiegeltes --
s = sp_import.uebernehme(conn, [termin(zugesagt=[103], offen=[101, 102, 104])])
assert status(mo, cleo) == ("anwesend", "spielerplus")
assert status(mo, anna) is None and s["entfernt"] == 1, s
assert status(mo, bea) == ("abgesagt", "app") and status(mo, dora) == ("anwesend", "trainer")
print("ok Aenderung + Entfernen")

# --- Parser-Schutz: leere Antwort loescht nichts --------------------------------
s = sp_import.uebernehme(conn, [termin()])
assert s["leer_uebersprungen"] == 1 and status(mo, cleo) == ("anwesend", "spielerplus"), s
print("ok leere Antwort uebersprungen")

# --- Unbekanntes Training wird angelegt, zweiter Termin am Tag nicht verquickt --
s = sp_import.uebernehme(conn, [termin("901", "2026-11-03", zugesagt=[101])])
assert s["trainings_neu"] == 1
neu = conn.execute("SELECT id FROM trainings WHERE spielerplus_event_id='901'").fetchone()["id"]
assert status(neu, anna) == ("anwesend", "spielerplus")
s = sp_import.uebernehme(conn, [termin("902", "2026-11-03", zugesagt=[102])])
assert s["doppelt_uebersprungen"] == 1 and status(neu, bea) is None, s
print("ok neues Training / zweiter Termin")

# --- Idempotenz -----------------------------------------------------------------
vorher = conn.execute("SELECT COUNT(*) c FROM training_teilnahme").fetchone()["c"]
sp_import.uebernehme(conn, [termin(zugesagt=[103], offen=[101, 102, 104])])
assert conn.execute("SELECT COUNT(*) c FROM training_teilnahme").fetchone()["c"] == vorher
print("ok idempotent")

# --- Trocken-Lauf schreibt nichts -------------------------------------------------
sp_import.uebernehme(conn, [termin("903", "2026-11-09", zugesagt=[101])], trocken=True)
assert conn.execute("SELECT COUNT(*) c FROM trainings WHERE datum='2026-11-09'").fetchone()["c"] == 0
print("ok trocken")

# --- Endpunkt ---------------------------------------------------------------------
conn.close()
sp_import.hole_von_spielerplus = lambda tage=14, heute=None: [termin("900", zugesagt=[101])]


def client(name, pin):
    c = TestClient(balu.app)
    assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


assert client("Anna", "2222").post("/api/spielerplus-abgleich").status_code == 403
T = client("Trainer", "1111")
r = T.post("/api/spielerplus-abgleich")
assert r.status_code == 200 and r.json()["eingetragen"] == 1, r.text
assert T.post("/api/spielerplus-abgleich").status_code == 429, "Mindestabstand"
print("ok Endpunkt (Rolle, Mindestabstand)")

balu._sp_zuletzt = 0.0


def kaputt(tage=14, heute=None):
    raise sp_import.SpielerPlusFehler("Login fehlgeschlagen")


sp_import.hole_von_spielerplus = kaputt
r = T.post("/api/spielerplus-abgleich")
assert r.status_code == 502 and "Login" in r.json()["detail"], r.text
print("ok Fehlerfall -> 502")
print("\nalle SpielerPlus-Import-Tests gruen")
