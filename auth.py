"""Authentifizierung fuer Balu's Training (Phase 4).

Bewusst ohne externe Libs (nur stdlib):
- PIN-Hash via PBKDF2-HMAC-SHA256 (Salt + viele Iterationen). PINs werden NIE im
  Klartext gespeichert.
- Session als signiertes Cookie: base64url(payload) + "." + HMAC-SHA256. Kein
  Server-State noetig; der Server kann das Cookie ohne DB-Lookup verifizieren.

Das Secret kommt aus der Umgebung (APP_SECRET) oder wird einmalig in
`.session_secret` (chmod 600) neben der App erzeugt und dort persistiert.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

BASIS = Path(__file__).parent
_ITER = 200_000
_MAX_ALTER = 60 * 24 * 3600          # Session-Gueltigkeit: 60 Tage
COOKIE_NAME = "sitzung"


# ------------------------------------------------------------------- Secret ----

def _lade_secret() -> bytes:
    s = os.getenv("APP_SECRET")
    if s:
        return s.encode("utf-8")
    pfad = BASIS / ".session_secret"
    if pfad.exists():
        return pfad.read_bytes().strip()
    roh = secrets.token_hex(32).encode("ascii")
    pfad.write_bytes(roh)
    try:
        os.chmod(pfad, 0o600)
    except OSError:
        pass
    return roh


_SECRET = _lade_secret()


# ---------------------------------------------------------------- PIN-Hash ----

def hash_pin(pin: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"), salt, _ITER)
    return f"pbkdf2_sha256${_ITER}${salt.hex()}${dk.hex()}"


def pruefe_pin(pin: str, gespeichert: str | None) -> bool:
    if not gespeichert:
        return False
    try:
        algo, iter_s, salt_hex, hash_hex = gespeichert.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", pin.encode("utf-8"),
                                 bytes.fromhex(salt_hex), int(iter_s))
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


# ----------------------------------------------------------------- Session ----

def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode("ascii").rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def session_erstellen(benutzer_id: int, als: int | None = None) -> str:
    """Session-Cookie fuer 'benutzer_id'. Mit 'als' (nur vom Server fuer einen
    Trainer gesetzt) sieht dieser die App aus Sicht von Benutzer 'als' -
    "Ansicht als"."""
    inhalt = {"uid": benutzer_id, "iat": int(time.time())}
    if als is not None:
        inhalt["als"] = int(als)
    payload = _b64e(json.dumps(inhalt).encode())
    sig = _b64e(hmac.new(_SECRET, payload.encode("ascii"), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def session_daten(token: str | None) -> dict | None:
    """Geprueftes Payload eines gueltigen Cookies ({'uid', 'iat', optional
    'als'}), sonst None. Prueft HMAC-Signatur und Alter."""
    if not token or "." not in token:
        return None
    payload, sig = token.rsplit(".", 1)
    erwartet = _b64e(hmac.new(_SECRET, payload.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, erwartet):
        return None
    try:
        daten = json.loads(_b64d(payload))
        if int(time.time()) - int(daten["iat"]) > _MAX_ALTER:
            return None
        int(daten["uid"])                       # muss eine Zahl sein
        return daten
    except (ValueError, KeyError, TypeError):
        return None


def session_pruefen(token: str | None) -> int | None:
    """Liefert die Benutzer-ID aus einem gueltigen Cookie, sonst None."""
    d = session_daten(token)
    return int(d["uid"]) if d else None
