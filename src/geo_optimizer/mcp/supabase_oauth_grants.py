"""Supabase-backed persistence for approved workspace MCP grants."""

from __future__ import annotations

from geo_optimizer.mcp.oauth_identity import WorkspaceGrant

_TABLE = "geo_mcp_workspace_grants"


class SupabaseOAuthGrants:
    """Use the platform's server-only Supabase store; never store OAuth tokens."""

    def __init__(self, platform_store):
        self.store = platform_store

    def save(self, grant):
        if (
            not isinstance(grant, WorkspaceGrant)
            or not grant.active
            or not grant.permissions
            or not grant.permissions <= {"setup:read", "setup:write"}
        ):
            raise ValueError("An active reviewed workspace grant is required.")
        self.store._request(
            "POST",
            _TABLE,
            params={"on_conflict": "issuer,subject,client_id,workspace_id"},
            json_body={
                "issuer": grant.issuer,
                "subject": grant.subject,
                "client_id": grant.client_id,
                "user_id": grant.user_id,
                "workspace_id": grant.workspace_id,
                "permissions": sorted(grant.permissions),
                "active": True,
            },
            prefer="resolution=merge-duplicates,return=minimal",
        )

    def find(self, issuer, subject, client_id, workspace_id):
        rows = self.store._request(
            "GET",
            _TABLE,
            params={
                "issuer": "eq." + issuer,
                "subject": "eq." + subject,
                "client_id": "eq." + client_id,
                "workspace_id": "eq." + str(workspace_id),
                "select": "*",
                "limit": "1",
            },
        )
        if not rows:
            return None
        row = rows[0]
        return WorkspaceGrant(
            row["issuer"],
            row["subject"],
            row["client_id"],
            row["user_id"],
            row["workspace_id"],
            frozenset(row["permissions"]),
            row["active"],
        )

    def revoke(self, issuer, subject, client_id, workspace_id, user_id):
        rows = self.store._request(
            "PATCH",
            _TABLE,
            params={
                "issuer": "eq." + issuer,
                "subject": "eq." + subject,
                "client_id": "eq." + client_id,
                "workspace_id": "eq." + str(workspace_id),
                "user_id": "eq." + str(user_id),
                "active": "eq.true",
            },
            json_body={"active": False},
        )
        return len(rows) == 1
