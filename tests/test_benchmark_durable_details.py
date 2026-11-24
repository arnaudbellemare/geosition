from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from geo_optimizer.models.results import AuditResult
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.web import app as web_app, platform_routes


def test_details_survive_store_restart_and_enforce_workspace_boundaries(tmp_path, monkeypatch):
    database = tmp_path / 'platform.db'
    store = PlatformStore(database)
    service = PlatformService(store)
    monkeypatch.setenv('GEO_BENCHMARK_DB', str(tmp_path / 'benchmark.db'))
    owners = []
    for label, domain in [('mom', 'robel-art.example'), ('velora', 'gestionvelora.example')]:
        account = service.register(email=f'{label}@example.test', password='password123', org_name=label)
        token = account['session']['token']
        domain_id = service.add_website_domain(token, domain)['domain']['domain_id']
        store.mark_domain_verified(domain_id, method='test')
        payload = {'answers': [{'prompt': f'Find {label}', 'answer_text': f'{label} evidence',
                                'provider': 'test', 'citation_urls': [f'https://{domain}/source']}]}
        with patch('geo_optimizer.core.benchmark.runner.run_full_audit', return_value=AuditResult(url=f'https://{domain}', error='skip')):
            run = service.run_benchmark(token, domain=domain, answers_payload=payload)
        owners.append((token, domain, run['link']['link_id'], label))
    (tmp_path / 'benchmark.db').unlink()
    restarted = PlatformService(PlatformStore(database))
    monkeypatch.setattr(platform_routes, '_service', restarted)
    client = TestClient(web_app.app)
    for token, domain, link, label in owners:
        response = client.get(f'/api/v1/benchmark/runs/{link}', headers={'Authorization': f'Bearer {token}'})
        assert response.status_code == 200
        assert response.json()['domain'] == domain
        assert response.json()['details']['answers'][0]['answer_text'] == f'{label} evidence'
        summary = restarted.citation_share_summary(token, domain=domain)
        assert summary['has_data'] is True
        assert summary['summary']['provider_coverage'] == {'test': 1}
        assert summary['summary']['target_cited_count'] == 1
        assert summary['summary']['top_cited_sources'] == {domain: 1}
        other = owners[1 if label == 'mom' else 0][0]
        with pytest.raises(ValueError, match="not verified"):
            restarted.citation_share_summary(other, domain=domain)
        assert client.get(f'/api/v1/benchmark/runs/{link}', headers={'Authorization': f'Bearer {other}'}).status_code == 404


def test_supabase_adapter_sends_workspace_filter_for_each_read():
    from geo_optimizer.saas.supabase_store import SupabasePlatformStore

    store = SupabasePlatformStore.__new__(SupabasePlatformStore)
    records = {('1', '11'): {'domain': 'robel-art.example', 'details': {'answer': 'mom'}},
               ('3', '22'): {'domain': 'gestionvelora.example', 'details': {'answer': 'velora'}}}
    def fake_request(method, table, *, params=None, **kwargs):
        assert method == 'GET' and table == 'geo_org_benchmark_runs'
        assert params['select'] == 'domain,details'
        key = (params['org_id'].removeprefix('eq.'), params['id'].removeprefix('eq.'))
        return [records[key]] if key in records else []
    store._request = fake_request
    assert store.get_benchmark_details(1, 11)['details']['answer'] == 'mom'
    assert store.get_benchmark_details(3, 22)['details']['answer'] == 'velora'
    assert store.get_benchmark_details(1, 22) is None
    assert store.get_benchmark_details(3, 11) is None


def test_supabase_latest_summary_query_is_scoped_by_workspace_and_domain():
    from geo_optimizer.saas.supabase_store import SupabasePlatformStore

    store = SupabasePlatformStore.__new__(SupabasePlatformStore)
    def fake_request(method, table, *, params=None, **kwargs):
        assert method == "GET" and table == "geo_org_benchmark_runs"
        assert params == {"org_id": "eq.3", "domain": "eq.gestionvelora.example",
                          "select": "details", "order": "run_at.desc,id.desc", "limit": "1"}
        return [{"details": {"citation_share_summary": {"sample_size": 1}}}]
    store._request = fake_request
    assert store.get_latest_benchmark_details(3, "gestionvelora.example")["details"]["citation_share_summary"]["sample_size"] == 1
