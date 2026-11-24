"""Workspace-scoped Vercel integration authorization and project binding."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from urllib.parse import quote, urlencode, urlsplit

from cryptography.fernet import Fernet, InvalidToken

from geo_optimizer.saas.search_connections import _provider_json

_CALLBACK = "/api/v1/commerce/vercel/callback"


def _config():
    slug = os.getenv("GEOSITION_VERCEL_INTEGRATION_SLUG", "")
    client = os.getenv("GEOSITION_VERCEL_CLIENT_ID", "")
    secret = os.getenv("GEOSITION_VERCEL_CLIENT_SECRET", "")
    base = os.getenv("GEOSITION_PUBLIC_BASE_URL", "").rstrip("/")
    key = os.getenv("GEOSITION_OAUTH_ENCRYPTION_KEY", "")
    parsed = urlsplit(base)
    if (
        not re.fullmatch(r"[a-z0-9-]{1,32}", slug)
        or not client
        or not secret
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Vercel connection is not configured. Ask your GEOSITION administrator for help.")
    try:
        cipher = Fernet(key.encode())
    except (ValueError, TypeError) as exc:
        raise ValueError("Vercel connection encryption is not configured.") from exc
    return slug, client, secret, base, cipher


def begin_connection(domain, project, org_id, session, team_slug=""):
    slug, _, _, _, cipher = _config()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", project):
        raise ValueError("Enter a valid Vercel project name or ID.")
    data = {
        "domain": domain,
        "project": project,
        "org": org_id,
        "session": hashlib.sha256(session.encode()).hexdigest(),
        "nonce": secrets.token_urlsafe(32),
    }
    state = cipher.encrypt(json.dumps(data).encode()).decode()
    if team_slug:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", team_slug):
            raise ValueError("Enter a valid Vercel team slug.")
        return "https://vercel.com/" + quote(team_slug, safe="") + "/~/integrations/" + slug, state
    return "https://vercel.com/integrations/" + slug + "/new?" + urlencode({"state": state}), state


def verify_state(state, cookie, session, org_id):
    _, _, _, _, cipher = _config()
    if not state or not cookie or not secrets.compare_digest(state, cookie):
        raise ValueError("The Vercel connection request expired. Try again.")
    try:
        data = json.loads(cipher.decrypt(state.encode(), ttl=600))
    except (InvalidToken, ValueError, UnicodeError) as exc:
        raise ValueError("The Vercel connection request expired. Try again.") from exc
    if (
        not isinstance(data, dict)
        or data.get("org") != org_id
        or not secrets.compare_digest(str(data.get("session", "")), hashlib.sha256(session.encode()).hexdigest())
    ):
        raise ValueError("The Vercel connection does not match this workspace and session.")
    return data


def exchange_and_verify(code, domain, project):
    _, client, secret, base, cipher = _config()
    if not code or len(code) > 4096:
        raise ValueError("Vercel did not grant access.")
    tokens = _provider_json(
        "POST",
        "https://api.vercel.com/v2/oauth/access_token",
        data={
            "client_id": client,
            "client_secret": secret,
            "code": code,
            "redirect_uri": base + _CALLBACK,
        },
    )
    access = tokens.get("access_token")
    team_id = tokens.get("team_id")
    if not isinstance(access, str) or not access or (team_id is not None and not isinstance(team_id, str)):
        raise ValueError("Vercel returned an invalid connection.")
    params = {"teamId": team_id} if team_id else {}
    result = _provider_json(
        "GET",
        "https://api.vercel.com/v9/projects/" + quote(project, safe="") + "/domains/" + quote(domain, safe=""),
        params=params,
        headers={"Authorization": "Bearer " + access},
    )
    if (
        not isinstance(result.get("name"), str)
        or result["name"].lower() != domain.lower()
        or result.get("verified") is not True
    ):
        raise ValueError("The selected Vercel project does not have this verified domain.")
    project_id = result.get("projectId")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("Vercel did not identify the project for this domain.")
    return project_id, team_id or "", cipher.encrypt(access.encode()).decode()


def make_dashboard_pending(
    state, session, org_id, domain, project_id, team_id, encrypted_token, next_url, configuration_id
):
    """Seal a dashboard authorization until its signed-in owner confirms it."""
    _, _, _, _, cipher = _config()
    parsed = urlsplit(next_url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "vercel.com"
        or parsed.port is not None
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or not re.fullmatch(r"/[A-Za-z0-9_-]+/~/integrations/icfg_[A-Za-z0-9]+/installed", parsed.path)
        or not re.fullmatch(r"icfg_[A-Za-z0-9]+", configuration_id)
        or parsed.path.split("/")[-2] != configuration_id
    ):
        raise ValueError("Vercel returned an invalid installation completion URL.")
    data = {
        "next_url": next_url,
        "state": state,
        "session": hashlib.sha256(session.encode()).hexdigest(),
        "org": org_id,
        "domain": domain,
        "project_id": project_id,
        "team_id": team_id,
        "encrypted_token": encrypted_token,
    }
    return cipher.encrypt(json.dumps(data).encode()).decode()


def read_dashboard_pending(cookie, session, org_id):
    _, _, _, _, cipher = _config()
    try:
        data = json.loads(cipher.decrypt(cookie.encode(), ttl=600))
    except (InvalidToken, ValueError, UnicodeError, AttributeError) as exc:
        raise ValueError("The pending Vercel connection expired.") from exc
    if (
        not isinstance(data, dict)
        or data.get("org") != org_id
        or not secrets.compare_digest(str(data.get("session", "")), hashlib.sha256(session.encode()).hexdigest())
    ):
        raise ValueError("The pending Vercel connection does not match this session.")
    return data
