"""Fail-closed authorization boundary for a future hosted workspace MCP server.

Identity links and consent grants must be created only after both accounts have
been authenticated. This module does not create links or expose an endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import jwt


@dataclass(frozen=True)
class WorkspaceGrant:
    """A previously consented link for one provider user, client and workspace."""

    issuer: str
    subject: str
    client_id: str
    user_id: int
    workspace_id: int
    permissions: frozenset[str]
    active: bool = True


@dataclass(frozen=True)
class WorkspacePrincipal:
    user_id: int
    workspace_id: int
    client_id: str


class WorkspaceTokenVerifier:
    """Verify asymmetric OAuth access tokens and resolve an explicit workspace grant.

    ``signing_key`` must resolve a key from the configured issuer's trusted
    JWKS, never from a URL supplied by the token. ``find_grant`` looks up the
    exact issuer, subject, client and workspace; ``is_member`` checks current
    membership in the platform's authoritative store on every operation.
    """

    def __init__(self, *, issuer: str, audience: str, signing_key: Callable, find_grant: Callable, is_member: Callable):
        if not issuer.startswith("https://") or not audience.startswith("https://"):
            raise ValueError("Issuer and resource audience must use HTTPS.")
        self.issuer = issuer
        self.audience = audience
        self.signing_key = signing_key
        self.find_grant = find_grant
        self.is_member = is_member

    def authenticate(self, token: str) -> dict:
        """Validate the signed resource token without authorizing a workspace."""
        if not token:
            raise PermissionError("Invalid authorization.")
        try:
            key = self.signing_key(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256", "ES256"],
                issuer=self.issuer,
                audience=self.audience,
                options={"require": ["iss", "sub", "aud", "exp", "iat", "client_id"]},
            )
        except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
            raise PermissionError("Invalid or expired authorization.") from exc
        subject, client = claims.get("sub"), claims.get("client_id")
        if not isinstance(subject, str) or not subject or not isinstance(client, str) or not client:
            raise PermissionError("Invalid or expired authorization.")
        return claims

    def authorize(self, token: str, workspace_id: int, permission: str) -> WorkspacePrincipal:
        """Return the scoped principal, or reject without exposing token details."""
        if not isinstance(workspace_id, int) or workspace_id <= 0 or not permission:
            raise PermissionError("Invalid authorization.")
        claims = self.authenticate(token)
        subject, client = claims["sub"], claims["client_id"]
        grant = self.find_grant(self.issuer, subject, client, workspace_id)
        if (
            not isinstance(grant, WorkspaceGrant)
            or not grant.active
            or (grant.issuer, grant.subject, grant.client_id, grant.workspace_id)
            != (self.issuer, subject, client, workspace_id)
            or permission not in grant.permissions
            or not self.is_member(grant.user_id, workspace_id)
        ):
            raise PermissionError("Workspace access not authorized.")
        return WorkspacePrincipal(user_id=grant.user_id, workspace_id=workspace_id, client_id=client)
