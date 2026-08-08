"""Anytype-Anbindung fuer das ELO-System.

- Import: liest die Spielerinnen (Name, Anytype-ID, spielerplus_id, Position)
  aus dem Anytype-Space in die lokale SQLite-DB.
- Sync: schreibt die aktuelle ELO jeder Spielerin zurueck in die Anytype-
  Eigenschaft `elo` (Number).

Config aus der .env (gleiche Schluessel wie beim SpielerPlus-Sync):
  Api_key, ANYTYPE_SPACE_ID, optional ANYTYPE_API_BASE (Homeserver: 31012),
  optional ANYTYPE_ELO_KEY (Default "elo").

CLI:
  python anytype_sync.py --pruefe    # Verbindung + Eigenschaften pruefen
  python anytype_sync.py --import     # Spielerinnen aus Anytype importieren
  python anytype_sync.py --sync       # ELOs nach Anytype schreiben
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests

BASIS = Path(__file__).parent
API_VERSION = "2025-05-20"
DEFAULT_BASE = "http://127.0.0.1:31009/v1"


# ------------------------------------------------------------------- .env ----

def load_env(pfad: Path | str = BASIS / ".env") -> dict[str, str]:
    env: dict[str, str] = {}
    pfad = Path(pfad)
    if pfad.exists():
        for zeile in pfad.read_text(encoding="utf-8").splitlines():
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            k, v = zeile.split("=", 1)
            env[k.strip()] = v.strip()
    # Umgebungsvariablen haben Vorrang (z. B. im systemd-Dienst)
    for k in ("Api_key", "ANYTYPE_SPACE_ID", "ANYTYPE_API_BASE", "ANYTYPE_ELO_KEY"):
        if os.getenv(k):
            env[k] = os.environ[k]
    return env


class AnytypeError(Exception):
    pass


# --------------------------------------------------------------- Client ----

class Anytype:
    def __init__(self, api_key: str, space_id: str, api_base: str | None = None):
        self.space = space_id
        self.api_base = (api_base or DEFAULT_BASE).rstrip("/")
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Bearer {api_key}",
            "Anytype-Version": API_VERSION,
            "Content-Type": "application/json",
        })

    def _url(self, path: str) -> str:
        return f"{self.api_base}/spaces/{self.space}{path}"

    def search(self, types=None, limit: int = 100) -> list[dict]:
        body: dict = {"query": ""}
        if types:
            body["types"] = types
        out, offset = [], 0
        while True:
            r = self.s.post(self._url("/search"), json=body,
                            params={"limit": limit, "offset": offset}, timeout=30)
            r.raise_for_status()
            d = r.json()
            out.extend(d.get("data", []))
            if not d.get("pagination", {}).get("has_more"):
                break
            offset += limit
        return out

    @staticmethod
    def prop_value(obj: dict, key: str):
        for p in obj.get("properties", []):
            if p.get("key") == key:
                for fmt in ("text", "number", "date", "objects", "select",
                            "multi_select", "checkbox", "url"):
                    if fmt in p:
                        return p[fmt]
        return None

    @staticmethod
    def prop_keys(obj: dict) -> list[str]:
        return [p.get("key") for p in obj.get("properties", [])]

    def get_object(self, object_id: str) -> dict:
        r = self.s.get(self._url(f"/objects/{object_id}"), timeout=30)
        r.raise_for_status()
        return r.json()["object"]

    def create_object(self, type_key: str, name: str, properties: list,
                      body: str | None = None) -> dict:
        payload: dict = {"type_key": type_key, "name": name, "properties": properties}
        if body is not None:
            payload["body"] = body
        r = self.s.post(self._url("/objects"), json=payload, timeout=30)
        if r.status_code >= 400:
            raise AnytypeError(f"create {r.status_code}: {r.text[:300]}")
        return r.json()["object"]

    def delete_object(self, object_id: str) -> bool:
        r = self.s.delete(self._url(f"/objects/{object_id}"), timeout=30)
        return r.status_code < 400

    def update_object(self, object_id: str, properties: list,
                      body: str | None = None) -> dict:
        payload: dict = {"properties": properties}
        if body is not None:
            payload["markdown"] = body
        r = self.s.patch(self._url(f"/objects/{object_id}"), json=payload, timeout=30)
        if r.status_code >= 400:
            raise AnytypeError(f"update {r.status_code}: {r.text[:300]}")
        return r.json()["object"]

    def create_property(self, name: str, fmt: str = "number") -> dict:
        """Legt eine Eigenschaft im Space an (falls die API das unterstuetzt)."""
        r = self.s.post(self._url("/properties"),
                        json={"name": name, "format": fmt}, timeout=30)
        if r.status_code >= 400:
            raise AnytypeError(f"create_property {r.status_code}: {r.text[:300]}")
        return r.json()


# ------------------------------------------------------------- Funktionen ----

def schreibe_status(job: str, ok: bool, summary: str, exit_code: int) -> None:
    """Status-Datei fuer den Home-Assistant-Report ablegen (gleiches Format wie
    jobstatus.py der anytype-sync-Jobs). ha_status.py liest den Ordner und meldet
    alle Jobs an Home Assistant."""
    import json
    status_dir = Path(os.getenv("ELO_STATUS_DIR",
                                Path.home() / "anytype-sync" / "status"))
    try:
        status_dir.mkdir(parents=True, exist_ok=True)
        data = {
            "job": job, "ok": ok, "summary": summary, "exit_code": exit_code,
            "last_run": datetime.now().astimezone().isoformat(timespec="seconds"),
        }
        (status_dir / f"{job}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def get_client(env: dict[str, str] | None = None) -> Anytype:
    env = env or load_env()
    if not env.get("Api_key") or not env.get("ANYTYPE_SPACE_ID"):
        raise AnytypeError(
            "Anytype nicht konfiguriert: Api_key / ANYTYPE_SPACE_ID fehlen in der .env."
        )
    return Anytype(env["Api_key"], env["ANYTYPE_SPACE_ID"],
                   api_base=env.get("ANYTYPE_API_BASE"))


def elo_key(env: dict[str, str] | None = None) -> str:
    env = env or load_env()
    return env.get("ANYTYPE_ELO_KEY", "elo")


def _position(pos_angriff: str) -> str:
    return "Tor" if str(pos_angriff).strip().lower().startswith("tor") else "Feld"


def lade_kader(at: Anytype) -> list[dict]:
    """Spielerinnen aus Anytype fuer den Import."""
    out = []
    for o in at.search(types=["spieler"]):
        sid = at.prop_value(o, "spielerplus_id")
        out.append({
            "anytype_id": o["id"],
            "name": o.get("name", ""),
            "spielerplus_id": str(sid) if sid else None,
            "position": _position(at.prop_value(o, "position_angriff") or ""),
        })
    return out


def schreibe_elos(at: Anytype, paare: list[tuple[str, int]], key: str) -> int:
    """paare: (anytype_id, elo). Liefert Anzahl geschriebener Objekte."""
    n = 0
    for aid, elo in paare:
        at.update_object(aid, [{"key": key, "number": int(elo)}])
        n += 1
    return n


ELO_SECTION_HEADING = "ELO-Verlauf"


def _strip_elo_section(md: str) -> str:
    """Entfernt eine fruehere ELO-Verlauf-Sektion (Ueberschrift + Bild), robust
    gegen Anytypes Roundtrip (## faellt weg, Bild-URL wird intern)."""
    lines = (md or "").split("\n")

    def ist_start(l: str) -> bool:
        return l.strip().lstrip("#").strip() == ELO_SECTION_HEADING

    def ist_sektionszeile(l: str) -> bool:
        s = l.strip()
        return s == "" or s.startswith("![") or ist_start(l)

    out, i, n = [], 0, len(lines)
    while i < n:
        if ist_start(lines[i]):
            i += 1
            while i < n and ist_sektionszeile(lines[i]):
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out).strip()


def _normalisiere(md: str) -> str:
    """Anytype haengt bei jedem Schreiben <br> und Spalten-Spaces an Tabellen an.
    Damit der erhaltene Rest-Text nicht nächtlich anwaechst: <br> entfernen und
    Mehrfach-Leerzeichen zusammenfassen (Anytype rendert die Tabelle eh neu)."""
    import re
    zeilen = []
    for l in (md or "").split("\n"):
        l = l.replace("<br>", "")
        l = re.sub(r"[ \t]{2,}", " ", l).rstrip()
        zeilen.append(l)
    return "\n".join(zeilen).strip()


def embed_graphs(at: Anytype, base_url: str = "http://127.0.0.1:8200") -> int:
    """Erzeugt die Verlaufs-PNGs und bettet sie je Spielerin in Anytype ein.
    Anytype laedt das Bild von der URL und speichert es intern."""
    import time

    import db
    import elo_graph

    conn = db.verbinde()
    db.init_db(conn)
    elo_graph.erzeuge_fuer_alle(conn)
    spieler = db.rangliste(conn)
    conn.close()

    ts = int(time.time())
    n = 0
    for p in spieler:
        aid = p.get("anytype_id")
        if not aid:
            continue
        rest = _normalisiere(_strip_elo_section(at.get_object(aid).get("markdown", "")))
        url = f"{base_url}/graphs/{p['id']}.png?v={ts}"
        section = f"## {ELO_SECTION_HEADING}\n\n![{ELO_SECTION_HEADING}]({url})"
        body = f"{rest}\n\n{section}" if rest else section
        at.update_object(aid, [], body=body)
        n += 1
    return n


def _parse_datum(roh) -> date | None:
    if not roh:
        return None
    try:
        dt = datetime.fromisoformat(str(roh).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone().date()


def _as_id_list(value) -> list[str]:
    """Objects-Property robust zu einer Liste von IDs machen."""
    if not value:
        return []
    if isinstance(value, list):
        return [v if isinstance(v, str) else v.get("id") for v in value if v]
    return []


def lade_trainings(at: Anytype, tage_zurueck: int = 1, tage_vor: int = 21) -> list[dict]:
    """Trainings mit Datum im Fenster [heute-tage_zurueck, heute+tage_vor],
    je mit den anwesenden (zugesagten) Spieler-IDs aus Anytype."""
    heute = date.today()
    von, bis = heute - timedelta(days=tage_zurueck), heute + timedelta(days=tage_vor)
    out = []
    for o in at.search(types=["training"]):
        d = _parse_datum(at.prop_value(o, "datum"))
        if d is None or d < von or d > bis:
            continue
        out.append({
            "id": o["id"],
            "name": o.get("name", ""),
            "datum": d.isoformat(),
            "anwesend_anytype": _as_id_list(at.prop_value(o, "teilnehmer")),
        })
    out.sort(key=lambda t: t["datum"])
    return out


def kader_info(at: Anytype) -> dict:
    """Anzahl Spielerinnen + Torhueterinnen fuers naechste Training.

    Primaer: Zusagen (teilnehmer) des naechsten anstehenden Trainings. Sonst
    Fallback auf den Gesamtkader. Torhueterin = position_angriff beginnt mit 'Tor'.
    """
    spieler = at.search(types=["spieler"])
    pos = {o["id"]: _position(at.prop_value(o, "position_angriff") or "")
           for o in spieler}

    heute = date.today().isoformat()
    kommend = [t for t in lade_trainings(at, tage_zurueck=0, tage_vor=60)
               if t["datum"] >= heute and t["anwesend_anytype"]]
    if kommend:
        ids = kommend[0]["anwesend_anytype"]
        anzahl = len(ids)
        torhueter = sum(1 for i in ids if pos.get(i) == "Tor")
        quelle = f"Zusagen Training {kommend[0]['datum']}"
    else:
        anzahl = len(spieler)
        torhueter = sum(1 for p in pos.values() if p == "Tor")
        quelle = "Gesamtkader"
    return {"anzahl": anzahl, "torhueter": torhueter, "quelle": quelle}


PLAN_HEADING = "Trainingsplan"


def _strip_plan_section(md: str) -> str:
    """Behaelt den Zusagen-Block, entfernt einen evtl. vorhandenen Plan darunter.

    Ist ein Zusagen-Block ('Zusagen nach Position') vorhanden, gilt alles nach
    dessen Tabelle als (ersetzbarer) Plan – auch ohne Markierung. Sonst wird ab
    einer 'Trainingsplan'-Ueberschrift abgeschnitten."""
    lines = (md or "").split("\n")

    zug = next((i for i, l in enumerate(lines) if "Zusagen nach Position" in l), None)
    if zug is not None:
        j = zug + 1
        while j < len(lines):
            s = lines[j].strip()
            if s == "" or "|" in lines[j] or s.startswith("Zugesagt"):
                j += 1  # gehoert noch zum Zusagen-Block
            else:
                break    # ab hier beginnt der Plan
        return "\n".join(lines[:j]).rstrip()

    for i, l in enumerate(lines):
        if l.strip().lstrip("#").strip().lower().startswith(PLAN_HEADING.lower()):
            return "\n".join(lines[:i]).strip()
    return (md or "").strip()


def training_plan_einfuegen(at: Anytype, titel: str, markdown: str,
                            training_id: str | None = None,
                            datum: str | None = None) -> dict:
    """Fuegt den Plan in ein Training ein. Mit training_id: an dieses Objekt
    (unter die vorhandene Zusagen-Tabelle) anhaengen. Sonst per Datum suchen;
    nicht gefunden -> neues Training anlegen. Ersetzt einen frueheren Plan."""
    aid = training_id
    if aid is None and datum:
        for t in lade_trainings(at, tage_zurueck=400, tage_vor=400):
            if t["datum"] == datum:
                aid = t["id"]
                break
    if aid is None:
        props = [{"key": "datum", "date": datum}] if datum else []
        obj = at.create_object("training", titel, props,
                               body=f"## {PLAN_HEADING}\n\n{markdown}")
        return {"id": obj.get("id"), "neu": True}

    behalten = _normalisiere(_strip_plan_section(at.get_object(aid).get("markdown", "")))
    block = f"## {PLAN_HEADING}\n\n{markdown}"
    body = f"{behalten}\n\n{block}" if behalten else block
    at.update_object(aid, [], body=body)
    return {"id": aid, "neu": False}


# --------------------------------------------------------------------- CLI ----

def _cli() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pruefe", action="store_true")
    ap.add_argument("--import", dest="do_import", action="store_true")
    ap.add_argument("--sync", action="store_true")
    ap.add_argument("--graphs", action="store_true",
                    help="ELO-Verlaufsdiagramme erzeugen und in Anytype einbetten")
    ap.add_argument("--erstelle-property", action="store_true",
                    help="versucht, die ELO-Eigenschaft in Anytype anzulegen")
    args = ap.parse_args()

    env = load_env()
    at = get_client(env)
    key = elo_key(env)

    if args.pruefe or args.erstelle_property:
        kader = at.search(types=["spieler"])
        print(f"Verbindung ok. Spielerinnen im Space: {len(kader)}")
        keys = set()
        for o in kader:
            keys.update(at.prop_keys(o))
        print("Gefundene Eigenschaften:", ", ".join(sorted(k for k in keys if k)))
        print(f"ELO-Key '{key}' vorhanden:", key in keys)
        if args.erstelle_property and key not in keys:
            try:
                res = at.create_property("ELO", "number")
                print("Property angelegt:", res)
            except AnytypeError as e:
                print("Konnte Property nicht anlegen:", e)
                print("-> In Anytype am Spieler-Typ eine Number-Eigenschaft 'ELO' anlegen.")

    if args.do_import:
        import db
        conn = db.verbinde()
        db.init_db(conn)
        res = db.import_kader(conn, lade_kader(at))
        conn.close()
        print(f"Import: {res['neu']} neu, {res['aktualisiert']} aktualisiert, "
              f"{res['gesamt']} gesamt in Anytype.")

    if args.sync:
        try:
            import db
            conn = db.verbinde()
            db.init_db(conn)
            paare = [(p["anytype_id"], p["elo"])
                     for p in db.rangliste(conn) if p.get("anytype_id")]
            conn.close()
            n = schreibe_elos(at, paare, key)
            print(f"Sync: {n} ELO-Werte nach Anytype geschrieben.")
            schreibe_status("elo_sync", True, f"{n} ELO-Werte geschrieben", 0)
        except Exception as e:
            print(f"Sync-Fehler: {e}")
            schreibe_status("elo_sync", False, f"Fehler: {e}", 1)
            raise

    if args.graphs:
        n = embed_graphs(at)
        print(f"Graphs: {n} Diagramme erzeugt und in Anytype eingebettet.")

    if not any([args.pruefe, args.do_import, args.sync, args.graphs,
                args.erstelle_property]):
        ap.print_help()


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    _cli()
