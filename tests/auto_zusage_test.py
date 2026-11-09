"""Tests fuer die automatische Zusage und die 24-Stunden-Frist bei normalen Trainings.

Regeln: Ab AUTO_ZUSAGE_AB sind bei Trainings (nicht freiwillig, keine Spiele) alle aktiven Spielerinnen
automatisch zugesagt (quelle 'auto'). Absagen und "unsicher" gehen in der App nur bis 24 Stunden vorher,
danach nur ueber den Trainer. Zusagen geht immer.

Laeuft gegen eine temporaere Datenbank, versendet nichts (push.sende wird abgefangen).
Start:  py tests/auto_zusage_test.py
"""
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import daten.termine as termine  # noqa: E402
import db  # noqa: E402
import push  # noqa: E402
import push_erinnerung  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="auto_zusage_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

heute = date.today()
termine.AUTO_ZUSAGE_AB = (heute - timedelta(days=30)).isoformat()      # die Regel gilt fuer alle Termine hier

conn = db.verbinde()
db.init_db(conn)
sp = {n: db.spieler_anlegen(conn, n) for n in ("Anna", "Bea", "Cora", "Dora")}
bu = {}
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
for n, sid in sp.items():
    bu[n] = db.benutzer_anlegen(conn, n, "spieler", auth.hash_pin("2222"), sid)
conn.execute("UPDATE spieler SET aktiv = 0 WHERE id = ?", (sp["Dora"],))      # Dora ist nicht mehr im Kader
conn.commit()
conn.close()

gesendet = []
push.sende = lambda conn, ids, titel, text, url="/", art=None: gesendet.append((sorted(ids), titel, text, art)) or {"gesendet": len(ids)}


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def client(name, pin):
    c = TestClient(balu.app)
    assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def kein_freitag(d, richtung=1):
    while d.weekday() == 4:                     # Freitag ist freiwillig
        d += timedelta(days=richtung)
    return d


def status_von(tid):
    c = db.verbinde()
    try:
        return {r["spieler_id"]: (r["status"], r["quelle"]) for r in c.execute(
            "SELECT spieler_id, status, quelle FROM training_teilnahme WHERE training_id = ?", (tid,))}
    finally:
        c.close()


T, A = client("Trainer", "1111"), client("Anna", "2222")

# --- Regel und Frist ---------------------------------------------------------------------------------------------------
mo = kein_freitag(heute + timedelta(days=10))
freitag = heute + timedelta(days=(4 - heute.weekday()) % 7 + 7)
check(termine.auto_zusage_gilt(mo.isoformat()) and not termine.auto_zusage_gilt(freitag.isoformat()),
      "gilt fuer normale Trainings, nicht fuer das freiwillige am Freitag")
check(not termine.auto_zusage_gilt(mo.isoformat(), "ligaspiel"), "gilt nicht fuer Spiele")
check(not termine.auto_zusage_gilt((heute - timedelta(days=60)).isoformat()), "gilt nicht vor AUTO_ZUSAGE_AB")
f = termine.absage_frist(mo.isoformat(), "20:00")
check(f == datetime.combine(mo - timedelta(days=1), datetime.strptime("20:00", "%H:%M").time(), tzinfo=db._berlin()),
      "Frist = 24 Stunden vor Beginn (Berliner Zeit)")
check(termine.absage_frist(freitag.isoformat(), "20:00") is None and termine.absage_frist(mo.isoformat(), "20:00", "testspiel") is None,
      "ohne Regel keine Frist")
check(termine.absage_frist(mo.isoformat(), None) is not None, "ohne Uhrzeit gibt es trotzdem eine Frist (ab Tagesbeginn)")
jetzt = datetime.now(db._berlin())
check(termine.absage_gesperrt(mo.isoformat(), "20:00", jetzt=datetime.combine(mo, datetime.min.time(), tzinfo=db._berlin()))
      and not termine.absage_gesperrt(mo.isoformat(), "20:00", jetzt=f - timedelta(minutes=1)),
      "gesperrt ab der Frist, eine Minute davor noch nicht")

# --- Automatische Zusage -----------------------------------------------------------------------------------------------
conn = db.verbinde()
t_mo = db.training_anlegen(conn, mo.isoformat(), "Training", None, uhrzeit="20:00")[0]
t_fr = db.training_anlegen(conn, freitag.isoformat(), "Freitag", None, uhrzeit="18:00")[0]
t_sp = db.training_anlegen(conn, mo.isoformat(), "Spiel", None, art="testspiel", gegner="X", heim=1, uhrzeit="18:00")[0]
conn.close()
st = status_von(t_mo)
check(all(st.get(sp[n]) == ("anwesend", "auto") for n in ("Anna", "Bea", "Cora")),
      "beim Anlegen des Trainings sind sofort alle aus dem Kader zugesagt (quelle 'auto')")
check(sp["Dora"] not in st, "wer nicht im Kader ist, bekommt keine Zusage")
check(not status_von(t_fr) and not status_von(t_sp), "Freitag und Spiele bleiben ohne automatische Zusage")
conn = db.verbinde()
db.teilnahme_setzen(conn, t_mo, sp["Bea"], "abgesagt", "krank", quelle="app")      # Bea sagt ab
check(db.auto_zusagen(conn, heute) == 0, "ein weiterer Lauf aendert nichts (idempotent)")
check(status_von(t_mo)[sp["Bea"]] == ("abgesagt", "app"), "Beas Absage bleibt unberuehrt")
conn.execute("DELETE FROM training_teilnahme WHERE training_id = ? AND spieler_id = ?", (t_mo, sp["Cora"]))
conn.commit()
check(db.auto_zusagen(conn, heute, trocken=True) == 1 and sp["Cora"] not in status_von(t_mo),
      "Trockenlauf zaehlt die fehlende Zeile, schreibt aber nichts")
check(db.auto_zusagen(conn, heute) == 1 and status_von(t_mo)[sp["Cora"]] == ("anwesend", "auto"),
      "der Abgleich (auch von Hand: py auto_zusagen.py) stellt sie wieder her")

# Neue und wieder aktive Spielerinnen sind bei kommenden Trainings gleich dabei
eva = db.spieler_anlegen(conn, "Eva")
check(status_von(t_mo)[eva] == ("anwesend", "auto") and eva not in status_von(t_fr), "neue Spielerin: gleich bei kommenden Trainings dabei")
db.spieler_aktualisieren(conn, sp["Dora"], aktiv=True)
check(status_von(t_mo)[sp["Dora"]] == ("anwesend", "auto"), "wieder aktivierte Spielerin: ebenfalls")
for wer in (eva, sp["Dora"]):                                  # fuer die weiteren Pruefungen wieder raus
    db.spieler_aktualisieren(conn, wer, aktiv=False)
conn.close()

# --- Frist per API -----------------------------------------------------------------------------------------------------
d = A.get(f"/api/trainings/{t_mo}").json()
check(d["absage_frist"] and d["absage_frist"].startswith((mo - timedelta(days=1)).isoformat() + "T20:00"),
      "das Training nennt die Frist (absage_frist)")
check(A.get("/api/trainings").json() and next(t for t in A.get("/api/trainings").json() if t["id"] == t_fr)["absage_frist"] is None,
      "freiwillige Trainings haben keine Frist")
r = A.post(f"/api/trainings/{t_mo}/teilnahme", json={"status": "abgesagt", "grund": "Arbeit"})
check(r.status_code == 200, "vor der Frist darf Anna absagen")
check(A.post(f"/api/trainings/{t_mo}/teilnahme", json={"status": "anwesend"}).status_code == 200, "und wieder zusagen")

alt = kein_freitag(heute - timedelta(days=3), -1)
conn = db.verbinde()
t_alt = db.training_anlegen(conn, alt.isoformat(), "Altes Training", None, uhrzeit="20:00")[0]
conn.close()
r = A.post(f"/api/trainings/{t_alt}/teilnahme", json={"status": "abgesagt", "grund": "krank"})
check(r.status_code == 403 and "24 Stunden" in r.json()["detail"] and "Luca" in r.json()["detail"],
      "nach der Frist lehnt der Server die Absage ab und nennt den Weg")
check(A.post(f"/api/trainings/{t_alt}/teilnahme", json={"status": "unsicher"}).status_code == 403, "auch 'unsicher' ist gesperrt")
check(A.post(f"/api/trainings/{t_alt}/teilnahme", json={"status": "anwesend"}).status_code == 200, "Zusagen geht weiter")
check(T.post(f"/api/trainings/{t_alt}/teilnahme/{sp['Anna']}", json={"status": "abgesagt", "grund": "angerufen"}).status_code == 200,
      "der Trainer traegt die Absage nach der Frist ein")
check(status_von(t_alt)[sp["Anna"]] == ("abgesagt", "trainer"), "Absage steht mit quelle 'trainer'")

# --- SpielerPlus-Import und Erinnerung -----------------------------------------------------------------------------------
conn = db.verbinde()
check(db.teilnahme_spiegeln(conn, t_mo, sp["Cora"], "abgesagt"), "eine echte SpielerPlus-Antwort ersetzt die Voreinstellung 'auto'")
check(not db.teilnahme_spiegeln(conn, t_mo, sp["Anna"], "abgesagt"), "eine Antwort aus der App ersetzt sie nicht")
conn.commit()
check(db.offene_spieler_benutzer(conn, t_mo) == [bu["Cora"]], "'auto' zaehlt als Antwort, nichts ist offen (Cora hat nur eine SpielerPlus-Antwort)")
check(db.zugesagte_spieler_benutzer(conn, t_mo) == [bu["Anna"]], "zugesagt sind nur die, die dabei sind")
conn.close()

ziel = next(tage for tage in (2, 3, 4) if (heute + timedelta(days=tage)).weekday() != 4)
conn = db.verbinde()
t_bald = db.training_anlegen(conn, (heute + timedelta(days=ziel)).isoformat(), "Training Gerhausen", None, uhrzeit="20:00", ort="Gerhausen")[0]
db.auto_zusagen(conn, heute)
db.teilnahme_setzen(conn, t_bald, sp["Bea"], "abgesagt", "krank", quelle="app")
gesendet.clear()
r = push_erinnerung.erinnere(conn, ziel, trocken=False)
conn.close()
check(not gesendet and r["offen"] == 0 and r["gesendet"] == 0,
      "bei automatischer Zusage geht keine Erinnerung raus (weder 'bitte antworten' noch 'du bist dabei')")

print("\nAlle Tests gruen.")
