from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from geo_optimizer.saas import vercel_connections
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.web import platform_routes
from geo_optimizer.web.app import app


def test_pilot_connections_are_encrypted_and_workspace_scoped(tmp_path, monkeypatch):
    key = Fernet.generate_key().decode()
    for name, value in {
        'GEOSITION_VERCEL_INTEGRATION_SLUG': 'geosition-test',
        'GEOSITION_VERCEL_CLIENT_ID': 'client', 'GEOSITION_VERCEL_CLIENT_SECRET': 'secret',
        'GEOSITION_PUBLIC_BASE_URL': 'https://geosition.test', 'GEOSITION_OAUTH_ENCRYPTION_KEY': key,
    }.items():
        monkeypatch.setenv(name, value)
    store = PlatformStore(tmp_path / 'platform.db')
    service = PlatformService(store)
    monkeypatch.setattr(platform_routes, '_service', service)
    def provider(method, url, **kwargs):
        if method == 'POST':
            return {'access_token': 'private-token-' + kwargs['data']['code'], 'team_id': 'team-test'}
        project, domain = url.split('/projects/')[1].split('/domains/')
        if (project, domain) not in [('mom-art-shop', 'www.robel-art.com'), ('gestion-velora-website', 'www.gestionvelora.com')]:
            return {'name': domain, 'projectId': 'wrong', 'verified': False}
        return {'name': domain, 'projectId': 'prj-' + project, 'verified': True}
    monkeypatch.setattr(vercel_connections, '_provider_json', provider)
    client = TestClient(app, base_url='https://geosition.test')
    pilots = []
    for email, site, project in [('owner@shop.test', 'www.robel-art.com', 'mom-art-shop'),
                                  ('owner@velora.test', 'www.gestionvelora.com', 'gestion-velora-website')]:
        account = service.register(email=email, password='password123', org_name=project)
        token = account['session']['token']; org = account['organization']['org_id']
        item = service.add_website_domain(token, site)['domain']
        store.mark_domain_verified(item['domain_id'], method='test')
        auth = {'Authorization': 'Bearer ' + token}
        started = client.post('/api/v1/commerce/vercel/start', headers=auth, json={'domain': site, 'project': project})
        assert started.status_code == 200
        state = parse_qs(urlsplit(started.json()['authorization_url']).query)['state'][0]
        callback = client.get('/api/v1/commerce/vercel/callback', headers=auth,
                              params={'code': project, 'state': state}, follow_redirects=False)
        assert callback.headers['location'].endswith('vercel=connected')
        row = store.get_vercel_connection(org, site)
        assert row['project_id'] == 'prj-' + project
        assert 'private-token' not in row['encrypted_token']
        assert Fernet(key.encode()).decrypt(row['encrypted_token'].encode()).decode() == 'private-token-' + project
        status = client.get('/api/v1/commerce/vercel', headers=auth, params={'domain': site})
        assert status.json() == {'connected': True, 'project_id': 'prj-' + project}
        pilots.append((token, org, site))
    other_auth = {'Authorization': 'Bearer ' + pilots[1][0]}
    assert client.get('/api/v1/commerce/vercel', headers=other_auth, params={'domain': pilots[0][2]}).status_code == 400
    assert client.post('/api/v1/commerce/vercel/disconnect', headers=other_auth, json={'domain': pilots[0][2]}).status_code == 400
    assert store.get_vercel_connection(pilots[0][1], pilots[0][2]) is not None


def test_state_rejects_wrong_session_and_workspace(monkeypatch):
    for name, value in {'GEOSITION_VERCEL_INTEGRATION_SLUG': 'test', 'GEOSITION_VERCEL_CLIENT_ID': 'id',
                        'GEOSITION_VERCEL_CLIENT_SECRET': 'secret', 'GEOSITION_PUBLIC_BASE_URL': 'https://geosition.test',
                        'GEOSITION_OAUTH_ENCRYPTION_KEY': Fernet.generate_key().decode()}.items():
        monkeypatch.setenv(name, value)
    _, state = vercel_connections.begin_connection('www.robel-art.com', 'mom-art-shop', 1, 'session')
    with pytest.raises(ValueError):
        vercel_connections.verify_state(state, state, 'session', 2)
    with pytest.raises(ValueError):
        vercel_connections.verify_state(state, state, 'other-session', 1)
    with pytest.raises(ValueError):
        vercel_connections.verify_state(state, 'different', 'session', 1)


@pytest.mark.parametrize('site,project', [
    ('www.robel-art.com', 'mom-art-shop'),
    ('www.gestionvelora.com', 'gestion-velora-website'),
])
def test_browser_cookie_flow_rejects_wrong_project(tmp_path, monkeypatch, site, project):
    for name, value in {'GEOSITION_VERCEL_INTEGRATION_SLUG': 'test', 'GEOSITION_VERCEL_CLIENT_ID': 'id',
                        'GEOSITION_VERCEL_CLIENT_SECRET': 'secret', 'GEOSITION_PUBLIC_BASE_URL': 'https://geosition.test',
                        'GEOSITION_OAUTH_ENCRYPTION_KEY': Fernet.generate_key().decode()}.items():
        monkeypatch.setenv(name, value)
    store = PlatformStore(tmp_path / 'platform.db')
    service = PlatformService(store)
    monkeypatch.setattr(platform_routes, '_service', service)
    account = service.register(email='owner@shop.test', password='password123', org_name='Pilot')
    domain = service.add_website_domain(account['session']['token'], site)['domain']
    store.mark_domain_verified(domain['domain_id'], method='test')
    client = TestClient(app, base_url='https://geosition.test')
    assert client.post('/api/v1/auth/login', json={'email': 'owner@shop.test', 'password': 'password123'}).status_code == 200
    csrf = client.cookies.get('geo_csrf')
    started = client.post('/api/v1/commerce/vercel/start', headers={'X-CSRF-Token': csrf},
                          json={'domain': site, 'project': project})
    assert started.status_code == 200
    state = parse_qs(urlsplit(started.json()['authorization_url']).query)['state'][0]
    def provider(method, url, **kwargs):
        return {'access_token': 'secret-token', 'team_id': None} if method == 'POST' else {
            'name': 'wrong.example', 'projectId': 'prj_wrong', 'verified': True}
    monkeypatch.setattr(vercel_connections, '_provider_json', provider)
    response = client.get('/api/v1/commerce/vercel/callback', params={'state': state, 'code': 'code'},
                          follow_redirects=False)
    assert response.headers['location'].endswith('vercel=failed')
    assert store.get_vercel_connection(account['organization']['org_id'], site) is None
