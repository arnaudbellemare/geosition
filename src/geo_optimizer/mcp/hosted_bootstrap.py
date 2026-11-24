"""Build the production MCP integration from explicit server configuration."""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import jwt
from cryptography.fernet import Fernet

from geo_optimizer.mcp.hosted_integration import install_hosted_integration
from geo_optimizer.mcp.oauth_identity import WorkspaceTokenVerifier
from geo_optimizer.mcp.supabase_oauth_grants import SupabaseOAuthGrants
from geo_optimizer.mcp.supabase_oauth_provider import SupabaseOAuthProvider
from geo_optimizer.saas.supabase_store import SupabasePlatformStore


def install_configured_hosted_integration(app, service, *, env=None):
    """Install only when explicitly called with persistent storage and full config.

    The caller must ensure the OAuth provider issues tokens with the exact
    resource audience before enabling this function in production.
    """
    values = os.environ if env is None else env
    project = (values.get("SUPABASE_URL") or values.get("NEXT_PUBLIC_SUPABASE_URL") or "").rstrip("/")
    publishable = values.get("SUPABASE_PUBLISHABLE_KEY") or values.get("NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY") or ""
    origin = (values.get("GEOSITION_PUBLIC_BASE_URL") or "").rstrip("/")
    raw_key = values.get("GEOSITION_OAUTH_ENCRYPTION_KEY") or ""
    if not isinstance(service.store, SupabasePlatformStore):
        raise ValueError("Hosted MCP requires persistent Supabase platform storage.")
    provider = SupabaseOAuthProvider(project, publishable, origin)
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
    try:
        cipher = Fernet(raw_key.encode())
    except (TypeError, ValueError) as exc:
        raise ValueError("Hosted MCP requires a valid encryption key.") from exc
    grants = SupabaseOAuthGrants(service.store)
    keys = jwt.PyJWKClient(provider.issuer + "/.well-known/jwks.json", timeout=10)
    verifier = WorkspaceTokenVerifier(
        issuer=provider.issuer,
        audience=origin + "/mcp",
        signing_key=lambda token: keys.get_signing_key_from_jwt(token).key,
        find_grant=grants.find,
        is_member=lambda user, org: service.store.get_member_org(user, org) is not None,
    )
    return install_hosted_integration(
        app, service=service, provider=provider, grants=grants, cipher=cipher, verifier=verifier
    )
