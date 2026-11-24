import json
from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner
from fastapi.testclient import TestClient

from geo_optimizer.cli.main import cli
from geo_optimizer.models.results.commerce_site import CommerceSiteReport
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.saas import commerce_guided
from geo_optimizer.web import platform_routes
from geo_optimizer.web.app import app


def sample():
    return json.loads(Path('docs/client-reports/moms-art-shop-vercel-evidence.json').read_text())


def report():
    return CommerceSiteReport(url='https://www.robel-art.com/', pages=[{'url':'https://www.robel-art.com/'}],
        coverage={'pages_audited':1,'pending':0}, browser_access={'verified_access':'unknown','observations':[],'test_steps':[],'guidance_url':'https://developers.openai.com/commerce/agent-access'},
        recommendations=[{'id':'verify-browser-access','title':'Check','priority':'medium','evidence':'unknown','action':'check','verification':'test'}])


def test_cli_attaches_correlated_evidence_without_claiming_direct_verification():
    with patch('geo_optimizer.core.commerce_site.run_site_audit', return_value=report()):
        result=CliRunner().invoke(cli,['commerce-audit','--site','--url','https://www.robel-art.com/','--format','json','--browser-evidence','docs/client-reports/moms-art-shop-vercel-evidence.json'])
    assert result.exit_code == 0, result.output
    access=json.loads(result.output)['browser_access']
    assert access['verified_access']=='unknown'
    assert access['provider_evidence']['classification']=='operator_reported_correlated'
    assert 'did not authenticate' in access['provider_evidence']['limit']


def test_workspace_evidence_is_scoped_and_rejects_mismatch(tmp_path, monkeypatch):
    store=PlatformStore(tmp_path/'store.db'); service=PlatformService(store)
    monkeypatch.setattr(platform_routes,'_service',service)
    owner=service.register(email='owner@art.test',password='password123',org_name='Art')
    token=owner['session']['token']; domain=service.add_website_domain(token,'www.robel-art.com')['domain']
    store.mark_domain_verified(domain['domain_id'],method='test')
    other=service.register(email='owner@other.test',password='password123',org_name='Other')
    monkeypatch.setattr(commerce_guided,'run_site_audit',lambda url,max_pages,render: report())
    client=TestClient(app); headers={'Authorization':f'Bearer {token}'}
    payload={'domain':'www.robel-art.com','evidence':sample()}
    assert client.post('/api/v1/commerce/setup/browser-evidence',headers=headers,json=payload).status_code==200
    assert client.post('/api/v1/commerce/setup/audit',headers=headers,json={'domain':payload['domain']}).status_code==200
    loaded=client.get('/api/v1/commerce/setup',headers=headers,params={'domain':payload['domain']}).json()['audit']
    assert loaded['browser_access']['provider_evidence']['request_id']==sample()['request_id']
    assert loaded['browser_access']['verified_access']=='unknown'
    unauthorized=client.get('/api/v1/commerce/setup',headers={'Authorization':f"Bearer {other['session']['token']}"},params={'domain':payload['domain']})
    assert unauthorized.status_code==400
    bad={**sample(),'page_url':'https://www.gestionvelora.com/contact'}
    assert client.post('/api/v1/commerce/setup/browser-evidence',headers=headers,json={**payload,'evidence':bad}).status_code==400
    bad={**sample(),'request_time':'2026-11-14T02:00:00Z'}
    assert client.post('/api/v1/commerce/setup/browser-evidence',headers=headers,json={**payload,'evidence':bad}).status_code==400


def test_both_pilots_show_historical_correlated_evidence():
    from geo_optimizer.core.commerce_provider_evidence import attach_vercel_evidence
    for filename, audit in [('moms-art-shop-vercel-evidence.json','https://www.robel-art.com/'),
                            ('gestion-velora-vercel-evidence.json','https://www.gestionvelora.com/')]:
        evidence=json.loads((Path('docs/client-reports') / filename).read_text())
        data={'url':audit,'browser_access':{'verified_access':'unknown'},'recommendations':[]}
        result=attach_vercel_evidence(data,evidence)
        assert result['browser_access']['provider_evidence']['page_url']==evidence['page_url']
        assert result['browser_access']['verified_access']=='unknown'
