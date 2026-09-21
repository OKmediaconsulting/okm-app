"""
Jarvis — Calendar Tools
Read and create events via macOS Calendar app (AppleScript).
Works with any calendar synced to macOS (Google, iCloud, etc.).
"""

import subprocess
import json
from datetime import datetime, timedelta


def _run_applescript(script: str) -> str:
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip()
    except (FileNotFoundError, OSError):
        return ""


def get_today_events() -> list[dict]:
    """Return all events for today from Privat, Arbeit and okmediaconsulting calendars."""
    script = """
    set output to ""
    set allowList to {"Privat", "Arbeit", "info@okmediaconsulting.net"}
    tell application "Calendar"
        set startDate to (current date)
        set hours of startDate to 0
        set minutes of startDate to 0
        set seconds of startDate to 0
        set endDate to startDate + 86399
        repeat with cal in every calendar
            set calName to name of cal
            if calName is in allowList then
                try
                    set calEvents to (every event of cal whose start date >= startDate and start date <= endDate)
                    repeat with evt in calEvents
                        set output to output & (summary of evt) & "|" & ((start date of evt) as string) & "||"
                    end repeat
                end try
            end if
        end repeat
    end tell
    return output
    """
    raw = _run_applescript(script)
    events = []
    for entry in raw.split("||"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("|")
        if len(parts) >= 2:
            events.append({"title": parts[0], "start": parts[1]})
    events.sort(key=lambda e: e["start"])
    return events


def get_week_events() -> list[dict]:
    """Return all events for the next 7 days."""
    today = datetime.now().strftime("%Y-%m-%d")
    week_end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    script = f"""
    set theDate to date "{today}"
    set endDate to date "{week_end}"
    set eventList to {{}}
    tell application "Calendar"
        repeat with cal in every calendar
            set evts to (every event of cal whose start date >= theDate and start date <= endDate)
            repeat with evt in evts
                set evtStart to start date of evt
                set evtTitle to summary of evt
                set evtInfo to (evtTitle & "|" & (evtStart as string))
                set end of eventList to evtInfo
            end repeat
        end repeat
    end tell
    set output to ""
    repeat with item in eventList
        set output to output & item & "||"
    end repeat
    return output
    """
    raw = _run_applescript(script)
    events = []
    for entry in raw.split("||"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("|")
        if len(parts) >= 2:
            events.append({"title": parts[0], "start": parts[1]})
    events.sort(key=lambda e: e["start"])
    return events


def create_event(title: str, date_str: str, time_str: str, duration_minutes: int = 60, calendar: str = "Arbeit") -> bool:
    """Create a new calendar event. date_str: DD.MM.YYYY, time_str: HH:MM"""
    try:
        day, month, year = date_str.split(".")
        hour, minute = time_str.split(":")
        start = datetime(int(year), int(month), int(day), int(hour), int(minute))
        end = start + timedelta(minutes=duration_minutes)
        start_str = start.strftime("%d.%m.%Y %H:%M")
        end_str = end.strftime("%d.%m.%Y %H:%M")
        script = f"""
        tell application "Calendar"
            tell calendar "{calendar}"
                make new event with properties {{summary:"{title}", start date:date "{start_str}", end date:date "{end_str}"}}
            end tell
        end tell
        return "ok"
        """
        result = _run_applescript(script)
        return "ok" in result
    except Exception as e:
        print(f"[calendar] create error: {e}")
        return False


def get_contacts(search: str = "") -> list[dict]:
    """Search contacts by name."""
    script = f"""
    tell application "Contacts"
        set results to {{}}
        set searchTerm to "{search}"
        repeat with p in every person
            set pName to name of p
            if searchTerm is "" or pName contains searchTerm then
                set pPhone to ""
                set pEmail to ""
                if (count of phones of p) > 0 then
                    set pPhone to value of item 1 of phones of p
                end if
                if (count of emails of p) > 0 then
                    set pEmail to value of item 1 of emails of p
                end if
                set end of results to (pName & "|" & pPhone & "|" & pEmail)
            end if
        end repeat
    end tell
    set output to ""
    repeat with item in results
        set output to output & item & "||"
    end repeat
    return output
    """
    raw = _run_applescript(script)
    contacts = []
    for entry in raw.split("||"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("|")
        if parts[0]:
            contacts.append({
                "name": parts[0],
                "phone": parts[1] if len(parts) > 1 else "",
                "email": parts[2] if len(parts) > 2 else "",
            })
    return contacts[:10]
