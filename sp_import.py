"""SpielerPlus -> Balu's Training: Zu- und Absagen der kommenden Trainings holen.

BRUECKE, kein Kernstueck: Die App legt ihre Trainings selbst an
(trainings_termine.py) und kennt SpielerPlus sonst nirgends. Dieses Modul ist
die einzige Stelle, die SpielerPlus kennt - wird SpielerPlus abgeloest, fliegen
diese Datei, der Cronjob und der Knopf in der App raus, sonst nichts.

Zwei Schichten:
  hole_von_spielerplus()  Netz: Login, Terminliste, Teilnehmerlisten
  uebernehme()            reine DB-Logik, ohne Netz (testbar)

Regeln (Source of Truth):
  - Antworten aus der App oder vom Trainer (quelle 'app'/'trainer') werden nie
    ueberschrieben, nur gespiegelte (quelle 'spielerplus'/'anytype').
  - Wer in SpielerPlus (wieder) offen ist, verliert nur eine gespiegelte Antwort.
  - Liefert SpielerPlus fuer einen Termin gar keine Namen (Layout geaendert,
    Fehlseite), wird dieser Termin uebersprungen statt Antworten zu loeschen.
  - Es wird nie ein Training geloescht.

CLI (Cron am Homeserver):
  python sp_import.py                  # naechste 14 Tage
  python sp_import.py --tage 3 --trocken
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, timedelta
from pathlib import Path

import db

# SpielerPlus-Gruppe -> Status in der App. 'offen' und 'nicht_nominiert' haben
# in der App keine Zeile ("noch keine Rueckmeldung").
STATUS = {"zugesagt": "anwesend", "unsicher": "unsicher", "abgesagt": "abgesagt"}
OHNE_ANTWORT = ("offen", "nicht_nominiert")
JOB = "balu_sp_import"


class SpielerPlusFehler(Exception):
    pass


def sp_ordner() -> Path:
    """Wo spielerplus.py und die .env mit den Zugangsdaten liegen."""
    return Path(os.environ.get("SP_SYNC_DIR") or Path.home() / "anytype-sync")


def _lade_env(pfad: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if pfad.exists():
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            k, v = zeile.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


# ---------------------------------------------------------------- Netz ----

def hole_von_spielerplus(tage: int = 14, heute: date | None = None) -> list[dict]:
    """Kommende Trainings (heute .. heute+tage) samt Teilnehmerlisten.

    Je Termin: {event_id, datum, beginn, treffen, titel, gruppen}. 'gruppen'
    hat die Schluessel zugesagt/abgesagt/unsicher/offen/nicht_nominiert, jeder
    mit [{name, user_id}].
    """
    heute = heute or date.today()
    ordner = sp_ordner()
    env = _lade_env(ordner / ".env")
    for k in ("SP_EMAIL", "SP_PASSWORD", "SP_TEAM_ID"):
        if not env.get(k):
            raise SpielerPlusFehler(f"{k} fehlt in {ordner / '.env'}")
    sys.path.insert(0, str(ordner))
    try:
        from spielerplus import SpielerPlus, SpielerPlusError
    except ImportError as e:
        raise SpielerPlusFehler(f"spielerplus.py nicht ladbar: {e}") from e

    try:
        sp = SpielerPlus(env["SP_EMAIL"], env["SP_PASSWORD"])
        sp.login()
        sp.switch_team(int(env["SP_TEAM_ID"]))
        events = [e for e in sp.list_events() if e.get("type") == "training" and e.get("datum")]
        bis = (heute + timedelta(days=tage)).isoformat()
        events = [e for e in events if heute.isoformat() <= e["datum"] <= bis]
        # Ein "Laufen"-Termin am selben Tag wie ein echtes Training zaehlt nicht
        # (gleiche Regel wie im Anytype-Sync).
        normal = {e["datum"] for e in events if "laufen" not in (e.get("title") or "").lower()}
        events = [e for e in events
                  if "laufen" not in (e.get("title") or "").lower() or e["datum"] not in normal]
        out = []
        for e in events:
            teil = sp.get_participation("training", e["id"])
            out.append({"event_id": str(e["id"]), "datum": e["datum"],
                        "beginn": e.get("beginn"), "treffen": e.get("treffen"),
                        "titel": e.get("title") or "", "gruppen": teil["groups"]})
        return out
    except SpielerPlusError as e:
        raise SpielerPlusFehler(str(e)) from e
    except Exception as e:  # Netz, HTML, Login - alles ist "SpielerPlus geht gerade nicht"
        raise SpielerPlusFehler(f"{type(e).__name__}: {e}") from e


# ------------------------------------------------------------------ DB ----

def _training_finden(conn, termin: dict) -> tuple[int | None, bool]:
    """(id, ist_neu_verknuepft). Erst per Event-ID, dann per Datum."""
    row = conn.execute("SELECT id FROM trainings WHERE spielerplus_event_id = ?",
                       (termin["event_id"],)).fetchone()
    if row:
        return int(row["id"]), False
    row = conn.execute(
        "SELECT id, spielerplus_event_id FROM trainings "
        "WHERE datum = ? AND art = 'training' ORDER BY id LIMIT 1",
        (termin["datum"],)).fetchone()
    if row is None:
        return None, False
    if row["spielerplus_event_id"]:
        return -1, False          # Tag gehoert schon zu einem anderen SP-Termin
    return int(row["id"]), True


def uebernehme(conn, termine: list[dict], trocken: bool = False) -> dict:
    """Teilnahme der SpielerPlus-Termine in die DB spiegeln. Commit am Ende."""
    stats = {"termine": len(termine), "trainings_neu": 0, "verknuepft": 0,
             "eingetragen": 0, "entfernt": 0, "manuell_behalten": 0,
             "leer_uebersprungen": 0, "doppelt_uebersprungen": 0, "unbekannt": []}
    spieler = {str(r["spielerplus_id"]): int(r["id"]) for r in conn.execute(
        "SELECT id, spielerplus_id FROM spieler "
        "WHERE spielerplus_id IS NOT NULL AND spielerplus_id != ''")}

    for t in termine:
        gruppen = t.get("gruppen") or {}
        if not any(gruppen.get(k) for k in (*STATUS, *OHNE_ANTWORT)):
            stats["leer_uebersprungen"] += 1       # Parser-Schutz: nichts loeschen
            continue
        tid, verknuepfen = _training_finden(conn, t)
        if tid == -1:
            stats["doppelt_uebersprungen"] += 1
            continue
        if tid is None:
            stats["trainings_neu"] += 1
            if trocken:
                continue
            tid, _ = db.training_anlegen(conn, t["datum"], "Training", uhrzeit=t.get("beginn"))
            verknuepfen = True
        if verknuepfen:
            stats["verknuepft"] += 1
            if not trocken:
                conn.execute("UPDATE trainings SET spielerplus_event_id = ? WHERE id = ?",
                             (t["event_id"], tid))

        for gruppe, status in STATUS.items():
            for u in gruppen.get(gruppe, []):
                sid = spieler.get(str(u.get("user_id")))
                if sid is None:
                    stats["unbekannt"].append(u.get("name") or str(u.get("user_id")))
                    continue
                if trocken:
                    continue
                if db.teilnahme_spiegeln(conn, tid, sid, status):
                    stats["eingetragen"] += 1
                else:
                    stats["manuell_behalten"] += 1
        for gruppe in OHNE_ANTWORT:
            for u in gruppen.get(gruppe, []):
                sid = spieler.get(str(u.get("user_id")))
                if sid is not None and not trocken \
                        and db.teilnahme_spiegel_entfernen(conn, tid, sid):
                    stats["entfernt"] += 1

    if trocken:
        conn.rollback()
    else:
        conn.commit()
    stats["unbekannt"] = sorted(set(stats["unbekannt"]))
    return stats


def lauf(conn, tage: int = 14, trocken: bool = False) -> dict:
    """Komplett: holen + uebernehmen. Wirft SpielerPlusFehler bei Netz-/Loginproblemen."""
    return uebernehme(conn, hole_von_spielerplus(tage), trocken=trocken)


def kurzfassung(s: dict) -> str:
    text = (f"{s['termine']} Termine, {s['eingetragen']} Antworten uebernommen, "
            f"{s['entfernt']} entfernt, {s['manuell_behalten']} manuelle behalten")
    if s["trainings_neu"]:
        text += f", {s['trainings_neu']} Training(s) neu"
    if s["leer_uebersprungen"]:
        text += f", {s['leer_uebersprungen']} ohne Daten uebersprungen"
    if s["unbekannt"]:
        text += f"; ohne Zuordnung: {', '.join(s['unbekannt'])}"
    return text


def _status_schreiben(ok: bool, text: str) -> None:
    """Job-Status fuer Home Assistant (ha_status.py macht daraus einen Sensor)."""
    try:
        sys.path.insert(0, str(sp_ordner()))
        from jobstatus import write_status
        write_status(JOB, ok, text, 0 if ok else 1)
    except Exception:
        pass


def _cli() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tage", type=int, default=14, help="so viele Tage voraus (Default 14)")
    ap.add_argument("--db")
    ap.add_argument("--trocken", action="store_true", help="nur zaehlen, nichts schreiben")
    args = ap.parse_args()
    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)
    try:
        s = lauf(conn, args.tage, args.trocken)
    except SpielerPlusFehler as e:
        print(f"FEHLER: {e}")
        if not args.trocken:
            _status_schreiben(False, f"SpielerPlus: {e}"[:200])
        return 1
    finally:
        conn.close()
    text = kurzfassung(s)
    print(text + (" (TROCKEN)" if args.trocken else ""))
    if not args.trocken:
        _status_schreiben(True, text[:200])
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    sys.exit(_cli())
