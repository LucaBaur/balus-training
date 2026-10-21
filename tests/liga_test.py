"""Tests fuer die Liga-Daten (Umwandlung, Zwischenspeicher, Ausfall der Quelle, Endpunkt).

Arbeitet mit einer gespeicherten Antwort der echten Schnittstelle
(tests/liga_beispiel.json, Stand 18.10.2026) - es wird nichts aus dem Netz geholt.
Start:  py tests/liga_test.py
"""
import json
import sys
import tempfile
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
import liga  # noqa: E402

ROH = json.loads((Path(__file__).with_name("liga_beispiel.json")).read_text(encoding="utf-8"))
tmp = Path(tempfile.mkdtemp(prefix="liga_test_"))
liga.CACHE_DATEI = tmp / "liga_cache.json"
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def frisch():
    liga._speicher.update(ts=0.0, daten=None)
    liga.CACHE_DATEI.unlink(missing_ok=True)


# ---- Umwandlung ------------------------------------------------------------
d = liga.normalisiere(ROH)
check(d["liga"] == "Frauen Bezirksoberliga" and d["region"] == "Oberschwaben-Ostalb", "Liga und Region")
check(d["runde"].endswith("2026/2027") and d["stand"] == "So, 18.10.2026, 18:25h", "Runde und Stand ohne Vorspann")
check(len(d["tabelle"]) == 10 and len(d["spiele"]) == 18, "10 Mannschaften, 18 Spiele")
t = d["tabelle"]
check([x["platz"] for x in t][:3] == [1, 2, 3] and t[0]["team"].startswith("HSG Oberkochen"), "Tabelle: Platz 1-3")
ger = next(x for x in t if x["eigen"])
check(ger["team"] == "TV Gerhausen 1900" and ger["platz"] == 3, "Eigene Mannschaft erkannt (Platz 3)")
check((ger["spiele"], ger["s"], ger["u"], ger["n"]) == (4, 2, 1, 1), "Gerhausen: 4 Spiele, 2-1-1")
check((ger["tore_plus"], ger["tore_minus"], ger["punkte_plus"], ger["punkte_minus"]) == (88, 94, 5, 3), "Gerhausen: 88:94 Tore, 5:3 Punkte")
check(sum(1 for x in t if x["eigen"]) == 1, "Genau eine eigene Mannschaft")
check(next(x for x in t if x["team"] == "Bregenz Handball")["platz"] is None, "Gleicher Platz: keine Platzziffer")
check(len(d["hinweise"]) == 1 and "direkten Vergleich" in d["hinweise"][0] and "<br>" not in d["hinweise"][0], "Tabellenhinweis ohne HTML")

s = d["spiele"]
check([x["datum"] for x in s] == sorted(x["datum"] for x in s), "Spiele nach Datum sortiert")
check(s[0]["datum"] == "2026-09-26" and s[0]["zeit"] == "18:00", "Datum ISO, Uhrzeit")
erstes = s[0]
check((erstes["heim"], erstes["gast"], erstes["tore_heim"], erstes["tore_gast"]) == ("SG Brenztal", "TV Gerhausen", 29, 32), "Spiel 1: Brenztal - Gerhausen 29:32")
check(erstes["ergebnis"] == "S" and erstes["eigen_heim"] is False and erstes["halbzeit"] == "13:14", "Spiel 1: Sieg auswaerts, Halbzeit 13:14")
check(erstes["bemerkung"] == "alt: 17:30" and erstes["status"] == "gespielt", "Spiel 1: Verlegung als Bemerkung")
check(s[1]["ergebnis"] == "S" and s[1]["eigen_heim"] is True, "Spiel 2: Heimsieg gegen Hard")
check(s[2]["ergebnis"] == "U" and s[2]["tore_heim"] == 19 and s[2]["tore_gast"] == 19, "Spiel 3: 19:19 unentschieden")
check(s[3]["ergebnis"] == "N" and (s[3]["tore_heim"], s[3]["tore_gast"]) == (26, 13), "Spiel 4: 13:26 Niederlage in Oberkochen")
check([x["status"] for x in s].count("gespielt") == 4 and [x["status"] for x in s].count("offen") == 14, "4 gespielt, 14 offen")
offen = next(x for x in s if x["status"] == "offen")
check(offen["tore_heim"] is None and offen["ergebnis"] is None and offen["halbzeit"] is None, "Offenes Spiel: keine Zahlen")
check(offen["halle"] and offen["ort"], "Halle und Ort vorhanden")
check(all(x["eigen_heim"] or x["gast"].startswith("TV Gerhausen") for x in s), "Jedes Spiel mit Gerhausen")
check(not any("�" in str(x) for x in s), "Umlaute unversehrt")

# ---- Zwischenspeicher ------------------------------------------------------
frisch()
aufrufe = []
def hole_ok():
    aufrufe.append(1)
    return ROH

a = liga.liga_daten(hole_ok, jetzt=1000.0, heute=date(2026, 10, 20))
check(len(aufrufe) == 1 and a["veraltet"] is False and a["abgerufen"].endswith("Z"), "Erster Aufruf holt die Daten")
liga.liga_daten(hole_ok, jetzt=1000.0 + 600, heute=date(2026, 10, 20))
check(len(aufrufe) == 1, "Nach 10 Minuten (kein Spieltag): aus dem Zwischenspeicher")
liga.liga_daten(hole_ok, jetzt=1000.0 + 16 * 60, heute=date(2026, 10, 20))
check(len(aufrufe) == 2, "Nach 16 Minuten: neuer Abruf")
liga.liga_daten(hole_ok, jetzt=1000.0 + 16 * 60 + 4 * 60, heute=date(2026, 10, 24))
check(len(aufrufe) == 3, "Spieltag (24.10.): nach 4 Minuten schon neu abgerufen")
liga.liga_daten(hole_ok, jetzt=1000.0 + 16 * 60 + 4 * 60 + 60, heute=date(2026, 10, 24))
check(len(aufrufe) == 3, "Spieltag: nach 1 Minute noch nicht")
check(liga.CACHE_DATEI.exists(), "Zwischenspeicher liegt auf der Platte")

# ---- Ausfall der Quelle ------------------------------------------------------
def hole_kaputt():
    raise OSError("Quelle nicht erreichbar")

r = liga.liga_daten(hole_kaputt, jetzt=1000.0 + 3600, heute=date(2026, 10, 20))
check(r["veraltet"] is True and len(r["spiele"]) == 18, "Quelle faellt aus: letzter Stand, als veraltet markiert")
liga._speicher.update(ts=0.0, daten=None)                      # simulierter Neustart: Datei ist der Startwert
r = liga.liga_daten(hole_kaputt, jetzt=1000.0 + 7200, heute=date(2026, 10, 20))
check(r["veraltet"] is True and len(r["tabelle"]) == 10, "Nach Neustart und Ausfall: Stand aus der Datei")
frisch()
try:
    liga.liga_daten(hole_kaputt, jetzt=5.0)
    check(False, "Ohne jeden Stand muss ein Fehler kommen")
except OSError:
    check(True, "Ohne jeden Stand: Fehler")
def hole_muell():
    return [{"unerwartet": True}]
try:
    liga.liga_daten(hole_muell, jetzt=5.0)
    check(False, "Unbrauchbare Antwort muss abgelehnt werden")
except (KeyError, IndexError, TypeError):
    check(True, "Unbrauchbare Antwort: Fehler statt kaputter Daten")
check(liga._speicher["daten"] is None, "Unbrauchbare Antwort landet nicht im Zwischenspeicher")

# ---- Endpunkt ------------------------------------------------------------
conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
db.benutzer_anlegen(conn, "Anna", "spieler", auth.hash_pin("2222"), anna)
conn.close()


def client(name, pin):
    c = TestClient(balu.app)
    assert c.post("/api/login", json={"name": name, "pin": pin}).status_code == 200
    return c


frisch()
orig = liga.hole_roh
liga.hole_roh = lambda: ROH
check(TestClient(balu.app).get("/api/liga").status_code == 401, "Ohne Login: 401")
r = client("Anna", "2222").get("/api/liga")
check(r.status_code == 200 and len(r.json()["spiele"]) == 18, "Spielerin liest die Liga")
check(client("Trainer", "1111").get("/api/liga").status_code == 200, "Trainer liest die Liga")
frisch()
liga.hole_roh = lambda: (_ for _ in ()).throw(OSError("aus"))
r = client("Anna", "2222").get("/api/liga")
check(r.status_code == 503, "Quelle weg, kein Stand: 503 mit verstaendlicher Meldung")
liga.hole_roh = orig

print("\nAlle Tests gruen.")
