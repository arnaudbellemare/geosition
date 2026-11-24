"""Local persistence for explicit workspace OAuth grants."""

from __future__ import annotations

import json

from geo_optimizer.mcp.oauth_identity import WorkspaceGrant


class SqliteOAuthGrants:
    """Store grants in the platform SQLite database, never raw OAuth tokens."""

    def __init__(self, platform_store):
        self.store = platform_store
        with self.store._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS mcp_workspace_grants (
                issuer TEXT NOT NULL,
                subject TEXT NOT NULL,
                client_id TEXT NOT NULL,
                user_id INTEGER NOT NULL,
                workspace_id INTEGER NOT NULL,
                permissions TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (issuer, subject, client_id, workspace_id),
                FOREIGN KEY (user_id, workspace_id) REFERENCES memberships(user_id, org_id) ON DELETE CASCADE
            )""")

    def save(self, grant):
        """Persist the reviewed grant; membership must exist when it is saved."""
        if (
            not isinstance(grant, WorkspaceGrant)
            or not grant.active
            or not grant.permissions
            or not grant.permissions <= {"setup:read", "setup:write"}
        ):
            raise ValueError("An active reviewed workspace grant is required.")
        with self.store._connect() as conn:
            conn.execute(
                """INSERT INTO mcp_workspace_grants
                (issuer, subject, client_id, user_id, workspace_id, permissions, active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(issuer, subject, client_id, workspace_id) DO UPDATE SET
                user_id=excluded.user_id, permissions=excluded.permissions, active=1""",
                (
                    grant.issuer,
                    grant.subject,
                    grant.client_id,
                    grant.user_id,
                    grant.workspace_id,
                    json.dumps(sorted(grant.permissions)),
                ),
            )

    def find(self, issuer, subject, client_id, workspace_id):
        """Find the exact grant for token authorization, including revoked state."""
        with self.store._connect() as conn:
            row = conn.execute(
                """SELECT * FROM mcp_workspace_grants
                WHERE issuer=? AND subject=? AND client_id=? AND workspace_id=?""",
                (issuer, subject, client_id, workspace_id),
            ).fetchone()
        if row is None:
            return None
        return WorkspaceGrant(
            row["issuer"],
            row["subject"],
            row["client_id"],
            row["user_id"],
            row["workspace_id"],
            frozenset(json.loads(row["permissions"])),
            bool(row["active"]),
        )

    def revoke(self, issuer, subject, client_id, workspace_id, user_id):
        """Revoke a user's grant in the specified workspace, returning whether it existed."""
        with self.store._connect() as conn:
            cursor = conn.execute(
                """UPDATE mcp_workspace_grants SET active=0
                WHERE issuer=? AND subject=? AND client_id=? AND workspace_id=? AND user_id=? AND active=1""",
                (issuer, subject, client_id, workspace_id, user_id),
            )
        return cursor.rowcount == 1
