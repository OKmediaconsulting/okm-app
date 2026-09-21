"""
Jarvis — Recherche-Archiv
Speichert Recherche-Ergebnisse lokal in SQLite.
"""
import sqlite3, os
from datetime import datetime

_DATA_DIR = os.environ.get("DATA_DIR", os.path.expanduser("~/Library/Application Support/OKMediaCRM"))
DB_PATH = os.path.join(_DATA_DIR, "jarvis_research.db")


def _con():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _con() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS recherchen (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            thema       TEXT NOT NULL,
            titel       TEXT NOT NULL,
            inhalt      TEXT NOT NULL,
            quellen     TEXT DEFAULT '',
            tags        TEXT DEFAULT '',
            erstellt_am TEXT DEFAULT (datetime('now','localtime')),
            aktualisiert_am TEXT DEFAULT (datetime('now','localtime'))
        );
        """)


def recherche_speichern(thema: str, titel: str, inhalt: str,
                         quellen: str = "", tags: str = "") -> int:
    with _con() as con:
        cur = con.execute(
            "INSERT INTO recherchen (thema, titel, inhalt, quellen, tags) VALUES (?,?,?,?,?)",
            (thema, titel, inhalt, quellen, tags)
        )
        return cur.lastrowid


def recherche_aktualisieren(rid: int, **kwargs):
    felder = {k: v for k, v in kwargs.items() if k in ("thema","titel","inhalt","quellen","tags")}
    if not felder:
        return
    felder["aktualisiert_am"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = ", ".join(f"{k}=?" for k in felder)
    with _con() as con:
        con.execute(f"UPDATE recherchen SET {sql} WHERE id=?", (*felder.values(), rid))


def recherche_loeschen(rid: int):
    with _con() as con:
        con.execute("DELETE FROM recherchen WHERE id=?", (rid,))


def recherchen_liste(suche: str = "", thema: str = "") -> list:
    sql = "SELECT * FROM recherchen WHERE 1=1"
    params = []
    if suche:
        sql += " AND (titel LIKE ? OR inhalt LIKE ? OR thema LIKE ? OR tags LIKE ?)"
        s = f"%{suche}%"
        params += [s, s, s, s]
    if thema:
        sql += " AND thema=?"
        params.append(thema)
    sql += " ORDER BY aktualisiert_am DESC"
    with _con() as con:
        return [dict(r) for r in con.execute(sql, params)]


def themen_liste() -> list:
    with _con() as con:
        rows = con.execute(
            "SELECT thema, COUNT(*) as anzahl FROM recherchen GROUP BY thema ORDER BY thema"
        ).fetchall()
        return [dict(r) for r in rows]


def recherche_detail(rid: int) -> dict:
    with _con() as con:
        row = con.execute("SELECT * FROM recherchen WHERE id=?", (rid,)).fetchone()
        return dict(row) if row else None


init_db()
