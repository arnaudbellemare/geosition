from types import SimpleNamespace
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from geo_optimizer.mcp.auth0_bootstrap import install_auth0_integration
from geo_optimizer.saas.supabase_store import SupabasePlatformStore


def test_auth0_hosted_integration_requires_config_and_publishes_metadata():
    store = SupabasePlatformStore.__new__(SupabasePlatformStore)
    service = SimpleNamespace(store=store)
    app = FastAPI()
    config = {'GEOSITION_PUBLIC_BASE_URL': 'https://geosition.example',
              'GEOSITION_AUTH0_ISSUER': 'https://pilot.us.auth0.com/',
              'GEOSITION_AUTH0_CLIENTS': '{"chatgpt-client":"ChatGPT"}',
              'GEOSITION_AUTH0_ACTION_SECRET': 'secret-key-for-test-purposes-only-123456',
              'GEOSITION_OAUTH_ENCRYPTION_KEY': Fernet.generate_key().decode()}
    install_auth0_integration(app, service, env=config)
    with TestClient(app, base_url='https://geosition.example') as client:
        metadata = client.get('/.well-known/oauth-protected-resource/mcp')
        assert metadata.status_code == 200
        assert metadata.json()['resource'] == 'https://geosition.example/mcp'
        assert client.post('/mcp').status_code == 401
    for name in ('GEOSITION_AUTH0_ACTION_SECRET', 'GEOSITION_AUTH0_CLIENTS', 'GEOSITION_AUTH0_ISSUER'):
        invalid = dict(config)
        invalid.pop(name)
        with pytest.raises(ValueError):
            install_auth0_integration(FastAPI(), service, env=invalid)
