"""Tests fuer gezielte Push-Nachrichten: Einstellungen je Art, Ausloeser, Einmaligkeit.

Laeuft gegen eine temporaere Datenbank und temporaere Medienordner. Der echte
Versand (pywebpush) wird durch einen Stub ersetzt - es geht nichts ins Netz.
Start:  py tests/push_ausloeser_test.py
"""
import json
import sys
import tempfile
import types
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pywebpush ist am Entwicklungs-PC nicht installiert: ein Stub zeichnet die Aufrufe auf.
abos_angeschrieben = []


class _FakeWebPushException(Exception):
    pass


fake = types.ModuleType("pywebpush")
fake.WebPushException = _FakeWebPushException
aufrufe = []                              # Parameter jedes webpush-Aufrufs


def _fake_webpush(sub, payload, **kw):
    abos_angeschrieben.append(sub["endpoint"])
    aufrufe.append(kw)


fake.webpush = _fake_webpush
sys.modules["pywebpush"] = fake

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
from routen import pfade  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
import push  # noqa: E402
import push_erinnerung  # noqa: E402
import push_spieltag  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="push_ausloeser_test_"))
DB = tmp / "test.db"
pfade.MEDIA_CLIPS = tmp / "clips"
pfade.MEDIA_CLIPS.mkdir()
pfade.MEDIA_SPIELE = tmp / "spiele"
pfade.MEDIA_SPIELE.mkdir()
pfade.MEDIA_SZENEN = tmp / "szenen"
pfade.MEDIA_SZENEN.mkdir()
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

HEUTE = date.today()
tag = lambda n: (HEUTE + timedelta(days=n)).isoformat()  # noqa: E731


def werktag(n):
    """n Tage voraus, aber nie ein Freitag (Freitags-Trainings sind freiwillig und warnen nicht)."""
    d = HEUTE + timedelta(days=n)
    while d.weekday() in db.FREIWILLIGE_WOCHENTAGE:
        d += timedelta(days=1)
    return d.isoformat()

conn = db.verbinde()
db.init_db(conn)
sp = {}                                   # Name -> Spieler-ID
bn = {}                                   # Name -> Benutzer-ID
trainer_b = db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
for name in ["Anna", "Bea", "Cleo", "Dora", "Eva", "Fee", "Gina", "Hanna"]:
    sp[name] = db.spieler_anlegen(conn, name)
    bn[name] = db.benutzer_anlegen(conn, name, "spieler", auth.hash_pin("2222"), sp[name])
conn.close()


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def client(name, pin):
    c = TestClient(balu.app)
    r = c.post("/api/login", json={"name": name, "pin": pin})
    assert r.status_code == 200, r.text
    return c


T = client("Trainer", "1111")
P = {n: client(n, "2222") for n in sp}
A = P["Anna"]

# ===================================================== Einstellungen je Art ===
r = A.get("/api/push/einstellungen")
check(r.status_code == 200, "Spielerin kann ihre Mitteilungs-Einstellungen lesen")
arten = {a["key"]: a for a in r.json()["arten"]}
check(list(arten) == ["termine", "aemter", "videos", "rueckmeldungen"], "Spielerin sieht genau vier Arten")
check(all(a["an"] for a in arten.values()), "alles ist standardmaessig an")
check(all(a["label"] and a["text"] for a in arten.values()), "jede Art hat Namen und Erklaerung")
check("warnungen" in {a["key"] for a in T.get("/api/push/einstellungen").json()["arten"]},
      "Trainer sieht zusaetzlich die Warnungen")
check(TestClient(balu.app).get("/api/push/einstellungen").status_code == 401, "ohne Login kein Zugriff")

check(A.post("/api/push/einstellungen", json={"art": "videos", "an": False}).status_code == 200,
      "Spielerin schaltet Videos aus")
check({a["key"]: a["an"] for a in A.get("/api/push/einstellungen").json()["arten"]}["videos"] is False,
      "die Einstellung bleibt gespeichert")
check({a["key"]: a["an"] for a in P["Bea"].get("/api/push/einstellungen").json()["arten"]}["videos"] is True,
      "Einstellungen gelten nur fuer die eigene Person")
check(A.post("/api/push/einstellungen", json={"art": "warnungen", "an": False}).status_code == 403,
      "Spielerin darf keine Trainer-Warnungen einstellen")
check(A.post("/api/push/einstellungen", json={"art": "quatsch", "an": True}).status_code == 400,
      "unbekannte Art wird abgelehnt")
check(A.post("/api/push/einstellungen", json={"art": "videos", "an": False}).status_code == 200,
      "dieselbe Einstellung zweimal ist idempotent")

# ============================================== push.sende beachtet die Art ===
conn = db.verbinde()
db.push_abo_speichern(conn, bn["Anna"], "https://push.test/anna", "k", "a")
db.push_abo_speichern(conn, bn["Bea"], "https://push.test/bea", "k", "a")
db.push_abo_speichern(conn, trainer_b, "https://push.test/trainer", "k", "a")
push.verfuegbar = lambda: True
echt_sende = push.sende
abos_angeschrieben.clear()
echt_sende(conn, [bn["Anna"], bn["Bea"]], "t", "x", art="videos")
check(abos_angeschrieben == ["https://push.test/bea"], "Art 'videos': Anna hat sie aus, nur Bea bekommt den Push")
abos_angeschrieben.clear()
echt_sende(conn, [bn["Anna"], bn["Bea"]], "t", "x", art="termine")
check(sorted(abos_angeschrieben) == ["https://push.test/anna", "https://push.test/bea"],
      "andere Art: beide bekommen ihn")
abos_angeschrieben.clear()
echt_sende(conn, [bn["Anna"]], "t", "x")
check(abos_angeschrieben == ["https://push.test/anna"], "ohne Art wird nichts gefiltert")
check(all(a.get("ttl", 0) >= 3600 for a in aufrufe),
      "jeder Push hat eine Lebensdauer (ttl 0 wird bei erreichbarem Gerät sofort verworfen, sonst nie zugestellt)")
check(all((a.get("headers") or {}).get("Urgency") == "high" for a in aufrufe),
      "Dringlichkeit 'high', damit Android im Ruhezustand weckt")
check(db.push_einmalig(conn, "test:1") is True and db.push_einmalig(conn, "test:1") is False,
      "push_einmalig meldet nur beim ersten Mal True")
conn.close()

# ===================================== ab hier: Versand aufzeichnen statt senden ===
gesendet = []        # {"an": [Benutzer-IDs], "titel", "text", "art"}


def aufzeichnen(conn, ids, titel, text, url="/", art=None):
    gesendet.append({"an": sorted(ids), "titel": titel, "text": text, "art": art})
    return {"gesendet": len(ids)}


push.sende = aufzeichnen


def letzte(n=1):
    return gesendet[-n:]


# ===================================================== Neuer Clip fuer dich ===
gesendet.clear()
meta = {"titel": "Tempogegenstoß", "spieler_ids": [sp["Anna"], sp["Bea"]]}
r = T.post("/api/clips", files={"video": ("x.mp4", b"0000", "video/mp4")}, data={"meta": json.dumps(meta)})
check(r.status_code == 200, "Trainer legt einen Clip an")
clip_id = r.json()["id"]
check(len(gesendet) == 1 and gesendet[0]["an"] == sorted([bn["Anna"], bn["Bea"]]),
      "Push geht nur an die zugeordneten Spielerinnen")
check(gesendet[0]["art"] == "videos" and "Tempogegenstoß" in gesendet[0]["text"]
      and "Clip" in gesendet[0]["titel"], "Art 'videos', Titel nennt den Clip, Text den Namen")

gesendet.clear()
check(T.post(f"/api/clips/{clip_id}", json={"spieler_ids": [sp["Anna"], sp["Bea"], sp["Cleo"]]}).status_code == 200,
      "Trainer ergaenzt Cleo")
check(len(gesendet) == 1 and gesendet[0]["an"] == [bn["Cleo"]],
      "nur die neu Hinzugekommene bekommt einen Push")
gesendet.clear()
T.post(f"/api/clips/{clip_id}", json={"titel": "Tempogegenstoß 2"})
check(not gesendet, "Aendern ohne neue Spielerinnen sendet nichts")

# ================================================ Neue Videoanalyse fuer dich ===
daten = {"extern_id": "push-analyse", "gegner": "HSG Test", "datum": tag(-3), "art": "Liga",
         "events": [{"typ": "tor", "t": 100, "spieler_id": sp["Anna"], "assist_id": sp["Bea"]}],
         "zuege": [{"name": "Kreisel", "t_start": 10, "t_ende": 20, "ampel": "gruen",
                    "spieler_ids": [sp["Anna"], sp["Dora"]]}]}
gesendet.clear()
r = T.post("/api/analysen", json=daten)
aid = r.json()["id"]
check(not gesendet, "Daten allein loesen noch keinen Push aus (das Video fehlt noch)")
r = T.put(f"/api/analysen/{aid}/video", content=b"1234")
check(r.status_code == 200 and len(gesendet) == 1, "Video hochgeladen -> ein Push")
check(gesendet[0]["an"] == sorted([bn["Anna"], bn["Bea"], bn["Dora"]]),
      "Push an alle Beteiligten (Torschuetzin, Vorlage, Spielzug)")
check(gesendet[0]["art"] == "videos" and "HSG Test" in gesendet[0]["text"], "Art 'videos', Gegner im Text")
gesendet.clear()
T.put(f"/api/analysen/{aid}/video", content=b"5678")
check(not gesendet, "erneuter Upload derselben Analyse sendet nicht noch einmal")

# ============================================================ Termin abgesagt ===
conn = db.verbinde()
tid, _ = db.training_anlegen(conn, tag(2), "Training Blaubeuren", None, uhrzeit="20:15")
db.teilnahme_setzen(conn, tid, sp["Anna"], "anwesend")
db.teilnahme_setzen(conn, tid, sp["Bea"], "unsicher")
db.teilnahme_setzen(conn, tid, sp["Cleo"], "abgesagt", "krank")
conn.close()
gesendet.clear()
check(A.post(f"/api/trainings/{tid}/loeschen").status_code == 403, "Spielerin darf keinen Termin loeschen")
check(not gesendet, "verbotener Versuch sendet nichts")
check(T.post(f"/api/trainings/{tid}/loeschen").status_code == 200, "Trainer loescht den Termin")
check(len(gesendet) == 1 and gesendet[0]["an"] == sorted([bn["Anna"], bn["Bea"]]),
      "nur wer zugesagt oder 'unsicher' gesagt hat, erfaehrt von der Absage")
check(gesendet[0]["art"] == "termine" and "abgesagt" in gesendet[0]["titel"].lower(),
      "Art 'termine', Titel sagt 'abgesagt'")
gesendet.clear()
T.post(f"/api/trainings/{tid}/loeschen")
check(not gesendet, "zweites Loeschen (Outbox-Wiederholung) sendet nichts")

# vergangener Termin: kein Push beim Loeschen
conn = db.verbinde()
alt, _ = db.training_anlegen(conn, tag(-5), "Altes Training", None)
db.teilnahme_setzen(conn, alt, sp["Anna"], "anwesend")
conn.close()
gesendet.clear()
T.post(f"/api/trainings/{alt}/loeschen")
check(not gesendet, "ein vergangener Termin wird ohne Push aufgeraeumt")

# ================================================= Trainer-Warnung: zu wenige ===
conn = db.verbinde()
tw, _ = db.training_anlegen(conn, werktag(3), "Training Gerhausen", None, uhrzeit="20:00")
for n in ["Anna", "Bea", "Cleo", "Dora", "Eva", "Fee"]:
    db.teilnahme_setzen(conn, tw, sp[n], "anwesend")
conn.close()
absagen = lambda n: P[n].post(f"/api/trainings/{tw}/teilnahme", json={"status": "abgesagt", "grund": "krank"})  # noqa: E731
zusagen = lambda n: P[n].post(f"/api/trainings/{tw}/teilnahme", json={"status": "anwesend"})  # noqa: E731
gesendet.clear()
check(absagen("Fee").status_code == 200, "Fee sagt ab (6 -> 5 Zusagen)")
check(len(gesendet) == 1 and gesendet[0]["an"] == [trainer_b] and gesendet[0]["art"] == "warnungen",
      "Trainer bekommt eine Warnung (Art 'warnungen')")
check("5" in gesendet[0]["text"] and "Training Gerhausen" in gesendet[0]["text"],
      "Warnung nennt Zahl und Termin")
absagen("Eva")
check(len(gesendet) == 1, "weitere Absage unter der Grenze loest keine zweite Warnung aus")
zusagen("Eva"); zusagen("Fee")                                  # wieder 6
check(len(gesendet) == 1, "Zusagen loesen keine Warnung aus")
absagen("Fee")                                                  # erneut 6 -> 5
check(len(gesendet) == 2, "faellt die Zahl erneut unter die Grenze, kommt wieder eine Warnung")
zusagen("Fee")                                                  # 6
gesendet.clear()
r = T.post(f"/api/trainings/{tw}/teilnahme/{sp['Anna']}", json={"status": "abgesagt"})
check(r.status_code == 200 and len(gesendet) == 1, "auch der Trainer-Eintrag fuer eine Spielerin zaehlt")
T.post(f"/api/trainings/{tw}/teilnahme/{sp['Anna']}", json={"status": "anwesend"})    # wieder 6
check(T.post("/api/push/einstellungen", json={"art": "warnungen", "an": False}).status_code == 200,
      "Trainer schaltet die Warnungen aus")
conn = db.verbinde()
check(db.push_filtern(conn, [trainer_b], "warnungen") == [], "Filter: Trainer erhaelt keine Warnungen mehr")
conn.close()
T.post("/api/push/einstellungen", json={"art": "warnungen", "an": True})

# vergangener Termin: keine Warnung
conn = db.verbinde()
vg, _ = db.training_anlegen(conn, tag(-1), "Gestern", None)
for n in ["Anna", "Bea", "Cleo", "Dora", "Eva", "Fee"]:
    db.teilnahme_setzen(conn, vg, sp[n], "anwesend")
conn.close()
gesendet.clear()
P["Anna"].post(f"/api/trainings/{vg}/teilnahme", json={"status": "abgesagt", "grund": "krank"})
check(not gesendet, "fuer vergangene Termine gibt es keine Warnung")

# ================================== Freiwilliges Training (Freitag) ===
def naechster(wochentag):
    """ISO-Datum des nächsten Wochentags (0 = Montag ... 4 = Freitag), mindestens 7 Tage entfernt."""
    d = HEUTE + timedelta(days=7)
    while d.weekday() != wochentag:
        d += timedelta(days=1)
    return d.isoformat()


conn = db.verbinde()
fr, mo = naechster(4), naechster(0)
fr_t, _ = db.training_anlegen(conn, fr, "Training Freitag", None, uhrzeit="19:00")
mo_t, _ = db.training_anlegen(conn, mo, "Training Montag", None, uhrzeit="20:00")
fr_spiel, _ = db.training_anlegen(conn, fr, "Ligaspiel gegen SG Frei", None, uhrzeit="19:30",
                                  art="ligaspiel", gegner="SG Frei", heim=1)
for t_ in (fr_t, mo_t):
    for n in ["Anna", "Bea", "Cleo", "Dora", "Eva", "Fee"]:
        db.teilnahme_setzen(conn, t_, sp[n], "anwesend")
conn.close()

for wer, c in (("Spielerin", A), ("Trainer", T)):
    liste = {t["id"]: t for t in c.get("/api/trainings").json()}
    check(liste[fr_t]["freiwillig"] == 1, f"{wer}: Training am Freitag ist als freiwillig markiert")
    check(liste[mo_t]["freiwillig"] == 0, f"{wer}: Training am Montag ist es nicht")
    check(liste[fr_spiel]["freiwillig"] == 0, f"{wer}: ein Spiel am Freitag ist nie freiwillig")
check(T.get(f"/api/trainings/{fr_t}").json()["freiwillig"] == 1, "auch die Detailansicht meldet es")

gesendet.clear()
P["Fee"].post(f"/api/trainings/{fr_t}/teilnahme", json={"status": "abgesagt", "grund": "krank"})
check(not gesendet, "Freitag: fällt die Zahl unter die Grenze, gibt es keine Warnung an die Trainer")
P["Fee"].post(f"/api/trainings/{mo_t}/teilnahme", json={"status": "abgesagt", "grund": "krank"})
check(len(gesendet) == 1 and gesendet[0]["art"] == "warnungen", "Montag: dieselbe Lage warnt weiterhin")

# ====================== Automatische Erinnerung "bitte zu-/absagen" ===
tage_fr = (4 - HEUTE.weekday()) % 7 or 7          # bis zum nächsten Freitag
tage_mo = (0 - HEUTE.weekday()) % 7 or 7          # bis zum nächsten Montag
conn = db.verbinde()
fr_id, _ = db.training_anlegen(conn, tag(tage_fr), "Training Freitag", None, uhrzeit="19:00")
mo_id, _ = db.training_anlegen(conn, tag(tage_mo), "Training Montag", None, uhrzeit="20:00")
check(db.offene_spieler_benutzer(conn, fr_id) and db.offene_spieler_benutzer(conn, mo_id),
      "Voraussetzung: bei beiden Terminen fehlen noch Antworten")
gesendet.clear()
r = push_erinnerung.erinnere(conn, tage_fr, False)
check(not gesendet and r["trainings"] == 0, "Freitags-Training: keine automatische Erinnerung")
r = push_erinnerung.erinnere(conn, tage_mo, False)
check(len(gesendet) >= 1 and gesendet[-1]["art"] == "termine" and r["trainings"] >= 1,
      "Montags-Training: die Erinnerung geht weiter raus")
conn.close()
# Die Erinnerung, die der Trainer von Hand auslöst, bleibt auch freitags möglich (bewusste Handlung).
gesendet.clear()
check(T.post(f"/api/trainings/{fr_id}/erinnern").status_code == 200 and len(gesendet) == 1,
      "Trainer kann die Erinnerung für einen Freitag von Hand auslösen")

# ================================================ Abfahrts-/Anwurf-Erinnerung ===
conn = db.verbinde()
morgen = tag(1)
aus, _ = db.training_anlegen(conn, morgen, "Ligaspiel bei SG Fern", None, uhrzeit="19:30", ort="Halle Fern",
                             art="ligaspiel", gegner="SG Fern", heim=0, abfahrt="16:30")
heim, _ = db.training_anlegen(conn, tag(2), "Testspiel gegen TSV Nah", None, uhrzeit="18:00",
                              ort="Sporthalle Gerhausen", art="testspiel", gegner="TSV Nah", heim=1)
trn, _ = db.training_anlegen(conn, morgen, "Training", None, uhrzeit="20:00")
for t_ in (aus, heim, trn):
    db.teilnahme_setzen(conn, t_, sp["Anna"], "anwesend")
    db.teilnahme_setzen(conn, t_, sp["Bea"], "unsicher")
    db.teilnahme_setzen(conn, t_, sp["Cleo"], "abgesagt", "krank")
gesendet.clear()
r = push_spieltag.erinnere(conn, HEUTE, 1)
check(len(gesendet) == 1, "am Vortag: nur das Auswaertsspiel von morgen (kein Training, kein Spiel uebermorgen)")
check(gesendet[0]["an"] == sorted([bn["Anna"], bn["Bea"]]), "Zusage und 'unsicher' bekommen sie, die Absage nicht")
check("16:30" in gesendet[0]["text"] and "SG Fern" in gesendet[0]["text"] and "Abfahrt" in gesendet[0]["text"],
      "Text nennt Abfahrt und Gegner")
check(gesendet[0]["art"] == "termine", "Art 'termine'")
check(r["gesendet_termine"] == 1, "Rueckgabe zaehlt die Spiele")
gesendet.clear()
push_spieltag.erinnere(conn, HEUTE, 1)
check(not gesendet, "zweiter Lauf am selben Tag sendet nichts (Einmaligkeit)")
push_spieltag.erinnere(conn, HEUTE + timedelta(days=1), 0)
check(len(gesendet) == 1 and "heute" in gesendet[0]["titel"].lower(), "am Spieltag kommt eine zweite, andere Nachricht")
gesendet.clear()
push_spieltag.erinnere(conn, HEUTE + timedelta(days=1), 1)       # Heimspiel (uebermorgen) am Vortag
check(len(gesendet) == 1 and "Anwurf" in gesendet[0]["text"] and "18:00" in gesendet[0]["text"],
      "Heimspiel: Text nennt den Anwurf statt einer Abfahrt")
gesendet.clear()
r = push_spieltag.erinnere(conn, HEUTE, 1, trocken=True)
check(not gesendet, "Trockenlauf sendet nichts")
conn.close()

# ======================================== bestehende Pushes tragen jetzt eine Art ===
gesendet.clear()
r = T.post(f"/api/trainings/{tw}/erinnern")
check(r.status_code == 200 and gesendet and gesendet[-1]["art"] == "termine", "manuelle Erinnerung: Art 'termine'")
r = T.post("/api/todos", json={"spieler_id": sp["Anna"], "text": "Fangen mit zwei Händen"})
todo_id = db.verbinde().execute("SELECT id FROM todo").fetchone()["id"]
A.post(f"/api/todos/{todo_id}/waehlen", json={"gewaehlt": True})
gesendet.clear()
T.post(f"/api/todos/{todo_id}/feedback", json={"woche": db.woche_montag(), "text": "gut", "ergebnis": "bleibt"})
check(gesendet and gesendet[-1]["art"] == "rueckmeldungen", "To-Do-Feedback: Art 'rueckmeldungen'")

print("\nAlle Push-Ausloeser-Tests gruen.")
