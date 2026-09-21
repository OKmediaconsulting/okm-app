#!/usr/bin/env python3
"""
Jarvis — Follow-up Erinnerungen
Läuft täglich via LaunchAgent, schickt macOS-Notifications für fällige Follow-ups.
"""
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(__file__))
import crm_tools


def notify(title: str, message: str):
    script = f'display notification "{message}" with title "{title}" sound name "Glass"'
    # Über Script Editor senden — hat macOS Notification-Berechtigung
    subprocess.run([
        "osascript", "-e",
        f'tell application "Script Editor" to run',
        "-e", script
    ])


def main():
    fups = crm_tools.followups_heute()
    if not fups:
        return

    # Einzelne Notification pro Follow-up (max 5)
    for f in fups[:5]:
        firma = f.get("firma", "")
        titel = f.get("titel", "")
        datum = f.get("faellig_am", "")
        notify(
            f"📋 Follow-up: {firma}",
            f"{titel} · fällig {datum}"
        )

    # Zusammenfassung wenn mehr als 5
    if len(fups) > 5:
        notify("Jarvis CRM", f"{len(fups)} fällige Follow-ups heute")


if __name__ == "__main__":
    main()
