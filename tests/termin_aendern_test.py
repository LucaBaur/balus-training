"""Tests fuer das Aendern von Trainingszeiten: ein einzelner Termin, und "ab diesem Datum fuer alle
folgenden Trainings dieses Wochentags" samt Wochenmuster. Der Termin bleibt dasselbe Objekt, niemand muss
neu antworten.

Laeuft gegen eine temporaere Datenbank, versendet nichts (push.sende wird abgefangen).
Start:  py tests/termin_aendern_test.py
"""
import sys
import tempfile
import time as _zeit
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import aemter  # noqa: E402
import app as balu  # noqa: E402
import auth  # noqa: E402
import daten.termine as _termine  # noqa: E402
import db  # noqa: E402
import push  # noqa: E402
import trainings_termine  # noqa: E402

_termine.AUTO_ZUSAGE_AB = "2999-12-31"          # hier geht es um die Zeiten, nicht um die automatische Zusage

tmp = Path(tempfile.mkdtemp(prefix="termin_aendern_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
sp = {n: db.spieler_anlegen(conn, n) for n in ("Anna", "Bea", "Rita")}
bu = {}
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
for n, sid in sp.items():
    bu[n] = db.benutzer_anlegen(conn, n, "spieler", auth.hash_pin("2222"), sid)
amt_id = conn.execute("SELECT id FROM amt WHERE schluessel = 'balu_app'").fetchone()["id"]
aemter.inhaber_setzen(conn, amt_id, sp["Rita"], True)         # Amt "Balu-Trainings-App": darf Termine pflegen
conn.close()

gesendet = []        # (benutzer_ids, titel, text, art)
push.sende = lambda conn, ids, titel, text, url="/", art=None: gesendet.append((sorted(ids), titel, text, art)) or {"gesendet": len(ids)}


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def client(name, pin):
    c = TestClient(balu.app)
    assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def warte(anzahl, sek=3.0):
    ende = _zeit.time() + sek
    while len(gesendet) < anzahl and _zeit.time() < ende:
        _zeit.sleep(0.05)


def zeile(tid):
    c = db.verbinde()
    try:
        return dict(c.execute("SELECT * FROM trainings WHERE id = ?", (tid,)).fetchone())
    finally:
        c.close()


def antworten(tid):
    c = db.verbinde()
    try:
        return {r["spieler_id"]: r["status"] for r in c.execute(
            "SELECT spieler_id, status FROM training_teilnahme WHERE training_id = ?", (tid,))}
    finally:
        c.close()


def naechster(wochentag, ab):
    d = ab
    while d.weekday() != wochentag:
        d += timedelta(days=1)
    return d


T, R, A = client("Trainer", "1111"), client("Rita", "2222"), client("Anna", "2222")

# --- Wochenmuster -------------------------------------------------------------------------------------------------
conn = db.verbinde()
check(db.trainings_regeln(conn) == {0: ("20:00", "Gerhausen"), 3: ("20:15", "Blaubeuren")},
      "Wochenmuster: Montag 20:00 Gerhausen, Donnerstag 20:15 Blaubeuren")
conn.close()
r = R.get("/api/training-regeln")
check(r.status_code == 200 and [x["name"] for x in r.json()] == ["Montag", "Donnerstag"], "Rita (Amt) sieht das Wochenmuster")
check(A.get("/api/training-regeln").status_code == 403, "eine Spielerin ohne Recht nicht")

# --- Termine vorbereiten: drei Donnerstage (alte Zeit 20:15), ein Montag, ein alter Donnerstag -----------------------
heute = date.today()
do1 = naechster(3, heute + timedelta(days=3))
do2, do3 = do1 + timedelta(days=7), do1 + timedelta(days=14)
do_frueher = do1 - timedelta(days=7)
mo1 = naechster(0, heute + timedelta(days=3))
conn = db.verbinde()
ids = {}
for name, d in (("do1", do1), ("do2", do2), ("do3", do3), ("do_frueher", do_frueher)):
    ids[name] = db.training_anlegen(conn, d.isoformat(), "Training Blaubeuren", None, uhrzeit="20:15", ort="Blaubeuren")[0]
ids["mo1"] = db.training_anlegen(conn, mo1.isoformat(), "Training Gerhausen", None, uhrzeit="20:00", ort="Gerhausen")[0]
db.teilnahme_setzen(conn, ids["do1"], sp["Anna"], "abgesagt", "krank", quelle="app")
db.teilnahme_setzen(conn, ids["do1"], sp["Bea"], "anwesend", None, quelle="app")
db.teilnahme_setzen(conn, ids["mo1"], sp["Bea"], "anwesend", None, quelle="app")
conn.close()

# --- Ab diesem Datum fuer alle Donnerstage ------------------------------------------------------------------------------
check(A.post("/api/training-serie", json={"wochentag": 3, "ab": do1.isoformat(), "uhrzeit": "18:30"}).status_code == 403,
      "eine Spielerin darf die Zeit nicht ändern")
check(R.post("/api/training-serie", json={"wochentag": 3, "ab": do1.isoformat(), "uhrzeit": "25:99"}).status_code == 400,
      "ungültige Uhrzeit wird abgelehnt")
check(R.post("/api/training-serie", json={"wochentag": 3, "ab": "morgen", "uhrzeit": "18:30"}).status_code == 400,
      "ungültiges Datum wird abgelehnt")
check(R.post("/api/training-serie", json={"wochentag": 1, "ab": do1.isoformat(), "uhrzeit": "18:30"}).status_code == 400,
      "ohne Wochenmuster (Dienstag) geht es nicht")
r = R.post("/api/training-serie", json={"wochentag": 3, "ab": do1.isoformat(), "uhrzeit": "18:30"})
check(r.status_code == 200 and r.json()["anzahl"] == 3 and r.json()["vorher"] == ["20:15", "Blaubeuren"]
      and r.json()["nachher"] == ["18:30", "Blaubeuren"], "Rita ändert die Donnerstage: 3 Termine, 20:15 auf 18:30")
check(all(zeile(ids[n])["uhrzeit"] == "18:30" for n in ("do1", "do2", "do3")), "die drei Donnerstage haben 18:30")
check(zeile(ids["do_frueher"])["uhrzeit"] == "20:15" and zeile(ids["mo1"])["uhrzeit"] == "20:00",
      "frühere Termine und der Montag bleiben unberührt")
check(antworten(ids["do1"]) == {sp["Anna"]: "abgesagt", sp["Bea"]: "anwesend"},
      "Antworten bleiben: Annas Absage gilt weiter, niemand muss neu antworten")
c = db.verbinde()
check(c.execute("SELECT COUNT(*) FROM trainings").fetchone()[0] == 5, "kein Termin wurde neu angelegt oder gelöscht")
check(db.trainings_regeln(c)[3] == ("18:30", "Blaubeuren"), "das Wochenmuster ist gespeichert")
c.close()
warte(1)
check(len(gesendet) == 1 and gesendet[0][1] == "Donnerstagstraining geändert" and "18:30 statt 20:15" in gesendet[0][2]
      and gesendet[0][3] == "termine" and gesendet[0][0] == sorted(bu[n] for n in ("Anna", "Bea", "Rita")),
      "genau eine Mitteilung an alle aus dem Kader, nicht eine je Termin")

# --- Neue Trainings entstehen mit der neuen Zeit ---------------------------------------------------------------------------
conn = db.verbinde()
neu = do3 + timedelta(days=7)
trainings_termine.anlegen(conn, neu, neu)
conn.commit()
check(conn.execute("SELECT uhrzeit FROM trainings WHERE datum = ?", (neu.isoformat(),)).fetchone()["uhrzeit"] == "18:30",
      "trainings_termine legt künftige Donnerstage mit 18:30 an")
conn.close()

# --- Ein einzelner Termin ----------------------------------------------------------------------------------------------------
gesendet.clear()
r = R.post(f"/api/trainings/{ids['mo1']}/aendern", json={"ort": "Halle Süd", "uhrzeit": "19:30"})
check(r.status_code == 200, "Rita ändert den Montagstermin")
z = zeile(ids["mo1"])
check(z["uhrzeit"] == "19:30" and z["ort"] == "Halle Süd" and z["titel"] == "Training Halle Süd",
      "Zeit und Ort neu, der Titel zieht mit")
check(zeile(ids["do1"])["uhrzeit"] == "18:30", "andere Termine bleiben")
check(antworten(ids["mo1"]) == {sp["Bea"]: "anwesend"}, "Beas Zusage bleibt")
warte(1)
check(len(gesendet) == 1 and gesendet[0][0] == [bu["Bea"]] and gesendet[0][1] == "Termin geändert"
      and "19:30" in gesendet[0][2] and "20:00" in gesendet[0][2], "Bea erfährt die neue Zeit (mit der alten daneben)")
gesendet.clear()
check(R.post(f"/api/trainings/{ids['mo1']}/aendern", json={"uhrzeit": "19:30"}).status_code == 200, "dieselbe Zeit noch einmal")
warte(1, 0.5)
check(not gesendet, "ohne echte Änderung keine Mitteilung")
check(R.post(f"/api/trainings/{ids['mo1']}/aendern", json={"uhrzeit": "halb acht"}).status_code == 400, "ungültige Uhrzeit")
check(R.post("/api/trainings/99999/aendern", json={"uhrzeit": "19:30"}).status_code == 404, "unbekannter Termin")
check(A.post(f"/api/trainings/{ids['mo1']}/aendern", json={"uhrzeit": "19:00"}).status_code == 403, "Spielerin darf nicht")

# --- Spiele ------------------------------------------------------------------------------------------------------------------------
conn = db.verbinde()
spiel = db.training_anlegen(conn, (heute + timedelta(days=9)).isoformat(), "Ligaspiel bei TSV Fern", None, art="ligaspiel",
                            gegner="TSV Fern", heim=0, abfahrt="16:30", uhrzeit="18:00")[0]
conn.close()
check(T.post(f"/api/trainings/{spiel}/aendern", json={"abfahrt": "16:00", "uhrzeit": "17:30", "gegner": "TSV Fernau"}).status_code == 200,
      "Trainer ändert Abfahrt, Anwurf und Gegner eines Spiels")
z = zeile(spiel)
check((z["abfahrt"], z["uhrzeit"], z["gegner"]) == ("16:00", "17:30", "TSV Fernau"), "Spiel: neue Werte gespeichert")

print("\nAlle Tests gruen.")
