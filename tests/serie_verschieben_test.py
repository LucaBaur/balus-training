"""Tests fuer "Trainingstag dauerhaft verschieben" (z. B. Montag -> Dienstag ab einem Datum).

Regeln: Alle kuenftigen Trainings des alten Wochentags ab dem Datum werden geloescht, an ihrer Stelle entstehen
Trainings am neuen Wochentag - OHNE automatische Zusage (alle sollen neu antworten). Das Wochenmuster wird sofort
umgeschrieben. Eine einzige Mitteilung an den Kader, nicht eine je Termin.

Laeuft gegen eine temporaere Datenbank, versendet nichts (push.sende wird abgefangen).
Start:  py tests/serie_verschieben_test.py
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

_termine.AUTO_ZUSAGE_AB = "2000-01-01"          # die automatische Zusage ist hier AN: die verschobenen duerfen sie nicht bekommen

tmp = Path(tempfile.mkdtemp(prefix="serie_verschieben_test_"))
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


def naechster(wochentag, ab):
    d = ab
    while d.weekday() != wochentag:
        d += timedelta(days=1)
    return d


def trainings(art="training"):
    c = db.verbinde()
    try:
        return {r["datum"]: dict(r) for r in c.execute("SELECT * FROM trainings WHERE art = ? ORDER BY datum", (art,))}
    finally:
        c.close()


def antworten(tid):
    c = db.verbinde()
    try:
        return {r["spieler_id"]: r["status"] for r in c.execute(
            "SELECT spieler_id, status FROM training_teilnahme WHERE training_id = ?", (tid,))}
    finally:
        c.close()


T, R, A = client("Trainer", "1111"), client("Rita", "2222"), client("Anna", "2222")

# --- Termine vorbereiten --------------------------------------------------------------------------------------------
heute = date.today()
mo1 = naechster(0, heute + timedelta(days=3))
mo2, mo3 = mo1 + timedelta(days=7), mo1 + timedelta(days=14)
di3 = mo3 + timedelta(days=1)                      # hier gibt es schon ein Training: darf nicht doppelt entstehen
do1 = naechster(3, heute + timedelta(days=3))
conn = db.verbinde()
for d in (mo1, mo2, mo3):
    db.training_anlegen(conn, d.isoformat(), "Training Gerhausen", None, uhrzeit="20:00", ort="Gerhausen")
db.training_anlegen(conn, di3.isoformat(), "Training Halle Sued", None, uhrzeit="18:00", ort="Halle Sued")
db.training_anlegen(conn, do1.isoformat(), "Training Blaubeuren", None, uhrzeit="20:15", ort="Blaubeuren")
db.training_anlegen(conn, mo2.isoformat(), "Ligaspiel gegen TSV Fern", None, art="ligaspiel", gegner="TSV Fern", heim=1)
db.teilnahme_setzen(conn, trainings()[di3.isoformat()]["id"], sp["Bea"], "abgesagt", "krank", quelle="app")
conn.close()
check(len(antworten(trainings()[mo2.isoformat()]["id"])) == 3, "Vorbedingung: Montagstrainings haben die automatische Zusage")
mo2_id = trainings()[mo2.isoformat()]["id"]
di3_id = trainings()[di3.isoformat()]["id"]

# Vergangene Trainings mit Anwesenheit: heute und gestern, dazu ein Montag vor einer Woche
conn = db.verbinde()
vergangen = {}
for d in (heute - timedelta(days=7), heute - timedelta(days=1), heute):
    tid = db.training_anlegen(conn, d.isoformat(), "Training Gerhausen", None, uhrzeit="20:00", ort="Gerhausen")[0]
    db.teilnahme_setzen(conn, tid, sp["Anna"], "anwesend", None, quelle="trainer")
    db.teilnahme_setzen(conn, tid, sp["Bea"], "abgesagt", "krank", quelle="app")
    vergangen[tid] = antworten(tid)
conn.close()
vorher_zeilen = {k: v for k, v in trainings().items() if v["id"] in vergangen}
check(len(vorher_zeilen) == 3, "Vorbedingung: drei vergangene bzw. heutige Trainings mit Anwesenheit")

# --- Eingaben pruefen -------------------------------------------------------------------------------------------------
body = {"wochentag": 0, "ab": mo2.isoformat(), "neuer_wochentag": 1, "uhrzeit": "19:30"}
check(A.post("/api/training-serie", json=body).status_code == 403, "eine Spielerin darf den Trainingstag nicht verschieben")
check(R.post("/api/training-serie", json={**body, "neuer_wochentag": 7}).status_code == 400, "Wochentag 7 gibt es nicht")
check(R.post("/api/training-serie", json={**body, "neuer_wochentag": 3}).status_code == 400,
      "auf einen Tag mit eigenem Wochenmuster (Donnerstag) geht es nicht")
check(R.post("/api/training-serie", json={**body, "wochentag": 2}).status_code == 400, "ohne Wochenmuster (Mittwoch) geht es nicht")
check(R.post("/api/training-serie", json={**body, "ab": (heute - timedelta(days=1)).isoformat()}).status_code == 400,
      "ein Datum in der Vergangenheit wird abgelehnt")
check(R.post("/api/training-serie", json={**body, "ab": heute.isoformat()}).status_code == 400,
      "auch heute wird abgelehnt: heutige und vergangene Trainings bleiben Geschichte")
check(R.post("/api/training-serie", json={**body, "uhrzeit": "25:99"}).status_code == 400, "ungültige Uhrzeit")
check(len(trainings()) == 5 + 3 and mo2.isoformat() in trainings(), "nach den Fehlversuchen ist nichts verändert")
check(gesendet == [], "und es wurde nichts gesendet")

# --- Verschieben ------------------------------------------------------------------------------------------------------
r = R.post("/api/training-serie", json=body)
check(r.status_code == 200, "Rita (Amt) verschiebt Montag -> Dienstag ab dem zweiten Montag")
j = r.json()
check(j["geloescht"] == 2 and j["angelegt"] == 1 and j["vorhanden"] == 1,
      f"2 Montage gelöscht, 1 Dienstag neu, 1 Dienstag war schon da ({j})")
t = trainings()
check(mo1.isoformat() in t and mo2.isoformat() not in t and mo3.isoformat() not in t,
      "der Montag davor bleibt, die Montage ab dem Datum sind weg")
check(trainings("ligaspiel").get(mo2.isoformat()) is not None, "ein Spiel am Montag bleibt unberührt")
check(do1.isoformat() in t, "der Donnerstag bleibt")
di2 = (mo2 + timedelta(days=1)).isoformat()
check(di2 in t and (t[di2]["uhrzeit"], t[di2]["ort"], t[di2]["titel"]) == ("19:30", "Gerhausen", "Training Gerhausen"),
      "am Dienstag entsteht ein Training mit der neuen Uhrzeit, Ort und Titel vom alten Muster")
check(antworten(t[di2]["id"]) == {}, "für das neue Dienstagstraining hat niemand zugesagt: alle müssen neu antworten")
conn = db.verbinde()
db.auto_zusagen(conn)
conn.close()
check(antworten(t[di2]["id"]) == {}, "auch ein späterer Lauf der automatischen Zusage ändert daran nichts")
check(t[di3.isoformat()]["id"] == di3_id and t[di3.isoformat()]["uhrzeit"] == "18:00"
      and antworten(di3_id)[sp["Bea"]] == "abgesagt", "das schon vorhandene Dienstagstraining bleibt mit Zeit und Beas Absage")
check(sum(1 for k in t if k == di3.isoformat()) == 1, "kein Duplikat am vorhandenen Dienstag")

check({k: v for k, v in trainings().items() if v["id"] in vergangen} == vorher_zeilen
      and all(antworten(tid) == stand for tid, stand in vergangen.items()),
      "vergangene und heutige Trainings sind samt Anwesenheit und Absagegründen unverändert")

# --- Wochenmuster ----------------------------------------------------------------------------------------------------------
conn = db.verbinde()
check(db.trainings_regeln(conn) == {1: ("19:30", "Gerhausen"), 3: ("20:15", "Blaubeuren")},
      "das Wochenmuster ist umgeschrieben: Dienstag 19:30 statt Montag, Donnerstag bleibt (und Montag kommt nicht zurück)")
neu = naechster(0, mo3 + timedelta(days=7))
trainings_termine.anlegen(conn, neu, neu + timedelta(days=6))
conn.commit()
conn.close()
t = trainings()
check(neu.isoformat() not in t and (neu + timedelta(days=1)).isoformat() in t,
      "trainings_termine legt künftig Dienstage statt Montage an")

# --- Mitteilung ------------------------------------------------------------------------------------------------------------------
warte(1)
check(len(gesendet) == 1 and gesendet[0][1] == "Montagstraining verschoben" and gesendet[0][3] == "termine"
      and gesendet[0][0] == sorted(bu.values()), "genau eine Mitteilung an den ganzen Kader (keine je Termin)")
check("Dienstag" in gesendet[0][2] and "19:30" in gesendet[0][2] and "zu- oder absagen" in gesendet[0][2],
      f"der Text nennt den neuen Tag, die Zeit und die Bitte um Antwort ({gesendet[0][2]})")

# --- Zweiter Aufruf --------------------------------------------------------------------------------------------------------------------
check(R.post("/api/training-serie", json=body).status_code == 400, "derselbe Aufruf noch einmal: kein Wochenmuster mehr für Montag, nichts passiert")
check(len(trainings()) == len(t), "und es entsteht nichts Doppeltes")

print("\nAlle Tests gruen.")
