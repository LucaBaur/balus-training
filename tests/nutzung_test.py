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
check("videos" not in anna_k and "video_ansicht" not in d,
      "Nutzung zeigt nur noch Spielerinnen: keine Videoliste mehr (die steht unter Team -> Videos)")
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

# ------------------------------- Spielzug-Uebersicht und schlanke Nutzung (v0.60) ----
#  Team -> Videos zeigt alle Spielzuege nach Spiel mit ID ("S1-z3") und wer sie KOMPLETT
#  gesehen hat; Team -> Nutzung nennt je Spielerin die Spielzuege, die ihr noch fehlen.
TT = client("Trainer", "1111")
c = db.verbinde()
aid = db.analyse_speichern(
    c, "ext-hsv", "HSV", "2026-09-14", "Liga",
    [{"typ": "tor", "t": 300.0, "spieler_id": anna, "detail": "Rueckraum", "key": "e1"},
     {"typ": "fehlwurf", "t": 724.0, "spieler_id": bea, "key": "z1"}],     # teilt die Kennung mit Spielzug z1
    [{"name": "Kreuz", "t_start": 723.0, "t_ende": 740.0, "ampel": "gruen", "key": "z1", "spieler_ids": [anna]},
     {"name": "Doppelpass", "t_start": 800.0, "t_ende": 815.0, "ampel": "rot", "key": "z2",
      "spieler_ids": [anna, bea]},
     {"name": "Kreuz", "t_start": 1200.0, "t_ende": 1212.0, "ampel": "orange", "key": "z3",
      "spieler_ids": [bea]},                                                 # gleicher Name, aber ohne Clip
     {"name": "Auftakt", "t_start": 50.0, "t_ende": 60.0, "ampel": "gruen", "spieler_ids": [anna]}],  # ohne Kennung
    None)
aid2 = db.analyse_speichern(
    c, "ext-kiel", "Kiel", "2026-09-21", "Liga", [],
    [{"name": "Kreuz", "t_start": 100.0, "t_ende": 112.0, "ampel": "gruen", "key": "z1",
      "spieler_ids": [anna]}], None)
for a_id, key in ((aid, "z1"), (aid, "z2"), (aid, "e1"), (aid2, "z1")):     # z3 und Auftakt: kein Clip
    db.szene_clip_speichern(c, a_id, key, f"{a_id}-{key}.mp4", 0.0, 10.0)
db.analyse_datei_setzen(c, aid, "hsv.mp4")
cid = {r["szene_key"]: r["id"] for r in c.execute("SELECT id, szene_key FROM spiel_szene_clip WHERE analyse_id = ?", (aid,))}
cid2 = c.execute("SELECT id FROM spiel_szene_clip WHERE analyse_id = ?", (aid2,)).fetchone()["id"]
c.close()
SP1, SP2 = "TVG – HSV · 14.09.", "TVG – Kiel · 21.09."

# Anna meldet im ALTEN Format (Titel fuer alle Szenen gleich); "gespielt" = komplett angeschaut
alt_titel = "TVG – HSV"
A.post("/api/nutzung", json={"ereignisse": [
    {"typ": "video", "ziel": f"szene:{cid['z1']}", "info": alt_titel},
    {"typ": "video", "ziel": f"szene:{cid['z1']}", "info": alt_titel},
    {"typ": "gespielt", "ziel": f"szene:{cid['z1']}", "info": alt_titel},
    {"typ": "video", "ziel": f"szene:{cid['z2']}", "info": alt_titel},        # nur angetippt
    {"typ": "video", "ziel": f"szene:{cid['e1']}", "info": alt_titel},
    {"typ": "video", "ziel": "szene:9999", "info": "TVG – Weg"}]})            # geloeschte Szene
B.post("/api/nutzung", json={"ereignisse": [
    {"typ": "video", "ziel": f"szene:{cid['z2']}", "info": alt_titel},
    {"typ": "gespielt", "ziel": f"szene:{cid['z2']}", "info": alt_titel}]})
c = db.verbinde()                                                              # Kiel: komplett, aber vor 40 Tagen
c.execute("INSERT INTO nutzung (benutzer_id, zeit, typ, ziel) VALUES (?, datetime('now','-40 days'), 'gespielt', ?)",
          (anna_k["benutzer_id"], f"szene:{cid2}"))
c.commit()
c.close()

# Fragen am Spielzug: gezaehlt werden Hauptkommentare (Antworten nicht)
c = db.verbinde()
frage = db.kommentar_anlegen(c, f"szene:{cid['z1']}", {"id": anna_k["benutzer_id"], "rolle": "spieler"},
                             "Wann kommt der Kreis?", False, None)
db.kommentar_anlegen(c, f"szene:{cid['z1']}", {"id": bea_k["benutzer_id"], "rolle": "spieler"},
                     "Auf drei.", False, frage["id"])
c.close()

# --- Rechte
check(A.get("/api/szenen-uebersicht").status_code == 403, "Spielzug-Uebersicht: Spielerin bekommt 403")
check(TestClient(balu.app).get("/api/szenen-uebersicht").status_code == 401, "Spielzug-Uebersicht: ohne Login 401")
r = TT.get("/api/szenen-uebersicht")
check(r.status_code == 200, "Spielzug-Uebersicht: Trainer liest sie")
spiele = r.json()["spiele"]
check([s["analyse_id"] for s in spiele] == [aid2, aid] and spiele[0]["spiel"] == SP2 and spiele[1]["spiel"] == SP1,
      "Spiele: neuestes zuerst, mit Gegner und Datum")

# --- IDs und Reihenfolge
sz = {s["id"]: s for s in spiele[1]["szenen"]}
check([s["id"] for s in spiele[1]["szenen"]] ==
      [f"S{aid}-t50", f"S{aid}-e1", f"S{aid}-z1", f"S{aid}-z2", f"S{aid}-z3"],
      "IDs 'S<Spiel>-<Kennung>', im Spiel nach Spielzeit sortiert; ohne Kennung Ersatz-ID aus der Startsekunde")
check(spiele[0]["szenen"][0]["id"] == f"S{aid2}-z1", "Gleiche Kennung in einem anderen Spiel ergibt eine andere ID")
z1, z2, z3, e1, ohne = (sz[f"S{aid}-{k}"] for k in ("z1", "z2", "z3", "e1", "t50"))
check(z1["name"] == "Kreuz" and z3["name"] == "Kreuz" and z1["id"] != z3["id"],
      "Zwei Spielzuege 'Kreuz' sind per ID unterscheidbar")
check((z1["kommentare"], z2["kommentare"]) == (1, 0), "Kommentarzahl am Spielzug: nur Hauptkommentare")
check(z1["spiel"] == SP1 and spiele[0]["szenen"][0]["spiel"] == SP2,
      "Jede Szene traegt ihr Spiel (fuer die Ansicht 'Nach Name' ueber mehrere Spiele)")
check((z1["art"], z1["label"], z1["ampel"], z1["zeit"], z1["t"]) ==
      ("zug", "Spielzug Kreuz", "gruen", "12:03–12:20", 723.0),
      "Spielzug hat bei gemeinsamer Kennung Vorrang vor dem Ereignis (Name, Ampel, Zeit)")
check((e1["art"], e1["name"], e1["label"], e1["zeit"]) == ("ereignis", "Tor", "Tor · Rueckraum", "5:00"),
      "Ereignis: Art als Name, Detail im Label")

# --- Wer hat gesehen (nur komplett zaehlt), wer soll sehen (nur Beteiligte)
check(z1["beteiligt"] == ["Anna", "Bea"], "Beteiligte: Spielzug und Ereignis derselben Kennung zusammen")
check([(g["name"], g["anzahl"], g["gespielt"]) for g in z1["gesehen"]] == [("Anna", 2, 1)]
      and z1["fehlt"] == ["Bea"], "z1: Anna komplett, Bea (nie geoeffnet) fehlt")
check(sorted((g["name"], g["gespielt"]) for g in z2["gesehen"]) == [("Anna", 0), ("Bea", 1)]
      and z2["fehlt"] == ["Anna"], "z2: nur angetippt zaehlt nicht - Anna fehlt, Bea hat komplett gesehen")
check(e1["fehlt"] == ["Anna"], "Ereignis nur angetippt: fehlt")
check(z3["kein_video"] and z3["clip_id"] is None and z3["fehlt"] is None and z3["gesehen"] == [],
      "Zug ohne Clip: 'kein Video', nichts ueber gesehen/fehlt behauptet")
check(ohne["kein_video"] and ohne["key"] is None, "Zug ohne Kennung hat keinen Clip")
kiel = spiele[0]["szenen"][0]
check(kiel["beteiligt"] == ["Anna"] and kiel["fehlt"] == [] and kiel["gesehen"][0]["gespielt"] == 1,
      "'Gesehen' gilt fuer immer: komplett angeschaut vor 40 Tagen zaehlt noch; Bea gehoert nicht dazu")
check(f"szene:9999" not in str(spiele), "Geloeschte Szene (Waise in der Nutzung) taucht nicht auf")

# --- Daten-Upload aendert die IDs nicht (spiel_zug.id wird neu vergeben, die Kennung bleibt)
ids_vorher = [s["id"] for s in spiele[1]["szenen"]]
c = db.verbinde()
db.analyse_speichern(
    c, "ext-hsv", "HSV", "2026-09-14", "Liga",
    [{"typ": "tor", "t": 300.0, "spieler_id": anna, "detail": "Rueckraum", "key": "e1"},
     {"typ": "fehlwurf", "t": 724.0, "spieler_id": bea, "key": "z1"}],
    [{"name": "Kreuz", "t_start": 723.0, "t_ende": 740.0, "ampel": "gruen", "key": "z1", "spieler_ids": [anna]},
     {"name": "Doppelpass", "t_start": 800.0, "t_ende": 815.0, "ampel": "rot", "key": "z2", "spieler_ids": [anna, bea]},
     {"name": "Kreuz", "t_start": 1200.0, "t_ende": 1212.0, "ampel": "orange", "key": "z3", "spieler_ids": [bea]},
     {"name": "Auftakt", "t_start": 50.0, "t_ende": 60.0, "ampel": "gruen", "spieler_ids": [anna]}], None)
c.close()
check([s["id"] for s in TT.get("/api/szenen-uebersicht").json()["spiele"][1]["szenen"]] == ids_vorher,
      "Erneuter Daten-Upload der Analyse: alle IDs bleiben gleich")

# --- Nutzung: je Spielerin die Spielzuege, die noch fehlen (nur Spielzuege, nur mit Clip)
d = TT.get("/api/nutzung").json()
anna_k = next(k for k in d["konten"] if k["name"] == "Anna")
bea_k = next(k for k in d["konten"] if k["name"] == "Bea")
check([n["id"] for n in anna_k["nicht_gesehen"]] == [f"S{aid}-z2"] and anna_k["offen"] == 1,
      "Anna: nur z2 fehlt (z1 und Kiel komplett; Tor und Spielzug ohne Clip zaehlen nicht)")
n = anna_k["nicht_gesehen"][0]
check((n["spiel"], n["label"], n["zeit"], n["ampel"], n["geoeffnet"]) ==
      (SP1, "Spielzug Doppelpass", "13:20–13:35", "rot", True),
      "Eintrag mit Spiel, Name, Zeit, Ampel; 'geoeffnet' kennzeichnet nur Angetipptes")
check([n["id"] for n in bea_k["nicht_gesehen"]] == [f"S{aid}-z1"] and not bea_k["nicht_gesehen"][0]["geoeffnet"]
      and bea_k["offen"] == 1, "Bea: z1 fehlt (nie geoeffnet); z2 hat sie komplett gesehen")
check(all(k["offen"] == len(k["nicht_gesehen"]) for k in d["konten"]), "'offen' entspricht der Listenlaenge")

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
check(anna_k["sekunden_gesamt"] == 120 + 60 + 45 + 1800, "Gesamtdauer je Spielerin")
check(anna_k["besuche"] == 1 and anna_k["videos_gesehen"] == 8,
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
