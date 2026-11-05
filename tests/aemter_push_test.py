"""Tests fuer die Ämter-Mitteilungen: "du bist dran" bei der Zuteilung und die Erinnerung
"heute nicht vergessen" eine Stunde vor dem Termin.

Laeuft gegen eine temporaere Datenbank, versendet nichts (push.sende wird abgefangen).
Start:  py tests/aemter_push_test.py
"""
import sys
import tempfile
import time as _zeit
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import aemter  # noqa: E402
import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
import push  # noqa: E402
import push_amt_erinnerung as erinnerung  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="aemter_push_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
sp = {n: db.spieler_anlegen(conn, n) for n in ("Anna", "Bea", "Cora", "Dora", "Emma")}
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


T, A = client("Trainer", "1111"), client("Anna", "2222")


def amt(schluessel):
    c = db.verbinde()
    try:
        return c.execute("SELECT id FROM amt WHERE schluessel = ?", (schluessel,)).fetchone()["id"]
    finally:
        c.close()


def warte_auf_push(anzahl, sek=3.0):
    """Die Mitteilung geht im Hintergrund raus; der TestClient wartet darauf, trotzdem kurz abwarten."""
    ende = _zeit.time() + sek
    while len(gesendet) < anzahl and _zeit.time() < ende:
        _zeit.sleep(0.05)


morgen = (date.today() + timedelta(days=2)).isoformat()
conn = db.verbinde()
aemter.inhaber_setzen(conn, amt("waschliste"), sp["Anna"], True)
aemter.inhaber_setzen(conn, amt("bussle"), sp["Anna"], True)
spiel = db.training_anlegen(conn, morgen, "Ligaspiel bei TSV Fern", None, art="ligaspiel", gegner="TSV Fern", heim=0, abfahrt="16:30", uhrzeit="18:00")[0]
conn.close()
zut = lambda amt_id, tid, name, da=True: A.post(f"/api/aemter/{amt_id}/zuteilung", json={"training_id": tid, "spieler_id": sp[name], "da": da})  # noqa: E731

# --- Push bei der Zuteilung ------------------------------------------------------------------------------
check("aemter" in push.ART_KEYS, "es gibt die Mitteilungsart „aemter“")
check(zut(amt("waschliste"), spiel, "Bea").status_code == 200, "Anna teilt Bea für die Trikots ein")
warte_auf_push(1)
check(len(gesendet) == 1 and gesendet[0][0] == [bu["Bea"]] and gesendet[0][3] == "aemter"
      and "Waschliste" in gesendet[0][1] and "TSV Fern" in gesendet[0][2], "Bea bekommt „Du bist dran: Waschliste“ mit dem Termin")
check(zut(amt("waschliste"), spiel, "Bea").status_code == 200, "dieselbe Zuteilung noch einmal senden")
warte_auf_push(2, 0.5)
check(len(gesendet) == 1, "eine wiederholte Zuteilung klingelt nicht noch einmal")
check(zut(amt("waschliste"), spiel, "Anna").status_code == 200, "Anna trägt sich selbst ein")
warte_auf_push(2, 0.5)
check(len(gesendet) == 1, "wer sich selbst einträgt, bekommt keine Nachricht")
check(zut(amt("waschliste"), spiel, "Bea", False).status_code == 200, "Zuteilung zurücknehmen")
warte_auf_push(2, 0.5)
check(len(gesendet) == 1, "beim Zurücknehmen geht nichts raus")
check(zut(amt("bussle"), spiel, "Cora").status_code == 200, "Anna trägt Cora als Selbstfahrerin ein")
warte_auf_push(2)
check(len(gesendet) == 2 and gesendet[1][0] == [bu["Cora"]] and "Auto" in gesendet[1][1], "Cora erfährt, dass sie selbst fährt")
conn = db.verbinde()
vergangen = db.training_anlegen(conn, (date.today() - timedelta(days=2)).isoformat(), "Altes Spiel", None, art="testspiel", gegner="G", heim=1)[0]
conn.close()
zut(amt("waschliste"), vergangen, "Dora")
warte_auf_push(3, 0.5)
check(len(gesendet) == 2, "für vergangene Termine kommt keine Nachricht")

# --- Erinnerung eine Stunde vorher -----------------------------------------------------------------------------
tz = db._berlin()
conn = db.verbinde()
for schluessel, wer in [("tape", "Emma"), ("harz_oel", "Emma"), ("duschgel", "Dora"), ("eiskoffer", "Dora"), ("musik", "Bea")]:
    aemter.inhaber_setzen(conn, amt(schluessel), sp[wer], True)
tag = date(2026, 12, 3)
training = db.training_anlegen(conn, tag.isoformat(), "Training", None, uhrzeit="19:00")[0]
auswaerts = db.training_anlegen(conn, tag.isoformat(), "Ligaspiel bei TSV Fern", None, art="ligaspiel", gegner="TSV Fern", heim=0, abfahrt="16:30", uhrzeit="18:00")[0]
heimspiel = db.training_anlegen(conn, tag.isoformat(), "Ligaspiel gegen TV Nah", None, art="ligaspiel", gegner="TV Nah", heim=1, uhrzeit="20:30")[0]
ohne_zeit = db.training_anlegen(conn, tag.isoformat(), "Testspiel", None, art="testspiel", gegner="X", heim=1)[0]
aemter.zuteilung_setzen(conn, amt("getraenke"), training, sp["Cora"], True)
aemter.zuteilung_setzen(conn, amt("leibchen"), training, sp["Cora"], True)
aemter.zuteilung_setzen(conn, amt("bussle"), auswaerts, sp["Bea"], True)
aemter.zuteilung_setzen(conn, amt("getraenke"), training, sp["Bea"], True)
db.teilnahme_setzen(conn, training, sp["Bea"], "abgesagt", "manuell", "krank")
conn.close()


def lauf(uhr, trocken=False):
    c = db.verbinde()
    try:
        gesendet.clear()
        r = erinnerung.erinnere(c, datetime.fromisoformat(f"2026-12-03 {uhr}").replace(tzinfo=tz), trocken=trocken)
        return r, list(gesendet)
    finally:
        c.close()


r, g = lauf("17:30")
check(r["faellig"] == 0 and not g, "90 Minuten vorher: noch nichts")
r, g = lauf("18:05")
texte = {tuple(x[0]): x[2] for x in g}
check(r["faellig"] == 1, "um 18:05 ist das Training (19:00) fällig, die Abfahrt (16:30) schon vorbei")
check(texte[(bu["Emma"],)] == "Tape und Harz und Öl · Training 19:00 Uhr", "Emma: Tape und Harz und Öl, mit Uhrzeit")
check(texte[(bu["Dora"],)] == "Duschgel · Training 19:00 Uhr", "Dora: Duschgel (Eiskoffer gibt es nur bei Spielen)")
check(texte[(bu["Cora"],)] == "Getränke und Leibchen nach dem Training mitnehmen · Training 19:00 Uhr",
      "Cora: Getränke und Leibchen, weil sie dafür eingeteilt ist")
check((bu["Bea"],) not in texte, "Bea hat abgesagt und bekommt nichts (auch kein Musik-Amt beim Training)")
check(all(x[1] == "Heute nicht vergessen" and x[3] == "aemter" for x in g), "Titel und Art stimmen")
r, g = lauf("18:15")
check(not g, "ein zweiter Lauf schickt dieselben Nachrichten nicht noch einmal")

r, g = lauf("15:45")
texte = {tuple(x[0]): x[2] for x in g}
check(r["faellig"] == 1 and texte[(bu["Bea"],)] == "Musik für die Kabine und mit dem eigenen Auto fahren · Abfahrt 16:30 Uhr · Spiel bei TSV Fern",
      "Auswärtsspiel: Bezug ist die Abfahrt, Bea hat Musik und fährt selbst")
check(texte[(bu["Emma"],)].startswith("Tape und Harz und Öl") and texte[(bu["Dora"],)].startswith("Eiskoffer"),
      "beim Spiel kommen der Eiskoffer dazu und das Duschgel entfällt")
r, g = lauf("19:35")
check(r["faellig"] == 1 and "Anwurf 20:30 Uhr · Spiel gegen TV Nah" in g[0][2], "Heimspiel: Bezug ist der Anwurf")
check(r["ohne_zeit"] == 1, "ein Termin ohne Uhrzeit wird gezählt, aber nicht erinnert")
r, g = lauf("20:45")
check(r["faellig"] == 0 and not g, "nach dem Beginn gibt es keine Erinnerung mehr")

conn = db.verbinde()
conn.execute("DELETE FROM push_gesendet")
conn.commit()
conn.close()
r, g = lauf("18:05", trocken=True)
check(r["gesendet"] == 3 and not g, "Trockenlauf zählt, sendet aber nichts")
r, g = lauf("18:05")
check(len(g) == 3, "und merkt sich nichts: der echte Lauf sendet danach")

print("\nAlle Ämter-Mitteilungs-Tests bestanden.")
