"""Systemgesundheit — echte Tests auf allen Jarvis-Modulen."""
import os, json, sqlite3, time, datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).parent
CRM_DB   = Path.home() / "Library/Application Support/OKMediaCRM/okm_crm.db"
SCR_DB   = Path.home() / "Library/Application Support/OKMediaCRM/okm_scripts.db"
RES_DB   = Path.home() / "Library/Application Support/OKMediaCRM/jarvis_research.db"
MEM_FILE = Path.home() / "Library/Application Support/OKMediaCRM/jarvis_memory.json"
PLIST    = Path.home() / "Library/LaunchAgents/net.okmediaconsulting.jarvis.plist"
KNOWLEDGE= BASE_DIR / "knowledge.txt"
CONFIG   = BASE_DIR / "config.json"

FRONTEND_FILES = [
    "dashboard.html", "crm.html", "skripte.html",
    "recherche.html", "denkt_mit.html", "index.html",
    "main.js", "style.css", "systemgesundheit.html",
]

CORE_FILES = [
    "server.py", "crm_tools.py", "scripts_tools.py",
    "research_tools.py", "meta_tools.py", "gmail_tools.py",
    "calendar_tools.py", "memory.py", "health_tools.py",
]


def _check(id_, name, category, weight, fn):
    try:
        status, message, detail, repair_id, repair_desc = fn()
    except Exception as e:
        status, message, detail, repair_id, repair_desc = (
            "error", f"Ausnahme: {type(e).__name__}", str(e), None, None
        )
    return {
        "id": id_,
        "name": name,
        "category": category,
        "weight": weight,
        "status": status,
        "message": message,
        "detail": detail,
        "repair_id": repair_id,
        "repair_description": repair_desc,
    }


# ── Datenbank-Checks ─────────────────────────────────────────────────────────

def _db_integrity(path: Path, label: str):
    if not path.exists():
        return "error", f"{label} Datenbankdatei fehlt", str(path), None, None
    con = sqlite3.connect(str(path))
    result = con.execute("PRAGMA integrity_check").fetchone()[0]
    size_kb = path.stat().st_size // 1024
    con.close()
    if result == "ok":
        return "ok", f"Integrität in Ordnung ({size_kb} KB)", None, None, None
    return "error", "Datenbankkorruption erkannt", result, None, None


def _crm_orphans():
    con = sqlite3.connect(str(CRM_DB))
    log_orphans  = con.execute(
        "SELECT COUNT(*) FROM kontakt_log WHERE kunden_id NOT IN (SELECT id FROM kunden)"
    ).fetchone()[0]
    fup_orphans  = con.execute(
        "SELECT COUNT(*) FROM follow_ups WHERE kunden_id NOT IN (SELECT id FROM kunden)"
    ).fetchone()[0]
    ang_orphans  = con.execute(
        "SELECT COUNT(*) FROM angebote WHERE kunden_id NOT IN (SELECT id FROM kunden)"
    ).fetchone()[0]
    con.close()
    total = log_orphans + fup_orphans + ang_orphans
    if total == 0:
        return "ok", "Keine verwaisten Datensätze", None, None, None
    detail = (f"Kontakteinträge: {log_orphans}, Follow-ups: {fup_orphans}, "
              f"Angebote: {ang_orphans}")
    return ("warning", f"{total} verwaiste Datensätze gefunden", detail,
            "fix_crm_orphans",
            "Verwaiste Kontakteinträge, Follow-ups und Angebote löschen "
            "(Datensätze ohne zugehörigen Kunden)")


def _scripts_orphans():
    con = sqlite3.connect(str(SCR_DB))
    skr_orphans = con.execute(
        "SELECT COUNT(*) FROM skripte WHERE batch_id NOT IN (SELECT id FROM skript_batches)"
    ).fetchone()[0]
    empty_batches = con.execute(
        "SELECT COUNT(*) FROM skript_batches WHERE id NOT IN (SELECT DISTINCT batch_id FROM skripte)"
    ).fetchone()[0]
    con.close()
    issues = []
    if skr_orphans:
        issues.append(f"{skr_orphans} Skripte ohne Batch")
    if empty_batches:
        issues.append(f"{empty_batches} leere Batches")
    if not issues:
        return "ok", "Keine Konsistenzprobleme", None, None, None
    return ("warning", "; ".join(issues), None,
            "fix_scripts_orphans",
            "Verwaiste Skripte und leere Batches bereinigen")


def _scripts_empty():
    con = sqlite3.connect(str(SCR_DB))
    empty = con.execute(
        "SELECT COUNT(*) FROM skripte WHERE skript IS NULL OR skript = ''"
    ).fetchone()[0]
    con.close()
    if empty == 0:
        return "ok", "Alle Skripte haben Inhalt", None, None, None
    return ("warning", f"{empty} Skripte ohne Skripttext", None, None, None)


# ── Datei-Checks ──────────────────────────────────────────────────────────────

def _frontend_files():
    missing = [f for f in FRONTEND_FILES
               if not (BASE_DIR / "frontend" / f).exists()]
    if not missing:
        return "ok", f"Alle {len(FRONTEND_FILES)} Frontend-Dateien vorhanden", None, None, None
    return ("error", f"{len(missing)} Frontend-Datei(en) fehlen",
            ", ".join(missing), None, None)


def _core_files():
    missing = [f for f in CORE_FILES if not (BASE_DIR / f).exists()]
    if not missing:
        return "ok", f"Alle {len(CORE_FILES)} Backend-Module vorhanden", None, None, None
    return ("error", f"{len(missing)} Backend-Datei(en) fehlen",
            ", ".join(missing), None, None)


def _launchagent():
    if PLIST.exists():
        return "ok", "LaunchAgent-Plist vorhanden", None, None, None
    return ("error", "LaunchAgent-Plist fehlt — Server startet nicht automatisch",
            str(PLIST), None, None)


def _knowledge():
    if not KNOWLEDGE.exists():
        return "error", "knowledge.txt fehlt", str(KNOWLEDGE), None, None
    size = KNOWLEDGE.stat().st_size
    if size < 100:
        return ("warning", f"knowledge.txt sehr klein ({size} Bytes)",
                "Möglicherweise leer oder beschädigt", None, None)
    return "ok", f"knowledge.txt vorhanden ({size // 1024} KB)", None, None, None


# ── Konfig-Checks ─────────────────────────────────────────────────────────────

def _config():
    if not CONFIG.exists():
        return "error", "config.json fehlt", str(CONFIG), None, None
    try:
        cfg = json.loads(CONFIG.read_text())
    except Exception as e:
        return "error", "config.json ist kein gültiges JSON", str(e), None, None
    required = ["anthropic_api_key", "elevenlabs_api_key", "elevenlabs_voice_id",
                "user_name", "user_address", "city"]
    missing = [k for k in required if not cfg.get(k)]
    if missing:
        return ("error", f"config.json: {len(missing)} Pflichtfeld(er) leer",
                ", ".join(missing), None, None)
    return "ok", "config.json vollständig und gültig", None, None, None


def _api_anthropic():
    cfg = json.loads(CONFIG.read_text())
    key = cfg.get("anthropic_api_key", "")
    if not key.startswith("sk-ant-"):
        return ("error", "Anthropic API-Key hat ungültiges Format",
                "Muss mit 'sk-ant-' beginnen", None, None)
    if len(key) < 40:
        return "warning", "Anthropic API-Key ungewöhnlich kurz", None, None, None
    return "ok", "Anthropic API-Key Format gültig", None, None, None


def _api_elevenlabs():
    import httpx
    cfg = json.loads(CONFIG.read_text())
    key = cfg.get("elevenlabs_api_key", "")
    if not key.startswith("sk_"):
        return ("error", "ElevenLabs API-Key hat ungültiges Format",
                "Muss mit 'sk_' beginnen", None, None)
    try:
        r = httpx.get(
            "https://api.elevenlabs.io/v1/voices",
            headers={"xi-api-key": key},
            timeout=8.0,
        )
        if r.status_code == 200:
            voices = r.json().get("voices", [])
            return ("ok",
                    f"ElevenLabs verbunden — {len(voices)} Stimmen verfügbar",
                    None, None, None)
        elif r.status_code == 401:
            return "error", "ElevenLabs API-Key ungültig (401)", None, None, None
        else:
            return "warning", f"ElevenLabs antwortete mit Status {r.status_code}", None, None, None
    except Exception as e:
        return "warning", "ElevenLabs nicht erreichbar (Netzwerk?)", str(e), None, None


# ── Speicher-Check ────────────────────────────────────────────────────────────

def _memory():
    if not MEM_FILE.exists():
        return "ok", "Speicherdatei noch nicht erstellt (normal)", None, None, None
    try:
        data = json.loads(MEM_FILE.read_text())
        n_notizen = len(data.get("notizen", []))
        n_themen  = len(data.get("letzte_themen", []))
        n_aufg    = len(data.get("aufgaben", []))
        return ("ok",
                f"Speicher OK — {n_notizen} Notizen, {n_themen} Themen, {n_aufg} Aufgaben",
                None, None, None)
    except Exception as e:
        return ("error", "jarvis_memory.json ist kein gültiges JSON", str(e),
                "fix_memory_json",
                "Speicherdatei mit leerem Objekt zurücksetzen (Inhalt geht verloren)")


# ── Disk-Check ────────────────────────────────────────────────────────────────

def _disk():
    import shutil
    total, used, free = shutil.disk_usage("/")
    free_gb = free / (1024 ** 3)
    pct_free = round(free / total * 100)
    if free_gb < 5:
        return ("error", f"Kritisch wenig Speicherplatz: {free_gb:.1f} GB frei",
                f"Gesamt: {total//(1024**3)} GB", None, None)
    if free_gb < 15:
        return ("warning", f"Wenig Speicherplatz: {free_gb:.1f} GB frei ({pct_free}%)",
                None, None, None)
    return "ok", f"{free_gb:.1f} GB frei ({pct_free}%)", None, None, None


# ── CRM Datenqualität ─────────────────────────────────────────────────────────

def _crm_data_quality():
    con = sqlite3.connect(str(CRM_DB))
    total   = con.execute("SELECT COUNT(*) FROM kunden").fetchone()[0]
    no_tel  = con.execute(
        "SELECT COUNT(*) FROM kunden WHERE telefon IS NULL OR telefon = ''"
    ).fetchone()[0]
    no_email = con.execute(
        "SELECT COUNT(*) FROM kunden WHERE email IS NULL OR email = ''"
    ).fetchone()[0]
    con.close()
    if total == 0:
        return "warning", "Keine Kunden im CRM", None, None, None
    issues = []
    if no_tel:
        issues.append(f"{no_tel} ohne Telefon")
    if no_email:
        issues.append(f"{no_email} ohne E-Mail")
    if not issues:
        return "ok", f"Alle {total} CRM-Kunden vollständig", None, None, None
    return ("warning",
            f"{'; '.join(issues)} (von {total} Kunden)",
            "Unvollständige Kundendaten können Lead-Prozesse behindern",
            None, None)


# ── Navigation ────────────────────────────────────────────────────────────────

def _nav_links():
    pages = ["dashboard.html", "crm.html", "skripte.html",
             "recherche.html", "denkt_mit.html"]
    missing = []
    for page in pages:
        path = BASE_DIR / "frontend" / page
        if not path.exists():
            continue
        content = path.read_text()
        if "systemgesundheit" not in content:
            missing.append(page)
    if not missing:
        return "ok", "Systemgesundheit-Link in allen Seiten vorhanden", None, None, None
    return ("warning",
            f"Systemgesundheit-Link fehlt in: {', '.join(missing)}",
            None, None, None)


# ── Hauptfunktion ─────────────────────────────────────────────────────────────

def run_health_checks() -> dict:
    start = time.time()
    checks = [
        _check("config_valid",       "Konfigurationsdatei",       "Konfiguration",  3, _config),
        _check("api_anthropic",      "Anthropic API-Key",          "APIs",           3, _api_anthropic),
        _check("api_elevenlabs",     "ElevenLabs API & Credits",   "APIs",           3, _api_elevenlabs),
        _check("crm_db_integrity",   "CRM Datenbank Integrität",   "Datenbanken",    3,
               lambda: _db_integrity(CRM_DB, "CRM")),
        _check("scripts_db_int",     "Skripte Datenbank",          "Datenbanken",    3,
               lambda: _db_integrity(SCR_DB, "Skripte")),
        _check("research_db_int",    "Recherche Datenbank",        "Datenbanken",    2,
               lambda: _db_integrity(RES_DB, "Recherche")),
        _check("core_files",         "Backend-Module",             "Dateien",        3, _core_files),
        _check("frontend_files",     "Frontend-Dateien",           "Dateien",        3, _frontend_files),
        _check("launchagent",        "LaunchAgent (Auto-Start)",   "System",         2, _launchagent),
        _check("knowledge_txt",      "Wissensdatei (knowledge.txt)","Dateien",       2, _knowledge),
        _check("disk_space",         "Speicherplatz",              "System",         2, _disk),
        _check("memory_file",        "Jarvis-Speicher",            "Daten",          1, _memory),
        _check("crm_orphans",        "CRM Datenkonsistenz",        "Datenbanken",    2, _crm_orphans),
        _check("scripts_orphans",    "Skripte Konsistenz",         "Datenbanken",    2, _scripts_orphans),
        _check("scripts_empty",      "Skripte mit Inhalt",         "Daten",          1, _scripts_empty),
        _check("crm_data_quality",   "CRM Datenqualität",          "Daten",          1, _crm_data_quality),
        _check("nav_links",          "Navigationslinks",           "UI",             1, _nav_links),
    ]

    total_weight   = sum(c["weight"] for c in checks)
    earned_weight  = sum(
        c["weight"] if c["status"] == "ok" else
        c["weight"] * 0.5 if c["status"] == "warning" else 0
        for c in checks
    )
    score = round(earned_weight / total_weight * 100) if total_weight else 0

    critical  = [c for c in checks if c["status"] == "error"]
    warnings  = [c for c in checks if c["status"] == "warning"]

    if critical:
        overall = "Kritisch"
    elif warnings:
        overall = "Warnung"
    else:
        overall = "Stabil"

    elapsed = round(time.time() - start, 2)
    return {
        "score":          score,
        "status":         overall,
        "checks":         checks,
        "critical_count": len(critical),
        "warning_count":  len(warnings),
        "ok_count":       len([c for c in checks if c["status"] == "ok"]),
        "total_checks":   len(checks),
        "elapsed_sec":    elapsed,
        "timestamp":      datetime.datetime.now().isoformat(),
    }


# ── Reparaturen ───────────────────────────────────────────────────────────────

REPAIRS = {
    "fix_crm_orphans": {
        "name":   "CRM verwaiste Datensätze bereinigen",
        "risk":   "Niedrig — nur Datensätze ohne gültigen Kunden werden gelöscht",
        "backup": True,
    },
    "fix_scripts_orphans": {
        "name":   "Skripte Konsistenz wiederherstellen",
        "risk":   "Niedrig — leere Batches und verwaiste Skripte werden gelöscht",
        "backup": True,
    },
    "fix_memory_json": {
        "name":   "Jarvis-Speicher zurücksetzen",
        "risk":   "Mittel — alle gespeicherten Notizen und Themen gehen verloren",
        "backup": True,
    },
}


def get_repair_info(repair_id: str) -> Optional[dict]:
    return REPAIRS.get(repair_id)


def execute_repair(repair_id: str) -> dict:
    backup_path = None
    if REPAIRS.get(repair_id, {}).get("backup"):
        backup_path = _create_backup(repair_id)

    if repair_id == "fix_crm_orphans":
        con = sqlite3.connect(str(CRM_DB))
        d1 = con.execute("DELETE FROM kontakt_log WHERE kunden_id NOT IN (SELECT id FROM kunden)").rowcount
        d2 = con.execute("DELETE FROM follow_ups  WHERE kunden_id NOT IN (SELECT id FROM kunden)").rowcount
        d3 = con.execute("DELETE FROM angebote    WHERE kunden_id NOT IN (SELECT id FROM kunden)").rowcount
        con.commit(); con.close()
        return {"ok": True, "message": f"{d1+d2+d3} Datensätze bereinigt", "backup": backup_path}

    elif repair_id == "fix_scripts_orphans":
        con = sqlite3.connect(str(SCR_DB))
        d1 = con.execute("DELETE FROM skripte WHERE batch_id NOT IN (SELECT id FROM skript_batches)").rowcount
        d2 = con.execute("DELETE FROM skript_batches WHERE id NOT IN (SELECT DISTINCT batch_id FROM skripte)").rowcount
        con.commit(); con.close()
        return {"ok": True, "message": f"{d1} Skripte, {d2} Batches bereinigt", "backup": backup_path}

    elif repair_id == "fix_memory_json":
        MEM_FILE.write_text(json.dumps({"notizen": [], "letzte_themen": [], "aufgaben": []}, ensure_ascii=False))
        return {"ok": True, "message": "Speicherdatei wurde zurückgesetzt", "backup": backup_path}

    return {"ok": False, "message": f"Unbekannte Reparatur: {repair_id}"}


def _create_backup(repair_id: str) -> str:
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = Path.home() / "Library/Application Support/OKMediaCRM/backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    backed_up = []
    for db_path in [CRM_DB, SCR_DB, RES_DB]:
        if db_path.exists():
            dst = backup_dir / f"{db_path.stem}_{ts}.db"
            import shutil
            shutil.copy2(str(db_path), str(dst))
            backed_up.append(dst.name)

    if MEM_FILE.exists():
        dst = backup_dir / f"jarvis_memory_{ts}.json"
        import shutil
        shutil.copy2(str(MEM_FILE), str(dst))
        backed_up.append(dst.name)

    return str(backup_dir / f"backup_{ts}") + f" ({len(backed_up)} Dateien)"
