"""Tests fuer die Ämter (Rechte, Inhaberinnen, Zuteilungslisten, Bussle).

Laeuft gegen eine temporaere Datenbank - die echte elo.db bleibt unberuehrt.
Start:  py tests/aemter_test.py
"""
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import aemter  # noqa: E402
import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="aemter_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
bea = db.spieler_anlegen(conn, "Bea")
cora = db.spieler_anlegen(conn, "Cora")
dora = db.spieler_anlegen(conn, "Dora")
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)
db.benutzer_anlegen(conn, "Bea", "spieler", auth.hash_pin("3333"), bea)
db.benutzer_anlegen(conn, "Cora", "spieler", auth.hash_pin("4444"), cora)
conn.close()


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def client(name, pin):
    c = TestClient(balu.app)
    assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


T, A, B, C = client("Trainer", "1111"), client("Anna", "2222"), client("Bea", "3333"), client("Cora", "4444")
OFFEN = TestClient(balu.app)


def amt_id(schluessel):
    c = db.verbinde()
    try:
        return c.execute("SELECT id FROM amt WHERE schluessel = ?", (schluessel,)).fetchone()["id"]
    finally:
        c.close()


def inhaber(c, schluessel, spieler, da=True):
    return c.post(f"/api/aemter/{amt_id(schluessel)}/inhaber", json={"spieler_id": spieler, "da": da})


def termin(c, **kw):
    daten = {"datum": (date.today() + timedelta(days=kw.pop("tage", 5))).isoformat(), "art": "training"}
    daten.update(kw)
    r = c.post("/api/trainings", json=daten)
    return r


# --- Standard-Ämter ---------------------------------------------------------------
conn = db.verbinde()
check(conn.execute("SELECT COUNT(*) FROM amt").fetchone()[0] == len(aemter.AEMTER_START),
      "alle Standard-Ämter sind angelegt")
conn.execute("UPDATE amt SET beschreibung = 'Vom Trainer geändert' WHERE schluessel = 'essensplan'")
conn.commit()
db.init_db(conn)
check(conn.execute("SELECT COUNT(*) FROM amt").fetchone()[0] == len(aemter.AEMTER_START),
      "erneuter Start legt nichts doppelt an")
check(conn.execute("SELECT beschreibung FROM amt WHERE schluessel = 'essensplan'").fetchone()[0] == "Vom Trainer geändert",
      "erneuter Start überschreibt keine geänderte Beschreibung")
conn.close()

# --- Lesen: nur angemeldet ------------------------------------------------------------
check(OFFEN.get("/api/aemter").status_code == 401, "Ämter nur für Angemeldete")
liste = A.get("/api/aemter").json()
check(len(liste["aemter"]) == len(aemter.AEMTER_START) and not liste["kann_verwalten"]
      and {k["name"] for k in liste["kader"]} == {"Anna", "Bea", "Cora", "Dora"},
      "Spielerin sieht alle Ämter und den Kader, verwaltet aber nichts")
check(T.get("/api/aemter").json()["kann_verwalten"], "Trainer darf verwalten")
rechte = {a["schluessel"]: a["rechte"] for a in T.get("/api/aemter").json()["aemter"]}
check(rechte["balu_app"] == [aemter.RECHTE["termine"]] and not rechte["kapitaen"],
      "die Anzeige nennt im Klartext, welches Recht ein Amt gibt")

# --- Inhaberinnen: nur Trainer, setzen statt umschalten ----------------------------------
check(inhaber(A, "kapitaen", anna).status_code == 403, "Spielerin vergibt keine Ämter")
check(inhaber(T, "kapitaen", anna).status_code == 200, "Trainer vergibt ein Amt")
check(inhaber(T, "kapitaen", anna).status_code == 200, "Vergeben ist idempotent")
check(inhaber(T, "kapitaen", 999).status_code == 404, "unbekannte Spielerin gibt 404")
check(T.post("/api/aemter/9999/inhaber", json={"spieler_id": anna, "da": True}).status_code == 404,
      "unbekanntes Amt gibt 404")
kap = next(a for a in A.get("/api/aemter").json()["aemter"] if a["schluessel"] == "kapitaen")
check([i["name"] for i in kap["inhaber"]] == ["Anna"] and kap["meine"], "Anna ist einmal Kapitän und sieht das")
me = A.get("/api/me").json()
check([a["name"] for a in me["aemter"]] == ["Kapitän"] and me["rechte"] == [], "/api/me nennt Ämter, ein Titel gibt kein Recht")
check(inhaber(T, "kapitaen", bea).status_code == 200
      and len([a for a in B.get("/api/aemter").json()["aemter"] if a["schluessel"] == "kapitaen"][0]["inhaber"]) == 2,
      "mehrere Inhaberinnen je Amt sind möglich")
check(inhaber(T, "kapitaen", bea, False).status_code == 200 and inhaber(T, "kapitaen", bea, False).status_code == 200,
      "Entziehen ist idempotent")

# --- Eigenes Amt anlegen und Beschreibung ändern ---------------------------------------------
check(A.post("/api/aemter", json={"name": "Neu"}).status_code == 403, "Spielerin legt kein Amt an")
check(T.post("/api/aemter", json={"name": "  "}).status_code == 400, "leerer Name wird abgelehnt")
check(T.post("/api/aemter", json={"name": "kapitän"}).status_code == 400, "doppelter Name wird abgelehnt")
check(T.post("/api/aemter", json={"name": "Zeugwart", "beschreibung": "Bälle"}).status_code == 200, "Trainer legt ein Amt an")
check(T.post(f"/api/aemter/{amt_id('essensplan')}/beschreibung", json={"beschreibung": "Neu geklärt"}).status_code == 200
      and A.post(f"/api/aemter/{amt_id('essensplan')}/beschreibung", json={"beschreibung": "x"}).status_code == 403,
      "Beschreibung ändert nur der Trainer")

# --- Das Amt "Balu-Trainings-App": Termine anlegen und löschen -----------------------------------
check(termin(B).status_code == 403, "ohne Amt darf Bea keinen Termin anlegen")
check(inhaber(T, "balu_app", bea).status_code == 200, "Trainer gibt Bea das Balu-App-Amt")
check(B.get("/api/me").json()["rechte"] == ["termine"], "Bea hat jetzt das Recht „termine“")
r = termin(B)
check(r.status_code == 200 and r.json()["neu"], "Bea legt ein Training an")
r = termin(B, art="ligaspiel", gegner="TSV Test", heim=False, abfahrt="17:30", tage=7)
check(r.status_code == 200, "Bea legt ein Auswärtsspiel an")
spiel_id = r.json()["id"]
check(termin(C).status_code == 403, "Cora ohne Amt bleibt ausgesperrt")
check(B.post(f"/api/trainings/{spiel_id}/plan", json={"markdown": "x"}).status_code == 403,
      "das Amt gibt keinen Zugriff auf den Trainingsplan")
check(B.get("/api/rangliste").status_code == 403, "und keinen auf die Rangliste")
check(inhaber(B, "balu_app", cora).status_code == 403, "Bea darf selbst keine Ämter vergeben")
loeschbar = termin(B, tage=30).json()["id"]
check(B.post(f"/api/trainings/{loeschbar}/loeschen").status_code == 200, "Bea löscht einen Termin")
check(C.post(f"/api/trainings/{loeschbar}/loeschen").status_code == 403, "Cora darf nicht löschen")
check(inhaber(T, "balu_app", bea, False).status_code == 200 and termin(B, tage=9).status_code == 403,
      "Amt entzogen = Recht weg")
check(T.post("/api/trainings", json={"datum": "2031-01-01", "art": "training"}).status_code == 200,
      "der Trainer darf weiterhin alles")

# --- Zuteilungsliste (Waschliste = nur Spiele) -----------------------------------------------------
inhaber(T, "waschliste", anna)
inhaber(T, "leibchen", bea)
w, l = amt_id("waschliste"), amt_id("leibchen")
zut = lambda c, amt, tid, sp, da=True: c.post(f"/api/aemter/{amt}/zuteilung", json={"training_id": tid, "spieler_id": sp, "da": da})  # noqa: E731

conn = db.verbinde()
training_id = conn.execute("SELECT id FROM trainings WHERE art = 'training' ORDER BY datum LIMIT 1").fetchone()["id"]
conn.close()

check(zut(C, w, spiel_id, cora).status_code == 403, "ohne das Amt keine Zuteilung")
check(zut(B, w, spiel_id, cora).status_code == 403, "ein anderes Amt gibt keine Rechte an dieser Liste")
check(zut(A, w, spiel_id, cora).status_code == 200, "Anna (Waschliste) teilt Cora für das Spiel ein")
check(zut(A, w, spiel_id, cora).status_code == 200, "Einteilen ist idempotent")
check(zut(A, w, training_id, cora).status_code == 400, "Waschliste gilt nicht für Trainings")
check(zut(B, l, training_id, dora).status_code == 200, "Bea (Leibchen) teilt Dora für das Training ein")
check(zut(B, l, spiel_id, dora).status_code == 400, "Leibchen gelten nicht für Spiele")
check(zut(T, w, spiel_id, dora).status_code == 200, "der Trainer pflegt jede Liste")
check(zut(A, 9999, spiel_id, cora).status_code == 404, "unbekanntes Amt gibt 404")
check(zut(A, w, 9999, cora).status_code == 404, "unbekannter Termin gibt 404")
check(zut(T, amt_id("tape"), spiel_id, cora).status_code == 400, "ein reines Titel-Amt hat keine Liste")

d = C.get(f"/api/aemter/{w}/liste").json()
spiel = next(t for t in d["termine"] if t["training_id"] == spiel_id)
check({z["name"] for z in spiel["zugeteilt"]} == {"Cora", "Dora"}, "jede sieht, wer die Trikots mitnimmt")
check(not d["darf_pflegen"] and A.get(f"/api/aemter/{w}/liste").json()["darf_pflegen"],
      "darf_pflegen stimmt für Cora (nein) und Anna (ja)")
check(training_id not in [t["training_id"] for t in d["termine"]], "Trainings stehen nicht in der Waschliste")
z = {x["name"]: x["anzahl"] for x in d["zaehler"]}
check(z == {"Anna": 0, "Bea": 0, "Cora": 1, "Dora": 1} and d["zaehler"][0]["anzahl"] == 0,
      "Zähler: wer selten dran war, steht oben")

check(A.post(f"/api/aemter/{w}/erledigt", json={"training_id": spiel_id, "spieler_id": cora, "erledigt": True}).status_code == 200,
      "Anna hakt ab")
check(C.post(f"/api/aemter/{w}/erledigt", json={"training_id": spiel_id, "spieler_id": cora, "erledigt": True}).status_code == 403,
      "Cora darf sich nicht selbst abhaken")
check(A.post(f"/api/aemter/{w}/erledigt", json={"training_id": spiel_id, "spieler_id": bea, "erledigt": True}).status_code == 404,
      "Abhaken ohne Zuteilung gibt 404")
check(zut(A, w, spiel_id, dora, False).status_code == 200
      and {x["name"] for x in A.get(f"/api/aemter/{w}/liste").json()["termine"][0]["zugeteilt"]} == {"Cora"},
      "Zuteilung lässt sich zurücknehmen")

# --- Saison und Fenster (feste Daten, ohne die Uhr) -------------------------------------------------
check(aemter.saison_beginn(date(2026, 11, 4)) == "2026-07-01" and aemter.saison_beginn(date(2027, 3, 1)) == "2026-07-01"
      and aemter.saison_beginn(date(2026, 6, 30)) == "2025-07-01", "Saison beginnt am 1. Juli")
conn = db.verbinde()
alt, neu = (db.training_anlegen(conn, d_, "Spiel", None, art="testspiel", gegner="G", heim=1)[0]
            for d_ in ("2026-06-20", "2026-11-10"))
aemter.zuteilung_setzen(conn, w, alt, bea, True)
aemter.zuteilung_setzen(conn, w, neu, bea, True)
stand = aemter.liste(conn, w, heute=date(2026, 11, 4))
check(next(x for x in stand["zaehler"] if x["name"] == "Bea")["anzahl"] == 1,
      "Zuteilungen aus der Vorsaison zählen nicht")
check(neu in [t["training_id"] for t in stand["termine"]] and alt not in [t["training_id"] for t in stand["termine"]],
      "die Terminliste zeigt nur das Zeitfenster")
check(next(x for x in aemter.liste(conn, w, heute=date(2026, 11, 20))["zaehler"] if x["name"] == "Bea")["offen"] == 1,
      "ein vergangener, nicht abgehakter Termin zählt als offen")
check(next(x for x in aemter.liste(conn, w, heute=date(2026, 11, 4))["zaehler"] if x["name"] == "Bea")["offen"] == 0,
      "ein künftiger Termin ist noch nicht offen")
conn.execute("UPDATE spieler SET aktiv = 0 WHERE id = ?", (dora,))
conn.commit()
check("Dora" not in {x["name"] for x in aemter.liste(conn, w)["zaehler"]}, "inaktive Spielerinnen stehen nicht im Zähler")
conn.execute("UPDATE spieler SET aktiv = 1 WHERE id = ?", (dora,))
conn.commit()

# --- "Du bist dran" für Home ------------------------------------------------------------------------
conn = db.verbinde()
vorbei, bald = (db.training_anlegen(conn, d_, "Spiel", None, art="testspiel", gegner="G", heim=1)[0]
                for d_ in ("2026-11-01", "2026-11-12"))
aemter.zuteilung_setzen(conn, w, vorbei, cora, True)
aemter.zuteilung_setzen(conn, w, bald, cora, True)
heute = date(2026, 11, 4)
meine = lambda: [a["training_id"] for a in aemter.aufgaben(conn, cora, heute) if a["training_id"] in (vorbei, bald)]  # noqa: E731
check(meine() == [vorbei, bald],
      "Home: ein vergangenes, nicht abgehaktes Spiel und das kommende stehen unter „Du bist dran“")
aemter.erledigt_setzen(conn, w, vorbei, cora, True)
check(meine() == [bald], "abgehakt verschwindet die Aufgabe")
check(aemter.aufgaben(conn, None, heute) == [] and aemter.aufgaben(conn, db.spieler_anlegen(conn, "Eva"), heute) == [], "ohne Zuteilung keine Aufgaben")
conn.close()
check(OFFEN.get("/api/aemter/meine-aufgaben").status_code == 401
      and C.get("/api/aemter/meine-aufgaben").status_code == 200, "Aufgaben-Endpunkt nur für Angemeldete")

# --- Termin löschen räumt die Zuteilung auf ---------------------------------------------------------
check(T.post(f"/api/trainings/{spiel_id}/loeschen").status_code == 200, "Trainer löscht das Spiel")
conn.close()
conn = db.verbinde()
check(conn.execute("SELECT COUNT(*) FROM amt_zuteilung WHERE training_id = ?", (spiel_id,)).fetchone()[0] == 0,
      "Zuteilungen des gelöschten Termins sind weg")
conn.close()

# --- Bussle -------------------------------------------------------------------------------------------
inhaber(T, "bussle", cora)
bu = amt_id("bussle")
auswaerts = termin(T, art="ligaspiel", gegner="TSV Fern", heim=False, abfahrt="16:00", tage=10).json()["id"]
daheim = termin(T, art="testspiel", gegner="TSV Nah", heim=True, tage=11).json()["id"]
status = lambda c, tid, s: c.post(f"/api/aemter/{bu}/bussle", json={"training_id": tid, "status": s})  # noqa: E731
check(status(A, auswaerts, "da").status_code == 403, "nur die Bussle-Inhaberin setzt den Status")
check(status(C, auswaerts, "da").status_code == 200, "Cora meldet: Bussle da")
check(status(C, auswaerts, "vielleicht").status_code == 400, "unbekannter Status wird abgelehnt")
check(status(C, daheim, "da").status_code == 400, "bei Heimspielen gibt es kein Bussle")
check(status(C, auswaerts, "da").status_code == 200, "Status setzen ist idempotent")
b = C.get(f"/api/aemter/{bu}/liste").json()
check([t["training_id"] for t in b["termine"]] == [auswaerts] and b["termine"][0]["status"] == "da",
      "die Liste zeigt nur Auswärtsspiele samt Status")
check(zut(C, bu, auswaerts, anna).status_code == 200 and zut(C, bu, auswaerts, bea).status_code == 200,
      "Cora trägt ein, wer selbst fährt")
b = A.get(f"/api/aemter/{bu}/liste").json()
check({z["name"]: z["anzahl"] for z in b["zaehler"]}["Anna"] == 1, "der Fahrten-Zähler steht für alle sichtbar")
check(status(C, auswaerts, None).status_code == 200
      and C.get(f"/api/aemter/{bu}/liste").json()["termine"][0]["status"] is None, "Status lässt sich zurücksetzen")
check(T.post(f"/api/aemter/{w}/bussle", json={"training_id": auswaerts, "status": "da"}).status_code == 400,
      "Bussle-Status gibt es nur bei einem Fahrten-Amt")

print("\nAlle Ämter-Tests bestanden.")
