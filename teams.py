"""Faire Team-Aufteilung auf Basis der ELO-Werte.

Teilt die anwesenden Spielerinnen in zwei moeglichst gleich starke Teams.
Nebenbedingung: sind mindestens zwei Torhueterinnen anwesend, bekommt jedes
Team eine ab.
"""

from __future__ import annotations

import itertools
from statistics import mean

POSITION_TOR = "Tor"


def _schnitt(team: list[dict]) -> float:
    return mean(p["elo"] for p in team)


def teams_generieren(spieler: list[dict]) -> tuple[list[dict], list[dict]]:
    """Zwei Teams mit minimaler ELO-Differenz.

    spieler: Liste von Dicts mit ``id``, ``elo``, ``position``. Die Teamgroessen
    unterscheiden sich um hoechstens eine Spielerin. Bei >=2 Torhueterinnen
    bekommt jedes Team mindestens eine.
    """
    n = len(spieler)
    if n < 2:
        return list(spieler), []

    groesse_a = n // 2
    anzahl_tor = sum(1 for p in spieler if p["position"] == POSITION_TOR)
    tor_pflicht = anzahl_tor >= 2

    bestes: tuple[float, list[dict], list[dict]] | None = None
    indizes = range(n)
    for combo in itertools.combinations(indizes, groesse_a):
        combo_set = set(combo)
        team_a = [spieler[i] for i in combo]
        team_b = [spieler[i] for i in indizes if i not in combo_set]

        if tor_pflicht:
            if not any(p["position"] == POSITION_TOR for p in team_a):
                continue
            if not any(p["position"] == POSITION_TOR for p in team_b):
                continue

        diff = abs(_schnitt(team_a) - _schnitt(team_b))
        if bestes is None or diff < bestes[0]:
            bestes = (diff, team_a, team_b)

    if bestes is None:
        # Sollte nur passieren, wenn die Tor-Pflicht unerfuellbar ist -> ohne sie.
        return _ohne_tor_pflicht(spieler, groesse_a)
    return bestes[1], bestes[2]


def teams_generieren_n(spieler: list[dict], anzahl: int = 2) -> list[list[dict]]:
    """Zwei bis vier moeglichst gleich starke Teams.

    Bei zwei Teams bleibt es bei der bisherigen, vollstaendigen Suche. Ab drei
    Teams waere das zu teuer: dort wird zuerst gierig verteilt (Staerkste
    zuerst ins jeweils schwaechste Team) und danach durch Tauschen verbessert.
    Torhueterinnen werden reihum verteilt, damit moeglichst viele Teams eine
    haben.
    """
    anzahl = max(2, min(int(anzahl or 2), 4))
    if anzahl == 2:
        a, b = teams_generieren(spieler)
        return [a, b]
    if len(spieler) < anzahl:                       # zu wenige: je eine, Rest leer
        return [[p] for p in spieler] + [[] for _ in range(anzahl - len(spieler))]

    teams: list[list[dict]] = [[] for _ in range(anzahl)]
    torhueter = [p for p in spieler if p["position"] == POSITION_TOR]
    feld = [p for p in spieler if p["position"] != POSITION_TOR]
    for i, p in enumerate(sorted(torhueter, key=lambda p: -p["elo"])):
        teams[i % anzahl].append(p)

    max_groesse = -(-len(spieler) // anzahl)        # aufgerundet
    for p in sorted(feld, key=lambda p: -p["elo"]):
        kandidaten = [t for t in teams if len(t) < max_groesse] or teams
        ziel = min(kandidaten, key=lambda t: (len(t), sum(x["elo"] for x in t)))
        ziel.append(p)

    _verbessern(teams, min(anzahl, len(torhueter)))
    return teams


def _tor_abdeckung(teams: list[list[dict]]) -> int:
    return sum(1 for t in teams if any(p["position"] == POSITION_TOR for p in t))


def _spanne(teams: list[list[dict]]) -> float:
    schnitte = [_schnitt(t) for t in teams if t]
    return max(schnitte) - min(schnitte) if schnitte else 0.0


def _verbessern(teams: list[list[dict]], tor_ziel: int, runden: int = 40) -> None:
    """Tauscht paarweise Spielerinnen, solange das die Staerke-Spanne
    verkleinert und die Torhueter-Verteilung nicht verschlechtert."""
    for _ in range(runden):
        akt = _spanne(teams)
        bestes = None
        for i in range(len(teams)):
            for j in range(i + 1, len(teams)):
                for x in range(len(teams[i])):
                    for y in range(len(teams[j])):
                        teams[i][x], teams[j][y] = teams[j][y], teams[i][x]
                        neu, tore = _spanne(teams), _tor_abdeckung(teams)
                        teams[i][x], teams[j][y] = teams[j][y], teams[i][x]
                        if tore < tor_ziel or neu >= akt - 1e-9:
                            continue
                        if bestes is None or neu < bestes[0]:
                            bestes = (neu, i, j, x, y)
        if bestes is None:
            return
        _, i, j, x, y = bestes
        teams[i][x], teams[j][y] = teams[j][y], teams[i][x]


def _ohne_tor_pflicht(spieler: list[dict], groesse_a: int) -> tuple[list[dict], list[dict]]:
    n = len(spieler)
    indizes = range(n)
    bestes: tuple[float, list[dict], list[dict]] | None = None
    for combo in itertools.combinations(indizes, groesse_a):
        combo_set = set(combo)
        team_a = [spieler[i] for i in combo]
        team_b = [spieler[i] for i in indizes if i not in combo_set]
        diff = abs(_schnitt(team_a) - _schnitt(team_b))
        if bestes is None or diff < bestes[0]:
            bestes = (diff, team_a, team_b)
    assert bestes is not None
    return bestes[1], bestes[2]
