from __future__ import annotations
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.saas import vercel_connections
from geo_optimizer.web import platform_routes
from geo_optimizer.web.app import app

@pytest.mark.parametrize(('domain','project'), [('www.robel-art.com','mom-art-shop'),('www.gestionvelora.com','gestion-velora-website')])
def test_dashboard_requires_explicit_confirmation(tmp_path, monkeypatch, domain, project):
    for k,v in {'GEOSITION_VERCEL_INTEGRATION_SLUG':'geosition-ai','GEOSITION_VERCEL_CLIENT_ID':'client',
        'GEOSITION_VERCEL_CLIENT_SECRET':'secret','GEOSITION_PUBLIC_BASE_URL':'https://geosition.test',
        'GEOSITION_OAUTH_ENCRYPTION_KEY':Fernet.generate_key().decode()}.items(): monkeypatch.setenv(k,v)
    store=PlatformStore(tmp_path/'test.db'); service=PlatformService(store); monkeypatch.setattr(platform_routes,'_service',service)
    user=service.register(email='pilot@example.test',password='example-password',org_name='Pilot')
    item=service.add_website_domain(user['session']['token'],domain)['domain']; store.mark_domain_verified(item['domain_id'],method='test')
    client=TestClient(app,base_url='https://geosition.test')
    assert client.post('/api/v1/auth/login',json={'email':'pilot@example.test','password':'example-password'}).status_code==200
    csrf=client.cookies.get('geo_csrf')
    r=client.post('/api/v1/commerce/vercel/start',headers={'X-CSRF-Token':csrf},json={'domain':domain,'project':project,'team_slug':'arnaud15'})
    assert r.status_code==200 and r.json()['authorization_url']=='https://vercel.com/arnaud15/~/integrations/geosition-ai'
    def provider(method,url,**kwargs):
        if method=='POST': return {'access_token':'sensitive-token','team_id':'team-1'}
        return {'name':domain,'projectId':'prj-'+project,'verified':True}
    monkeypatch.setattr(vercel_connections,'_provider_json',provider)
    r=client.get('/api/v1/commerce/vercel/callback',params={'source':'marketplace','code':'example','configurationId':'icfg_123','next':'https://vercel.com/arnaud15/~/integrations/icfg_123/installed'},follow_redirects=False)
    assert r.status_code==303 and r.headers['location'].endswith('vercel=confirm')
    assert store.get_vercel_connection(user['organization']['org_id'],domain) is None
    assert client.post('/api/v1/commerce/vercel/confirm',json={}).status_code==403
    result=client.get('/api/v1/commerce/vercel/pending'); assert result.json()['domain']==domain
    assert 'sensitive-token' not in result.text
    confirmed=client.post('/api/v1/commerce/vercel/confirm',headers={'X-CSRF-Token':csrf},json={})
    assert confirmed.status_code==200 and confirmed.json()['project_id']=='prj-'+project
    assert 'sensitive-token' not in store.get_vercel_connection(user['organization']['org_id'],domain)['encrypted_token']
    assert client.post('/api/v1/commerce/vercel/confirm',headers={'X-CSRF-Token':csrf},json={}).status_code==400

def test_dashboard_rejects_an_unsolicited_callback(tmp_path, monkeypatch):
    for k,v in {'GEOSITION_VERCEL_INTEGRATION_SLUG':'geosition-ai','GEOSITION_VERCEL_CLIENT_ID':'client',
        'GEOSITION_VERCEL_CLIENT_SECRET':'secret','GEOSITION_PUBLIC_BASE_URL':'https://geosition.test',
        'GEOSITION_OAUTH_ENCRYPTION_KEY':Fernet.generate_key().decode()}.items(): monkeypatch.setenv(k,v)
    store=PlatformStore(tmp_path/'test.db'); service=PlatformService(store); monkeypatch.setattr(platform_routes,'_service',service)
    service.register(email='pilot@example.test',password='example-password',org_name='Pilot')
    client=TestClient(app,base_url='https://geosition.test')
    client.post('/api/v1/auth/login',json={'email':'pilot@example.test','password':'example-password'})
    monkeypatch.setattr(vercel_connections,'_provider_json',lambda *args,**kwargs: pytest.fail('unsolicited code exchange'))
    r=client.get('/api/v1/commerce/vercel/callback',params={'source':'marketplace','code':'bad'},follow_redirects=False)
    assert r.headers['location'].endswith('vercel=failed')

@pytest.mark.parametrize('next_url', [
    'https://example.com/arnaud15/~/integrations/icfg_123/installed',
    'https://vercel.com/arnaud15/~/integrations/icfg_wrong/installed',
    'https://vercel.com/arnaud15/~/integrations/icfg_123/installed?next=https://example.com',
])
def test_dashboard_rejects_untrusted_completion_urls(monkeypatch, next_url):
    for k,v in {'GEOSITION_VERCEL_INTEGRATION_SLUG':'geosition-ai','GEOSITION_VERCEL_CLIENT_ID':'client',
        'GEOSITION_VERCEL_CLIENT_SECRET':'secret','GEOSITION_PUBLIC_BASE_URL':'https://geosition.test',
        'GEOSITION_OAUTH_ENCRYPTION_KEY':Fernet.generate_key().decode()}.items(): monkeypatch.setenv(k,v)
    with pytest.raises(ValueError):
        vercel_connections.make_dashboard_pending('state','session',1,'www.robel-art.com','prj_1','team_1','encrypted',next_url,'icfg_123')

def test_dashboard_pending_is_bound_to_session_and_workspace(monkeypatch):
    for k,v in {'GEOSITION_VERCEL_INTEGRATION_SLUG':'geosition-ai','GEOSITION_VERCEL_CLIENT_ID':'client',
        'GEOSITION_VERCEL_CLIENT_SECRET':'secret','GEOSITION_PUBLIC_BASE_URL':'https://geosition.test',
        'GEOSITION_OAUTH_ENCRYPTION_KEY':Fernet.generate_key().decode()}.items(): monkeypatch.setenv(k,v)
    pending=vercel_connections.make_dashboard_pending('state','session',1,'www.robel-art.com','prj_1','team_1','encrypted','https://vercel.com/arnaud15/~/integrations/icfg_123/installed','icfg_123')
    with pytest.raises(ValueError): vercel_connections.read_dashboard_pending(pending,'other',1)
    with pytest.raises(ValueError): vercel_connections.read_dashboard_pending(pending,'session',2)
