"""
OK Media CRM — Lokale SQLite Datenbank
Speicherort: ~/Library/Application Support/OKMediaCRM/okm_crm.db
"""
import sqlite3, os
from datetime import datetime, date

_DATA_DIR = os.environ.get("DATA_DIR", os.path.expanduser("~/Library/Application Support/OKMediaCRM"))
DB_PATH = os.path.join(_DATA_DIR, "okm_crm.db")


def _con():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _con() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS kunden (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            firma           TEXT NOT NULL,
            ansprechpartner TEXT DEFAULT '',
            telefon         TEXT DEFAULT '',
            email           TEXT DEFAULT '',
            adresse         TEXT DEFAULT '',
            website         TEXT DEFAULT '',
            kategorie       TEXT DEFAULT 'Lead',
            status          TEXT DEFAULT 'Aktiv',
            branche         TEXT DEFAULT '',
            notizen         TEXT DEFAULT '',
            erstellt_am     TEXT DEFAULT (datetime('now','localtime')),
            aktualisiert_am TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS kontakt_log (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            kunden_id       INTEGER NOT NULL REFERENCES kunden(id) ON DELETE CASCADE,
            datum           TEXT DEFAULT (datetime('now','localtime')),
            art             TEXT DEFAULT 'Anruf',
            zusammenfassung TEXT DEFAULT '',
            naechste_schritte TEXT DEFAULT '',
            erstellt_am     TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS follow_ups (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kunden_id   INTEGER NOT NULL REFERENCES kunden(id) ON DELETE CASCADE,
            faellig_am  TEXT NOT NULL,
            titel       TEXT NOT NULL,
            beschreibung TEXT DEFAULT '',
            erledigt    INTEGER DEFAULT 0,
            erstellt_am TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS angebote (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kunden_id   INTEGER NOT NULL REFERENCES kunden(id) ON DELETE CASCADE,
            titel       TEXT NOT NULL,
            betrag      REAL DEFAULT 0,
            status      TEXT DEFAULT 'Entwurf',
            notizen     TEXT DEFAULT '',
            erstellt_am TEXT DEFAULT (datetime('now','localtime')),
            aktualisiert_am TEXT DEFAULT (datetime('now','localtime'))
        );
        """)
    print(f"[CRM] Datenbank bereit: {DB_PATH}")


# ── Kunden ────────────────────────────────────────────────────────────────────

def kunde_erstellen(firma: str, **kwargs) -> int:
    with _con() as con:
        cur = con.execute(
            """INSERT INTO kunden (firma, ansprechpartner, telefon, email, adresse,
               website, kategorie, status, branche, notizen)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (firma,
             kwargs.get("ansprechpartner", ""),
             kwargs.get("telefon", ""),
             kwargs.get("email", ""),
             kwargs.get("adresse", ""),
             kwargs.get("website", ""),
             kwargs.get("kategorie", "Lead"),
             kwargs.get("status", "Aktiv"),
             kwargs.get("branche", ""),
             kwargs.get("notizen", ""))
        )
        return cur.lastrowid


def kunde_aktualisieren(kid: int, **kwargs):
    felder = {k: v for k, v in kwargs.items() if k in
              ("firma","ansprechpartner","telefon","email","adresse",
               "website","kategorie","status","branche","notizen")}
    if not felder:
        return
    felder["aktualisiert_am"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = ", ".join(f"{k}=?" for k in felder)
    with _con() as con:
        con.execute(f"UPDATE kunden SET {sql} WHERE id=?", (*felder.values(), kid))


def kunde_loeschen(kid: int):
    with _con() as con:
        con.execute("DELETE FROM kunden WHERE id=?", (kid,))


def kunden_liste(suche: str = "", kategorie: str = "", status: str = "") -> list:
    sql = "SELECT * FROM kunden WHERE 1=1"
    params = []
    if suche:
        sql += " AND (firma LIKE ? OR ansprechpartner LIKE ? OR email LIKE ? OR telefon LIKE ?)"
        s = f"%{suche}%"
        params += [s, s, s, s]
    if kategorie:
        sql += " AND kategorie=?"
        params.append(kategorie)
    if status:
        sql += " AND status=?"
        params.append(status)
    sql += " ORDER BY aktualisiert_am DESC"
    with _con() as con:
        return [dict(r) for r in con.execute(sql, params)]


def kunde_detail(kid: int) -> dict:
    with _con() as con:
        row = con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["log"] = [dict(r) for r in con.execute(
            "SELECT * FROM kontakt_log WHERE kunden_id=? ORDER BY datum DESC", (kid,))]
        d["follow_ups"] = [dict(r) for r in con.execute(
            "SELECT * FROM follow_ups WHERE kunden_id=? AND erledigt=0 ORDER BY faellig_am", (kid,))]
        return d


def kunde_detail_by_name(name: str) -> dict:
    """Findet Kunden mit vollem Detail per Name (für Jarvis)."""
    with _con() as con:
        row = con.execute(
            "SELECT * FROM kunden WHERE firma LIKE ? ORDER BY aktualisiert_am DESC LIMIT 1",
            (f"%{name}%",)
        ).fetchone()
        if not row:
            return None
        return kunde_detail(row["id"])


def kunde_suchen(name: str) -> dict:
    """Findet einen Kunden by Name (für Jarvis Sprachbefehle)."""
    with _con() as con:
        row = con.execute(
            "SELECT * FROM kunden WHERE firma LIKE ? ORDER BY aktualisiert_am DESC LIMIT 1",
            (f"%{name}%",)
        ).fetchone()
        return dict(row) if row else None


# ── Kontakt-Log ───────────────────────────────────────────────────────────────

def log_erstellen(kunden_id: int, zusammenfassung: str, art: str = "Anruf",
                  naechste_schritte: str = "", datum: str = "") -> int:
    if not datum:
        datum = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with _con() as con:
        # Letzten Kontakt im Kundendatensatz aktualisieren
        con.execute("UPDATE kunden SET aktualisiert_am=? WHERE id=?",
                    (datum, kunden_id))
        cur = con.execute(
            "INSERT INTO kontakt_log (kunden_id, datum, art, zusammenfassung, naechste_schritte) VALUES (?,?,?,?,?)",
            (kunden_id, datum, art, zusammenfassung, naechste_schritte)
        )
        return cur.lastrowid


def log_loeschen(log_id: int):
    with _con() as con:
        con.execute("DELETE FROM kontakt_log WHERE id=?", (log_id,))


# ── Follow-ups ────────────────────────────────────────────────────────────────

def followup_erstellen(kunden_id: int, faellig_am: str, titel: str,
                       beschreibung: str = "") -> int:
    with _con() as con:
        cur = con.execute(
            "INSERT INTO follow_ups (kunden_id, faellig_am, titel, beschreibung) VALUES (?,?,?,?)",
            (kunden_id, faellig_am, titel, beschreibung)
        )
        return cur.lastrowid


def followup_erledigen(fid: int):
    with _con() as con:
        con.execute("UPDATE follow_ups SET erledigt=1 WHERE id=?", (fid,))


def followup_loeschen(fid: int):
    with _con() as con:
        con.execute("DELETE FROM follow_ups WHERE id=?", (fid,))


def followups_heute() -> list:
    heute = date.today().isoformat()
    with _con() as con:
        rows = con.execute("""
            SELECT f.*, k.firma FROM follow_ups f
            JOIN kunden k ON k.id = f.kunden_id
            WHERE f.erledigt=0 AND f.faellig_am <= ?
            ORDER BY f.faellig_am
        """, (heute,)).fetchall()
        return [dict(r) for r in rows]


def followups_alle() -> list:
    with _con() as con:
        rows = con.execute("""
            SELECT f.*, k.firma FROM follow_ups f
            JOIN kunden k ON k.id = f.kunden_id
            WHERE f.erledigt=0
            ORDER BY f.faellig_am
        """).fetchall()
        return [dict(r) for r in rows]


# ── Stats ─────────────────────────────────────────────────────────────────────

def stats() -> dict:
    with _con() as con:
        total     = con.execute("SELECT COUNT(*) FROM kunden").fetchone()[0]
        kunden    = con.execute("SELECT COUNT(*) FROM kunden WHERE kategorie='Kunde'").fetchone()[0]
        leads     = con.execute("SELECT COUNT(*) FROM kunden WHERE kategorie='Lead'").fetchone()[0]
        heute_fup = len(followups_heute())
        letzter   = con.execute(
            "SELECT firma, aktualisiert_am FROM kunden ORDER BY aktualisiert_am DESC LIMIT 1"
        ).fetchone()
        return {
            "gesamt": total,
            "kunden": kunden,
            "leads": leads,
            "follow_ups_heute": heute_fup,
            "letzter_kontakt": dict(letzter) if letzter else None,
        }


# ── Angebote ──────────────────────────────────────────────────────────────────

def angebot_erstellen(kunden_id: int, titel: str, betrag: float = 0,
                      status: str = "Entwurf", notizen: str = "") -> int:
    with _con() as con:
        cur = con.execute(
            "INSERT INTO angebote (kunden_id, titel, betrag, status, notizen) VALUES (?,?,?,?,?)",
            (kunden_id, titel, betrag, status, notizen)
        )
        return cur.lastrowid


def angebot_aktualisieren(aid: int, **kwargs):
    felder = {k: v for k, v in kwargs.items() if k in ("titel","betrag","status","notizen")}
    if not felder:
        return
    felder["aktualisiert_am"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    sql = ", ".join(f"{k}=?" for k in felder)
    with _con() as con:
        con.execute(f"UPDATE angebote SET {sql} WHERE id=?", (*felder.values(), aid))


def angebot_loeschen(aid: int):
    with _con() as con:
        con.execute("DELETE FROM angebote WHERE id=?", (aid,))


def angebote_fuer_kunde(kunden_id: int) -> list:
    with _con() as con:
        rows = con.execute(
            "SELECT * FROM angebote WHERE kunden_id=? ORDER BY erstellt_am DESC", (kunden_id,)
        ).fetchall()
        return [dict(r) for r in rows]


def angebote_stats() -> dict:
    with _con() as con:
        rows = con.execute(
            "SELECT status, COUNT(*) as anzahl, SUM(betrag) as volumen FROM angebote GROUP BY status"
        ).fetchall()
        result = {}
        gesamt_volumen = 0
        for r in rows:
            result[r["status"]] = {"anzahl": r["anzahl"], "volumen": r["volumen"] or 0}
            gesamt_volumen += r["volumen"] or 0
        result["gesamt_volumen"] = gesamt_volumen
        return result


init_db()
