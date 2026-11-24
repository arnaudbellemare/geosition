from __future__ import annotations

import sqlite3

import pytest

pytest.importorskip('jwt')

from geo_optimizer.mcp.oauth_identity import WorkspaceGrant
from geo_optimizer.mcp.sqlite_oauth_grants import SqliteOAuthGrants
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore


def test_workspace_grant_persists_and_revocation_is_user_scoped(tmp_path):
    store = PlatformStore(tmp_path / 'platform.db')
    service = PlatformService(store)
    mom = service.register(email='mom@example.test', password='password123', org_name='Mom’s Art Shop')
    velora = service.register(email='velora@example.test', password='password123', org_name='Gestion Velora')
    grants = SqliteOAuthGrants(store)
    user, workspace = mom['user']['user_id'], mom['organization']['org_id']
    grant = WorkspaceGrant('https://issuer.example', 'subject', 'client', user, workspace, frozenset({'setup:read'}))
    grants.save(grant)
    reopened = SqliteOAuthGrants(PlatformStore(tmp_path / 'platform.db'))
    assert reopened.find(grant.issuer, grant.subject, grant.client_id, workspace) == grant
    assert reopened.find(grant.issuer, grant.subject, grant.client_id, velora['organization']['org_id']) is None
    assert not reopened.revoke(grant.issuer, grant.subject, grant.client_id, workspace, velora['user']['user_id'])
    assert reopened.revoke(grant.issuer, grant.subject, grant.client_id, workspace, user)
    assert not reopened.find(grant.issuer, grant.subject, grant.client_id, workspace).active
    with pytest.raises(sqlite3.IntegrityError):
        grants.save(WorkspaceGrant(grant.issuer, 'other', grant.client_id, user,
                                   velora['organization']['org_id'], frozenset({'setup:read'})))
