"""Explicit, fail-closed Auth0 integration for hosted workspace tools."""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

import jwt
from cryptography.fernet import Fernet

from geo_optimizer.mcp.auth0_routes import create_auth0_router
from geo_optimizer.mcp.hosted_workspace import create_hosted_workspace_server
from geo_optimizer.mcp.oauth_identity import WorkspaceTokenVerifier
from geo_optimizer.mcp.supabase_oauth_grants import SupabaseOAuthGrants
from geo_optimizer.saas.supabase_store import SupabasePlatformStore


def install_auth0_integration(app, service, *, env=None):
    """Install Auth0 only with persistent storage and complete explicit configuration."""
    values = os.environ if env is None else env
    if not isinstance(service.store, SupabasePlatformStore):
        raise ValueError("Hosted MCP requires persistent Supabase platform storage.")
    origin = (values.get("GEOSITION_PUBLIC_BASE_URL") or "").rstrip("/")
    parsed = urlsplit(origin)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Hosted MCP requires an HTTPS public origin.")
    issuer = values.get("GEOSITION_AUTH0_ISSUER") or ""
    auth = urlsplit(issuer)
    if (
        auth.scheme != "https"
        or not auth.hostname
        or auth.username
        or auth.password
        or auth.path != "/"
        or auth.query
        or auth.fragment
    ):
        raise ValueError("Auth0 issuer must be an HTTPS origin with a trailing slash.")
    try:
        clients = json.loads(values.get("GEOSITION_AUTH0_CLIENTS") or "")
        cipher = Fernet((values.get("GEOSITION_OAUTH_ENCRYPTION_KEY") or "").encode())
    except (ValueError, TypeError) as exc:
        raise ValueError("Auth0 client allowlist and encryption key are required.") from exc
    if (
        not isinstance(clients, dict)
        or not clients
        or any(not isinstance(k, str) or not k or not isinstance(v, str) or not v for k, v in clients.items())
    ):
        raise ValueError("Auth0 client allowlist must map client IDs to display names.")
    secret = values.get("GEOSITION_AUTH0_ACTION_SECRET") or ""
    resource = origin + "/mcp"
    grants = SupabaseOAuthGrants(service.store)
    keys = jwt.PyJWKClient(issuer + ".well-known/jwks.json", timeout=10)
    verifier = WorkspaceTokenVerifier(
        issuer=issuer,
        audience=resource,
        signing_key=lambda token: keys.get_signing_key_from_jwt(token).key,
        find_grant=grants.find,
        is_member=lambda user, workspace: service.store.get_member_org(user, workspace) is not None,
    )
    assets = Path(__file__).resolve().parents[1] / "web" / "templates" / "platform" / "assets"
    router = create_auth0_router(
        service,
        grants,
        cipher,
        secret=secret,
        issuer=issuer,
        resource=resource,
        clients=clients,
        html=(assets / "auth0-consent.html").read_text(encoding="utf-8"),
    )
    server = create_hosted_workspace_server(service, verifier)
    mcp_app = server.streamable_http_app()
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(parent):
        async with previous(parent) as state, server.session_manager.run():
            yield state

    app.router.lifespan_context = lifespan
    app.include_router(router)
    app.mount("/", mcp_app, name="geosition-mcp")
    return server
