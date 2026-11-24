from __future__ import annotations

from fastapi.testclient import TestClient
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.web.app import app
from geo_optimizer.web import platform_routes


def test_invitation_switches_only_the_accepting_session_and_is_one_use(tmp_path, monkeypatch):
    service = PlatformService(PlatformStore(tmp_path / 'test.db'))
    monkeypatch.setattr(platform_routes, '_service', service)
    owner = service.register(email='owner@shop.test', password='password123', org_name='Shop')
    operator = service.register(email='operator@agency.test', password='password123', org_name='Agency')
    stranger = service.register(email='stranger@other.test', password='password123', org_name='Other')
    domain = service.add_website_domain(owner['session']['token'], 'www.robel-art.com')['domain']
    service.store.mark_domain_verified(domain['domain_id'], method='test-fixture')
    owner_auth = {'Authorization': 'Bearer ' + owner['session']['token']}
    operator_auth = {'Authorization': 'Bearer ' + operator['session']['token']}
    stranger_auth = {'Authorization': 'Bearer ' + stranger['session']['token']}
    client = TestClient(app)
    created = client.post('/api/v1/workspace/invitations', json={'email': 'operator@agency.test'}, headers=owner_auth)
    assert created.status_code == 200
    invite = created.json()['token']
    assert client.post('/api/v1/workspace/invitations/accept', json={'token': invite}, headers=stranger_auth).status_code == 400
    assert client.post('/api/v1/workspace/invitations/accept', json={'token': invite}, headers=operator_auth).status_code == 200
    assert service.require_session(operator['session']['token'])[1].org_id == owner['organization']['org_id']
    choices = client.get('/api/v1/workspaces', headers=operator_auth).json()
    assert len(choices['workspaces']) == 2
    assert client.post('/api/v1/workspaces/select', json={'org_id': stranger['organization']['org_id']}, headers=operator_auth).status_code == 403
    assert client.post('/api/v1/workspaces/select', json={'org_id': operator['organization']['org_id']}, headers=operator_auth).status_code == 200
    assert client.post('/api/v1/workspaces/select', json={'org_id': owner['organization']['org_id']}, headers=operator_auth).status_code == 200
    assert service.require_session(stranger['session']['token'])[1].org_id == stranger['organization']['org_id']
    assert client.get('/api/v1/commerce/setup', params={'domain': 'www.robel-art.com'}, headers=operator_auth).status_code == 200
    assert client.post('/api/v1/workspace/invitations/accept', json={'token': invite}, headers=operator_auth).status_code == 400
    assert client.post('/api/v1/workspace/invitations', json={'email': 'new@example.test'}, headers=operator_auth).status_code == 403
