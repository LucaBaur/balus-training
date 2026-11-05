"""Gemeinsame Bausteine der Routen: DB-Verbindung, Anmeldung, Rollen- und Rechtepruefung."""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request

import aemter
import auth
import db


def hole_conn():
    conn = db.verbinde()
    try:
        yield conn
    finally:
        conn.close()


# ------------------------------------------------------------------- Auth ----
#  Rollen werden SERVER-SEITIG erzwungen (nicht im UI). 'require_user' verlangt
#  ein gueltiges Session-Cookie, 'require_trainer' zusaetzlich die Trainer-Rolle.

def aktueller_benutzer(request: Request, conn=Depends(hole_conn)) -> dict | None:
    """Der effektive Benutzer. Sieht ein Trainer die App "als" eine Spielerin
    (Feld 'als' im signierten Cookie), wird die Spielerin zurueckgegeben - alle
    Rollen-Pruefungen wirken dann wie fuer sie."""
    d = auth.session_daten(request.cookies.get(auth.COOKIE_NAME))
    if d is None:
        return None
    real = db.benutzer_nach_id(conn, int(d["uid"]))
    if real is None:
        return None
    als = d.get("als")
    if als is not None and real["rolle"] == "trainer":
        eff = db.benutzer_nach_id(conn, int(als))
        if eff is not None:
            return {**eff, "_ansicht_als": True,
                    "_echter_name": real["name"], "_echter_uid": real["id"]}
    return real


def echter_benutzer(request: Request, conn=Depends(hole_conn)) -> dict | None:
    """Der wirklich angemeldete Benutzer - ignoriert 'als'. Fuer die
    Umschalt-Endpunkte, damit nur ein echter Trainer schalten kann."""
    d = auth.session_daten(request.cookies.get(auth.COOKIE_NAME))
    if d is None:
        return None
    return db.benutzer_nach_id(conn, int(d["uid"]))


def require_user(benutzer=Depends(aktueller_benutzer)) -> dict:
    if not benutzer:
        raise HTTPException(401, "Nicht angemeldet")
    return benutzer


def require_trainer(benutzer=Depends(require_user)) -> dict:
    if benutzer["rolle"] != "trainer":
        raise HTTPException(403, "Nur für Trainer")
    return benutzer


def require_echter_trainer(benutzer=Depends(echter_benutzer)) -> dict:
    if not benutzer:
        raise HTTPException(401, "Nicht angemeldet")
    if benutzer["rolle"] != "trainer":
        raise HTTPException(403, "Nur für Trainer")
    return benutzer


def _rechte(conn, benutzer: dict) -> set[str]:
    """Alle Rechte des Benutzers: der Trainer hat jedes, eine Spielerin die ihrer Ämter
    (aemter.AMT_RECHTE). Im "Ansicht als"-Modus ist `benutzer` die angesehene Spielerin."""
    if benutzer["rolle"] == "trainer":
        return set(aemter.RECHTE)
    return aemter.rechte_von(conn, benutzer.get("spieler_id"))


def require_recht(recht: str):
    """Abhängigkeit für Endpunkte, die ein Amt freigeben kann (Capability statt Rolle)."""
    def pruefen(benutzer=Depends(require_user), conn=Depends(hole_conn)) -> dict:
        if recht not in _rechte(conn, benutzer):
            raise HTTPException(403, "Dafür fehlt dir das passende Amt.")
        return benutzer
    return pruefen


_log = logging.getLogger("uvicorn.error")      # landet im Dienst-Log (journalctl --user -u elo)


def _push_hintergrund(ausloeser, *args) -> None:
    """Führt einen Auslöser aus benachrichtigung.py mit eigener DB-Verbindung aus (die der
    Anfrage ist dann schon zu). Push ist Zugabe: scheitert er, bleibt die Aktion gültig,
    aber der Fehler steht im Log."""
    conn = db.verbinde()
    try:
        _log.info("Push %s%s: %s", ausloeser.__name__, args, ausloeser(conn, *args))
    except Exception:
        _log.exception("Push %s fehlgeschlagen", ausloeser.__name__)
    finally:
        conn.close()
