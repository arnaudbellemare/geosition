from __future__ import annotations

from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet

pytest.importorskip('jwt')
pytest.importorskip('mcp')

from geo_optimizer.mcp import hosted_bootstrap
from geo_optimizer.saas.supabase_store import SupabasePlatformStore


def test_hosted_bootstrap_requires_persistent_storage_and_resource_bound_config(monkeypatch):
    env = {'SUPABASE_URL': 'https://pilot.supabase.co', 'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_test',
           'GEOSITION_PUBLIC_BASE_URL': 'https://geosition.example.test',
           'GEOSITION_OAUTH_ENCRYPTION_KEY': Fernet.generate_key().decode()}
    with pytest.raises(ValueError, match='persistent Supabase'):
        hosted_bootstrap.install_configured_hosted_integration(object(), SimpleNamespace(store=object()), env=env)
    service = SimpleNamespace(store=object.__new__(SupabasePlatformStore))
    captured = {}
    monkeypatch.setattr(hosted_bootstrap, 'install_hosted_integration',
                        lambda app, **kwargs: captured.update(kwargs) or 'installed')
    assert hosted_bootstrap.install_configured_hosted_integration(object(), service, env=env) == 'installed'
    assert captured['verifier'].issuer == 'https://pilot.supabase.co/auth/v1'
    assert captured['verifier'].audience == 'https://geosition.example.test/mcp'
    with pytest.raises(ValueError):
        hosted_bootstrap.install_configured_hosted_integration(object(), service,
            env={**env, 'GEOSITION_PUBLIC_BASE_URL': 'http://geosition.example.test'})
    with pytest.raises(ValueError, match='encryption key'):
        hosted_bootstrap.install_configured_hosted_integration(object(), service,
            env={**env, 'GEOSITION_OAUTH_ENCRYPTION_KEY': 'invalid'})
