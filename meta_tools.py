"""
Jarvis — Meta Business Suite Tools
Liest Follower-Zahlen aus Chrome via AppleScript/JavaScript.
Öffnet Chrome automatisch falls kein Meta-Tab vorhanden.
"""

import subprocess
import os
import time
import json
import tempfile

# Kunden-Seiten mit asset_id und business_id
PAGES = {
    "browns":               {"asset_id": "108636835886418", "name": "Browns Active Park"},
    "browns active":        {"asset_id": "108636835886418", "name": "Browns Active Park"},
    "browns active park":   {"asset_id": "108636835886418", "name": "Browns Active Park"},
    "genesis":              {"asset_id": "220493307989744", "name": "Genesis Vital Verl"},
    "genesis verl":         {"asset_id": "220493307989744", "name": "Genesis Vital Verl"},
    "genesis vital":        {"asset_id": "220493307989744", "name": "Genesis Vital Verl"},
    "genesis hövelhof":     {"asset_id": "849622271575810", "name": "Genesis Vital Hövelhof"},
    "genesis rietberg":     {"asset_id": "319608678114403", "name": "Genesis Vital Rietberg"},
    "werners":              {"asset_id": "106749787580156", "name": "Werners Fahrrad Fach-Werk"},
    "werner":               {"asset_id": "106749787580156", "name": "Werners Fahrrad Fach-Werk"},
    "fahrrad":              {"asset_id": "106749787580156", "name": "Werners Fahrrad Fach-Werk"},
}

BUSINESS_IDS = {
    "108636835886418": "2813923292152413",
    "220493307989744": "2019757088316476",
    "849622271575810": "2019757088316476",
    "319608678114403": "141263553181246",
    "106749787580156": "723062474828803",
}

META_CLIENTS_LIST = [
    {"key": "browns",  "name": "Browns Active Park",       "asset": "108636835886418", "biz": "2813923292152413"},
    {"key": "gnv",     "name": "Genesis Vital Verl",       "asset": "220493307989744", "biz": "2019757088316476"},
    {"key": "gnh",     "name": "Genesis Vital Hövelhof",   "asset": "849622271575810", "biz": "2019757088316476"},
    {"key": "gnr",     "name": "Genesis Vital Rietberg",   "asset": "319608678114403", "biz": "141263553181246"},
    {"key": "werners", "name": "Werners Fahrrad Fach-Werk","asset": "106749787580156", "biz": "723062474828803"},
]

# JS um Follower-Zahlen aus Meta Business Suite zu extrahieren
_FOLLOWER_JS = r"""
(function() {
    var txt = document.body ? (document.body.innerText || '') : '';
    var lines = txt.split('\n').map(function(l){ return l.trim(); }).filter(Boolean);
    var fb = null, ig = null, reach = null;

    for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        var next = (lines[i+1] || '').toLowerCase();
        var prev = (lines[i-1] || '').toLowerCase();

        // Zahl allein auf Zeile, danach "Follower" / "Abonnenten"
        var numMatch = line.match(/^([\d.,]+)$/);
        if (numMatch) {
            var n = next;
            if (n.indexOf('follower') !== -1 || n.indexOf('abonnent') !== -1) {
                var val = parseInt(line.replace(/[.,]/g, ''));
                if (!isNaN(val)) {
                    if (fb === null) fb = val;
                    else if (ig === null) ig = val;
                }
            }
            if (n.indexOf('erreicht') !== -1 || n.indexOf('reach') !== -1) {
                var val2 = parseInt(line.replace(/[.,]/g, ''));
                if (!isNaN(val2) && reach === null) reach = val2;
            }
        }

        // "1.234 Follower" in einer Zeile
        var m1 = line.match(/([\d.,]+)\s+(Follower|Abonnenten)/i);
        if (m1 && fb === null) fb = parseInt(m1[1].replace(/[.,]/g, ''));
        else if (m1 && ig === null) ig = parseInt(m1[1].replace(/[.,]/g, ''));

        // Reach
        var m2 = line.match(/([\d.,]+)\s+(Personen erreicht|erreicht|reached)/i);
        if (m2 && reach === null) reach = parseInt(m2[1].replace(/[.,]/g, ''));
    }

    return JSON.stringify({
        fb_followers: fb,
        ig_followers: ig,
        reach_7d: reach,
        url: window.location.href,
        title: document.title,
        text_length: txt.length
    });
})();
"""


def _run_js_in_chrome(js_code: str) -> str:
    """Führt JavaScript in einem Chrome-Tab mit business.facebook.com aus."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
        f.write(js_code)
        js_path = f.name

    script = f"""
tell application "Google Chrome"
    set targetTab to missing value
    repeat with w in every window
        repeat with t in every tab of w
            if URL of t contains "business.facebook.com" then
                set targetTab to t
                exit repeat
            end if
        end repeat
        if targetTab is not missing value then exit repeat
    end repeat
    if targetTab is missing value then
        return "TAB_NOT_FOUND"
    end if
    set jsCode to do shell script "cat " & quoted form of "{js_path}"
    set result to execute targetTab javascript jsCode
    return result as string
end tell
"""
    try:
        result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=20)
        return result.stdout.strip()
    except Exception as e:
        return f"FEHLER: {e}"
    finally:
        try:
            os.unlink(js_path)
        except Exception:
            pass


def _ensure_meta_tab_open() -> bool:
    """Öffnet Meta Business Suite in Chrome falls kein Tab vorhanden."""
    # Prüfen ob Tab schon offen
    check = _run_js_in_chrome("window.location.href")
    if check != "TAB_NOT_FOUND":
        return True

    # Chrome öffnen mit Meta Business Suite
    default_url = f"https://business.facebook.com/latest/home?asset_id={META_CLIENTS_LIST[0]['asset']}&business_id={META_CLIENTS_LIST[0]['biz']}"
    script = f"""
tell application "Google Chrome"
    activate
    if (count of windows) = 0 then
        make new window
    end if
    set newTab to make new tab at end of tabs of window 1
    set URL of newTab to "{default_url}"
end tell
"""
    try:
        subprocess.run(["osascript", "-e", script], capture_output=True, timeout=10)
    except (FileNotFoundError, OSError):
        pass
    time.sleep(6)  # Seite laden lassen

    # Nochmal prüfen
    check2 = _run_js_in_chrome("window.location.href")
    return check2 != "TAB_NOT_FOUND"


def _navigate_to_page(asset_id: str, wait: int = 6) -> bool:
    """Navigiert in Meta Business Suite zur angegebenen Seite, erzwingt Reload."""
    business_id = BUSINESS_IDS.get(asset_id, "2813923292152413")
    url = f"https://business.facebook.com/latest/home?asset_id={asset_id}&business_id={business_id}"
    # Immer neu laden — auch wenn URL schon stimmt
    js = f"window.location.href = '{url}'; 'ok'"
    result = _run_js_in_chrome(js)
    if result == "TAB_NOT_FOUND":
        return False
    time.sleep(wait)
    return True


def _extract_followers(asset_id: str) -> dict:
    """Navigiert zur Seite und extrahiert Follower-Zahlen strukturiert."""
    if not _navigate_to_page(asset_id, wait=6):
        return {"error": "Meta Business Suite nicht geöffnet"}

    raw = _run_js_in_chrome(_FOLLOWER_JS)
    if not raw or raw == "TAB_NOT_FOUND":
        return {"error": "Seite konnte nicht ausgelesen werden"}

    try:
        data = json.loads(raw)
        return data
    except Exception:
        return {"error": f"Parse-Fehler: {raw[:100]}"}


def find_page(client_name: str):
    """Findet eine Kunden-Page anhand des Namens."""
    name_lower = client_name.lower().strip()
    if name_lower in PAGES:
        return PAGES[name_lower]
    for key, page in PAGES.items():
        if key in name_lower or name_lower in key:
            return page
    for key, page in PAGES.items():
        if any(w in page["name"].lower() for w in name_lower.split()):
            return page
    return None


def get_client_data(client_name: str) -> str:
    """Liest Follower-Zahlen für einen Kunden und gibt lesbaren Text zurück."""
    page = find_page(client_name)
    if not page:
        available = ", ".join(sorted(set(p["name"] for p in PAGES.values())))
        return f"Kunde '{client_name}' nicht gefunden. Bekannte Seiten: {available}"

    _ensure_meta_tab_open()
    data = _extract_followers(page["asset_id"])

    if "error" in data:
        return f"{page['name']}: {data['error']}"

    fb  = f"{data['fb_followers']:,}".replace(",", ".") if data.get("fb_followers") else "—"
    ig  = f"{data['ig_followers']:,}".replace(",", ".") if data.get("ig_followers") else "—"
    reach = f"{data['reach_7d']:,}".replace(",", ".") if data.get("reach_7d") else "—"

    return (
        f"{page['name']}\n"
        f"Facebook: {fb} Follower\n"
        f"Instagram: {ig} Follower\n"
        f"Reichweite (7 Tage): {reach}"
    )


def get_meta_overview() -> str:
    """Liest die aktuell angezeigte Meta Business Suite Seite (Rohtext)."""
    _ensure_meta_tab_open()
    js = "(function(){ try{ return document.body.innerText.substring(0,5000); }catch(e){ return String(e); } })()"
    data = _run_js_in_chrome(js)
    if not data or data == "TAB_NOT_FOUND" or len(data) < 20:
        return "Meta Business Suite konnte nicht ausgelesen werden."
    return data


def get_all_clients_overview() -> str:
    """Liest alle Kunden-Seiten nacheinander."""
    _ensure_meta_tab_open()
    results = []
    seen = set()
    for key, page in PAGES.items():
        if page["asset_id"] in seen:
            continue
        seen.add(page["asset_id"])
        data = _extract_followers(page["asset_id"])
        if "error" not in data:
            fb = data.get("fb_followers", "—")
            ig = data.get("ig_followers", "—")
            results.append(f"{page['name']}: FB {fb} · IG {ig}")
        else:
            results.append(f"{page['name']}: {data['error']}")
    return "\n".join(results) if results else "Keine Daten verfügbar."
