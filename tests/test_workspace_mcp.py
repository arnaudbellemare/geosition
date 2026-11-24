from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

pytest.importorskip('mcp')

from geo_optimizer.mcp import workspace_connector as connector
from geo_optimizer.models.results.commerce_site import CommerceSiteReport
from geo_optimizer.saas import commerce_guided
from geo_optimizer.saas.service import PlatformService
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.web import platform_routes
from geo_optimizer.web.app import app


def test_pilot_workspaces_setup_and_isolation(tmp_path, monkeypatch):
    service = PlatformService(PlatformStore(tmp_path / 'pilot.db'))
    monkeypatch.setattr(platform_routes, '_service', service)
    pilots = []
    for email, name, domain in [('mom@example.test', 'Mom’s Art Shop', 'www.robel-art.com'),
                                ('velora@example.test', 'Gestion Velora', 'www.gestionvelora.com')]:
        account = service.register(email=email, password='password123', org_name=name)
        token = account['session']['token']
        record = service.add_website_domain(token, domain)['domain']
        service.store.mark_domain_verified(record['domain_id'], method='test')
        pilots.append((token, account['organization']['org_id'], domain))

    def audit(url, max_pages, render):
        return CommerceSiteReport(url=url, coverage={'pages_audited': 1}, recommendations=[{'title': 'Review journey'}])
    monkeypatch.setattr(commerce_guided, 'run_site_audit', audit)
    monkeypatch.setattr('geo_optimizer.saas.service.verify_domain', lambda domain, token, method: (True, 'Verified'))
    client = TestClient(app)

    def request(method, url, *, headers, params, json, timeout, follow_redirects):
        assert urlsplit(url).hostname == 'www.geositionai.com'
        assert follow_redirects is False
        return client.request(method, urlsplit(url).path, headers=headers, params=params, json=json)
    monkeypatch.setattr(connector.httpx, 'request', request)

    for token, workspace, domain in pilots:
        monkeypatch.setenv('GEOSITION_SESSION_TOKEN', token)
        context = json.loads(connector.geosition_workspace())
        assert context['current_workspace_id'] == workspace
        assert context['domains'][0]['domain'] == domain
        assert 'verify_token' not in json.dumps(context)
        assert token not in json.dumps(context)
        assert json.loads(connector.geosition_check_domain(workspace, context['domains'][0]['domain_id']))['verified']
        result = json.loads(connector.geosition_run_commerce_audit(workspace, domain))
        assert result['coverage']['pages_audited'] == 1
        assert json.loads(connector.geosition_record_setup_progress(workspace, domain, 'site', 'working'))['verified'] is False
        status = json.loads(connector.geosition_setup_status(workspace, domain))
        assert status['setup']['statuses']['site'] == 'working'
        assert status['setup']['audit']['url'].startswith('https://' + domain)
        assert status['vercel']['connected'] is False
        other = next(p for p in pilots if p[1] != workspace)
        with pytest.raises(PermissionError):
            connector.geosition_setup_status(other[1], other[2])
        with pytest.raises(ValueError):
            connector.geosition_setup_status(workspace, other[2])
        with pytest.raises(ValueError):
            connector.geosition_check_domain(workspace, context['domains'][0]['domain_id'], 'invalid')


def test_mcp_stdio_discovers_setup_tools():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def check():
        env = dict(os.environ)
        env['PYTHONPATH'] = str(Path(connector.__file__).resolve().parents[2])
        startup = "import sys,runpy;sys.path.insert(0,sys.argv[1]);runpy.run_module('geo_optimizer.mcp.workspace_connector',run_name='__main__')"
        server = StdioServerParameters(command=sys.executable, args=['-c', startup, env['PYTHONPATH']],
                                       env=env, cwd=str(Path(connector.__file__).resolve().parents[3]))
        async with stdio_client(server) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                names = {tool.name for tool in (await session.list_tools()).tools}
                assert {'geosition_workspace', 'geosition_setup_status', 'geosition_run_commerce_audit',
                        'geosition_record_setup_progress', 'geosition_check_domain'} <= names

    asyncio.run(asyncio.wait_for(check(), timeout=30))
