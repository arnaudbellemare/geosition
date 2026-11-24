from __future__ import annotations

from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

pytest.importorskip('jwt')

from geo_optimizer.mcp.consent_routes import create_consent_router
from geo_optimizer.mcp.sqlite_oauth_grants import SqliteOAuthGrants
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore


class Provider:
    issuer = 'https://issuer.example.test'

    def sign_in(self, email, password):
        assert email == 'owner@example.test' and password == 'provider-password'
        return 'provider-secret-token'

    def get_user(self, token):
        assert token == 'provider-secret-token'
        return {'id': 'subject-1'}

    def get_authorization_details(self, token, authorization_id):
        return {'authorization_id': authorization_id, 'user': {'id': 'subject-1'},
                'client': {'id': 'client-1', 'name': 'Example AI'},
                'redirect_uri': 'https://ai.example.test/callback', 'scope': 'openid'}

    def decide(self, token, authorization_id, decision):
        return {'redirect_url': 'https://ai.example.test/callback?code=temporary-code'}


def test_browser_consent_requires_both_sessions_csrf_and_review(tmp_path):
    store = PlatformStore(tmp_path / 'platform.db')
    service = PlatformService(store)
    mom = service.register(email='mom@example.test', password='password123', org_name='Mom’s Art Shop')
    other = service.register(email='other@example.test', password='password123', org_name='Gestion Velora')
    grants = SqliteOAuthGrants(store)
    app = FastAPI()
    app.include_router(create_consent_router(service, Provider(), grants, Fernet(Fernet.generate_key())))
    client = TestClient(app, base_url='https://geosition.example.test')
    path = '/api/v1/mcp/consent/'
    page = client.get('/oauth/consent?authorization_id=auth-1')
    assert page.status_code == 200
    assert 'Connect your workspace' in page.text
    assert page.headers['cache-control'] == 'no-store'
    assert client.get('/platform/assets/mcp-consent.js').status_code == 200
    client.cookies.set('geo_session', mom['session']['token'])
    client.cookies.set('geo_csrf', 'csrf-value')
    credentials = {'email': 'owner@example.test', 'password': 'provider-password'}
    assert client.post(path + 'provider-login', json=credentials).status_code == 403
    headers = {'x-csrf-token': 'csrf-value'}
    signed_in = client.post(path + 'provider-login', json=credentials, headers=headers)
    assert signed_in.status_code == 200
    assert 'provider-secret-token' not in signed_in.text
    assert 'httponly' in signed_in.headers['set-cookie'].lower()
    assert client.post(path + 'decision', json={'decision': 'approve', 'permissions': ['setup:read']},
                       headers=headers).status_code == 400
    review = client.post(path + 'review', json={'authorization_id': 'auth-1'}, headers=headers)
    assert review.json()['workspace_name'] == 'Mom’s Art Shop'
    assert review.json()['client_name'] == 'Example AI'
    client.cookies.set('geo_session', other['session']['token'])
    assert client.post(path + 'decision', json={'decision': 'approve', 'permissions': ['setup:read']},
                       headers=headers).status_code == 400
    client.cookies.set('geo_session', mom['session']['token'])
    approved = client.post(path + 'decision', json={'decision': 'approve', 'permissions': ['setup:read']},
                           headers=headers)
    assert approved.status_code == 200
    assert grants.find(Provider.issuer, 'subject-1', 'client-1', mom['organization']['org_id']).active
