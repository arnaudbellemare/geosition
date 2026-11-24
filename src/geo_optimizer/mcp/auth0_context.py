"""Validate the signed Auth0 Action context before workspace linking.

This is a verification primitive only; it does not mount an endpoint or grant
access. The Action and the application must share a dedicated signing secret.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import jwt


@dataclass(frozen=True)
class Auth0ActionContext:
    subject: str
    client_id: str
    client_name: str
    email: str = ""
    email_verified: bool = False


def verify_action_context(
    token: str, *, secret: str, issuer: str, resource: str, clients: Mapping[str, str]
) -> Auth0ActionContext:
    """Validate a short-lived, provider-signed linking request for one API."""
    if not secret or not issuer or not resource or not clients:
        raise ValueError("Auth0 linking configuration is incomplete.")
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            issuer=issuer,
            options={"require": ["iss", "sub", "iat", "exp", "client_id", "resource", "purpose"]},
        )
        subject, client = claims["sub"], claims["client_id"]
        if (
            not isinstance(subject, str)
            or not subject
            or not isinstance(client, str)
            or client not in clients
            or not isinstance(clients[client], str)
            or not clients[client]
            or not isinstance(claims.get("email", ""), str)
            or not isinstance(claims.get("email_verified", False), bool)
            or claims["resource"] != resource
            or claims["purpose"] != "workspace-link"
            or not isinstance(claims["iat"], int)
            or not isinstance(claims["exp"], int)
            or claims["exp"] <= claims["iat"]
            or claims["exp"] - claims["iat"] > 120
        ):
            raise ValueError("Invalid context")
    except (jwt.PyJWTError, ValueError, TypeError, KeyError) as exc:
        raise PermissionError("Invalid or expired connection request.") from exc
    return Auth0ActionContext(
        subject, client, clients[client], claims.get("email", ""), claims.get("email_verified", False)
    )
