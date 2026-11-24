from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

jwt = pytest.importorskip('jwt')
pytest.importorskip('mcp')

from geo_optimizer.mcp.hosted_workspace import create_hosted_workspace_server
from geo_optimizer.mcp.oauth_identity import WorkspaceGrant, WorkspaceTokenVerifier
from geo_optimizer.models.results.commerce_site import CommerceSiteReport
from geo_optimizer.saas import commerce_guided
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore


def test_hosted_mcp_enforces_grants_for_both_pilots(tmp_path, monkeypatch):
    service = PlatformService(PlatformStore(tmp_path / 'hosted.db'))
    pilots = []
    for email, name, domain in [('mom@example.test', 'Mom’s Art Shop', 'www.robel-art.com'),
                                ('velora@example.test', 'Gestion Velora', 'www.gestionvelora.com')]:
        account = service.register(email=email, password='password123', org_name=name)
        row = service.add_website_domain(account['session']['token'], domain)['domain']
        service.store.mark_domain_verified(row['domain_id'], method='test')
        pilots.append((account['user']['user_id'], account['organization']['org_id'], domain))
    monkeypatch.setattr(commerce_guided, 'run_site_audit',
                        lambda url, max_pages, render: CommerceSiteReport(
                            url=url, coverage={'pages_audited': 1}, recommendations=[{'title': 'Review'}]))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    issuer, audience = 'https://issuer.example.test', 'https://geosition.example.test/mcp'
    grants = {}
    for i, (user, workspace, _) in enumerate(pilots):
        grant = WorkspaceGrant(issuer, 'subject-%d' % i, 'client-%d' % i, user, workspace,
                               frozenset({'setup:read', 'setup:write'}))
        grants[(grant.subject, grant.client_id, workspace)] = grant
    verifier = WorkspaceTokenVerifier(issuer=issuer, audience=audience, signing_key=lambda _: key.public_key(),
        find_grant=lambda iss, sub, client, workspace: grants.get((sub, client, workspace)),
        is_member=lambda user, workspace: service.store.get_member_org(user, workspace) is not None)
    app = create_hosted_workspace_server(service, verifier).streamable_http_app()
    now = datetime.now(timezone.utc)
    def bearer(i):
        return jwt.encode({'iss': issuer, 'aud': audience, 'sub': 'subject-%d' % i,
                           'client_id': 'client-%d' % i, 'iat': now, 'exp': now + timedelta(minutes=5)},
                          key, algorithm='RS256')
    def rpc(client, token, name, arguments):
        return client.post('/mcp', headers={'Authorization': 'Bearer ' + token,
                           'Accept': 'application/json, text/event-stream', 'Content-Type': 'application/json'},
                           json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                 'params': {'name': name, 'arguments': arguments}})
    with TestClient(app, base_url='https://geosition.example.test') as client:
        unauthorized = client.post('/mcp')
        assert unauthorized.status_code == 401
        assert 'resource_metadata=' in unauthorized.headers['www-authenticate']
        wrong_host = client.post('/mcp', headers={'Host': 'attacker.example.test',
                                 'Authorization': 'Bearer ' + bearer(0),
                                 'Accept': 'application/json, text/event-stream',
                                 'Content-Type': 'application/json'},
                                 json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list', 'params': {}})
        assert wrong_host.status_code == 421
        metadata = client.get('/.well-known/oauth-protected-resource/mcp')
        assert metadata.status_code == 200
        assert metadata.json()['resource'] == audience
        for i, (_, workspace, domain) in enumerate(pilots):
            own = {'workspace_id': workspace, 'domain': domain}
            audit = rpc(client, bearer(i), 'geosition_run_commerce_audit', own)
            assert audit.status_code == 200
            assert not audit.json()['result'].get('isError')
            status = rpc(client, bearer(i), 'geosition_setup_status', own).json()['result']
            data = json.loads(status['content'][0]['text'])
            assert data['setup']['audit']['coverage']['pages_audited'] == 1
            assert data['vercel']['connected'] is False
            other = pilots[1 - i]
            denied = rpc(client, bearer(i), 'geosition_setup_status',
                         {'workspace_id': other[1], 'domain': other[2]}).json()['result']
            assert denied['isError']
            assert other[2] not in json.dumps(denied)
        grants.clear()
        assert rpc(client, bearer(0), 'geosition_setup_status',
                   {'workspace_id': pilots[0][1], 'domain': pilots[0][2]}).json()['result']['isError']
