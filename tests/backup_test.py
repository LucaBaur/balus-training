"""Tests fuer backup.py: taegliche Sicherung der elo.db mit Aufbewahrungsregel.

Laeuft gegen temporaere Dateien - die echte elo.db bleibt unberuehrt.
Start:  py tests/backup_test.py
"""
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import backup  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="backup_test_"))
JETZT = datetime(2026, 11, 18, 3, 10)          # ein Mittwoch


def neue_quelle(name="quelle.db"):
    p = tmp / name
    c = sqlite3.connect(p)
    c.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, x TEXT)")
    c.executemany("INSERT INTO t (x) VALUES (?)", [("a",), ("b",), ("c",)])
    c.commit()
    c.close()
    return p


# ---------------------------------------------------------------- sichern ----
quelle = neue_quelle()
ziel = tmp / "ziel"
datei = backup.sichern(quelle, ziel, JETZT)
assert datei.name == "elo-20261118-0310.db", datei.name
assert datei.parent == ziel and datei.exists()
c = sqlite3.connect(datei)
assert c.execute("SELECT count(*) FROM t").fetchone()[0] == 3
assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
c.close()
assert not list(ziel.glob("*.tmp")), "keine halbfertige Datei zurueckbleiben"
print("ok sichern: Datei mit Inhalt, integrity ok, kein .tmp")

# Zweimal in derselben Minute (z. B. manueller Lauf) ueberschreibt ohne Fehler
backup.sichern(quelle, ziel, JETZT)
assert len(list(ziel.glob("elo-*.db"))) == 1
print("ok sichern: derselbe Zeitpunkt ist idempotent")

# Die Quelle wird nur gelesen: Aenderungszeit und Inhalt bleiben
vorher = quelle.read_bytes()
backup.sichern(quelle, ziel, JETZT + timedelta(minutes=5))
assert quelle.read_bytes() == vorher
print("ok sichern: Quelle unveraendert")

# Fehlende Quelle: Fehler, und es entsteht KEINE leere Datenbank (sqlite3.connect legt sonst eine an)
fehlt = tmp / "gibt_es_nicht.db"
try:
    backup.sichern(fehlt, ziel, JETZT + timedelta(days=1))
    raise SystemExit("FEHLER: fehlende Quelle haette einen Fehler werfen muessen")
except FileNotFoundError:
    pass
assert not fehlt.exists(), "die Quelle darf nicht als leere DB neu entstehen"
assert not (ziel / "elo-20261119-0310.db").exists()
print("ok sichern: fehlende Quelle -> Fehler, nichts angelegt")

# Kaputte Quelle: Fehler und keine halbe Sicherung
kaputt = tmp / "kaputt.db"
kaputt.write_bytes(b"das ist keine sqlite-datenbank" * 50)
try:
    backup.sichern(kaputt, ziel, JETZT + timedelta(days=2))
    raise SystemExit("FEHLER: kaputte Quelle haette einen Fehler werfen muessen")
except sqlite3.DatabaseError:
    pass
assert not (ziel / "elo-20261120-0310.db").exists() and not list(ziel.glob("*.tmp"))
print("ok sichern: kaputte Quelle -> Fehler, keine halbe Datei")


# ------------------------------------------------------------- Aufbewahrung ----
def name(tage_zurueck, stunde=3):
    t = (JETZT - timedelta(days=tage_zurueck)).replace(hour=stunde, minute=10)
    return t.strftime("elo-%Y%m%d-%H%M.db")


# 100 Tage lang jede Nacht eine Sicherung
alle = [name(t) for t in range(0, 100)]
weg = set(backup.zu_loeschen(alle, JETZT))
behalten = [n for n in alle if n not in weg]

assert all(name(t) in behalten for t in range(0, 14)), "die letzten 14 Tage bleiben alle"
print("ok Aufbewahrung: 14 Tage vollstaendig")

aelter = [n for n in behalten if n not in {name(t) for t in range(0, 14)}]
wochen = {backup.datum_aus_name(n).isocalendar()[:2] for n in aelter}
assert len(aelter) == len(wochen), "aus aelteren Wochen bleibt je Woche genau eine"
assert 7 <= len(aelter) <= 8, f"etwa 8 Wochen Rueckblick, nicht {len(aelter)}"
print(f"ok Aufbewahrung: {len(aelter)} Wochenstaende dahinter")

assert name(99) in weg and name(90) in weg, "nach ca. 8 Wochen wird geloescht"
assert name(0) not in weg, "die neueste Sicherung wird nie geloescht"
print("ok Aufbewahrung: Altes weg, Neueste nie")

# Je Woche bleibt die NEUESTE
wochenstand = {}
for n in alle:
    d = backup.datum_aus_name(n)
    if (JETZT - d).days >= 14:
        wochenstand.setdefault(d.isocalendar()[:2], []).append(n)
for w, namen in wochenstand.items():
    if any(n in behalten for n in namen):
        assert max(namen) in behalten, f"Woche {w}: nicht die neueste behalten"
print("ok Aufbewahrung: je Woche die neueste")

# Fremde Dateien und kaputte Namen fasst die Regel nie an
fremd = ["notiz.txt", "elo-kaputt.db", "elo-20261118.db", "andere-20200101-0310.db"]
assert backup.zu_loeschen(fremd + [name(0)], JETZT) == []
print("ok Aufbewahrung: fremde Namen unberuehrt")

# Eine einzige Sicherung (auch uralt) bleibt: lieber zu viel als gar keine
assert backup.zu_loeschen([name(400)], JETZT) == []
print("ok Aufbewahrung: die einzige Sicherung bleibt")

# Idempotent
rest = [n for n in alle if n not in weg]
assert backup.zu_loeschen(rest, JETZT) == []
print("ok Aufbewahrung: zweiter Lauf loescht nichts mehr")


# ----------------------------------------------------------------- aufraeumen ----
ordner = tmp / "rotation"
ordner.mkdir()
for n in alle[:60]:
    (ordner / n).write_bytes(b"x")
(ordner / "notiz.txt").write_text("bleibt")
geloescht = backup.aufraeumen(ordner, JETZT)
uebrig = {p.name for p in ordner.iterdir()}
assert "notiz.txt" in uebrig
assert name(0) in uebrig and name(13) in uebrig
assert geloescht == len([n for n in alle[:60] if n in set(backup.zu_loeschen(alle[:60], JETZT))])
assert not (set(alle[:60]) - uebrig) - set(backup.zu_loeschen(alle[:60], JETZT))
print("ok aufraeumen: loescht nur, was die Regel nennt")

print("\nalles ok")
