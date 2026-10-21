"""Tests fuer die Nutzungs-Erfassung (Melden, Rechte, Entprellen, Auswertung).

Laeuft gegen eine temporaere Datenbank - die echte elo.db bleibt unberuehrt.
Start:  py tests/nutzung_test.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="nutzung_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
bea = db.spieler_anlegen(conn, "Bea")
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)
db.benutzer_anlegen(conn, "Bea", "spieler", auth.hash_pin("4444"), bea)
conn.close()


def client(name, pin):
    c = TestClient(balu.app)
    r = c.post("/api/login", json={"name": name, "pin": pin})
    assert r.status_code == 200, r.text
    return c


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


T, A, B = client("Trainer", "1111"), client("Anna", "2222"), client("Bea", "4444")

# Login liefert spieler_id (Fehler v0.49: "Ich"-Reiter fehlte nach dem Login)
r = TestClient(balu.app).post("/api/login", json={"name": "Anna", "pin": "2222"})
check(r.json().get("spieler_id") == anna, "Login liefert spieler_id")

# Melden
ev = [{"typ": "besuch"},
      {"typ": "besuch"},                                    # zweiter Besuch im selben Schwung zaehlt nicht
      {"typ": "bereich", "ziel": "ich/videos"},
      {"typ": "bereich", "ziel": "ich/videos"},
      {"typ": "bereich", "ziel": "taktik/playbook"},
      {"typ": "video", "ziel": "clip:5", "info": "Kreisanspiel 1"},
      {"typ": "video", "ziel": "clip:5", "info": "Kreisanspiel 1"},
      {"typ": "unsinn", "ziel": "x"}]                       # unbekannter Typ wird verworfen
r = A.post("/api/nutzung", json={"ereignisse": ev})
check(r.status_code == 200 and r.json()["gespeichert"] == 6, "Anna meldet: 6 von 8 gespeichert")
r = A.post("/api/nutzung", json={"ereignisse": [{"typ": "besuch"}]})
check(r.json()["gespeichert"] == 0, "Weiterer Besuch binnen 30 Minuten wird entprellt")
check(client("Anna", "2222").post("/api/nutzung", json={"ereignisse": [{"typ": "bereich", "ziel": "home/home"}]})
      .json()["gespeichert"] == 1, "Bereich wird nicht entprellt")
check(TestClient(balu.app).post("/api/nutzung", json={"ereignisse": []}).status_code == 401,
      "Ohne Anmeldung: 401")
r = A.post("/api/nutzung", json={"ereignisse": [{"typ": "bereich", "ziel": "x" * 500, "info": "y" * 500}]})
c = db.verbinde()
z = c.execute("SELECT ziel, info FROM nutzung ORDER BY id DESC LIMIT 1").fetchone()
c.close()
check(len(z["ziel"]) == 60 and len(z["info"]) == 120, "Zu lange Texte werden gekuerzt")

# Rechte beim Lesen
check(A.get("/api/nutzung").status_code == 403, "Spielerin darf die Auswertung nicht lesen")
check(B.get("/api/nutzung").status_code == 403, "Auch Bea nicht")
a = T.get("/api/nutzung")
check(a.status_code == 200, "Trainer liest die Auswertung")
d = a.json()
namen = [k["name"] for k in d["konten"]]
check(namen == ["Anna", "Bea"], "Nur Spielerinnen-Konten, ohne Trainer")
anna_k = next(k for k in d["konten"] if k["name"] == "Anna")
bea_k = next(k for k in d["konten"] if k["name"] == "Bea")
check(anna_k["besuche"] == 1, "Anna: 1 Besuch")
check(anna_k["tage"] == 1, "Anna: 1 aktiver Tag")
check(anna_k["videos_gesehen"] == 2, "Anna: 2 Videos gesehen")
check(anna_k["bereiche"][0] == {"ziel": "ich/videos", "anzahl": 2}, "Haeufigster Bereich zuerst")
check(anna_k["videos"] == [{"ziel": "clip:5", "titel": "Kreisanspiel 1", "anzahl": 2,
                            "zuletzt": anna_k["videos"][0]["zuletzt"]}], "Videos zusammengefasst")
check(anna_k["zuletzt"].endswith("Z"), "Zeitpunkt als UTC mit Z")
check(bea_k["zuletzt"] is None and bea_k["besuche"] == 0, "Bea: noch nie aktiv")
check(d["seit"] is not None, "Erfassung seit gesetzt")

# "Ansehen als": Trainer sieht die App als Anna -> darf nichts schreiben
check(T.post(f"/api/ansicht/{anna_k['benutzer_id']}").status_code == 200, "Ansicht als Anna")
check(T.post("/api/nutzung", json={"ereignisse": [{"typ": "besuch"}]}).status_code == 403,
      "Im Ansicht-Modus zaehlt nichts mit")

# Aeltere Ereignisse (> 30 Tage) fallen aus den Zaehlern, bleiben aber gespeichert
c = db.verbinde()
c.execute("INSERT INTO nutzung (benutzer_id, zeit, typ) VALUES (?, datetime('now','-40 days'), 'besuch')",
          (bea_k["benutzer_id"],))
c.commit()
c.close()
bea_k = next(k for k in client("Trainer", "1111").get("/api/nutzung").json()["konten"]
             if k["name"] == "Bea")
check(bea_k["besuche"] == 0 and bea_k["zuletzt"] is not None, "Alter Besuch: nicht in 30 Tagen, aber 'zuletzt' bleibt")

# ----------------------------------------------------------------- Geraete ----
G1 = {"os": "Android 13", "browser": "Chrome 126", "modus": "installiert",
      "bildschirm": "412x915", "modell": "SM-S911B", "app_version": "v0.52.0", "sw": True}
check(A.post("/api/geraet", json=G1).status_code == 200, "Geraet melden")
check(A.post("/api/geraet", json={**G1, "app_version": "v0.52.1"}).status_code == 200,
      "Gleiches Geraet nochmal: aktualisiert statt doppelt")
check(A.post("/api/geraet", json={**G1, "os": "iOS 17", "browser": "Safari 17", "modell": ""}).status_code == 200,
      "Zweites Geraet derselben Spielerin")
check(TestClient(balu.app).post("/api/geraet", json=G1).status_code == 401, "Geraet ohne Login: 401")
c = db.verbinde()
check(c.execute("SELECT COUNT(*) FROM geraet").fetchone()[0] == 2, "2 Geraete gespeichert, nicht 3")
c.close()
d = client("Trainer", "1111").get("/api/nutzung").json()
anna_k = next(k for k in d["konten"] if k["name"] == "Anna")
check(len(anna_k["geraete"]) == 2, "Auswertung: 2 Geraete bei Anna")
android = next(g for g in anna_k["geraete"] if g["os"] == "Android 13")
check(android["app_version"] == "v0.52.1" and android["sw"] is True and android["modell"] == "SM-S911B",
      "Geraet: neueste App-Version, Modell, Service Worker")
check(next(k for k in d["konten"] if k["name"] == "Bea")["geraete"] == [], "Bea: keine Geraete")

# ----------------------------------------------------------------- Fehler -----
F = {"quelle": "video", "meldung": "Video Code 4: nicht abspielbar", "ort": "ich/videos",
     "app_version": "v0.52.1", "geraet": "Android 13 · Chrome 126 · installiert"}
check(A.post("/api/fehler", json=F).json()["ok"] is True, "Fehler melden")
check(B.post("/api/fehler", json={**F, "geraet": "iOS 17 · Safari 17"}).json()["ok"] is True, "Gleicher Fehler bei Bea")
check(A.post("/api/fehler", json={"meldung": "   "}).json()["ok"] is False, "Leere Meldung wird verworfen")
check(TestClient(balu.app).post("/api/fehler", json=F).status_code == 401, "Fehler ohne Login: 401")
check(A.post("/api/fehler", json={"meldung": "x" * 900}).json()["ok"] is True, "Lange Meldung wird akzeptiert")
c = db.verbinde()
check(max(len(r[0]) for r in c.execute("SELECT meldung FROM fehler")) == 300, "Meldung auf 300 Zeichen gekuerzt")
c.close()
d = client("Trainer", "1111").get("/api/nutzung").json()
video = next(f for f in d["fehler"] if f["meldung"].startswith("Video Code 4"))
check(video["anzahl"] == 2 and sorted(video["namen"]) == ["Anna", "Bea"], "Fehler gruppiert: 2x, Anna + Bea")
check(len(video["geraete"]) == 2 and video["versionen"] == ["v0.52.1"], "Fehler: Geraete + Versionen")
check(A.get("/api/nutzung").status_code == 403, "Spielerin sieht keine Fehlerliste")

# Stundenlimit
ok = [A.post("/api/fehler", json={"meldung": f"Schleife {i}"}).json()["ok"] for i in range(30)]
check(ok.count(True) < 30 and ok[-1] is False, "Stundenlimit bremst eine Fehlerschleife")

print("\nAlle Tests gruen.")
