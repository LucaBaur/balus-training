"""Ablageorte auf der Platte.

Die Routen lesen diese Werte zur Laufzeit als `pfade.MEDIA_CLIPS` (nicht per
`from ... import`), damit Tests sie auf ein Temp-Verzeichnis umbiegen koennen.
"""

from __future__ import annotations

from pathlib import Path

BASIS = Path(__file__).resolve().parent.parent
STATIC = BASIS / "static"

# Szenen-Videos: die fertigen Clips (hochgeladen vom Schnittwerkzeug am PC).
# Gehoeren NICHT unter den StaticFiles-Mount - Auslieferung nur ueber
# /api/clips/{id}/video mit Rollen-/Zuordnungspruefung. Nicht im Repo (.gitignore).
MEDIA_CLIPS = BASIS / "media" / "clips"
# Selbst hochgeladene Portraits (<spieler_id>.jpg), ebenfalls nur ueber die API.
MEDIA_PORTRAITS = BASIS / "media" / "portraits"
# Spielvideos (ganze Spiele) und kurze Szenen-Clips, am PC aus dem Spielvideo geschnitten.
# Handys laden Clips in Sekunden, das ganze Spielvideo dauert ueber Tailscale Funnel zu lange.
MEDIA_SPIELE = BASIS / "media" / "spiele"
MEDIA_SZENEN = BASIS / "media" / "szenen"

for _ordner in (MEDIA_CLIPS, MEDIA_PORTRAITS, MEDIA_SPIELE, MEDIA_SZENEN):
    _ordner.mkdir(parents=True, exist_ok=True)
