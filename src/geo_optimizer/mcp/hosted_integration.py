"""Compose the opt-in hosted MCP and browser-consent ASGI routes."""

from __future__ import annotations

from contextlib import asynccontextmanager

from geo_optimizer.mcp.consent_routes import create_consent_router
from geo_optimizer.mcp.hosted_workspace import create_hosted_workspace_server


def install_hosted_integration(app, *, service, provider, grants, cipher, verifier):
    """Attach the consent routes and MCP server to an existing FastAPI app.

    Call only after configuring and verifying the OAuth issuer, resource
    audience, grant store, and cookie encryption. Install after existing app
    routes: the root mount must be the final fallback. This function does not
    activate itself or configure production credentials.
    """
    server = create_hosted_workspace_server(service, verifier)
    mcp_app = server.streamable_http_app()
    previous_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(parent):
        async with previous_lifespan(parent) as state, server.session_manager.run():
            yield state

    app.router.lifespan_context = lifespan
    app.include_router(create_consent_router(service, provider, grants, cipher))
    app.mount("/", mcp_app, name="geosition-mcp")
    return server
