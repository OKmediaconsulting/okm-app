"""
Canva Connect API client — OAuth (PKCE), asset upload, brand template autofill.

Setup required once in Canva (see README.md "Skripte / Canva Setup"):
  1. Create a Developer Integration at canva.com/developers -> get Client ID + Secret.
  2. Set the Integration's redirect URI to match `canva_redirect_uri` in config.json
     (default: http://localhost:8340/canva/callback).
  3. Create a Brand Template with autofill fields named exactly:
       logo      (image)
       foto      (image)
       headline  (text)
       subtext   (text)
       cta       (text)
     Note its Brand Template ID (visible in the template's share/API panel).
"""

import asyncio
import base64
import hashlib
import json
import os
import secrets
import time
from urllib.parse import urlencode

import httpx

WORKSPACE = os.path.dirname(__file__)
TOKENS_PATH = os.path.join(WORKSPACE, "canva_tokens.json")

AUTHORIZE_URL = "https://www.canva.com/api/oauth/authorize"
TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
API_BASE = "https://api.canva.com/rest/v1"

SCOPES = "asset:read asset:write brandtemplate:content:read brandtemplate:meta:read design:content:read design:content:write design:meta:read"

# Field names the frontend/backend expect on every Brand Template used here.
FIELD_LOGO = "logo"
FIELD_FOTO = "foto"
FIELD_HEADLINE = "headline"
FIELD_SUBTEXT = "subtext"
FIELD_CTA = "cta"


class CanvaError(Exception):
    pass


class CanvaNotConnected(CanvaError):
    pass


# --- token storage -----------------------------------------------------

def _load_tokens():
    if not os.path.exists(TOKENS_PATH):
        return None
    with open(TOKENS_PATH, "r") as f:
        return json.load(f)


def _save_tokens(tokens: dict):
    with open(TOKENS_PATH, "w") as f:
        json.dump(tokens, f, indent=2)


def is_connected() -> bool:
    return _load_tokens() is not None


def disconnect():
    if os.path.exists(TOKENS_PATH):
        os.remove(TOKENS_PATH)


# --- OAuth (PKCE) --------------------------------------------------------

def build_authorize_url(client_id: str, redirect_uri: str) -> tuple[str, str, str]:
    """Returns (authorize_url, code_verifier, state). Caller must persist
    code_verifier + state (e.g. in a short-lived cookie/session) to complete
    the exchange in the callback."""
    code_verifier = secrets.token_urlsafe(64)[:96]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(16)

    params = {
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "scope": SCOPES,
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}", code_verifier, state


async def exchange_code(client_id: str, client_secret: str, redirect_uri: str, code: str, code_verifier: str):
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            TOKEN_URL,
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            },
        )
    if resp.status_code != 200:
        raise CanvaError(f"Token-Austausch fehlgeschlagen ({resp.status_code}): {resp.text[:300]}")
    tokens = resp.json()
    tokens["obtained_at"] = time.time()
    _save_tokens(tokens)
    return tokens


async def _refresh(client_id: str, client_secret: str, refresh_token: str):
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            TOKEN_URL,
            headers={"Authorization": f"Basic {auth}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
    if resp.status_code != 200:
        raise CanvaError(f"Token-Refresh fehlgeschlagen ({resp.status_code}): {resp.text[:300]}")
    tokens = resp.json()
    tokens["obtained_at"] = time.time()
    _save_tokens(tokens)
    return tokens


async def get_access_token(client_id: str, client_secret: str) -> str:
    tokens = _load_tokens()
    if not tokens:
        raise CanvaNotConnected("Canva ist nicht verbunden. Bitte zuerst unter /skripte verbinden.")

    age = time.time() - tokens.get("obtained_at", 0)
    if age > tokens.get("expires_in", 3600) - 60:
        tokens = await _refresh(client_id, client_secret, tokens["refresh_token"])
    return tokens["access_token"]


# --- API calls -----------------------------------------------------------

async def _request(method: str, path: str, token: str, **kwargs) -> dict:
    async with httpx.AsyncClient(timeout=60) as http:
        resp = await http.request(method, f"{API_BASE}{path}", headers={"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}, **kwargs)
    if resp.status_code >= 400:
        raise CanvaError(f"Canva API {method} {path} -> {resp.status_code}: {resp.text[:300]}")
    return resp.json() if resp.content else {}


async def list_brand_templates(client_id: str, client_secret: str) -> list[dict]:
    token = await get_access_token(client_id, client_secret)
    data = await _request("GET", "/brand-templates", token)
    return data.get("items", [])


async def get_brand_template_fields(client_id: str, client_secret: str, brand_template_id: str) -> dict:
    token = await get_access_token(client_id, client_secret)
    data = await _request("GET", f"/brand-templates/{brand_template_id}/dataset", token)
    return data.get("dataset", {})


REQUIRED_FIELDS = [FIELD_LOGO, FIELD_FOTO, FIELD_HEADLINE, FIELD_SUBTEXT, FIELD_CTA]


async def validate_brand_template(client_id: str, client_secret: str, brand_template_id: str):
    """Wirft CanvaError mit klarer Meldung, falls dem Template Autofill-Felder fehlen."""
    dataset = await get_brand_template_fields(client_id, client_secret, brand_template_id)
    missing = [f for f in REQUIRED_FIELDS if f not in dataset]
    if missing:
        raise CanvaError(
            f"Brand Template '{brand_template_id}' hat nicht alle erwarteten Autofill-Felder. "
            f"Fehlend: {', '.join(missing)}. Vorhanden: {', '.join(dataset.keys()) or 'keine'}."
        )


async def upload_asset(client_id: str, client_secret: str, file_path: str, name: str) -> str:
    """Uploads a local image and returns its Canva asset_id."""
    token = await get_access_token(client_id, client_secret)
    with open(file_path, "rb") as f:
        content = f.read()

    metadata = json.dumps({"name": name}, ensure_ascii=False)
    async with httpx.AsyncClient(timeout=60) as http:
        resp = await http.post(
            f"{API_BASE}/asset-uploads",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/octet-stream",
                "Asset-Upload-Metadata": metadata,
            },
            content=content,
        )
    if resp.status_code >= 400:
        raise CanvaError(f"Asset-Upload fehlgeschlagen ({resp.status_code}): {resp.text[:300]}")
    job_id = resp.json()["job"]["id"]

    for _ in range(30):
        status = await _request("GET", f"/asset-uploads/{job_id}", token)
        job = status["job"]
        if job["status"] == "success":
            return job["asset"]["id"]
        if job["status"] == "failed":
            raise CanvaError(f"Asset-Upload fehlgeschlagen: {job.get('error')}")
        await asyncio.sleep(2)
    raise CanvaError("Asset-Upload Timeout")


async def create_autofill_design(client_id: str, client_secret: str, brand_template_id: str, title: str, data: dict) -> dict:
    """data maps field name -> {"type": "text", "text": "..."} or {"type": "image", "asset_id": "..."}.
    Returns {"id": design_id, "edit_url": ..., "thumbnail_url": ...}."""
    token = await get_access_token(client_id, client_secret)
    resp = await _request(
        "POST", "/autofills", token,
        json={"brand_template_id": brand_template_id, "title": title, "data": data},
    )
    job_id = resp["job"]["id"]

    for _ in range(30):
        status = await _request("GET", f"/autofills/{job_id}", token)
        job = status["job"]
        if job["status"] == "success":
            design = job["result"]["design"]
            design_id = design["id"]
            thumb = (design.get("thumbnail") or {}).get("url", "")
            return {
                "id": design_id,
                "edit_url": f"https://www.canva.com/design/{design_id}/edit",
                "thumbnail_url": thumb,
            }
        if job["status"] == "failed":
            raise CanvaError(f"Autofill fehlgeschlagen: {job.get('error')}")
        await asyncio.sleep(2)
    raise CanvaError("Autofill Timeout")


async def create_export(client_id: str, client_secret: str, design_id: str, file_format: str = "png") -> str:
    """Exportiert ein Design und gibt eine (zeitlich begrenzte) Download-URL zurueck."""
    token = await get_access_token(client_id, client_secret)
    resp = await _request(
        "POST", "/exports", token,
        json={"design_id": design_id, "format": {"type": file_format}},
    )
    job_id = resp["job"]["id"]

    for _ in range(30):
        status = await _request("GET", f"/exports/{job_id}", token)
        job = status["job"]
        if job["status"] == "success":
            urls = job.get("urls") or []
            if not urls:
                raise CanvaError("Export lieferte keine Download-URL")
            return urls[0]
        if job["status"] == "failed":
            raise CanvaError(f"Export fehlgeschlagen: {job.get('error')}")
        await asyncio.sleep(2)
    raise CanvaError("Export Timeout")
