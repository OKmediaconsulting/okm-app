"""
OK Media Consulting — Skript-Programm
Datenbank für Kunden, Skript-Batches und einzelne Skripte.
"""
import sqlite3, os
from datetime import datetime

_DATA_DIR = os.environ.get("DATA_DIR", os.path.expanduser("~/Library/Application Support/OKMediaCRM"))
DB_PATH = os.path.join(_DATA_DIR, "okm_scripts.db")

QUALITAETSBEISPIELE = """
BEISPIEL 1 — Titel: Der Spiegel
Hook: „Die Wahrheit ist: Die meisten merken erst im Spiegel, dass sie etwas verändern müssen."
Skript:
„Nicht heute.
Nicht morgen.
Sondern irgendwann.

Wenn die Treppe anstrengender wird.
Wenn die Energie fehlt.
Wenn man sich selbst nicht mehr so fühlt wie früher.

Die gute Nachricht?

Du musst nicht perfekt starten.

Du musst nur anfangen.

Jede Veränderung beginnt mit einer einzigen Entscheidung.

Und vielleicht ist genau heute der Tag, an dem du sie triffst."

---

BEISPIEL 2 — Titel: Rückenschmerzen
Hook: „Stehst du morgens auf und dein Rücken meldet sich sofort?"
Skript:
„Für viele Menschen beginnt der Tag nicht mit Energie, sondern mit Verspannungen und Rückenschmerzen.

Oft liegt die Ursache nicht am Alter, sondern daran, dass unsere Muskulatur im Alltag zu wenig gefordert wird.

Wir sitzen mehr.

Wir bewegen uns weniger.

Und genau das macht sich irgendwann bemerkbar.

Die gute Nachricht:

Mit gezieltem Krafttraining lässt sich in vielen Fällen aktiv etwas dagegen tun.

Im Browns Active Park Harsewinkel unterstützen wir Menschen dabei, ihren Rücken nachhaltig zu stärken.

Denn das Ziel ist nicht nur weniger Schmerzen.

Sondern mehr Lebensqualität."
"""

STARTKUNDEN = [
    {
        "name": "Genesis Verl",
        "branche": "Fitness- und Gesundheitsstudio",
        "standort": "Verl",
        "zielgruppe": "Frauen und Männer ab ca. 30 Jahren, Einsteiger, Menschen mit gesundheitlichen Beschwerden, Rückenproblemen, Menschen die langfristig fitter und gesünder werden möchten.",
        "ziele": "Neue Mitglieder gewinnen, Vertrauen aufbauen, Gesundheitskompetenz zeigen, Hochwertiges Studio präsentieren, Langfristige Mitglieder gewinnen",
        "leistungen": "Krafttraining, Gesundheitstraining, eGym, Kurse, Personal Training, Rückenprogramme, Ernährungsberatung",
        "tonalitaet": "Emotional, motivierend, gesundheitsorientiert, inspirierend und nahbar. Die Sprache spricht die Gefühle an, gibt Hoffnung und motiviert zum ersten Schritt.",
        "postingrhythmus": "Dienstag 18:00 Uhr",
        "skripte_pro_monat": 4,
        "besonderheiten": "Einer von drei Genesis-Standorten. Kein Inhalt mit anderen Genesis-Standorten mischen.",
        "ansprechpartner": "",
        "contentstrategie": "Vertrauen aufbauen durch Gesundheitskompetenz, Hürden senken für Einsteiger, Erfolgsgeschichten andeuten, saisonale Themen nutzen",
    },
    {
        "name": "Genesis Hövelhof",
        "branche": "Fitness- und Gesundheitsstudio",
        "standort": "Hövelhof",
        "zielgruppe": "Frauen und Männer ab ca. 30 Jahren, Einsteiger, Menschen mit gesundheitlichen Beschwerden, Rückenproblemen, Menschen die langfristig fitter und gesünder werden möchten.",
        "ziele": "Mitglieder gewinnen, Expertenstatus stärken, Vertrauen aufbauen, Gesundheit in den Mittelpunkt stellen",
        "leistungen": "Krafttraining, Gesundheitstraining, eGym, Kurse, Personal Training, Rückenprogramme, Ernährungsberatung",
        "tonalitaet": "Emotional, motivierend, gesundheitsorientiert, inspirierend und nahbar. Die Sprache spricht die Gefühle an, gibt Hoffnung und motiviert zum ersten Schritt.",
        "postingrhythmus": "Dienstag 18:00 Uhr",
        "skripte_pro_monat": 4,
        "besonderheiten": "Einer von drei Genesis-Standorten. Kein Inhalt mit anderen Genesis-Standorten mischen.",
        "ansprechpartner": "",
        "contentstrategie": "Expertenstatus durch Gesundheitswissen zeigen, Hürden für Einsteiger senken, regionale Verbundenheit betonen",
    },
    {
        "name": "Genesis Rietberg",
        "branche": "Fitness- und Gesundheitsstudio",
        "standort": "Rietberg",
        "zielgruppe": "Frauen und Männer ab ca. 30 Jahren, Einsteiger, Menschen mit gesundheitlichen Beschwerden, Rückenproblemen, Menschen die langfristig fitter und gesünder werden möchten.",
        "ziele": "Mitglieder gewinnen, Langfristige Kundenbindung, Gesundheit fördern, Regionale Bekanntheit steigern",
        "leistungen": "Krafttraining, Gesundheitstraining, eGym, Kurse, Personal Training, Rückenprogramme, Ernährungsberatung",
        "tonalitaet": "Emotional, motivierend, gesundheitsorientiert, inspirierend und nahbar. Die Sprache spricht die Gefühle an, gibt Hoffnung und motiviert zum ersten Schritt.",
        "postingrhythmus": "Dienstag 18:00 Uhr",
        "skripte_pro_monat": 4,
        "besonderheiten": "Einer von drei Genesis-Standorten. Kein Inhalt mit anderen Genesis-Standorten mischen.",
        "ansprechpartner": "",
        "contentstrategie": "Regionale Bekanntheit steigern, Langzeitbindung durch Gesundheitskompetenz, Einstiegshürden senken",
    },
    {
        "name": "Browns Active Park Harsewinkel",
        "branche": "Fitnessstudio & Gesundheitsclub",
        "standort": "Harsewinkel",
        "zielgruppe": "Frauen und Männer zwischen ca. 30 und 70 Jahren, gesundheitsorientierte Menschen, Einsteiger, Menschen mit Rückenproblemen, Personen die langfristig beweglich bleiben möchten.",
        "ziele": "Neue Mitglieder gewinnen, Gesundheit verständlich erklären, Vertrauen schaffen, Hochwertiges Training zeigen, Expertenstatus aufbauen",
        "leistungen": "Krafttraining, eGym, Flexx, Rückenprogramme, Kurse, Ernährungsberatung",
        "tonalitaet": "Gesundheitlich fundiert, verständlich, vertrauensvoll, motivierend und kompetent. Ruhige, sachliche Sprache die gleichzeitig Wärme und Expertise ausstrahlt. Keine übertriebene Emotionalität.",
        "postingrhythmus": "Dienstag 18:00 Uhr",
        "skripte_pro_monat": 4,
        "besonderheiten": "Breite Zielgruppe bis 70 Jahre — Sprache muss niedrigschwellig und einladend sein, nicht sportlich-übertrieben.",
        "ansprechpartner": "",
        "contentstrategie": "Gesundheitskompetenz zeigen, Ängste nehmen, einfache Erklärungen für komplexe Gesundheitsthemen, Expertenstatus durch Wissen aufbauen",
    },
    {
        "name": "DEVK Agentur Selent",
        "branche": "Versicherungsagentur",
        "standort": "Melle und Halle (Westf.)",
        "zielgruppe": "Privatkunden, Familien, Berufseinsteiger, Hausbesitzer, junge Erwachsene und Bestandskunden.",
        "ziele": "Vertrauen aufbauen, Beratungskompetenz zeigen, Neue Kunden gewinnen, Regionale Bekanntheit steigern, Komplexe Versicherungsthemen einfach erklären",
        "leistungen": "Versicherungen, Altersvorsorge, Berufsunfähigkeit, Zahnzusatz, Haftpflicht, Hausrat, Wohngebäude, Kfz-Versicherung, Geldanlage",
        "tonalitaet": "Seriös, verständlich, ruhig, beratend und vertrauenswürdig. Sicherheit und Kompetenz stehen im Vordergrund. Keine übertrieben emotionalen Hooks oder reißerische Aussagen. Die Sprache ist klar, sachlich und gleichzeitig menschlich.",
        "postingrhythmus": "Dienstag 18:00 Uhr",
        "skripte_pro_monat": 4,
        "besonderheiten": "Versicherungsbranche erfordert besondere Seriosität. Keine Angstmacherei. Komplexe Themen einfach und verständlich erklären.",
        "ansprechpartner": "",
        "contentstrategie": "Beratungskompetenz durch einfache Erklärungen zeigen, häufige Fehler aufzeigen ohne Angst zu machen, regionale Vertrauensperson sein",
    },
    {
        "name": "Werners Fahrrad Fachwerk",
        "branche": "Fahrradfachhandel & Werkstatt",
        "standort": "Region",
        "zielgruppe": "Familien, Pendler, E-Bike-Fahrer, sportliche Radfahrer und Menschen aus der Region.",
        "ziele": "Vertrauen schaffen, Hochwertige Beratung zeigen, Werkstatt präsentieren, Fahrräder verkaufen, Regionale Sichtbarkeit erhöhen",
        "leistungen": "Fahrradverkauf, E-Bikes, Werkstatt, Inspektionen, Reparaturen, Leasing, Zubehör",
        "tonalitaet": "Regional, authentisch, sympathisch, bodenständig und fachlich kompetent. Der Fokus liegt auf Beratung, Service und Vertrauen. Sprache ist herzlich, direkt und ohne Verkaufsdruck.",
        "postingrhythmus": "Dienstag 18:00 Uhr",
        "skripte_pro_monat": 4,
        "besonderheiten": "Lokales Fachgeschäft — regionale Identität und persönliche Beratung sind die größten Stärken gegenüber Online-Händlern.",
        "ansprechpartner": "",
        "contentstrategie": "Fachkompetenz durch Tipps zeigen, Werkstatt-Expertise präsentieren, regionalen Charakter betonen, Kaufberatung geben",
    },
]


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
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            name                TEXT NOT NULL,
            branche             TEXT DEFAULT '',
            standort            TEXT DEFAULT '',
            zielgruppe          TEXT DEFAULT '',
            ziele               TEXT DEFAULT '',
            leistungen          TEXT DEFAULT '',
            tonalitaet          TEXT DEFAULT '',
            postingrhythmus     TEXT DEFAULT 'Dienstag 18:00 Uhr',
            skripte_pro_monat   INTEGER DEFAULT 4,
            besonderheiten      TEXT DEFAULT '',
            ansprechpartner     TEXT DEFAULT '',
            contentstrategie    TEXT DEFAULT '',
            erstellt_am         TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS skript_batches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            kunden_id   INTEGER NOT NULL REFERENCES kunden(id) ON DELETE CASCADE,
            monat       TEXT NOT NULL,
            strategie   TEXT DEFAULT '',
            erstellt_am TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS skripte (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            batch_id     INTEGER NOT NULL REFERENCES skript_batches(id) ON DELETE CASCADE,
            kunden_id    INTEGER NOT NULL REFERENCES kunden(id) ON DELETE CASCADE,
            position     INTEGER DEFAULT 1,
            titel        TEXT DEFAULT '',
            hook         TEXT DEFAULT '',
            skript       TEXT DEFAULT '',
            cta          TEXT DEFAULT '',
            drehhinweis  TEXT DEFAULT '',
            thema_tag    TEXT DEFAULT '',
            beitrag_text TEXT DEFAULT '',
            story_titel  TEXT DEFAULT '',
            erstellt_am  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS canva_posts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            kunden_id    INTEGER NOT NULL REFERENCES kunden(id) ON DELETE CASCADE,
            goal         TEXT DEFAULT '',
            headline     TEXT DEFAULT '',
            subtext      TEXT DEFAULT '',
            cta          TEXT DEFAULT '',
            design_id    TEXT DEFAULT '',
            edit_url     TEXT DEFAULT '',
            thumbnail_url TEXT DEFAULT '',
            image_path   TEXT DEFAULT '',
            erstellt_am  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS instagram_posts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            kunden_id    INTEGER NOT NULL REFERENCES kunden(id) ON DELETE CASCADE,
            thema        TEXT DEFAULT '',
            format       TEXT DEFAULT '',
            slides_json  TEXT DEFAULT '[]',
            caption      TEXT DEFAULT '',
            hashtags     TEXT DEFAULT '',
            erstellt_am  TEXT DEFAULT (datetime('now','localtime'))
        );

        CREATE TABLE IF NOT EXISTS kunden_branding (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            kunden_id       INTEGER NOT NULL UNIQUE REFERENCES kunden(id) ON DELETE CASCADE,
            primary_color   TEXT DEFAULT '',
            secondary_color TEXT DEFAULT '',
            accent_color    TEXT DEFAULT '',
            font_haupt      TEXT DEFAULT '',
            font_text       TEXT DEFAULT '',
            design_stil     TEXT DEFAULT '',
            bildsprache     TEXT DEFAULT '',
            logo_path       TEXT DEFAULT '',
            beispiele_json  TEXT DEFAULT '[]',
            aktualisiert_am TEXT DEFAULT (datetime('now','localtime'))
        );
        """)

    # Startkunden anlegen falls noch nicht vorhanden
    with _con() as con:
        count = con.execute("SELECT COUNT(*) FROM kunden").fetchone()[0]
        if count == 0:
            for k in STARTKUNDEN:
                con.execute("""
                    INSERT INTO kunden (name, branche, standort, zielgruppe, ziele, leistungen,
                    tonalitaet, postingrhythmus, skripte_pro_monat, besonderheiten,
                    ansprechpartner, contentstrategie)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (k["name"], k["branche"], k["standort"], k["zielgruppe"],
                      k["ziele"], k["leistungen"], k["tonalitaet"], k["postingrhythmus"],
                      k["skripte_pro_monat"], k["besonderheiten"],
                      k["ansprechpartner"], k["contentstrategie"]))


# ── Kunden ────────────────────────────────────────────────────────────────────

def kunden_liste() -> list:
    with _con() as con:
        return [dict(r) for r in con.execute("SELECT * FROM kunden ORDER BY name")]

def kunde_detail(kid: int) -> dict:
    with _con() as con:
        row = con.execute("SELECT * FROM kunden WHERE id=?", (kid,)).fetchone()
        return dict(row) if row else None

def kunde_erstellen(data: dict) -> int:
    with _con() as con:
        cur = con.execute("""
            INSERT INTO kunden (name, branche, standort, zielgruppe, ziele, leistungen,
            tonalitaet, postingrhythmus, skripte_pro_monat, besonderheiten,
            ansprechpartner, contentstrategie)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (data.get("name",""), data.get("branche",""), data.get("standort",""),
              data.get("zielgruppe",""), data.get("ziele",""), data.get("leistungen",""),
              data.get("tonalitaet",""), data.get("postingrhythmus","Dienstag 18:00 Uhr"),
              int(data.get("skripte_pro_monat",4)), data.get("besonderheiten",""),
              data.get("ansprechpartner",""), data.get("contentstrategie","")))
        return cur.lastrowid

def kunde_aktualisieren(kid: int, data: dict):
    felder = {k: v for k, v in data.items() if k in (
        "name","branche","standort","zielgruppe","ziele","leistungen",
        "tonalitaet","postingrhythmus","skripte_pro_monat","besonderheiten",
        "ansprechpartner","contentstrategie","website","produkte","social_media_ziele"
    )}
    if not felder:
        return
    sql = ", ".join(f"{k}=?" for k in felder)
    with _con() as con:
        con.execute(f"UPDATE kunden SET {sql} WHERE id=?", (*felder.values(), kid))

def kunde_loeschen(kid: int):
    with _con() as con:
        con.execute("DELETE FROM kunden WHERE id=?", (kid,))


# ── Batches & Skripte ─────────────────────────────────────────────────────────

def batch_erstellen(kunden_id: int, monat: str, strategie: str) -> int:
    with _con() as con:
        cur = con.execute(
            "INSERT INTO skript_batches (kunden_id, monat, strategie) VALUES (?,?,?)",
            (kunden_id, monat, strategie)
        )
        return cur.lastrowid

def skript_erstellen(batch_id: int, kunden_id: int, position: int,
                     titel: str, hook: str, skript: str, cta: str,
                     drehhinweis: str = "", thema_tag: str = "") -> int:
    with _con() as con:
        cur = con.execute("""
            INSERT INTO skripte (batch_id, kunden_id, position, titel, hook, skript, cta, drehhinweis, thema_tag)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (batch_id, kunden_id, position, titel, hook, skript, cta, drehhinweis, thema_tag))
        return cur.lastrowid

def batches_fuer_kunde(kunden_id: int) -> list:
    with _con() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM skript_batches WHERE kunden_id=? ORDER BY monat DESC", (kunden_id,)
        )]

def skripte_fuer_batch(batch_id: int) -> list:
    with _con() as con:
        return [dict(r) for r in con.execute(
            "SELECT * FROM skripte WHERE batch_id=? ORDER BY position", (batch_id,)
        )]

def alle_themen_fuer_kunde(kunden_id: int) -> list:
    """Alle bisherigen Titel/Themen eines Kunden — für Wiederholungsschutz."""
    with _con() as con:
        rows = con.execute(
            "SELECT titel, thema_tag, erstellt_am FROM skripte WHERE kunden_id=? ORDER BY erstellt_am DESC",
            (kunden_id,)
        ).fetchall()
        return [dict(r) for r in rows]

def batch_mit_skripten(batch_id: int) -> dict:
    with _con() as con:
        batch = con.execute("SELECT * FROM skript_batches WHERE id=?", (batch_id,)).fetchone()
        if not batch:
            return None
        d = dict(batch)
        d["skripte"] = skripte_fuer_batch(batch_id)
        kunde = con.execute("SELECT * FROM kunden WHERE id=?", (d["kunden_id"],)).fetchone()
        d["kunde"] = dict(kunde) if kunde else {}
        return d

def batch_loeschen(batch_id: int):
    with _con() as con:
        con.execute("DELETE FROM skript_batches WHERE id=?", (batch_id,))

def monat_hat_batch(kunden_id: int, monat: str) -> bool:
    with _con() as con:
        count = con.execute(
            "SELECT COUNT(*) FROM skript_batches WHERE kunden_id=? AND monat=?",
            (kunden_id, monat)
        ).fetchone()[0]
        return count > 0


def skript_detail(skript_id: int) -> dict:
    with _con() as con:
        row = con.execute("SELECT * FROM skripte WHERE id=?", (skript_id,)).fetchone()
        return dict(row) if row else None


def skript_beitrag_speichern(skript_id: int, beitrag_text: str, story_titel: str):
    with _con() as con:
        con.execute(
            "UPDATE skripte SET beitrag_text=?, story_titel=? WHERE id=?",
            (beitrag_text, story_titel, skript_id)
        )


init_db()


def _migrate():
    """Nachrüstung älterer DBs um neue Spalten."""
    with _con() as con:
        cols = [r[1] for r in con.execute("PRAGMA table_info(skripte)").fetchall()]
        if "beitrag_text" not in cols:
            con.execute("ALTER TABLE skripte ADD COLUMN beitrag_text TEXT DEFAULT ''")
        if "story_titel" not in cols:
            con.execute("ALTER TABLE skripte ADD COLUMN story_titel TEXT DEFAULT ''")
        if "struktur" not in cols:
            con.execute("ALTER TABLE skripte ADD COLUMN struktur TEXT DEFAULT ''")
        if "einzeln" not in cols:
            con.execute("ALTER TABLE skripte ADD COLUMN einzeln INTEGER DEFAULT 0")

        kunden_cols = [r[1] for r in con.execute("PRAGMA table_info(kunden)").fetchall()]
        for col, default in [
            ("canva_brand_template_id", "''"),
            ("canva_medien_pfad", "''"),
            ("canva_used_photos", "'[]'"),
            ("canva_last_run", "''"),
            ("canva_last_status", "''"),
            ("website", "''"),
            ("produkte", "''"),
            ("social_media_ziele", "''"),
        ]:
            if col not in kunden_cols:
                con.execute(f"ALTER TABLE kunden ADD COLUMN {col} TEXT DEFAULT {default}")

        # Neue Tabellen sicher anlegen (falls DB älter als CREATE TABLE IF NOT EXISTS)
        con.executescript("""
        CREATE TABLE IF NOT EXISTS instagram_posts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            kunden_id    INTEGER NOT NULL REFERENCES kunden(id) ON DELETE CASCADE,
            thema        TEXT DEFAULT '',
            format       TEXT DEFAULT '',
            slides_json  TEXT DEFAULT '[]',
            caption      TEXT DEFAULT '',
            hashtags     TEXT DEFAULT '',
            erstellt_am  TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS kunden_branding (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            kunden_id       INTEGER NOT NULL UNIQUE REFERENCES kunden(id) ON DELETE CASCADE,
            primary_color   TEXT DEFAULT '',
            secondary_color TEXT DEFAULT '',
            accent_color    TEXT DEFAULT '',
            font_haupt      TEXT DEFAULT '',
            font_text       TEXT DEFAULT '',
            design_stil     TEXT DEFAULT '',
            bildsprache     TEXT DEFAULT '',
            logo_path       TEXT DEFAULT '',
            beispiele_json  TEXT DEFAULT '[]',
            aktualisiert_am TEXT DEFAULT (datetime('now','localtime'))
        );
        """)

_migrate()


# ── Canva ─────────────────────────────────────────────────────────────────────

def canva_config_setzen(kid: int, brand_template_id: str, medien_pfad: str):
    with _con() as con:
        con.execute(
            "UPDATE kunden SET canva_brand_template_id=?, canva_medien_pfad=? WHERE id=?",
            (brand_template_id, medien_pfad, kid),
        )


def canva_run_status_setzen(kid: int, used_photos_json: str, status: str):
    with _con() as con:
        con.execute(
            "UPDATE kunden SET canva_used_photos=?, canva_last_run=datetime('now','localtime'), canva_last_status=? WHERE id=?",
            (used_photos_json, status, kid),
        )


def canva_posts_speichern(kid: int, posts: list):
    with _con() as con:
        for p in posts:
            con.execute("""
                INSERT INTO canva_posts (kunden_id, goal, headline, subtext, cta, design_id, edit_url, thumbnail_url, image_path)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (kid, p.get("goal", ""), p.get("headline", ""), p.get("subtext", ""), p.get("cta", ""),
                  p.get("id", ""), p.get("edit_url", ""), p.get("thumbnail_url", ""), p.get("image_path", "") or ""))


def canva_posts_fuer_kunde(kid: int, limit: int = 9) -> list:
    with _con() as con:
        rows = con.execute(
            "SELECT * FROM canva_posts WHERE kunden_id=? ORDER BY erstellt_am DESC LIMIT ?",
            (kid, limit),
        ).fetchall()
        return [dict(r) for r in rows]


def canva_post_detail(post_id: int) -> dict:
    with _con() as con:
        row = con.execute("SELECT * FROM canva_posts WHERE id=?", (post_id,)).fetchone()
        return dict(row) if row else None


# ── Erweiterter Wiederholungsschutz ───────────────────────────────────────────

def wiederholungsschutz_daten(kunden_id: int, letzte_n_batches: int = 3) -> dict:
    """Analysiert die letzten N Batches eines Kunden für den Anti-Repetition-Prompt."""
    with _con() as con:
        batches = con.execute(
            "SELECT id FROM skript_batches WHERE kunden_id=? ORDER BY erstellt_am DESC LIMIT ?",
            (kunden_id, letzte_n_batches)
        ).fetchall()
        batch_ids = [b[0] for b in batches]
        if not batch_ids:
            return {"hooks": [], "ctas": [], "strukturen": [], "titel": [], "einstiegswoerter": []}

        placeholders = ",".join("?" * len(batch_ids))
        skripte = con.execute(
            f"SELECT titel, hook, cta, struktur FROM skripte WHERE batch_id IN ({placeholders}) ORDER BY erstellt_am DESC",
            batch_ids
        ).fetchall()

    hooks = [s[1] for s in skripte if s[1]]
    ctas = [s[2] for s in skripte if s[2]]
    strukturen = [s[3] for s in skripte if s[3]]
    titel = [s[0] for s in skripte if s[0]]

    # Erste Wörter der Hooks extrahieren (Einstiegsmuster)
    einstiegswoerter = []
    for h in hooks:
        words = h.strip().strip('"').strip("„").split()
        if words:
            einstiegswoerter.append(words[0])
        if len(words) > 1:
            einstiegswoerter.append(f"{words[0]} {words[1]}")

    return {
        "hooks": hooks,
        "ctas": ctas,
        "strukturen": strukturen,
        "titel": titel,
        "einstiegswoerter": list(set(einstiegswoerter))
    }


def skript_einzeln_speichern(kunden_id: int, thema: str, titel: str, hook: str,
                              skript: str, cta: str, drehhinweis: str,
                              struktur: str) -> int:
    """Speichert ein Einzelskript ohne Batch."""
    with _con() as con:
        # Einzelskripte bekommen einen eigenen Batch mit Thema als Monat-Label
        from datetime import datetime as _dt
        monat_label = f"einzeln_{_dt.now().strftime('%Y%m%d%H%M%S')}"
        cur_batch = con.execute(
            "INSERT INTO skript_batches (kunden_id, monat, strategie) VALUES (?,?,?)",
            (kunden_id, monat_label, f"Einzelskript: {thema}")
        )
        batch_id = cur_batch.lastrowid
        cur_skript = con.execute("""
            INSERT INTO skripte (batch_id, kunden_id, position, titel, hook, skript, cta,
                                 drehhinweis, thema_tag, struktur, einzeln)
            VALUES (?,?,1,?,?,?,?,?,?,?,1)
        """, (batch_id, kunden_id, titel, hook, skript, cta, drehhinweis, thema, struktur))
        return cur_skript.lastrowid


# ── Instagram Posts ───────────────────────────────────────────────────────────

def instagram_post_speichern(kunden_id: int, thema: str, format_typ: str,
                              slides_json: str, caption: str, hashtags: str) -> int:
    with _con() as con:
        cur = con.execute("""
            INSERT INTO instagram_posts (kunden_id, thema, format, slides_json, caption, hashtags)
            VALUES (?,?,?,?,?,?)
        """, (kunden_id, thema, format_typ, slides_json, caption, hashtags))
        return cur.lastrowid


def instagram_posts_fuer_kunde(kunden_id: int, limit: int = 20) -> list:
    with _con() as con:
        rows = con.execute(
            "SELECT * FROM instagram_posts WHERE kunden_id=? ORDER BY erstellt_am DESC LIMIT ?",
            (kunden_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def instagram_post_detail(post_id: int) -> dict:
    with _con() as con:
        row = con.execute("SELECT * FROM instagram_posts WHERE id=?", (post_id,)).fetchone()
        return dict(row) if row else None


def instagram_post_loeschen(post_id: int):
    with _con() as con:
        con.execute("DELETE FROM instagram_posts WHERE id=?", (post_id,))


# ── Kunden Branding ───────────────────────────────────────────────────────────

def branding_fuer_kunde(kunden_id: int) -> dict:
    with _con() as con:
        row = con.execute("SELECT * FROM kunden_branding WHERE kunden_id=?", (kunden_id,)).fetchone()
        return dict(row) if row else {}


def branding_speichern(kunden_id: int, data: dict):
    felder = {k: v for k, v in data.items() if k in (
        "primary_color", "secondary_color", "accent_color",
        "font_haupt", "font_text", "design_stil", "bildsprache",
        "logo_path", "beispiele_json"
    )}
    with _con() as con:
        existing = con.execute("SELECT id FROM kunden_branding WHERE kunden_id=?", (kunden_id,)).fetchone()
        if existing:
            sql = ", ".join(f"{k}=?" for k in felder)
            sql += ", aktualisiert_am=datetime('now','localtime')"
            con.execute(f"UPDATE kunden_branding SET {sql} WHERE kunden_id=?", (*felder.values(), kunden_id))
        else:
            cols = "kunden_id, " + ", ".join(felder.keys())
            vals = "?, " + ", ".join("?" * len(felder))
            con.execute(f"INSERT INTO kunden_branding ({cols}) VALUES ({vals})", (kunden_id, *felder.values()))
