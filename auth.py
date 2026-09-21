"""
OK Media Consulting — Authentication & Authorization
JWT + bcrypt, Role/Permission system, Customer assignments, Audit log.
"""

import hashlib
import json
import os
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt as _bcrypt
from jose import JWTError, jwt

# Railway: set DATA_DIR env var to /app/data (persistent volume)
# Local Mac: defaults to ~/Library/Application Support/OKMediaCRM/
_default_data_dir = os.path.join(
    os.path.expanduser("~"), "Library", "Application Support", "OKMediaCRM"
)
_DATA_DIR = os.environ.get("DATA_DIR", _default_data_dir)
os.makedirs(_DATA_DIR, exist_ok=True)

AUTH_DB = os.path.join(_DATA_DIR, "okm_auth.db")

ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 30


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode()[:72], _bcrypt.gensalt()).decode()

def _verify_password(password: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except Exception:
        return False
_jwt_secret: str = ""


def set_jwt_secret(secret: str):
    global _jwt_secret
    _jwt_secret = secret


def _db():
    con = sqlite3.connect(AUTH_DB, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys = ON")
    return con


# ── Permission definitions ────────────────────────────────────────────────────

PERMISSIONS = [
    ("customers.view",    "Kunden anzeigen"),
    ("customers.create",  "Kunden anlegen"),
    ("customers.edit",    "Kunden bearbeiten"),
    ("customers.delete",  "Kunden löschen"),
    ("scripts.view",      "Skripte anzeigen"),
    ("scripts.create",    "Skripte erstellen"),
    ("scripts.edit",      "Skripte bearbeiten"),
    ("scripts.delete",    "Skripte löschen"),
    ("content.view",      "Inhalte anzeigen"),
    ("content.create",    "Inhalte erstellen"),
    ("content.edit",      "Inhalte bearbeiten"),
    ("content.delete",    "Inhalte löschen"),
    ("research.view",     "Recherchen anzeigen"),
    ("research.create",   "Recherchen erstellen"),
    ("research.edit",     "Recherchen bearbeiten"),
    ("research.delete",   "Recherchen löschen"),
    ("tasks.view",        "Aufgaben anzeigen"),
    ("tasks.create",      "Aufgaben erstellen"),
    ("tasks.edit",        "Aufgaben bearbeiten"),
    ("tasks.assign",      "Aufgaben zuweisen"),
    ("calendar.view",     "Kalender anzeigen"),
    ("calendar.edit",     "Kalender bearbeiten"),
    ("users.view",        "Benutzer anzeigen"),
    ("users.invite",      "Benutzer einladen"),
    ("users.edit",        "Benutzer bearbeiten"),
    ("users.disable",     "Benutzer deaktivieren"),
    ("settings.view",     "Einstellungen anzeigen"),
    ("settings.edit",     "Einstellungen bearbeiten"),
    ("analytics.view",    "Auswertungen anzeigen"),
    ("finance.view",      "Finanzen anzeigen"),
    ("finance.edit",      "Finanzen bearbeiten"),
]

_ALL = [p[0] for p in PERMISSIONS]

ROLE_PERMISSIONS = {
    "owner": _ALL,
    "manager": [p for p in _ALL if p not in ("finance.view", "finance.edit", "users.disable", "settings.edit")],
    "employee": [
        "customers.view",
        "scripts.view", "scripts.create", "scripts.edit",
        "content.view", "content.create", "content.edit",
        "research.view", "research.create",
        "tasks.view", "tasks.edit",
        "calendar.view",
    ],
}


# ── Database init ─────────────────────────────────────────────────────────────

def init_db():
    con = _db()
    con.executescript("""
        CREATE TABLE IF NOT EXISTS organizations (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            slug        TEXT UNIQUE NOT NULL,
            erstellt_am TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS roles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id          INTEGER NOT NULL,
            name            TEXT NOT NULL,
            label           TEXT NOT NULL,
            ist_system_rolle INTEGER DEFAULT 1,
            FOREIGN KEY (org_id) REFERENCES organizations(id)
        );

        CREATE TABLE IF NOT EXISTS permissions (
            key          TEXT PRIMARY KEY,
            beschreibung TEXT
        );

        CREATE TABLE IF NOT EXISTS role_permissions (
            rolle_id       INTEGER NOT NULL,
            permission_key TEXT NOT NULL,
            PRIMARY KEY (rolle_id, permission_key),
            FOREIGN KEY (rolle_id)       REFERENCES roles(id),
            FOREIGN KEY (permission_key) REFERENCES permissions(key)
        );

        CREATE TABLE IF NOT EXISTS users (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id          INTEGER NOT NULL,
            email           TEXT UNIQUE NOT NULL,
            password_hash   TEXT,
            vorname         TEXT NOT NULL,
            nachname        TEXT NOT NULL,
            rolle_id        INTEGER,
            status          TEXT DEFAULT 'active',
            profilbild_url  TEXT,
            letzter_login   TEXT,
            erstellt_am     TEXT DEFAULT (datetime('now')),
            einstellungen_json TEXT DEFAULT '{}',
            FOREIGN KEY (org_id)    REFERENCES organizations(id),
            FOREIGN KEY (rolle_id)  REFERENCES roles(id)
        );

        CREATE TABLE IF NOT EXISTS user_permissions (
            user_id        INTEGER NOT NULL,
            permission_key TEXT NOT NULL,
            erlaubt        INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, permission_key),
            FOREIGN KEY (user_id)        REFERENCES users(id),
            FOREIGN KEY (permission_key) REFERENCES permissions(key)
        );

        CREATE TABLE IF NOT EXISTS customer_assignments (
            user_id     INTEGER NOT NULL,
            kunden_id   INTEGER NOT NULL,
            db_quelle   TEXT NOT NULL,
            erstellt_von INTEGER,
            erstellt_am TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, kunden_id, db_quelle)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id           TEXT PRIMARY KEY,
            user_id      INTEGER NOT NULL,
            token_hash   TEXT NOT NULL,
            erstellt_am  TEXT DEFAULT (datetime('now')),
            laeuft_ab_am TEXT NOT NULL,
            widerrufen   INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS invitations (
            id           TEXT PRIMARY KEY,
            org_id       INTEGER NOT NULL,
            email        TEXT NOT NULL,
            rolle_id     INTEGER,
            token_hash   TEXT NOT NULL,
            eingeladen_von INTEGER,
            vorname      TEXT,
            nachname     TEXT,
            erstellt_am  TEXT DEFAULT (datetime('now')),
            laeuft_ab_am TEXT NOT NULL,
            verwendet_am TEXT,
            FOREIGN KEY (org_id) REFERENCES organizations(id)
        );

        CREATE TABLE IF NOT EXISTS audit_logs (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            org_id        INTEGER,
            user_id       INTEGER,
            aktion        TEXT NOT NULL,
            ressource_typ TEXT,
            ressource_id  TEXT,
            details_json  TEXT,
            erstellt_am   TEXT DEFAULT (datetime('now'))
        );
    """)

    for key, beschreibung in PERMISSIONS:
        con.execute(
            "INSERT OR IGNORE INTO permissions (key, beschreibung) VALUES (?, ?)",
            (key, beschreibung)
        )

    con.commit()
    con.close()


# ── Organization & Role setup ─────────────────────────────────────────────────

def ensure_org(name: str = "OK Media Consulting", slug: str = "okm") -> int:
    con = _db()
    existing = con.execute("SELECT id FROM organizations WHERE slug=?", (slug,)).fetchone()
    if existing:
        org_id = existing["id"]
    else:
        cur = con.execute(
            "INSERT INTO organizations (name, slug) VALUES (?, ?)", (name, slug)
        )
        org_id = cur.lastrowid

    for role_name, label in [("owner", "Geschäftsführer"), ("manager", "Manager"), ("employee", "Mitarbeiter")]:
        existing_role = con.execute(
            "SELECT id FROM roles WHERE org_id=? AND name=?", (org_id, role_name)
        ).fetchone()
        if not existing_role:
            cur2 = con.execute(
                "INSERT INTO roles (org_id, name, label, ist_system_rolle) VALUES (?, ?, ?, 1)",
                (org_id, role_name, label)
            )
            rolle_id = cur2.lastrowid
            for perm in ROLE_PERMISSIONS.get(role_name, []):
                con.execute(
                    "INSERT OR IGNORE INTO role_permissions (rolle_id, permission_key) VALUES (?, ?)",
                    (rolle_id, perm)
                )

    con.commit()
    con.close()
    return org_id


def has_users() -> bool:
    con = _db()
    count = con.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    con.close()
    return count > 0


def get_org_id() -> Optional[int]:
    con = _db()
    row = con.execute("SELECT id FROM organizations LIMIT 1").fetchone()
    con.close()
    return row["id"] if row else None


# ── User management ───────────────────────────────────────────────────────────

def create_owner(org_id: int, vorname: str, nachname: str, email: str, password: str) -> dict:
    con = _db()
    rolle = con.execute(
        "SELECT id FROM roles WHERE org_id=? AND name='owner'", (org_id,)
    ).fetchone()
    pw_hash = _hash_password(password)
    cur = con.execute(
        """INSERT INTO users (org_id, email, password_hash, vorname, nachname, rolle_id, status)
           VALUES (?, ?, ?, ?, ?, ?, 'active')""",
        (org_id, email.lower().strip(), pw_hash, vorname, nachname, rolle["id"])
    )
    user_id = cur.lastrowid
    con.commit()
    user = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    con.close()
    log_action(org_id, user_id, "account.created", "user", str(user_id), {"rolle": "owner"})
    return dict(user)


def authenticate_user(email: str, password: str) -> Optional[dict]:
    con = _db()
    user = con.execute(
        "SELECT * FROM users WHERE email=? AND status='active'",
        (email.lower().strip(),)
    ).fetchone()
    con.close()
    if not user or not _verify_password(password, user["password_hash"] or ""):
        return None
    return dict(user)


def get_user_permissions(user_id: int) -> set:
    con = _db()
    user = con.execute("SELECT rolle_id FROM users WHERE id=?", (user_id,)).fetchone()
    if not user:
        con.close()
        return set()

    perms = set()
    if user["rolle_id"]:
        rows = con.execute(
            "SELECT permission_key FROM role_permissions WHERE rolle_id=?",
            (user["rolle_id"],)
        ).fetchall()
        perms = {r["permission_key"] for r in rows}

    overrides = con.execute(
        "SELECT permission_key, erlaubt FROM user_permissions WHERE user_id=?",
        (user_id,)
    ).fetchall()
    for o in overrides:
        if o["erlaubt"]:
            perms.add(o["permission_key"])
        else:
            perms.discard(o["permission_key"])

    con.close()
    return perms


def get_user_role_name(user_id: int) -> Optional[str]:
    con = _db()
    row = con.execute(
        "SELECT r.name FROM users u JOIN roles r ON u.rolle_id=r.id WHERE u.id=?",
        (user_id,)
    ).fetchone()
    con.close()
    return row["name"] if row else None


def is_owner(user_id: int) -> bool:
    return get_user_role_name(user_id) == "owner"


def get_all_users(org_id: int) -> list:
    con = _db()
    rows = con.execute(
        """SELECT u.id, u.vorname, u.nachname, u.email, u.status,
                  u.letzter_login, u.erstellt_am,
                  r.name as rolle_name, r.label as rolle_label
           FROM users u
           LEFT JOIN roles r ON u.rolle_id = r.id
           WHERE u.org_id=?
           ORDER BY u.erstellt_am""",
        (org_id,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def get_user_by_id(user_id: int) -> Optional[dict]:
    con = _db()
    row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def update_user_status(user_id: int, status: str, by_user_id: int, org_id: int):
    con = _db()
    con.execute("UPDATE users SET status=? WHERE id=?", (status, user_id))
    con.commit()
    con.close()
    if status == "inactive":
        revoke_user_sessions(user_id)
    log_action(org_id, by_user_id, f"user.{status}", "user", str(user_id))


# ── Customer access control ───────────────────────────────────────────────────

def get_accessible_customer_ids(user_id: int, db_quelle: str) -> Optional[list]:
    """None = full access (owner/manager). List = restricted to these IDs."""
    role = get_user_role_name(user_id)
    if role in ("owner", "manager"):
        return None
    con = _db()
    rows = con.execute(
        "SELECT kunden_id FROM customer_assignments WHERE user_id=? AND db_quelle=?",
        (user_id, db_quelle)
    ).fetchall()
    con.close()
    return [r["kunden_id"] for r in rows]


def can_access_customer(user_id: int, kunden_id: int, db_quelle: str) -> bool:
    allowed = get_accessible_customer_ids(user_id, db_quelle)
    if allowed is None:
        return True
    return kunden_id in allowed


def assign_customer(user_id: int, kunden_id: int, db_quelle: str, by_user_id: int, org_id: int):
    con = _db()
    con.execute(
        """INSERT OR IGNORE INTO customer_assignments (user_id, kunden_id, db_quelle, erstellt_von)
           VALUES (?, ?, ?, ?)""",
        (user_id, kunden_id, db_quelle, by_user_id)
    )
    con.commit()
    con.close()
    log_action(org_id, by_user_id, "customer.assigned", "user", str(user_id),
               {"kunden_id": kunden_id, "db_quelle": db_quelle})


def unassign_customer(user_id: int, kunden_id: int, db_quelle: str, by_user_id: int, org_id: int):
    con = _db()
    con.execute(
        "DELETE FROM customer_assignments WHERE user_id=? AND kunden_id=? AND db_quelle=?",
        (user_id, kunden_id, db_quelle)
    )
    con.commit()
    con.close()
    log_action(org_id, by_user_id, "customer.unassigned", "user", str(user_id),
               {"kunden_id": kunden_id})


# ── JWT ───────────────────────────────────────────────────────────────────────

def _make_token(data: dict, expires: timedelta) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + expires
    return jwt.encode(payload, _jwt_secret, algorithm="HS256")


def create_tokens(user_id: int, org_id: int) -> tuple:
    access = _make_token(
        {"sub": str(user_id), "org": org_id, "type": "access"},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    refresh = _make_token(
        {"sub": str(user_id), "org": org_id, "type": "refresh"},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    )
    session_id = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(refresh.encode()).hexdigest()
    expires_at = (datetime.now(timezone.utc) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)).isoformat()
    con = _db()
    con.execute(
        "INSERT INTO sessions (id, user_id, token_hash, laeuft_ab_am) VALUES (?, ?, ?, ?)",
        (session_id, user_id, token_hash, expires_at)
    )
    con.execute("UPDATE users SET letzter_login=datetime('now') WHERE id=?", (user_id,))
    con.commit()
    con.close()
    return access, refresh


def verify_access_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, _jwt_secret, algorithms=["HS256"])
        if payload.get("type") != "access":
            return None
        user_id = int(payload["sub"])
        con = _db()
        user = con.execute(
            "SELECT * FROM users WHERE id=? AND status='active'", (user_id,)
        ).fetchone()
        con.close()
        if not user:
            return None
        u = dict(user)
        u["permissions"] = list(get_user_permissions(user_id))
        u["rolle_name"] = get_user_role_name(user_id)
        u.pop("password_hash", None)
        return u
    except JWTError:
        return None


def refresh_access_token(refresh_token: str) -> Optional[tuple]:
    try:
        payload = jwt.decode(refresh_token, _jwt_secret, algorithms=["HS256"])
        if payload.get("type") != "refresh":
            return None
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        con = _db()
        session = con.execute(
            "SELECT * FROM sessions WHERE token_hash=? AND widerrufen=0", (token_hash,)
        ).fetchone()
        if not session:
            con.close()
            return None
        con.execute("UPDATE sessions SET widerrufen=1 WHERE token_hash=?", (token_hash,))
        con.commit()
        con.close()
        return create_tokens(int(payload["sub"]), payload["org"])
    except JWTError:
        return None


def create_invitation(org_id: int, einlader_id: int, email: str, rolle: str) -> str:
    """Create an invitation token, returns the token string."""
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    inv_id = secrets.token_hex(16)
    expire = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    con = _db()
    rolle_row = con.execute(
        "SELECT id FROM roles WHERE org_id=? AND name=?", (org_id, rolle)
    ).fetchone()
    rolle_id = rolle_row["id"] if rolle_row else None
    con.execute(
        """INSERT INTO invitations (id, org_id, email, rolle_id, token_hash, eingeladen_von, laeuft_ab_am)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (inv_id, org_id, email.lower().strip(), rolle_id, token_hash, einlader_id, expire)
    )
    con.commit()
    con.close()
    return token


def accept_invitation(token: str, vorname: str, nachname: str, password: str) -> Optional[dict]:
    """Accept an invitation, create the user, return user dict or None."""
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    con = _db()
    inv = con.execute(
        "SELECT * FROM invitations WHERE token_hash=? AND verwendet_am IS NULL", (token_hash,)
    ).fetchone()
    if not inv:
        con.close()
        return None
    if datetime.fromisoformat(inv["laeuft_ab_am"]) < datetime.now(timezone.utc):
        con.close()
        return None

    pw_hash = _hash_password(password)
    try:
        cur = con.execute(
            """INSERT INTO users (org_id, email, password_hash, vorname, nachname, rolle_id, status)
               VALUES (?, ?, ?, ?, ?, ?, 'active')""",
            (inv["org_id"], inv["email"], pw_hash, vorname, nachname, inv["rolle_id"])
        )
        user_id = cur.lastrowid
        con.execute(
            "UPDATE invitations SET verwendet_am=datetime('now') WHERE id=?", (inv["id"],)
        )
        con.commit()
        user = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        con.close()
        log_action(inv["org_id"], user_id, "account.created", "user", str(user_id), {"via": "invitation"})
        return dict(user)
    except Exception:
        con.close()
        return None


def revoke_user_sessions(user_id: int):
    con = _db()
    con.execute("UPDATE sessions SET widerrufen=1 WHERE user_id=?", (user_id,))
    con.commit()
    con.close()


# ── Audit log ─────────────────────────────────────────────────────────────────

def log_action(org_id: int, user_id: int, aktion: str,
               ressource_typ: str = None, ressource_id: str = None, details: dict = None):
    con = _db()
    con.execute(
        """INSERT INTO audit_logs (org_id, user_id, aktion, ressource_typ, ressource_id, details_json)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (org_id, user_id, aktion, ressource_typ,
         str(ressource_id) if ressource_id else None,
         json.dumps(details, ensure_ascii=False) if details else None)
    )
    con.commit()
    con.close()


def get_audit_logs(org_id: int, limit: int = 50) -> list:
    con = _db()
    rows = con.execute(
        """SELECT a.*, u.vorname || ' ' || u.nachname as user_name
           FROM audit_logs a
           LEFT JOIN users u ON a.user_id = u.id
           WHERE a.org_id=?
           ORDER BY a.erstellt_am DESC LIMIT ?""",
        (org_id, limit)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


# ── Roles list ────────────────────────────────────────────────────────────────

def get_roles(org_id: int) -> list:
    con = _db()
    rows = con.execute(
        "SELECT id, name, label FROM roles WHERE org_id=? ORDER BY id", (org_id,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]
