from fastapi.testclient import TestClient
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.web import app as web_app
from geo_optimizer.web import platform_routes


def test_history_uses_durable_link_id_for_reused_internal_run_ids(tmp_path, monkeypatch):
    store = PlatformStore(tmp_path / 'platform.db')
    service = PlatformService(store)
    monkeypatch.setattr(platform_routes, '_service', service)
    registered = service.register(email='owner@example.test', password='password123', org_name='Example')
    org = registered['organization']['org_id']
    token = registered['session']['token']
    for date in ('2026-11-14T18:00:00+00:00', '2026-11-14T19:00:00+00:00'):
        store.link_benchmark_run(org, domain='example.test', benchmark_run_id=1, benchmark_score=21, band='vulnerable', run_at=date)
    response = TestClient(web_app.app).get('/platform/dashboard', headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 200
    assert '#1 example.test' in response.text
    assert '#2 example.test' in response.text
    assert '2026-11-14T18:00:00' in response.text
    assert '2026-11-14T19:00:00' in response.text
