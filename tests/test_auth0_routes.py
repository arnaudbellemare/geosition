from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

jwt = pytest.importorskip('jwt')

from geo_optimizer.mcp import auth0_routes as module

SECRET = 'a-long-purpose-specific-test-secret-value-123456789'
ISSUER = 'https://pilot.us.auth0.com/'
RESOURCE = 'https://geosition.example/mcp'

class Service:
    store = SimpleNamespace(membership_role=lambda user_id, org_id: 'owner')
    def require_session(self, token):
        if token != 'mom-session':
            raise PermissionError()
        return SimpleNamespace(user_id=1), SimpleNamespace(org_id=10, name='Mom’s Art Shop')

class Grants:
    def __init__(self): self.items = []
    def save(self, grant): self.items.append(grant)

@pytest.fixture
def client():
    grants = Grants()
    app = FastAPI()
    app.include_router(module.create_auth0_router(Service(), grants, Fernet(Fernet.generate_key()),
        secret=SECRET, issuer=ISSUER, resource=RESOURCE, clients={'client-1':'ChatGPT'}, html='<p>Consent</p>'))
    with TestClient(app, base_url='https://geosition.example') as c:
        c.grants = grants
        yield c

def context(**changes):
    now = datetime.now(timezone.utc)
    payload = {'iss':'pilot.us.auth0.com','sub':'auth0|mom','iat':now,'exp':now+timedelta(seconds=60),
               'client_id':'client-1','resource':RESOURCE,'purpose':'workspace-link'}
    payload.update(changes)
    return jwt.encode(payload, SECRET, algorithm='HS256')

def start(client, token=None):
    return client.get('/oauth/auth0/start', params={'state':'auth0-state','session_token':token or context()},
                      follow_redirects=False)

def test_consent_links_authenticated_workspace_and_posts_state_token(client):
    response = start(client)
    assert response.status_code == 303
    assert response.headers['location'] == '/oauth/auth0/consent'
    client.cookies.set('geo_session','mom-session', domain='geosition.example',path='/')
    assert client.get('/oauth/auth0/consent').status_code == 200
    review = client.get('/api/v1/mcp/auth0/review')
    assert review.json() == {'workspace':'Mom’s Art Shop','client':'ChatGPT','identity':'auth0|mom','email':'','email_verified':False}
    csrf = client.cookies.get('geo_csrf')
    result = client.post('/api/v1/mcp/auth0/decision', headers={'x-csrf-token':csrf},
                         json={'decision':'approve','permissions':['setup:read']})
    assert result.status_code == 200
    grant = client.grants.items[0]
    assert (grant.user_id, grant.workspace_id, grant.subject, grant.client_id) == (1,10,'auth0|mom','client-1')
    payload = jwt.decode(result.json()['token'], SECRET, algorithms=['HS256'])
    assert payload['state'] == 'auth0-state' and payload['decision'] == 'approve'
    assert result.json()['continue_url'] == ISSUER + 'continue'

def test_rejects_wrong_resource_and_requires_review_and_csrf(client):
    assert start(client, context(resource='https://attacker.example')).status_code == 400
    assert start(client).status_code == 303
    client.cookies.set('geo_session','mom-session', domain='geosition.example',path='/')
    assert client.get('/oauth/auth0/consent').status_code == 200
    assert client.get('/api/v1/mcp/auth0/review').status_code == 200
    denied = client.post('/api/v1/mcp/auth0/decision', json={'decision':'approve','permissions':['setup:read']})
    assert denied.status_code == 403
    assert not client.grants.items

def test_changed_workspace_after_review_is_rejected(client, monkeypatch):
    assert start(client).status_code == 303
    client.cookies.set('geo_session','mom-session', domain='geosition.example',path='/')
    assert client.get('/oauth/auth0/consent').status_code == 200
    assert client.get('/api/v1/mcp/auth0/review').status_code == 200
    monkeypatch.setattr(Service, 'require_session', lambda self, token: (
        SimpleNamespace(user_id=1), SimpleNamespace(org_id=20, name='Gestion Velora')))
    response = client.post('/api/v1/mcp/auth0/decision', headers={'x-csrf-token':client.cookies.get('geo_csrf')},
                           json={'decision':'approve','permissions':['setup:read']})
    assert response.status_code == 403
    assert not client.grants.items

def test_workspace_member_cannot_grant_connector_access(client, monkeypatch):
    assert start(client).status_code == 303
    client.cookies.set('geo_session', 'mom-session', domain='geosition.example', path='/')
    assert client.get('/oauth/auth0/consent').status_code == 200
    monkeypatch.setattr(Service, 'store', SimpleNamespace(membership_role=lambda user_id, org_id: 'member'))
    assert client.get('/api/v1/mcp/auth0/review').status_code == 403
    assert not client.grants.items


def test_denial_does_not_create_grant(client):
    assert start(client).status_code == 303
    client.cookies.set('geo_session', 'mom-session', domain='geosition.example', path='/')
    assert client.get('/oauth/auth0/consent').status_code == 200
    assert client.get('/api/v1/mcp/auth0/review').status_code == 200
    result = client.post('/api/v1/mcp/auth0/decision', headers={'x-csrf-token': client.cookies.get('geo_csrf')},
                         json={'decision': 'deny', 'permissions': []})
    assert result.status_code == 200
    assert not client.grants.items
    assert jwt.decode(result.json()['token'], SECRET, algorithms=['HS256'])['decision'] == 'deny'
