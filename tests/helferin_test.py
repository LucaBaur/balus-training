"""Tests fuer "Helferinnen": ehemalige Spielerinnen (nicht mehr im Kader), die noch ein Konto haben und
zum Beispiel ein Amt uebernehmen (etwa Kassenwart oder Social Media).

Technisch: Spieler-Eintrag `aktiv = 0` + ein aktives Konto (rolle 'spieler'). Sie darf sich anmelden und ein
Amt haben, soll aber nicht wie eine Spielerin behandelt werden: keine Erinnerungen, keine Zusage, keine
Teilnehmerliste, nicht in der Nutzungsuebersicht. Alle Namen hier sind erfunden.

Laeuft gegen eine temporaere Datenbank. Start:  py tests/helferin_test.py
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

tmp = Path(tempfile.mkdtemp(prefix="helferin_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
mia = db.spieler_anlegen(conn, "Mia")                 # aktive Spielerin mit Konto
hella = db.spieler_anlegen(conn, "Hella")             # ehemalig, mit Konto = Helferin
gerda = db.spieler_anlegen(conn, "Gerda")             # ehemalig, OHNE Konto
db.spieler_aktualisieren(conn, hella, aktiv=False)
db.spieler_aktualisieren(conn, gerda, aktiv=False)
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
konto_mia = db.benutzer_anlegen(conn, "Mia", "spieler", auth.hash_pin("2222"), mia)
konto_hella = db.benutzer_anlegen(conn, "Hella", "spieler", auth.hash_pin("3333"), hella)
tid, _ = db.training_anlegen(conn, (date.today() + timedelta(days=3)).isoformat(), "Training", None, uhrzeit="20:00")
conn.close()


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def client(name, pin):
    c = TestClient(balu.app)
    r = c.post("/api/login", json={"name": name, "pin": pin})
    assert r.status_code == 200, (name, r.text)
    return c


T, M, H = client("Trainer", "1111"), client("Mia", "2222"), client("Hella", "3333")


def amt_id(schluessel):
    c = db.verbinde()
    try:
        return c.execute("SELECT id FROM amt WHERE schluessel = ?", (schluessel,)).fetchone()["id"]
    finally:
        c.close()


# --- Anmeldung und Profil --------------------------------------------------------------------------------------
check(M.get("/api/me").json()["im_kader"] is True, "/api/me: Mia ist im Kader")
check(H.get("/api/me").json()["im_kader"] is False, "/api/me: Hella (Helferin) ist nicht im Kader")
check(T.get("/api/me").json()["im_kader"] is None, "/api/me: der Trainer hat keinen Spieler-Eintrag, im_kader ist leer")

# --- Keine Zusage, keine Erinnerung, keine Teilnehmerliste ---------------------------------------------------
check(H.post(f"/api/trainings/{tid}/teilnahme", json={"status": "anwesend"}).status_code == 403,
      "Hella kann nicht zusagen (sie gehört nicht zum Kader)")
check(M.post(f"/api/trainings/{tid}/teilnahme", json={"status": "anwesend"}).status_code == 200, "Mia kann zusagen")
c = db.verbinde()
check(konto_hella not in db.offene_spieler_benutzer(c, tid), "Hella bekommt keine Erinnerung „bitte zu-/absagen“")
check(konto_mia not in db.offene_spieler_benutzer(c, tid), "(Mia hat geantwortet: auch keine)")
tid2, _ = db.training_anlegen(c, (date.today() + timedelta(days=4)).isoformat(), "Training 2", None, uhrzeit="20:00")
check(db.offene_spieler_benutzer(c, tid2) == [konto_mia], "Bei einem Termin ohne Antworten wird nur Mia erinnert")
c.close()
detail = T.get(f"/api/trainings/{tid}").json()
check(hella not in [p["id"] for p in detail["teilnahme"]], "Hella steht nicht in der Teilnehmerliste")
check(hella not in [s["id"] for s in T.get("/api/spieler").json()] and hella not in [s["id"] for s in T.get("/api/rangliste").json()],
      "Hella steht weder im Kader noch in der Rangliste")
check("Hella" not in [k["name"] for k in T.get("/api/nutzung").json()["konten"]]
      and "Mia" in [k["name"] for k in T.get("/api/nutzung").json()["konten"]],
      "Die Nutzungsübersicht (Videos ansehen usw.) führt nur Spielerinnen, nicht Hella")

# --- Amt: Helferin ist auswählbar, ehemalige ohne Konto nicht -----------------------------------------------
kader = {k["name"] for k in T.get("/api/aemter").json()["kader"]}
check({"Mia", "Hella"} <= kader and "Gerda" not in kader,
      "Bei den Ämtern sind Spielerinnen UND Helferinnen wählbar; ehemalige ohne Konto nicht")
check(M.get("/api/aemter").json()["kader"] == T.get("/api/aemter").json()["kader"], "…für Spielerinnen und Trainer gleich")

r = T.post(f"/api/aemter/{amt_id('kassenwart')}/inhaber", json={"spieler_id": hella, "da": True})
check(r.status_code == 200, "Der Trainer macht Hella zur Kassenwartin")
me = H.get("/api/me").json()
check(me["rechte"] == ["kasse"] and [a["name"] for a in me["aemter"]] == ["Kassenwart"] and me["im_kader"] is False,
      "Hella hat das Recht „kasse“ und das Amt, bleibt aber außerhalb des Kaders")
check(H.post("/api/kasse/buchung", json={"art": "forderung", "betrag_cent": 300, "text": "Zu spät", "spieler_id": mia}).status_code == 200,
      "Hella bucht als Kassenwartin eine Strafe für Mia")
k = H.get("/api/kasse").json()
check(k["darf_buchen"] and "Hella" not in [x["name"] for x in k["kader"]] and "Mia" in [x["name"] for x in k["kader"]],
      "Beim Buchen stehen die Spielerinnen zur Wahl, nicht die Helferin selbst")
check(M.get("/api/kasse").json()["mein_offen_cent"] == 300, "Mia sieht ihre Strafe")
check(H.get("/api/trainings").status_code == 200, "Hella sieht weiter die Termine (nur Lesen)")

# --- Amtsliste (Zähler) betrifft nur den Kader ------------------------------------------------------------------
getraenke = amt_id("getraenke")
r = T.get(f"/api/aemter/{getraenke}/liste").json()
check("Hella" not in [z["name"] for z in r["zaehler"]] and "Mia" in [z["name"] for z in r["zaehler"]],
      "Der Zähler der Listen (wer wie oft dran war) führt Hella nicht")

print("\nalles ok")
