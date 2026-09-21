#!/bin/bash
# Installiert den woechentlichen Canva-Posts-Job als macOS launchd-Agent
# (laeuft jeden Montag 08:00 Uhr, unabhaengig davon ob Jarvis offen ist).
set -e

PLIST_SRC="$(cd "$(dirname "$0")" && pwd)/com.jarvis.weeklycanva.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.jarvis.weeklycanva.plist"

cp "$PLIST_SRC" "$PLIST_DEST"
launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo "Installiert. Naechster Lauf: Montag 08:00 Uhr."
echo "Logs: $(dirname "$PLIST_SRC")/weekly-canva.log"
echo "Deinstallieren: launchctl unload '$PLIST_DEST' && rm '$PLIST_DEST'"
