"""Tests fuer die zeitliche Login-Sperre und die Drosselung pro Adresse.

Vorher wurde die PIN nach 3 Fehlversuchen DAUERHAFT geloescht - wer nur einen Namen kannte, konnte jedes
Konto (auch das des Trainers) aus dem Internet aussperren. Jetzt gilt, je Mandant (team_id):
  - Name + Adresse:  5 Fehlversuche in 15 Minuten  -> diese Kombination wartet
  - Name (alle Adressen): 20 Fehlversuche in 60 Minuten -> dieser Name wartet (verteiltes Raten)
  - Adresse (alle Namen): 15 Fehlversuche in 15 Minuten -> diese Adresse wartet (ein Rechner probiert viele Namen)
Gezaehlt werden nur Fehlversuche; waehrend einer Wartezeit zaehlt nichts mehr dazu. Die PIN bleibt immer erhalten.
Alle Namen sind erfunden. Laeuft gegen eine temporaere Datenbank. Start:  py tests/login_sperre_test.py
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
from routen import konto as konto_route  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="login_sperre_test_"))
DB = tmp / "test.db"
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

conn = db.verbinde()
db.init_db(conn)
for n, pin in [("Anna", "1111"), ("Bea", "2222"), ("Cora", "3333"), ("Trainer", "4444")]:
    db.benutzer_anlegen(conn, n, "trainer" if n == "Trainer" else "spieler", auth.hash_pin(pin))
db.benutzer_anlegen(conn, "Dora", "spieler", None)          # Konto ohne PIN (alte Sperre / noch keine PIN)
conn.close()

JETZT = [1_800_000_000.0]
konto_route._jetzt = lambda: JETZT[0]                         # Uhr, die der Test selbst vorstellt


def check(bedingung, text):
    print(("ok   " if bedingung else "FEHLER ") + text)
    if not bedingung:
        sys.exit(1)


def login(name, pin, client=None):
    return (client or TestClient(balu.app)).post("/api/login", json={"name": name, "pin": pin})


def pin_da(name):
    c = db.verbinde()
    try:
        return bool(db.benutzer_nach_name(c, name)["pin_hash"])
    finally:
        c.close()


# --- Schema: Mandantenfaehigkeit ------------------------------------------------------------------------------
c = db.verbinde()
spalten = {r["name"]: r for r in c.execute("PRAGMA table_info(login_versuche)")}
check({"team_id", "ip", "name", "zeit"} <= set(spalten), "Tabelle login_versuche mit team_id, ip, name, zeit")
check(spalten["team_id"]["notnull"] == 1 and spalten["team_id"]["dflt_value"] == "1", "team_id NOT NULL DEFAULT 1")
indizes = [r["name"] for r in c.execute("PRAGMA index_list(login_versuche)")]
check(any("team" in i for i in indizes), "Index auf team_id vorhanden")
c.close()

# --- Normalfall: wenige Fehler sind harmlos ------------------------------------------------------------------
for rest in (4, 3, 2, 1):
    r = login("Anna", "0000")
    check(r.status_code == 401 and f"noch {rest} Versuch" in r.json()["detail"], f"Fehlversuch: 401, noch {rest} Versuch(e)")
check(login("Anna", "1111").status_code == 200, "mit richtiger PIN nach 4 Fehlern: Anmeldung klappt")
check(login("Anna", "1111").status_code == 200, "und weiterhin (Erfolg sperrt nie)")

# --- 5. Fehlversuch: Wartezeit statt dauerhafter Sperre -------------------------------------------------------
JETZT[0] += 3600          # frisches Zeitfenster
for _ in range(4):
    login("Bea", "0000")
r = login("Bea", "0000")
check(r.status_code == 401 and "15 Minuten" in r.json()["detail"], "5. Fehlversuch nennt die Wartezeit")
r = login("Bea", "2222")
check(r.status_code == 429, "danach ist selbst die RICHTIGE PIN abgelehnt (429), solange die Wartezeit laeuft")
check("Retry-After" in r.headers and 1 <= int(r.headers["Retry-After"]) <= 900, "Retry-After nennt die Sekunden (hoechstens 15 Minuten)")
check("Minute" in r.json()["detail"], "die Meldung nennt die Minuten")
check(pin_da("Bea"), "Die PIN bleibt erhalten (frueher: NULL = dauerhaft gesperrt)")
check(login("Cora", "3333").status_code == 200, "ein anderer Name von derselben Adresse kann sich anmelden")

# Waehrend der Wartezeit zaehlt nichts dazu: Dauerhaemmern verlaengert sie nicht
JETZT[0] += 600
for _ in range(10):
    login("Bea", "0000")
JETZT[0] += 301                                                # 15 min + 1 s nach dem 5. Fehlversuch
check(login("Bea", "2222").status_code == 200, "nach 15 Minuten geht es wieder (Hammern in der Pause verlaengert nichts)")

# --- Trainer-Konto laesst sich nicht dauerhaft aussperren ---------------------------------------------------
JETZT[0] += 3600
for _ in range(30):
    login("Trainer", "0000")
check(pin_da("Trainer"), "30 Fehlversuche auf den Trainer: PIN bleibt gespeichert")
JETZT[0] += 3600
check(login("Trainer", "4444").status_code == 200, "eine Stunde spaeter kommt der Trainer wieder rein")

# --- Unbekannter Name: gleiche Antwort, gleiche Drosselung ----------------------------------------------------
JETZT[0] += 3600
r1 = login("gibtsnicht", "0000")
JETZT[0] += 3600
login("Cora", "0000")
r2 = login("Cora", "0000")
check(r1.status_code == 401 and r2.status_code == 401, "unbekannter Name und falsche PIN: beide 401")
check(r1.json()["detail"].split("–")[0].strip() == r2.json()["detail"].split("–")[0].strip(),
      "gleiche Meldung vorne - nichts verraten, ob es den Namen gibt")
JETZT[0] += 3600
for _ in range(5):
    login("gibtsnicht", "0000")
check(login("gibtsnicht", "0000").status_code == 429, "auch fuer erfundene Namen greift die Drosselung")

# --- Konto ohne PIN bleibt, wie es war --------------------------------------------------------------------
JETZT[0] += 3600
r = login("Dora", "0000")
check(r.status_code == 403 and "Trainer" in r.json()["detail"], "Konto ohne PIN: weiter 403 mit Hinweis auf den Trainer")

# --- Verteiltes Raten: viele Adressen, ein Name ----------------------------------------------------------------
JETZT[0] += 3600
c = db.verbinde()
for i in range(20):
    db.login_fehlschlag(c, 1, f"10.0.0.{i}", "Cora", JETZT[0])
check(db.login_wartezeit(c, 1, "10.9.9.9", "Cora", JETZT[0]) > 0, "20 Fehlversuche von 20 Adressen: der NAME wartet, auch fuer neue Adressen")
check(db.login_wartezeit(c, 1, "10.9.9.9", "Bea", JETZT[0]) == 0, "andere Namen sind davon nicht betroffen")
check(db.login_wartezeit(c, 1, "10.9.9.9", "Cora", JETZT[0] + 3601) == 0, "nach einer Stunde ist es vorbei")
c.close()

# --- Eine Adresse probiert viele Namen --------------------------------------------------------------------------
JETZT[0] += 7200
c = db.verbinde()
for i in range(15):
    db.login_fehlschlag(c, 1, "203.0.113.7", f"name{i}", JETZT[0])
check(db.login_wartezeit(c, 1, "203.0.113.7", "Anna", JETZT[0]) > 0, "15 Fehlversuche mit 15 Namen: die ADRESSE wartet")
check(db.login_wartezeit(c, 1, "203.0.113.8", "Anna", JETZT[0]) == 0, "andere Adressen sind frei")
check(db.login_wartezeit(c, 1, "203.0.113.7", "Anna", JETZT[0] + 901) == 0, "nach 15 Minuten ist es vorbei")

# --- Wartezeit-Rechnung genau ---------------------------------------------------------------------------------------
t0 = JETZT[0] + 100000
for k in range(5):
    db.login_fehlschlag(c, 1, "198.51.100.1", "Eva", t0 + k * 10)   # 5 Fehler im Abstand von 10 s
w = db.login_wartezeit(c, 1, "198.51.100.1", "Eva", t0 + 40)
check(w == 860, f"Wartezeit = bis der aelteste der 5 Fehler das 15-Minuten-Fenster verlaesst (erwartet 860 s, ist {w})")
check(db.login_wartezeit(c, 1, "198.51.100.1", "Eva", t0 + 899) == 1, "eine Sekunde vor Ablauf: noch 1 s")
check(db.login_wartezeit(c, 1, "198.51.100.1", "Eva", t0 + 900) == 0, "genau nach 15 Minuten frei")

# --- Mandanten ------------------------------------------------------------------------------------------------------
for _ in range(5):
    db.login_fehlschlag(c, 2, "192.0.2.5", "Fay", t0)
check(db.login_wartezeit(c, 2, "192.0.2.5", "Fay", t0 + 1) > 0, "Team 2: gesperrt")
check(db.login_wartezeit(c, 1, "192.0.2.5", "Fay", t0 + 1) == 0, "Team 1 sieht Fehlversuche aus Team 2 nicht")

# --- Aufraeumen ----------------------------------------------------------------------------------------------------
db.login_fehlschlag(c, 1, "192.0.2.9", "alt", t0 - 10000)
db.login_fehlschlag(c, 1, "192.0.2.9", "neu", t0)            # loest das Aufraeumen aus
reste = [r["name"] for r in c.execute("SELECT name FROM login_versuche WHERE ip = '192.0.2.9'")]
check(reste == ["neu"], "Eintraege aelter als 2 Stunden werden beim naechsten Fehlversuch geloescht")
c.close()

# --- Adresse aus Anfrage (hinter dem Funnel kommt alles von 127.0.0.1) ------------------------------------------------
check(db.client_ip("127.0.0.1", "203.0.113.9") == "203.0.113.9", "Proxy auf demselben Rechner: Adresse aus X-Forwarded-For")
check(db.client_ip("127.0.0.1", "6.6.6.6, 203.0.113.9") == "203.0.113.9", "mehrere Eintraege: der letzte (vom Proxy), nicht der vom Client")
check(db.client_ip("::1", "2001:db8::1") == "2001:db8::1", "IPv6")
check(db.client_ip("192.168.8.50", "6.6.6.6") == "192.168.8.50", "ohne Proxy wird X-Forwarded-For NICHT geglaubt (laesst sich faelschen)")
check(db.client_ip("127.0.0.1", "kein-ip") == "127.0.0.1", "Unsinn im Header: Rueckfall auf die Verbindungsadresse")
check(db.client_ip("127.0.0.1", None) == "127.0.0.1", "ohne Header: Verbindungsadresse")
check(db.client_ip(None, None) == "unbekannt", "ganz ohne Angabe: 'unbekannt'")

print("\nalles ok")
