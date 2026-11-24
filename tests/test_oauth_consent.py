from __future__ import annotations

import pytest

pytest.importorskip('jwt')

from geo_optimizer.mcp.oauth_consent import decide, preview
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore


class Provider:
    issuer = 'https://issuer.example.test/auth/v1'

    def __init__(self):
        self.identity = {'id': 'provider-subject'}
        self.details = {'authorization_id': 'auth-1', 'user': {'id': 'provider-subject'},
                        'client': {'id': 'client-1', 'name': 'Test AI'},
                        'redirect_uri': 'https://client.example.test/callback', 'scope': 'openid'}
        self.redirect = 'https://client.example.test/callback?code=test'
        self.decisions = []

    def get_user(self, token):
        return self.identity if token == 'provider-session' else None

    def get_authorization_details(self, token, auth_id):
        return self.details

    def decide(self, token, auth_id, decision):
        self.decisions.append(decision)
        return {'redirect_url': self.redirect}


def test_consent_binds_both_identities_and_current_workspace(tmp_path):
    service = PlatformService(PlatformStore(tmp_path / 'consent.db'))
    mom = service.register(email='mom@example.test', password='password123', org_name='Mom’s Art Shop')
    velora = service.register(email='velora@example.test', password='password123', org_name='Gestion Velora')
    token = mom['session']['token']
    provider = Provider()
    grants = []
    reviewed = preview(service, token, provider, 'provider-session', 'auth-1')
    assert reviewed['workspace_name'] == 'Mom’s Art Shop'
    outcome = decide(service, token, provider, 'provider-session', 'auth-1', reviewed=reviewed,
                     permissions=['setup:read'], decision='approve', save_grant=grants.append)
    assert outcome['decision'] == 'approve'
    assert grants[0].subject == 'provider-subject'
    assert grants[0].workspace_id == mom['organization']['org_id']
    assert grants[0].user_id == mom['user']['user_id']
    assert grants[0].permissions == frozenset({'setup:read'})
    with pytest.raises(PermissionError):
        decide(service, velora['session']['token'], provider, 'provider-session', 'auth-1', reviewed=reviewed,
               permissions=['setup:read'], decision='approve', save_grant=grants.append)
    provider.details['user']['id'] = 'different-subject'
    with pytest.raises(ValueError):
        preview(service, token, provider, 'provider-session', 'auth-1')
    assert provider.decisions == ['approve']


def test_consent_deny_and_invalid_redirect_never_save_grants(tmp_path):
    service = PlatformService(PlatformStore(tmp_path / 'consent.db'))
    account = service.register(email='mom@example.test', password='password123', org_name='Mom')
    token, provider, grants = account['session']['token'], Provider(), []
    reviewed = preview(service, token, provider, 'provider-session', 'auth-1')
    decide(service, token, provider, 'provider-session', 'auth-1', reviewed=reviewed,
           permissions=[], decision='deny', save_grant=grants.append)
    assert grants == []
    provider.redirect = 'https://attacker.example.test/callback?code=test'
    with pytest.raises(ValueError):
        decide(service, token, provider, 'provider-session', 'auth-1', reviewed=reviewed,
               permissions=['setup:read'], decision='approve', save_grant=grants.append)
    assert grants == []
