"""Tests: Spielzug-Ansicht (Entscheidungsbaum mit Angriff, Abwehr und Videos je Loesung).

Ein Spielzug ist ein Baum: gemeinsame Schritte, dann eine Verzweigung "Was macht die Abwehr?"
mit je einer Loesung. An jeder Loesung kann ein Clip aus der Spielanalyse haengen.
Mandantenfaehig: alles hat eine team_id, fremde Teams sehen und aendern nichts.
Start:  py tests/spielzug_test.py
"""
import copy
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
from routen import pfade  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="spielzug_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)
pfade.MEDIA_SZENEN = tmp / "szenen"
pfade.MEDIA_SZENEN.mkdir()


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def fehlt(fn, *args, **kw):
    """True, wenn fn mit ValueError abgelehnt wird."""
    try:
        fn(*args, **kw)
    except ValueError:
        return True
    return False


# --- Ausgangslage -----------------------------------------------------------------------
conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)
gruppe = db.seite_anlegen(conn, "Allgemeine Spielzuege", "playbook", None, "Standards.")
jugo = db.seite_anlegen(conn, "Jugo", "playbook", gruppe, "Grundkonzept.")
kreisel = db.seite_anlegen(conn, "Kreisel", "playbook", gruppe, "Mitte spielt auf Halblinks.")
gegner = db.seite_anlegen(conn, "HSG Beispiel", "gegner", None, "Steht tief.")

aid = db.analyse_speichern(
    conn, "ext-1", "HSG", "2026-09-14", "Liga", [],
    [{"name": "Jugo", "t_start": 100.0, "t_ende": 112.0, "ampel": "gruen", "key": "z1",
      "spieler_ids": [anna]}], None)
db.szene_clip_speichern(conn, aid, "z1", "z1.mp4", 90.0, 120.0)
(pfade.MEDIA_SZENEN / "z1.mp4").write_bytes(b"VIDEO-EINS")
clip1 = conn.execute("SELECT id FROM spiel_szene_clip WHERE szene_key = 'z1'").fetchone()["id"]

aid2 = db.analyse_speichern(
    conn, "ext-fremd", "FremdTeam", "2026-09-20", "Liga", [],
    [{"name": "Jugo", "t_start": 5.0, "t_ende": 9.0, "ampel": "gruen", "key": "f1",
      "spieler_ids": []}], None)
db.szene_clip_speichern(conn, aid2, "f1", "f1.mp4", 1.0, 12.0)
conn.execute("UPDATE spiel_analyse SET team_id = 2 WHERE id = ?", (aid2,))
conn.commit()
clip_fremd = conn.execute("SELECT id FROM spiel_szene_clip WHERE szene_key = 'f1'").fetchone()["id"]

ANGRIFF = {"LA": [40, 70], "HL": [110, 185], "RM": [200, 205], "HR": [290, 185],
           "RA": [360, 70], "KR": [200, 130]}
ABWEHR = {"D1": [85, 75], "D2": [135, 105], "D3": [180, 122], "D4": [220, 122],
          "D5": [265, 105], "D6": [315, 75]}


def knoten(text, kinder=None, reaktion=None, stellung=None, video=None):
    return {"text": text, "reaktion": reaktion, "stellung": stellung or {},
            "video_clip_id": video, "kinder": kinder or []}


def baum():
    grund = copy.deepcopy({"angriff": ANGRIFF, "abwehr": ABWEHR, "ball": "RM"})   # frische Kopie: Negativfaelle veraendern sie
    return knoten("Grundaufstellung", stellung=grund, kinder=[
        knoten("RM passt auf HL", stellung={"angriff": {"KR": [170, 125]}, "ball": "HL"}, kinder=[
            knoten("HL geht ins 1-gegen-1", stellung={"angriff": {"HL": [150, 165]}}, kinder=[
                knoten("KR schliesst ab", reaktion="D3 tritt raus",
                       stellung={"abwehr": {"D3": [160, 148]}, "ball": "KR"}, video=clip1),
                knoten("RA wirft", reaktion="D1 schiebt",
                       stellung={"abwehr": {"D1": [115, 95]}, "ball": "RA"}),
                knoten("RM wirft aus der Distanz", reaktion="Mitte zu",
                       stellung={"abwehr": {"D3": [170, 125]}, "ball": "RM"}),
            ])])])


def texte(n):
    """Alle Texte des Baums in Tiefensuche - zum Vergleichen."""
    return [n["text"]] + [t for k in n["kinder"] for t in texte(k)]


def zeilen(tabelle="spielzug_schritt"):
    c = sqlite3.connect(DB)
    n = c.execute(f"SELECT COUNT(*) FROM {tabelle}").fetchone()[0]
    c.close()
    return n


# --- Schema / Migration ---------------------------------------------------------------------
def spalten(t):
    return {r["name"]: r for r in conn.execute(f"PRAGMA table_info({t})")}


check("team_id" in spalten("seiten") and "team_id" in spalten("spiel_analyse"),
      "Seiten und Analysen haben eine team_id (Mandantenfaehigkeit)")
check(spalten("seiten")["team_id"]["dflt_value"] == "1", "Bestandsdaten gehoeren zu Team 1")
check("team_id" in spalten("spielzug_schritt"), "Die neue Tabelle spielzug_schritt hat team_id")

# --- Speichern und Laden --------------------------------------------------------------------
check(db.ansicht_laden(conn, 1, jugo) is None, "Ohne gespeicherte Ansicht: None")
db.ansicht_speichern(conn, 1, jugo, baum())
b = db.ansicht_laden(conn, 1, jugo)
check(texte(b) == texte(baum()), "Der Baum kommt unveraendert zurueck (Reihenfolge der Aeste bleibt)")
verz = b["kinder"][0]["kinder"][0]
check([k["reaktion"] for k in verz["kinder"]] == ["D3 tritt raus", "D1 schiebt", "Mitte zu"],
      "Die drei Abwehrreaktionen stehen in der gespeicherten Reihenfolge")
check(all(isinstance(k["id"], int) for k in verz["kinder"]), "Jeder Knoten hat eine ID")
check(b["stellung"]["angriff"]["RM"] == [200, 205] and b["stellung"]["abwehr"]["D6"] == [315, 75],
      "Angriff UND Abwehr werden gespeichert")
check(verz["kinder"][0]["video_clip_id"] == clip1 and verz["kinder"][1]["video_clip_id"] is None,
      "Das Video haengt an genau einer Loesung")

# --- Idempotenz / Ersetzen -------------------------------------------------------------------
db.ansicht_speichern(conn, 1, jugo, baum())
check(zeilen() == 6, "Zweimal dasselbe speichern verdoppelt nichts (6 Knoten)")
klein = knoten("Nur ein Schritt", stellung={"angriff": ANGRIFF})
db.ansicht_speichern(conn, 1, jugo, klein)
check(zeilen() == 1 and texte(db.ansicht_laden(conn, 1, jugo)) == ["Nur ein Schritt"],
      "Speichern ersetzt die alte Ansicht komplett")
db.ansicht_speichern(conn, 1, jugo, baum())

# --- Pruefungen: ungueltige Daten werden abgelehnt, die alte Ansicht bleibt ---------------
def mit(aenderung):
    x = baum()
    aenderung(x)
    return x


def verzweigung(x):
    return x["kinder"][0]["kinder"][0]


faelle = {
    "unbekannte Angriffs-Position": mit(lambda x: x["stellung"]["angriff"].update({"XX": [10, 10]})),
    "unbekannte Abwehr-Position": mit(lambda x: x["stellung"]["abwehr"].update({"D7": [10, 10]})),
    "Koordinate ausserhalb des Feldes": mit(lambda x: x["stellung"]["angriff"].update({"LA": [500, 10]})),
    "Koordinate keine Zahl": mit(lambda x: x["stellung"]["angriff"].update({"LA": ["a", 10]})),
    "Ball bei unbekannter Spielerin": mit(lambda x: x["stellung"].update({"ball": "ZZ"})),
    "Verzweigung ohne Beschriftung": mit(lambda x: verzweigung(x)["kinder"][1].update({"reaktion": ""})),
    "mehr als 6 Aeste": mit(lambda x: verzweigung(x)["kinder"].extend(
        [knoten(f"Extra {i}", reaktion=f"R{i}") for i in range(4)])),
    "Text fehlt": mit(lambda x: x.update({"text": ""})),
    "Text zu lang": mit(lambda x: x.update({"text": "a" * 1001})),
    "unbekannter Clip": mit(lambda x: verzweigung(x)["kinder"][1].update({"video_clip_id": 99999})),
    "Clip eines fremden Teams": mit(lambda x: verzweigung(x)["kinder"][1].update({"video_clip_id": clip_fremd})),
}
tief = knoten("t0")
cur = tief
for i in range(1, 15):
    nxt = knoten(f"t{i}")
    cur["kinder"].append(nxt)
    cur = nxt
faelle["zu tief (ueber 12 Schritte)"] = tief
for name, x in faelle.items():
    check(fehlt(db.ansicht_speichern, conn, 1, jugo, x), "Abgelehnt: " + name)
check(texte(db.ansicht_laden(conn, 1, jugo)) == texte(baum()) and zeilen() == 6,
      "Nach abgelehnten Versuchen ist die alte Ansicht unveraendert (alles oder nichts)")
check(fehlt(db.ansicht_speichern, conn, 1, gegner, baum()), "Ansicht nur fuer Playbook-Seiten")
check(fehlt(db.ansicht_speichern, conn, 1, 99999, baum()), "Ansicht fuer unbekannte Seite abgelehnt")

# --- Teams -----------------------------------------------------------------------------------
check(db.ansicht_laden(conn, 2, jugo) is None, "Team 2 sieht die Ansicht von Team 1 nicht")
check(fehlt(db.ansicht_speichern, conn, 2, jugo, baum()), "Team 2 darf die Seite von Team 1 nicht beschreiben")
check(zeilen() == 6, "... und es entstehen keine Zeilen")
check([c["clip_id"] for c in db.spielzug_clips(conn, 1)] == [clip1], "Clip-Auswahl: nur Clips des eigenen Teams")
check([c["clip_id"] for c in db.spielzug_clips(conn, 2)] == [clip_fremd], "... und Team 2 sieht nur den eigenen")
c1 = db.spielzug_clips(conn, 1)[0]
check(c1["gegner"] == "HSG" and c1["datum"] == "2026-09-14" and c1["name"] == "Jugo"
      and c1["ampel"] == "gruen", "Auswahl zeigt Gegner, Datum, Spielzug-Name und Ampel")

# --- Video weg -> Knoten bleibt -------------------------------------------------------------
tmp_aid = db.analyse_speichern(conn, "ext-weg", "Weg", "2026-10-01", "Liga", [],
                               [{"name": "Jugo", "t_start": 1.0, "t_ende": 5.0, "ampel": "gelb",
                                 "key": "w1", "spieler_ids": []}], None)
db.szene_clip_speichern(conn, tmp_aid, "w1", "w1.mp4", 0.0, 6.0)
clip_weg = conn.execute("SELECT id FROM spiel_szene_clip WHERE szene_key = 'w1'").fetchone()["id"]
x = baum()
verzweigung(x)["kinder"][1]["video_clip_id"] = clip_weg
db.ansicht_speichern(conn, 1, jugo, x)
db.analyse_loeschen(conn, tmp_aid)
k = verzweigung(db.ansicht_laden(conn, 1, jugo))["kinder"][1]
check(k["text"] == "RA wirft" and k["video_clip_id"] is None,
      "Wird die Analyse geloescht, bleibt die Loesung und nur das Video faellt weg")
db.ansicht_speichern(conn, 1, jugo, baum())
conn.close()

# --- API ------------------------------------------------------------------------------------
def client(name=None, pin=None):
    c = TestClient(balu.app)
    if name:
        assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


T, A, ANON = client("Trainer", "1111"), client("Anna", "2222"), client()
url = f"/api/seiten/{jugo}/ansicht"

check(ANON.get(url).status_code == 401, "API: ohne Anmeldung 401")
r = A.get(url)
check(r.status_code == 200 and r.json()["ansicht"]["text"] == "Grundaufstellung",
      "API: Spielerin sieht die Ansicht eines Playbook-Spielzugs")
check(A.get(f"/api/seiten/{kreisel}/ansicht").json() == {"ansicht": None},
      "API: Seite ohne Ansicht liefert ansicht = null (kein Fehler)")
check(A.get(f"/api/seiten/{gegner}/ansicht").status_code == 403, "API: Gegner-Seiten bleiben fuer Spielerinnen gesperrt")
check(A.get("/api/seiten/99999/ansicht").status_code == 404, "API: unbekannte Seite 404")

check(A.post(url, json={"ansicht": baum()}).status_code == 403, "API: Spielerin darf nicht speichern")
check(ANON.post(url, json={"ansicht": baum()}).status_code == 401, "API: ohne Anmeldung kein Speichern")
r = T.post(url, json={"ansicht": baum()})
check(r.status_code == 200, "API: Trainer speichert")
check(T.post(url, json={"ansicht": baum()}).status_code == 200 and zeilen() == 6,
      "API: Wiederholung (Outbox) ist harmlos")
r = T.post(url, json={"ansicht": mit(lambda x: x["stellung"]["angriff"].update({"LA": [999, 0]}))})
check(r.status_code == 400 and "Feld" in r.json()["detail"], "API: ungueltige Daten -> 400 mit lesbarer Meldung")
check(T.post(f"/api/seiten/{gegner}/ansicht", json={"ansicht": baum()}).status_code == 400,
      "API: Ansicht fuer eine Gegner-Seite -> 400")

# Video ausliefern
schritt_mit_video = verzweigung(A.get(url).json()["ansicht"])["kinder"][0]["id"]
schritt_ohne = verzweigung(A.get(url).json()["ansicht"])["kinder"][1]["id"]
r = A.get(f"/api/spielzug-schritte/{schritt_mit_video}/video")
check(r.status_code == 200 and r.content == b"VIDEO-EINS",
      "API: Spielerin sieht das Video einer Loesung (Playbook ist fuer alle da)")
check(A.get(f"/api/spielzug-schritte/{schritt_ohne}/video").status_code == 404, "API: Loesung ohne Video -> 404")
check(ANON.get(f"/api/spielzug-schritte/{schritt_mit_video}/video").status_code == 401, "API: Video nur angemeldet")

# Clip-Auswahl
check(A.get("/api/spielzug-clips").status_code == 403, "API: Clip-Auswahl nur fuer Trainer")
check([c["clip_id"] for c in T.get("/api/spielzug-clips").json()] == [clip1], "API: Trainer sieht die Clips seines Teams")

# Archivieren entfernt die Ansicht, der Name bleibt
check(T.post(f"/api/seiten/{jugo}/loeschen").status_code == 200, "Spielzug archivieren")
check(zeilen() == 0, "Mit dem Archivieren verschwindet die Ansicht (Daten + Videoverknuepfung)")
check(T.get(url).status_code == 404, "... und die archivierte Seite hat keine Ansicht mehr")

# Entfernen per null
db2 = db.verbinde()
db.ansicht_speichern(db2, 1, kreisel, baum())
db2.close()
check(T.post(f"/api/seiten/{kreisel}/ansicht", json={"ansicht": None}).status_code == 200
      and A.get(f"/api/seiten/{kreisel}/ansicht").json() == {"ansicht": None},
      "API: ansicht = null entfernt die Ansicht")

print("\nAlle Tests gruen.")
