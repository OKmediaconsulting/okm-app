# Railway.app Deployment — OK Media Consulting

## Einmalige Einrichtung

### 1. GitHub Repo erstellen
```bash
cd /Users/user/jarvis/app
git init
git add .
git commit -m "Initial commit"
```
Dann auf github.com ein neues privates Repo erstellen und pushen:
```bash
git remote add origin https://github.com/DEIN_USERNAME/okm-app.git
git push -u origin main
```

### 2. Railway.app einrichten
1. Gehe auf **railway.app** → "New Project" → "Deploy from GitHub repo"
2. Wähle das `okm-app` Repo
3. Railway erkennt automatisch Python + `Procfile`

### 3. Environment Variables auf Railway setzen
In Railway → Dein Projekt → "Variables" diese Werte eintragen:

| Variable | Wert |
|---|---|
| `ANTHROPIC_API_KEY` | dein Anthropic API Key |
| `JWT_SECRET` | zufälliger langer String (min. 32 Zeichen) |
| `DATA_DIR` | `/app/data` |
| `USER_NAME` | `Okan` |
| `CITY` | `Melle` |

### 4. Persistent Volume für Datenbanken
In Railway → Dein Projekt → "Add Volume":
- Mount Path: `/app/data`
- Ohne Volume gehen alle Daten beim Restart verloren!

### 5. Domain
Railway gibt automatisch eine URL wie `okm-app.up.railway.app`.
Eigene Domain: Railway → Settings → Custom Domain → DNS CNAME eintragen.

### 6. Erste Anmeldung
Beim ersten Aufruf der App → automatisch zu `/setup` weitergeleitet → Owner-Account anlegen.

## Lokale Entwicklung (weiterhin möglich)
```bash
cd /Users/user/jarvis/app
python3 -m uvicorn server:app --port 8340 --reload
```
Öffne http://localhost:8340

## ENV-Variablen lokal (optional)
Statt config.json können auch ENV-Variablen gesetzt werden:
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export JWT_SECRET="..."
python3 -m uvicorn server:app --port 8340
```
