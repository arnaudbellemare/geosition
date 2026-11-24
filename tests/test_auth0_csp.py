from fastapi import FastAPI
from fastapi.testclient import TestClient
from geo_optimizer.web.app import SecurityHeadersMiddleware


def test_auth0_form_destination_only_on_consent_page(monkeypatch):
    monkeypatch.setenv('GEOSITION_AUTH0_ISSUER', 'https://pilot.us.auth0.com/')
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    @app.get('/oauth/auth0/consent')
    def consent():
        return {'ok': True}
    @app.get('/other')
    def other():
        return {'ok': True}
    with TestClient(app) as client:
        assert "form-action 'self' https://pilot.us.auth0.com" in client.get('/oauth/auth0/consent').headers['content-security-policy']
        assert "form-action 'self'" in client.get('/other').headers['content-security-policy']
        assert 'pilot.us.auth0.com' not in client.get('/other').headers['content-security-policy']
