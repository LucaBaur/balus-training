"""Fragen und Kommentare unter Videos."""

from __future__ import annotations

import sqlite3

from .zeit import _utc_z


def _kommentar_zahlen(conn: sqlite3.Connection) -> dict[str, int]:
    """ziel ("clip:5", "szene:12", ...) -> Anzahl der Hauptkommentare (Antworten zaehlen nicht)."""
    return dict(conn.execute("SELECT ziel, COUNT(*) FROM video_kommentar "
                             "WHERE antwort_auf IS NULL GROUP BY ziel").fetchall())


# ------------------------------------------------------- Video-Kommentare ----
#  Siehe Tabelle 'video_kommentar'. Ob jemand das Video ueberhaupt sehen darf,
#  prueft der Aufrufer (routen/kommentare.py) - hier geht es nur um die Sichtbarkeit je Kommentar.

KOMMENTAR_MAX_ZEICHEN = 1000
KOMMENTAR_MAX_PRO_STUNDE = 30


def _kommentar_sichtbar(k, benutzer: dict) -> bool:
    return (benutzer["rolle"] == "trainer" or not k["nur_trainer"]
            or k["privat_fuer"] == benutzer["id"])


def kommentare_fuer(conn: sqlite3.Connection, ziel: str, benutzer: dict) -> list[dict]:
    rows = conn.execute(
        "SELECT k.id, k.benutzer_id, k.text, k.antwort_auf, k.nur_trainer, k.privat_fuer, "
        "       k.erstellt_am, b.name, b.rolle "
        "FROM video_kommentar k JOIN benutzer b ON b.id = k.benutzer_id "
        "WHERE k.ziel = ? ORDER BY k.id", (ziel,)).fetchall()
    return [{"id": k["id"], "name": k["name"], "trainer": k["rolle"] == "trainer",
             "eigene": k["benutzer_id"] == benutzer["id"], "text": k["text"],
             "antwort_auf": k["antwort_auf"], "nur_trainer": bool(k["nur_trainer"]),
             "zeit": _utc_z(k["erstellt_am"])}
            for k in rows if _kommentar_sichtbar(k, benutzer)]


def kommentar_anlegen(conn: sqlite3.Connection, ziel: str, benutzer: dict, text: str,
                      nur_trainer: bool, antwort_auf: int | None) -> dict:
    """Legt einen Kommentar an. Wirft ValueError mit lesbarer Meldung, wenn er nicht
    zulaessig ist. Gibt {id, nur_trainer, eltern_benutzer} zurueck (fuer die Benachrichtigung)."""
    text = (text or "").strip()[:KOMMENTAR_MAX_ZEICHEN]
    if not text:
        raise ValueError("Der Kommentar ist leer.")
    n = conn.execute("SELECT COUNT(*) FROM video_kommentar WHERE benutzer_id = ? "
                     "AND erstellt_am > datetime('now', '-1 hour')", (benutzer["id"],)).fetchone()[0]
    if n >= KOMMENTAR_MAX_PRO_STUNDE:
        raise ValueError("Zu viele Kommentare in kurzer Zeit – bitte kurz warten.")
    ist_trainer = benutzer["rolle"] == "trainer"
    privat_fuer = None
    eltern_benutzer = None
    if antwort_auf is not None:
        p = conn.execute("SELECT * FROM video_kommentar WHERE id = ?", (antwort_auf,)).fetchone()
        if p is None or p["ziel"] != ziel or not _kommentar_sichtbar(p, benutzer):
            raise ValueError("Auf diesen Kommentar kann nicht geantwortet werden.")
        eltern_benutzer = p["benutzer_id"]
        antwort_auf = p["antwort_auf"] or p["id"]          # immer an den Ursprung haengen
        if p["nur_trainer"]:                                # privater Faden bleibt privat
            nur_trainer, privat_fuer = True, p["privat_fuer"]
        elif nur_trainer and not ist_trainer:
            privat_fuer = benutzer["id"]
    elif nur_trainer and not ist_trainer:
        privat_fuer = benutzer["id"]
    cur = conn.execute(
        "INSERT INTO video_kommentar (ziel, benutzer_id, text, antwort_auf, nur_trainer, privat_fuer) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (ziel, benutzer["id"], text, antwort_auf, 1 if nur_trainer else 0, privat_fuer))
    conn.commit()
    return {"id": int(cur.lastrowid), "nur_trainer": bool(nur_trainer),
            "eltern_benutzer": eltern_benutzer}


def kommentar_loeschen(conn: sqlite3.Connection, kid: int, benutzer: dict) -> bool:
    """Eigene Kommentare darf jede(r) loeschen, alle der Trainer. Antworten fallen mit weg."""
    r = conn.execute("SELECT benutzer_id FROM video_kommentar WHERE id = ?", (kid,)).fetchone()
    if r is None or not (benutzer["rolle"] == "trainer" or r["benutzer_id"] == benutzer["id"]):
        return False
    conn.execute("DELETE FROM video_kommentar WHERE id = ?", (kid,))
    conn.commit()
    return True


def _video_existiert(conn: sqlite3.Connection, ziel: str) -> bool:
    tabelle = {"clip": "video_clip", "szene": "spiel_szene_clip", "spiel": "spiel_analyse"}.get(
        ziel.partition(":")[0])
    kennung = ziel.partition(":")[2]
    return bool(tabelle and kennung.isdigit() and conn.execute(
        f"SELECT 1 FROM {tabelle} WHERE id = ?", (int(kennung),)).fetchone())


def offene_fragen(conn: sqlite3.Connection) -> list[dict]:
    """Trainer-Sicht: Videos mit Fragen oder Kommentaren von Spielerinnen, die der Trainer
    noch nicht beantwortet hat. Ein Faden (Kommentar + Antworten) ist offen, wenn seine
    LETZTE Nachricht nicht vom Trainer stammt - schreibt die Spielerin nach der Antwort
    noch einmal, ist er wieder offen. Neueste Videos zuerst; je Video eine Zeile."""
    faeden: dict[int, sqlite3.Row] = {}
    for k in conn.execute(
            "SELECT k.id, k.ziel, k.antwort_auf, k.erstellt_am, b.name, b.rolle, b.aktiv "
            "FROM video_kommentar k JOIN benutzer b ON b.id = k.benutzer_id ORDER BY k.id"):
        faeden[k["antwort_auf"] or k["id"]] = k                  # spaetere Nachricht ueberschreibt
    je_video: dict[str, dict] = {}
    for letzte in faeden.values():
        if letzte["rolle"] == "trainer" or not letzte["aktiv"]:
            continue
        v = je_video.setdefault(letzte["ziel"], {"ziel": letzte["ziel"], "anzahl": 0, "von": [],
                                                 "_id": 0, "zuletzt": None})
        v["anzahl"] += 1
        if letzte["name"] not in v["von"]:
            v["von"].append(letzte["name"])
        if letzte["id"] > v["_id"]:
            v["_id"], v["zuletzt"] = letzte["id"], _utc_z(letzte["erstellt_am"])
    aus = []
    for v in sorted(je_video.values(), key=lambda x: -x["_id"]):
        if not _video_existiert(conn, v["ziel"]):
            continue
        info = conn.execute("SELECT info FROM nutzung WHERE ziel = ? AND info IS NOT NULL "
                            "ORDER BY id DESC LIMIT 1", (v["ziel"],)).fetchone()
        v["titel"] = info["info"] if info else "Video"
        del v["_id"]
        aus.append(v)
    return aus
