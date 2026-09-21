# CLAUDE.md

Dieses Workspace ist **Jarvis** — ein persoenlicher KI-Assistent mit Sprachsteuerung, Browser-Kontrolle und Doppelklatschen-Trigger.

---

## Fuer Claude Code: Setup-Modus

Wenn der Nutzer nach dem Setup fragt oder "Richte Jarvis ein" sagt, folge den Anweisungen in `SETUP.md`. Frage den Nutzer nach seinem Namen, seiner Taetigkeit, und wie er angesprochen werden moechte — diese Infos muessen in den Systemprompt in `server.py` eingetragen werden (ersetze die aktuellen Platzhalter "Julian", "KI-Berater und Automatisierungsexperte", "Sir").

**WICHTIG — Pruefe und installiere zuerst alle Voraussetzungen:**

1. **Python**: Pruefe ob Python 3.10+ installiert ist (`python --version`). Falls nicht, installiere es:
   - Windows: `winget install Python.Python.3.12`
   - Warte bis die Installation abgeschlossen ist und pruefe erneut

2. **Google Chrome**: Pruefe ob Chrome installiert ist. Falls nicht, weise den Nutzer an Chrome von https://google.com/chrome zu installieren.

3. **pip Dependencies**: `pip install -r requirements.txt`

4. **Playwright Browser**: `playwright install chromium`

Erst NACHDEM alle Voraussetzungen installiert sind, fahre mit dem Setup in `SETUP.md` fort (API Keys abfragen, config.json erstellen, etc.).

---

## Workspace Structure

```
.
├── CLAUDE.md              # This file
├── SETUP.md               # Setup-Anleitung fuer Claude Code
├── config.json            # Persoenliche Config (gitignored)
├── config.example.json    # Template mit Platzhaltern
├── requirements.txt       # Python Dependencies
├── server.py              # FastAPI Backend (Claude Haiku + ElevenLabs TTS)
├── browser_tools.py       # Playwright Browser-Steuerung
├── screen_capture.py      # Screenshot + Claude Vision
├── frontend/
│   ├── index.html         # Jarvis Web-UI
│   ├── main.js            # Speech Recognition + WebSocket + Audio
│   └── style.css          # Dark Theme mit Orb-Animation
└── scripts/
    ├── clap-trigger.py    # Doppelklatschen-Erkennung
    └── launch-session.ps1 # Startet alle Apps + Jarvis
```

## Skripte / Canva Setup

Zusaetzlich zu den Reel-Skripten (Text) erzeugt die `/skripte`-Seite pro Kunde
woechentlich 3 fertige Canva-Postings (Bild): `canva_automation.py` (OAuth +
Asset-Upload + Autofill), `canva_content.py` (Claude generiert Post-Texte aus
dem bestehenden Kundenprofil in `scripts_tools.py`), `canva_pipeline.py`
(verbindet beides). Kunden-Canva-Felder (`canva_brand_template_id`,
`canva_medien_pfad`, `canva_used_photos`, `canva_last_run`,
`canva_last_status`) liegen als zusaetzliche Spalten direkt in der
bestehenden `kunden`-Tabelle; Ergebnisse in der neuen `canva_posts`-Tabelle.

Einmalige manuelle Einrichtung:

1. **Canva Developer Integration anlegen**: [canva.com/developers](https://www.canva.com/developers) →
   neue Integration → Client ID + Secret in `config.json` eintragen
   (`canva_client_id`, `canva_client_secret`). Redirect URI:
   `http://localhost:8340/canva/callback`.
2. **Ein Brand Template in Canva anlegen** mit genau diesen Autofill-Feldnamen:
   `logo` (Bild), `foto` (Bild), `headline` (Text), `subtext` (Text), `cta` (Text).
   Die Brand Template ID direkt im Canva-Bereich der Kundenansicht auf
   `/skripte` eintragen, zusammen mit dem Medien-Ordner (Logo + Fotos).
3. Auf `/skripte` bei einem Kunden auf "Jetzt verbinden" klicken (einmalige
   Canva-OAuth-Freigabe).
4. Fuer den woechentlichen Auto-Lauf (auch wenn Jarvis nicht offen ist):
   `bash scripts/install-weekly-canva.sh` (installiert einen launchd-Job,
   Montag 08:00 Uhr, unabhaengig vom Hauptserver).
