"""Einmal-Migration: 'Taktik generell' wird aufgebaut wie 'Allgemeine Spielzuege'.

Ausgangslage: die Playbook-Seite 'Taktik generell' enthaelt einen langen Text
'6:0 Grundprinzipien' mit drei Abschnitten '**Prinzip N: ...**'.

Danach:

    Playbook
      Taktik generell              (reine Gruppe, wie 'Allgemeine Spielzuege')
        - Aktives Verschieben                       **Abwehr:** 6:0
        - Abstimmung IR/IL und HR/HL                **Abwehr:** 6:0
        - Unterbrechung des Angriffsspiels          **Abwehr:** 6:0
      ...

Wie `migrate_spielzuege.py`: arbeitet auf dem Stand, den es vorfindet, stellt
nichts wieder her und ist idempotent - hat 'Taktik generell' schon Unterseiten,
passiert nichts mehr.

CLI:
  py migrate_taktik.py --dry-run      # nur zeigen, was passieren wuerde
  py migrate_taktik.py                # ausfuehren (elo.db der App)
  py migrate_taktik.py --db pfad.db   # andere DB
"""

from __future__ import annotations

import argparse
import re
import sys

import db

GRUPPE = "Taktik generell"

# Ueberschrift des Quelltexts -> Titel der eigenen Seite. Was hier nicht steht,
# bekommt den Text hinter 'Prinzip N:' als Titel.
TITEL = {
    "Das aktive Verschieben": "Aktives Verschieben",
    "Abstimmung zwischen IR/IL und HR/HL": "Abstimmung IR/IL und HR/HL",
}

# Steht als erste Zeile auf jeder neuen Seite (wie '**Gegen:** 6:0' bei den
# Spielzuegen) - der Kontext '6:0 Grundprinzipien' geht sonst verloren.
KOPF = "**Abwehr:** 6:0"

PRINZIP = re.compile(r"^\s*\**\s*Prinzip\s*\d+\s*:\s*(.*?)\s*\**\s*$")


def _norm(s: str) -> str:
    return (s or "").strip().lower()


def _finde(conn, kategorie: str, titel: str):
    """Seite einer Kategorie per Titel (case-insensitive), sonst None."""
    for r in conn.execute("SELECT * FROM seiten WHERE kategorie = ?", (kategorie,)):
        if _norm(r["titel"]) == _norm(titel):
            return dict(r)
    return None


def zerlege(markdown: str) -> list[tuple[str, str]]:
    """(Titel, Inhalt) je '**Prinzip N: ...**'-Abschnitt, in Reihenfolge."""
    teile: list[tuple[str, list[str]]] = []
    for zeile in (markdown or "").splitlines():
        m = PRINZIP.match(zeile)
        if m:
            teile.append((m.group(1), []))
        elif teile:
            teile[-1][1].append(zeile.rstrip())
    raus = []
    for ueberschrift, zeilen in teile:
        titel = TITEL.get(ueberschrift, ueberschrift)
        text = "\n".join(zeilen).strip()
        raus.append((titel, (KOPF + "\n\n" + text).strip()))
    return raus


def migriere(conn, dry: bool) -> list[str]:
    log: list[str] = []

    def tue(text: str, sql: str | None = None, params: tuple = ()):
        log.append(("[dry] " if dry else "") + text)
        if not dry and sql:
            conn.execute(sql, params)

    seite = _finde(conn, "playbook", GRUPPE)
    if seite is None:
        log.append(f"'{GRUPPE}' im Playbook nicht gefunden - nichts zu tun.")
        return log

    if conn.execute("SELECT 1 FROM seiten WHERE parent_id = ? LIMIT 1",
                    (seite["id"],)).fetchone():
        log.append(f"'{GRUPPE}' hat bereits Unterseiten - nichts zu tun.")
        return log

    abschnitte = zerlege(seite.get("markdown") or "")
    if not abschnitte:
        log.append(f"Keine '**Prinzip N: ...**'-Abschnitte in '{GRUPPE}' gefunden "
                   "- nichts zu tun.")
        return log

    for i, (titel, md) in enumerate(abschnitte):
        tue(f"Unterseite '{titel}' ({len(md)} Zeichen)")
        if not dry:
            db.seite_anlegen(conn, titel, "playbook", parent_id=seite["id"],
                             markdown=md, sortierung=i)

    tue(f"'{GRUPPE}' wird reine Gruppe (Text steht jetzt in den Unterseiten)",
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
