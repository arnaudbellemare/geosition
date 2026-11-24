"""Owner consent routes for an Auth0 Post-Login redirect.

This router must only be mounted with a dedicated Auth0 Action secret, an
explicit client allowlist, and the Auth0 Action that validates the return JWT.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from urllib.parse import urlsplit

import jwt
from cryptography.fernet import InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from geo_optimizer.mcp.auth0_context import verify_action_context
from geo_optimizer.mcp.oauth_identity import WorkspaceGrant


class Decision(BaseModel):
    decision: str
    permissions: list[str] = Field(default_factory=list, max_length=2)


def create_auth0_router(service, grants, cipher, *, secret, issuer, resource, clients, html):
    """Create browser routes, with all production dependencies supplied explicitly."""
    parsed = urlsplit(issuer)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.path != "/"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Auth0 issuer must be an HTTPS origin with a trailing slash.")
    if not isinstance(secret, str) or len(secret.encode()) < 32 or not clients:
        raise ValueError("Auth0 linking requires a dedicated secret and approved clients.")
    continue_url = "https://" + parsed.netloc + "/continue"
    router = APIRouter()

    def seal(payload):
        return cipher.encrypt(json.dumps(payload, separators=(",", ":")).encode()).decode()

    def unseal(value):
        try:
            data = json.loads(cipher.decrypt((value or "").encode(), ttl=600))
            if not isinstance(data, dict):
                raise ValueError("Invalid state")
            return data
        except (InvalidToken, ValueError, TypeError, UnicodeError) as exc:
            raise HTTPException(400, "Connection request expired. Start again.") from exc

    def account(request, *, csrf=False):
        token = request.cookies.get("geo_session", "")
        try:
            user, workspace = service.require_session(token)
        except PermissionError as exc:
            raise HTTPException(401, "Sign in to GEOSITION first.") from exc
        if service.store.membership_role(user.user_id, workspace.org_id) != "owner":
            raise HTTPException(403, "A workspace owner must approve this connection.")
        if csrf:
            cookie = request.cookies.get("geo_csrf", "")
            supplied = request.headers.get("x-csrf-token", "")
            if not cookie or not supplied or not secrets.compare_digest(cookie, supplied):
                raise HTTPException(403, "Your session expired. Reload and try again.")
        return token, user, workspace

    @router.get("/oauth/auth0/start")
    def start(state: str, session_token: str):
        if not state or len(state) > 2048:
            raise HTTPException(400, "Invalid connection request.")
        try:
            context = verify_action_context(
                session_token, secret=secret, issuer=parsed.hostname, resource=resource, clients=clients
            )
        except (PermissionError, ValueError) as exc:
            raise HTTPException(400, "Invalid or expired connection request.") from exc
        response = RedirectResponse(
            "/oauth/auth0/consent",
            status_code=303,
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )
        response.set_cookie(
            "geo_auth0_request",
            seal(
                {
                    "state": state,
                    "subject": context.subject,
                    "client_id": context.client_id,
                    "email": context.email,
                    "email_verified": context.email_verified,
                }
            ),
            max_age=600,
            secure=True,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    @router.get("/oauth/auth0/consent")
    def page(request: Request):
        unseal(request.cookies.get("geo_auth0_request"))
        response = HTMLResponse(html, headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})
        response.set_cookie(
            "geo_csrf",
            request.cookies.get("geo_csrf") or secrets.token_urlsafe(24),
            secure=True,
            httponly=False,
            samesite="lax",
            path="/",
        )
        return response

    @router.get("/api/v1/mcp/auth0/review")
    def review(request: Request):
        token, user, workspace = account(request)
        context = unseal(request.cookies.get("geo_auth0_request"))
        client_name = clients.get(context.get("client_id"))
        if not client_name:
            raise HTTPException(403, "This AI service is not approved.")
        reviewed = {
            "user": user.user_id,
            "workspace": workspace.org_id,
            "session": hashlib.sha256(token.encode()).hexdigest(),
            "context": context,
        }
        response = JSONResponse(
            {
                "workspace": workspace.name,
                "client": client_name,
                "identity": context["subject"],
                "email": context.get("email", ""),
                "email_verified": context.get("email_verified", False),
            },
            headers={"Cache-Control": "no-store"},
        )
        response.set_cookie(
            "geo_auth0_review",
            seal(reviewed),
            max_age=600,
            secure=True,
            httponly=True,
            samesite="strict",
            path="/api/v1/mcp/auth0",
        )
        return response

    @router.post("/api/v1/mcp/auth0/decision")
    def decision(body: Decision, request: Request):
        token, user, workspace = account(request, csrf=True)
        context = unseal(request.cookies.get("geo_auth0_request"))
        reviewed = unseal(request.cookies.get("geo_auth0_review"))
        expected = {
            "user": user.user_id,
            "workspace": workspace.org_id,
            "session": hashlib.sha256(token.encode()).hexdigest(),
            "context": context,
        }
        if reviewed != expected or context.get("client_id") not in clients:
            raise HTTPException(403, "The workspace or connection changed. Review it again.")
        permissions = frozenset(body.permissions)
        if body.decision not in ("approve", "deny"):
            raise HTTPException(400, "Choose whether to connect.")
        if body.decision == "approve":
            if not permissions or not permissions <= {"setup:read", "setup:write"}:
                raise HTTPException(400, "Choose valid workspace permissions.")
            grants.save(
                WorkspaceGrant(
                    issuer, context["subject"], context["client_id"], user.user_id, workspace.org_id, permissions
                )
            )
        now = int(time.time())
        result = jwt.encode(
            {
                "iss": resource,
                "sub": context["subject"],
                "state": context["state"],
                "client_id": context["client_id"],
                "resource": resource,
                "decision": body.decision,
                "iat": now,
                "exp": now + 60,
            },
            secret,
            algorithm="HS256",
        )
        response = JSONResponse(
            {"continue_url": continue_url, "state": context["state"], "token": result},
            headers={"Cache-Control": "no-store"},
        )
        response.delete_cookie("geo_auth0_review", path="/api/v1/mcp/auth0")
        response.delete_cookie("geo_auth0_request", path="/")
        return response

    return router
