"""Liga-Daten (Tabelle + Spielplan) aus handball4all, dem Dienst hinter bwhv.org.

Die Verbandsseite laedt ihre Daten aus einer oeffentlichen JSON-Schnittstelle
(`spo.handball4all.de/service/if_g_json.php`). Hier wird sie bei Bedarf abgerufen,
auf ein schlankes Format gebracht und kurz zwischengespeichert:

- hoechstens alle 15 Minuten (an Spieltagen alle 3 Minuten) ein Abruf, und nur
  wenn jemand die Seite oeffnet - es gibt keinen Dauerabruf,
- bei einem Ausfall der Quelle gibt es den letzten Stand zurueck (`veraltet`),
  auch nach einem Neustart (Datei `liga_cache.json`).

Die Kennungen stehen in der URL der Verbandsseite (ogId/lId/tId) und lassen
sich per Umgebungsvariable ersetzen: LIGA_OG, LIGA_CL, LIGA_CT, LIGA_EIGENER_NAME.
"""
from __future__ import annotations

import json
import os
import threading
import time
import urllib.request
from datetime import date, datetime, timezone
from pathlib import Path

OG = os.environ.get("LIGA_OG", "216")          # Organisation (Bezirk Oberschwaben-Ostalb)
CL = os.environ.get("LIGA_CL", "166266")       # Staffel: Frauen Bezirksoberliga
CT = os.environ.get("LIGA_CT", "1495111")      # Mannschaft: TV Gerhausen 1900
EIGENER_NAME = os.environ.get("LIGA_EIGENER_NAME", "TV Gerhausen")   # Vorsilbe in den Spielzeilen

URL = ("https://spo.handball4all.de/service/if_g_json.php"
       f"?ca=0&cl={CL}&cmd=ps&ct={CT}&og={OG}")
CACHE_DATEI = Path(__file__).with_name("liga_cache.json")

TTL_NORMAL_S = 15 * 60
TTL_SPIELTAG_S = 3 * 60
TIMEOUT_S = 10

_lock = threading.Lock()
_speicher: dict = {"ts": 0.0, "daten": None}


def hole_roh() -> list:
    """Ruft die Schnittstelle ab (Browser-Kennung, damit sie nicht abgewiesen wird)."""
    anfrage = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (Balu-Training)"})
    with urllib.request.urlopen(anfrage, timeout=TIMEOUT_S) as r:
        return json.loads(r.read().decode("utf-8"))


def _zahl(wert) -> int | None:
    try:
        return int(str(wert).strip())
    except (TypeError, ValueError):
        return None


def _datum(text: str) -> str | None:
    """'26.09.26' -> '2026-09-26'."""
    try:
        return datetime.strptime(str(text).strip(), "%d.%m.%y").date().isoformat()
    except ValueError:
        return None


def _eigen(name: str) -> bool:
    return str(name or "").strip().startswith(EIGENER_NAME)


def normalisiere(roh: list) -> dict:
    """Rohdaten -> {liga, stand, tabelle, spiele, hinweise}. Wirft bei unbrauchbaren Daten."""
    seite = roh[0]
    inhalt, kopf = seite["content"], seite.get("head", {})
    tabelle = []
    for r in inhalt["score"]:
        tabelle.append({
            "platz": _zahl(r.get("tabScore")),            # leer bei gleichem Platz wie der Vordermann
            "team": r["tabTeamname"], "eigen": str(r.get("tabTeamID")) == str(CT) or _eigen(r["tabTeamname"]),
            "spiele": r.get("numPlayedGames", 0), "s": r.get("numWonGames", 0),
            "u": r.get("numEqualGames", 0), "n": r.get("numLostGames", 0),
            "tore_plus": r.get("numGoalsShot", 0), "tore_minus": r.get("numGoalsGot", 0),
            "punkte_plus": r.get("pointsPlus", 0), "punkte_minus": r.get("pointsMinus", 0),
        })

    spiele = []
    for g in inhalt["futureGames"]["games"]:
        heim, gast = g["gHomeTeam"].strip(), g["gGuestTeam"].strip()
        tore_h, tore_g = _zahl(g.get("gHomeGoals")), _zahl(g.get("gGuestGoals"))
        gespielt = tore_h is not None and tore_g is not None
        eigen_heim = _eigen(heim)
        ergebnis = None                                    # aus Sicht der eigenen Mannschaft
        if gespielt and (eigen_heim or _eigen(gast)):
            mein, dein = (tore_h, tore_g) if eigen_heim else (tore_g, tore_h)
            ergebnis = "S" if mein > dein else "N" if mein < dein else "U"
        hz_h, hz_g = _zahl(g.get("gHomeGoals_1")), _zahl(g.get("gGuestGoals_1"))
        spiele.append({
            "nr": g["gNo"], "datum": _datum(g["gDate"]), "wochentag": g["gWDay"].strip(),
            "zeit": g["gTime"].strip(), "heim": heim, "gast": gast, "eigen_heim": eigen_heim,
            "tore_heim": tore_h, "tore_gast": tore_g,
            "halbzeit": f"{hz_h}:{hz_g}" if hz_h is not None and hz_g is not None else None,
            "status": "live" if g.get("live") else "gespielt" if gespielt else "offen",
            "ergebnis": ergebnis,
            "bemerkung": (g.get("gComment") or "").strip() or None,
            "halle": (g.get("gGymnasiumName") or "").strip() or None,
            "plz": (g.get("gGymnasiumPostal") or "").strip() or None,
            "ort": (g.get("gGymnasiumTown") or "").strip() or None,
            "strasse": (g.get("gGymnasiumStreet") or "").strip() or None,
        })
    spiele.sort(key=lambda s: (s["datum"] or "", s["zeit"]))

    stand = (kopf.get("actualized") or "").replace("Letzte Änderung:", "").strip() or None
    hinweise = [h.replace("<br>", " ").strip() for h in inhalt.get("scoreComments", [])]
    return {
        "liga": kopf.get("name"), "region": kopf.get("headline1"), "runde": kopf.get("headline2"),
        "stand": stand, "tabelle": tabelle, "spiele": spiele, "hinweise": hinweise,
    }


def _hat_spieltag(daten: dict, heute: date | None = None) -> bool:
    heute = (heute or date.today()).isoformat()
    return any(s["datum"] == heute for s in daten.get("spiele", []))


def _lade_datei() -> dict | None:
    try:
        return json.loads(CACHE_DATEI.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _speichere_datei(eintrag: dict) -> None:
    try:
        CACHE_DATEI.write_text(json.dumps(eintrag, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass                                              # Cache ist nur eine Hilfe


def liga_daten(hole=None, jetzt: float | None = None, heute: date | None = None) -> dict:
    """Aktuelle Liga-Daten. Frisch aus dem Zwischenspeicher, sonst von der Quelle;
    faellt die aus, kommt der letzte Stand mit `veraltet=True`. Ohne jeden Stand: Fehler."""
    hole = hole or hole_roh
    jetzt = time.time() if jetzt is None else jetzt
    with _lock:
        if _speicher["daten"] is None:                     # nach einem Neustart: Datei als Startwert
            alt = _lade_datei()
            if alt and alt.get("daten"):
                _speicher.update(ts=float(alt.get("ts", 0)), daten=alt["daten"])
        daten = _speicher["daten"]
        ttl = TTL_SPIELTAG_S if daten and _hat_spieltag(daten, heute) else TTL_NORMAL_S
        if daten and jetzt - _speicher["ts"] < ttl:
            return {**daten, "abgerufen": _iso(_speicher["ts"]), "veraltet": False}
        try:
            neu = normalisiere(hole())
        except Exception:
            if daten:
                return {**daten, "abgerufen": _iso(_speicher["ts"]), "veraltet": True}
            raise
        _speicher.update(ts=jetzt, daten=neu)
        _speichere_datei({"ts": jetzt, "daten": neu})
        return {**neu, "abgerufen": _iso(jetzt), "veraltet": False}


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
