"""ELO-Berechnung fuer Trainingsspiele.

Individuelle Variante: jede Spielerin wird behandelt, als haette sie
1-gegen-1 gegen den ELO-Durchschnitt des Gegnerteams gespielt. Eine starke
Spielerin im Siegerteam gewinnt daher wenig, eine schwaechere viel.
"""

from __future__ import annotations

from statistics import mean

# Start-Werte je Stufe (Seeding, damit Teams von Beginn an fair sind)
STUFEN: dict[str, int] = {
    "stark": 1150,
    "mittel": 1000,
    "schwach": 850,
}
START_ELO_DEFAULT = STUFEN["mittel"]

# K-Faktor: hoch waehrend der Kalibrierung, danach ruhiger.
K_PROVISORISCH = 40
K_STANDARD = 20
KALIBRIERUNGS_SPIELE = 10

# Ergebnis -> Score fuer Team A (Zwei-Team-Fall)
_SCORE_A = {"A": 1.0, "U": 0.5, "B": 0.0}

# Ergebnis-Buchstabe -> Index des Siegerteams. 'U' = unentschieden.
BUCHSTABEN = "ABCD"
MAX_TEAMS = len(BUCHSTABEN)


def k_faktor(spiele_gesamt: int) -> int:
    """Hoeheres K in den ersten Spielen, damit sich der Wert schnell einpendelt."""
    return K_PROVISORISCH if spiele_gesamt < KALIBRIERUNGS_SPIELE else K_STANDARD


def erwartung(elo: float, gegner_schnitt: float) -> float:
    """Erwarteter Score (0..1) einer Spielerin gegen den Gegnerteam-Schnitt."""
    return 1.0 / (1.0 + 10 ** ((gegner_schnitt - elo) / 400.0))


def team_schnitt(spieler: list[dict]) -> float:
    return mean(p["elo"] for p in spieler)


def berechne_spiel_mehrere(teams: list[list[dict]], ergebnis: str) -> dict[int, int]:
    """Liefert je Spieler-ID das ELO-Delta - fuer ZWEI BIS VIER Teams.

    Jede Spielerin wird gegen **jedes andere Team einzeln** gerechnet und der
    Schnitt daraus genommen. Gegen das Siegerteam gilt Score 0, als Sieger
    gegen jedes andere Team 1; zwei Teams, die beide verloren haben, spielen
    gegeneinander unentschieden (0.5). ``ergebnis`` ist der Buchstabe des
    Siegerteams ('A'..'D') oder 'U'.

    Warum paarweise und nicht gegen einen Topf aus allen anderen: bei drei
    Teams gibt es einen Sieger und zwei Verlierer. Wuerde man einfach 1 bzw. 0
    vergeben, verlieren in Summe alle - die Werte saeckten mit der Zeit ab.
    Paarweise bleibt die Summe der Aenderungen wie gehabt bei rund null.

    Bei genau zwei Teams ist es rechnerisch exakt die alte Formel (es gibt nur
    ein anderes Team). Bestehende Spiele ergeben also unveraenderte Werte.
    """
    if len(teams) < 2:
        raise ValueError("Es braucht mindestens zwei Teams.")
    if len(teams) > MAX_TEAMS:
        raise ValueError(f"Hoechstens {MAX_TEAMS} Teams.")
    if any(not t for t in teams):
        raise ValueError("Jedes Team braucht mindestens eine Spielerin.")
    if ergebnis != "U":
        if ergebnis not in BUCHSTABEN[:len(teams)]:
            raise ValueError(
                f"Ergebnis muss 'U' oder einer von "
                f"{list(BUCHSTABEN[:len(teams)])} sein, nicht {ergebnis!r}"
            )
    sieger = None if ergebnis == "U" else BUCHSTABEN.index(ergebnis)

    schnitte = [team_schnitt(t) for t in teams]
    gegner = len(teams) - 1

    roh: dict[int, float] = {}
    for i, team in enumerate(teams):
        for p in team:
            summe = 0.0
            for j in range(len(teams)):
                if j == i:
                    continue
                if sieger is None:
                    s = 0.5                       # unentschieden fuer alle
                elif sieger == i:
                    s = 1.0                       # ich habe gewonnen
                elif sieger == j:
                    s = 0.0                       # gegen den Sieger verloren
                else:
                    s = 0.5                       # beide verloren -> Remis
                summe += s - erwartung(p["elo"], schnitte[j])
            roh[p["id"]] = k_faktor(p["spiele_gesamt"]) * summe / gegner

    if len(teams) == 2:
        # Zwei Teams: einzeln runden - genau wie bisher. Die bestehenden Spiele
        # sollen sich durch den Umbau nicht um einen einzigen Punkt aendern.
        return {i: round(v) for i, v in roh.items()}
    return _runde_summentreu(roh)


def _runde_summentreu(roh: dict[int, float]) -> dict[int, int]:
    """Rundet die Deltas so, dass ihre Summe der gerundeten Gesamtsumme
    entspricht.

    Ohne das wandert bei vier Teams jedes Mal ein kleiner Betrag ins System
    (Sieger +10, drei Verlierer je -3,33 -> gerundet -3): pro Spiel gut drei
    Punkte, die sich ueber eine Saison summieren. Korrigiert werden die
    Eintraege mit dem groessten Rundungsverlust.
    """
    gerundet = {i: round(v) for i, v in roh.items()}
    rest = round(sum(roh.values())) - sum(gerundet.values())
    if rest:
        richtung = 1 if rest > 0 else -1
        kandidaten = sorted(roh, key=lambda i: (roh[i] - gerundet[i]) * richtung, reverse=True)
        for i in kandidaten[:abs(rest)]:
            gerundet[i] += richtung
    return gerundet


def berechne_spiel(team_a: list[dict], team_b: list[dict], ergebnis: str) -> dict[int, int]:
    """Zwei Teams - unveraendertes Verhalten, gerechnet ueber die allgemeine
    Funktion oben. ``ergebnis`` ist "A", "U" (unentschieden) oder "B".
    """
    if ergebnis not in _SCORE_A:
        raise ValueError(f"Ergebnis muss 'A', 'U' oder 'B' sein, nicht {ergebnis!r}")
    if not team_a or not team_b:
        raise ValueError("Beide Teams brauchen mindestens eine Spielerin.")
    return berechne_spiel_mehrere([team_a, team_b], ergebnis)
