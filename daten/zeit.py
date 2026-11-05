"""Zeit-Helfer: deutsche Zeit und UTC-Zeitstempel."""

from __future__ import annotations

from datetime import timezone


def _berlin():
    """Zeitzone fuer die Tageszaehlung; ohne Zeitzonen-Datenbank (z. B. Windows
    ohne tzdata) UTC - nur die Tagesgrenze verschiebt sich dann um 1-2 Stunden."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Berlin")
    except Exception:
        return timezone.utc


def _utc_z(z: str | None) -> str | None:
    return (z.replace(" ", "T") + "Z") if z else None
