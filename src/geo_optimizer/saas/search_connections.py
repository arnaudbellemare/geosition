"""Read-only OAuth connections and daily first-party search synchronization."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken

from geo_optimizer.core.search_measurement import fetch_search_measurement, validate_property

_PROVIDERS = {
    "google": {
        "authorize": "https://accounts.google.com/o/oauth2/v2/auth",
        "token": "https://oauth2.googleapis.com/token",
        "sites": "https://www.googleapis.com/webmasters/v3/sites",
        "scope": "https://www.googleapis.com/auth/webmasters.readonly",
    },
    "bing": {
        "authorize": "https://www.bing.com/webmasters/oauth/authorize",
        "token": "https://www.bing.com/webmasters/oauth/token",
        "sites": "https://ssl.bing.com/webmaster/api.svc/json/GetUserSites",
        "scope": "webmaster.read",
    },
}


def _config(provider: str) -> tuple[dict, str, str, str, Fernet]:
    if provider not in _PROVIDERS:
        raise ValueError("Unsupported search provider.")
    prefix = f"GEOSITION_{provider.upper()}_OAUTH_"
    client_id, client_secret = os.getenv(prefix + "CLIENT_ID", ""), os.getenv(prefix + "CLIENT_SECRET", "")
    base = os.getenv("GEOSITION_PUBLIC_BASE_URL", "").rstrip("/")
    key = os.getenv("GEOSITION_OAUTH_ENCRYPTION_KEY", "")
    if not all((client_id, client_secret, key, base)) or not base.startswith("https://"):
        raise ValueError("Search connection is not configured. Ask your administrator to finish OAuth setup.")
    try:
        cipher = Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise ValueError("Search connection encryption is not configured correctly.") from exc
    return _PROVIDERS[provider], client_id, client_secret, base, cipher


def begin_connection(provider: str, domain: str, session: str) -> tuple[str, str]:
    config, client_id, _, base, cipher = _config(provider)
    payload = {
        "provider": provider,
        "domain": domain,
        "session": hashlib.sha256(session.encode()).hexdigest(),
        "nonce": secrets.token_urlsafe(32),
    }
    state = cipher.encrypt(json.dumps(payload).encode()).decode()
    params = {
        "client_id": client_id,
        "redirect_uri": base + "/api/v1/search-connections/callback/" + provider,
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
    }
    if provider == "google":
        params.update({"access_type": "offline", "prompt": "consent"})
    return config["authorize"] + "?" + urlencode(params), state


def verify_state(provider: str, state: str, cookie: str, session: str) -> dict:
    _, _, _, _, cipher = _config(provider)
    if not state or not cookie or not secrets.compare_digest(state, cookie):
        raise ValueError("The connection request expired. Please try again.")
    try:
        data = json.loads(cipher.decrypt(state.encode(), ttl=600))
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise ValueError("The connection request expired. Please try again.") from exc
    if not isinstance(data, dict):
        raise ValueError("The connection request is invalid. Please try again.")
    if data.get("provider") != provider or not secrets.compare_digest(
        str(data.get("session", "")), hashlib.sha256(session.encode()).hexdigest()
    ):
        raise ValueError("The connection request does not match this session.")
    return data


def _provider_json(method: str, url: str, **kwargs) -> dict:
    try:
        with requests.request(method, url, timeout=15, allow_redirects=False, stream=True, **kwargs) as response:
            if response.status_code != 200:
                raise ValueError("The provider could not complete the request. Check access and try reconnecting.")
            content = bytearray()
            for chunk in response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 2 * 1024 * 1024:
                    raise ValueError("The provider response was too large.")
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("The provider returned an unexpected response.")
        return data
    except (requests.RequestException, json.JSONDecodeError, UnicodeError) as exc:
        raise ValueError("The provider could not be reached. Try again later.") from exc


def exchange_code(provider: str, code: str) -> dict:
    config, client_id, secret, base, _ = _config(provider)
    return _provider_json(
        "POST",
        config["token"],
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": secret,
            "redirect_uri": base + "/api/v1/search-connections/callback/" + provider,
        },
    )


def select_property(provider: str, domain: str, access_token: str) -> str:
    config, _, _, _, _ = _config(provider)
    payload = _provider_json("GET", config["sites"], headers={"Authorization": f"Bearer {access_token}"})
    rows = payload.get("siteEntry", []) if provider == "google" else payload.get("d", [])
    if not isinstance(rows, list):
        raise ValueError("The provider returned an unexpected property list.")
    candidates = []
    for row in rows:
        if not isinstance(row, dict) or row.get("permissionLevel") == "siteUnverifiedUser":
            continue
        if provider == "bing" and not row.get("IsVerified"):
            continue
        prop = row.get("siteUrl" if provider == "google" else "Url", "")
        if not isinstance(prop, str):
            continue
        try:
            validate_property(provider, prop, domain)
        except ValueError:
            continue
        candidates.append(prop)
    if not candidates:
        raise ValueError("No matching verified property was found in that provider account.")
    # Domain properties cover all paths; otherwise choose the broadest URL prefix.
    return sorted(candidates, key=lambda prop: (not prop.startswith("sc-domain:"), len(prop)))[0]


def save_connection(store, org_id: int, domain: str, provider: str, tokens: dict) -> None:
    _, _, _, _, cipher = _config(provider)
    access, refresh = tokens.get("access_token"), tokens.get("refresh_token")
    if not isinstance(access, str) or not isinstance(refresh, str) or not access or not refresh:
        raise ValueError("The provider did not grant offline access. Please reconnect and approve access.")
    prop = select_property(provider, domain, access)
    store.save_search_connection(org_id, domain, provider, prop, cipher.encrypt(refresh.encode()).decode())


def sync_connection(store, row: dict) -> None:
    provider = row["provider"]
    config, client_id, secret, _, cipher = _config(provider)
    refresh = cipher.decrypt(row["encrypted_refresh_token"].encode()).decode()
    tokens = _provider_json(
        "POST",
        config["token"],
        data={"grant_type": "refresh_token", "refresh_token": refresh, "client_id": client_id, "client_secret": secret},
    )
    access = tokens.get("access_token")
    if not isinstance(access, str) or not access:
        raise ValueError("Provider access expired; reconnect the account.")
    rotated = tokens.get("refresh_token") or refresh
    encrypted = cipher.encrypt(rotated.encode()).decode()
    now = datetime.now(timezone.utc)
    values = {
        "status": "connected",
        "last_synced_at": now.isoformat(),
        "last_result_json": row.get("last_result_json") or "{}",
        "encrypted_refresh_token": encrypted,
    }
    # Save rotated refresh tokens even when the subsequent analytics request fails.
    store.update_search_connection(row["org_id"], row["domain"], provider, values)
    try:
        result = fetch_search_measurement(
            provider, row["property_id"], access, (now.date() - timedelta(days=30)).isoformat(), now.date().isoformat()
        )
        values["last_result_json"] = json.dumps(result)
    except ValueError:
        values["status"] = "sync_error"
        store.update_search_connection(row["org_id"], row["domain"], provider, values)
        raise
    store.update_search_connection(row["org_id"], row["domain"], provider, values)
