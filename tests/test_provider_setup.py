from __future__ import annotations

from fastapi.testclient import TestClient
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.web.app import app
from geo_optimizer.web import platform_routes


def test_provider_progress_is_independent_and_workspace_scoped(tmp_path, monkeypatch):
    service = PlatformService(PlatformStore(tmp_path / 'platform.db'))
    monkeypatch.setattr(platform_routes, '_service', service)
    owner = service.register(email='shop@example.test', password='password123', org_name='Shop')
    other = service.register(email='other@example.test', password='password123', org_name='Other')
    token = owner['session']['token']
    domain = service.add_website_domain(token, 'www.robel-art.com')['domain']
    service.store.mark_domain_verified(domain['domain_id'], method='test')
    client = TestClient(app)
    headers = {'Authorization': 'Bearer ' + token}
    path = '/api/v1/commerce/setup'
    body = {'domain': 'www.robel-art.com', 'step': 'chatgpt_connector', 'status': 'done'}
    assert client.post(path + '/step', headers=headers, json=body).status_code == 200
    setup = client.get(path, headers=headers, params={'domain': body['domain']}).json()
    assert [item['name'] for item in setup['providers']] == ['ChatGPT', 'Claude']
    assert setup['statuses']['chatgpt_connector'] == 'done'
    assert 'claude_connector' not in setup['statuses']
    assert client.post(path + '/step', headers=headers, json={**body, 'step': 'claude_connector', 'status': 'working'}).status_code == 200
    assert client.get(path, headers=headers, params={'domain': body['domain']}).json()['statuses']['claude_connector'] == 'working'
    assert client.get(path, headers={'Authorization': 'Bearer ' + other['session']['token']}, params={'domain': body['domain']}).status_code == 400
    assert client.post(path + '/step', headers=headers, json={**body, 'step': 'other_connector'}).status_code == 400
