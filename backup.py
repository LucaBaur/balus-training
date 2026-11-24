"""Taegliche Sicherung der elo.db mit Aufbewahrungsregel.

Cron (Homeserver, taeglich 03:10 Berlin):
  10 3 * * *   cd /home/luca/elo && /home/luca/anytype-sync/.venv/bin/python backup.py

Was passiert:
  1. Die Datenbank wird mit der SQLite-Backup-API kopiert (konsistent, auch waehrend die App laeuft;
     ein einfaches Kopieren der Datei koennte mitten in einer Schreibaktion passieren).
  2. Die Kopie wird mit `PRAGMA integrity_check` geprueft. Erst danach bekommt sie ihren Namen -
     eine kaputte oder halbe Sicherung liegt nie als "gueltig" im Ordner.
  3. Alte Sicherungen werden ausgeduennt: die letzten 14 Tage alle, dahinter je Woche die neueste,
     bis etwa 8 Wochen zurueck.

Nicht gesichert wird media/ (Videos, mehrere GB, am PC im Original vorhanden) - nur die Datenbank.

Ablage: ~/backups/elo (oder BACKUP_DIR). Die Quelle wird nur gelesen (mode=ro).
"""
from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BASIS = Path(__file__).resolve().parent
NAME_FORMAT = "elo-%Y%m%d-%H%M.db"
_NAME = re.compile(r"^elo-(\d{8})-(\d{4})\.db$")
JOB = "balu_backup"                 # Name des Job-Status fuer Home Assistant


def datum_aus_name(name: str) -> datetime | None:
    """Zeitpunkt aus dem Dateinamen, None bei fremden oder kaputten Namen."""
    m = _NAME.match(name)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M")
    except ValueError:
        return None


def sichern(quelle: Path | str, ordner: Path | str, jetzt: datetime | None = None) -> Path:
    """Konsistente, geprueftes Kopie der Datenbank in `ordner`. Gibt den Pfad der Sicherung zurueck."""
    quelle, ordner = Path(quelle), Path(ordner)
    if not quelle.is_file():                      # sqlite3.connect wuerde sonst eine LEERE Datenbank anlegen
        raise FileNotFoundError(f"Datenbank nicht gefunden: {quelle}")
    jetzt = jetzt or datetime.now()
    ordner.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(ordner, 0o700)                   # enthaelt PIN-Hashes: nur der Benutzer selbst
    except OSError:
        pass
    ziel = ordner / jetzt.strftime(NAME_FORMAT)
    teil = ordner / (ziel.name + ".tmp")
    teil.unlink(missing_ok=True)

    src = sqlite3.connect(quelle.as_uri() + "?mode=ro", uri=True, timeout=15)
    dst = sqlite3.connect(teil)
    try:
        src.backup(dst)
        ergebnis = dst.execute("PRAGMA integrity_check").fetchone()[0]
        if ergebnis != "ok":
            raise sqlite3.DatabaseError(f"integrity_check der Sicherung: {ergebnis}")
    except BaseException:
        src.close()
        dst.close()
        teil.unlink(missing_ok=True)
        raise
    src.close()
    dst.close()
    try:
        os.chmod(teil, 0o600)
    except OSError:
        pass
    os.replace(teil, ziel)                        # atomar: entweder ganz da oder gar nicht
    return ziel


def zu_loeschen(namen: list[str], jetzt: datetime, tage: int = 14, wochen: int = 8) -> list[str]:
    """Welche der Namen duerfen weg? Rein rechnerisch, ohne Dateizugriff (daher gut testbar).

    Behalten: alles juenger als `tage` Tage; aus der Zeit danach je ISO-Woche die neueste,
    bis `wochen` Wochen zurueck. Fremde Namen werden nie genannt, und die neueste gueltige
    Sicherung ist immer geschuetzt - lieber zu viel als gar keine."""
    gueltig = {n: datum_aus_name(n) for n in namen}
    gueltig = {n: d for n, d in gueltig.items() if d is not None}
    if len(gueltig) <= 1:
        return []
    neueste = max(gueltig)                        # Namen sind datumssortiert
    behalten = {neueste}
    aelter: dict[tuple[int, int], list[str]] = {}
    for n, d in gueltig.items():
        alter = (jetzt.date() - d.date()).days
        if alter < tage:
            behalten.add(n)
        elif alter < wochen * 7:
            aelter.setdefault(d.isocalendar()[:2], []).append(n)
    for gruppe in aelter.values():
        behalten.add(max(gruppe))
    return sorted(n for n in gueltig if n not in behalten)


def aufraeumen(ordner: Path | str, jetzt: datetime | None = None) -> int:
    """Duennt den Ordner nach der Regel aus. Gibt die Zahl geloeschter Sicherungen zurueck."""
    ordner = Path(ordner)
    jetzt = jetzt or datetime.now()
    weg = zu_loeschen([p.name for p in ordner.iterdir() if p.is_file()], jetzt)
    for n in weg:
        (ordner / n).unlink()
    return len(weg)


def _status(ok: bool, text: str) -> None:
    """Job-Status fuer Home Assistant (wie die anderen Balu-Jobs); fehlt das Modul, ist das kein Fehler."""
    try:
        import anytype_sync
        anytype_sync.schreibe_status(JOB, ok, text, 0 if ok else 1)
    except Exception:
        pass


def _cli() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(BASIS / "elo.db"), help="Quelle (Standard: elo.db neben diesem Skript)")
    ap.add_argument("--ziel", default=os.getenv("BACKUP_DIR") or str(Path.home() / "backups" / "elo"),
                    help="Zielordner (Standard: ~/backups/elo oder BACKUP_DIR)")
    args = ap.parse_args()
    try:
        datei = sichern(args.db, args.ziel)
        weg = aufraeumen(args.ziel)
        gesamt = len([p for p in Path(args.ziel).glob("elo-*.db")])
        text = f"{datei.name} ({datei.stat().st_size / 1024:.0f} KB), {gesamt} Stand/Staende, {weg} alte geloescht"
        print(text)
        _status(True, text)
        return 0
    except Exception as e:
        text = f"Fehler: {e}"
        print(text, file=sys.stderr)
        _status(False, text)
        return 1


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(_cli())
