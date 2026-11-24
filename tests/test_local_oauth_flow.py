from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

jwt = pytest.importorskip('jwt')
pytest.importorskip('mcp')

from geo_optimizer.mcp.hosted_workspace import create_hosted_workspace_server
from geo_optimizer.mcp.oauth_consent import decide, preview
from geo_optimizer.mcp.oauth_identity import WorkspaceTokenVerifier
from geo_optimizer.mcp.sqlite_oauth_grants import SqliteOAuthGrants
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore


class FakeProvider:
    issuer = 'https://auth.example.test'

    def __init__(self, index):
        self.index = index

    def get_user(self, session):
        return {'id': 'subject-%s' % self.index}

    def get_authorization_details(self, session, authorization_id):
        return {'authorization_id': authorization_id, 'user': self.get_user(session),
                'client': {'id': 'client-%s' % self.index, 'name': 'AI'},
                'redirect_uri': 'https://client.example.test/callback', 'scope': 'openid'}

    def decide(self, session, authorization_id, decision):
        return {'redirect_url': 'https://client.example.test/callback?code=demo'}


def test_consent_to_hosted_mcp_for_both_pilots(tmp_path):
    store = PlatformStore(tmp_path / 'flow.db')
    service, grants = PlatformService(store), SqliteOAuthGrants(store)
    pilots = []
    for index, (name, domain) in enumerate([('Mom’s Art Shop', 'www.robel-art.com'),
                                            ('Gestion Velora', 'www.gestionvelora.com')]):
        account = service.register(email='owner%d@example.test' % index, password='password123', org_name=name)
        domain_row = service.add_website_domain(account['session']['token'], domain)['domain']
        store.mark_domain_verified(domain_row['domain_id'], method='test')
        provider = FakeProvider(index)
        geo_token = account['session']['token']
        review = preview(service, geo_token, provider, 'provider-session', 'auth-1')
        decide(service, geo_token, provider, 'provider-session', 'auth-1', reviewed=review,
               permissions=['setup:read'], decision='approve', save_grant=grants.save)
        pilots.append((account['organization']['org_id'], domain, review))
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    audience = 'https://geosition.example.test/mcp'
    verifier = WorkspaceTokenVerifier(issuer=FakeProvider.issuer, audience=audience,
        signing_key=lambda _: private.public_key(), find_grant=grants.find,
        is_member=lambda user, workspace: store.get_member_org(user, workspace) is not None)
    app = create_hosted_workspace_server(service, verifier).streamable_http_app()
    now = datetime.now(timezone.utc)
    with TestClient(app, base_url='https://geosition.example.test') as client:
        for index, (workspace, domain, review) in enumerate(pilots):
            bearer = jwt.encode({'iss': FakeProvider.issuer, 'aud': audience, 'sub': review['provider_subject'],
                                 'client_id': review['client_id'], 'iat': now, 'exp': now + timedelta(minutes=5)},
                                private, algorithm='RS256')
            def call(target_workspace, target_domain):
                return client.post('/mcp', headers={'Authorization': 'Bearer ' + bearer,
                    'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'},
                    json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call', 'params': {
                        'name': 'geosition_setup_status', 'arguments': {
                            'workspace_id': target_workspace, 'domain': target_domain}}}).json()['result']
            assert json.loads(call(workspace, domain)['content'][0]['text'])['setup']['domain'] == domain
            other = pilots[1-index]
            assert call(other[0], other[1])['isError']
            assert grants.revoke(FakeProvider.issuer, review['provider_subject'], review['client_id'],
                                 workspace, review['user_id'])
            assert call(workspace, domain)['isError']
