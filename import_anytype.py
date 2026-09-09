"""Einmal-/Wiederhol-Import: Anytype-Space 'Frauen TVG' -> lokale SQLite.

Phase 3 der Anytype-Abloesung. Spiegelt die inhaltstragenden Anytype-Objekte in
die nativen Tabellen (siehe db.py). Idempotent ueber `anytype_id` (partielle
Unique-Indexe) -> mehrfaches Laufen aktualisiert, dupliziert nicht. Anytype
bleibt dabei unveraendert und dient weiter als Fallback, bis alles nativ laeuft.

Was importiert wird:
  - Spieler        -> spieler (Profilfelder; ELO/Spiele bleiben unangetastet)
  - Training       -> trainings + training_teilnahme (Anwesend/Abgesagt)
  - Page/Bespr./Coll -> seiten (Wiki, mit Body-Markdown)

Uebungen werden (noch) NICHT strukturiert extrahiert - die Uebungs-Inhalte
stecken als Freitext in Pages und landen zunaechst in `seiten`. Die Extraktion
in `uebungen` ist ein spaeterer LLM-Schritt (Idee 3).

CLI:
  py import_anytype.py --dry-run          # nur zeigen, was importiert wuerde
  py import_anytype.py                     # in die App-DB (elo.db) importieren
  py import_anytype.py --db pfad.db        # in eine andere DB
  py import_anytype.py --env pfad/.env     # andere .env (Default: Balu-.env,
                                           #   Fallback SpielerPlus-.env)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import anytype_sync as A
import db

BASIS = Path(__file__).parent
# Der Balu-Ordner hat oft keine eigene .env; die Anytype-Zugangsdaten liegen im
# SpielerPlus-Projekt. Beide Kandidaten der Reihe nach probieren.
ENV_KANDIDATEN = [
    BASIS / ".env",
    BASIS.parent / "Anytype-Sync" / ".env",
]


def finde_env(explizit: str | None) -> Path:
    if explizit:
        return Path(explizit)
    for p in ENV_KANDIDATEN:
        if p.exists() and "Api_key" in p.read_text(encoding="utf-8"):
            return p
    return ENV_KANDIDATEN[0]


# ------------------------------------------------------------------ Helfer ----

def _voll(at: A.Anytype, obj: dict) -> dict:
    """Objekt mit vollem Body nachladen (search liefert nur ~300z Snippet)."""
    try:
        return at.get_object(obj["id"])
    except Exception:
        return obj


def _body(obj: dict) -> str:
    return (obj.get("markdown") or obj.get("snippet") or "").strip()


def _tags_json(at: A.Anytype, obj: dict) -> str | None:
    import json
    v = at.prop_value(obj, "tag")
    if not v:
        return None
    namen = []
    for t in v:
        if isinstance(t, dict):
            namen.append(t.get("name") or t.get("id"))
        elif t:
            namen.append(str(t))
    return json.dumps(namen, ensure_ascii=False) if namen else None


# --------------------------------------------------------------- Spieler ----

def import_spieler(conn, at, dry: bool) -> dict:
    """Profilfelder aus Anytype in die spieler-Tabelle. Ordnet ueber anytype_id
    zu; legt fehlende Spielerinnen an (Stufe 'mittel'). ELO/Spiele bleiben."""
    felder = {
        "position_angriff": "position_angriff",
        "posotion_abwehr": "position_abwehr",   # Tippfehler-Key so in Anytype
        "trainingsbeteiligung": "trainingsbeteiligung",
        "absprache": "absprache",
        "urlaub": "urlaub",
        "starken": "staerken",
        "schwachen": "schwaechen",
    }
    neu = akt = 0
    for o in at.search(types=["spieler"]):
        aid = o["id"]
        name = o.get("name", "") or ""
        sp_id = A.Anytype.prop_value(o, "spielerplus_id")
        pos_grob = A._position(A.Anytype.prop_value(o, "position_angriff") or "")
        werte = {ziel: (A.Anytype.prop_value(o, key) or None)
                 for key, ziel in felder.items()}

        row = conn.execute("SELECT id FROM spieler WHERE anytype_id = ?", (aid,)).fetchone()
        if row is None and name:
            row = conn.execute("SELECT id FROM spieler WHERE name = ? AND anytype_id IS NULL",
                               (name,)).fetchone()
        if dry:
            (akt if row else neu).__int__()  # nichts tun im Dry-Run
            neu += 0 if row else 1
            akt += 1 if row else 0
            continue

        if row:
            # Name NICHT überschreiben: die App ist die Wahrheit, lokale Namens-
            # korrekturen (z. B. Spitzname -> echter Name) bleiben erhalten.
            sets = ["anytype_id = ?", "position = ?",
                    "spielerplus_id = COALESCE(?, spielerplus_id)"]
            params = [aid, pos_grob, str(sp_id) if sp_id else None]
            for ziel, v in werte.items():
                sets.append(f"{ziel} = ?")
                params.append(v)
            params.append(row["id"])
            conn.execute(f"UPDATE spieler SET {', '.join(sets)} WHERE id = ?", params)
            akt += 1
        else:
            sid = db.spieler_anlegen(conn, name or "(ohne Name)", stufe="mittel",
                                     position=pos_grob, anytype_id=aid,
                                     spielerplus_id=str(sp_id) if sp_id else None)
            sets = [f"{ziel} = ?" for ziel in werte]
            conn.execute(f"UPDATE spieler SET {', '.join(sets)} WHERE id = ?",
                         [*werte.values(), sid])
            neu += 1
    if not dry:
        conn.commit()
    return {"neu": neu, "aktualisiert": akt}


# -------------------------------------------------------------- Trainings ----

def import_trainings(conn, at, dry: bool) -> dict:
    """Trainings + Teilnahme. Anwesend/Abgesagt (Objects->Spieler) werden ueber
    die anytype_id der Spielerinnen auf lokale IDs gemappt."""
    karte = {r["anytype_id"]: r["id"]
             for r in conn.execute(
                 "SELECT id, anytype_id FROM spieler WHERE anytype_id IS NOT NULL")}
    neu = akt = teilnahmen = 0
    for o in at.search(types=["training"]):
        voll = _voll(at, o)
        aid = o["id"]
        datum = A._parse_datum(A.Anytype.prop_value(o, "datum"))
        datum_iso = datum.isoformat() if datum else ""
        titel = o.get("name", "") or ""
        inhalt = A.Anytype.prop_value(o, "inhalt") or None
        plan = _body(voll) or None
        ev = A.Anytype.prop_value(o, "spielerplus_event_id")
        anwesend = A._as_id_list(A.Anytype.prop_value(o, "teilnehmer"))
        abgesagt = A._as_id_list(A.Anytype.prop_value(o, "abgesagt"))

        if dry:
            neu += 1
            teilnahmen += sum(1 for a in anwesend + abgesagt if a in karte)
            continue

        row = conn.execute("SELECT id FROM trainings WHERE anytype_id = ?", (aid,)).fetchone()
        if row:
            conn.execute(
                "UPDATE trainings SET datum=?, titel=?, inhalt=?, plan_markdown=?, "
                "spielerplus_event_id=? WHERE id=?",
                (datum_iso, titel, inhalt, plan, str(ev) if ev else None, row["id"]))
            tid = row["id"]
            akt += 1
        else:
            cur = conn.execute(
                "INSERT INTO trainings (datum, titel, inhalt, plan_markdown, "
                "spielerplus_event_id, anytype_id) VALUES (?,?,?,?,?,?)",
                (datum_iso, titel, inhalt, plan, str(ev) if ev else None, aid))
            tid = cur.lastrowid
            neu += 1

        # Teilnahme nur SEEDEN, wo noch keine Antwort existiert. App-Antworten
        # (quelle='app') sind die Wahrheit und bleiben unangetastet -> kein DELETE,
        # INSERT OR IGNORE laesst vorhandene Zeilen (app wie anytype) stehen.
        for status, ids in (("anwesend", anwesend), ("abgesagt", abgesagt)):
            for a in ids:
                sid = karte.get(a)
                if sid:
                    conn.execute(
                        "INSERT OR IGNORE INTO training_teilnahme "
                        "(training_id, spieler_id, status, quelle) VALUES (?,?,?, 'anytype')",
                        (tid, sid, status))
                    teilnahmen += 1
    if not dry:
        conn.commit()
    return {"neu": neu, "aktualisiert": akt, "teilnahmen": teilnahmen}


# ----------------------------------------------------------------- Seiten ----

# Grobe Kategorisierung der Wiki-Pages nach Titel (nur Startwert; spaeter manuell
# verfeinerbar). Kleinbuchstaben-Teilstrings.
KATEGORIE_REGELN = [
    # Playbook = Taktik generell, Absprache-Frauen, Spielzuege (+ deren
    # Unterseiten). Die frueher hier einsortierten Titel wie 'Innenblock' oder
    # '2te Welle' sind Uebungs-Kategorien und stehen deshalb unter 'uebung'.
    ("playbook", ["playbook", "taktik generell", "taktik-generell", "absprache",
                  "spielzug", "spielzüge", "spielzuege", "überzahl", "ueberzahl",
                  "unterzahl", "offensive abwehr"]),
    ("gegner",   ["gegner"]),
    ("uebung",   ["aufwaerm", "aufwärm", "erwaermung", "erwärmung", "wurf", "kraft",
                  "technik", "ausdauer", "wettkamp", "wettkämp", "trainingseinheit",
                  "innenblock", "2te welle", "2. welle", "zweite welle", "konter",
                  "abschlusspiel", "abschlussspiel", "taktikschulung"]),
    ("saison",   ["saison", "vorbereitung", "trainingslager", "auftakt", "grillen"]),
    ("statistik", ["statistik", "tabelle", "resultate", "laufchallenge", "video"]),
    ("orga",     ["to-do", "todo", "halle", "trainer treff", "ideen", "kader",
                  "home", "sonstiges", "option"]),
]


def _kategorie(titel: str, herkunft: str) -> str | None:
    if herkunft == "besprechung":
        return "besprechung"
    t = (titel or "").lower()
    for kat, worte in KATEGORIE_REGELN:
        if any(w in t for w in worte):
            return kat
    return "notiz"


def import_seiten(conn, at, dry: bool) -> dict:
    neu = akt = 0
    proben = []
    for typ in ("page", "besprechung", "collection"):
        for o in at.search(types=[typ]):
            voll = _voll(at, o)
            aid = o["id"]
            titel = o.get("name", "") or "(ohne Titel)"
            md = _body(voll) or None
            kat = _kategorie(titel, typ)
            tags = _tags_json(at, o)
            if dry:
                neu += 1
                if len(proben) < 8:
                    proben.append(f"{kat}: {titel}")
                continue
            row = conn.execute("SELECT id FROM seiten WHERE anytype_id = ?",
                               (aid,)).fetchone()
            if row:
                # Kategorie/Hierarchie NICHT ueberschreiben: die App ist die
                # Wahrheit fuer die Struktur (Playbook-Umbau, verschobene Seiten).
                # KATEGORIE_REGELN gilt nur noch fuer neu importierte Seiten.
                conn.execute(
                    "UPDATE seiten SET titel=?, markdown=?, tags=?, "
                    "anytype_typ=?, aktualisiert=datetime('now') WHERE id=?",
                    (titel, md, tags, typ, row["id"]))
                akt += 1
            else:
                conn.execute(
                    "INSERT INTO seiten (titel, kategorie, markdown, tags, anytype_id, "
                    "anytype_typ) VALUES (?,?,?,?,?,?)",
                    (titel, kat, md, tags, aid, typ))
                neu += 1
    if not dry:
        conn.commit()
    return {"neu": neu, "aktualisiert": akt, "proben": proben}


# --------------------------------------------------------------------- CLI ----

def _cli() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="nichts schreiben, nur zaehlen")
    ap.add_argument("--db", help="Ziel-SQLite (Default: elo.db der App)")
    ap.add_argument("--env", help="Pfad zur .env mit Api_key/ANYTYPE_SPACE_ID")
    ap.add_argument("--nur", choices=["spieler", "trainings", "seiten"],
                    help="nur einen Teil importieren")
    args = ap.parse_args()

    env_pfad = finde_env(args.env)
    env = A.load_env(env_pfad)
    at = A.get_client(env)

    conn = db.verbinde(args.db) if args.db else db.verbinde()
    db.init_db(conn)

    modus = "DRY-RUN (nichts wird geschrieben)" if args.dry_run else f"Schreibe nach {args.db or 'elo.db'}"
    print(f"Anytype: {env.get('ANYTYPE_SPACE_ID','?')[:8]}…  .env: {env_pfad}")
    print(f"Modus:   {modus}\n")

    teile = [args.nur] if args.nur else ["spieler", "trainings", "seiten"]

    if "spieler" in teile:
        r = import_spieler(conn, at, args.dry_run)
        print(f"Spieler   : {r['neu']} neu, {r['aktualisiert']} aktualisiert")
    if "trainings" in teile:
        r = import_trainings(conn, at, args.dry_run)
        print(f"Trainings : {r['neu']} neu, {r['aktualisiert']} aktualisiert, "
              f"{r['teilnahmen']} Teilnahme-Eintraege")
    if "seiten" in teile:
        r = import_seiten(conn, at, args.dry_run)
        print(f"Seiten    : {r['neu']} neu, {r['aktualisiert']} aktualisiert")
        if r.get("proben"):
            print("  Beispiele:", "; ".join(r["proben"]))

    conn.close()
    if args.dry_run:
        print("\nDry-Run beendet - es wurde nichts geschrieben.")


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _cli()
