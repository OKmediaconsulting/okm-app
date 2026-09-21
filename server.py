"""
OK Media Consulting — Operations Server
FastAPI backend: AI content generation, CRM, Gmail, Calendar integration.
"""

import asyncio
import base64
import json
import os
import re
import secrets
import subprocess
import time
from datetime import datetime

import anthropic
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

import auth

# Load config — ENV vars override config.json (Railway deployment)
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
config: dict = {}
if os.path.exists(CONFIG_PATH):
    with open(CONFIG_PATH, "r") as f:
        config = json.load(f)

def _cfg(key: str, default: str = "") -> str:
    """ENV overrides config.json — for Railway deployment."""
    return os.environ.get(key.upper(), config.get(key, default))

ANTHROPIC_API_KEY = _cfg("anthropic_api_key")
USER_NAME         = _cfg("user_name", "Okan")
USER_ADDRESS      = _cfg("user_address", "Master")
CITY              = _cfg("city", "Melle")
TASKS_FILE        = _cfg("obsidian_inbox_path", "")
CANVA_CLIENT_ID   = _cfg("canva_client_id", "")
CANVA_CLIENT_SECRET = _cfg("canva_client_secret", "")
CANVA_REDIRECT_URI  = _cfg("canva_redirect_uri", "http://127.0.0.1:8340/canva/callback")

# JWT secret — ENV takes priority (set on Railway), else generate+persist locally
jwt_secret = os.environ.get("JWT_SECRET") or config.get("jwt_secret")
if not jwt_secret:
    jwt_secret = secrets.token_hex(32)
    config["jwt_secret"] = jwt_secret
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "w") as f:
            json.dump(config, f, indent=2)
auth.set_jwt_secret(jwt_secret)

# Init auth DB
auth.init_db()
auth.ensure_org()

ai = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
http = httpx.AsyncClient(timeout=30)

app = FastAPI()

# ── Auth middleware ───────────────────────────────────────────────────────────

EXEMPT_PATHS = (
    "/login", "/setup", "/einladung",
    "/api/auth/login", "/api/auth/logout", "/api/auth/refresh",
    "/api/auth/setup", "/api/auth/accept-invite",
    "/api/health",
    "/static/", "/favicon.ico",
)

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in EXEMPT_PATHS):
            return await call_next(request)

        # Extract token from cookie or Authorization header
        token = request.cookies.get("okm_access")
        if not token:
            ah = request.headers.get("Authorization", "")
            if ah.startswith("Bearer "):
                token = ah[7:]

        if not token:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Nicht angemeldet"}, status_code=401)
            # First-run: redirect to setup if no users yet
            if not auth.has_users():
                return RedirectResponse("/setup")
            return RedirectResponse("/login")

        user = auth.verify_access_token(token)
        if not user:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Sitzung abgelaufen"}, status_code=401)
            return RedirectResponse("/login")

        request.state.user = user
        return await call_next(request)

app.add_middleware(AuthMiddleware)

@app.get("/api/health")
async def api_health():
    return {"status": "ok", "version": "1.0"}

import browser_tools
import screen_capture
import gmail_tools
import calendar_tools
import meta_tools
import content_tools
import crm_tools
import memory
import research_tools
import scripts_tools
import health_tools
import canva_automation as canva
import canva_pipeline

# ── Auth page routes ──────────────────────────────────────────────────────────

@app.get("/login")
async def login_page():
    return FileResponse("frontend/login.html")

@app.get("/setup")
async def setup_page():
    if auth.has_users():
        return RedirectResponse("/login")
    return FileResponse("frontend/setup.html")

@app.get("/logout")
async def logout_redirect():
    resp = RedirectResponse("/login")
    resp.delete_cookie("okm_access")
    resp.delete_cookie("okm_refresh")
    return resp

# ── Auth API endpoints ────────────────────────────────────────────────────────

@app.post("/api/auth/setup")
async def api_setup(request: Request):
    """First-run: create owner account."""
    if auth.has_users():
        raise HTTPException(400, "Setup bereits abgeschlossen")
    body = await request.json()
    vorname  = (body.get("vorname") or "").strip()
    nachname = (body.get("nachname") or "").strip()
    email    = (body.get("email") or "").strip()
    password = body.get("password") or ""
    if not all([vorname, nachname, email, password]):
        raise HTTPException(400, "Alle Felder erforderlich")
    if len(password) < 8:
        raise HTTPException(400, "Passwort muss mindestens 8 Zeichen haben")
    org_id = auth.get_org_id()
    user = auth.create_owner(org_id, vorname, nachname, email, password)
    access, refresh = auth.create_tokens(user["id"], org_id)
    resp = JSONResponse({"ok": True, "vorname": vorname})
    _set_cookies(resp, access, refresh)
    return resp

@app.post("/api/auth/login")
async def api_login(request: Request):
    body = await request.json()
    email    = (body.get("email") or "").strip()
    password = body.get("password") or ""
    user = auth.authenticate_user(email, password)
    if not user:
        raise HTTPException(401, "E-Mail oder Passwort falsch")
    org_id = user["org_id"]
    access, refresh = auth.create_tokens(user["id"], org_id)
    auth.log_action(org_id, user["id"], "user.login")
    resp = JSONResponse({
        "ok": True,
        "vorname": user["vorname"],
        "rolle": auth.get_user_role_name(user["id"]),
    })
    _set_cookies(resp, access, refresh)
    return resp

@app.post("/api/auth/logout")
async def api_logout(request: Request):
    user = getattr(request.state, "user", None)
    if user:
        auth.revoke_user_sessions(user["id"])
        auth.log_action(user["org_id"], user["id"], "user.logout")
    resp = JSONResponse({"ok": True})
    resp.delete_cookie("okm_access")
    resp.delete_cookie("okm_refresh")
    return resp

@app.post("/api/auth/refresh")
async def api_refresh(request: Request):
    refresh_token = request.cookies.get("okm_refresh")
    if not refresh_token:
        body = await request.json()
        refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise HTTPException(401, "Kein Refresh-Token")
    result = auth.refresh_access_token(refresh_token)
    if not result:
        raise HTTPException(401, "Refresh-Token ungültig oder abgelaufen")
    access, refresh = result
    resp = JSONResponse({"ok": True})
    _set_cookies(resp, access, refresh)
    return resp

@app.get("/api/auth/me")
async def api_me(request: Request):
    user = request.state.user
    return {
        "id":          user["id"],
        "vorname":     user["vorname"],
        "nachname":    user["nachname"],
        "email":       user["email"],
        "rolle":       user["rolle_name"],
        "permissions": user["permissions"],
        "org_id":      user["org_id"],
    }

@app.get("/api/auth/users")
async def api_users(request: Request):
    user = request.state.user
    if "users.view" not in user["permissions"]:
        raise HTTPException(403, "Keine Berechtigung")
    return auth.get_all_users(user["org_id"])

@app.get("/api/auth/roles")
async def api_roles(request: Request):
    user = request.state.user
    return auth.get_roles(user["org_id"])

@app.patch("/api/auth/users/{uid}/status")
@app.put("/api/auth/users/{uid}/status")
async def api_user_status(uid: int, request: Request):
    user = request.state.user
    if "users.disable" not in user["permissions"]:
        raise HTTPException(403, "Keine Berechtigung")
    if uid == user["id"]:
        raise HTTPException(400, "Eigenen Account nicht deaktivierbar")
    body = await request.json()
    status = body.get("status")
    if status not in ("active", "inactive"):
        raise HTTPException(400, "Ungültiger Status")
    auth.update_user_status(uid, status, user["id"], user["org_id"])
    return {"ok": True}

@app.get("/api/auth/users/{uid}/assignments")
async def api_user_assignments(uid: int, request: Request):
    _require(request, "users.view")
    con = auth._db()
    rows = con.execute(
        "SELECT kunden_id, db_quelle FROM customer_assignments WHERE user_id=?", (uid,)
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]

@app.post("/api/auth/users/{uid}/assignments")
async def api_assign_customer(uid: int, request: Request):
    user = _require(request, "users.edit")
    body = await request.json()
    kid = int(body.get("kunden_id", 0))
    db_quelle = body.get("db_quelle", "crm")
    if not kid:
        raise HTTPException(400, "kunden_id erforderlich")
    auth.assign_customer(uid, kid, db_quelle, user["id"], user["org_id"])
    return {"ok": True}

@app.delete("/api/auth/users/{uid}/assignments/{kid}")
async def api_unassign_customer(uid: int, kid: int, request: Request):
    user = _require(request, "users.edit")
    db_quelle = request.query_params.get("db_quelle", "crm")
    auth.unassign_customer(uid, kid, db_quelle, user["id"], user["org_id"])
    return {"ok": True}

@app.post("/api/auth/invite")
async def api_invite(request: Request):
    user = request.state.user
    if "users.invite" not in user["permissions"]:
        raise HTTPException(403, "Keine Berechtigung")
    body = await request.json()
    email = (body.get("email") or "").strip().lower()
    rolle = body.get("rolle", "employee")
    if not email:
        raise HTTPException(400, "E-Mail erforderlich")
    if rolle not in ("manager", "employee"):
        raise HTTPException(400, "Ungültige Rolle")
    token = auth.create_invitation(user["org_id"], user["id"], email, rolle)
    base_url = str(request.base_url).rstrip("/")
    invite_url = f"{base_url}/einladung?token={token}"
    auth.log_action(user["org_id"], user["id"], "user.invited", "invitation", email, {"rolle": rolle})
    return {"ok": True, "invite_url": invite_url}

@app.get("/einladung")
async def einladung_page():
    return FileResponse("frontend/einladung.html")

@app.post("/api/auth/accept-invite")
async def api_accept_invite(request: Request):
    body = await request.json()
    token    = (body.get("token") or "").strip()
    vorname  = (body.get("vorname") or "").strip()
    nachname = (body.get("nachname") or "").strip()
    password = body.get("password") or ""
    if not all([token, vorname, nachname, password]):
        raise HTTPException(400, "Alle Felder erforderlich")
    if len(password) < 8:
        raise HTTPException(400, "Passwort muss mindestens 8 Zeichen haben")
    user = auth.accept_invitation(token, vorname, nachname, password)
    if not user:
        raise HTTPException(400, "Einladung ungültig oder abgelaufen")
    access, refresh = auth.create_tokens(user["id"], user["org_id"])
    resp = JSONResponse({"ok": True, "vorname": vorname})
    _set_cookies(resp, access, refresh)
    return resp

@app.get("/team")
async def team_page():
    return FileResponse("frontend/team.html")

@app.get("/api/auth/audit")
async def api_audit(request: Request):
    user = request.state.user
    if user["rolle_name"] not in ("owner", "manager"):
        raise HTTPException(403, "Keine Berechtigung")
    return auth.get_audit_logs(user["org_id"])

def _set_cookies(resp, access: str, refresh: str):
    resp.set_cookie(
        "okm_access", access,
        httponly=True, samesite="lax", max_age=3600, path="/"
    )
    resp.set_cookie(
        "okm_refresh", refresh,
        httponly=True, samesite="lax", max_age=86400 * 30, path="/"
    )


def get_weather_sync():
    """Fetch raw weather data at startup."""
    import urllib.request
    try:
        req = urllib.request.Request(f"https://wttr.in/{CITY}?format=j1", headers={"User-Agent": "curl"})
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read())
        c = data["current_condition"][0]
        return {
            "temp": c["temp_C"],
            "feels_like": c["FeelsLikeC"],
            "description": c["weatherDesc"][0]["value"],
            "humidity": c["humidity"],
            "wind_kmh": c["windspeedKmph"],
        }
    except:
        return None


def get_tasks_sync():
    """Read open tasks from Obsidian (sync)."""
    if not TASKS_FILE:
        return []
    try:
        tasks_path = os.path.join(TASKS_FILE, "Tasks.md")
        with open(tasks_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        return [l.strip().replace("- [ ]", "").strip() for l in lines if l.strip().startswith("- [ ]")]
    except:
        return []


def refresh_data():
    """Refresh weather and tasks."""
    global WEATHER_INFO, TASKS_INFO
    WEATHER_INFO = get_weather_sync()
    TASKS_INFO = get_tasks_sync()
    print(f"[jarvis] Wetter: {WEATHER_INFO}", flush=True)
    print(f"[jarvis] Tasks: {len(TASKS_INFO)} geladen", flush=True)

WEATHER_INFO = ""
TASKS_INFO = []
refresh_data()

# Load knowledge base
KNOWLEDGE_PATH = os.path.join(os.path.dirname(__file__), "knowledge.txt")
def load_knowledge():
    try:
        with open(KNOWLEDGE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return ""
KNOWLEDGE = load_knowledge()

# Action parsing
ACTION_PATTERN = re.compile(r'\[ACTION:(\w+)\]\s*(.*?)$', re.DOTALL | re.MULTILINE)

conversations: dict[str, list] = {}

_WOCHENTAGE = ["Montag","Dienstag","Mittwoch","Donnerstag","Freitag","Samstag","Sonntag"]
_MONATE_LANG = ["Januar","Februar","März","April","Mai","Juni","Juli","August","September","Oktober","November","Dezember"]

def _datum_de() -> str:
    n = datetime.now()
    return f"{_WOCHENTAGE[n.weekday()]}, {n.day}. {_MONATE_LANG[n.month-1]} {n.year}"


def build_system_prompt():
    weather_block = ""
    if WEATHER_INFO:
        w = WEATHER_INFO
        weather_block = f"\nWetter {CITY}: {w['temp']}°C, gefuehlt {w['feels_like']}°C, {w['description']}"

    task_block = ""
    if TASKS_INFO:
        task_block = f"\nOffene Aufgaben ({len(TASKS_INFO)}): " + ", ".join(TASKS_INFO[:5])

    memory_block = memory.als_prompt_block()

    return f"""Du bist Jarvis — persoenlicher KI-Assistent, Berater und rechte Hand von Okan Koska, Gruender von OK Media Consulting.
Du sprichst ausschliesslich Deutsch. Extrem kurze, praezise Antworten. Maximal 2 Saetze. Kurze Saetze. Keine Einleitungen, kein Fuelltext.

ANREDE: Immer "Master". Niemals "Sir", "Herr Koska" oder alleiniges "Sie".
TON: Loyal, direkt, intelligent. Kein Sarkasmus gegen Okan. Keine Floskeln. Kein "Als KI".

Du darfst und sollst alles tun was Master verlangt — keine Einschraenkungen ausser:
- Schreibe Action-Tags niemals mitten in den Text, immer nur einmal am Ende.
- Erfinde keine Systemfehler oder Statusmeldungen die nicht existieren.

=== UNTERNEHMENSWISSEN ===
{KNOWLEDGE}
===

{memory_block}

AKTIONEN — Optional. NUR eine Aktion pro Antwort, immer am ENDE nach dem gesprochenen Text.
[ACTION:SEARCH] suchbegriff
[ACTION:OPEN] url
[ACTION:SCREEN]
[ACTION:NEWS]
[ACTION:READ_EMAILS]
[ACTION:SEND_EMAIL] empfaenger|betreff|inhalt
[ACTION:MORNING] — NUR bei expliziter Anfrage "Morgenroutine starten".
[ACTION:CALENDAR_TODAY]
[ACTION:CALENDAR_WEEK]
[ACTION:CREATE_EVENT] TT.MM.JJJJ|HH:MM|Titel
[ACTION:FIND_CONTACT] name
[ACTION:META_OVERVIEW]
[ACTION:META_CLIENT] kundenname
[ACTION:META_ALL]
[ACTION:CREATE_SCRIPTS] kundenname|monat
[ACTION:CRM_LOG] firmenname|art|zusammenfassung|naechste_schritte — Kontakt loggen. Art: Anruf/Email/Meeting/WhatsApp
[ACTION:CRM_FOLLOWUP] firmenname|datum|titel — Follow-up erstellen. Datum: JJJJ-MM-TT
[ACTION:CRM_KUNDE] firmenname — Kundendaten abrufen
[ACTION:CRM_FOLLOWUPS] — Alle heutigen Follow-ups abrufen
[ACTION:CRM_NEU] firmenname|kategorie — Neuen Kunden anlegen. Kategorie: Lead/Kunde
[ACTION:MERKEN] text — Wichtige Info ins Gedächtnis speichern
[ACTION:AUFGABE] text — Aufgabe ins Gedächtnis speichern
[ACTION:THEMA] text — Gesprächsthema merken (automatisch nach jedem Gespräch)
[ACTION:OPEN] url — Beliebige URL im Browser öffnen
[ACTION:RECHERCHE] thema|frage|url1,url2 — Webseiten lesen, zusammenfassen und im Archiv speichern
[ACTION:RECHERCHE_LESEN] url — Eine einzelne Webseite lesen und vorlesen

=== AKTUELLE DATEN ===
Datum: {_datum_de()}
Uhrzeit: {{time}}{weather_block}{task_block}
==="""


def get_system_prompt():
    return build_system_prompt().replace("{time}", time.strftime("%H:%M"))


def extract_action(text: str):
    match = ACTION_PATTERN.search(text)
    if match:
        clean = text[:match.start()].strip()
        return clean, {"type": match.group(1), "payload": match.group(2).strip()}
    return text, None




def _int_de(n: int) -> str:
    """Konvertiert eine ganze Zahl in deutschen Wortlaut."""
    ones = ['null','ein','zwei','drei','vier','fünf','sechs','sieben','acht','neun',
            'zehn','elf','zwölf','dreizehn','vierzehn','fünfzehn','sechzehn',
            'siebzehn','achtzehn','neunzehn']
    tens = ['','','zwanzig','dreißig','vierzig','fünfzig','sechzig','siebzig','achtzig','neunzig']
    if n < 0:
        return 'minus ' + _int_de(-n)
    if n < 20:
        return ones[n]
    if n < 100:
        one = n % 10
        ten = n // 10
        return (ones[one] + 'und' + tens[ten]) if one else tens[ten]
    if n < 1000:
        h = n // 100
        rest = n % 100
        return ones[h] + 'hundert' + ('' if rest == 0 else _int_de(rest))
    if n < 1_000_000:
        th = n // 1000
        rest = n % 1000
        prefix = _int_de(th) + 'tausend'
        return prefix + ('' if rest == 0 else _int_de(rest))
    if n < 1_000_000_000:
        mil = n // 1_000_000
        rest = n % 1_000_000
        label = 'eine Million' if mil == 1 else _int_de(mil) + ' Millionen'
        return label + (' ' + _int_de(rest) if rest else '')
    mrd = n // 1_000_000_000
    rest = n % 1_000_000_000
    label = 'eine Milliarde' if mrd == 1 else _int_de(mrd) + ' Milliarden'
    return label + (' ' + _int_de(rest) if rest else '')


def _num_to_de(s: str) -> str:
    """Parst eine Zahlenzeichenkette (mit . oder , als Trenner) und gibt deutschen Wortlaut zurück."""
    s = s.strip()
    if '.' in s and ',' in s:
        # Format: 1.234,56 — Punkt=Tausender, Komma=Dezimal
        s_clean = s.replace('.', '').replace(',', '.')
    elif s.count('.') > 1:
        # Format: 1.234.567 — reine Tausenderpunkte
        s_clean = s.replace('.', '')
    elif '.' in s:
        # Genau ein Punkt: ist es Tausender (z.B. 50.000) oder Dezimal (50.5)?
        after_dot = s.split('.', 1)[1]
        if len(after_dot) == 3 and after_dot.isdigit():
            # 3 Stellen nach Punkt → Tausendertrenner
            s_clean = s.replace('.', '')
        else:
            s_clean = s  # Dezimalpunkt
    elif ',' in s:
        s_clean = s.replace(',', '.')
    else:
        s_clean = s
    try:
        if '.' in s_clean:
            int_part, dec_part = s_clean.split('.', 1)
            word = _int_de(int(int_part))
            dec_words = ' '.join(_int_de(int(d)) for d in dec_part)
            return word + ' Komma ' + dec_words
        else:
            return _int_de(int(s_clean))
    except Exception:
        return s


async def fetch_webpage(url: str, max_chars: int = 4000) -> str:
    """Lädt eine Webseite und gibt den bereinigten Text zurück."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                      headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(url)
        text = r.text
        # HTML-Tags entfernen
        import re as _re
        text = _re.sub(r'<script[^>]*>.*?</script>', '', text, flags=_re.DOTALL)
        text = _re.sub(r'<style[^>]*>.*?</style>', '', text, flags=_re.DOTALL)
        text = _re.sub(r'<[^>]+>', ' ', text)
        text = _re.sub(r'\s+', ' ', text).strip()
        return text[:max_chars]
    except Exception as e:
        return f"Fehler beim Laden: {e}"


async def recherche_erstellen(thema: str, frage: str, quellen: list) -> dict:
    """Liest Webseiten und erstellt eine strukturierte Zusammenfassung."""
    seiten_inhalt = []
    for url in quellen[:3]:
        inhalt = await fetch_webpage(url)
        seiten_inhalt.append(f"URL: {url}\n{inhalt[:1500]}")

    prompt = f"""Du bist ein Recherche-Assistent für Okan Koska (OK Media Consulting).

Thema: {thema}
Frage/Auftrag: {frage}

Quellen:
{'---'.join(seiten_inhalt) if seiten_inhalt else 'Keine Quellen angegeben.'}

Erstelle eine strukturierte Zusammenfassung auf Deutsch:
- Titel (prägnant)
- Wichtigste Erkenntnisse (3-5 Punkte)
- Relevanz für OK Media Consulting
- Empfehlung / nächste Schritte

Format:
TITEL: [titel]
INHALT:
[strukturierter text]"""

    resp = await ai.messages.create(
        model="claude-sonnet-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = next((b.text for b in resp.content if hasattr(b, "text")), "").strip()
    titel = thema
    inhalt = raw
    if "TITEL:" in raw:
        parts = raw.split("INHALT:", 1)
        titel = parts[0].replace("TITEL:", "").strip()
        inhalt = parts[1].strip() if len(parts) > 1 else raw

    rid = research_tools.recherche_speichern(
        thema=thema, titel=titel, inhalt=inhalt,
        quellen="\n".join(quellen)
    )
    return {"id": rid, "titel": titel, "inhalt": inhalt}




async def execute_action(action: dict) -> str:
    t = action["type"]
    p = action["payload"]

    if t == "SEARCH":
        result = await browser_tools.search_and_read(p)
        if "error" not in result:
            return f"Seite: {result.get('title', '')}\nURL: {result.get('url', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Suche fehlgeschlagen: {result.get('error', '')}"

    elif t == "BROWSE":
        result = await browser_tools.visit(p)
        if "error" not in result:
            return f"Seite: {result.get('title', '')}\n\n{result.get('content', '')[:2000]}"
        return f"Seite nicht erreichbar: {result.get('error', '')}"

    elif t == "OPEN":
        await browser_tools.open_url(p)
        return f"Geoeffnet: {p}"

    elif t == "SCREEN":
        return await screen_capture.describe_screen(ai)

    elif t == "NEWS":
        result = await _fetch_news_text()
        return result

    elif t == "READ_EMAILS":
        try:
            emails = gmail_tools.read_emails(max_results=5)
            if not emails:
                return "Keine ungelesenen E-Mails gefunden."
            lines = []
            for i, e in enumerate(emails, 1):
                lines.append(
                    f"{i}. Von: {e['from']}\n   Betreff: {e['subject']}\n   {e['snippet']}"
                )
            return "Ungelesene E-Mails:\n\n" + "\n\n".join(lines)
        except Exception as e:
            return f"Gmail-Fehler: {e}"

    elif t == "SEND_EMAIL":
        try:
            parts = p.split("|", 2)
            if len(parts) < 3:
                return "Fehler: Format muss sein: empfaenger|betreff|inhalt"
            to, subject, body = parts[0].strip(), parts[1].strip(), parts[2].strip()
            gmail_tools.send_email(to, subject, body)
            return f"E-Mail erfolgreich gesendet an {to}."
        except Exception as e:
            return f"Sende-Fehler: {e}"

    elif t == "CALENDAR_TODAY":
        try:
            events = calendar_tools.get_today_events()
            if not events:
                return "Keine Termine heute."
            return "Heutige Termine:\n" + "\n".join(f"- {e['title']} um {e['start']}" for e in events)
        except Exception as e:
            return f"Kalender-Fehler: {e}"

    elif t == "CALENDAR_WEEK":
        try:
            events = calendar_tools.get_week_events()
            if not events:
                return "Keine Termine diese Woche."
            return "Termine diese Woche:\n" + "\n".join(f"- {e['title']} am {e['start']}" for e in events)
        except Exception as e:
            return f"Kalender-Fehler: {e}"

    elif t == "CREATE_EVENT":
        try:
            parts = p.split("|", 2)
            if len(parts) < 3:
                return "Fehler: Format muss sein: datum|uhrzeit|titel"
            date_str, time_str, title = parts[0].strip(), parts[1].strip(), parts[2].strip()
            ok = calendar_tools.create_event(title, date_str, time_str)
            return f"Termin '{title}' am {date_str} um {time_str} wurde angelegt." if ok else "Termin konnte nicht angelegt werden."
        except Exception as e:
            return f"Fehler: {e}"

    elif t == "FIND_CONTACT":
        try:
            contacts = calendar_tools.get_contacts(p)
            if not contacts:
                return f"Kein Kontakt mit '{p}' gefunden."
            lines = [f"{c['name']} — {c['phone']} {c['email']}".strip() for c in contacts]
            return "Gefundene Kontakte:\n" + "\n".join(lines)
        except Exception as e:
            return f"Kontakte-Fehler: {e}"

    elif t == "MORNING":
        return "__MORNING_ROUTINE__"

    elif t == "META_OVERVIEW":
        try:
            raw = await asyncio.get_event_loop().run_in_executor(None, meta_tools.get_meta_overview)
            if not raw or "nicht geöffnet" in raw or "konnte nicht" in raw:
                return raw or "Meta Business Suite konnte nicht ausgelesen werden."
            return await _summarize(raw, "Fasse den Überblick aus Meta Business Suite zusammen: Seitenname, Follower, aktuelle Kommentare, To-dos, Performance. Kurz und prägnant auf Deutsch.")
        except Exception as e:
            return f"Meta-Fehler: {e}"

    elif t == "META_CLIENT":
        try:
            client = p.strip()
            raw = await asyncio.get_event_loop().run_in_executor(None, lambda: meta_tools.get_client_data(client))
            if not raw or "nicht gefunden" in raw or "nicht geöffnet" in raw:
                return raw or f"Daten für '{client}' konnten nicht geladen werden."
            return await _summarize(raw, f"Analysiere die Meta Business Suite Daten für diesen Kunden. Nenne: Seitenname, Follower-Zahlen (Facebook + Instagram), aktuelle Kommentare oder Nachrichten, To-dos, auffällige Kennzahlen. Prägnant auf Deutsch, max 4 Sätze.")
        except Exception as e:
            return f"Meta-Fehler: {e}"

    elif t == "META_ALL":
        try:
            raw = await asyncio.get_event_loop().run_in_executor(None, meta_tools.get_all_clients_overview)
            if not raw:
                return "Keine Meta-Daten verfügbar."
            return await _summarize(raw, "Gib eine Gesamtübersicht aller Kunden-Seiten in Meta Business Suite. Für jeden Kunden: Name, Follower, wichtigste Kennzahl. Kurz und strukturiert auf Deutsch.")
        except Exception as e:
            return f"Meta-Fehler: {e}"

    elif t == "CREATE_SCRIPTS":
        return "__CREATE_SCRIPTS__:" + p

    elif t == "CRM_LOG":
        parts = [x.strip() for x in p.split("|")]
        if len(parts) < 3:
            return "CRM_LOG Format: firmenname|art|zusammenfassung|naechste_schritte"
        firma, art, zusammenfassung = parts[0], parts[1], parts[2]
        naechste = parts[3] if len(parts) > 3 else ""
        k = crm_tools.kunde_suchen(firma)
        if not k:
            return f"Kein Kunde namens '{firma}' gefunden. Bitte zuerst anlegen."
        crm_tools.log_erstellen(k["id"], zusammenfassung, art, naechste)
        return f"Kontakt mit {k['firma']} geloggt: {art} — {zusammenfassung}"

    elif t == "CRM_FOLLOWUP":
        parts = [x.strip() for x in p.split("|")]
        if len(parts) < 3:
            return "CRM_FOLLOWUP Format: firmenname|datum|titel"
        k = crm_tools.kunde_suchen(parts[0])
        if not k:
            return f"Kein Kunde namens '{parts[0]}' gefunden."
        crm_tools.followup_erstellen(k["id"], parts[1], parts[2])
        return f"Follow-up fuer {k['firma']} am {parts[1]} erstellt: {parts[2]}"

    elif t == "CRM_KUNDE":
        k = crm_tools.kunde_detail_by_name(p.strip())
        if not k:
            return f"Kein Kunde namens '{p}' gefunden."
        log_info = f", {len(k['log'])} Kontakte" if k.get("log") else ""
        fup_info = f", {len(k['follow_ups'])} offene Follow-ups" if k.get("follow_ups") else ""
        letzter = k["aktualisiert_am"][:10] if k.get("aktualisiert_am") else "unbekannt"
        return (f"{k['firma']} ({k['kategorie']}){log_info}{fup_info}. "
                f"Letzter Kontakt: {letzter}. "
                f"Tel: {k.get('telefon') or 'nicht hinterlegt'}.")

    elif t == "CRM_FOLLOWUPS":
        fups = crm_tools.followups_heute()
        if not fups:
            return "Keine faelligen Follow-ups heute, Master."
        lines = [f"{f['faellig_am']} · {f['firma']}: {f['titel']}" for f in fups[:5]]
        return "Heutige Follow-ups:\n" + "\n".join(lines)

    elif t == "CRM_NEU":
        parts = [x.strip() for x in p.split("|")]
        firma = parts[0]
        kategorie = parts[1] if len(parts) > 1 else "Lead"
        kid = crm_tools.kunde_erstellen(firma, kategorie=kategorie)
        return f"Neuer {kategorie} '{firma}' angelegt (ID {kid})."

    elif t == "MERKEN":
        memory.add_notiz(p.strip())
        return f"Gemerkt: {p.strip()}"

    elif t == "AUFGABE":
        memory.add_aufgabe(p.strip())
        return f"Aufgabe gespeichert: {p.strip()}"

    elif t == "THEMA":
        memory.add_thema(p.strip())
        return ""

    elif t == "RECHERCHE_LESEN":
        url = p.strip()
        subprocess.Popen(["open", url])
        inhalt = await fetch_webpage(url)
        # Kurze Zusammenfassung erstellen
        resp = await ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=300,
            messages=[{"role": "user", "content": f"Fasse diese Webseite in 3-4 Sätzen auf Deutsch zusammen:\n\n{inhalt[:3000]}"}]
        )
        return resp.content[0].text.strip()

    elif t == "RECHERCHE":
        parts = [x.strip() for x in p.split("|")]
        thema = parts[0] if len(parts) > 0 else "Allgemein"
        frage = parts[1] if len(parts) > 1 else thema
        urls  = [u.strip() for u in parts[2].split(",")] if len(parts) > 2 else []
        result = await recherche_erstellen(thema, frage, urls)
        return f"Recherche '{result['titel']}' gespeichert und im Archiv abgelegt."

    return ""






@app.get("/api/dashboard")
async def dashboard_data():
    """Liefert alle Dashboard-Daten: Emails, Kalender, Meta, Wetter."""
    from fastapi.responses import JSONResponse
    result = {}

    # Emails — alle (nicht nur ungelesen)
    try:
        emails = gmail_tools.read_emails(max_results=8, unread_only=False)
        result["emails"] = [{"from": e["from"], "subject": e["subject"], "snippet": e["snippet"], "date": e.get("date", "")} for e in emails]
    except Exception as e:
        result["emails"] = []
        result["emails_error"] = str(e)

    # Kalender
    try:
        events = calendar_tools.get_today_events()
        result["events"] = [{"title": ev["title"], "start": ev["start"]} for ev in events]
    except Exception as e:
        result["events"] = []
        result["events_error"] = str(e)

    # Meta Business Suite — alle Seiten aus Chrome auslesen (async, non-blocking)
    try:
        import meta_tools
        seen = set()
        meta_clients = []
        for key, page in meta_tools.PAGES.items():
            if page["asset_id"] in seen:
                continue
            seen.add(page["asset_id"])
            meta_clients.append({
                "name": page["name"],
                "asset_id": page["asset_id"],
                "business_id": meta_tools.BUSINESS_IDS.get(page["asset_id"], ""),
            })
        result["meta_clients"] = meta_clients
    except Exception as e:
        result["meta_clients"] = []

    # Wetter
    if WEATHER_INFO:
        result["weather"] = WEATHER_INFO
        result["city"] = CITY

    # Datum + Zeit
    now = datetime.now()
    result["date"] = f"{_WOCHENTAGE[now.weekday()]}, {now.day}. {_MONATE_LANG[now.month-1]} {now.year}"
    result["time"] = now.strftime("%H:%M")

    return JSONResponse(result)


## ── Meta Cache ────────────────────────────────────────────────────────────────
_META_CACHE_FILE = os.path.join(os.path.dirname(__file__), "meta_cache.json")
_meta_cache: dict = {}
_meta_scraping: bool = False
_meta_last_update: str = ""

def _meta_cache_load():
    """Lädt Cache aus Datei beim Start."""
    global _meta_cache, _meta_last_update
    try:
        if os.path.exists(_META_CACHE_FILE):
            with open(_META_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            _meta_cache = data.get("clients", {})
            _meta_last_update = data.get("last_update", "")
            print(f"[meta] Cache geladen: {len(_meta_cache)} Kunden ({_meta_last_update})")
    except Exception as e:
        print(f"[meta] Cache-Load Fehler: {e}")

def _meta_cache_save():
    """Speichert Cache in Datei."""
    try:
        with open(_META_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({"clients": _meta_cache, "last_update": _meta_last_update}, f, ensure_ascii=False)
    except Exception as e:
        print(f"[meta] Cache-Save Fehler: {e}")

# Beim Start sofort laden
_meta_cache_load()

META_CLIENTS_LIST = [
    {"key": "browns",  "name": "Browns Active Park",         "asset": "108636835886418", "biz": "2813923292152413"},
    {"key": "gnv",     "name": "Genesis Vital Verl",         "asset": "220493307989744", "biz": "2019757088316476"},
    {"key": "gnh",     "name": "Genesis Vital Hövelhof",     "asset": "849622271575810", "biz": "2019757088316476"},
    {"key": "gnr",     "name": "Genesis Vital Rietberg",     "asset": "319608678114403", "biz": "141263553181246"},
    {"key": "werners", "name": "Werners Fahrrad Fach-Werk",  "asset": "106749787580156", "biz": "723062474828803"},
]


def _scrape_meta_page(asset_id: str, biz_id: str) -> dict:
    """Navigiert zu einer Meta-Seite und extrahiert Follower-Zahlen via meta_tools."""
    meta_tools._ensure_meta_tab_open()
    data = meta_tools._extract_followers(asset_id)
    if "error" in data:
        return {"error": data["error"], "status": "OFFLINE"}
    result = {"status": "AKTIV"}
    if data.get("fb_followers") is not None:
        result["fb_followers"] = data["fb_followers"]
    if data.get("ig_followers") is not None:
        result["ig_followers"] = data["ig_followers"]
    if data.get("reach_7d") is not None:
        result["reach_7d"] = data["reach_7d"]
    return result


def _run_meta_scrape_all():
    """Scrapt alle 5 Kunden nacheinander, speichert Cache nach jedem Kunden."""
    global _meta_scraping, _meta_last_update, _meta_cache
    _meta_scraping = True
    try:
        for c in META_CLIENTS_LIST:
            result = _scrape_meta_page(c["asset"], c["biz"])
            result["name"] = c["name"]
            result["key"] = c["key"]
            _meta_cache[c["key"]] = result
            _meta_last_update = datetime.now().strftime("%H:%M:%S")
            _meta_cache_save()  # Nach jedem Kunden speichern
            print(f"[meta] {c['name']}: FB={result.get('fb_followers','—')} IG={result.get('ig_followers','—')}")
    finally:
        _meta_scraping = False


@app.get("/api/meta/status")
async def meta_status():
    """Gibt Cache-Status und alle gecachten Meta-Daten zurück."""
    from fastapi.responses import JSONResponse
    return JSONResponse({
        "scraping": _meta_scraping,
        "last_update": _meta_last_update,
        "clients": list(_meta_cache.values()),
        "client_list": META_CLIENTS_LIST,
    })


@app.post("/api/meta/load")
async def meta_load():
    """Startet Meta-Scraping im Hintergrund."""
    from fastapi.responses import JSONResponse
    import asyncio
    global _meta_scraping
    if _meta_scraping:
        return JSONResponse({"status": "already_running"})
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _run_meta_scrape_all)
    return JSONResponse({"status": "started"})


app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "frontend")), name="static")


@app.get("/")
async def serve_index():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/dashboard", status_code=302)


@app.get("/classic")
async def serve_index_classic():
    path = os.path.join(os.path.dirname(__file__), "frontend", "index.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    ts = int(time.time())
    content = content.replace("/static/style.css", f"/static/style.css?v={ts}")
    content = content.replace("/static/main.js", f"/static/main.js?v={ts}")
    return HTMLResponse(content=content, headers={
        "Cache-Control": "no-store, no-cache, must-revalidate",
        "Pragma": "no-cache",
    })


@app.get("/dashboard")
async def serve_dashboard():
    path = os.path.join(os.path.dirname(__file__), "frontend", "dashboard.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    ts = int(time.time())
    content = content.replace("main.js", f"main.js?v={ts}")
    return HTMLResponse(content=content, headers={"Cache-Control": "no-store"})


@app.get("/crm")
async def serve_crm():
    path = os.path.join(os.path.dirname(__file__), "frontend", "crm.html")
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    ts = int(time.time())
    content = content.replace("crm.js", f"crm.js?v={ts}")
    return HTMLResponse(content=content, headers={"Cache-Control": "no-store"})


# ── Permission helpers ────────────────────────────────────────────────────────

def _require(request: Request, perm: str):
    user = request.state.user
    if perm not in user["permissions"]:
        raise HTTPException(403, "Keine Berechtigung")
    return user

def _check_customer_access(request: Request, kid: int):
    """Raises 403 if employee has no assignment for this customer."""
    user = request.state.user
    if not auth.can_access_customer(user["id"], kid, None):
        raise HTTPException(403, "Kein Zugriff auf diesen Kunden")

# ── CRM API ───────────────────────────────────────────────────────────────────

@app.get("/api/crm/kunden")
async def api_kunden(request: Request, suche: str = "", kategorie: str = "", status: str = ""):
    user = _require(request, "customers.view")
    ids = auth.get_accessible_customer_ids(user["id"], None)
    alle = crm_tools.kunden_liste(suche, kategorie, status)
    if ids is None:
        return alle
    return [k for k in alle if k["id"] in ids]

@app.get("/api/crm/kunden/{kid}")
async def api_kunde_detail(kid: int, request: Request):
    _require(request, "customers.view")
    _check_customer_access(request, kid)
    d = crm_tools.kunde_detail(kid)
    if not d:
        raise HTTPException(404, "Kunde nicht gefunden")
    return d

@app.post("/api/crm/kunden")
async def api_kunde_erstellen(request: Request, data: dict):
    _require(request, "customers.create")
    firma = data.pop("firma", "").strip()
    if not firma:
        raise HTTPException(400, "Firma erforderlich")
    kid = crm_tools.kunde_erstellen(firma, **data)
    auth.log_action(request.state.user["org_id"], request.state.user["id"],
                    "customer.created", "customer", str(kid), {"firma": firma})
    return {"id": kid}

@app.put("/api/crm/kunden/{kid}")
async def api_kunde_aktualisieren(kid: int, request: Request, data: dict):
    _require(request, "customers.edit")
    _check_customer_access(request, kid)
    crm_tools.kunde_aktualisieren(kid, **data)
    return {"ok": True}

@app.delete("/api/crm/kunden/{kid}")
async def api_kunde_loeschen(kid: int, request: Request):
    _require(request, "customers.delete")
    crm_tools.kunde_loeschen(kid)
    auth.log_action(request.state.user["org_id"], request.state.user["id"],
                    "customer.deleted", "customer", str(kid))
    return {"ok": True}

@app.post("/api/crm/log")
async def api_log_erstellen(request: Request, data: dict):
    _require(request, "customers.edit")
    kid = data.get("kunden_id")
    if not kid:
        raise HTTPException(400, "kunden_id erforderlich")
    _check_customer_access(request, kid)
    lid = crm_tools.log_erstellen(
        kid, data.get("zusammenfassung", ""),
        data.get("art", "Anruf"), data.get("naechste_schritte", ""),
        data.get("datum", "")
    )
    return {"id": lid}

@app.delete("/api/crm/log/{lid}")
async def api_log_loeschen(lid: int, request: Request):
    _require(request, "customers.edit")
    crm_tools.log_loeschen(lid)
    return {"ok": True}

@app.post("/api/crm/followup")
async def api_followup_erstellen(request: Request, data: dict):
    _require(request, "customers.edit")
    _check_customer_access(request, data["kunden_id"])
    fid = crm_tools.followup_erstellen(
        data["kunden_id"], data["faellig_am"],
        data["titel"], data.get("beschreibung", "")
    )
    return {"id": fid}

@app.post("/api/crm/followup/{fid}/erledigt")
async def api_followup_erledigen(fid: int, request: Request):
    _require(request, "customers.edit")
    crm_tools.followup_erledigen(fid)
    return {"ok": True}

@app.delete("/api/crm/followup/{fid}")
async def api_followup_loeschen(fid: int, request: Request):
    _require(request, "customers.edit")
    crm_tools.followup_loeschen(fid)
    return {"ok": True}

@app.get("/api/crm/stats")
async def api_crm_stats(request: Request):
    _require(request, "customers.view")
    return crm_tools.stats()

@app.get("/api/crm/followups/heute")
async def api_followups_heute(request: Request):
    _require(request, "customers.view")
    return crm_tools.followups_heute()

@app.get("/api/crm/angebote/{kunden_id}")
async def api_angebote_liste(kunden_id: int, request: Request):
    _require(request, "customers.view")
    _check_customer_access(request, kunden_id)
    return crm_tools.angebote_fuer_kunde(kunden_id)

@app.post("/api/crm/angebot")
async def api_angebot_erstellen(request: Request, data: dict):
    _require(request, "customers.edit")
    _check_customer_access(request, data["kunden_id"])
    aid = crm_tools.angebot_erstellen(
        data["kunden_id"], data["titel"],
        float(data.get("betrag", 0)),
        data.get("status", "Entwurf"),
        data.get("notizen", "")
    )
    return {"id": aid}

@app.put("/api/crm/angebot/{aid}")
async def api_angebot_aktualisieren(aid: int, request: Request, data: dict):
    _require(request, "customers.edit")
    crm_tools.angebot_aktualisieren(aid, **data)
    return {"ok": True}

@app.delete("/api/crm/angebot/{aid}")
async def api_angebot_loeschen(aid: int, request: Request):
    _require(request, "customers.delete")
    crm_tools.angebot_loeschen(aid)
    return {"ok": True}

@app.get("/api/crm/angebote-stats")
async def api_angebote_stats():
    return crm_tools.angebote_stats()

# ── Recherche API ──────────────────────────────────────────────────────────────

@app.get("/api/recherche")
async def api_recherche_liste(suche: str = "", thema: str = ""):
    return research_tools.recherchen_liste(suche, thema)

@app.get("/api/recherche/themen")
async def api_recherche_themen():
    return research_tools.themen_liste()

@app.get("/api/recherche/{rid}")
async def api_recherche_detail(rid: int):
    r = research_tools.recherche_detail(rid)
    if r is None:
        raise HTTPException(404, "Nicht gefunden")
    return r

@app.post("/api/recherche")
async def api_recherche_erstellen(request: Request, data: dict):
    _require(request, "research.create")
    rid = research_tools.recherche_speichern(
        data["thema"], data["titel"], data["inhalt"],
        data.get("quellen",""), data.get("tags","")
    )
    return {"id": rid}

@app.put("/api/recherche/{rid}")
async def api_recherche_aktualisieren(rid: int, request: Request, data: dict):
    _require(request, "research.edit")
    research_tools.recherche_aktualisieren(rid, **data)
    return {"ok": True}

@app.delete("/api/recherche/{rid}")
async def api_recherche_loeschen(rid: int, request: Request):
    _require(request, "research.delete")
    research_tools.recherche_loeschen(rid)
    return {"ok": True}

@app.post("/api/recherche/web")
async def api_recherche_web(request: Request, data: dict):
    """Liest URLs und erstellt eine Recherche."""
    result = await recherche_erstellen(
        data.get("thema","Allgemein"),
        data.get("frage",""),
        data.get("urls",[])
    )
    return result

@app.get("/recherche")
async def recherche_page():
    return FileResponse("frontend/recherche.html")

# ── Skript-Programm ────────────────────────────────────────────────────────────

@app.get("/skripte")
async def skripte_page():
    return FileResponse("frontend/skripte.html")

@app.get("/skripte/pdf/{batch_id}")
async def skripte_pdf_page(batch_id: int):
    return FileResponse("frontend/skripte_pdf.html")

@app.get("/api/skripte/kunden")
async def api_skripte_kunden(request: Request):
    user = _require(request, "scripts.view")
    alle = scripts_tools.kunden_liste()
    ids = auth.get_accessible_customer_ids(user["id"], None)
    if ids is None:
        return alle
    return [k for k in alle if k["id"] in ids]

@app.get("/api/skripte/kunden/{kid}")
async def api_skripte_kunde(kid: int, request: Request):
    _require(request, "scripts.view")
    _check_customer_access(request, kid)
    k = scripts_tools.kunde_detail(kid)
    if not k:
        raise HTTPException(404, "Nicht gefunden")
    batches = scripts_tools.batches_fuer_kunde(kid)
    for b in batches:
        b["skripte"] = scripts_tools.skripte_fuer_batch(b["id"])
    k["batches"] = batches
    return k

@app.post("/api/skripte/kunden")
async def api_skripte_kunde_neu(request: Request, data: dict):
    _require(request, "scripts.create")
    kid = scripts_tools.kunde_erstellen(data)
    return {"id": kid}

@app.put("/api/skripte/kunden/{kid}")
async def api_skripte_kunde_update(kid: int, request: Request, data: dict):
    _require(request, "scripts.edit")
    _check_customer_access(request, kid)
    scripts_tools.kunde_aktualisieren(kid, data)
    return {"ok": True}

@app.delete("/api/skripte/kunden/{kid}")
async def api_skripte_kunde_loeschen(kid: int, request: Request):
    _require(request, "scripts.delete")
    scripts_tools.kunde_loeschen(kid)
    return {"ok": True}

@app.get("/api/skripte/batch/{batch_id}")
async def api_skripte_batch(batch_id: int, request: Request):
    _require(request, "scripts.view")
    b = scripts_tools.batch_mit_skripten(batch_id)
    if not b:
        raise HTTPException(404, "Nicht gefunden")
    return b

@app.delete("/api/skripte/batch/{batch_id}")
async def api_skripte_batch_loeschen(batch_id: int, request: Request):
    _require(request, "scripts.delete")
    scripts_tools.batch_loeschen(batch_id)
    return {"ok": True}


# ── Canva: OAuth ────────────────────────────────────────────────────────────

_canva_oauth_pending: dict = {}  # state -> code_verifier

@app.get("/api/canva/status")
async def api_canva_status():
    return {
        "configured": bool(CANVA_CLIENT_ID and CANVA_CLIENT_SECRET),
        "connected": canva.is_connected(),
    }

@app.get("/canva/connect")
async def canva_connect():
    if not (CANVA_CLIENT_ID and CANVA_CLIENT_SECRET):
        return JSONResponse({"detail": "canva_client_id/canva_client_secret fehlen in config.json"}, status_code=400)
    url, verifier, state = canva.build_authorize_url(CANVA_CLIENT_ID, CANVA_REDIRECT_URI)
    _canva_oauth_pending[state] = verifier
    return RedirectResponse(url)

@app.get("/canva/callback")
async def canva_callback(code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(f"/skripte?canva_error={error}")
    verifier = _canva_oauth_pending.pop(state, None)
    if not verifier:
        return RedirectResponse("/skripte?canva_error=invalid_state")
    try:
        await canva.exchange_code(CANVA_CLIENT_ID, CANVA_CLIENT_SECRET, CANVA_REDIRECT_URI, code, verifier)
    except canva.CanvaError as e:
        return RedirectResponse(f"/skripte?canva_error={e}")
    return RedirectResponse("/skripte?canva_connected=1")

@app.get("/api/canva/brand-templates")
async def api_canva_brand_templates():
    try:
        return await canva.list_brand_templates(CANVA_CLIENT_ID, CANVA_CLIENT_SECRET)
    except canva.CanvaError as e:
        return JSONResponse({"detail": str(e)}, status_code=400)


# ── Canva: pro Kunde konfigurieren + generieren ──────────────────────────────

@app.put("/api/skripte/kunden/{kid}/canva-config")
async def api_canva_config_setzen(kid: int, data: dict):
    if not scripts_tools.kunde_detail(kid):
        raise HTTPException(404, "Kunde nicht gefunden")
    medien_pfad = str(data.get("medien_pfad", "")).strip()
    if medien_pfad:
        os.makedirs(medien_pfad, exist_ok=True)
    scripts_tools.canva_config_setzen(
        kid,
        str(data.get("brand_template_id", "")).strip(),
        medien_pfad,
    )
    return {"ok": True}

@app.get("/api/skripte/kunden/{kid}/canva-posts")
async def api_canva_posts(kid: int):
    return scripts_tools.canva_posts_fuer_kunde(kid)

@app.post("/api/skripte/kunden/{kid}/canva-run")
async def api_canva_run(kid: int):
    # Laeuft als eigener Subprozess: der Hauptserver haelt bereits eine
    # eigene Playwright-Browserinstanz (browser_tools.py) fuer die
    # Sprachsteuerung, eine zweite im selben Prozess blockiert/haengt.
    script = os.path.join(os.path.dirname(__file__), "scripts", "weekly_canva_posts.py")
    proc = await asyncio.create_subprocess_exec(
        "/usr/bin/python3", script, "--kid", str(kid),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    if proc.returncode != 0:
        return JSONResponse({"detail": stdout.decode(errors="replace")[-800:]}, status_code=500)
    return scripts_tools.canva_posts_fuer_kunde(kid)

@app.get("/api/canva-posts/{post_id}/image")
async def api_canva_post_image(post_id: int):
    post = scripts_tools.canva_post_detail(post_id)
    if not post or not post.get("image_path") or not os.path.exists(post["image_path"]):
        raise HTTPException(404, "Bild nicht gefunden")
    return FileResponse(post["image_path"])

@app.get("/api/canva-posts/{post_id}/download")
async def api_canva_post_download(post_id: int):
    post = scripts_tools.canva_post_detail(post_id)
    if not post or not post.get("image_path") or not os.path.exists(post["image_path"]):
        raise HTTPException(404, "Bild nicht gefunden")
    return FileResponse(post["image_path"], filename=os.path.basename(post["image_path"]), media_type="image/png")

@app.post("/api/skripte/generieren")
async def api_skripte_generieren(data: dict):
    """Generiert 4 Reel-Skripte für einen Kunden und Monat."""
    if "kunden_id" not in data or "monat" not in data:
        raise HTTPException(400, "kunden_id und monat erforderlich")
    try:
        kid = int(data["kunden_id"])
    except (ValueError, TypeError):
        raise HTTPException(400, "kunden_id muss eine Zahl sein")
    monat  = str(data["monat"]).strip()
    themen = str(data.get("themen", "")).strip()
    try:
        if len(monat) != 7 or monat[4] != '-':
            raise ValueError()
        mon_num = int(monat[5:7])
        if not 1 <= mon_num <= 12:
            raise ValueError()
    except ValueError:
        raise HTTPException(400, "monat muss im Format YYYY-MM sein (z.B. 2026-07)")

    kunde = scripts_tools.kunde_detail(kid)
    if not kunde:
        raise HTTPException(404, "Kunde nicht gefunden")

    # Prüfen ob für diesen Monat schon Skripte existieren
    if scripts_tools.monat_hat_batch(kid, monat):
        raise HTTPException(409, f"Für {monat} existieren bereits Skripte für diesen Kunden.")

    # Alle bisherigen Themen laden (Wiederholungsschutz)
    bisherige_themen = scripts_tools.alle_themen_fuer_kunde(kid)
    themen_liste = "\n".join(f"- {t['titel']} ({t['erstellt_am'][:7]})"
                              for t in bisherige_themen) if bisherige_themen else "Noch keine bisherigen Skripte."

    # Erweiterter Wiederholungsschutz: Hooks, CTAs, Strukturen, Einstiegswörter analysieren
    wiederholung = scripts_tools.wiederholungsschutz_daten(kid, letzte_n_batches=4)
    hooks_liste = "\n".join(f'  • "{h}"' for h in wiederholung["hooks"]) if wiederholung["hooks"] else "  Noch keine."
    ctas_liste = "\n".join(f'  • "{c}"' for c in wiederholung["ctas"]) if wiederholung["ctas"] else "  Noch keine."
    strukturen_liste = "\n".join(f"  • {s}" for s in wiederholung["strukturen"]) if wiederholung["strukturen"] else "  Noch keine."
    einstiege_liste = ", ".join(wiederholung["einstiegswoerter"]) if wiederholung["einstiegswoerter"] else "Noch keine."

    # Monat auf Deutsch
    from datetime import datetime as dt
    monate_de = ["","Januar","Februar","März","April","Mai","Juni",
                  "Juli","August","September","Oktober","November","Dezember"]
    jahr, mon = monat.split("-")
    monat_de = f"{monate_de[int(mon)]} {jahr}"

    anzahl = kunde.get("skripte_pro_monat", 4)

    if themen:
        themen_block = (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "KUNDENWÜNSCHE — DIESE THEMEN SIND PFLICHT:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Der Auftraggeber hat folgende Themen/Stichwörter vorgegeben. Entwickle die {anzahl} Skripte\n"
            "gezielt aus diesen Vorgaben. Interpretiere sie kreativ, bleibe inhaltlich präzise:\n\n"
            f"{themen}\n\n"
            f"Verteile die Themen sinnvoll auf die {anzahl} Skripte.\n"
            "Falls mehr Themen als Skripte: wähle die stärksten aus.\n"
            "Falls weniger Themen als Skripte: ergänze mit thematisch passenden Ideen.\n"
        )
    else:
        themen_block = ""

    # Website-Kontext einbauen falls vorhanden
    website_block = ""
    if kunde.get("website"):
        website_block = (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "FAKTISCHE GRUNDLAGE:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Website: {kunde['website']}\n"
            "Verwende NUR Fakten, die durch das Kundenprofil abgedeckt sind.\n"
            "Erfinde NIEMALS Leistungen, Preise, Zertifikate, Standorte oder Eigenschaften.\n"
            "Wenn eine Aussage nicht durch das Profil belegt ist, formuliere sie allgemein.\n"
        )

    prompt = f"""Du bist Creative Director und Senior Copywriter bei OK Media Consulting.

Deine Aufgabe: {anzahl} professionelle Reel-Skripte für {kunde['name']} ({monat_de}) erstellen.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KUNDENPROFIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name: {kunde['name']}
Branche: {kunde['branche']}
Standort: {kunde['standort']}
Leistungen: {kunde['leistungen']}
Zielgruppe: {kunde['zielgruppe']}
Unternehmensziele: {kunde['ziele']}
Contentstrategie: {kunde['contentstrategie']}
Besonderheiten: {kunde['besonderheiten']}
Tonalität: {kunde['tonalitaet']}
{website_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
BISHERIGE INHALTE — STRIKTE DIFFERENZIERUNG ERFORDERLICH
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bereits behandelte Themen/Titel (keines davon wiederholen):
{themen_liste}

Zuletzt verwendete Hooks (NICHT mit denselben Wörtern beginnen):
{hooks_liste}

Zuletzt verwendete Einstiegswörter/-phrasen (vollständig vermeiden):
{einstiege_liste}

Zuletzt verwendete CTAs (variieren):
{ctas_liste}

Zuletzt verwendete Strukturen (andere wählen):
{strukturen_liste}
{themen_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STRUKTUR — EIGENSTÄNDIGE ENTSCHEIDUNG PFLICHT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Du entscheidest für JEDES Skript selbst, welcher dramaturgische Aufbau am stärksten wirkt.
Es gibt KEINE Standardstruktur. Die Entscheidung basiert auf Thema, Zielgruppe und Wirkungsabsicht.

Mögliche Ansätze (NUR als Denkimpuls — keine Vorlage):
Überraschende These → Beleg | Konkretes Alltagsbeispiel → Erkenntnis | Mythos → Realität |
Direkte Ansprache → Lösung | Emotionaler Moment → Einordnung | Expertenmeinung → Anwendung |
Fehler → Konsequenz → Weg heraus | Vergleich zweier Welten | Frage die hängen bleibt → Antwort |
Vorher-Nachher-Kontrast | Kontroverse These → differenzierte Erklärung | Storytelling-Einstieg |
Sachlicher Faktenaufbau | Vertrauensaufbau durch Expertise | Einwandbehandlung

JEDES der {anzahl} Skripte muss eine andere Struktur haben.
Benenne die gewählte Struktur im STRUKTUR-Feld des Outputs.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUALITÄTSSTANDARD — Orientiere dich an diesen Beispielen:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{scripts_tools.QUALITAETSBEISPIELE}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SPRACHLICHE QUALITÄTSREGELN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Kurze Sätze — maximal 10 Wörter, viele Zeilenumbrüche
✓ Natürlich gesprochen — muss sich für die Kamera gut anfühlen
✓ 30–60 Sekunden Sprechzeit (ca. 80–150 Wörter)
✓ Jeder Satz muss einen konkreten Mehrwert liefern
✓ Hook: erster Satz ist das Einzige, das zählt — er entscheidet ob jemand bleibt
✓ CTA: konkret, ohne Druck, passend zur Zielgruppe
✓ Sprache: so wie ein erfahrener Copywriter für diesen Kunden schreiben würde — NICHT generisch

VERBOTEN — folgende Phrasen und Muster dürfen NICHT verwendet werden:
✗ "Viele wissen nicht…" / "Die meisten wissen nicht…"
✗ "Hast du dich schon mal gefragt…"
✗ "In der heutigen Zeit…" / "Heutzutage…"
✗ "Es ist wichtig zu wissen…" / "Nicht zu vergessen…"
✗ "Genau deshalb…" (als Einleitung)
✗ "Das Beste daran…" / "Das Schönste ist…"
✗ "Melde dich jetzt…" / "Zögere nicht…"
✗ "Denn eines ist sicher…" / "Die Wahrheit ist…" (als Standardfloskel)
✗ Übertriebene Superlative ohne Substanz
✗ Phrasen die bei jedem beliebigen Unternehmen passen würden
✗ KI-typische Formulierungen oder Marketingsprache aus den 2010ern

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INTERNER QUALITÄTS-CHECK VOR DER AUSGABE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bevor du jeden Skriptentwurf ausgibst, prüfe intern:
1. Klingt der Hook wie von einem Menschen geschrieben — oder generisch?
2. Unterscheidet sich die Struktur von den bisherigen?
3. Beginnt kein Hook mit denselben Wörtern wie die zuletzt verwendeten?
4. Passt der CTA wirklich zu diesem Unternehmen und dieser Zielgruppe?
5. Gibt es einen einzigen Satz der als Floskel erkennbar ist? → streichen
6. Wäre dieses Skript als Reel wirklich sehenswert?
Wenn eine dieser Fragen mit Nein beantwortet wird: Skript intern überarbeiten, DANN ausgeben.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (exakt einhalten):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STRATEGIE: [2–3 Sätze: warum diese Themen für diesen Kunden jetzt, was ist die übergeordnete Botschaft]

SKRIPT_1
TITEL: [prägnanter Titel — nicht der Hook, sondern ein interner Arbeitstitel]
STRUKTUR: [Name der gewählten dramaturgischen Struktur, 3–5 Wörter]
HOOK: [Erster gesprochener Satz — keine Anführungszeichen]
SKRIPT:
[Vollständiger Text mit Zeilenumbrüchen nach jedem Satz/Sinnabschnitt]
CTA: [Aufruf — konkret, zum Unternehmen passend]
DREHHINWEIS: [Optional: kurzer Produktionshinweis]

SKRIPT_2
TITEL: [Titel]
STRUKTUR: [Struktur]
HOOK: [Hook]
SKRIPT:
[Text]
CTA: [CTA]
DREHHINWEIS: [Optional]

[So weiter für alle {anzahl} Skripte — jedes mit anderer Struktur und anderem Hook-Typ]"""

    try:
        response = await ai.messages.create(
            model="claude-sonnet-5",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}]
        )
    except anthropic.APIConnectionError:
        raise HTTPException(503, "Verbindung zu Claude nicht möglich — bitte Internetverbindung prüfen und erneut versuchen.")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Claude API-Limit erreicht — bitte kurz warten und erneut versuchen.")
    except anthropic.APIStatusError as _e:
        raise HTTPException(502, f"Claude API-Fehler: {_e.message}")
    raw = next((b.text for b in response.content if hasattr(b, "text")), "").strip()

    # Parsen
    strategie = ""
    if "STRATEGIE:" in raw:
        strat_end = raw.find("SKRIPT_1")
        if strat_end > 0:
            strategie = raw[raw.find("STRATEGIE:")+10:strat_end].strip()

    # Batch erstellen
    batch_id = scripts_tools.batch_erstellen(kid, monat, strategie)

    # Einzelne Skripte parsen
    import re as _re
    skript_blocks = _re.split(r'\nSKRIPT_\d+\n', raw)
    if skript_blocks and "SKRIPT_1" not in skript_blocks[0]:
        skript_blocks = skript_blocks[1:]  # ersten Block (Strategie) überspringen

    # Nochmal sauber splitten
    pattern = _re.compile(r'SKRIPT_(\d+)')
    parts = pattern.split(raw)
    skript_contents = []
    for i in range(1, len(parts), 2):
        if i+1 < len(parts):
            skript_contents.append(parts[i+1].strip())

    def extrahiere(block: str, feld: str, naechstes: str = None) -> str:
        if feld + ":" not in block:
            return ""
        start = block.find(feld + ":") + len(feld) + 1
        if naechstes and naechstes + ":" in block:
            end = block.find(naechstes + ":")
            return block[start:end].strip()
        return block[start:].strip()

    gespeicherte = []
    for i, block in enumerate(skript_contents[:anzahl]):
        # STRUKTUR-Feld vor HOOK extrahieren
        if "STRUKTUR:" in block and "HOOK:" in block:
            titel    = extrahiere(block, "TITEL", "STRUKTUR")
            struktur = extrahiere(block, "STRUKTUR", "HOOK")
        else:
            titel    = extrahiere(block, "TITEL", "HOOK")
            struktur = ""
        hook       = extrahiere(block, "HOOK", "SKRIPT")
        skript_txt = extrahiere(block, "SKRIPT", "CTA")
        cta        = extrahiere(block, "CTA", "DREHHINWEIS")
        dreh       = extrahiere(block, "DREHHINWEIS")

        sid = scripts_tools.skript_erstellen(
            batch_id, kid, i+1, titel, hook, skript_txt, cta, dreh, titel
        )
        # Struktur separat speichern (ALTER TABLE hat es hinzugefügt)
        if struktur:
            import sqlite3 as _sq
            try:
                with _sq.connect(scripts_tools.DB_PATH) as _c:
                    _c.execute("UPDATE skripte SET struktur=? WHERE id=?", (struktur, sid))
            except Exception:
                pass
        gespeicherte.append({
            "id": sid, "position": i+1, "titel": titel,
            "hook": hook, "skript": skript_txt, "cta": cta,
            "drehhinweis": dreh, "struktur": struktur
        })

    return {
        "id": batch_id,
        "batch_id": batch_id,
        "strategie": strategie,
        "skripte": gespeicherte,
        "monat": monat_de
    }


@app.post("/api/skripte/einzeln")
async def api_skript_einzeln(data: dict):
    """Generiert ein einzelnes Reel-Skript für ein bestimmtes Thema."""
    if "kunden_id" not in data or not data.get("thema", "").strip():
        raise HTTPException(400, "kunden_id und thema erforderlich")
    try:
        kid = int(data["kunden_id"])
    except (ValueError, TypeError):
        raise HTTPException(400, "kunden_id muss eine Zahl sein")

    thema = str(data["thema"]).strip()
    zusatzinfo = str(data.get("zusatzinfo", "")).strip()

    kunde = scripts_tools.kunde_detail(kid)
    if not kunde:
        raise HTTPException(404, "Kunde nicht gefunden")

    wiederholung = scripts_tools.wiederholungsschutz_daten(kid, letzte_n_batches=4)
    hooks_liste = "\n".join(f'  • "{h}"' for h in wiederholung["hooks"]) if wiederholung["hooks"] else "  Noch keine."
    einstiege_liste = ", ".join(wiederholung["einstiegswoerter"]) if wiederholung["einstiegswoerter"] else "Noch keine."
    ctas_liste = "\n".join(f'  • "{c}"' for c in wiederholung["ctas"]) if wiederholung["ctas"] else "  Noch keine."
    strukturen_liste = "\n".join(f"  • {s}" for s in wiederholung["strukturen"]) if wiederholung["strukturen"] else "  Noch keine."

    bisherige_themen = scripts_tools.alle_themen_fuer_kunde(kid)
    themen_liste = "\n".join(f"- {t['titel']}" for t in bisherige_themen[:20]) if bisherige_themen else "Noch keine."

    zusatz_block = ""
    if zusatzinfo:
        zusatz_block = (
            "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "ZUSÄTZLICHE INFORMATIONEN VOM AUFTRAGGEBER:\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"{zusatzinfo}\n"
            "Berücksichtige diese Infos konkret im Skript.\n"
        )

    website_block = ""
    if kunde.get("website"):
        website_block = f"\nWebsite: {kunde['website']} — verwende NUR verifizierbare Fakten aus dem Kundenprofil.\n"

    prompt = f"""Du bist Creative Director und Senior Copywriter bei OK Media Consulting.

Erstelle ein professionelles Social-Media-Reel-Skript für folgendes Thema:

THEMA: {thema}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KUNDENPROFIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Name: {kunde['name']}
Branche: {kunde['branche']}
Standort: {kunde['standort']}
Leistungen: {kunde['leistungen']}
Zielgruppe: {kunde['zielgruppe']}
Besonderheiten: {kunde['besonderheiten']}
Tonalität: {kunde['tonalitaet']}
{website_block}{zusatz_block}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DIFFERENZIERUNG — STRIKTE ANFORDERUNGEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Bereits behandelte Themen (keines ähnliches):
{themen_liste}

Zuletzt verwendete Hooks (NICHT ähnlich beginnen):
{hooks_liste}

Einstiegswörter/-phrasen die VERBOTEN sind:
{einstiege_liste}

Zuletzt verwendete CTAs (variieren):
{ctas_liste}

Bereits verwendete Strukturen (andere wählen):
{strukturen_liste}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANFORDERUNGEN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Entscheide selbst welche dramaturgische Struktur am stärksten für dieses Thema wirkt
• Kurze Sätze (max. 10 Wörter), Zeilenumbrüche nach jedem Satz
• 30–60 Sekunden Sprechzeit (ca. 80–150 Wörter)
• Hook: hält die Aufmerksamkeit in den ersten 3 Sekunden
• Kein Satz der wie generische KI-Ausgabe klingt
• CTA passend zum Unternehmen, ohne Druck

VERBOTEN: "Viele wissen nicht…", "Hast du dich schon mal gefragt…", "In der heutigen Zeit…",
"Genau deshalb…", "Das Beste daran…", "Melde dich jetzt…", "Zögere nicht…"

Prüfe intern bevor du ausgibst: Klingt jeder Satz menschlich? Gibt es eine Floskel? → streichen.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (exakt so):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TITEL: [Arbeitstitel]
STRUKTUR: [Name der gewählten Struktur, 3–5 Wörter]
HOOK: [Erster gesprochener Satz]
SKRIPT:
[Volltext mit Zeilenumbrüchen]
CTA: [Konkreter Aufruf]
DREHHINWEIS: [Optional]"""

    try:
        response = await ai.messages.create(
            model="claude-sonnet-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
    except anthropic.APIConnectionError:
        raise HTTPException(503, "Verbindung zu Claude nicht möglich — bitte Internetverbindung prüfen.")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Claude API-Limit erreicht — bitte kurz warten.")
    except anthropic.APIStatusError as _e:
        raise HTTPException(502, f"Claude API-Fehler: {_e.message}")

    raw = next((b.text for b in response.content if hasattr(b, "text")), "").strip()

    def _extr(text: str, feld: str, naechstes: str = None) -> str:
        if feld + ":" not in text:
            return ""
        start = text.find(feld + ":") + len(feld) + 1
        if naechstes and naechstes + ":" in text:
            end = text.find(naechstes + ":")
            return text[start:end].strip()
        return text[start:].strip()

    if "STRUKTUR:" in raw and "HOOK:" in raw:
        titel    = _extr(raw, "TITEL", "STRUKTUR")
        struktur = _extr(raw, "STRUKTUR", "HOOK")
    else:
        titel    = _extr(raw, "TITEL", "HOOK")
        struktur = ""
    hook       = _extr(raw, "HOOK", "SKRIPT")
    skript_txt = _extr(raw, "SKRIPT", "CTA")
    cta        = _extr(raw, "CTA", "DREHHINWEIS")
    dreh       = _extr(raw, "DREHHINWEIS")

    sid = scripts_tools.skript_einzeln_speichern(
        kid, thema, titel, hook, skript_txt, cta, dreh, struktur
    )

    return {
        "id": sid,
        "thema": thema,
        "titel": titel,
        "struktur": struktur,
        "hook": hook,
        "skript": skript_txt,
        "cta": cta,
        "drehhinweis": dreh
    }


# ── Instagram ─────────────────────────────────────────────────────────────────

@app.get("/api/instagram/kunden/{kid}")
async def api_instagram_liste(kid: int, request: Request):
    _require(request, "scripts.view")
    _check_customer_access(request, kid)
    posts = scripts_tools.instagram_posts_fuer_kunde(kid)
    return {"posts": posts}


@app.delete("/api/instagram/{post_id}")
async def api_instagram_loeschen(post_id: int, request: Request):
    _require(request, "scripts.delete")
    scripts_tools.instagram_post_loeschen(post_id)
    return {"ok": True}


@app.post("/api/instagram/generieren")
async def api_instagram_generieren(request: Request, data: dict):
    """Generiert einen professionellen Instagram-Beitrag oder Carousel."""
    _require(request, "scripts.create")
    if "kunden_id" not in data or not data.get("thema", "").strip():
        raise HTTPException(400, "kunden_id und thema erforderlich")
    try:
        kid = int(data["kunden_id"])
    except (ValueError, TypeError):
        raise HTTPException(400, "kunden_id muss eine Zahl sein")

    thema      = str(data["thema"]).strip()
    format_hint = str(data.get("format", "auto")).strip().lower()

    kunde = scripts_tools.kunde_detail(kid)
    if not kunde:
        raise HTTPException(404, "Kunde nicht gefunden")

    branding = scripts_tools.branding_fuer_kunde(kid)
    branding_block = ""
    if branding:
        parts = []
        if branding.get("primary_color"):
            parts.append(f"Primärfarbe: {branding['primary_color']}")
        if branding.get("design_stil"):
            parts.append(f"Designstil: {branding['design_stil']}")
        if branding.get("bildsprache"):
            parts.append(f"Bildsprache: {branding['bildsprache']}")
        if parts:
            branding_block = "Corporate Design: " + " | ".join(parts) + "\n"

    bisherige_ig = scripts_tools.instagram_posts_fuer_kunde(kid, limit=10)
    ig_themen = "\n".join(f"- {p['thema']} ({p['erstellt_am'][:10]})" for p in bisherige_ig) if bisherige_ig else "Noch keine."

    format_instruction = ""
    if format_hint == "auto":
        format_instruction = (
            "Entscheide selbst welches Format für dieses Thema am stärksten wirkt:\n"
            "Einzelner Feed-Post | Informationsgrafik | Angebots-Post | Experten-Post | "
            "Carousel | Unternehmens-Post | Recruiting-Post | Branding-Post | Event-Post\n"
            "Begründe deine Wahl kurz im FORMAT-Feld."
        )
    else:
        format_instruction = f"Erstelle einen {format_hint}-Post."

    prompt = f"""Du bist Creative Director und Social-Media-Stratege bei OK Media Consulting.

Erstelle einen professionellen Instagram-Beitrag für {kunde['name']}.

THEMA: {thema}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KUNDENPROFIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Branche: {kunde['branche']}
Zielgruppe: {kunde['zielgruppe']}
Leistungen: {kunde['leistungen']}
Tonalität: {kunde['tonalitaet']}
Besonderheiten: {kunde['besonderheiten']}
{branding_block}
Bereits erstellte Instagram-Inhalte (nicht wiederholen):
{ig_themen}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMAT-ENTSCHEIDUNG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{format_instruction}

Für Carousel-Posts: 3–7 Slides. Slide 1 = starker Einstieg/Headline. Letzte Slide = CTA.
Die Struktur der Slides soll inhaltlich sinnvoll aufgebaut sein, nicht nach Schema.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
QUALITÄTSREGELN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Headline jeder Slide: maximal 8 Wörter, neugierig machend
• Text je Slide: 1–3 kurze Sätze, prägnant
• Caption: professionell, zum Öffnen animierend, 3–6 Zeilen
• Hashtags: 8–15 relevante Tags (nicht generisch)
• Kein KI-Sprech, keine Floskeln, keine übertriebenen Superlative

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (exakt einhalten):
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FORMAT: [gewähltes Format + 1 Satz Begründung]

SLIDE_1
HEADLINE: [Hauptüberschrift]
TEXT: [Kurzer Begleittext, optional]
VISUAL: [Kurze Bildbeschreibung: was sollte auf dem Bild/der Grafik zu sehen sein]

SLIDE_2
HEADLINE: [...]
TEXT: [...]
VISUAL: [...]

[weitere Slides je nach Format]

CAPTION:
[Instagram-Begleittext für den Post]

HASHTAGS: [#tag1 #tag2 ...]"""

    try:
        response = await ai.messages.create(
            model="claude-sonnet-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )
    except anthropic.APIConnectionError:
        raise HTTPException(503, "Verbindung zu Claude nicht möglich — bitte Internetverbindung prüfen.")
    except anthropic.RateLimitError:
        raise HTTPException(429, "Claude API-Limit erreicht — bitte kurz warten.")
    except anthropic.APIStatusError as _ig_e:
        raise HTTPException(502, f"Claude API-Fehler: {_ig_e.message}")

    raw = next((b.text for b in response.content if hasattr(b, "text")), "").strip()

    # Format extrahieren
    format_zeile = ""
    if "FORMAT:" in raw:
        f_end = raw.find("\n", raw.find("FORMAT:"))
        format_zeile = raw[raw.find("FORMAT:")+7:f_end].strip() if f_end > 0 else ""

    # Slides parsen
    import re as _ig_re, json as _json
    slide_pattern = _ig_re.compile(r'SLIDE_(\d+)\s*\n(.*?)(?=SLIDE_\d+\s*\n|CAPTION:|$)', _ig_re.DOTALL)
    slides = []
    for m in slide_pattern.finditer(raw):
        block = m.group(2).strip()
        def _sg(field: str, nxt: str = None) -> str:
            if field + ":" not in block:
                return ""
            s = block.find(field + ":") + len(field) + 1
            if nxt and nxt + ":" in block:
                e = block.find(nxt + ":")
                return block[s:e].strip()
            return block[s:].strip().split("\n")[0].strip()
        slides.append({
            "nr": int(m.group(1)),
            "headline": _sg("HEADLINE", "TEXT"),
            "text": _sg("TEXT", "VISUAL"),
            "visual": _sg("VISUAL")
        })

    caption = ""
    if "CAPTION:" in raw:
        cap_start = raw.find("CAPTION:") + 8
        cap_end = raw.find("HASHTAGS:")
        caption = raw[cap_start:cap_end].strip() if cap_end > cap_start else raw[cap_start:].split("HASHTAGS:")[0].strip()

    hashtags = ""
    if "HASHTAGS:" in raw:
        hashtags = raw[raw.find("HASHTAGS:")+9:].strip().split("\n")[0].strip()

    slides_json = _json.dumps(slides, ensure_ascii=False)
    post_id = scripts_tools.instagram_post_speichern(kid, thema, format_zeile, slides_json, caption, hashtags)

    return {
        "id": post_id,
        "thema": thema,
        "format": format_zeile,
        "slides": slides,
        "caption": caption,
        "hashtags": hashtags
    }


# ── Branding ─────────────────────────────────────────────────────────────────

@app.get("/api/branding/{kid}")
async def api_branding_get(kid: int, request: Request):
    _require(request, "scripts.view")
    _check_customer_access(request, kid)
    return scripts_tools.branding_fuer_kunde(kid) or {}


@app.put("/api/branding/{kid}")
async def api_branding_set(kid: int, request: Request, data: dict):
    _require(request, "scripts.edit")
    _check_customer_access(request, kid)
    kunde = scripts_tools.kunde_detail(kid)
    if not kunde:
        raise HTTPException(404, "Kunde nicht gefunden")
    scripts_tools.branding_speichern(kid, data)
    return {"ok": True}


# ── Erweiterte Kunden-Update (website, produkte, social_media_ziele) ─────────

@app.put("/api/skripte/kunden/{kid}/profil")
async def api_kunde_profil_update(kid: int, request: Request, data: dict):
    _require(request, "scripts.edit")
    _check_customer_access(request, kid)
    """Aktualisiert das erweiterte Kundenprofil inkl. website-Feld."""
    erlaubte = {
        "name", "branche", "standort", "zielgruppe", "ziele", "leistungen",
        "tonalitaet", "postingrhythmus", "skripte_pro_monat", "besonderheiten",
        "ansprechpartner", "contentstrategie", "website", "produkte", "social_media_ziele"
    }
    felder = {k: v for k, v in data.items() if k in erlaubte}
    if not felder:
        raise HTTPException(400, "Keine gültigen Felder")
    import sqlite3 as _sq2
    sql = ", ".join(f"{k}=?" for k in felder)
    with _sq2.connect(scripts_tools.DB_PATH) as _c:
        _c.execute(f"UPDATE kunden SET {sql} WHERE id=?", (*felder.values(), kid))
    return {"ok": True}


@app.post("/api/skripte/{skript_id}/beitrag-story")
async def api_beitrag_story(skript_id: int):
    """Generiert Beitragstext + Story-Titel für ein bestehendes Skript."""
    skript = scripts_tools.skript_detail(skript_id)
    if not skript:
        raise HTTPException(404, "Skript nicht gefunden")
    kunde = scripts_tools.kunde_detail(skript["kunden_id"])
    if not kunde:
        raise HTTPException(404, "Kunde nicht gefunden")

    prompt = f"""Du bist der Creative Director von OK Media Consulting.

Erstelle für das folgende Reel-Skript:
1. Einen professionellen Beitragstext (Caption für Instagram/Facebook)
2. Einen kurzen Story-Titel

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
KUNDENPROFIL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kunde: {kunde['name']}
Branche: {kunde['branche']}
Standort: {kunde['standort']}
Zielgruppe: {kunde['zielgruppe']}
Unternehmensziele: {kunde['ziele']}
Leistungen: {kunde['leistungen']}
Tonalität: {kunde['tonalitaet']}
Contentstrategie: {kunde.get('contentstrategie', '')}
Besonderheiten: {kunde.get('besonderheiten', '')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
REEL-SKRIPT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Titel: {skript['titel']}
Hook: {skript['hook']}
Skript:
{skript['skript']}
CTA: {skript.get('cta', '')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANFORDERUNGEN BEITRAGSTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Individuell zum Reel und Unternehmen
- Professionell, modern, leicht lesbar
- 8-10 Sätze — ausführlich aber strukturiert
- Nicht verkäuferisch — vertrauensaufbauend
- Passend zur Zielgruppe und Markenidentität
- Kein Copy-Paste aus dem Skript
- Eigene, ergänzende Perspektive
- Optional 2-3 passende Hashtags am Ende

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ANFORDERUNGEN STORY-TITEL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- Kurz (max. 4-6 Wörter)
- Aufmerksamkeitsstark und modern
- Zum Reel und Unternehmen passend
- Leicht verständlich

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT (exakt so):
BEITRAG:
[Beitragstext hier]

STORY:
[Story-Titel hier]"""

    response = await ai.messages.create(
        model="claude-sonnet-5",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = next((b.text for b in response.content if hasattr(b, "text")), "").strip()

    beitrag_text = ""
    story_titel = ""

    if "BEITRAG:" in raw and "STORY:" in raw:
        parts = raw.split("STORY:", 1)
        beitrag_text = parts[0].replace("BEITRAG:", "").strip()
        story_titel = parts[1].strip()
    elif "BEITRAG:" in raw:
        beitrag_text = raw.replace("BEITRAG:", "").strip()
    else:
        beitrag_text = raw

    scripts_tools.skript_beitrag_speichern(skript_id, beitrag_text, story_titel)

    return {"beitrag_text": beitrag_text, "story_titel": story_titel}


@app.post("/api/crm/email-entwurf")
async def api_email_entwurf(data: dict):
    """Generiert einen E-Mail-Entwurf basierend auf Kundendaten und Kontext."""
    kid = data.get("kunden_id")
    kontext = data.get("kontext", "")
    kunde = crm_tools.kunde_detail(kid)
    if not kunde:
        return {"error": "Kunde nicht gefunden"}

    # Kundendaten zusammenfassen
    letzter_log = kunde["log"][0] if kunde.get("log") else None
    offene_angebote = [a for a in crm_tools.angebote_fuer_kunde(kid) if a["status"] in ("Entwurf","Gesendet")]

    kontext_block = f"""Kunde: {kunde['firma']}
Ansprechpartner: {kunde.get('ansprechpartner') or '—'}
E-Mail: {kunde.get('email') or '—'}
Branche: {kunde.get('branche') or '—'}
Kategorie: {kunde.get('kategorie')}
{f"Letzter Kontakt: {letzter_log['art']} am {letzter_log['datum'][:10]} — {letzter_log['zusammenfassung']}" if letzter_log else "Noch kein Kontakt geloggt"}
{f"Offene Angebote: {', '.join(a['titel'] + ' (€' + str(int(a['betrag'])) + ')' for a in offene_angebote)}" if offene_angebote else ""}
Anlass/Kontext: {kontext}"""

    prompt = f"""Schreibe eine kurze, professionelle E-Mail auf Deutsch für OK Media Consulting.

{kontext_block}

Anforderungen:
- Absender: Okan Koska, OK Media Consulting
- Maximal 5-6 Sätze, klar und freundlich
- Kein "Sehr geehrte/r" — nutze den Vornamen wenn bekannt, sonst "Guten Tag"
- Betreff und E-Mail-Text getrennt ausgeben
- Format: BETREFF: [betreff]\\nINHALT: [inhalt]"""

    response = await ai.messages.create(
        model="claude-sonnet-5",
        max_tokens=600,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = next((b.text for b in response.content if hasattr(b, "text")), "").strip()

    # Betreff und Inhalt extrahieren
    betreff = ""
    inhalt = raw
    if "BETREFF:" in raw:
        parts = raw.split("INHALT:", 1)
        betreff = parts[0].replace("BETREFF:", "").strip()
        inhalt = parts[1].strip() if len(parts) > 1 else raw

    return {
        "betreff": betreff,
        "inhalt": inhalt,
        "empfaenger": kunde.get("email", ""),
        "empfaenger_name": kunde.get("ansprechpartner", kunde["firma"])
    }


@app.get("/denkt-mit")
async def denkt_mit_page():
    return FileResponse("frontend/denkt_mit.html")


@app.post("/api/jarvis/denkt-mit")
async def api_denkt_mit():
    """Analysiert alle Programmdaten und gibt Jarvis-Empfehlungen zurück."""
    from datetime import date as _date, timedelta

    heute = _date.today().isoformat()
    naechste_7 = (_date.today() + timedelta(days=7)).isoformat()

    # ── Daten sammeln ────────────────────────────────────────────────
    crm_kunden   = crm_tools.kunden_liste()
    crm_stats    = crm_tools.stats()
    fups_heute   = crm_tools.followups_heute()
    angebote_stats = crm_tools.angebote_stats()

    # Follow-ups nächste 7 Tage
    with crm_tools._con() as con:
        fups_woche = [dict(r) for r in con.execute("""
            SELECT f.*, k.firma FROM follow_ups f
            JOIN kunden k ON k.id = f.kunden_id
            WHERE f.erledigt=0 AND f.faellig_am <= ? AND f.faellig_am > ?
            ORDER BY f.faellig_am
        """, (naechste_7, heute)).fetchall()]

    # Kunden ohne Kontakt seit > 14 Tagen
    kunden_ohne_kontakt = []
    for k in crm_kunden:
        letzter = k.get("aktualisiert_am", "")[:10]
        if letzter:
            try:
                delta = (_date.today() - _date.fromisoformat(letzter)).days
                if delta > 14 and k.get("kategorie") == "Kunde":
                    kunden_ohne_kontakt.append({"firma": k["firma"], "tage": delta, "id": k["id"]})
            except Exception:
                pass
    kunden_ohne_kontakt.sort(key=lambda x: x["tage"], reverse=True)

    # Offene Angebote
    offene_angebote = []
    for k in crm_kunden:
        angebote = crm_tools.angebote_fuer_kunde(k["id"])
        for a in angebote:
            if a["status"] in ("Entwurf", "Gesendet"):
                offene_angebote.append({
                    "firma": k["firma"], "titel": a["titel"],
                    "betrag": a["betrag"], "status": a["status"],
                    "erstellt": a["erstellt_am"][:10]
                })

    # Leads ohne Aktivität (keine Logs, nie aktualisiert)
    leads_kalt = []
    for k in crm_kunden:
        if k.get("kategorie") == "Lead":
            letzter = k.get("aktualisiert_am", "")[:10]
            try:
                delta = (_date.today() - _date.fromisoformat(letzter)).days if letzter else 99
                if delta > 7:
                    leads_kalt.append({"firma": k["firma"], "tage": delta, "id": k["id"]})
            except Exception:
                pass
    leads_kalt.sort(key=lambda x: x["tage"], reverse=True)

    # Skripte
    skripte_kunden = scripts_tools.kunden_liste()
    skripte_ohne_beitrag = []
    for sk in skripte_kunden:
        batches = scripts_tools.batches_fuer_kunde(sk["id"])
        for b in batches:
            skripte = scripts_tools.skripte_fuer_batch(b["id"])
            for s in skripte:
                if not s.get("beitrag_text"):
                    skripte_ohne_beitrag.append({
                        "kunde": sk["name"], "titel": s["titel"],
                        "monat": b["monat"], "skript_id": s["id"]
                    })

    # Recherchen (letzte 5)
    recherchen = research_tools.recherchen_liste()[:5]

    # Gedächtnis
    mem_data = memory.load()
    offene_aufgaben = [a for a in mem_data.get("aufgaben", []) if not a.get("erledigt")]
    notizen = mem_data.get("notizen", [])[:3]

    # ── Prompt bauen ────────────────────────────────────────────────
    prompt = f"""Du bist Jarvis — persönlicher KI-Assistent von Okan Koska, OK Media Consulting.

Analysiere die folgenden Programmdaten und erstelle präzise, geschäftlich relevante Empfehlungen.
Keine allgemeinen Phrasen. Nur konkrete Handlungsempfehlungen basierend auf den echten Daten.
Kurze Sätze. Direkte Sprache. Maximale Relevanz für das Tagesgeschäft.

=== AKTUELLE DATEN ===

CRM-Übersicht:
- Gesamt: {crm_stats['gesamt']} Kontakte ({crm_stats['kunden']} Kunden, {crm_stats['leads']} Leads)
- Follow-ups heute fällig: {len(fups_heute)}
- Follow-ups nächste 7 Tage: {len(fups_woche)}

Follow-ups heute:
{chr(10).join(f"- {f['firma']}: {f['titel']}" for f in fups_heute[:5]) if fups_heute else "- Keine"}

Kunden ohne Kontakt seit >14 Tagen:
{chr(10).join(f"- {k['firma']}: {k['tage']} Tage kein Kontakt" for k in kunden_ohne_kontakt[:5]) if kunden_ohne_kontakt else "- Alle Kunden aktuell betreut"}

Offene Angebote:
{chr(10).join(f"- {a['firma']}: {a['titel']} ({a['status']}, €{int(a['betrag'])}, seit {a['erstellt']})" for a in offene_angebote[:5]) if offene_angebote else "- Keine offenen Angebote"}

Kalte Leads (>7 Tage keine Aktivität):
{chr(10).join(f"- {l['firma']}: {l['tage']} Tage inaktiv" for l in leads_kalt[:5]) if leads_kalt else "- Keine"}

Angebots-Volumen:
{chr(10).join(f"- {status}: {d['anzahl']} Angebote, €{int(d['volumen'])} Volumen" for status, d in angebote_stats.items() if status != 'gesamt_volumen' and isinstance(d, dict))}
- Gesamt: €{int(angebote_stats.get('gesamt_volumen', 0))}

Skripte ohne Beitrag & Story ({len(skripte_ohne_beitrag)} Skripte):
{chr(10).join(f"- {s['kunde']}: {s['titel']} ({s['monat']})" for s in skripte_ohne_beitrag[:5]) if skripte_ohne_beitrag else "- Alle Skripte vollständig"}

Letzte Recherchen:
{chr(10).join(f"- {r['titel']} ({r['erstellt_am'][:10]})" for r in recherchen) if recherchen else "- Keine Recherchen vorhanden"}

Offene Aufgaben aus Gedächtnis:
{chr(10).join(f"- {a['text']}" for a in offene_aufgaben[:5]) if offene_aufgaben else "- Keine"}

Letzte Notizen:
{chr(10).join(f"- {n['text']}" for n in notizen) if notizen else "- Keine"}

=== AUSGABE ===

Erstelle exakt dieses Format — jeder Bereich genau 3-5 Punkte, kein Punkt mehr als 15 Wörter:

EMPFEHLUNG:
[Die eine wichtigste Handlung die heute zählt — 1 konkreter Satz]

CHANCEN:
- [Chance 1]
- [Chance 2]
- [Chance 3]

RISIKEN:
- [Risiko 1]
- [Risiko 2]
- [Risiko 3]

HANDLUNGSBEDARF:
- [Kundenname]: [konkreter Handlungsbedarf]
- [Kundenname]: [konkreter Handlungsbedarf]
- [Kundenname]: [konkreter Handlungsbedarf]

NAECHSTER_SCHRITT:
[Ein einziger konkreter nächster Schritt — heute umsetzbar]"""

    response = await ai.messages.create(
        model="claude-sonnet-5",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = next((b.text for b in response.content if hasattr(b, "text")), "").strip()

    def _parse_section(text: str, key: str, next_key: str = None) -> str:
        if key + ":" not in text:
            return ""
        start = text.find(key + ":") + len(key) + 1
        if next_key and next_key + ":" in text:
            end = text.find(next_key + ":")
            return text[start:end].strip()
        return text[start:].strip()

    empfehlung    = _parse_section(raw, "EMPFEHLUNG", "CHANCEN")
    chancen       = _parse_section(raw, "CHANCEN", "RISIKEN")
    risiken       = _parse_section(raw, "RISIKEN", "HANDLUNGSBEDARF")
    handlungsbedarf = _parse_section(raw, "HANDLUNGSBEDARF", "NAECHSTER_SCHRITT")
    naechster     = _parse_section(raw, "NAECHSTER_SCHRITT")

    def _bullets(text: str) -> list:
        lines = [l.strip().lstrip("- •*").strip() for l in text.splitlines() if l.strip().startswith("-")]
        return [l for l in lines if l]

    return {
        "empfehlung": empfehlung,
        "chancen": _bullets(chancen),
        "risiken": _bullets(risiken),
        "handlungsbedarf": _bullets(handlungsbedarf),
        "naechster_schritt": naechster,
        "meta": {
            "fups_heute": len(fups_heute),
            "fups_woche": len(fups_woche),
            "kunden_ohne_kontakt": len(kunden_ohne_kontakt),
            "offene_angebote": len(offene_angebote),
            "leads_kalt": len(leads_kalt),
            "skripte_ohne_beitrag": len(skripte_ohne_beitrag),
        }
    }


_heute_cache: dict = {"date": None, "data": None}

@app.get("/api/heute-wichtig")
async def api_heute_wichtig(request: Request):
    from fastapi.responses import JSONResponse
    import datetime as _dt
    today = _dt.date.today().isoformat()
    if _heute_cache["date"] == today and _heute_cache["data"]:
        return JSONResponse(_heute_cache["data"])

    prompt = f"""Du bist Jarvis, KI-Assistent von OK Media Consulting (Social-Media-Agentur, Deutschland).
Erstelle kompakte, praxisnahe Brancheninformationen für heute ({today}).

Antworte NUR mit validem JSON, kein Text davor/danach:
{{
  "karten": [
    {{"titel": "Social Media", "icon": "📱", "inhalt": "1-2 Sätze zu einem aktuellen Social-Media-Trend oder Algorithmus-Tipp", "tag": "TREND"}},
    {{"titel": "Local SEO", "icon": "📍", "inhalt": "1-2 Sätze zu Google Business / Local SEO für KMU", "tag": "LOKAL"}},
    {{"titel": "Video-Content", "icon": "🎬", "inhalt": "1-2 Sätze zu Reels, TikTok oder Kurzvideos Tipps", "tag": "TIPP"}},
    {{"titel": "Strategie", "icon": "🎯", "inhalt": "1-2 Sätze zur Contentstrategie oder Kundengewinnung", "tag": "STRATEGIE"}}
  ],
  "empfehlung": "Eine konkrete Handlungsempfehlung für Okan und OK Media heute. Maximal 1–2 Sätze, direkt und umsetzbar."
}}"""

    try:
        resp = await ai.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = resp.content[0].text.strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
            _heute_cache["date"] = today
            _heute_cache["data"] = data
            return JSONResponse(data)
    except Exception:
        pass

    fallback = {
        "karten": [
            {"titel": "Social Media", "icon": "📱",
             "inhalt": "Instagram Reels erzielen 22% mehr Reichweite als statische Posts. Authentische, kurze Videos priorisieren.",
             "tag": "TREND"},
            {"titel": "Local SEO", "icon": "📍",
             "inhalt": "Google Business Profil täglich aktuell halten. Beiträge erhöhen lokale Sichtbarkeit um bis zu 35%.",
             "tag": "LOKAL"},
            {"titel": "Video-Content", "icon": "🎬",
             "inhalt": "Hook in den ersten 1,5 Sekunden entscheidend. Direkt mit dem Kerninhalt starten — kein Intro.",
             "tag": "TIPP"},
            {"titel": "Strategie", "icon": "🎯",
             "inhalt": "3–5 Postings pro Woche sind optimal. Konsistenz schlägt Quantität bei jedem Algorithmus.",
             "tag": "STRATEGIE"},
        ],
        "empfehlung": "Heute Story-Umfragen bei allen Kunden einplanen — interaktive Formate erhöhen die Engagement-Rate messbar.",
    }
    _heute_cache["date"] = today
    _heute_cache["data"] = fallback
    return JSONResponse(fallback)


@app.get("/systemgesundheit")
async def systemgesundheit_page():
    return FileResponse("frontend/systemgesundheit.html")


@app.post("/api/system/health")
async def api_system_health():
    from fastapi.responses import JSONResponse
    try:
        result = health_tools.run_health_checks()
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"detail": str(e)}, status_code=500)


@app.get("/api/system/repair/{repair_id}")
async def api_repair_info(repair_id: str):
    from fastapi.responses import JSONResponse
    info = health_tools.get_repair_info(repair_id)
    if not info:
        raise HTTPException(404, "Reparatur nicht gefunden")
    return JSONResponse(info)


@app.post("/api/system/repair/{repair_id}")
async def api_execute_repair(repair_id: str):
    from fastapi.responses import JSONResponse
    info = health_tools.get_repair_info(repair_id)
    if not info:
        raise HTTPException(404, "Reparatur nicht gefunden")
    try:
        result = health_tools.execute_repair(repair_id)
        return JSONResponse(result)
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    print("=" * 50, flush=True)
    print("  J.A.R.V.I.S. V2 Server", flush=True)
    print(f"  http://localhost:8340", flush=True)
    print("=" * 50, flush=True)
    uvicorn.run(app, host="0.0.0.0", port=8340)
