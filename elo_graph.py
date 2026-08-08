"""ELO-Verlaufsdiagramme (PNG) je Spielerin, gezeichnet mit Pillow.

Die PNGs landen unter static/graphs/<id>.png und werden von der App unter
/graphs/<id>.png ausgeliefert. anytype_sync.py bettet sie per Bild-URL in die
Anytype-Objekte ein (Anytype laedt das Bild und speichert es intern).
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import db

GRAPH_DIR = Path(__file__).with_name("static") / "graphs"

GRUEN = "#1f7a6d"
TEXT = "#23201c"
GRAU = "#8a857d"
BG = "#ffffff"


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)      # Pillow >= 10.1
    except TypeError:
        return ImageFont.load_default()


def verlauf(conn, spieler_id: int, aktuelle_elo: int) -> list[tuple[str, int]]:
    """Zeitreihe [(label, elo), ...]: Startwert + ELO nach jedem Spiel."""
    rows = conn.execute(
        "SELECT v.elo_vorher, v.elo_nachher, s.datum FROM elo_verlauf v "
        "JOIN spiele s ON s.id = v.spiel_id "
        "WHERE v.spieler_id = ? ORDER BY v.spiel_id, v.id",
        (spieler_id,),
    ).fetchall()
    if not rows:
        return [("Start", aktuelle_elo)]
    punkte = [("Start", rows[0]["elo_vorher"])]
    for r in rows:
        d = r["datum"] or ""
        lbl = f"{d[8:10]}.{d[5:7]}." if len(d) >= 10 else "?"
        punkte.append((lbl, r["elo_nachher"]))
    return punkte


def zeichne(name: str, punkte: list[tuple[str, int]], pfad: Path, aktuelle_elo: int) -> None:
    W, H = 640, 320
    ml, mr, mt, mb = 55, 20, 46, 42
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    f_title, f = _font(19), _font(13)

    d.text((ml, 12), f"{name} — ELO {aktuelle_elo}", fill=TEXT, font=f_title)

    x0, y0, x1, y1 = ml, mt, W - mr, H - mb
    elos = [e for _, e in punkte]
    lo, hi = min(elos), max(elos)
    if hi == lo:
        lo, hi = lo - 20, hi + 20
    spanne = hi - lo
    lo -= spanne * 0.12
    hi += spanne * 0.12

    def X(i: int) -> float:
        return x0 if len(punkte) == 1 else x0 + (x1 - x0) * i / (len(punkte) - 1)

    def Y(e: float) -> float:
        return y1 - (y1 - y0) * (e - lo) / (hi - lo)

    # Gitter + y-Beschriftung
    for e in (lo, (lo + hi) / 2, hi):
        yy = Y(e)
        d.line([(x0, yy), (x1, yy)], fill="#eeeeee")
        d.text((6, yy - 7), str(round(e)), fill=GRAU, font=f)
    # Achsen
    d.line([(x0, y0), (x0, y1)], fill="#cccccc")
    d.line([(x0, y1), (x1, y1)], fill="#cccccc")

    pts = [(X(i), Y(e)) for i, (_, e) in enumerate(punkte)]
    if len(pts) >= 2:
        d.line(pts, fill=GRUEN, width=3)
    for px, py in pts:
        d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=GRUEN)

    # x-Beschriftung: erster und letzter Punkt
    d.text((x0, y1 + 6), str(punkte[0][0]), fill=GRAU, font=f)
    if len(punkte) > 1:
        d.text((x1 - 46, y1 + 6), str(punkte[-1][0]), fill=GRAU, font=f)
    else:
        d.text(((x0 + x1) / 2 - 45, (y0 + y1) / 2), "noch keine Spiele",
               fill=GRAU, font=f)

    pfad.parent.mkdir(parents=True, exist_ok=True)
    img.save(pfad)


def erzeuge_fuer_alle(conn) -> int:
    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in db.rangliste(conn):
        punkte = verlauf(conn, p["id"], p["elo"])
        zeichne(p["name"], punkte, GRAPH_DIR / f"{p['id']}.png", p["elo"])
        n += 1
    return n


if __name__ == "__main__":
    conn = db.verbinde()
    db.init_db(conn)
    n = erzeuge_fuer_alle(conn)
    conn.close()
    print(f"{n} Diagramme erzeugt in {GRAPH_DIR}")
