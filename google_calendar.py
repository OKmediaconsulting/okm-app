"""
Google Calendar Integration für Jarvis / OKM
OAuth2 Web-Flow: einmalig autorisieren, danach läuft alles über Refresh-Token.
"""
import os
import json
from datetime import datetime, timedelta, timezone
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

CLIENT_ID = "571667776861-hj816hp5gm9r1ldkojcnficv58ql7nur.apps.googleusercontent.com"
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "https://web-production-8d295.up.railway.app/api/calendar/oauth/callback"
)
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

TOKEN_FILE = os.path.join(os.environ.get("DATA_DIR", "/app/data"), "google_token.json")


def _load_creds():
    refresh_token = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
    if not refresh_token and os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE) as f:
                refresh_token = json.load(f).get("refresh_token", "")
        except Exception:
            pass
    if not refresh_token:
        return None
    try:
        creds = Credentials(
            token=None,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scopes=SCOPES,
        )
        creds.refresh(Request())
        return creds
    except Exception as e:
        print(f"[gcal] creds error: {e}")
        return None


def _save_creds(creds: Credentials):
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
        }, f)


def get_auth_url() -> str:
    import urllib.parse
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
    })
    return f"https://accounts.google.com/o/oauth2/auth?{params}"


def handle_callback(code: str, state: str = "") -> bool:
    try:
        import urllib.request
        import urllib.parse
        data = urllib.parse.urlencode({
            "code": code,
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uri": REDIRECT_URI,
            "grant_type": "authorization_code",
        }).encode()
        req = urllib.request.Request(
            "https://oauth2.googleapis.com/token",
            data=data,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            tokens = json.loads(resp.read())
        os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
        with open(TOKEN_FILE, "w") as f:
            json.dump({
                "token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
            }, f)
        return True, ""
    except Exception as e:
        print(f"[gcal] callback error: {e}")
        return False, str(e)


def is_connected() -> bool:
    return _load_creds() is not None


def get_today_events() -> list[dict]:
    creds = _load_creds()
    if not creds:
        return []
    try:
        service = build("calendar", "v3", credentials=creds)
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        result = service.events().list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = []
        for e in result.get("items", []):
            start_raw = e["start"].get("dateTime", e["start"].get("date", ""))
            events.append({"title": e.get("summary", ""), "start": start_raw})
        return events
    except Exception as ex:
        print(f"[gcal] get_today_events error: {ex}")
        return []


def get_week_events() -> list[dict]:
    creds = _load_creds()
    if not creds:
        return []
    try:
        service = build("calendar", "v3", credentials=creds)
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        result = service.events().list(
            calendarId="primary",
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
        events = []
        for e in result.get("items", []):
            start_raw = e["start"].get("dateTime", e["start"].get("date", ""))
            events.append({"title": e.get("summary", ""), "start": start_raw})
        return events
    except Exception as ex:
        print(f"[gcal] get_week_events error: {ex}")
        return []
