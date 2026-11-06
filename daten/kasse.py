"""Mannschaftskasse (Amt Kassenwart): Kassenbuch mit Forderungen, Einzahlungen, Ausgaben, Einnahmen.

Alle Regeln, die immer gelten, stehen hier: Betraege sind ganze Cent und positiv, die Richtung
steckt in der Art, Buchungen werden nie geloescht (nur storniert) und ein Token macht doppeltes
Absenden harmlos. Wer buchen darf, prueft die Route (routen/kasse.py ueber das Recht "kasse").

Namen beginnen mit `kasse_`, weil die Fassade db.py alle Datenmodule mit `import *` zusammenfuehrt.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date, datetime

from .zeit import _berlin

KASSE_ARTEN = ("forderung", "einzahlung", "ausgabe", "einnahme")
KASSE_MIT_SPIELERIN = ("forderung", "einzahlung")        # diese beiden betreffen eine Spielerin
KASSE_MAX_CENT = 1_000_000                               # 10.000 EUR: faengt Tippfehler (Komma vergessen) ab
KASSE_MAX_TEXT = 120
KASSE_MAX_TOKEN = 64
KASSE_MAX_ZEILEN = 500                                   # so viele Buchungen liefert die Uebersicht (neueste zuerst)
_DATUM = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#  Strafenkatalog der Frauenmannschaft. Reine Eingabehilfe: die Oberflaeche fuellt Text und Betrag
#  vor, gebucht wird weiter ueber kasse_buchen (das alle Regeln selbst prueft). `cent` None heisst
#  „Kasten“ (Sachstrafe, Wert traegt die Kassenwartin von Hand ein); `einheit` heisst: Betrag je Min/Teil.
#  Die Strafen fuer Trainer gelten doppelt, das rechnet die Oberflaeche ueber ein Feld.
def _k(key, label, cent=None, einheit=None):
    return {"key": key, "label": label, "cent": cent, "einheit": einheit}


KASSE_KATALOG = (
    _k("beitrag", "Monatsbeitrag (fällig bis zum 7.)", 500),
    _k("beitrag_spaet", "Monatsbeitrag nicht innerhalb 1 Woche bezahlt", 500),
    _k("training_nicht_abgesagt", "Training nicht abgesagt", 1500),
    _k("training_spaet_abgesagt", "Training zu spät abgesagt (24 h vorher)", 500),
    _k("spiel_nicht_abgesagt", "Spiel nicht zu-/abgesagt", 4000),
    _k("spiel_spaet_abgesagt", "Spiel zu spät abgesagt (1 Woche vorher)", 2000),
    _k("treffpunkt_spaet", "Spieltreffpunkt zu spät", 300, "Min"),
    _k("trikots_vergessen", "Trikots vergessen", 7000),
    _k("kurze_socken", "Kurze Socken im Spiel", 1000),
    _k("aufwaermshirt", "Aufwärmshirt vergessen", 1000),
    _k("gelb_meckern", "Gelb wegen Meckern (gilt nicht für Trainer)", 1000),
    _k("zwei_min_meckern", "2 Min wegen Meckern oder Ball wegwerfen (Kasten)"),
    _k("rot", "Glatte Rote Karte", 4500),
    _k("trinken_trikot", "Trinken/Rauchen im Trikot", 1000),
    _k("bier_verschuettet", "Bier verschüttet (Kasten)"),
    _k("sachen_liegen_lassen", "Sachen liegen lassen", 200, "Teil"),
    _k("dienst_nicht_gemacht", "Dienst nicht gemacht, kein Ersatz gesucht oder unentschuldigt gefehlt", 6000),
    _k("dienst_spaet", "Dienst zu spät", 300, "Min"),
    _k("amt_vergessen", "Amt vergessen (Harz, Shampoo, Leibchen, Tape …)", 2000),
    _k("geburtstag", "Geburtstag, zum nächsten Training/Spiel (Kasten)"),
    _k("dummheit", "Dummheit", 333),
    _k("harzsuende", "Harzsünde (Anweisungen vom Putzwart nicht befolgt)", 1000),
)


def kasse_katalog() -> list[dict]:
    return [dict(k) for k in KASSE_KATALOG]


def kasse_heute() -> str:
    """Heutiges Datum in deutscher Zeit (der Server laeuft in UTC)."""
    return datetime.now(_berlin()).date().isoformat()


def kasse_buchen(conn: sqlite3.Connection, art: str, betrag_cent: int, text: str,
                 spieler_id: int | None, datum: str | None, autor: str,
                 token: str | None = None) -> tuple[int, bool]:
    """Legt eine Buchung an. Gibt (id, neu) zurueck; `neu` ist False, wenn das Token schon gebucht
    war (dann ist es dieselbe Buchung wie beim ersten Mal und es wird nichts doppelt angelegt)."""
    if art not in KASSE_ARTEN:
        raise ValueError("Unbekannte Art der Buchung.")
    if isinstance(betrag_cent, bool) or not isinstance(betrag_cent, int):
        raise ValueError("Der Betrag muss in ganzen Cent angegeben werden.")
    if betrag_cent <= 0:
        raise ValueError("Der Betrag muss größer als null sein.")
    if betrag_cent > KASSE_MAX_CENT:
        raise ValueError("Der Betrag ist zu hoch (höchstens 10.000 €). Komma vergessen?")
    text = " ".join((text or "").split())
    if not text:
        raise ValueError("Der Text fehlt.")
    if len(text) > KASSE_MAX_TEXT:
        raise ValueError(f"Der Text ist zu lang (höchstens {KASSE_MAX_TEXT} Zeichen).")
    if art in KASSE_MIT_SPIELERIN:
        if spieler_id is None:
            raise ValueError("Für diese Art gehört eine Spielerin dazu.")
    elif spieler_id is not None:
        raise ValueError("Ausgaben und Einnahmen gehören keiner Spielerin.")
    if datum is None or datum == "":
        datum = kasse_heute()
    elif not _DATUM.match(datum):
        raise ValueError("Das Datum muss JJJJ-MM-TT sein.")
    else:
        try:
            date.fromisoformat(datum)
        except ValueError:
            raise ValueError("Das Datum gibt es nicht.") from None
    if token is not None and (not token or len(token) > KASSE_MAX_TOKEN):
        raise ValueError("Ungültiges Token.")
    if spieler_id is not None and conn.execute("SELECT 1 FROM spieler WHERE id = ?", (spieler_id,)).fetchone() is None:
        raise LookupError("Spielerin nicht gefunden")

    if token is not None:
        vorhanden = conn.execute("SELECT id FROM kasse_buchung WHERE token = ?", (token,)).fetchone()
        if vorhanden:
            return int(vorhanden["id"]), False
    try:
        cur = conn.execute(
            "INSERT INTO kasse_buchung (art, betrag_cent, text, datum, spieler_id, erstellt_von, token) "
            "VALUES (?,?,?,?,?,?,?)", (art, betrag_cent, text, datum, spieler_id, autor, token))
    except sqlite3.IntegrityError:
        # Zwei gleiche Anfragen gleichzeitig: die andere war schneller. Dann gilt deren Buchung.
        conn.rollback()
        vorhanden = conn.execute("SELECT id FROM kasse_buchung WHERE token = ?", (token,)).fetchone()
        if vorhanden is None:
            raise
        return int(vorhanden["id"]), False
    conn.commit()
    return int(cur.lastrowid), True


def kasse_stornieren(conn: sqlite3.Connection, buchung_id: int, autor: str) -> bool:
    """Markiert die Buchung als storniert (sie bleibt im Kassenbuch sichtbar, zaehlt aber nicht mehr).
    True, wenn dabei etwas geaendert wurde; wiederholen aendert nichts."""
    r = conn.execute("SELECT storniert_am FROM kasse_buchung WHERE id = ?", (buchung_id,)).fetchone()
    if r is None:
        raise LookupError("Buchung nicht gefunden")
    if r["storniert_am"] is not None:
        return False
    conn.execute("UPDATE kasse_buchung SET storniert_am = datetime('now'), storniert_von = ? WHERE id = ?",
                 (autor, buchung_id))
    conn.commit()
    return True


def kasse_stand(conn: sqlite3.Connection) -> dict:
    """Kassenstand aus den nicht stornierten Buchungen. Forderungen zaehlen nicht: sie sind noch kein Geld."""
    r = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN art IN ('einzahlung','einnahme') THEN betrag_cent END), 0) AS ein, "
        "       COALESCE(SUM(CASE WHEN art = 'ausgabe' THEN betrag_cent END), 0) AS aus "
        "FROM kasse_buchung WHERE storniert_am IS NULL").fetchone()
    return {"kasse_cent": int(r["ein"] - r["aus"]), "einnahmen_cent": int(r["ein"]), "ausgaben_cent": int(r["aus"])}


def kasse_offen(conn: sqlite3.Connection) -> list[dict]:
    """Je Spielerin Forderungen, Einzahlungen und was noch offen ist (negativ = Guthaben).
    Wer das meiste schuldet, steht oben."""
    zeilen = [dict(r) for r in conn.execute(
        "SELECT s.id AS spieler_id, s.name, "
        "       COALESCE(SUM(CASE WHEN b.art = 'forderung'  THEN b.betrag_cent END), 0) AS forderung_cent, "
        "       COALESCE(SUM(CASE WHEN b.art = 'einzahlung' THEN b.betrag_cent END), 0) AS einzahlung_cent "
        "FROM kasse_buchung b JOIN spieler s ON s.id = b.spieler_id "
        "WHERE b.storniert_am IS NULL GROUP BY s.id")]
    for z in zeilen:
        z["offen_cent"] = z["forderung_cent"] - z["einzahlung_cent"]
    return sorted(zeilen, key=lambda z: (-z["offen_cent"], z["name"]))


def kasse_uebersicht(conn: sqlite3.Connection, spieler_id: int | None, alle: bool) -> dict:
    """Was die Anfragende sehen darf. Jede sieht den Kassenstand, die Buchungen der Kasse (Ausgaben,
    Einnahmen) und WER WIE VIEL SCHULDET (Wunsch der Mannschaft: offene Strafen sind oeffentlich).
    Wofuer jemand etwas schuldet, also die einzelnen Posten einer Spielerin, sieht nur sie selbst.
    `alle` (Kassenwart, Trainer) sieht jede Buchung und in der Offen-Liste auch die Einzelsummen und
    Guthaben."""
    sql = ("SELECT b.id, b.art, b.betrag_cent, b.text, b.datum, b.spieler_id, s.name AS spieler_name, "
           "       b.erstellt_von, b.storniert_am IS NOT NULL AS storniert "
           "FROM kasse_buchung b LEFT JOIN spieler s ON s.id = b.spieler_id ")
    args: tuple = ()
    if not alle:
        sql += "WHERE b.spieler_id IS NULL OR b.spieler_id = ? "
        args = (spieler_id,)
    sql += "ORDER BY b.datum DESC, b.id DESC LIMIT ?"
    buchungen = [dict(r) for r in conn.execute(sql, args + (KASSE_MAX_ZEILEN,))]
    for b in buchungen:
        b["storniert"] = bool(b["storniert"])

    offen = kasse_offen(conn)
    mein = None
    if spieler_id:
        eigene = next((o for o in offen if o["spieler_id"] == spieler_id), None)
        mein = eigene["offen_cent"] if eigene else 0
    stand = kasse_stand(conn)
    stand["offen_cent"] = sum(o["offen_cent"] for o in offen if o["offen_cent"] > 0)
    if not alle:
        # Nur echte Schulden und nur Name + Betrag: ein Guthaben geht niemanden etwas an.
        offen = [{"spieler_id": o["spieler_id"], "name": o["name"], "offen_cent": o["offen_cent"]}
                 for o in offen if o["offen_cent"] > 0]
    return {"stand": stand, "buchungen": buchungen, "mein_offen_cent": mein, "offen": offen}
