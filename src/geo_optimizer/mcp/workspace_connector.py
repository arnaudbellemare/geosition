"""Local, session-scoped GEOSITION workspace setup tools.

This server deliberately uses the same hosted API as the platform. It is not a
multi-tenant remote server and must not be exposed directly on the network.
"""

from __future__ import annotations

import json
import os
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("geosition-workspace-setup")
_BASE = "https://www.geositionai.com"


def _request(method: str, path: str, *, params=None, body=None):
    token = os.environ.get("GEOSITION_SESSION_TOKEN", "").strip()
    if not token:
        raise ValueError("No GEOSITION session configured for this local connector.")
    # Never send the session to an arbitrary URL or a redirect.
    url = _BASE + path
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != "www.geositionai.com":
        raise ValueError("Invalid GEOSITION API URL.")
    try:
        response = httpx.request(
            method,
            url,
            headers={"Authorization": "Bearer " + token},
            params=params,
            json=body,
            timeout=120,
            follow_redirects=False,
        )
    except httpx.HTTPError as exc:
        raise RuntimeError("GEOSITION is unavailable; retry later.") from exc
    if response.status_code == 401:
        raise PermissionError("GEOSITION session expired or is invalid; reconnect the account.")
    if response.status_code >= 400 or response.status_code < 200 or response.status_code >= 300:
        raise ValueError(
            f"GEOSITION rejected the request (HTTP {response.status_code:d}). Check workspace and domain access."
        )
    return response.json()


def _scope(workspace_id: int):
    data = _request("GET", "/api/v1/workspaces")
    if data["current_org_id"] != workspace_id:
        raise PermissionError(
            "This session is using another workspace. Reconnect or select the intended workspace first."
        )


@mcp.tool()
def geosition_workspace() -> str:
    """Find the signed-in workspace and its domains before choosing a setup task.

    Returns only workspace names, IDs and domain verification states. Does not
    disclose session credentials or domain verification tokens.
    """
    workspaces = _request("GET", "/api/v1/workspaces")
    dashboard = _request("GET", "/api/v1/dashboard")
    domains = [
        {"domain": d["domain"], "status": d["status"], "domain_id": d["domain_id"]}
        for d in dashboard.get("domains", [])
    ]
    return json.dumps(
        {
            "current_workspace_id": workspaces["current_org_id"],
            "workspaces": workspaces["workspaces"],
            "domains": domains,
        }
    )


@mcp.tool()
def geosition_setup_status(workspace_id: int, domain: str) -> str:
    """Read a verified domain's saved commerce audit, shared progress and Vercel connection status.

    Use the current workspace ID returned by geosition_workspace. A saved Vercel
    connection does not prove live provider access or verified AI browser access.
    """
    _scope(workspace_id)
    setup = _request("GET", "/api/v1/commerce/setup", params={"domain": domain})
    vercel = _request("GET", "/api/v1/commerce/vercel", params={"domain": domain})
    return json.dumps(
        {
            "setup": setup,
            "vercel": vercel,
            "note": "Progress is self-reported. A saved connection does not verify provider or browser access.",
        }
    )


@mcp.tool()
def geosition_run_commerce_audit(workspace_id: int, domain: str) -> str:
    """Audit a verified workspace domain and save the results to shared workspace history.

    The bounded public-site crawl does not make purchases or verify provider access.
    """
    _scope(workspace_id)
    return json.dumps(_request("POST", "/api/v1/commerce/setup/audit", body={"domain": domain}))


@mcp.tool()
def geosition_record_setup_progress(workspace_id: int, domain: str, step: str, status: str) -> str:
    """Record the team's setup progress for a verified domain; this is not provider verification.

    Status must be todo, working, done or blocked. Use only when the user asks
    to record progress or the action is supported by the observed work.
    """
    _scope(workspace_id)
    return json.dumps(
        _request("POST", "/api/v1/commerce/setup/step", body={"domain": domain, "step": step, "status": status})
    )


@mcp.tool()
def geosition_check_domain(workspace_id: int, domain_id: int, method: str = "dns") -> str:
    """Check existing DNS or HTTPS ownership proof for a domain in this workspace.

    Does not create or change DNS records. Successful verification can enable
    configured hosted collection, as in the GEOSITION dashboard.
    """
    if method not in ("dns", "https"):
        raise ValueError("Method must be dns or https.")
    _scope(workspace_id)
    result = _request("POST", f"/api/v1/domains/{domain_id:d}/verify", body={"method": method})
    domain = result.get("domain") or {}
    return json.dumps(
        {
            "verified": result.get("verified"),
            "message": result.get("message"),
            "domain": {k: domain.get(k) for k in ("domain_id", "domain", "status")},
            "collection": result.get("collection"),
        }
    )


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
