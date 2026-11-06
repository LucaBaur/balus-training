"""Tests fuer die Mannschaftskasse (Amt "Kassenwart"): Rechte, Validierung, Rechnung, Idempotenz,
Storno, Sichtbarkeit.

Laeuft gegen eine temporaere Datenbank - die echte elo.db bleibt unberuehrt.
Start:  py tests/kasse_test.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import aemter  # noqa: E402
import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="kasse_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
anna = db.spieler_anlegen(conn, "Anna")
bea = db.spieler_anlegen(conn, "Bea")
cora = db.spieler_anlegen(conn, "Cora")
dora = db.spieler_anlegen(conn, "Dora")            # hat kein Konto: Schuldnerin ohne App-Zugang
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


def amt_vergeben(schluessel, spieler, da=True):
    r = T.post(f"/api/aemter/{amt_id(schluessel)}/inhaber", json={"spieler_id": spieler, "da": da})
    assert r.status_code == 200, r.text


def buchen(c, art, cent, text="Test", spieler=None, **extra):
    daten = {"art": art, "betrag_cent": cent, "text": text, "spieler_id": spieler}
    daten.update(extra)
    return c.post("/api/kasse/buchung", json=daten)


def uebersicht(c):
    r = c.get("/api/kasse")
    assert r.status_code == 200, r.text
    return r.json()


# --- Lesen: nur angemeldet; leere Kasse ------------------------------------------------------------------
check(OFFEN.get("/api/kasse").status_code == 401, "Kasse nur für Angemeldete")
check(OFFEN.post("/api/kasse/buchung", json={"art": "einnahme", "betrag_cent": 100, "text": "x"}).status_code == 401,
      "Buchen ohne Anmeldung gibt 401")
leer = uebersicht(A)
check(leer["stand"]["kasse_cent"] == 0 and leer["buchungen"] == [] and leer["mein_offen_cent"] == 0
      and not leer["darf_buchen"], "leere Kasse: Stand 0, keine Buchungen, nichts offen, kein Buchungsrecht")

# --- Rechte: nur das Amt Kassenwart (und der Trainer) buchen ----------------------------------------------
check(buchen(A, "einnahme", 100).status_code == 403, "Spielerin ohne Amt darf nicht buchen")
amt_vergeben("kapitaen", cora)
check(buchen(C, "einnahme", 100).status_code == 403, "ein anderes Amt (Kapitän) gibt kein Kassenrecht")
amt_vergeben("kassenwart", bea)
check(B.get("/api/me").json()["rechte"] == ["kasse"], "/api/me: Kassenwart hat das Recht „kasse“")
check("kasse" in aemter.RECHTE and aemter.AMT_RECHTE["kassenwart"] == ("kasse",),
      "Das Recht „kasse“ hängt am Amt Kassenwart")
kw = next(a for a in B.get("/api/aemter").json()["aemter"] if a["schluessel"] == "kassenwart")
check(kw["rechte"] == [aemter.RECHTE["kasse"]] and "noch nicht in der App" not in kw["beschreibung"],
      "Amtskarte nennt das Recht; der Text „noch nicht in der App“ ist weg")
check(uebersicht(B)["darf_buchen"] and uebersicht(T)["darf_buchen"] and not uebersicht(A)["darf_buchen"],
      "darf_buchen: Kassenwart und Trainer ja, Spielerin nein")

# --- Validierung -----------------------------------------------------------------------------------------
check(buchen(B, "einnahme", 0).status_code == 400, "Betrag 0 wird abgelehnt")
check(buchen(B, "einnahme", -500).status_code == 400, "negativer Betrag wird abgelehnt (Richtung steckt in der Art)")
check(buchen(B, "einnahme", 100_000_001).status_code == 400, "absurd hoher Betrag wird abgelehnt (Tippfehler-Schutz)")
check(buchen(B, "einnahme", 12.5).status_code in (400, 422), "Kommabeträge gibt es nicht: nur ganze Cent")
check(buchen(B, "einnahme", "viel").status_code in (400, 422), "Text statt Zahl wird abgelehnt")
check(buchen(B, "spende", 100).status_code == 400, "unbekannte Art wird abgelehnt")
check(buchen(B, "forderung", 500).status_code == 400, "Forderung braucht eine Spielerin")
check(buchen(B, "einzahlung", 500).status_code == 400, "Einzahlung braucht eine Spielerin")
check(buchen(B, "ausgabe", 500, spieler=anna).status_code == 400, "Ausgabe ohne Spielerinnen-Bezug")
check(buchen(B, "einnahme", 500, spieler=anna).status_code == 400, "Einnahme ohne Spielerinnen-Bezug")
check(buchen(B, "forderung", 500, spieler=9999).status_code == 404, "unbekannte Spielerin gibt 404")
check(buchen(B, "einnahme", 500, text="   ").status_code == 400, "leerer Text wird abgelehnt")
check(buchen(B, "einnahme", 500, text="x" * 121).status_code == 400, "zu langer Text wird abgelehnt")
check(buchen(B, "einnahme", 500, datum="2026-13-40").status_code == 400, "ungültiges Datum wird abgelehnt")
check(buchen(B, "einnahme", 500, datum="gestern").status_code == 400, "Datum muss JJJJ-MM-TT sein")
check(buchen(B, "einnahme", 500, token="t" * 65).status_code == 400, "zu langes Token wird abgelehnt")
check(uebersicht(B)["buchungen"] == [], "nach lauter Fehlversuchen steht nichts im Kassenbuch")

# --- Rechnung: Kassenstand und offene Posten ---------------------------------------------------------------
r = buchen(B, "forderung", 500, "Zu spät", anna, datum="2026-10-01")
check(r.status_code == 200 and r.json()["neu"] and isinstance(r.json()["id"], int), "Kassenwart bucht eine Forderung")
id_forderung_anna = r.json()["id"]
id_forderung_dora = buchen(B, "forderung", 300, "Handy in der Halle", dora).json()["id"]
id_einzahlung_anna = buchen(B, "einzahlung", 200, "Bar bezahlt", anna).json()["id"]
id_ausgabe = buchen(T, "ausgabe", 1000, "Getränke", None).json()["id"]
id_einnahme = buchen(T, "einnahme", 4000, "Spende").json()["id"]
u = uebersicht(B)
check(u["stand"]["kasse_cent"] == 200 + 4000 - 1000, "Kassenstand = Einzahlungen + Einnahmen - Ausgaben (Forderungen noch nicht)")
check(u["stand"]["einnahmen_cent"] == 4200 and u["stand"]["ausgaben_cent"] == 1000, "Summe der Einnahmen und Ausgaben")
offen = {o["name"]: o for o in u["offen"]}
check(offen["Anna"]["offen_cent"] == 300 and offen["Anna"]["forderung_cent"] == 500 and offen["Anna"]["einzahlung_cent"] == 200,
      "Anna schuldet 5,00 - 2,00 = 3,00")
check(offen["Dora"]["offen_cent"] == 300, "Dora (ohne Konto) schuldet 3,00")
check(u["stand"]["offen_cent"] == 600, "Gesamt offen = 6,00")
check([o["name"] for o in u["offen"]] == ["Anna", "Dora"] or [o["name"] for o in u["offen"]] == ["Dora", "Anna"],
      "nur Spielerinnen mit Buchungen stehen in der Offen-Liste")
check(all(isinstance(x, int) for x in (u["stand"]["kasse_cent"], u["stand"]["offen_cent"])), "alle Beträge sind ganze Cent")
b_eintrag = next(x for x in u["buchungen"] if x["id"] == id_forderung_anna)
check(b_eintrag["datum"] == "2026-10-01" and b_eintrag["spieler_name"] == "Anna" and b_eintrag["art"] == "forderung"
      and b_eintrag["erstellt_von"] == "Bea" and not b_eintrag["storniert"], "Buchung trägt Datum, Name, Art und Verfasserin")
heute_eintrag = next(x for x in u["buchungen"] if x["id"] == id_einnahme)
check(len(heute_eintrag["datum"]) == 10 and heute_eintrag["datum"][4] == "-", "ohne Datum gilt heute")

# Cent-Genauigkeit: 0,10 + 0,20 ist exakt 0,30 (mit Gleitkommazahlen wären es 0,30000000000000004)
buchen(B, "forderung", 10, "a", dora)
buchen(B, "forderung", 20, "b", dora)
check({o["name"]: o for o in uebersicht(B)["offen"]}["Dora"]["offen_cent"] == 330, "10 + 20 Cent sind exakt 30 Cent")

# Überzahlung ist ein Guthaben (negativ), kein Fehler
buchen(B, "einzahlung", 1000, "Vorauszahlung", cora)
check({o["name"]: o for o in uebersicht(B)["offen"]}["Cora"]["offen_cent"] == -1000, "Vorauszahlung steht als Guthaben (-10,00)")
check(uebersicht(B)["stand"]["offen_cent"] == 300 + 330, "Guthaben mindert die Gesamtsumme der offenen Posten nicht")
id_vorauszahlung = next(x["id"] for x in uebersicht(B)["buchungen"] if x["text"] == "Vorauszahlung")
check(T.post(f"/api/kasse/buchung/{id_vorauszahlung}/storno").status_code == 200, "Vorauszahlung wieder storniert")

# --- Idempotenz: doppelt gesendet wird einmal gebucht -----------------------------------------------------------
anzahl = len(uebersicht(B)["buchungen"])
r1 = buchen(B, "einnahme", 700, "Flohmarkt", token="flohmarkt-1")
r2 = buchen(B, "einnahme", 700, "Flohmarkt", token="flohmarkt-1")
check(r1.status_code == 200 and r2.status_code == 200 and r1.json()["id"] == r2.json()["id"]
      and r1.json()["neu"] and not r2.json()["neu"], "gleiches Token: zweiter Aufruf liefert dieselbe Buchung, neu=false")
check(len(uebersicht(B)["buchungen"]) == anzahl + 1, "…und im Kassenbuch steht sie nur einmal")
check(buchen(B, "einnahme", 700, "Flohmarkt", token="flohmarkt-2").json()["neu"], "anderes Token: neue Buchung")
stand_vor_storno = uebersicht(B)["stand"]["kasse_cent"]

# --- Storno: nichts wird gelöscht ---------------------------------------------------------------------------------
check(A.post(f"/api/kasse/buchung/{id_einzahlung_anna}/storno").status_code == 403, "Spielerin storniert nicht")
check(C.post(f"/api/kasse/buchung/{id_einzahlung_anna}/storno").status_code == 403, "Kapitänin storniert nicht")
check(B.post("/api/kasse/buchung/9999/storno").status_code == 404, "Storno einer unbekannten Buchung gibt 404")
r = B.post(f"/api/kasse/buchung/{id_einzahlung_anna}/storno")
check(r.status_code == 200 and r.json()["neu"], "Kassenwart storniert Annas Einzahlung")
check(not B.post(f"/api/kasse/buchung/{id_einzahlung_anna}/storno").json()["neu"], "Storno wiederholen ändert nichts (idempotent)")
u = uebersicht(B)
check(u["stand"]["kasse_cent"] == stand_vor_storno - 200, "stornierte Einzahlung zählt nicht mehr zur Kasse")
check({o["name"]: o for o in u["offen"]}["Anna"]["offen_cent"] == 500, "…und Anna schuldet wieder 5,00")
eintrag = next(x for x in u["buchungen"] if x["id"] == id_einzahlung_anna)
check(eintrag["storniert"] is True, "Die stornierte Buchung bleibt im Kassenbuch sichtbar, als storniert markiert")
check(T.post(f"/api/kasse/buchung/{id_forderung_anna}/storno").status_code == 200
      and "Anna" not in {o["name"] for o in uebersicht(B)["offen"] if o["offen_cent"] > 0}, "Trainer storniert Annas Forderung; sie schuldet nichts mehr")
c = db.verbinde()
check(c.execute("SELECT COUNT(*) FROM kasse_buchung WHERE storniert_am IS NOT NULL").fetchone()[0] >= 3
      and c.execute("SELECT COUNT(*) FROM kasse_buchung").fetchone()[0] == len(uebersicht(B)["buchungen"]),
      "in der Datenbank ist nichts gelöscht, nur markiert")
c.close()

# --- Sichtbarkeit: Spielerinnen sehen die Kasse, aber nur die eigenen Posten --------------------------------------
buchen(B, "forderung", 400, "Trikot vergessen", anna)             # Annas offene Forderung
ua = uebersicht(A)
sichtbar = {x["text"] for x in ua["buchungen"]}
check(ua["stand"]["kasse_cent"] == uebersicht(B)["stand"]["kasse_cent"], "Anna sieht denselben Kassenstand wie die Kassenwartin")
check({"Getränke", "Spende", "Trikot vergessen"} <= sichtbar, "Anna sieht die Ausgaben/Einnahmen der Kasse und ihre eigenen Posten")
check("Handy in der Halle" not in sichtbar and all(x["spieler_id"] in (None, anna) for x in ua["buchungen"]),
      "…aber nicht die Posten anderer Spielerinnen (Doras Strafe)")
check(ua["mein_offen_cent"] == 400 and "kader" not in ua and not ua["darf_buchen"],
      "Anna sieht ihren eigenen offenen Betrag, aber weder Kader noch Buchungsrecht")
# Offene Strafen sind für alle sichtbar (Wunsch der Mannschaft): Name und offener Betrag, sonst nichts.
check([(o["name"], o["offen_cent"]) for o in ua["offen"]] == [("Anna", 400), ("Dora", 330)],
      "Anna sieht die offenen Strafen aller: Anna 4,00 und Dora 3,30, der größte Betrag zuerst")
check(all(set(o) == {"spieler_id", "name", "offen_cent"} for o in ua["offen"]),
      "…ohne Einzelheiten: nur Spielerin und offener Betrag (keine Summen von Forderungen/Zahlungen)")
check(ua["stand"]["offen_cent"] == 730, "…und die Gesamtsumme der offenen Strafen (7,30)")
check("Handy in der Halle" not in {x["text"] for x in ua["buchungen"]},
      "…aber WOFÜR jemand eine Strafe bekam, sieht nur sie selbst (Buchungen anderer bleiben privat)")
buchen(B, "einzahlung", 500, "Vorauszahlung Beitrag", cora)                      # Cora hat jetzt Guthaben (-5,00)
check("Cora" not in {o["name"] for o in uebersicht(A)["offen"]} and uebersicht(A)["stand"]["offen_cent"] == 730,
      "Guthaben anderer sieht niemand außer Kassenwartin/Trainer (offen heißt: schuldet)")
check({o["name"]: o["offen_cent"] for o in uebersicht(B)["offen"]}["Cora"] == -500, "Die Kassenwartin sieht Coras Guthaben")
B.post(f"/api/kasse/buchung/{next(x['id'] for x in uebersicht(B)['buchungen'] if x['text'] == 'Vorauszahlung Beitrag')}/storno")
check(uebersicht(C)["mein_offen_cent"] == 0 and [o["name"] for o in uebersicht(C)["offen"]] == ["Anna", "Dora"],
      "Auch Cora ohne eigene Schuld sieht die offenen Strafen der anderen")
uc = uebersicht(C)
check(uc["mein_offen_cent"] == 0 and all(x["spieler_id"] in (None, cora) for x in uc["buchungen"])
      and "Vorauszahlung" in {x["text"] for x in uc["buchungen"]} and "Zu spät" not in {x["text"] for x in uc["buchungen"]},
      "Cora sieht die Kassen-Buchungen und ihre eigene (stornierte) Vorauszahlung, sonst nichts")
ub, ut = uebersicht(B), uebersicht(T)
check("Handy in der Halle" in {x["text"] for x in ub["buchungen"]} and ub["stand"]["offen_cent"] == 730
      and {k["name"] for k in ub["kader"]} >= {"Anna", "Dora"}, "Kassenwartin sieht alle Buchungen und den Kader zum Auswählen")
check(all({"forderung_cent", "einzahlung_cent"} <= set(o) for o in ub["offen"]),
      "…und in der Offen-Liste die Einzelsummen (Forderungen, Zahlungen)")
check(len(ut["buchungen"]) == len(ub["buchungen"]) and ut["offen"] == ub["offen"], "Trainer sieht dasselbe wie die Kassenwartin")

# --- Strafenkatalog: Eingabehilfe, die jede sieht --------------------------------------------------------------------
kat = uebersicht(C)["katalog"]
keys = [k["key"] for k in kat]
check(len(kat) >= 20 and len(set(keys)) == len(keys), "Katalog: mindestens 20 Posten, Schlüssel eindeutig, auch für Spielerinnen sichtbar")
check(all(k["cent"] is None or (isinstance(k["cent"], int) and 0 < k["cent"] <= db.KASSE_MAX_CENT) for k in kat),
      "Katalog: Beträge sind ganze Cent (oder leer bei „Kasten“) und innerhalb der Obergrenze")
check(all(k["einheit"] in (None, "Min", "Teil") for k in kat), "Katalog: Einheiten sind bekannt")
check(any(k["cent"] is None for k in kat) and any(k["einheit"] for k in kat), "Katalog enthält Kasten-Posten und Posten „pro Einheit“")

# --- Amt entzogen = Recht weg; Nur-Lesen-Modus ---------------------------------------------------------------------
amt_vergeben("kassenwart", bea, False)
check(buchen(B, "einnahme", 100).status_code == 403 and not uebersicht(B)["darf_buchen"], "ohne das Amt wieder keine Buchungen")
check(B.post(f"/api/kasse/buchung/{id_ausgabe}/storno").status_code == 403, "…und kein Storno")
konten = T.get("/api/ansicht/konten").json()
annas_konto = next(k["benutzer_id"] for k in konten if k["name"] == "Anna")
T2 = client("Trainer", "1111")
check(T2.post(f"/api/ansicht/{annas_konto}").status_code == 200, "Trainer sieht die App als Anna")
check(uebersicht(T2)["mein_offen_cent"] == 400 and not uebersicht(T2)["darf_buchen"], "…sieht Annas Sicht auf die Kasse")
check(T2.post("/api/kasse/buchung", json={"art": "einnahme", "betrag_cent": 100, "text": "x"}).status_code == 403,
      "…und kann in diesem Modus nichts buchen (Nur-Lesen)")

# --- Migration 2: Standardtext des Amts Kassenwart ---------------------------------------------------------------
import sqlite3  # noqa: E402

from daten import migrationen  # noqa: E402


def amt_text(c):
    return c.execute("SELECT beschreibung FROM amt WHERE schluessel = 'kassenwart'").fetchone()[0]


def bestands_db(name, text):
    """Eine Datenbank wie vor dieser Version: Stand 1, Kassenwart mit dem alten (oder einem eigenen) Text."""
    c = _verbinde(tmp / name)
    db.init_db(c)
    c.execute("UPDATE amt SET beschreibung = ? WHERE schluessel = 'kassenwart'", (text,))
    c.execute("PRAGMA user_version = 1")
    c.commit()
    return c


c1 = bestands_db("alt.db", migrationen.KASSENWART_TEXT_ALT)
check(migrationen.migriere(c1) == [2] and amt_text(c1) == migrationen.KASSENWART_TEXT_NEU,
      "Migration 2 ersetzt den alten Standardtext des Kassenwarts")
check(migrationen.migriere(c1) == [], "…und läuft nicht ein zweites Mal")
c2 = bestands_db("eigen.db", "Unser Text, vom Trainer geschrieben")
migrationen.migriere(c2)
check(amt_text(c2) == "Unser Text, vom Trainer geschrieben", "Ein vom Trainer geänderter Text bleibt unberührt")
roh = sqlite3.connect(tmp / "leer.db")
roh.row_factory = sqlite3.Row
roh.executescript(db.SCHEMA)
check(migrationen.migriere(roh) == [1, 2], "Migration 2 überlebt eine Datenbank ohne Tabelle „amt“ (frischer Start)")
c1.close(); c2.close(); roh.close()

print("\nalles ok")
