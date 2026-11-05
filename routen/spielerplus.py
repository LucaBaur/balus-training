"""Abgleich der Zu- und Absagen mit SpielerPlus (mit Mindestabstand)."""

from __future__ import annotations

import threading
import time

from fastapi import APIRouter, Depends, HTTPException

from .gemeinsam import hole_conn, require_trainer


router = APIRouter()


_SP_SPERRE = threading.Lock()
_SP_MINDESTABSTAND = 45          # Sekunden zwischen zwei Abgleichen
_sp_zuletzt = 0.0


@router.post("/api/spielerplus-abgleich")
def api_spielerplus_abgleich(conn=Depends(hole_conn), _t=Depends(require_trainer)):
    """Trainer holt Zu-/Absagen jetzt aus SpielerPlus (statt auf den Cron zu
    warten). Gleiche Logik wie der Cronjob (sp_import) - und gleiche Regel:
    Eingaben aus der App/vom Trainer werden nicht ueberschrieben.

    Zwei Schutzmechanismen, weil SpielerPlus scraping-basiert und der Zugang
    geteilt ist: nur EIN Lauf gleichzeitig (Lock) und ein Mindestabstand."""
    global _sp_zuletzt
    import sp_import
    if not _SP_SPERRE.acquire(blocking=False):
        raise HTTPException(429, "Ein Abgleich läuft gerade schon.")
    try:
        warte = _SP_MINDESTABSTAND - (time.monotonic() - _sp_zuletzt)
        if warte > 0:
            raise HTTPException(429, f"Gerade erst abgeglichen – bitte {int(warte) + 1} s warten.")
        _sp_zuletzt = time.monotonic()
        try:
            s = sp_import.lauf(conn)
        except sp_import.SpielerPlusFehler as e:
            raise HTTPException(502, f"SpielerPlus nicht erreichbar: {e}")
        return {"ok": True, "text": sp_import.kurzfassung(s), **s}
    finally:
        _SP_SPERRE.release()
