"""Schneller End-to-End-Test des Kerns (ohne Server/App).

Legt eine temporaere Datenbank an, seedet ein paar Spielerinnen per Stufe,
generiert faire Teams, traegt ein Spiel ein und zeigt die Rangliste.

Aufruf:  python demo.py
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import db
import teams


def zeile(p: dict) -> str:
    return f"  {p['name']:<12} {p['position']:<4} ELO {p['elo']:>5}  ({p['spiele_gesamt']} Sp.)"


def main() -> None:
    pfad = Path(tempfile.gettempdir()) / "elo_demo.db"
    if pfad.exists():
        pfad.unlink()
    conn = db.verbinde(pfad)
    db.init_db(conn)

    # Seeding per Stufe
    kader = [
        ("Anna", "stark", "Feld"),
        ("Bea", "stark", "Tor"),
        ("Clara", "mittel", "Feld"),
        ("Dana", "mittel", "Feld"),
        ("Emma", "mittel", "Tor"),
        ("Finja", "schwach", "Feld"),
        ("Greta", "schwach", "Feld"),
        ("Hanna", "mittel", "Feld"),
    ]
    for name, stufe, pos in kader:
        db.spieler_anlegen(conn, name, stufe=stufe, position=pos)

    anwesend = db.aktive_spieler(conn)
    print(f"Anwesend: {len(anwesend)} Spielerinnen\n")

    team_a, team_b = teams.teams_generieren(anwesend)
    print(f"Team A (Schnitt {sum(p['elo'] for p in team_a)/len(team_a):.0f}):")
    for p in team_a:
        print(zeile(p))
    print(f"Team B (Schnitt {sum(p['elo'] for p in team_b)/len(team_b):.0f}):")
    for p in team_b:
        print(zeile(p))

    # Team B gewinnt
    deltas, _ = db.spiel_eintragen(
        conn,
        [p["id"] for p in team_a],
        [p["id"] for p in team_b],
        ergebnis="B",
    )
    print("\nErgebnis: Team B gewinnt. Deltas:")
    namen = {p["id"]: p["name"] for p in anwesend}
    for pid, d in deltas.items():
        print(f"  {namen[pid]:<12} {d:+d}")

    print("\nRangliste:")
    for i, p in enumerate(db.rangliste(conn), 1):
        print(f"  {i:>2}. {p['name']:<12} ELO {p['elo']:>5}")

    conn.close()


if __name__ == "__main__":
    main()
