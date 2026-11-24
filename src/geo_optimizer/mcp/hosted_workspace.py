"""Factory for a scoped remote MCP resource server.

This module is not mounted on the production app. Its caller must supply a
trusted issuer verifier and durable, consented workspace grant lookup.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from geo_optimizer.saas import commerce_guided


class _BearerVerifier:
    def __init__(self, verifier):
        self.verifier = verifier

    async def verify_token(self, token: str):
        try:
            claims = self.verifier.authenticate(token)
        except PermissionError:
            return None
        return AccessToken(
            token=token,
            client_id=claims["client_id"],
            subject=claims["sub"],
            scopes=[],
            expires_at=int(claims["exp"]),
            resource=self.verifier.audience,
        )


class _ScopedService:
    """Adapt existing guided operations to an already authorized principal."""

    def __init__(self, service, principal):
        self.service = service
        self.store = service.store
        self.principal = principal

    def require_session(self, unused_token):
        user = self.store.get_user_by_id(self.principal.user_id)
        org = self.store.get_member_org(self.principal.user_id, self.principal.workspace_id)
        if user is None or org is None:
            raise PermissionError("Workspace access not authorized.")
        return user, org

    def _normalize_domain(self, domain):
        return self.service._normalize_domain(domain)

    def _require_verified(self, org_id, domain):
        if org_id != self.principal.workspace_id:
            raise PermissionError("Workspace access not authorized.")
        self.service._require_verified(org_id, domain)


def create_hosted_workspace_server(service, verifier):
    """Create a stateless MCP server; each tool checks an explicit workspace grant."""
    resource = urlsplit(verifier.audience)
    if (
        resource.scheme != "https"
        or not resource.hostname
        or resource.username
        or resource.password
        or resource.path != "/mcp"
        or resource.query
        or resource.fragment
    ):
        raise ValueError("The MCP audience must be an HTTPS /mcp resource URL.")
    origin = resource.scheme + "://" + resource.netloc
    mcp = FastMCP(
        "GEOSITION workspace setup",
        token_verifier=_BearerVerifier(verifier),
        auth=AuthSettings(
            issuer_url=verifier.issuer, resource_server_url=verifier.audience, validate_token_resource=True
        ),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True, allowed_hosts=[resource.netloc], allowed_origins=[origin]
        ),
        stateless_http=True,
        json_response=True,
    )

    def scope(workspace_id, permission):
        access = get_access_token()
        if access is None:
            raise PermissionError("Authentication required.")
        principal = verifier.authorize(access.token, workspace_id, permission)
        return _ScopedService(service, principal)

    @mcp.tool()
    def geosition_setup_status(workspace_id: int, domain: str) -> str:
        """Read saved setup status for a verified domain in an authorized workspace."""
        scoped = scope(workspace_id, "setup:read")
        result = commerce_guided.get_setup(scoped, "", domain)
        row = scoped.store.get_vercel_connection(workspace_id, result["domain"])
        return json.dumps(
            {
                "setup": result,
                "vercel": {"connected": bool(row), "project_id": row["project_id"] if row else None},
                "note": "A saved connection does not verify provider or browser access.",
            }
        )

    @mcp.tool()
    def geosition_run_commerce_audit(workspace_id: int, domain: str) -> str:
        """Audit and save public commerce readiness for an authorized, verified domain."""
        scoped = scope(workspace_id, "setup:write")
        return json.dumps(commerce_guided.run_audit(scoped, "", domain))

    @mcp.tool()
    def geosition_record_setup_progress(workspace_id: int, domain: str, step: str, status: str) -> str:
        """Record team-reported progress; this does not verify an external provider."""
        scoped = scope(workspace_id, "setup:write")
        return json.dumps(commerce_guided.save_step(scoped, "", domain, step, status))

    return mcp
