"""Tests fuer die Spiel-Nachbereitung (nur Trainer: Rechte, Nur-Spiele, Konflikt, Rueckspiel-Hinweis).

Laeuft gegen eine temporaere Datenbank - die echte elo.db bleibt unberuehrt.
Nur erfundene Namen und Texte.
Start:  py tests/nachbereitung_test.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="nachb_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

GEHEIM = "GEHEIMNOTIZ-4711"

conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
db.benutzer_anlegen(conn, "Trainer2", "trainer", auth.hash_pin("3333"))
db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)
hin, _ = db.training_anlegen(conn, "2026-09-12", "Hinspiel", art="ligaspiel", gegner="TV Musterstadt", heim=1)
rueck, _ = db.training_anlegen(conn, "2026-11-07", "Rückspiel", art="ligaspiel", gegner="  tv  MUSTERSTADT ", heim=0)
anders, _ = db.training_anlegen(conn, "2026-11-14", "Anderer Name", art="testspiel", gegner="Musterstadt II", heim=1)
fremd, _ = db.training_anlegen(conn, "2026-10-01", "Testspiel", art="testspiel", gegner="SG Beispiel", heim=1)
normal, _ = db.training_anlegen(conn, "2026-11-03", "Training")
conn.close()


def client(name, pin):
    c = TestClient(balu.app)
    assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


T, T2, A = client("Trainer", "1111"), client("Trainer2", "3333"), client("Anna", "2222")
URL = "/api/trainings/{}/nachbereitung"

# Rechte
check(TestClient(balu.app).get(URL.format(hin)).status_code == 401, "Ohne Login: 401")
check(A.get(URL.format(hin)).status_code == 403, "Spielerin: Lesen verboten")
check(A.post(URL.format(hin), json={"gedanken": "x"}).status_code == 403, "Spielerin: Schreiben verboten")

# Nur Spiele
check(T.get(URL.format(normal)).status_code == 404, "Normales Training: 404 (Lesen)")
check(T.post(URL.format(normal), json={"gedanken": "x"}).status_code == 404, "Normales Training: 404 (Schreiben)")
check(T.get(URL.format(9999)).status_code == 404, "Unbekannte ID: 404")

# Erstes Speichern
r = T.get(URL.format(hin)).json()
check(r["gedanken"] == "" and r["geaendert_am"] is None, "Leeres Spiel: leere Felder, kein Stand")
r = T.post(URL.format(hin), json={"gedanken": GEHEIM, "gegner": "Spielen schnell über Außen", "ansprache": "Montag: Lob",
                                  "basis": None})
check(r.status_code == 200 and r.json()["gedanken"] == GEHEIM, "Trainer speichert")
stand = r.json()["geaendert_am"]
check(r.json()["autor"] == "Trainer", "Autor wird festgehalten")

# Beide Trainer sehen es
check(T2.get(URL.format(hin)).json()["gedanken"] == GEHEIM, "Zweiter Trainer sieht die Notiz")

# Konflikt: veralteter Stand wird nicht ueberschrieben
r = T2.post(URL.format(hin), json={"gedanken": "neu", "basis": None})
check(r.status_code == 409 and r.json()["aktuell"]["gedanken"] == GEHEIM, "Veralteter Stand: 409, nichts ueberschrieben")
check(T.get(URL.format(hin)).json()["gedanken"] == GEHEIM, "Notiz nach Konflikt unveraendert")
r = T2.post(URL.format(hin), json={"gedanken": GEHEIM + " +", "gegner": "g", "ansprache": "a", "basis": stand})
check(r.status_code == 200 and r.json()["autor"] == "Trainer2", "Mit aktuellem Stand: Speichern klappt")

# Grenzen
check(T.post(URL.format(hin), json={"gedanken": "x" * 10001, "basis": r.json()["geaendert_am"]}).status_code == 400,
      "Zu langer Text: 400")
check(T.post(URL.format(hin), json={"vorspiel_id": normal, "basis": r.json()["geaendert_am"]}).status_code == 400,
      "Vorspiel muss ein Spiel sein: 400")

# Spielerinnen sehen nichts davon: Liste, Detail, Antworttexte
def nichts_geheimes(c, wer):
    for pfad in ("/api/trainings", f"/api/trainings/{hin}", f"/api/trainings/{rueck}", "/api/naechstes-training"):
        resp = c.get(pfad)
        check(GEHEIM not in resp.text and "Montag: Lob" not in resp.text and "nachbereitung" not in resp.text.lower(),
              f"{wer}: {pfad} enthaelt keine Nachbereitung")


nichts_geheimes(A, "Spielerin")
check("hat_nachbereitung" not in A.get("/api/trainings").json()[0], "Spielerin: kein Merker in der Liste")
liste = {t["id"]: t for t in T.get("/api/trainings").json()}
check(liste[hin]["hat_nachbereitung"] == 1 and liste[rueck]["hat_nachbereitung"] == 0, "Trainer: Merker nur beim Spiel mit Notiz")
check(GEHEIM not in T.get("/api/trainings").text, "Auch Trainer-Liste traegt nur den Merker, keinen Inhalt")
check(GEHEIM not in T.get(f"/api/trainings/{hin}").text, "Detail-Endpunkt traegt keine Notiz")

# Rueckspiel-Hinweis ueber normalisierten Gegnernamen
f = T.get(URL.format(rueck)).json()["frueher"]
check(len(f) == 1 and f[0]["training_id"] == hin and not f[0]["manuell"], "Rueckspiel: Notiz des Hinspiels (Name normalisiert)")
check(T.get(URL.format(hin)).json()["frueher"] == [], "Hinspiel zeigt keine spaeteren Notizen")
check(T.get(URL.format(fremd)).json()["frueher"] == [], "Anderer Gegner: kein Hinweis")

# Manuell, wenn die Schreibweise abweicht
check(T.get(URL.format(anders)).json()["frueher"] == [], "Abweichende Schreibweise: zunaechst kein Hinweis")
check(any(k["id"] == hin for k in T.get(URL.format(anders)).json()["kandidaten"]), "Kandidatenliste enthaelt das Hinspiel")
r = T.post(URL.format(anders), json={"vorspiel_id": hin, "basis": None})
check(r.status_code == 200 and [e["training_id"] for e in r.json()["frueher"]] == [hin]
      and r.json()["frueher"][0]["manuell"], "Manuell gewaehltes Vorspiel erscheint")

# Loeschen eines Spiels nimmt die Notiz mit; Vorspiel-Verweis wird geleert
c = db.verbinde()
db.training_loeschen(c, hin)
check(c.execute("SELECT COUNT(*) FROM spiel_nachbereitung WHERE training_id = ?", (hin,)).fetchone()[0] == 0,
      "Spiel geloescht -> Notiz weg")
check(c.execute("SELECT vorspiel_id FROM spiel_nachbereitung WHERE training_id = ?", (anders,)).fetchone()[0] is None,
      "Verweis auf geloeschtes Vorspiel wird NULL")
c.close()

print("\nAlle Tests gruen.")
