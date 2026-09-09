"""Web-Push-Versand (Phase 4, Stufe B).

Nutzt pywebpush + die VAPID-Schluessel neben der App:
  .vapid_private.pem  (geheim, 0600)   -> signiert die Pushes
  .vapid_public.txt   (oeffentlich)    -> Browser-applicationServerKey

Abgelaufene Abos (404/410 vom Push-Dienst) werden automatisch entfernt.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

BASIS = Path(__file__).parent
_PRIV = BASIS / ".vapid_private.pem"
_PUB = BASIS / ".vapid_public.txt"


def public_key() -> str:
    return _PUB.read_text(encoding="utf-8").strip() if _PUB.exists() else ""


def verfuegbar() -> bool:
    return _PRIV.exists() and bool(public_key())


def _subject() -> str:
    return os.getenv("VAPID_SUBJECT", "mailto:admin@example.com")


def sende(conn, benutzer_ids: list[int], titel: str, text: str,
          url: str = "/") -> dict:
    """Push an alle Abos der genannten Benutzer. Liefert {gesendet, entfernt}."""
    import db
    if not verfuegbar() or not benutzer_ids:
        return {"gesendet": 0, "entfernt": 0, "abos": 0}
    from pywebpush import WebPushException, webpush

    abos = db.push_abos_fuer(conn, benutzer_ids)
    payload = json.dumps({"title": titel, "body": text, "url": url})
    gesendet = entfernt = 0
    for a in abos:
        sub = {"endpoint": a["endpoint"],
               "keys": {"p256dh": a["p256dh"], "auth": a["auth"]}}
        try:
            webpush(sub, payload, vapid_private_key=str(_PRIV),
                    vapid_claims={"sub": _subject()})
            gesendet += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):          # Abo tot -> aufraeumen
                db.push_abo_loeschen_id(conn, a["id"])
                entfernt += 1
    return {"gesendet": gesendet, "entfernt": entfernt, "abos": len(abos)}
