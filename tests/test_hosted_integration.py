from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

jwt = pytest.importorskip('jwt')
pytest.importorskip('mcp')

from geo_optimizer.mcp.hosted_integration import install_hosted_integration
from geo_optimizer.mcp.oauth_identity import WorkspaceTokenVerifier
from geo_optimizer.mcp.sqlite_oauth_grants import SqliteOAuthGrants
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore


class Provider:
    issuer = 'https://issuer.example.test'

    def sign_in(self, email, password):
        return email

    def get_user(self, token):
        return {'id': token}

    def get_authorization_details(self, token, authorization_id):
        return {'authorization_id': authorization_id, 'user': {'id': token},
                'client': {'id': 'client-' + token, 'name': 'Example AI'},
                'redirect_uri': 'https://client.example.test/callback', 'scope': 'openid'}

    def decide(self, token, authorization_id, decision):
        return {'redirect_url': 'https://client.example.test/callback?code=test'}


def test_browser_consent_and_mcp_share_workspace_grants(tmp_path):
    store = PlatformStore(tmp_path / 'platform.db')
    service, grants = PlatformService(store), SqliteOAuthGrants(store)
    pilots = []
    for index, (name, domain) in enumerate([('Mom’s Art Shop', 'www.robel-art.com'),
                                            ('Gestion Velora', 'www.gestionvelora.com')]):
        account = service.register(email='owner%d@example.test' % index, password='password123', org_name=name)
        domain_row = service.add_website_domain(account['session']['token'], domain)['domain']
        store.mark_domain_verified(domain_row['domain_id'], method='test')
        pilots.append((account, domain))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    audience = 'https://geosition.example.test/mcp'
    verifier = WorkspaceTokenVerifier(issuer=Provider.issuer, audience=audience,
        signing_key=lambda _: key.public_key(), find_grant=grants.find,
        is_member=lambda user, org: store.get_member_org(user, org) is not None)
    app = FastAPI()
    @app.get('/existing')
    def existing():
        return {'still_available': True}
    install_hosted_integration(app, service=service, provider=Provider(), grants=grants,
                               cipher=Fernet(Fernet.generate_key()), verifier=verifier)
    now = datetime.now(timezone.utc)
    with TestClient(app, base_url='https://geosition.example.test') as client:
        assert client.get('/existing').json()['still_available']
        assert client.get('/oauth/consent?authorization_id=auth-1').status_code == 200
        for index, (account, domain) in enumerate(pilots):
            client.cookies.set('geo_session', account['session']['token'])
            client.cookies.set('geo_csrf', 'csrf-value')
            headers = {'x-csrf-token': 'csrf-value'}
            path = '/api/v1/mcp/consent/'
            assert client.post(path + 'provider-login', headers=headers,
                               json={'email': 'subject-%d' % index, 'password': 'test'}).status_code == 200
            review = client.post(path + 'review', headers=headers, json={'authorization_id': 'auth-1'})
            assert review.json()['workspace_name'] == account['organization']['name']
            assert client.post(path + 'decision', headers=headers,
                               json={'decision': 'approve', 'permissions': ['setup:read']}).status_code == 200
            bearer = jwt.encode({'iss': Provider.issuer, 'aud': audience, 'sub': 'subject-%d' % index,
                                 'client_id': 'client-subject-%d' % index, 'iat': now,
                                 'exp': now + timedelta(minutes=5)}, key, algorithm='RS256')
            def call(workspace, url):
                return client.post('/mcp', headers={'Authorization': 'Bearer ' + bearer,
                    'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'},
                    json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
                        'name': 'geosition_setup_status', 'arguments': {
                            'workspace_id': workspace, 'domain': url}}}).json()['result']
            own = call(account['organization']['org_id'], domain)
            assert json.loads(own['content'][0]['text'])['setup']['domain'] == domain
            other, other_domain = pilots[1-index]
            assert call(other['organization']['org_id'], other_domain)['isError']
