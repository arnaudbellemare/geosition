"""Uninstalled router for browser-based MCP account linking and consent."""

from __future__ import annotations

import hashlib
import json
import secrets
from pathlib import Path

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

from geo_optimizer.mcp import oauth_consent


class ProviderLogin(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=1024)


class ReviewRequest(BaseModel):
    authorization_id: str = Field(max_length=128)


class ConsentDecision(BaseModel):
    decision: str
    permissions: list[str] = Field(default_factory=list, max_length=2)


def create_consent_router(service, provider, grants, cipher):
    """Create routes with explicit dependencies; do not mount without production configuration."""
    router = APIRouter()
    assets = Path(__file__).resolve().parents[1] / "web" / "templates" / "platform" / "assets"

    @router.get("/oauth/consent")
    def consent_page(request: Request):
        response = HTMLResponse(
            (assets / "mcp-consent.html").read_text(encoding="utf-8"),
            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
        )
        response.set_cookie(
            "geo_csrf",
            request.cookies.get("geo_csrf") or secrets.token_urlsafe(24),
            httponly=False,
            secure=True,
            samesite="lax",
            path="/",
        )
        return response

    @router.get("/platform/assets/mcp-consent.js")
    def consent_script():
        return Response(
            (assets / "mcp-consent.js").read_text(encoding="utf-8"),
            media_type="text/javascript",
            headers={"Cache-Control": "no-store"},
        )

    def session(request):
        token = request.cookies.get("geo_session", "")
        if not token:
            raise HTTPException(401, "Sign in to GEOSITION first.")
        try:
            service.require_session(token)
        except PermissionError as exc:
            raise HTTPException(401, "Sign in to GEOSITION first.") from exc
        csrf = request.cookies.get("geo_csrf", "")
        supplied = request.headers.get("x-csrf-token", "")
        if not csrf or not supplied or not secrets.compare_digest(csrf, supplied):
            raise HTTPException(403, "Your session expired. Reload and try again.")
        return token

    def seal(payload, geo_token):
        return cipher.encrypt(
            json.dumps({"session": hashlib.sha256(geo_token.encode()).hexdigest(), "payload": payload}).encode()
        ).decode()

    def unseal(value, geo_token):
        try:
            record = json.loads(cipher.decrypt((value or "").encode(), ttl=600))
            if not secrets.compare_digest(record["session"], hashlib.sha256(geo_token.encode()).hexdigest()):
                raise ValueError("Session mismatch")
            return record["payload"]
        except (InvalidToken, ValueError, KeyError, TypeError, UnicodeError) as exc:
            raise HTTPException(400, "The connection request expired. Start again.") from exc

    def cookie(response, name, value):
        response.set_cookie(
            name, value, max_age=600, path="/api/v1/mcp/consent", httponly=True, secure=True, samesite="strict"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @router.post("/api/v1/mcp/consent/provider-login")
    def provider_login(body: ProviderLogin, request: Request):
        geo_token = session(request)
        try:
            token = provider.sign_in(body.email, body.password)
        except (ValueError, PermissionError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        response = JSONResponse({"signed_in": True})
        response.delete_cookie("geo_mcp_review", path="/api/v1/mcp/consent")
        return cookie(response, "geo_mcp_identity", seal({"token": token}, geo_token))

    @router.post("/api/v1/mcp/consent/review")
    def review(body: ReviewRequest, request: Request):
        geo_token = session(request)
        identity = unseal(request.cookies.get("geo_mcp_identity"), geo_token)
        try:
            result = oauth_consent.preview(service, geo_token, provider, identity["token"], body.authorization_id)
        except (ValueError, PermissionError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        response = JSONResponse(
            {
                "workspace_name": result["workspace_name"],
                "client_name": result["client_name"],
                "redirect_uri": result["redirect_uri"],
                "provider_scopes": result["provider_scopes"],
                "available_permissions": result["available_permissions"],
            }
        )
        return cookie(response, "geo_mcp_review", seal({"review": result, "id": body.authorization_id}, geo_token))

    @router.post("/api/v1/mcp/consent/decision")
    def decision(body: ConsentDecision, request: Request):
        geo_token = session(request)
        identity = unseal(request.cookies.get("geo_mcp_identity"), geo_token)
        reviewed = unseal(request.cookies.get("geo_mcp_review"), geo_token)
        try:
            outcome = oauth_consent.decide(
                service,
                geo_token,
                provider,
                identity["token"],
                reviewed["id"],
                reviewed=reviewed["review"],
                permissions=body.permissions,
                decision=body.decision,
                save_grant=grants.save,
            )
        except (ValueError, PermissionError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        response = JSONResponse(outcome, headers={"Cache-Control": "no-store"})
        response.delete_cookie("geo_mcp_review", path="/api/v1/mcp/consent")
        response.delete_cookie("geo_mcp_identity", path="/api/v1/mcp/consent")
        return response

    return router
