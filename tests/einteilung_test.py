"""Tests fuer "Training uebernehmen" in der Team-Einteilung (native Daten, ohne Anytype).

Temporaere Datenbank; die echte elo.db bleibt unberuehrt.
Start:  py tests/einteilung_test.py
"""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="einteilung_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
anna, bea, cleo, dora = (db.spieler_anlegen(conn, n) for n in ("Anna", "Bea", "Cleo", "Dora"))
db.spieler_aktualisieren(conn, dora, aktiv=False)               # Dora ist ausgetreten
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)

heute = date.today()
d = lambda n: (heute + timedelta(days=n)).isoformat()            # noqa: E731
t_morgen, _ = db.training_anlegen(conn, d(1), "Training Gerhausen")
t_alt, _ = db.training_anlegen(conn, d(-5), "Altes Training")     # ausserhalb des Fensters
t_fern, _ = db.training_anlegen(conn, d(40), "Weit weg")          # ausserhalb des Fensters
spiel, _ = db.training_anlegen(conn, d(2), "Heimspiel", art="ligaspiel", gegner="X", heim=1)
t_leer, _ = db.training_anlegen(conn, d(3), "Ohne Antworten")
for sid, st, quelle in [(anna, "anwesend", "app"), (bea, "anwesend", "spielerplus"),
                        (cleo, "abgesagt", "trainer"), (dora, "anwesend", "spielerplus")]:
    db.teilnahme_setzen(conn, t_morgen, sid, st, "Arbeit" if st == "abgesagt" else None, quelle)
db.teilnahme_setzen(conn, spiel, anna, "anwesend", None, "app")
conn.close()


def client(name, pin):
    c = TestClient(balu.app)
    assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


T, A = client("Trainer", "1111"), client("Anna", "2222")
check(TestClient(balu.app).get("/api/einteilung/trainings").status_code == 401, "ohne Anmeldung gesperrt")
check(A.get("/api/einteilung/trainings").status_code == 403, "Spielerin darf die Einteilung nicht abrufen")

r = T.get("/api/einteilung/trainings")
check(r.status_code == 200, "Trainer bekommt die Liste")
liste = r.json()
ids = [t["id"] for t in liste]
check(t_morgen in ids and t_leer in ids, "Trainings im Fenster sind dabei")
check(t_alt not in ids and t_fern not in ids, "zu altes und zu fernes Training fehlen")
check(spiel not in ids, "Spiele werden nicht eingeteilt")
check(ids == sorted(ids, key=lambda i: next(t["datum"] for t in liste if t["id"] == i)), "nach Datum sortiert")

m = next(t for t in liste if t["id"] == t_morgen)
check(sorted(m["spieler_ids"]) == sorted([anna, bea]), "nur Zusagen und nur aktive Spielerinnen (kein Absager, keine Ausgetretene)")
check(m["anwesend_gesamt"] == 3, "anwesend_gesamt zaehlt alle Zusagen (auch Ausgetretene)")
check(m["label"].startswith("morgen"), "Label wie bisher (\"morgen TT.MM.\")")
leer = next(t for t in liste if t["id"] == t_leer)
check(leer["spieler_ids"] == [] and leer["anwesend_gesamt"] == 0, "Training ohne Antworten: leere Liste")

check(T.get("/api/anytype/trainings").status_code in (404, 405), "alter Anytype-Endpunkt ist entfernt")
print("\nAlle Tests gruen.")
