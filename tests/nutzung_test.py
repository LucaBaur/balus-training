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
check(anna_k["bereiche"][0] == {"ziel": "ich/videos", "anzahl": 2, "sekunden": 0}, "Haeufigster Bereich zuerst")
check(anna_k["videos"] == [{"ziel": "clip:5", "titel": "Kreisanspiel 1", "anzahl": 2, "gespielt": 0,
                            "sekunden": 0, "label": "Kreisanspiel 1", "spiel": None, "ampel": None,
                            "zeit": None, "t": None, "zuletzt": anna_k["videos"][0]["zuletzt"]}],
      "Videos zusammengefasst (ohne Dauer: 0 Sekunden)")
check(anna_k["zuletzt"].endswith("Z"), "Zeitpunkt als UTC mit Z")
check(bea_k["zuletzt"] is None and bea_k["besuche"] == 0, "Bea: noch nie aktiv")
check(d["seit"] is not None, "Erfassung seit gesetzt")

# Videozentrierte Sicht: ein echter Clip fuer Anna UND Bea, nur Anna schaut ihn
c = db.verbinde()
clip = db.clip_anlegen(c, "Kreisanspiel 2", None, "x.mp4", None, 10.0, None, [anna, bea])
unbeachtet = db.clip_anlegen(c, "Gegenstoss", None, "y.mp4", None, 8.0, None, [anna])
c.close()
check(A.post("/api/nutzung", json={"ereignisse": [
    {"typ": "video", "ziel": f"clip:{clip}", "info": "Kreisanspiel 2"},
    {"typ": "gespielt", "ziel": f"clip:{clip}", "info": "Kreisanspiel 2"}]}).json()["gespeichert"] == 2,
    "Ereignis 'gespielt' wird gespeichert")
va = {v["ziel"]: v for v in T.get("/api/nutzung").json()["video_ansicht"]}
v = va[f"clip:{clip}"]
check([g["name"] for g in v["gesehen"]] == ["Anna"] and v["gesehen"][0]["gespielt"] == 1
      and v["gesehen"][0]["anzahl"] == 1, "Clip: Anna hat ihn geoeffnet und komplett angeschaut")
check(v["fehlt"] == ["Bea"], "Clip: Bea ist zugeordnet, hat ihn aber nicht gesehen")
check(va[f"clip:{unbeachtet}"]["gesehen"] == [] and va[f"clip:{unbeachtet}"]["fehlt"] == ["Anna"],
      "Clip, den noch niemand geoeffnet hat, erscheint trotzdem")
check(va["clip:5"]["fehlt"] == [] and va["clip:5"]["gesehen"][0]["anzahl"] == 2,
      "Geloeschter/unbekannter Clip: niemand 'fehlt', Ansichten bleiben sichtbar")
check(not any(z.startswith("analyse:") for z in va), "Analyse-Detailseite ist kein eigenes Video")
check(next(iter(T.get("/api/nutzung").json()["video_ansicht"]))["fehlt"], "Videos mit Offenem stehen oben")

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

# ------------------------------------------- Spielzuege unterscheidbar (v0.57) ----
#  Frueher hiess jede Szene eines Spiels "TVG - Gegner". Jetzt loest der Server
#  Spiel, Name, Ampel und Zeit im Spiel ueber die Szene-Kennung auf.
TT = client("Trainer", "1111")
c = db.verbinde()
aid = db.analyse_speichern(
    c, "ext-hsv", "HSV", "2026-09-14", "Liga",
    [{"typ": "tor", "t": 300.0, "spieler_id": anna, "detail": "Rueckraum", "key": "e1"}],
    [{"name": "Kreuz", "t_start": 723.0, "t_ende": 740.0, "ampel": "gruen", "key": "z1",
      "spieler_ids": [anna]},
     {"name": "Doppelpass", "t_start": 800.0, "t_ende": 815.0, "ampel": "rot", "key": "z2",
      "spieler_ids": [anna]}],
    None)
db.szene_clip_speichern(c, aid, "z1", "z1.mp4", 720.0, 745.0)
db.szene_clip_speichern(c, aid, "z2", "z2.mp4", 797.0, 820.0)
db.szene_clip_speichern(c, aid, "e1", "e1.mp4", 297.0, 305.0)
db.analyse_datei_setzen(c, aid, "hsv.mp4")
cid = {r["szene_key"]: r["id"] for r in c.execute("SELECT id, szene_key FROM spiel_szene_clip")}
c.close()

# Anna meldet im ALTEN Format: Titel ist fuer alle Szenen gleich
alt_titel = "TVG – HSV"
A.post("/api/nutzung", json={"ereignisse": [
    {"typ": "video", "ziel": f"szene:{cid['z1']}", "info": alt_titel},
    {"typ": "video", "ziel": f"szene:{cid['z1']}", "info": alt_titel},
    {"typ": "video", "ziel": f"szene:{cid['e1']}", "info": alt_titel},
    {"typ": "video", "ziel": "szene:9999", "info": "TVG – Weg"}]})
d = TT.get("/api/nutzung").json()
va = {v["ziel"]: v for v in d["video_ansicht"]}
z1, z2, e1 = (va[f"szene:{cid[k]}"] for k in ("z1", "z2", "e1"))
check(z1["label"] == "Spielzug Kreuz" and z2["label"] == "Spielzug Doppelpass",
      "Zwei Spielzuege desselben Spiels haben verschiedene Namen")
check(e1["label"] == "Tor · Rueckraum", "Ereignis-Szene: Art + Detail statt Spielname")
check(z1["spiel"] == z2["spiel"] == e1["spiel"] == "TVG – HSV · 14.09.", "Alle Szenen tragen ihr Spiel mit Datum")
check((z1["ampel"], z2["ampel"], e1["ampel"]) == ("gruen", "rot", None), "Ampel: Spielzug gruen/rot, Ereignis keine")
check((z1["zeit"], z2["zeit"], e1["zeit"]) == ("12:03–12:20", "13:20–13:35", "5:00"),
      "Zeit im Spiel: Spanne beim Spielzug, Zeitpunkt beim Ereignis")
check((z1["t"], z2["t"], e1["t"]) == (723.0, 800.0, 300.0),
      "Startzeit als Zahl (t) fuer die Sortierung im Spiel")
check(va[f"spiel:{aid}"]["t"] is None and va["szene:9999"]["t"] is None, "Ohne Szene keine Startzeit")
check(z1["gesehen"][0]["anzahl"] == 2 and z1["fehlt"] == [],"Spielzug 1: von Anna 2x geoeffnet, niemand fehlt")
check(z2["gesehen"] == [] and z2["fehlt"] == ["Anna"], "Ungeoeffneter Spielzug erscheint, Anna fehlt")
weg = va["szene:9999"]
check(weg["label"] == "TVG – Weg" and weg["spiel"] is None,
      "Geloeschte Szene: Fallback auf gespeicherten Titel, kein Fehler")
check(va[f"spiel:{aid}"]["spiel"] == "TVG – HSV · 14.09." and va[f"spiel:{aid}"]["label"] == "Ganzes Spiel",
      "Ganzes Spiel haengt in seiner Spielgruppe")
anna_k = next(k for k in d["konten"] if k["name"] == "Anna")
av = {v["ziel"]: v for v in anna_k["videos"]}
check(av[f"szene:{cid['z1']}"]["label"] == "Spielzug Kreuz" and av[f"szene:{cid['e1']}"]["label"] == "Tor · Rueckraum",
      "Auch in Annas Kartenliste sind die Szenen unterscheidbar")

# ------------------------------------------------------------ Verweildauer ----
ev = [{"typ": "verweil", "ziel": "ich/videos", "dauer_s": 120},
      {"typ": "verweil", "ziel": "ich/videos", "dauer_s": 60},
      {"typ": "verweil", "ziel": f"szene:{cid['z1']}", "dauer_s": 45},
      {"typ": "verweil", "ziel": "home/home", "dauer_s": 1800},        # Obergrenze gilt noch
      {"typ": "verweil", "ziel": "ich/videos", "dauer_s": 0},          # zu kurz
      {"typ": "verweil", "ziel": "ich/videos", "dauer_s": 1801},       # Tab ueber Nacht offen
      {"typ": "verweil", "ziel": "ich/videos", "dauer_s": -5},
      {"typ": "verweil", "ziel": "ich/videos"},                        # ohne Dauer
      {"typ": "verweil", "dauer_s": 30}]                               # ohne Ziel
r = A.post("/api/nutzung", json={"ereignisse": ev})
check(r.json()["gespeichert"] == 4, "Verweildauer: nur 1..1800 Sekunden mit Ziel werden gespeichert")
c = db.verbinde()
check(c.execute("SELECT COUNT(*) FROM nutzung WHERE typ = 'verweil' AND benutzer_id = "
                "(SELECT id FROM benutzer WHERE name = 'Anna')").fetchone()[0] == 4, "4 Verweil-Zeilen in der DB")
c.close()
d = TT.get("/api/nutzung").json()
anna_k = next(k for k in d["konten"] if k["name"] == "Anna")
bereich = {b["ziel"]: b for b in anna_k["bereiche"]}
check(bereich["ich/videos"]["sekunden"] == 180 and bereich["ich/videos"]["anzahl"] == 2,
      "Bereich: 120 + 60 Sekunden summiert, Anzahl der Besuche unveraendert")
check(bereich["home/home"]["sekunden"] == 1800, "Bereich: Obergrenze 1800 Sekunden wird akzeptiert")
av = {v["ziel"]: v for v in anna_k["videos"]}
check(av[f"szene:{cid['z1']}"]["sekunden"] == 45, "Video/Spielzug: Dauer je Ziel")
check(anna_k["sekunden_gesamt"] == 120 + 60 + 45 + 1800, "Gesamtdauer je Spielerin")
check(anna_k["besuche"] == 1 and anna_k["videos_gesehen"] == 7,
      "Verweil-Ereignisse veraendern Besuche und Video-Zaehler nicht")
bea_k = next(k for k in d["konten"] if k["name"] == "Bea")
check(bea_k["sekunden_gesamt"] == 0, "Ohne Messung: 0 Sekunden")
check(A.get("/api/nutzung").status_code == 403, "Dauer sieht nur die Trainerin")

# -------------------------------------------------------------- Migration ----
import sqlite3  # noqa: E402
alt = tmp / "alt.db"
c0 = sqlite3.connect(alt)
c0.execute("CREATE TABLE nutzung (id INTEGER PRIMARY KEY AUTOINCREMENT, benutzer_id INTEGER NOT NULL, "
           "zeit TEXT NOT NULL DEFAULT (datetime('now')), typ TEXT NOT NULL, ziel TEXT, info TEXT)")
c0.execute("INSERT INTO nutzung (benutzer_id, typ, ziel) VALUES (1, 'besuch', NULL)")
c0.commit()
c0.close()
for durchgang in (1, 2):                      # zweiter Start darf nichts kaputt machen
    cm = _verbinde(alt)
    db.init_db(cm)
    spalten = {r["name"] for r in cm.execute("PRAGMA table_info(nutzung)")}
    check("dauer_s" in spalten, f"Alte DB, Start {durchgang}: Spalte dauer_s vorhanden")
    check(cm.execute("SELECT COUNT(*) FROM nutzung").fetchone()[0] == 1, f"Alte Daten bleiben erhalten (Start {durchgang})")
    cm.close()

print("\nAlle Tests gruen.")
