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


# Arten von Mitteilungen. Jede Person kann sie einzeln abschalten (Menü -> Mitteilungen).
# `rollen` bestimmt, wem die Einstellung angezeigt wird.
ARTEN = [
    {"key": "termine", "label": "Termine",
     "text": "Abfahrt und Anwurf, abgesagte Termine, Erinnerung zum Antworten",
     "rollen": ("spieler", "trainer")},
    {"key": "aemter", "label": "Ämter",
     "text": "Wenn du für Trikots, Leibchen, Getränke oder eine Fahrt eingeteilt wirst, und eine Stunde vor "
             "dem Termin, was du mitbringen sollst", "rollen": ("spieler", "trainer")},
    {"key": "videos", "label": "Videos",
     "text": "Neue Clips und Videoanalysen für dich", "rollen": ("spieler",)},
    {"key": "rueckmeldungen", "label": "Rückmeldungen",
     "text": "Feedback zu To-Dos, Fragen und Antworten unter Videos",
     "rollen": ("spieler", "trainer")},
    {"key": "warnungen", "label": "Warnungen",
     "text": "Wenn für einen Termin zu wenige Zusagen da sind", "rollen": ("trainer",)},
]
ART_KEYS = {a["key"] for a in ARTEN}

TTL_SEKUNDEN = 12 * 3600      # eine Abfahrtszeit von gestern will niemand mehr, ein paar Stunden schon


def arten_fuer(rolle: str) -> list[dict]:
    return [a for a in ARTEN if rolle in a["rollen"]]


def sende(conn, benutzer_ids: list[int], titel: str, text: str,
          url: str = "/", art: str | None = None) -> dict:
    """Push an alle Abos der genannten Benutzer. Liefert {gesendet, entfernt}.

    Mit `art` wird vorher gefiltert: wer diese Art abgeschaltet hat, bekommt nichts.
    Die Prüfung sitzt hier und nicht bei jedem Auslöser, damit keiner sie vergessen kann."""
    import db
    benutzer_ids = db.push_filtern(conn, benutzer_ids, art)
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
            # ttl: wie lange der Push-Dienst die Nachricht aufbewahrt, falls das Gerät gerade nicht
            # erreichbar ist (Ruhezustand, Browser zu). pywebpush setzt ohne Angabe 0 = sofort
            # verwerfen. Urgency "high" weckt Android auch im Ruhezustand.
            webpush(sub, payload, vapid_private_key=str(_PRIV),
                    vapid_claims={"sub": _subject()}, ttl=TTL_SEKUNDEN,
                    headers={"Urgency": "high"})
            gesendet += 1
        except WebPushException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code in (404, 410):          # Abo tot -> aufraeumen
                db.push_abo_loeschen_id(conn, a["id"])
                entfernt += 1
    return {"gesendet": gesendet, "entfernt": entfernt, "abos": len(abos)}
