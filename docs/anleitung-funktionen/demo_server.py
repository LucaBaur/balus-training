"""Startet Balu's Training mit ERFUNDENEN Demo-Daten (für Screenshots der Anleitung).

Nichts davon berührt die echte App: temporäre Datenbank, eigener Session-Schlüssel,
eigener Medienordner, Liga-Daten aus der Beispieldatei (kein Netz). Die Namen sind frei
erfunden und kommen bewusst nicht in static/portraits/index.json vor, damit keine
echten Fotos auftauchen.

Start:   py docs/anleitung-funktionen/demo_server.py          (Port 8299)
Logins:  Trainer / 1111      Lena / 2222 (Spielerin)
"""
from __future__ import annotations

import json
import os
import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

os.environ["APP_SECRET"] = "nur-fuer-die-anleitung"
BASIS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASIS))

import app as balu  # noqa: E402
import auth  # noqa: E402
import db  # noqa: E402
import liga  # noqa: E402
import trainings_termine  # noqa: E402

PORT = 8299
tmp = Path(tempfile.mkdtemp(prefix="balu_demo_"))
DB = tmp / "demo.db"
balu.MEDIA_CLIPS = tmp / "clips"
balu.MEDIA_CLIPS.mkdir()
balu.MEDIA_SPIELE = tmp / "spiele"
balu.MEDIA_SPIELE.mkdir()
_verbinde = db.verbinde
db.verbinde = lambda pfad=DB: _verbinde(pfad)

# Liga: gespeicherte Antwort der Verbands-Schnittstelle statt Netzabruf
_ROH = json.loads((BASIS / "tests" / "liga_beispiel.json").read_text(encoding="utf-8"))
liga.hole_roh = lambda: _ROH
liga.CACHE_DATEI = tmp / "liga_cache.json"

HEUTE = date.today()

# (Name, Stufe, grobe Position, Angriffsposition)
KADER = [
    ("Mia", "stark", "Tor", "Tor"), ("Nora", "mittel", "Tor", "Tor"),
    ("Ida", "mittel", "Feld", "Linksaußen"), ("Zoe", "stark", "Feld", "Rechtsaußen"),
    ("Lena", "stark", "Feld", "Halblinks"), ("Paula", "mittel", "Feld", "Halblinks"),
    ("Sophie", "stark", "Feld", "Mitte"), ("Clara", "mittel", "Feld", "Mitte"),
    ("Jule", "mittel", "Feld", "Halbrechts"), ("Emma", "schwach", "Feld", "Halbrechts"),
    ("Greta", "mittel", "Feld", "Kreis"), ("Vera", "schwach", "Feld", "Kreis"),
    ("Pia", "mittel", "Feld", "Rechtsaußen"), ("Romy", "schwach", "Feld", "Linksaußen"),
    ("Tilda", "mittel", "Feld", "Mitte"), ("Ella", "schwach", "Feld", "Halblinks"),
]


def seed() -> dict:
    rnd = random.Random(7)
    conn = db.verbinde()
    db.init_db(conn)

    ids = {}
    for name, stufe, pos, angriff in KADER:
        sid = db.spieler_anlegen(conn, name, stufe=stufe, position=pos)
        db.spieler_aktualisieren(conn, sid, position_angriff=angriff)
        ids[name] = sid
    alle = list(ids.values())

    # Benutzer: 1 Trainer (ohne Profil) + Spielerinnen mit Zugang
    db.benutzer_anlegen(conn, "Trainer", "trainer", auth.hash_pin("1111"))
    for name in ("Lena", "Mia", "Sophie", "Zoe", "Ida", "Greta", "Paula", "Jule"):
        pin = "2222" if name == "Lena" else "3333"
        db.benutzer_anlegen(conn, name, "spieler", auth.hash_pin(pin), ids[name])

    # Vergangene Trainings (Quote) und Trainingsspiele (ELO)
    vergangen = []
    d = HEUTE - timedelta(days=1)
    while len(vergangen) < 10:
        if d.weekday() in (0, 3):
            vergangen.append(d)
        d -= timedelta(days=1)
    for d in sorted(vergangen):
        tid, _ = db.training_anlegen(
            conn, d.isoformat(), "Training " + ("Gerhausen" if d.weekday() == 0 else "Blaubeuren"),
            uhrzeit="20:00" if d.weekday() == 0 else "20:15",
            ort="Gerhausen" if d.weekday() == 0 else "Blaubeuren")
        anwesend = [s for s in alle if rnd.random() < 0.82]
        if d in vergangen[-3:-1] and ids["Lena"] in anwesend:   # Lena fehlt zweimal (realistischere Quote)
            anwesend.remove(ids["Lena"])
        for s in alle:
            db.teilnahme_setzen(conn, tid, s, "anwesend" if s in anwesend else "abgesagt",
                                None if s in anwesend else "Arbeit", quelle="spielerplus")
        if len(anwesend) >= 10:
            rnd.shuffle(anwesend)
            h = len(anwesend) // 2
            db.spiel_eintragen(conn, anwesend[:h], anwesend[h:h * 2],
                               rnd.choice(["A", "B", "A", "B", "U"]),
                               datum=d.isoformat())

    # Test- und Ligaspiele
    db.training_anlegen(conn, (HEUTE + timedelta(days=3)).isoformat(), "Heimspiel",
                        uhrzeit="19:30", ort="Sporthalle Gerhausen", art="ligaspiel",
                        gegner="HSG Beispielstadt", heim=1)
    db.training_anlegen(conn, (HEUTE + timedelta(days=11)).isoformat(), "Auswärtsspiel",
                        uhrzeit="17:00", ort="Halle Musterdorf", art="ligaspiel",
                        gegner="SG Muster", heim=0, abfahrt="15:30")

    # Kommende Trainings aus dem Wochenmuster (wie auf dem Server)
    trainings_termine.anlegen(conn, HEUTE, HEUTE + timedelta(days=14))
    conn.commit()
    kommende = [r["id"] for r in conn.execute(
        "SELECT id FROM trainings WHERE datum >= ? ORDER BY datum, id",
        (HEUTE.isoformat(),))]
    gruende = ["Arbeit", "Krank", "Prüfung", "Familienfeier", "Verletzt", "Im Urlaub"]
    for n, tid in enumerate(kommende):
        for name in ids:
            if name == "Lena" and n == 0:
                continue                       # Lena hat noch nicht geantwortet (für Screenshot)
            w = rnd.random()
            if w < 0.62:
                st, grund = "anwesend", None
            elif w < 0.72:
                st, grund = "unsicher", None
            elif w < 0.88 or (n == 0 and name in ("Ella", "Vera", "Romy")):
                st, grund = "abgesagt", rnd.choice(gruende)
            else:
                continue                       # noch offen
            quelle = rnd.choice(["app", "app", "spielerplus", "spielerplus", "trainer"])
            db.teilnahme_setzen(conn, tid, ids[name], st, grund, quelle=quelle)

    # Plan fürs nächste Training
    db.plan_bloecke_setzen(conn, kommende[0], [
        {"dauer_min": 15, "titel": "Aufwärmen mit Ball", "notiz": "Passen im Dreieck, dann Torwurf aus dem Lauf"},
        {"dauer_min": 20, "titel": "Wurfserien", "notiz": "Alle Positionen, Torhüterinnen einwerfen"},
        {"dauer_min": 25, "titel": "2. Welle", "notiz": "Schnelle Mitte, Außen laufen früh los"},
        {"dauer_min": 20, "titel": "Abschlussspiel 6:6", "notiz": "Teams per Einteilung"},
        {"dauer_min": 10, "titel": "Auslaufen & Besprechung", "notiz": ""},
    ])

    # Wiki: Playbook, Übungen, Gegner, Orga, Notizen, Statistik
    s = db.seite_anlegen
    gruppe = s(conn, "Allgemeine Spielzüge", "playbook", markdown="Unsere Standard-Auslösehandlungen.")
    s(conn, "Kreisel", "playbook", parent_id=gruppe, markdown=(
        "**Gegen:** 6:0\n\n1. Mitte spielt auf Halblinks\n2. Halblinks geht in die Lücke\n"
        "3. Kreis sperrt, Halbrechts schließt ab\n\n*Achtung:* Außen früh anlaufen."))
    s(conn, "Auftakt", "playbook", parent_id=gruppe, markdown="Schneller Anwurf, Mitte und Halblinks kreuzen.")
    s(conn, "Doppelkreuz", "playbook", parent_id=gruppe, markdown="Zwei Kreuzbewegungen hintereinander.")
    s(conn, "Überzahl", "playbook", markdown="Breit aufstellen, Ball laufen lassen, Kreis anspielen.")
    s(conn, "Unterzahl", "playbook", markdown="Kompakt stehen, Passwege zustellen, Tempo rausnehmen.")
    s(conn, "Offensive Abwehr", "playbook", markdown="Halbe stehen vorn, Außen schieben mit.")
    for titel, text in (("Erwärmung mit Ball", "Dreiecksspiel, 10 Minuten."),
                        ("Konterspiele", "Von der Abwehr direkt in die erste Welle."),
                        ("2. Welle", "Mitte und Außen laufen nach dem Torwurf sofort los."),
                        ("Abschlussspiel 6:6", "Mit Punktewertung für schnelle Tore.")):
        s(conn, titel, "uebung", markdown=text)
    s(conn, "HSG Beispielstadt", "gegner", markdown="**Abwehr:** 6:0, steht tief.\n\n**Gefährlich:** Rückraum links, Wurf aus dem Stand.")
    s(conn, "Saison 26/27", "orga", markdown="Hallenzeiten: Montag Gerhausen, Donnerstag Blaubeuren.")
    s(conn, "Besprechung Oktober", "notiz", markdown="Fokus: Tempospiel und Kreisanspiel.")
    s(conn, "Wurfstatistik Herbst", "statistik", markdown="Quote Rückraum 41 %, Außen 58 %, Kreis 66 %.")

    # Spielanalyse (ohne Video-Datei)
    z = ids
    events = []
    t = 60.0
    for typ, wer, assist in [
            ("tor", "Lena", "Sophie"), ("tor", "Zoe", None), ("fehlwurf", "Jule", None),
            ("tor", "Greta", "Clara"), ("ballverlust", "Emma", None), ("tor", "Lena", None),
            ("parade", "Mia", None), ("tor", "Zoe", "Lena"), ("fehlwurf", "Lena", None),
            ("ballverlust", "Sophie", None), ("tor", "Sophie", None), ("parade", "Mia", None),
            ("strafe", "Vera", None), ("tor", "Pia", "Ida"), ("fehlwurf", "Greta", None)]:
        t += rnd.uniform(70, 180)
        events.append({"typ": typ, "t": round(t, 1), "spieler_id": z[wer],
                       "assist_id": z[assist] if assist else None, "key": f"e{len(events)}"})
    zuege = [
        {"name": "Kreisel", "t_start": 200, "t_ende": 214, "ampel": "gruen",
         "spieler_ids": [z["Sophie"], z["Lena"], z["Greta"]], "key": "z1"},
        {"name": "Auftakt", "t_start": 640, "t_ende": 652, "ampel": "orange",
         "kommentar": "Timing stimmt noch nicht, Außen läuft zu spät los.",
         "spieler_ids": [z["Sophie"], z["Zoe"]], "key": "z2"},
        {"name": "Doppelkreuz", "t_start": 1210, "t_ende": 1224, "ampel": "rot",
         "kommentar": "Fehlpass am Kreis, Ballverlust zum Gegenstoß.",
         "spieler_ids": [z["Lena"], z["Greta"], z["Emma"]], "key": "z3"},
        {"name": "Kreisel", "t_start": 1900, "t_ende": 1912, "ampel": "gruen",
         "spieler_ids": [z["Lena"], z["Sophie"], z["Jule"]], "key": "z4"},
    ]
    trainer_id = db.benutzer_nach_name(conn, "Trainer")["id"]
    aid = db.analyse_speichern(conn, "demo-spiel-1", "HSG Beispielstadt",
                         (HEUTE - timedelta(days=9)).isoformat(), "Liga", events, zuege, trainer_id)
    (balu.MEDIA_SPIELE / "demo-spiel-1.mp4").write_bytes(bytes(2048))    # Platzhalter, wird nicht abgespielt
    db.analyse_datei_setzen(conn, aid, "demo-spiel-1.mp4")

    # Zwei Szenen-Clips (Platzhalterdateien, in der Liste zählt nur der Eintrag)
    for n, (titel, notiz, wer) in enumerate([
            ("Tempogegenstoß 1. Halbzeit", "Mitte läuft früh an, Außen startet sofort.", ["Lena", "Zoe"]),
            ("Kreisanspiel gegen 6:0", "Sperre am Kreis sauber gestellt.", ["Greta", "Sophie"])]):
        datei = f"demo-{n}.mp4"
        (balu.MEDIA_CLIPS / datei).write_bytes(bytes(1024))
        db.clip_anlegen(conn, titel, notiz, datei, (HEUTE - timedelta(days=9)).isoformat(),
                        12.0, trainer_id, [ids[w] for w in wer])

    # Nutzung: ein paar Besuche, damit die Nutzungsseite etwas zeigt
    for i, name in enumerate(("Lena", "Mia", "Sophie", "Zoe", "Ida", "Greta")):
        bid = db.benutzer_nach_name(conn, name)["id"]
        db.nutzung_speichern(conn, bid, [{"typ": "besuch"}, {"typ": "bereich", "ziel": "training/trainings"},
                                         {"typ": "bereich", "ziel": "taktik/playbook"}])
        db.geraet_speichern(conn, bid, {"os": "Android 14" if i % 2 else "iOS 18", "browser": "Chrome 130" if i % 2 else "Safari 18",
                                        "modus": "installiert", "bildschirm": "390x844", "app_version": "v0.55.0", "sw": True})
        conn.execute("UPDATE nutzung SET zeit = datetime('now', ?) WHERE benutzer_id = ?",
                     (f"-{i * 9 + 1} hours", bid))
    conn.commit()
    conn.close()
    return ids


if __name__ == "__main__":
    import uvicorn
    seed()
    print(f"Demo-Instanz läuft auf http://127.0.0.1:{PORT}  (Trainer/1111, Lena/2222)", flush=True)
    uvicorn.run(balu.app, host="127.0.0.1", port=PORT, log_level="warning")
