"""Tests fuer "Du hast abgesagt - wer uebernimmt?": Wer absagt, aber fuer den Termin noch ein Amt hat
(Tape mitbringen, Getraenke, Fahrt ...), wird gebeten, es weiterzugeben.

Laeuft gegen eine temporaere Datenbank, versendet nichts (push.sende wird abgefangen).
Start:  py tests/amt_uebergabe_test.py
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
import db  # noqa: E402
import daten.termine as _termine  # noqa: E402

_termine.AUTO_ZUSAGE_AB = "2999-12-31"   # diese Tests pruefen das Opt-in-Verhalten (auto_zusage_test.py das neue)
import push  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="amt_uebergabe_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
sp = {n: db.spieler_anlegen(conn, n) for n in ("Anna", "Bea", "Cora", "Dora")}
bu = {}
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
for n, sid in sp.items():
    bu[n] = db.benutzer_anlegen(conn, n, "spieler", auth.hash_pin("2222"), sid)
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
    """Die Mitteilung geht im Hintergrund raus; kurz abwarten (oder zeigen, dass nichts kommt)."""
    ende = _zeit.time() + sek
    while len(gesendet) < anzahl and _zeit.time() < ende:
        _zeit.sleep(0.05)


def amt(schluessel):
    c = db.verbinde()
    try:
        return c.execute("SELECT id FROM amt WHERE schluessel = ?", (schluessel,)).fetchone()["id"]
    finally:
        c.close()


T, A, C, D = client("Trainer", "1111"), client("Anna", "2222"), client("Cora", "2222"), client("Dora", "2222")
absagen = lambda c, tid: c.post(f"/api/trainings/{tid}/teilnahme", json={"status": "abgesagt", "grund": "krank"})  # noqa: E731
zusagen = lambda c, tid: c.post(f"/api/trainings/{tid}/teilnahme", json={"status": "anwesend"})  # noqa: E731

tag = (date.today() + timedelta(days=3)).isoformat()
conn = db.verbinde()
aemter.inhaber_setzen(conn, amt("tape"), sp["Anna"], True)              # Mitbring-Amt: gilt fuer jeden Termin
t1 = db.training_anlegen(conn, tag, "Training", None, uhrzeit="19:00")[0]
t2 = db.training_anlegen(conn, (date.today() + timedelta(days=4)).isoformat(), "Training", None, uhrzeit="19:00")[0]
alt = db.training_anlegen(conn, (date.today() - timedelta(days=2)).isoformat(), "Altes Training", None, uhrzeit="19:00")[0]
aemter.zuteilung_setzen(conn, amt("getraenke"), t1, sp["Cora"], True)   # Listen-Amt: nur an diesem Termin
conn.close()

# --- Mitbring-Amt ---------------------------------------------------------------------------------------------
check(absagen(A, t1).status_code == 200, "Anna (Tape) sagt für Training 1 ab")
warte(1)
check(len(gesendet) == 1 and gesendet[0][0] == [bu["Anna"]] and gesendet[0][3] == "aemter"
      and "Tape" in gesendet[0][2] and "weiter" in gesendet[0][2] and "abgesagt" in gesendet[0][1],
      "Anna wird gebeten, das Tape weiterzugeben (Art „aemter“)")
check(absagen(A, t1).status_code == 200, "Anna sendet dieselbe Absage noch einmal")
warte(2, 0.5)
check(len(gesendet) == 1, "je Termin und Person nur einmal")
check(zusagen(A, t1).status_code == 200 and absagen(A, t1).status_code == 200, "Anna schaltet hin und her")
warte(2, 0.5)
check(len(gesendet) == 1, "auch beim Hin- und Herschalten klingelt es nicht erneut")
check(absagen(A, t2).status_code == 200, "Anna sagt auch für Training 2 ab")
warte(2)
check(len(gesendet) == 2, "ein anderer Termin ist eine neue Nachricht")

# --- Listen-Amt (Getraenke) -------------------------------------------------------------------------------------
check(absagen(C, t1).status_code == 200, "Cora (Getränke am Training 1) sagt ab")
warte(3)
check(len(gesendet) == 3 and gesendet[2][0] == [bu["Cora"]] and "Getränke" in gesendet[2][2],
      "Cora wird gebeten, die Getränke weiterzugeben")
check(absagen(C, t2).status_code == 200, "Cora sagt für Training 2 ab, wo sie nichts zu tun hat")
warte(4, 0.5)
check(len(gesendet) == 3, "ohne Amt an diesem Termin keine Nachricht")

# --- Kein Amt, Zusage, Vergangenheit, Trainer --------------------------------------------------------------------
check(absagen(D, t1).status_code == 200, "Dora (ohne Amt) sagt ab")
check(zusagen(C, t1).status_code == 200, "Cora sagt wieder zu")
warte(4, 0.5)
check(len(gesendet) == 3, "ohne Amt und bei einer Zusage kommt nichts")
absagen(A, alt)
warte(4, 0.5)
check(len(gesendet) == 3, "für vergangene Termine kommt nichts")
conn = db.verbinde()
t3 = db.training_anlegen(conn, (date.today() + timedelta(days=6)).isoformat(), "Training", None, uhrzeit="19:00")[0]
conn.close()
r = T.post(f"/api/trainings/{t3}/teilnahme/{sp['Anna']}", json={"status": "abgesagt"})
check(r.status_code == 200, "Der Trainer trägt Annas Absage ein")
warte(4)
check(len(gesendet) == 4 and gesendet[3][0] == [bu["Anna"]] and "Tape" in gesendet[3][2],
      "auch dann wird Anna gebeten, das Tape weiterzugeben")

# --- Wer abgesagt hat, kann nicht eingeteilt werden --------------------------------------------------------------
n = len(gesendet)
zut = lambda amt_id, tid, name, da=True: T.post(f"/api/aemter/{amt_id}/zuteilung", json={"training_id": tid, "spieler_id": sp[name], "da": da})  # noqa: E731
r = zut(amt("getraenke"), t1, "Dora")                       # Dora hat fuer t1 abgesagt (siehe oben)
check(r.status_code == 400 and "abgesagt" in r.json().get("detail", ""), "Dora (abgesagt) wird nicht für Getränke eingeteilt")
warte(n + 1, 0.5)
check(len(gesendet) == n, "dabei geht keine „Du bist dran“-Nachricht raus")
liste = T.get(f"/api/aemter/{amt('getraenke')}/liste").json()
termin1 = next(t for t in liste["termine"] if t["training_id"] == t1)
check(sp["Dora"] in termin1["abgesagt"] and sp["Cora"] not in termin1["abgesagt"],
      "die Liste nennt, wer abgesagt hat (Dora ja, Cora hat wieder zugesagt)")
check(zut(amt("getraenke"), t1, "Cora").status_code == 200, "wer nicht abgesagt hat, lässt sich einteilen")
check(zut(amt("getraenke"), t1, "Dora", False).status_code == 200, "Zurücknehmen bleibt auch bei Abgesagten möglich")
zusagen(D, t1)
check(zut(amt("getraenke"), t1, "Dora").status_code == 200, "nach einer Zusage ist Dora wieder einteilbar")
check(zut(amt("bussle"), t1, "Anna").status_code == 400, "Anna (abgesagt) trägt sich nicht als Selbstfahrerin ein")

print("\nAlle Tests gruen.")
