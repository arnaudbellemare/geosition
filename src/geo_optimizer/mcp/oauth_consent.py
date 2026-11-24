"""Account-link and workspace consent logic for hosted MCP connections.

The provider adapter must authenticate the supplied provider session and fetch
authorization details directly from the provider, not from browser input. This
service is not an HTTP route and does not expose a consent page by itself.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from geo_optimizer.mcp.oauth_identity import WorkspaceGrant

_PERMISSIONS = frozenset({"setup:read", "setup:write"})


def _provider_request(provider, provider_session, authorization_id):
    if not authorization_id or not provider_session:
        raise ValueError("The authorization request is unavailable.")
    identity = provider.get_user(provider_session)
    details = provider.get_authorization_details(provider_session, authorization_id)
    if not isinstance(identity, dict) or not isinstance(details, dict):
        raise ValueError("The authorization request is unavailable.")
    subject = identity.get("id")
    request_user = details.get("user") or {}
    client = details.get("client") or {}
    if (
        not isinstance(subject, str)
        or not subject
        or request_user.get("id") != subject
        or details.get("authorization_id") != authorization_id
        or not isinstance(client.get("id"), str)
        or not client["id"]
        or not isinstance(details.get("redirect_uri"), str)
        or not details["redirect_uri"]
    ):
        raise ValueError("The authorization request is unavailable or already completed.")
    return subject, details


def preview(service, geo_session, provider, provider_session, authorization_id):
    """Display provider-verified client details and the active GEOSITION workspace."""
    user, workspace = service.require_session(geo_session)
    subject, details = _provider_request(provider, provider_session, authorization_id)
    return {
        "workspace_id": workspace.org_id,
        "workspace_name": workspace.name,
        "user_id": user.user_id,
        "provider_subject": subject,
        "client_id": details["client"]["id"],
        "client_name": details["client"].get("name") or "Unnamed application",
        "redirect_uri": details["redirect_uri"],
        "provider_scopes": details.get("scope") or "",
        "available_permissions": sorted(_PERMISSIONS),
    }


def _safe_redirect(registered_uri, result_uri):
    registered, result = urlsplit(registered_uri), urlsplit(result_uri)
    if (
        registered.scheme != "https"
        or not registered.hostname
        or registered.username
        or registered.password
        or result.scheme != registered.scheme
        or result.netloc != registered.netloc
        or result.path != registered.path
        or result.fragment
    ):
        raise ValueError("The provider returned an unexpected redirect.")
    return result_uri


def decide(
    service, geo_session, provider, provider_session, authorization_id, *, reviewed, permissions, decision, save_grant
):
    """Approve or deny one provider request after both accounts authenticate.

    The web caller must protect this operation from CSRF, obtain the user's
    explicit decision and supply the preview from integrity-protected server
    state. It must not trust a preview sent by the browser without a signature.
    """
    if decision not in ("approve", "deny"):
        raise ValueError("Choose whether to approve or deny the request.")
    user, workspace = service.require_session(geo_session)
    subject, details = _provider_request(provider, provider_session, authorization_id)
    current = {
        "workspace_id": workspace.org_id,
        "workspace_name": workspace.name,
        "user_id": user.user_id,
        "provider_subject": subject,
        "client_id": details["client"]["id"],
        "client_name": details["client"].get("name") or "Unnamed application",
        "redirect_uri": details["redirect_uri"],
        "provider_scopes": details.get("scope") or "",
        "available_permissions": sorted(_PERMISSIONS),
    }
    if reviewed != current:
        raise PermissionError("The request changed. Review it again.")
    selected = frozenset(permissions)
    if decision == "approve" and (not selected or not selected <= _PERMISSIONS):
        raise ValueError("Select valid workspace permissions.")
    result = provider.decide(provider_session, authorization_id, decision)
    redirect = _safe_redirect(details["redirect_uri"], result.get("redirect_url", ""))
    if decision == "approve":
        grant = WorkspaceGrant(
            provider.issuer, subject, details["client"]["id"], user.user_id, workspace.org_id, selected
        )
        # If persistence fails, do not return the provider's authorization code.
        save_grant(grant)
    return {"redirect_url": redirect, "decision": decision}
