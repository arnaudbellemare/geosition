from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from geo_optimizer.models.results.commerce_site import CommerceSiteReport
from geo_optimizer.saas.auth import hash_password
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.web.app import app
from geo_optimizer.web import platform_routes
from geo_optimizer.saas import commerce_guided


def test_workspace_audit_and_shared_progress_are_scoped(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / 'platform.db')
    service = PlatformService(store)
    monkeypatch.setattr(platform_routes, '_service', service)
    owner = service.register(email='owner@shop.test', password='password123', org_name="Mom's Art Shop")
    owner_token = owner['session']['token']
    domain = service.add_website_domain(owner_token, 'www.robel-art.com')['domain']
    store.mark_domain_verified(domain['domain_id'], method='test')
    operator = store.create_user('operator@agency.test', 'agency.test', hash_password('password123'))
    with store._connect() as conn:
        conn.execute("INSERT INTO memberships (user_id, org_id, role) VALUES (?, ?, 'member')", (operator.user_id, owner['organization']['org_id']))
    operator_token = service.login(email='operator@agency.test', password='password123')['session']['token']
    other = service.register(email='other@other.test', password='password123', org_name='Other')
    other_token = other['session']['token']
    evidence = json.loads(Path('docs/client-reports/moms-art-shop-evidence.json').read_text())
    report = CommerceSiteReport(**{k: evidence[k] for k in ('url', 'pages', 'failures', 'skipped', 'warnings', 'coverage', 'recommendations')})
    monkeypatch.setattr(commerce_guided, 'run_site_audit', lambda url, max_pages, render: report)
    client = TestClient(app)
    auth = lambda token: {'Authorization': f'Bearer {token}'}
    body = {'domain': 'www.robel-art.com', 'step': 'connection', 'status': 'working'}
    assert client.post('/api/v1/commerce/setup/step', headers=auth(owner_token), json=body).status_code == 200
    response = client.get('/api/v1/commerce/setup', headers=auth(operator_token), params={'domain': body['domain']})
    assert response.json()['statuses']['connection'] == 'working'
    assert client.get('/api/v1/commerce/setup', headers=auth(other_token), params={'domain': body['domain']}).status_code == 400
    assert client.post('/api/v1/commerce/setup/step', headers=auth(owner_token), json={**body, 'status': 'verified'}).status_code == 400
    audited = client.post('/api/v1/commerce/setup/audit', headers=auth(operator_token), json={'domain': body['domain']})
    assert audited.status_code == 200
    assert audited.json()['coverage']['pages_audited'] > 0
    loaded = client.get('/api/v1/commerce/setup', headers=auth(owner_token), params={'domain': body['domain']}).json()
    assert loaded['audit']['recommendations'] == audited.json()['recommendations']
    assert 'No payment' in loaded['audit']['limitations']
    assert client.get('/api/v1/commerce/setup', params={'domain': body['domain']}).status_code == 401
