"""Erzeugt die PWA-Icons: ein stilisierter Handball (grün mit hellen Nähten)
auf hellem Kachel-Hintergrund.

Nutzt Pillow (im Projekt-venv vorhanden, da elo_graph.py es ebenfalls braucht)
und rendert 4x hoch, um die Kanten sauber zu glätten.

Aufruf:  python make_icons.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

SS = 4                              # Supersampling für glatte Kanten
CREAM = (244, 241, 234)            # heller Hintergrund / Nähte
GREEN = (31, 122, 109)             # Markengrün (Ball)


def _icon(groesse: int, pfad: Path) -> None:
    S = groesse * SS
    img = Image.new("RGB", (S, S), CREAM)
    d = ImageDraw.Draw(img)

    cx = cy = S / 2
    R = S * 0.40                    # Ball-Radius (Durchmesser 0,8·S → maskable-safe)
    w = max(1, int(S * 0.022))      # Naht-Breite

    # Ball
    d.ellipse([cx - R, cy - R, cx + R, cy + R], fill=GREEN)

    # Gebogene Nähte (Kugel-Optik) in Creme. Zwei „Meridiane" (senkrechte Ellipse)
    # und zwei „Breitengrade" (waagerechte Ellipse) lassen den grünen Kreis als
    # 3D-Ball lesen. Ragt eine Naht über den Ballrand hinaus, ist sie
    # creme-auf-creme = unsichtbar – deshalb ist kein Clipping nötig.
    naht = CREAM
    m = 0.48 * R                    # halbe Breite/Höhe der inneren Ellipsen
    d.ellipse([cx - m, cy - R, cx + m, cy + R], outline=naht, width=w)   # Längsnaht
    d.ellipse([cx - R, cy - m, cx + R, cy + m], outline=naht, width=w)   # Quernaht

    img = img.resize((groesse, groesse), Image.LANCZOS)
    img.save(pfad)
    print("geschrieben:", pfad.name)


if __name__ == "__main__":
    basis = Path(__file__).with_name("static")
    _icon(192, basis / "icon-192.png")
    _icon(512, basis / "icon-512.png")
