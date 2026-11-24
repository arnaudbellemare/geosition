from __future__ import annotations

from unittest.mock import Mock

import pytest

pytest.importorskip('jwt')

from geo_optimizer.mcp.oauth_identity import WorkspaceGrant
from geo_optimizer.mcp.supabase_oauth_grants import SupabaseOAuthGrants


def test_supabase_grant_storage_scopes_reads_and_revocations():
    store = Mock()
    grants = SupabaseOAuthGrants(store)
    grant = WorkspaceGrant('https://issuer.example', 'subject', 'client', 1, 2, frozenset({'setup:read'}))
    grants.save(grant)
    method, table = store._request.call_args.args
    assert (method, table) == ('POST', 'geo_mcp_workspace_grants')
    assert store._request.call_args.kwargs['json_body']['permissions'] == ['setup:read']
    store._request.return_value = [{'issuer': grant.issuer, 'subject': grant.subject,
        'client_id': grant.client_id, 'user_id': grant.user_id, 'workspace_id': grant.workspace_id,
        'permissions': ['setup:read'], 'active': True}]
    assert grants.find(grant.issuer, grant.subject, grant.client_id, 2) == grant
    assert store._request.call_args.kwargs['params']['workspace_id'] == 'eq.2'
    assert grants.revoke(grant.issuer, grant.subject, grant.client_id, 2, 1)
    assert store._request.call_args.kwargs['params']['user_id'] == 'eq.1'
    assert store._request.call_args.kwargs['params']['workspace_id'] == 'eq.2'
    with pytest.raises(ValueError):
        grants.save(WorkspaceGrant(grant.issuer, grant.subject, grant.client_id, 1, 2, frozenset({'admin'})))
