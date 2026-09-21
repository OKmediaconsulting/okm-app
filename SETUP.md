# Jarvis Setup Guide

Dein persoenlicher KI-Assistent — inspiriert von Iron Mans Jarvis.

**Was du bekommst:**
- Zweimal klatschen → dein komplettes Arbeits-Setup startet
- Jarvis begruesst dich mit Wetter und deinen Aufgaben
- Du sprichst frei mit Jarvis — er antwortet per Stimme
- Jarvis kann deinen Browser steuern (suchen, Seiten oeffnen)
- Jarvis kann deinen Bildschirm sehen und beschreiben

---

## Voraussetzungen

- **Windows 10/11**
- **Google Chrome** (fuer Spracheingabe + Jarvis UI)
- **Claude Code** installiert

Python, alle Dependencies und Browser-Treiber werden automatisch von Claude Code installiert — du musst nichts manuell einrichten.

---

## Setup starten

Oeffne diesen Ordner in VS Code, starte Claude Code, und sag:

> Richte Jarvis fuer mich ein.

Claude Code fragt dich dann nach:

1. **Dein Name** und wie du angesprochen werden willst (z.B. "Sir")
2. **Anthropic API Key** — von https://console.anthropic.com (fuer Claude Haiku, das Gehirn)
3. **ElevenLabs API Key** — von https://elevenlabs.io (fuer die Stimme)
4. **Spotify-Song** — Link zum Song der beim Start spielen soll
5. **Programme** — welche Apps sollen beim Doppelklatschen starten?
6. **Website** — welche Seite soll im Browser aufgehen?
7. **Stadt fuers Wetter** — z.B. Hamburg
8. **Obsidian Vault** — optional, welcher Ordner soll Jarvis kennen?

---

## Was Claude Code fuer dich einrichtet

### 1. Voraussetzungen installieren
Claude Code prueft und installiert automatisch:
- **Python 3.10+** (falls nicht vorhanden, via `winget install Python.Python.3.12`)
- **Alle Python-Pakete** (`pip install -r requirements.txt`)
- **Playwright Chromium** (`playwright install chromium`)

### 2. config.json erstellen
Claude Code erstellt `config.json` aus `config.example.json` mit deinen echten Daten:
```json
{
  "anthropic_api_key": "sk-ant-...",
  "elevenlabs_api_key": "sk_...",
  "elevenlabs_voice_id": "VOICE_ID",
  "user_name": "Dein Name",
  "user_address": "Sir",
  "city": "Hamburg",
  "workspace_path": "C:\\pfad\\zum\\jarvis_template",
  "spotify_track": "spotify:track:DEIN_TRACK_ID",
  "browser_url": "https://deine-website.com",
  "obsidian_inbox_path": "C:\\pfad\\zum\\obsidian\\inbox",
  "apps": ["obsidian://open"]
}
```

### 3. ElevenLabs Stimme
Eine deutsche Stimme auswaehlen und die Voice ID in die Config eintragen. Empfehlung: **Felix Serenitas** (Starter Plan noetig) oder eine der Standard-Stimmen (Free Plan).

### 4. Systemprompt
Der Systemprompt wird in `server.py` automatisch aus der Config generiert. Er enthaelt:
- Jarvis-Persoenlichkeit (trocken, sarkastisch, britisch-hoeflich)
- Siezen mit gewaehlter Anrede
- Wetter- und Aufgaben-Integration
- Browser-Steuerung via Action-Tags
- Screen-Capture-Faehigkeit

---

## Architektur

```
Mikrofon (Chrome) → Web Speech API → WebSocket → FastAPI Server
                                                      ↓
                                                Claude Haiku (denkt)
                                                      ↓
                                    ┌─────────────────┼──────────────────┐
                                    ↓                 ↓                  ↓
                            ElevenLabs TTS     Playwright Browser   Screen Capture
                            (spricht)          (sucht/oeffnet)     (sieht Bildschirm)
                                    ↓
                            Audio → Browser Speaker
```

---

## Starten

### Jarvis manuell starten
```
python server.py
```
Dann http://localhost:8340 in Chrome oeffnen.

### Alles per Doppelklatschen starten
```
python scripts\clap-trigger.py
```
Zweimal klatschen → Spotify, VS Code, Obsidian, Chrome mit Jarvis starten automatisch.

### Clap Trigger beim Windows-Start
1. `Win + R` → `taskschd.msc`
2. Aufgabe erstellen → Trigger: "Bei Anmeldung"
3. Aktion: `powershell` mit Argument:
   `-ExecutionPolicy Bypass -WindowStyle Hidden -Command "python C:\DEIN\PFAD\scripts\clap-trigger.py"`

---

## Was Jarvis kann

- **"Wie ist das Wetter?"** → kennt das aktuelle Wetter
- **"Such nach MiroFish"** → oeffnet Browser, sucht, liest Ergebnisse
- **"Oeffne skool.com"** → oeffnet die Seite im Browser
- **"Was siehst du auf meinem Bildschirm?"** → macht Screenshot, beschreibt was er sieht
- **Jede Frage** → antwortet im Jarvis-Stil mit Stimme

---

## Fehlerbehebung

| Problem | Loesung |
|---|---|
| Jarvis spricht nicht | Pruefen ob Server laeuft (`python server.py`) und Chrome offen ist |
| "Verbindung verloren" | Alter Server-Prozess laeuft noch → `taskkill /f /im python.exe` und neu starten |
| Klatschen wird nicht erkannt | Threshold in `clap-trigger.py` anpassen |
| Browser-Suche geht nicht | `playwright install chromium` ausfuehren |
| Kein Audio im Browser | Einmal auf die Seite klicken (Chrome Autoplay-Policy) |

---

## Fuer Claude Code: Setup-Anweisungen

Wenn ein Nutzer "Richte Jarvis ein" sagt, fuehre folgende Schritte aus:

**Schritt 0 — Voraussetzungen pruefen und installieren:**
- Pruefe ob Python 3.10+ installiert ist: `python --version`
- Falls nicht: `winget install Python.Python.3.12` — warte bis fertig, pruefe erneut
- Pruefe ob Google Chrome installiert ist. Falls nicht, weise den Nutzer an Chrome zu installieren
- Installiere Python-Pakete: `pip install -r requirements.txt`
- Installiere Playwright Browser: `playwright install chromium`

**Schritt 1 — Nutzerdaten abfragen:**
Frage nach:
- Name (z.B. "Julian")
- Taetigkeit/Rolle (z.B. "KI-Berater und Automatisierungsexperte") — wird in den Systemprompt eingebaut
- Gewuenschte Anrede (z.B. "Sir", "Chef", oder einfach Vorname)
- Anthropic API Key (von https://console.anthropic.com)
- ElevenLabs API Key (von https://elevenlabs.io)
- Spotify-Song (Link zum Song der beim Start spielen soll)
- Programme die beim Doppelklatschen starten sollen (z.B. Obsidian, Notion)
- Website die im Browser aufgehen soll
- Stadt fuers Wetter (z.B. Hamburg)
- Obsidian Vault Pfad (optional)

**Schritt 2 — Config erstellen:**
Erstelle `config.json` aus `config.example.json` mit den Nutzerdaten. Setze den `workspace_path` auf den aktuellen Ordnerpfad.

**Schritt 3 — ElevenLabs Stimme einrichten:**
- Liste verfuegbare Stimmen via ElevenLabs API
- Empfehle eine deutsche Stimme
- Trage die Voice ID in die Config ein

**Schritt 4 — Systemprompt anpassen:**
Oeffne `server.py` und finde die Funktion `build_system_prompt()`. Dort steht der komplette Systemprompt als f-String. Ersetze ALLE Vorkommen der folgenden Werte im gesamten Prompt-Text:
- Jedes "Julian" → Name des Nutzers (kommt mehrfach vor im Prompt!)
- "KI-Berater und Automatisierungsexperte" → Taetigkeit/Rolle des Nutzers
- Jedes "Sir" als Anrede → gewuenschte Anrede des Nutzers
- "Hamburg" → Stadt des Nutzers

Ausserdem oben in `server.py` bei den Config-Defaults:
- `USER_NAME = config.get("user_name", "Julian")` → Default-Name anpassen
- `CITY = config.get("city", "Hamburg")` → Default-Stadt anpassen

WICHTIG: Pruefe den Prompt sorgfaeltig — "Julian" und "Sir" kommen an mehreren Stellen vor. Alle muessen ersetzt werden.

**Schritt 5 — Testen:**
- Starte den Server: `python server.py`
- Oeffne http://localhost:8340 in Chrome
- Pruefe ob Jarvis spricht und antwortet

**Schritt 6 — Optional: Autostart einrichten (Task Scheduler)**

---

## Credits

Template von Julian — [Skool Community](https://skool.com/ki-automatisierung)
