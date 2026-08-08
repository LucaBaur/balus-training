"""Einmal-Migration 2/2: jeder Spielzug bekommt eine eigene Seite.

Ausgangslage (nach `migrate_playbook.py` und der Handarbeit in der App):
die Seite 'Allgemein' im Playbook enthaelt eine Liste aller Spielzuege,
gegliedert nach 'Gegen 6:0' und 'Gegen 5:1'.

Danach:

    Playbook
      ...
      Allgemeine Spielzuege        (umbenannt von 'Allgemein', reine Gruppe)
        - Jugo
        - Kreisel
        - Goran
        - Auftakt
        - X?
        - Jugo-Loevgren            **Gegen:** 6:0
        - Iso halb                 **Gegen:** 6:0
        - 4                        **Gegen:** 6:0
      ...
      Offensive Abwehr             + Abschnitt 'Gegen 5:1' (5:1 ist eine
                                     offensive Abwehr)

Das Skript arbeitet auf dem STAND, DEN ES VORFINDET: es verschiebt und legt
an, aber es stellt nichts wieder her, was in der App geloescht wurde, und es
verschiebt keine Seite, die schon woanders eingehaengt ist. Idempotent - ein
zweiter Lauf sieht die Unterseiten und macht nichts mehr.

CLI:
  py migrate_spielzuege.py --dry-run      # nur zeigen, was passieren wuerde
  py migrate_spielzuege.py                # ausfuehren (elo.db der App)
  py migrate_spielzuege.py --db pfad.db   # andere DB
"""

from __future__ import annotations

import argparse
import re
import sys

import db

ALT_TITEL = "Allgemein"
NEU_TITEL = "Allgemeine Spielzüge"

# (Titel der neuen Seite, Zeile aus der alten Liste, Abwehr, gegen die er laeuft)
SPIELZUEGE = [
    ("Jugo",         "Jugo",               None),
    ("Kreisel",      "Kreisel",            None),
    ("Goran",        "Goran",              None),
    ("Auftakt",      "Auftakt",            None),
    ("X?",           "X?",                 None),
    ("Jugo-Lövgren", "Jugo-Lövgren",       "6:0"),
    ("Iso halb",     "Iso halb zieht weg", "6:0"),
    ("4",            "4",                  "6:0"),
]

# Abschnitte, die auf eine andere Seite gehoeren: 5:1 ist eine offensive Abwehr.
ABSCHNITT_UMZUG = {"Gegen 5:1": "Offensive Abwehr"}

# Reihenfolge der obersten Playbook-Ebene. Seiten, die hier nicht stehen,
# haengen hinten dran (in ihrer bisherigen Reihenfolge).
PLAYBOOK_REIHENFOLGE = [
    "Taktik generell",
    "Absprache-Frauen",
    NEU_TITEL,
    "Überzahl",
    "Unterzahl",
    "Offensive Abwehr",
]


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _finde(conn, kategorie: str, titel: str):
    """Seite einer Kategorie per Titel (case-insensitive), sonst None."""
    for r in conn.execute("SELECT * FROM seiten WHERE kategorie = ?", (kategorie,)):
        if _norm(r["titel"]) == _norm(titel):
            return dict(r)
    return None


def abschnitt(markdown: str, name: str) -> str:
    """Den '### <name>'-Abschnitt inklusive Ueberschrift herausziehen."""
    raus: list[str] = []
    drin = False
    for zeile in (markdown or "").splitlines():
        m = re.match(r"^#{2,4}\s+(.*?):?\s*$", zeile)
        if m:
            drin = _norm(m.group(1)) == _norm(name)
            if drin:
                raus.append(zeile.rstrip())
            continue
        if drin:
            raus.append(zeile.rstrip())
    return "\n".join(raus).strip()


def seiten_text(titel: str, original: str, gegen: str | None) -> str | None:
    """Startinhalt einer Spielzug-Seite. Ohne Zusatzinfo bleibt sie leer -
    dann zeigt die App 'leer' und man sieht, wo noch was zu schreiben ist."""
    teile = []
    if gegen:
        teile.append(f"**Gegen:** {gegen}")
    if _norm(original) != _norm(titel):
        teile.append(f"Aus dem alten Playbook: „{original}“")
    return "\n\n".join(teile) or None


def migriere(conn, dry: bool) -> list[str]:
    log: list[str] = []

    def tue(text: str, sql: str | None = None, params: tuple = ()):
        log.append(("[dry] " if dry else "") + text)
        if not dry and sql:
            conn.execute(sql, params)

    seite = _finde(conn, "playbook", NEU_TITEL) or _finde(conn, "playbook", ALT_TITEL)
    if seite is None:
        log.append(f"Weder '{ALT_TITEL}' noch '{NEU_TITEL}' im Playbook gefunden "
                   "- nichts zu tun.")
        return log

    # 1) Umbenennen (nur wenn noetig).
    if _norm(seite["titel"]) != _norm(NEU_TITEL):
        tue(f"'{seite['titel']}' umbenennen in '{NEU_TITEL}'",
            "UPDATE seiten SET titel=?, aktualisiert=datetime('now') WHERE id=?",
            (NEU_TITEL, seite["id"]))

    # 1b) Seiten, deren Gruppe geloescht wurde, zeigen ins Leere -> sauber auf
    #     die oberste Ebene setzen (die App zeigt sie ohnehin schon dort).
    for r in conn.execute(
            "SELECT s.id, s.titel FROM seiten s LEFT JOIN seiten p ON p.id = s.parent_id "
            "WHERE s.parent_id IS NOT NULL AND p.id IS NULL"):
        tue(f"'{r['titel']}': Gruppe existiert nicht mehr -> oberste Ebene",
            "UPDATE seiten SET parent_id=NULL WHERE id=?", (r["id"],))

    # 1c) Oberste Ebene des Playbooks in eine feste Reihenfolge bringen.
    alle = [dict(r) for r in conn.execute(
        "SELECT id, titel, parent_id, sortierung FROM seiten WHERE kategorie='playbook'")]
    ids = {r["id"] for r in alle}
    oben = [r for r in alle if not r["parent_id"] or r["parent_id"] not in ids]

    def rang(r):
        t = _norm(NEU_TITEL) if _norm(r["titel"]) == _norm(ALT_TITEL) else _norm(r["titel"])
        for i, name in enumerate(PLAYBOOK_REIHENFOLGE):
            if _norm(name) == t:
                return i
        return len(PLAYBOOK_REIHENFOLGE)

    oben.sort(key=lambda r: (rang(r), r["sortierung"], r["titel"]))
    for i, r in enumerate(oben):
        if r["sortierung"] != i:
            tue(f"Reihenfolge: '{r['titel']}' auf Platz {i + 1}",
                "UPDATE seiten SET sortierung=? WHERE id=?", (i, r["id"]))

    # 2) Schon Unterseiten da? Dann ist der Rest bereits passiert.
    if conn.execute("SELECT 1 FROM seiten WHERE parent_id = ? LIMIT 1",
                    (seite["id"],)).fetchone():
        log.append(f"'{NEU_TITEL}' hat bereits Unterseiten - Spielzuege werden "
                   "nicht erneut angelegt.")
        if not dry:
            conn.commit()          # Umbenennen/Reihenfolge oben trotzdem sichern
        return log

    quelle = seite.get("markdown") or ""

    # 3) Abschnitte, die woanders hingehoeren, umziehen (vor dem Leeren!).
    for name, ziel_titel in ABSCHNITT_UMZUG.items():
        text = abschnitt(quelle, name)
        ziel = _finde(conn, "playbook", ziel_titel)
        if not text:
            log.append(f"Abschnitt '{name}' nicht gefunden - nichts umgezogen.")
            continue
        if ziel is None:
            log.append(f"Zielseite '{ziel_titel}' gibt es nicht - '{name}' bleibt stehen.")
            continue
        vorher = (ziel.get("markdown") or "").rstrip()
        if text in vorher:
            log.append(f"'{name}' steht schon in '{ziel_titel}'.")
            continue
        tue(f"Abschnitt '{name}' -> '{ziel_titel}' ({len(text)} Zeichen)",
            "UPDATE seiten SET markdown=?, aktualisiert=datetime('now') WHERE id=?",
            ((vorher + "\n\n" + text).strip(), ziel["id"]))

    # 4) Je Spielzug eine Unterseite.
    for i, (titel, original, gegen) in enumerate(SPIELZUEGE):
        md = seiten_text(titel, original, gegen)
        tue(f"Spielzug '{titel}'" + (f" (gegen {gegen})" if gegen else "") +
            (" - mit Notiz" if md and not gegen else ""))
        if not dry:
            db.seite_anlegen(conn, titel, "playbook", parent_id=seite["id"],
                             markdown=md, sortierung=i)

    # 5) Die Liste selbst wird nicht mehr gebraucht - sie steckt in den Seiten.
    tue(f"'{NEU_TITEL}' wird reine Gruppe (Liste steht jetzt in den Unterseiten)",
        "UPDATE seiten SET markdown=NULL, aktualisiert=datetime('now') WHERE id=?",
        (seite["id"],))

    if not dry:
        conn.commit()
    return log


def zeige_baum(conn) -> None:
    zeilen = [dict(r) for r in conn.execute(
        "SELECT id, titel, parent_id, sortierung, "
        "length(COALESCE(markdown,'')) AS n FROM seiten "
        "WHERE kategorie='playbook' ORDER BY sortierung, titel")]
    ids = {z["id"] for z in zeilen}

    def stufe(eltern, tiefe):
        for z in zeilen:
            oben = z["parent_id"] if z["parent_id"] in ids else None
            if oben == eltern:
                print("  " * (tiefe + 1) + f"- {z['titel']} ({z['n']} Zeichen)")
                stufe(z["id"], tiefe + 1)

    stufe(None, 0)


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="nichts schreiben, nur zeigen")
    ap.add_argument("--db", help="Ziel-SQLite (Default: elo.db der App)")
    args = ap.parse_args()

    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)
    for zeile in migriere(conn, args.dry_run):
        print(" ", zeile)
    print("\nPlaybook danach:")
    zeige_baum(conn)
    conn.close()
    if args.dry_run:
        print("\nDry-Run beendet - es wurde nichts geschrieben.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _cli()
