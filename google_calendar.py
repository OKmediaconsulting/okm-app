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

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get(
    "GOOGLE_REDIRECT_URI",
    "https://web-production-8d295.up.railway.app/api/calendar/oauth/callback"
)
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

TOKEN_FILE = os.path.join(os.environ.get("DATA_DIR", "/app/data"), "google_token.json")


def _load_creds() -> Credentials | None:
    if not os.path.exists(TOKEN_FILE):
        return None
    try:
        with open(TOKEN_FILE) as f:
            data = json.load(f)
        creds = Credentials(
            token=data.get("token"),
            refresh_token=data.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            scopes=SCOPES,
        )
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            _save_creds(creds)
        return creds
    except Exception:
        return None


def _save_creds(creds: Credentials):
    os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({
            "token": creds.token,
            "refresh_token": creds.refresh_token,
        }, f)


def get_auth_url() -> str:
    from google_auth_oauthlib.flow import Flow
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "redirect_uris": [REDIRECT_URI],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    return url


def handle_callback(code: str) -> bool:
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_config(
            {
                "web": {
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                    "redirect_uris": [REDIRECT_URI],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
        )
        flow.fetch_token(code=code)
        _save_creds(flow.credentials)
        return True
    except Exception as e:
        print(f"[gcal] callback error: {e}")
        return False


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
