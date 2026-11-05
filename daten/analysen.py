"""Spielanalysen aus Balu-Spielanalyse: Ereignisse, Spielzuege, Szenen-Clips."""

from __future__ import annotations

import sqlite3


# ------------------------------------------------------------ Spielanalysen ----
#  Ganzes Spielvideo + Ereignisse/Spielzuege aus "Balu-Spielanalyse".

def analyse_speichern(conn: sqlite3.Connection, extern_id: str, gegner: str,
                      datum: str | None, art: str | None, events: list[dict],
                      zuege: list[dict], erstellt_von: int | None) -> int:
    """Legt die Analyse an oder ersetzt Ereignisse/Spielzuege einer vorhandenen
    (gleiche extern_id). Das Video bleibt dabei erhalten. Spielerinnen-IDs, die
    es hier nicht gibt, werden zu NULL bzw. fallen aus der Zuordnung."""
    gueltig = {r["id"] for r in conn.execute("SELECT id FROM spieler")}
    sp = lambda x: x if x in gueltig else None          # noqa: E731
    r = conn.execute("SELECT id FROM spiel_analyse WHERE extern_id = ?", (extern_id,)).fetchone()
    if r:
        aid = int(r["id"])
        conn.execute("UPDATE spiel_analyse SET gegner = ?, datum = ?, art = ? WHERE id = ?",
                     (gegner, datum, art, aid))
        conn.execute("DELETE FROM spiel_event WHERE analyse_id = ?", (aid,))
        conn.execute("DELETE FROM spiel_zug WHERE analyse_id = ?", (aid,))   # Kaskade -> Zuordnung
    else:
        cur = conn.execute(
            "INSERT INTO spiel_analyse (extern_id, gegner, datum, art, erstellt_von) VALUES (?,?,?,?,?)",
            (extern_id, gegner, datum, art, erstellt_von))
        aid = int(cur.lastrowid)
    conn.executemany(
        "INSERT INTO spiel_event (analyse_id, typ, t, spieler_id, assist_id, detail, szene_key) "
        "VALUES (?,?,?,?,?,?,?)",
        [(aid, e["typ"], e["t"], sp(e.get("spieler_id")), sp(e.get("assist_id")), e.get("detail"),
          e.get("key")) for e in events])
    for z in zuege:
        cur = conn.execute(
            "INSERT INTO spiel_zug (analyse_id, name, t_start, t_ende, ampel, kommentar, szene_key) "
            "VALUES (?,?,?,?,?,?,?)",
            (aid, z["name"], z["t_start"], z["t_ende"], z["ampel"], z.get("kommentar") or None,
             z.get("key")))
        conn.executemany(
            "INSERT OR IGNORE INTO spiel_zug_spieler (zug_id, spieler_id) VALUES (?, ?)",
            [(int(cur.lastrowid), s) for s in z.get("spieler_ids", []) if s in gueltig])
    conn.commit()
    return aid


def analyse_datei_setzen(conn: sqlite3.Connection, aid: int, datei: str) -> str | None:
    """Setzt den Videodateinamen und gibt den alten zurueck (zum Aufraeumen)."""
    r = conn.execute("SELECT datei FROM spiel_analyse WHERE id = ?", (aid,)).fetchone()
    alt = r["datei"] if r else None
    conn.execute("UPDATE spiel_analyse SET datei = ? WHERE id = ?", (datei, aid))
    conn.commit()
    return alt


def analyse_nach_id(conn: sqlite3.Connection, aid: int) -> dict | None:
    r = conn.execute("SELECT * FROM spiel_analyse WHERE id = ?", (aid,)).fetchone()
    return dict(r) if r else None


def analysen_liste(conn: sqlite3.Connection, spieler_id: int | None = None,
                   alle: bool = False) -> list[dict]:
    """Alle Analysen (Trainer) oder nur die, in denen die Spielerin vorkommt.
    Mit `alle=True` (und spieler_id) kommen ALLE Analysen, dazu je Spiel die
    Zahl der Ereignisse (`meine_events`) und Spielzuege (`meine_zuege`), an denen
    die Spielerin beteiligt ist - 0/0 heisst: sie kommt nicht vor."""
    sql = ("SELECT a.id, a.gegner, a.datum, a.art, a.datei IS NOT NULL AS video_da, "
           "(SELECT COUNT(*) FROM spiel_event e WHERE e.analyse_id = a.id) AS events, "
           "(SELECT COUNT(*) FROM spiel_zug z WHERE z.analyse_id = a.id) AS zuege")
    params: tuple = ()
    if spieler_id is not None and alle:
        sql += (", (SELECT COUNT(*) FROM spiel_event e WHERE e.analyse_id = a.id "
                "AND (e.spieler_id = ?1 OR e.assist_id = ?1)) AS meine_events, "
                "(SELECT COUNT(*) FROM spiel_zug z JOIN spiel_zug_spieler s ON s.zug_id = z.id "
                "WHERE z.analyse_id = a.id AND s.spieler_id = ?1) AS meine_zuege")
        params = (spieler_id,)
    sql += " FROM spiel_analyse a"
    if spieler_id is not None and not alle:
        sql += (" WHERE EXISTS (SELECT 1 FROM spiel_event e WHERE e.analyse_id = a.id "
                "AND (e.spieler_id = ?1 OR e.assist_id = ?1)) "
                "OR EXISTS (SELECT 1 FROM spiel_zug z JOIN spiel_zug_spieler s ON s.zug_id = z.id "
                "WHERE z.analyse_id = a.id AND s.spieler_id = ?1)")
        params = (spieler_id,)
    sql += " ORDER BY COALESCE(a.datum, '') DESC, a.id DESC"
    return [dict(r) | {"video_da": bool(r["video_da"])} for r in conn.execute(sql, params)]


def analyse_inhalt(conn: sqlite3.Connection, aid: int,
                   spieler_id: int | None = None) -> dict:
    """Ereignisse + Spielzuege einer Analyse; mit spieler_id nur die, an denen
    die Spielerin beteiligt ist (Torschuetzin/Vorlage bzw. im Spielzug)."""
    ev_sql = ("SELECT e.id, e.typ, e.t, e.spieler_id, e.assist_id, e.detail, c.id AS clip_id "
              "FROM spiel_event e LEFT JOIN spiel_szene_clip c "
              "ON c.analyse_id = e.analyse_id AND c.szene_key = e.szene_key "
              "WHERE e.analyse_id = ?")
    ev_par: list = [aid]
    if spieler_id is not None:
        ev_sql += " AND (e.spieler_id = ? OR e.assist_id = ?)"
        ev_par += [spieler_id, spieler_id]
    events = [dict(r) for r in conn.execute(ev_sql + " ORDER BY e.t", ev_par)]

    zuege = [dict(r) for r in conn.execute(
        "SELECT z.id, z.name, z.t_start, z.t_ende, z.ampel, z.kommentar, c.id AS clip_id "
        "FROM spiel_zug z LEFT JOIN spiel_szene_clip c "
        "ON c.analyse_id = z.analyse_id AND c.szene_key = z.szene_key "
        "WHERE z.analyse_id = ? ORDER BY z.t_start", (aid,))]
    zuord: dict[int, list[int]] = {}
    for r in conn.execute(
            "SELECT s.zug_id, s.spieler_id FROM spiel_zug_spieler s "
            "JOIN spiel_zug z ON z.id = s.zug_id WHERE z.analyse_id = ?", (aid,)):
        zuord.setdefault(r["zug_id"], []).append(r["spieler_id"])
    for z in zuege:
        z["spieler_ids"] = zuord.get(z["id"], [])
    if spieler_id is not None:
        zuege = [z for z in zuege if spieler_id in z["spieler_ids"]]
    return {"events": events, "zuege": zuege}


def analyse_beteiligte(conn: sqlite3.Connection, aid: int) -> list[int]:
    """Alle Spielerinnen, die in dieser Analyse vorkommen (Torschuetzin, Vorlage, Spielzug)."""
    ids: set[int] = set()
    for r in conn.execute("SELECT spieler_id, assist_id FROM spiel_event WHERE analyse_id = ?", (aid,)):
        ids.update(x for x in (r["spieler_id"], r["assist_id"]) if x)
    for r in conn.execute(
            "SELECT s.spieler_id FROM spiel_zug_spieler s JOIN spiel_zug z ON z.id = s.zug_id "
            "WHERE z.analyse_id = ?", (aid,)):
        ids.add(r["spieler_id"])
    return sorted(ids)


def analyse_loeschen(conn: sqlite3.Connection, aid: int) -> tuple[str, list[str]] | None:
    """Loescht die Analyse (Kaskade). Gibt Videodatei und Clip-Dateien zurueck, damit der
    Aufrufer sie von der Platte entfernen kann; None, wenn es die Analyse nicht gibt."""
    r = conn.execute("SELECT datei FROM spiel_analyse WHERE id = ?", (aid,)).fetchone()
    if not r:
        return None
    clips = [x["datei"] for x in conn.execute(
        "SELECT datei FROM spiel_szene_clip WHERE analyse_id = ?", (aid,))]
    conn.execute("DELETE FROM spiel_analyse WHERE id = ?", (aid,))     # Kaskade
    conn.commit()
    return (r["datei"] or ""), clips


# ---- Szenen-Clips ---------------------------------------------------------------

def szene_clips_liste(conn: sqlite3.Connection, aid: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT id, szene_key AS key, von, bis FROM spiel_szene_clip "
        "WHERE analyse_id = ? ORDER BY szene_key", (aid,))]


def szene_clip_speichern(conn: sqlite3.Connection, aid: int, key: str, datei: str,
                         von: float, bis: float) -> str | None:
    """Legt den Clip an oder ersetzt ihn. Gibt den Namen der ALTEN Datei zurueck (oder None)."""
    alt = conn.execute("SELECT datei FROM spiel_szene_clip WHERE analyse_id = ? AND szene_key = ?",
                       (aid, key)).fetchone()
    conn.execute(
        "INSERT INTO spiel_szene_clip (analyse_id, szene_key, datei, von, bis) VALUES (?,?,?,?,?) "
        "ON CONFLICT (analyse_id, szene_key) DO UPDATE SET datei = excluded.datei, "
        "von = excluded.von, bis = excluded.bis, erstellt_am = datetime('now')",
        (aid, key, datei, von, bis))
    conn.commit()
    return alt["datei"] if alt else None


def szene_clip_nach_id(conn: sqlite3.Connection, cid: int) -> dict | None:
    r = conn.execute("SELECT * FROM spiel_szene_clip WHERE id = ?", (cid,)).fetchone()
    return dict(r) if r else None


def szene_clip_darf(conn: sqlite3.Connection, cid: int, spieler_id: int) -> bool:
    """Eine Spielerin darf den Clip sehen, wenn sie an mindestens einer Szene mit dieser
    Kennung beteiligt ist (Spielzug-Mitspielerin bzw. Schuetzin/Vorlage/Betroffene)."""
    r = conn.execute(
        "SELECT 1 FROM spiel_szene_clip c WHERE c.id = ?1 AND ("
        " EXISTS (SELECT 1 FROM spiel_event e WHERE e.analyse_id = c.analyse_id "
        "         AND e.szene_key = c.szene_key AND (e.spieler_id = ?2 OR e.assist_id = ?2))"
        " OR EXISTS (SELECT 1 FROM spiel_zug z JOIN spiel_zug_spieler s ON s.zug_id = z.id "
        "            WHERE z.analyse_id = c.analyse_id AND z.szene_key = c.szene_key "
        "            AND s.spieler_id = ?2))", (cid, spieler_id)).fetchone()
    return r is not None


def szene_clips_aufraeumen(conn: sqlite3.Connection, aid: int, keys: set[str]) -> list[str]:
    """Entfernt Clips, deren Szene es nicht mehr gibt. Gibt deren Dateinamen zurueck."""
    weg = [r for r in conn.execute(
        "SELECT id, szene_key, datei FROM spiel_szene_clip WHERE analyse_id = ?", (aid,))
        if r["szene_key"] not in keys]
    for r in weg:
        conn.execute("DELETE FROM spiel_szene_clip WHERE id = ?", (r["id"],))
    conn.commit()
    return [r["datei"] for r in weg]
