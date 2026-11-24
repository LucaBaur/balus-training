"""Drosselung falscher Anmeldungen (Rate Limiting) - statt der frueheren dauerhaften PIN-Sperre.

Warum nicht sperren? Die App ist ueber das Internet erreichbar (Tailscale Funnel). Wer nur den Namen einer
Spielerin oder des Trainers kennt, konnte deren PIN mit drei falschen Versuchen fuer immer loeschen
(Denial of Service). Eine Wartezeit schuetzt genauso vor dem Raten, laesst das Konto aber heil.

Drei Regeln, je Mandant (team_id) und mit gleitendem Zeitfenster - es zaehlen nur FEHLversuche:
  Name + Adresse   5 in 15 Minuten   ein Geraet, das einen Namen probiert
  Name (alle)     20 in 60 Minuten   ein Angreifer, der die Adressen wechselt
  Adresse (alle)  15 in 15 Minuten   ein Geraet, das viele Namen probiert
Obergrenze fuer ein Konto: 20 Versuche pro Stunde, also bei 4-stelliger PIN (10 000 Moeglichkeiten) rund
500 Stunden, selbst wenn sich der Angreifer ueber viele Adressen verteilt.
"""

from __future__ import annotations

import ipaddress
import math
import sqlite3
import time

__all__ = ["client_ip", "wartezeit", "login_wartezeit", "login_fehlschlag", "login_versuche_uebrig"]

#            (Fenster in Sekunden, Grenze)
REGEL_PAAR = (15 * 60, 5)
REGEL_NAME = (60 * 60, 20)
REGEL_IP = (15 * 60, 15)
AUFBEWAHREN = 2 * 3600          # laenger als das groesste Fenster; danach loescht der naechste Fehlversuch die Zeile
_LOOPBACK = {"127.0.0.1", "::1"}


def _name(name: str) -> str:
    return (name or "").strip().casefold()[:60]


def client_ip(verbindung: str | None, weitergeleitet: str | None) -> str:
    """Die Adresse des Besuchers.

    Hinter dem Funnel kommt jede Anfrage von 127.0.0.1 an; die echte Adresse steht im Header
    X-Forwarded-For. Dem Header wird NUR geglaubt, wenn die Verbindung selbst vom eigenen Rechner kommt
    (also vom Proxy) - sonst koennte jeder Besucher eine beliebige Adresse eintragen und die Drosselung
    umgehen. Der Proxy haengt die Adresse hinten an, deshalb zaehlt der LETZTE Eintrag; vorne darf der
    Besucher selbst etwas hineinschreiben."""
    if not verbindung:
        return "unbekannt"
    if verbindung in _LOOPBACK and weitergeleitet:
        letzte = weitergeleitet.split(",")[-1].strip()
        try:
            return str(ipaddress.ip_address(letzte))
        except ValueError:
            pass
    return verbindung


def wartezeit(paar: list[float], name: list[float], ip: list[float], jetzt: float) -> int:
    """Wie viele Sekunden muss gewartet werden? 0 = frei. Reine Rechnung auf Zeitstempel-Listen.

    Pro Regel: sind in den letzten `fenster` Sekunden mindestens `grenze` Fehlversuche, ist frei, sobald der
    `grenze`-juengste Fehlversuch das Fenster verlaesst. Gewartet wird auf die laengste der drei Regeln."""
    warte = 0.0
    for zeiten, (fenster, grenze) in ((paar, REGEL_PAAR), (name, REGEL_NAME), (ip, REGEL_IP)):
        neu = sorted((t for t in zeiten if jetzt - t < fenster), reverse=True)
        if len(neu) >= grenze:
            warte = max(warte, neu[grenze - 1] + fenster - jetzt)
    return math.ceil(warte) if warte > 0 else 0


def _zeiten(conn: sqlite3.Connection, team_id: int, spalte: str, wert: str, ab: float, **zusatz: str) -> list[float]:
    sql = f"SELECT zeit FROM login_versuche WHERE team_id = ? AND {spalte} = ? AND zeit > ?"
    args: list = [team_id, wert, ab]
    for k, v in zusatz.items():
        sql += f" AND {k} = ?"
        args.append(v)
    return [r["zeit"] for r in conn.execute(sql, args)]


def login_wartezeit(conn: sqlite3.Connection, team_id: int, ip: str, name: str, jetzt: float | None = None) -> int:
    """Sekunden, die diese Anfrage (Adresse + Name) noch warten muss. 0 = darf es versuchen."""
    jetzt = time.time() if jetzt is None else jetzt
    n = _name(name)
    ab = jetzt - max(REGEL_PAAR[0], REGEL_NAME[0], REGEL_IP[0])
    return wartezeit(_zeiten(conn, team_id, "name", n, ab, ip=ip),
                     _zeiten(conn, team_id, "name", n, ab),
                     _zeiten(conn, team_id, "ip", ip, ab), jetzt)


def login_fehlschlag(conn: sqlite3.Connection, team_id: int, ip: str, name: str, jetzt: float | None = None) -> None:
    """Einen Fehlversuch festhalten und dabei Altes wegraeumen (kein eigener Aufraeum-Job noetig)."""
    jetzt = time.time() if jetzt is None else jetzt
    conn.execute("DELETE FROM login_versuche WHERE zeit < ?", (jetzt - AUFBEWAHREN,))
    conn.execute("INSERT INTO login_versuche (team_id, ip, name, zeit) VALUES (?,?,?,?)",
                 (team_id, ip, _name(name), jetzt))
    conn.commit()


def login_versuche_uebrig(conn: sqlite3.Connection, team_id: int, ip: str, name: str, jetzt: float | None = None) -> int:
    """Wie viele Fehlversuche (Adresse + Name) bis zur Wartezeit noch frei sind - nur fuer die Meldung."""
    jetzt = time.time() if jetzt is None else jetzt
    fenster, grenze = REGEL_PAAR
    bisher = len([t for t in _zeiten(conn, team_id, "name", _name(name), jetzt - fenster, ip=ip) if jetzt - t < fenster])
    return max(0, grenze - bisher)
