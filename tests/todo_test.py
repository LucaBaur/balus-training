"""Tests fuer Wochen-To-Dos (Rechte, Wahl-Limit, Idempotenz, Feedback, Push, Wochenende).

Laeuft gegen eine temporaere Datenbank - die echte elo.db bleibt unberuehrt.
Start:  py tests/todo_test.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
import push  # noqa: E402
import todo_wochenende  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="todo_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
bea = db.spieler_anlegen(conn, "Bea")
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
anna_b = db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)
db.benutzer_anlegen(conn, "Bea", "spieler", auth.hash_pin("4444"), bea)
conn.close()

gesendet = []                       # (empfaenger, titel, text)
push.sende = lambda conn, ids, titel, text, url="/", art=None: gesendet.append((sorted(ids), titel, text)) or {"gesendet": len(ids)}


def client(name, pin):
    c = TestClient(balu.app)
    assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


T, A, B = client("Trainer", "1111"), client("Anna", "2222"), client("Bea", "4444")


def anlegen(text, sid=anna):
    return T.post("/api/todos", json={"spieler_id": sid, "text": text})


def meine(c):
    return {t["text"]: t for t in c.get("/api/todos").json()["todos"]}


# --- Anlegen: nur Trainer, Text geprueft -------------------------------------
check(A.post("/api/todos", json={"spieler_id": anna, "text": "x"}).status_code == 403,
      "Spielerin darf keine To-Dos anlegen")
check(anlegen("   ").status_code == 400, "leerer Text wird abgelehnt")
check(anlegen("x" * 201).status_code == 400, "zu langer Text wird abgelehnt")
check(anlegen("Fangen mit zwei Händen").status_code == 200, "Trainer legt To-Do an")
anlegen("Sprungwurf aus dem Stand")
anlegen("Abwehr: Füße bewegen")
anlegen("Nur für Bea", bea)
check(set(meine(A)) == {"Fangen mit zwei Händen", "Sprungwurf aus dem Stand", "Abwehr: Füße bewegen"},
      "Anna sieht genau ihre drei To-Dos, nicht die von Bea")
check(A.get("/api/todos/team").status_code == 403, "Team-Übersicht nur für Trainer")

# --- Wählen: Limit, Idempotenz, fremde To-Dos ---------------------------------
fangen = meine(A)["Fangen mit zwei Händen"]["id"]
wurf = meine(A)["Sprungwurf aus dem Stand"]["id"]
bea_todo = meine(B)["Nur für Bea"]["id"]
wahl = lambda c, tid, an=True: c.post(f"/api/todos/{tid}/waehlen", json={"gewaehlt": an})  # noqa: E731

check(wahl(A, bea_todo).status_code == 400, "fremdes To-Do lässt sich nicht wählen")
check(wahl(A, fangen).status_code == 200 and meine(A)["Fangen mit zwei Händen"]["gewaehlt"], "Anna wählt ein To-Do")
check(wahl(A, fangen).status_code == 200, "Wählen ist idempotent (zweimal = einmal)")
check(wahl(A, wurf).status_code == 400, "zweite Wahl in derselben Woche wird abgelehnt (Limit 1)")
check(wahl(A, fangen, False).status_code == 200 and not meine(A)["Fangen mit zwei Händen"]["gewaehlt"],
      "Auswahl lässt sich zurücknehmen")
check(wahl(A, fangen, False).status_code == 200, "Zurücknehmen ist idempotent")
wahl(A, fangen)

# --- Trainer sieht die Wahl -----------------------------------------------------
team = T.get("/api/todos/team").json()
anna_t = next(s for s in team["spielerinnen"] if s["name"] == "Anna")
check(team["warten"] == 1 and [t["text"] for t in anna_t["todos"] if t["gewaehlt"]] == ["Fangen mit zwei Händen"],
      "Trainer sieht Annas Wahl und 1 wartendes Feedback")
check(team["warten_faellig"] == 0 and not anna_t["todos"][0]["feedback_faellig"],
      "Laufende Woche: Feedback ist noch nicht fällig (Spielerin probiert noch)")
conn = db.verbinde()
conn.execute("UPDATE todo_woche SET woche = '2000-01-03'")          # Woche ist vorbei
conn.commit()
check(T.get("/api/todos/team").json()["warten_faellig"] == 1, "Nach Ablauf der Woche ist das Feedback fällig")
conn.execute("UPDATE todo_woche SET woche = ?", (db.woche_montag(),))
conn.commit()
conn.close()

# --- Wochenende-Push an Trainer ---------------------------------------------------
conn = db.verbinde()
r = todo_wochenende.melde(conn, trocken=True)
check(r["wartend"] == 1 and not gesendet, "Wochenend-Job im Trockenlauf zählt, sendet nichts")
r = todo_wochenende.melde(conn, trocken=False)
check(r["gesendet"] > 0 and gesendet and gesendet[-1][0] == db.trainer_benutzer_ids(conn)
      and "Anna" in gesendet[-1][2], "Wochenend-Job meldet den Trainern, wer auf Feedback wartet")
conn.close()

# --- Feedback ------------------------------------------------------------------------
woche = db.woche_montag()
fb = lambda c, tid, w, erg, text="": c.post(f"/api/todos/{tid}/feedback", json={"woche": w, "text": text, "ergebnis": erg})  # noqa: E731
check(fb(A, fangen, woche, "erledigt").status_code == 403, "Spielerin darf kein Feedback geben")
check(fb(T, fangen, woche, "vielleicht").status_code == 400, "unbekanntes Ergebnis wird abgelehnt")
check(fb(T, wurf, woche, "bleibt").status_code == 400, "Feedback nur zu gewählten To-Dos")
gesendet.clear()
check(fb(T, fangen, woche, "bleibt", "Schon besser, noch bei hohen Bällen üben").status_code == 200,
      "Trainer gibt Feedback „bleibt“")
t = meine(A)["Fangen mit zwei Händen"]
check(t["status"] == "offen" and t["wochen"][0]["feedback"].startswith("Schon besser"),
      "To-Do bleibt offen, Annas Ansicht zeigt das Feedback")
check(gesendet and gesendet[-1][0] == [anna_b], "Anna bekommt einen Push zum Feedback")
check(wahl(A, fangen, False).status_code == 400, "Wahl mit Feedback lässt sich nicht mehr zurücknehmen")
check(T.get("/api/todos/team").json()["warten"] == 0, "nach Feedback wartet nichts mehr")

# Nächste Woche: dasselbe To-Do wieder wählen und diesmal abhaken
conn = db.verbinde()
conn.execute("UPDATE todo_woche SET woche = '2000-01-03'")     # die Wahl liegt jetzt "in der Vergangenheit"
conn.commit()
conn.close()
check(wahl(A, fangen).status_code == 200, "in der neuen Woche kann dasselbe To-Do erneut gewählt werden")
gesendet.clear()
check(fb(T, fangen, woche, "erledigt", "Sitzt!").status_code == 200, "Trainer hakt das To-Do ab")
t = meine(A)["Fangen mit zwei Händen"]
check(t["status"] == "erledigt" and t["erledigt_am"], "To-Do steht für Anna als erledigt da")
check(wahl(A, fangen).status_code == 200, "bereits gewählte Woche bleibt idempotent")
check(gesendet and gesendet[-1][1].startswith("To-Do geschafft"), "Push „geschafft“ geht an Anna")
check(wahl(A, wurf).status_code == 400, "das Limit zählt auch die bereits abgehakte Wahl dieser Woche")

# --- Ändern, Wiederöffnen, Löschen -----------------------------------------------------
check(T.post(f"/api/todos/{fangen}/aendern", json={"status": "offen"}).status_code == 200
      and meine(A)["Fangen mit zwei Händen"]["status"] == "offen", "Trainer öffnet ein To-Do wieder")
check(T.post(f"/api/todos/{wurf}/aendern", json={"text": "Sprungwurf mit Anlauf"}).status_code == 200
      and "Sprungwurf mit Anlauf" in meine(A), "Trainer ändert den Text")
check(A.post(f"/api/todos/{wurf}/loeschen").status_code == 403, "Spielerin darf nicht löschen")
check(T.post(f"/api/todos/{wurf}/loeschen").status_code == 200 and "Sprungwurf mit Anlauf" not in meine(A),
      "Trainer löscht ein To-Do")
check(T.post("/api/todos/99999/loeschen").status_code == 404, "unbekanntes To-Do gibt 404")

print("\nAlle To-Do-Tests bestanden.")
