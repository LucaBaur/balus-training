"""Einmal-Migration 1/2: Playbook entflechten (gelaufen am 2026-07-23).

!!! NICHT ERNEUT AUSFUEHREN !!!
Das Skript stellt eine Zielstruktur her und wuerde dabei Seiten neu anlegen,
die inzwischen bewusst in der App geloescht oder umbenannt wurden. Seit dem
Umbau ist die App die Wahrheit fuer die Struktur; Aenderungen macht man dort
(Trainer: „＋ Neue Seite" / „✏️ Bearbeiten" / „🗑 Löschen").
Die Datei bleibt als Protokoll dessen liegen, was damals passiert ist.
Der zweite Schritt (Spielzuege einzeln) steckt in `migrate_spielzuege.py`.

Vorher war das Playbook eine flache Liste, in der auch Uebungs-Kategorien
lagen und alle Spielzuege in EINER Sammelseite standen.

Nachher:

    Playbook
      1. Taktik generell        (bestehende Seite 'Taktik-Generell')
      2. Absprache-Frauen       (neu)
      3. Spielzuege             (Gruppe)
           - Allgemein          <- Abschnitt 'Angriff-Normal' der Sammelseite
           - Ueberzahl          <- Abschnitt 'Angriff-Ueberzahl'
           - Unterzahl          <- Abschnitt 'Angriff-Unterzahl'
           - Offensive Abwehr   (neu, leer)

    Uebungen  (dorthin verschoben, es sind Uebungs-Kategorien)
      2te Welle, Innenblock, Abschlussspiele, Konterspiele, Taktikschulung

Die alte Sammelseite 'Playbook' wurde nicht geloescht, sondern als 'archiv'
weggelegt (taucht in keiner Ansicht mehr auf, bleibt in der DB nachlesbar).

CLI:
  py migrate_playbook.py --dry-run      # nur zeigen, was passieren wuerde
  py migrate_playbook.py --db pfad.db   # andere DB
"""

from __future__ import annotations

import argparse
import re
import sys

import db

# Titel, die aus dem Playbook zu den Uebungen wandern -> Zieltitel.
NACH_UEBUNGEN = {
    "2te welle": "2te Welle",
    "innenblock": "Innenblock",
    "abschlusspiele": "Abschlussspiele",     # Tippfehler im Original
    "abschlussspiele": "Abschlussspiele",
    "konterspiele": "Konterspiele",
    "taktikschulung": "Taktikschulung",
}

# Abschnitt der alten Sammelseite -> Titel der neuen Unterseite.
SPIELZUG_ABSCHNITTE = {
    "angriff-normal": "Allgemein",
    "angriff-ueberzahl": "Überzahl",
    "angriff-überzahl": "Überzahl",
    "angriff-unterzahl": "Unterzahl",
}

SPIELZUG_UNTERSEITEN = ["Allgemein", "Überzahl", "Unterzahl", "Offensive Abwehr"]


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _finde(conn, kategorie: str, titel: str):
    """Seite einer Kategorie per Titel (case-insensitive), sonst None."""
    for r in conn.execute("SELECT * FROM seiten WHERE kategorie = ?", (kategorie,)):
        if _norm(r["titel"]) == _norm(titel):
            return dict(r)
    return None


def teile_sammelseite(markdown: str) -> dict[str, str]:
    """Die alte Playbook-Seite an ihren '## ...'-Ueberschriften aufteilen.
    Liefert {Unterseiten-Titel: Markdown ohne die '##'-Zeile}."""
    if not markdown:
        return {}
    teile: dict[str, list[str]] = {}
    aktuell: list[str] | None = None
    for zeile in markdown.splitlines():
        m = re.match(r"^##\s+(?!#)(.*?)\s*$", zeile)
        if m:
            ziel = SPIELZUG_ABSCHNITTE.get(_norm(m.group(1)))
            aktuell = teile.setdefault(ziel, []) if ziel else None
            continue
        if aktuell is not None:
            aktuell.append(zeile.rstrip())

    fertig = {}
    for titel, zeilen in teile.items():
        text = "\n".join(zeilen).strip()
        # Fuehrende '### Allgemein:'-Zeile weg, wenn sie nur den Seitentitel
        # wiederholt (der steht jetzt ueber der Seite).
        m = re.match(r"^###\s+(.*?):?\s*$", text.split("\n", 1)[0])
        if m and _norm(m.group(1)) == _norm(titel):
            text = text.split("\n", 1)[1].strip() if "\n" in text else ""
        if text:
            fertig[titel] = text
    return fertig


def migriere(conn, dry: bool) -> list[str]:
    log: list[str] = []

    def tue(text: str, sql: str | None = None, params: tuple = ()):
        log.append(("[dry] " if dry else "") + text)
        if not dry and sql:
            conn.execute(sql, params)

    # 1) Uebungs-Kategorien aus dem Playbook zu den Uebungen schieben.
    for r in conn.execute("SELECT id, titel FROM seiten WHERE kategorie = 'playbook'"):
        ziel = NACH_UEBUNGEN.get(_norm(r["titel"]))
        if ziel:
            tue(f"'{r['titel']}' -> Uebungen (als '{ziel}')",
                "UPDATE seiten SET kategorie='uebung', parent_id=NULL, titel=?, "
                "sortierung=0, aktualisiert=datetime('now') WHERE id=?",
                (ziel, r["id"]))

    # 2) Taktik generell an Position 1.
    tg = _finde(conn, "playbook", "Taktik-Generell") or _finde(conn, "playbook", "Taktik generell")
    if tg:
        tue("'Taktik generell' an Position 1",
            "UPDATE seiten SET titel='Taktik generell', parent_id=NULL, sortierung=0 "
            "WHERE id=?", (tg["id"],))
    else:
        tue("'Taktik generell' neu anlegen (leer)")
        if not dry:
            db.seite_anlegen(conn, "Taktik generell", "playbook", sortierung=0)

    # 3) Absprache-Frauen an Position 2.
    af = _finde(conn, "playbook", "Absprache-Frauen")
    if af:
        tue("'Absprache-Frauen' an Position 2",
            "UPDATE seiten SET parent_id=NULL, sortierung=1 WHERE id=?", (af["id"],))
    else:
        tue("'Absprache-Frauen' neu anlegen (leer)")
        if not dry:
            db.seite_anlegen(conn, "Absprache-Frauen", "playbook", sortierung=1)

    # 4) Gruppe 'Spielzuege' an Position 3.
    sz = _finde(conn, "playbook", "Spielzüge")
    if sz:
        tue("Gruppe 'Spielzüge' an Position 3",
            "UPDATE seiten SET parent_id=NULL, sortierung=2 WHERE id=?", (sz["id"],))
        sz_id = sz["id"]
    else:
        tue("Gruppe 'Spielzüge' neu anlegen")
        sz_id = db.seite_anlegen(conn, "Spielzüge", "playbook", sortierung=2) if not dry else -1

    # 5) Die vier Unterseiten sicherstellen.
    kinder: dict[str, int] = {}
    for i, titel in enumerate(SPIELZUG_UNTERSEITEN):
        vorhanden = _finde(conn, "playbook", titel)
        if vorhanden:
            tue(f"Unterseite '{titel}' einhaengen (Position {i + 1})",
                "UPDATE seiten SET parent_id=?, sortierung=? WHERE id=?",
                (sz_id, i, vorhanden["id"]))
            kinder[titel] = vorhanden["id"]
        else:
            tue(f"Unterseite '{titel}' neu anlegen")
            if not dry:
                kinder[titel] = db.seite_anlegen(conn, titel, "playbook",
                                                 parent_id=sz_id, sortierung=i)

    # 6) Alte Sammelseite 'Playbook' aufteilen und archivieren.
    alt = _finde(conn, "playbook", "Playbook")
    if alt:
        abschnitte = teile_sammelseite(alt.get("markdown") or "")
        for titel, md in abschnitte.items():
            kid = kinder.get(titel)
            leer = True
            if kid and not dry:
                r = conn.execute("SELECT markdown FROM seiten WHERE id=?", (kid,)).fetchone()
                leer = not (r and (r["markdown"] or "").strip())
            if not leer:
                log.append(f"'{titel}' hat schon Inhalt -> nicht ueberschrieben")
                continue
            tue(f"Inhalt nach '{titel}' uebernehmen ({len(md)} Zeichen)",
                "UPDATE seiten SET markdown=?, aktualisiert=datetime('now') WHERE id=?",
                (md, kid))
        fehlt = [t for t in SPIELZUG_ABSCHNITTE.values() if t not in abschnitte]
        if fehlt:
            log.append("kein Abschnitt gefunden fuer: " + ", ".join(sorted(set(fehlt))))
        tue("alte Sammelseite 'Playbook' archivieren",
            "UPDATE seiten SET kategorie='archiv', parent_id=NULL, "
            "titel='Playbook (Original vor Umbau)' WHERE id=?", (alt["id"],))

    if not dry:
        conn.commit()
    return log


def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="nichts schreiben, nur zeigen")
    ap.add_argument("--db", help="Ziel-SQLite (Default: elo.db der App)")
    ap.add_argument("--ich-weiss-was-ich-tue", action="store_true",
                    help="Sicherung aushebeln (siehe Warnung im Kopf der Datei)")
    args = ap.parse_args()

    if not args.dry_run and not args.ich_weiss_was_ich_tue:
        print("Dieses Skript ist bereits gelaufen und wuerde geloeschte Seiten\n"
              "wiederherstellen. Nur mit --dry-run ansehen, oder bewusst mit\n"
              "--ich-weiss-was-ich-tue erzwingen.")
        return

    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)
    for zeile in migriere(conn, args.dry_run):
        print(" ", zeile)

    print("\nPlaybook danach:")
    for r in conn.execute(
            "SELECT id, titel, parent_id, sortierung, "
            "length(COALESCE(markdown,'')) AS n FROM seiten "
            "WHERE kategorie='playbook' "
            "ORDER BY COALESCE(parent_id, id), (parent_id IS NOT NULL), sortierung"):
        einzug = "    - " if r["parent_id"] else "  " + str(r["sortierung"] + 1) + ". "
        print(f"{einzug}{r['titel']} ({r['n']} Zeichen)")
    conn.close()
    if args.dry_run:
        print("\nDry-Run beendet - es wurde nichts geschrieben.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _cli()
