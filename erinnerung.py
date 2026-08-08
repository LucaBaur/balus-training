"""Erinnerung per Home-Assistant-Push, wenn ein Training HEUTE noch keinen Plan hat.

Prueft die Trainings des heutigen Tages in Anytype. Fehlt der Plan (nur Zusagen,
kein Trainingsplan darunter), kommt eine Push-Benachrichtigung aufs Handy
(HA notify.mobile_app_handy_luca) mit Zusagen-Zahl + Torhueter und einem Link,
der die App/den Coach oeffnet.

Gedacht fuer Cron (Trainingstag nachmittags). Log: ~/logs/erinnerung_cron.log
"""
from __future__ import annotations

import datetime
import sys
import traceback

import requests

import anytype_sync as A

PUSH_ZIEL = "mobile_app_handy_luca"
APP_URL = "https://homeserver.tail112520.ts.net/"


def hat_plan(body: str) -> bool:
    """True, wenn unter dem Zusagen-Block schon ein Plan steht."""
    kept = A._strip_plan_section(body or "")
    return len((body or "").strip()) - len(kept.strip()) > 20


def sende_push(env: dict, titel: str, nachricht: str) -> None:
    base = (env.get("HA_URL") or "http://127.0.0.1:8123").rstrip("/")
    token = env.get("HA_TOKEN")
    if not token:
        raise RuntimeError("HA_TOKEN fehlt in der .env")
    r = requests.post(
        f"{base}/api/services/notify/{PUSH_ZIEL}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": titel, "message": nachricht,
              "data": {"clickAction": APP_URL, "url": APP_URL}},
        timeout=15,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"HA-Push {r.status_code}: {r.text[:200]}")


def main() -> int:
    env = A.load_env()
    at = A.get_client()
    heute = datetime.date.today().isoformat()

    # Torhueter-Zuordnung einmal laden
    spieler = at.search(types=["spieler"])
    pos = {o["id"]: A._position(A.Anytype.prop_value(o, "position_angriff") or "")
           for o in spieler}

    trainings = [t for t in A.lade_trainings(at, tage_zurueck=0, tage_vor=1)
                 if t["datum"] == heute]

    gesendet = 0
    for t in trainings:
        body = at.get_object(t["id"]).get("markdown", "")
        if hat_plan(body):
            continue
        ids = t["anwesend_anytype"]
        tw = sum(1 for i in ids if pos.get(i) == "Tor")
        datum_de = datetime.date.fromisoformat(t["datum"]).strftime("%a %d.%m.")
        sende_push(
            env,
            f"Training {datum_de} – noch kein Plan",
            f"{len(ids)} Zusagen ({tw} TW). Tippe hier und sag dem Coach, "
            f"was trainiert werden soll.",
        )
        gesendet += 1

    A.schreibe_status("erinnerung", True, f"{gesendet} Erinnerung(en) gesendet", 0)
    print(f"{gesendet} Erinnerung(en) gesendet (Trainings heute: {len(trainings)}).")
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    try:
        sys.exit(main())
    except Exception as e:
        traceback.print_exc()
        try:
            A.schreibe_status("erinnerung", False, f"Fehler: {e}", 1)
        except Exception:
            pass
        sys.exit(1)
