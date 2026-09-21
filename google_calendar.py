"""
Google Calendar Integration — pure urllib, keine google-auth Abhängigkeit.
"""
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

CLIENT_ID = "571667776861-hj816hp5gm9r1ldkojcnficv58ql7nur.apps.googleusercontent.com"
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
REFRESH_TOKEN = os.environ.get("GOOGLE_REFRESH_TOKEN", "")
REDIRECT_URI = "https://web-production-8d295.up.railway.app/api/calendar/oauth/callback"
SCOPES = "https://www.googleapis.com/auth/calendar.readonly"


def _get_access_token() -> str:
    """Holt einen frischen Access Token via Refresh Token."""
    if not REFRESH_TOKEN or not CLIENT_SECRET:
        return ""
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=data,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("access_token", "")
    except Exception as e:
        print(f"[gcal] token error: {e}")
        return ""


def _api_get(path: str, params: dict) -> dict:
    """Ruft die Google Calendar API auf."""
    token = _get_access_token()
    if not token:
        return {}
    url = f"https://www.googleapis.com/calendar/v3/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[gcal] api error: {e}")
        return {}


def is_connected() -> bool:
    return bool(REFRESH_TOKEN and CLIENT_SECRET)


def get_auth_url() -> str:
    params = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    })
    return f"https://accounts.google.com/o/oauth2/auth?{params}"


def handle_callback(code: str, state: str = "") -> tuple:
    data = urllib.parse.urlencode({
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
    }).encode()
    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token", data=data, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            tokens = json.loads(r.read())
        rt = tokens.get("refresh_token", "")
        if rt:
            print(f"[gcal] new refresh token: {rt[:20]}...")
        return True, ""
    except Exception as e:
        return False, str(e)


def _parse_events(data: dict) -> list:
    events = []
    for e in data.get("items", []):
        start_raw = e["start"].get("dateTime", e["start"].get("date", ""))
        events.append({"title": e.get("summary", ""), "start": start_raw})
    return events


def get_today_events() -> list:
    from datetime import timezone as tz
    import zoneinfo
    try:
        local_tz = zoneinfo.ZoneInfo("Europe/Berlin")
        now = datetime.now(local_tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    except Exception:
        now = datetime.now(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    data = _api_get("calendars/primary/events", {
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
    })
    return _parse_events(data)


def get_week_events() -> list:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=7)
    data = _api_get("calendars/primary/events", {
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
    })
    return _parse_events(data)
