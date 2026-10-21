"""Tests fuer die Spielanalyse-Endpunkte (Upload, Rechte, Idempotenz, Streaming).

Laeuft gegen eine temporaere Datenbank und ein temporaeres Medien-Verzeichnis -
die echte elo.db und media/ bleiben unberuehrt.
Start:  py tests/analyse_test.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="analyse_test_"))
DB = tmp / "test.db"
balu.MEDIA_SPIELE = tmp / "spiele"
balu.MEDIA_SPIELE.mkdir()
balu.MEDIA_SZENEN = tmp / "szenen"
balu.MEDIA_SZENEN.mkdir()
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
bea = db.spieler_anlegen(conn, "Bea")
cleo = db.spieler_anlegen(conn, "Cleo")
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)
db.benutzer_anlegen(conn, "Cleo", "spieler", auth.hash_pin("3333"), cleo)
db.benutzer_anlegen(conn, "Bea", "spieler", auth.hash_pin("4444"), bea)
conn.close()


def client(name, pin):
    c = TestClient(balu.app)
    r = c.post("/api/login", json={"name": name, "pin": pin})
    assert r.status_code == 200, r.text
    return c


T, A, C = client("Trainer", "1111"), client("Anna", "2222"), client("Cleo", "3333")

DATEN = {
    "extern_id": "20261018-test", "gegner": "HSG Test", "datum": "2026-10-18", "art": "Liga",
    "events": [
        {"typ": "tor", "t": 100.5, "spieler_id": anna, "assist_id": bea, "key": "z1"},   # Tor teilt den Clip des Spielzugs
        {"typ": "fehlwurf", "t": 200, "spieler_id": bea, "detail": "gehalten", "key": "e2"},
        {"typ": "tor", "t": 300, "spieler_id": bea, "key": "e3"},
    ],
    "zuege": [
        {"name": "Jugo", "t_start": 95, "t_ende": 101, "ampel": "gruen", "spieler_ids": [anna, bea, 9999], "key": "z1"},
        {"name": "Kreisel", "t_start": 190, "t_ende": 201, "ampel": "rot",
         "kommentar": "Fehlpass am Kreis", "spieler_ids": [bea], "key": "z3"},
    ],
}


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


# Rechte beim Hochladen
check(A.post("/api/analysen", json=DATEN).status_code == 403, "Spielerin darf keine Analyse hochladen")
check(client("Trainer", "1111").post("/api/analysen", json={**DATEN, "extern_id": "../x"}).status_code == 400,
      "ungueltige extern_id abgelehnt")
check(T.post("/api/analysen", json={**DATEN, "zuege": [{**DATEN["zuege"][0], "ampel": "blau"}]}).status_code == 400,
      "ungueltige Ampel abgelehnt")

# Daten hochladen, zweimal -> keine Duplikate
r = T.post("/api/analysen", json=DATEN)
check(r.status_code == 200 and r.json()["events"] == 3, "Daten hochgeladen")
aid = r.json()["id"]
r2 = T.post("/api/analysen", json=DATEN)
check(r2.json()["id"] == aid, "erneuter Upload ersetzt statt zu verdoppeln")
check(len(T.get("/api/analysen").json()) == 1, "genau eine Analyse in der Liste")
inh = T.get(f"/api/analysen/{aid}").json()
check(len(inh["events"]) == 3 and len(inh["zuege"]) == 2, "Trainer sieht alles")
check(any(z["kommentar"] == "Fehlpass am Kreis" for z in inh["zuege"]), "Trainer sieht Kommentare")
check(all(9999 not in z["spieler_ids"] for z in inh["zuege"]), "unbekannte Spielerin-ID verworfen")

# Video-Streaming
check(T.get(f"/api/analysen/{aid}/video").status_code == 404, "ohne Video: 404")
video = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 4000        # ~1 MB
r = T.put(f"/api/analysen/{aid}/video", content=iter([video[:300000], video[300000:]]))
check(r.status_code == 200 and r.json()["bytes"] == len(video), "Video gestreamt hochgeladen")
check(A.put(f"/api/analysen/{aid}/video", content=b"x").status_code == 403, "Spielerin darf kein Video hochladen")
check(T.put(f"/api/analysen/{aid}/video", content=b"").status_code == 400, "leeres Video abgelehnt")
check(len(list(balu.MEDIA_SPIELE.glob("*.part"))) == 0, "keine .part-Reste")
check(len(list(balu.MEDIA_SPIELE.glob("*.mp4"))) == 1, "genau eine Videodatei (leerer Upload ersetzt nichts)")
g = T.get(f"/api/analysen/{aid}/video", headers={"Range": "bytes=10-19"})
check(g.status_code == 206 and g.content == video[10:20], "Range-Abruf (Seek) funktioniert")
T.post("/api/analysen", json=DATEN)
check(T.get(f"/api/analysen/{aid}").json()["video_da"], "Daten-Update behaelt das Video")
T.put(f"/api/analysen/{aid}/video", content=video)
check(len(list(balu.MEDIA_SPIELE.glob("*.mp4"))) == 1, "neues Video ersetzt das alte Datei")

# ---- Szenen-Clips ----------------------------------------------------------------
clip = b"\x00\x00\x00\x18ftypmp42" + bytes(range(256)) * 40                      # ~10 KB
check(T.get(f"/api/analysen/{aid}/clips").json() == [], "noch keine Clips")
check(A.get(f"/api/analysen/{aid}/clips").status_code == 403, "Spielerin darf die Clip-Liste nicht abrufen")
check(A.put(f"/api/analysen/{aid}/clips/z1?von=92&bis=104", content=clip).status_code == 403, "Spielerin darf keinen Clip hochladen")
check(T.put(f"/api/analysen/{aid}/clips/../x?von=1&bis=2", content=clip).status_code in (404, 400, 405), "Pfadtrick bei der Kennung abgelehnt")
check(T.put(f"/api/analysen/{aid}/clips/z%201?von=92&bis=104", content=clip).status_code == 400, "Kennung mit Leerzeichen abgelehnt")
check(T.put(f"/api/analysen/{aid}/clips/z1?von=104&bis=92", content=clip).status_code == 400, "Ausschnitt mit bis < von abgelehnt")
check(T.put(f"/api/analysen/{aid}/clips/z1?von=92&bis=104", content=b"").status_code == 400, "leerer Clip abgelehnt")
check(T.put(f"/api/analysen/999/clips/z1?von=92&bis=104", content=clip).status_code == 404, "Clip zu unbekannter Analyse: 404")
check(len(list(balu.MEDIA_SZENEN.glob("*"))) == 0, "abgelehnte Uploads hinterlassen nichts")
r = T.put(f"/api/analysen/{aid}/clips/z1?von=92&bis=104", content=iter([clip[:4000], clip[4000:]]))
check(r.status_code == 200 and r.json()["bytes"] == len(clip), "Clip z1 gestreamt hochgeladen")
T.put(f"/api/analysen/{aid}/clips/z3?von=187&bis=204", content=clip)
T.put(f"/api/analysen/{aid}/clips/e2?von=194&bis=204", content=clip)
l = {x["key"]: x for x in T.get(f"/api/analysen/{aid}/clips").json()}
check(set(l) == {"z1", "z3", "e2"} and l["z1"]["von"] == 92 and l["z1"]["bis"] == 104, "Clip-Liste nennt Kennung und Ausschnitt")
T.put(f"/api/analysen/{aid}/clips/z1?von=91&bis=105", content=clip + b"x")
check(len(list(balu.MEDIA_SZENEN.glob("*.mp4"))) == 3, "erneuter Upload ersetzt den Clip (weiter 3 Dateien)")
check({x["key"]: x for x in T.get(f"/api/analysen/{aid}/clips").json()}["z1"]["von"] == 91, "ersetzter Clip hat den neuen Ausschnitt")
inh = T.get(f"/api/analysen/{aid}").json()
cid_z1 = [z["clip_id"] for z in inh["zuege"] if z["name"] == "Jugo"][0]
check(cid_z1 is not None and [e["clip_id"] for e in inh["events"] if e["t"] == 100.5] == [cid_z1], "Tor und Spielzug teilen sich denselben Clip")
check([e["clip_id"] for e in inh["events"] if e["t"] == 300] == [None], "Szene ohne Clip hat clip_id null")
cid_z3 = [z["clip_id"] for z in inh["zuege"] if z["name"] == "Kreisel"][0]
g = T.get(f"/api/szenen/{cid_z1}/video", headers={"Range": "bytes=10-19"})
check(g.status_code == 206 and g.content == (clip + b"x")[10:20], "Trainer: Clip mit Range-Abruf")
check(A.get(f"/api/szenen/{cid_z1}/video").status_code == 200, "Anna (im Spielzug Jugo) sieht den Clip")
check(A.get(f"/api/szenen/{cid_z3}/video").status_code == 403, "Anna sieht den roten Kreisel-Clip nicht (nicht beteiligt)")
check(C.get(f"/api/szenen/{cid_z1}/video").status_code == 403, "Cleo (nirgends beteiligt) sieht keinen Clip")
check(T.get("/api/szenen/9999/video").status_code == 404, "unbekannter Clip: 404")
check(client("Bea", "4444").get(f"/api/szenen/{cid_z3}/video").status_code == 200, "Bea sieht ihren roten Spielzug-Clip")
# Spielerinnen-Sicht liefert die Clip-ID mit
ar = A.get(f"/api/spieler/{anna}/analyse").json()[0]
check(all(x["clip_id"] == cid_z1 for x in ar["events"] + ar["zuege"]), "Annas Szenen zeigen auf ihren Clip")

# Daten-Upload OHNE die Szene e2: ihr Clip wird samt Datei entfernt, die anderen bleiben
daten2 = {**DATEN, "events": [e for e in DATEN["events"] if e.get("key") != "e2"]}
r = T.post("/api/analysen", json=daten2)
check(r.json()["clips"] == 2, "Szene entfernt: ihr Clip verschwindet")
check(len(list(balu.MEDIA_SZENEN.glob("*.mp4"))) == 2, "Clip-Datei der entfernten Szene ist von der Platte gelöscht")
check(sorted(x["key"] for x in T.get(f"/api/analysen/{aid}/clips").json()) == ["z1", "z3"], "Clips der übrigen Szenen bleiben")
T.post("/api/analysen", json=DATEN)                                               # Daten-Upload ersetzt Zeilen, Clips bleiben
check(sorted(x["key"] for x in T.get(f"/api/analysen/{aid}/clips").json()) == ["z1", "z3"], "Daten-Upload lässt Clips unberührt")
check(T.get(f"/api/szenen/{cid_z1}/video").status_code == 200, "Clip-ID bleibt nach Daten-Upload gültig")

# Spielerin Anna: nur eigene Szenen
r = A.get(f"/api/spieler/{anna}/analyse").json()
check(len(r) == 1 and r[0]["stats"]["tore"] == 1, "Anna: 1 Tor")
check(len(r[0]["events"]) == 1 and len(r[0]["zuege"]) == 1, "Anna sieht nur ihre Szenen")
r_bea = T.get(f"/api/spieler/{bea}/analyse").json()[0]
check(r_bea["stats"]["vorlagen"] == 1 and r_bea["stats"]["fehlwuerfe"] == 1 and r_bea["stats"]["rot"] == 1,
      "Bea: Vorlage, Fehlwurf, roter Spielzug")
r_bea_selbst = client("Trainer", "1111").get(f"/api/spieler/{bea}/analyse").json()[0]
check(any(z["kommentar"] for z in r_bea_selbst["zuege"]), "Trainer sieht Kommentar im Spielerprofil")
check(A.get(f"/api/spieler/{bea}/analyse").status_code == 403, "Anna sieht Beas Profil nicht")
# Kommentar der Trainerin: Bea (im roten Spielzug) sieht ihn, Anna (nicht beteiligt) sieht den Zug gar nicht
B = client("Bea", "4444")
bea_rot = [z for z in B.get(f"/api/spieler/{bea}/analyse").json()[0]["zuege"] if z["ampel"] == "rot"]
check(len(bea_rot) == 1 and bea_rot[0]["kommentar"] == "Fehlpass am Kreis", "Bea sieht den Kommentar zu ihrem roten Spielzug")
check(all(z["name"] != "Kreisel" for z in A.get(f"/api/analysen/{aid}").json()["zuege"]), "Anna sieht den fremden roten Spielzug samt Kommentar nicht")
check(any(z["kommentar"] == "Fehlpass am Kreis" for z in B.get(f"/api/analysen/{aid}").json()["zuege"]), "Detailabruf liefert Bea den Kommentar ebenfalls")
check(A.get(f"/api/analysen/{aid}/video").status_code == 200, "Anna darf das Video sehen (sie kommt vor)")

# Alle Spielerinnen sehen das Spiel in der Liste - mit Zaehlern, wie viele Szenen es fuer sie gibt
la = A.get("/api/analysen").json()
check(len(la) == 1 and la[0]["gegner"] == "HSG Test", "Anna: Spiel in der Liste")
check(la[0]["meine_events"] == 1 and la[0]["meine_zuege"] == 1, "Anna: Szenen-Zaehler (1 Ereignis, 1 Spielzug)")
lb = B.get("/api/analysen").json()
check(lb[0]["meine_events"] >= 1 and lb[0]["meine_zuege"] == 2, "Bea: eigene Zaehler")

# Cleo kommt nicht vor: sieht das Spiel trotzdem, aber ohne Szenen
lc = C.get("/api/analysen").json()
check(len(lc) == 1 and lc[0]["meine_events"] == 0 and lc[0]["meine_zuege"] == 0, "Cleo: Spiel in der Liste, 0 Szenen")
dc = C.get(f"/api/analysen/{aid}")
check(dc.status_code == 200 and dc.json()["events"] == [] and dc.json()["zuege"] == [], "Cleo: Detail ohne fremde Szenen")
check(dc.json()["stats"]["tore"] == 0 and dc.json()["video_da"] is True, "Cleo: Statistik 0, Spielvideo vorhanden")
check(C.get(f"/api/analysen/{aid}/video").status_code == 200, "Cleo darf das ganze Spielvideo sehen")
check(C.get(f"/api/spieler/{cleo}/analyse").json() == [], "Cleo: Profil-Statistik leer (nicht beteiligt)")
check(C.get(f"/api/spieler/{anna}/analyse").status_code == 403, "Cleo sieht Annas Profil nicht")
check(C.get(f"/api/szenen/{cid_z1}/video").status_code == 403, "Cleo: Szenen-Clips bleiben gesperrt")

# Konto OHNE Spielerprofil (spieler_id fehlt): darf nie "alles" sehen
c0 = db.verbinde()
db.benutzer_anlegen(c0, "Ohne", "spieler", auth.hash_pin("5555"), None)
c0.close()
O = client("Ohne", "5555")
check(O.get("/api/analysen").json() == [], "Konto ohne Profil: leere Liste")
check(O.get(f"/api/analysen/{aid}").status_code == 403, "Konto ohne Profil: Detail gesperrt (kein Trainerblick)")
check(O.get(f"/api/analysen/{aid}/video").status_code == 403, "Konto ohne Profil: Video gesperrt")

# Loeschen
check(A.post(f"/api/analysen/{aid}/loeschen").status_code == 403, "Spielerin darf nicht loeschen")
check(T.post(f"/api/analysen/{aid}/loeschen").status_code == 200, "Trainer loescht")
check(len(list(balu.MEDIA_SPIELE.glob("*.mp4"))) == 0, "Videodatei mit geloescht")
check(len(list(balu.MEDIA_SZENEN.glob("*"))) == 0, "Clip-Dateien mit geloescht")
check(T.get("/api/analysen").json() == [], "Liste leer")
c = db.verbinde()
check(c.execute("SELECT COUNT(*) FROM spiel_event").fetchone()[0] == 0
      and c.execute("SELECT COUNT(*) FROM spiel_zug_spieler").fetchone()[0] == 0, "Kaskade raeumt Ereignisse + Zuordnung")
c.close()
print("\nAlle Tests gruen.")
