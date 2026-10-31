"""Tests fuer Video-Kommentare (Rechte, Sichtbarkeit, privater Faden, Loeschen, Push).

Laeuft gegen eine temporaere Datenbank - die echte elo.db bleibt unberuehrt.
Start:  py tests/kommentar_test.py
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

tmp = Path(tempfile.mkdtemp(prefix="kommentar_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
bea = db.spieler_anlegen(conn, "Bea")
clara = db.spieler_anlegen(conn, "Clara")
trainer_id = db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
anna_b = db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)
bea_b = db.benutzer_anlegen(conn, "Bea", "spieler", auth.hash_pin("4444"), bea)
db.benutzer_anlegen(conn, "Clara", "spieler", auth.hash_pin("5555"), clara)
clip = db.clip_anlegen(conn, "Kreisanspiel", None, "x.mp4", None, 10.0, None, [anna, bea])
conn.close()

gesendet = []                       # (empfaenger, titel, text)
push.sende = lambda conn, ids, titel, text, url="/": gesendet.append((sorted(ids), titel, text)) or {}


def client(name, pin):
    c = TestClient(balu.app)
    assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


T, A, B, C = (client("Trainer", "1111"), client("Anna", "2222"),
              client("Bea", "4444"), client("Clara", "5555"))
Z = f"clip:{clip}"


def neu(c, text, **kw):
    return c.post("/api/kommentare", json={"ziel": Z, "text": text, **kw})


def texte(c):
    return [k["text"] for k in c.get(f"/api/kommentare?ziel={Z}").json()]


# Zugriff: nur wer das Video sehen darf
check(C.get(f"/api/kommentare?ziel={Z}").status_code == 403, "Clara (nicht zugeordnet): Lesen verboten")
check(neu(C, "hallo").status_code == 403, "Clara: Schreiben verboten")
check(TestClient(balu.app).get(f"/api/kommentare?ziel={Z}").status_code == 401, "Ohne Login: 401")
check(A.get("/api/kommentare?ziel=clip:999").status_code == 403, "Unbekannter Clip: 403")
check(A.get("/api/kommentare?ziel=quatsch").status_code == 403, "Ungueltiges Ziel: 403")

# Oeffentlicher Kommentar: alle Zugeordneten sehen ihn
r = neu(A, "Wo steht die Kreislaeuferin?")
check(r.status_code == 200 and texte(B) == ["Wo steht die Kreislaeuferin?"], "Oeffentlich: Bea sieht Annas Frage")
check(gesendet[-1][0] == [trainer_id], "Push: Frage geht an den Trainer")
check("Anna:" in gesendet[-1][2], "Push-Text nennt die Verfasserin")

# Antwort vom Trainer auf die oeffentliche Frage
frage = A.get(f"/api/kommentare?ziel={Z}").json()[0]["id"]
neu(T, "Neben der 6er-Abwehr.", antwort_auf=frage)
check(gesendet[-1][0] == [anna_b], "Push: Trainer-Antwort geht an Anna")
check(texte(B) == ["Wo steht die Kreislaeuferin?", "Neben der 6er-Abwehr."], "Antwort ist fuer Bea sichtbar")

# Antwort auf eine Antwort haengt am Ursprung (nur eine Ebene)
antwort_id = [k for k in T.get(f"/api/kommentare?ziel={Z}").json() if k["antwort_auf"]][0]["id"]
neu(B, "Danke!", antwort_auf=antwort_id)
k = [x for x in T.get(f"/api/kommentare?ziel={Z}").json() if x["text"] == "Danke!"][0]
check(k["antwort_auf"] == frage, "Antwort auf Antwort haengt am Ursprungs-Kommentar")

# Privater Faden
neu(A, "Ich verstehe den Laufweg nicht, peinlich.", nur_trainer=True)
check("Ich verstehe den Laufweg nicht, peinlich." not in texte(B), "Privat: Bea sieht es nicht")
check("Ich verstehe den Laufweg nicht, peinlich." in texte(A), "Privat: Anna sieht es selbst")
check("Ich verstehe den Laufweg nicht, peinlich." in texte(T), "Privat: Trainer sieht es")
privat = [x for x in A.get(f"/api/kommentare?ziel={Z}").json() if x["nur_trainer"]][0]
check(privat["eigene"] is True, "Privat: als eigener Kommentar markiert")
check(neu(B, "ich auch nicht", antwort_auf=privat["id"]).status_code == 400,
      "Bea kann nicht auf einen fremden privaten Kommentar antworten")

# Trainer-Antwort in einem privaten Faden bleibt privat, auch ohne Haekchen
neu(T, "Schau dir Sekunde 4 an.", antwort_auf=privat["id"])
check("Schau dir Sekunde 4 an." in texte(A), "Private Antwort: Anna sieht sie")
check("Schau dir Sekunde 4 an." not in texte(B), "Private Antwort: Bea sieht sie NICHT")
check(gesendet[-1][0] == [anna_b], "Push: private Antwort geht nur an Anna")

# Eine Spielerin kann einen oeffentlichen Faden privat fortsetzen
neu(B, "Darf ich dich dazu privat was fragen?", nur_trainer=True, antwort_auf=frage)
check("Darf ich dich dazu privat was fragen?" not in texte(A), "Private Antwort in oeffentlichem Faden: Anna sieht sie nicht")

# Eingabepruefung
check(neu(A, "   ").status_code == 400, "Leerer Kommentar: 400")
check(neu(A, "x" * 3000).status_code == 200, "Langer Kommentar wird akzeptiert ...")
c = db.verbinde()
check(max(len(r[0]) for r in c.execute("SELECT text FROM video_kommentar")) == 1000, "... und auf 1000 Zeichen gekuerzt")
c.close()
check(neu(A, "x", antwort_auf=99999).status_code == 400, "Antwort auf nicht vorhandenen Kommentar: 400")

# Loeschen
check(B.post(f"/api/kommentare/{frage}/loeschen").status_code == 404, "Bea darf Annas Kommentar nicht loeschen")
check(A.post(f"/api/kommentare/{frage}/loeschen").status_code == 200, "Anna loescht ihre Frage")
check("Neben der 6er-Abwehr." not in texte(T), "Antworten fallen mit weg")
rest = T.get(f"/api/kommentare?ziel={Z}").json()
check(T.post(f"/api/kommentare/{rest[0]['id']}/loeschen").status_code == 200, "Trainer darf jeden loeschen")

# Rate-Limit
ok = [neu(A, f"Spam {i}").status_code for i in range(40)]
check(200 in ok and ok[-1] == 400, "Stundenlimit bremst Spam")

# Ansicht-als schreibt nicht
check(T.post(f"/api/ansicht/{anna_b}").status_code == 200, "Ansicht als Anna")
check(neu(T, "darf nicht").status_code == 403, "Im Ansicht-Modus ist Schreiben gesperrt")

# Team -> Videos (Trainer): Hauptkommentare werden am eigenen Clip gezaehlt
eigener = next(x for x in client("Trainer", "1111").get("/api/clips").json() if x["id"] == clip)
check(eigener["kommentare"] > 0, "Eigene Clips: Kommentarzahl am Clip")
check(all("kommentare" not in x for x in client("Anna", "2222").get("/api/clips").json()),
      "Spielerin bekommt keine Zaehler (Clipliste unveraendert)")

print("\nAlle Tests gruen.")
