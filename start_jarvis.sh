#!/bin/bash
# Jarvis starten — LaunchAgent verwaltet den Server, wir öffnen nur Chrome

PLIST=~/Library/LaunchAgents/net.okmediaconsulting.jarvis.plist

# Server per LaunchAgent sicherstellen (startet ihn falls noch nicht aktiv)
launchctl load "$PLIST" 2>/dev/null || true

# Warten bis Server bereit (max 15s)
for i in $(seq 1 20); do
  sleep 0.75
  curl -s http://localhost:8340/api/crm/stats > /dev/null 2>&1 && break
done

# Dashboard in Chrome öffnen
open -a "Google Chrome" "http://localhost:8340/dashboard"
