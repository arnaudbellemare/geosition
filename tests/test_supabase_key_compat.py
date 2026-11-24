from geo_optimizer.saas.supabase_store import SupabasePlatformStore
from geo_optimizer.storage.platform import get_platform_store


def test_new_secret_key_is_used_without_jwt_header(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SECRET_KEY', 'sb_secret_example')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'old-key')
    monkeypatch.setenv('VERCEL', '1')
    monkeypatch.delenv('GEO_PLATFORM_BACKEND', raising=False)
    store = get_platform_store()
    assert isinstance(store, SupabasePlatformStore)
    assert store.headers['apikey'] == 'sb_secret_example'
    assert 'Authorization' not in store.headers


def test_legacy_key_retains_bearer_authorization(monkeypatch):
    monkeypatch.setenv('SUPABASE_URL', 'https://example.supabase.co')
    monkeypatch.setenv('SUPABASE_SERVICE_ROLE_KEY', 'legacy-token')
    monkeypatch.delenv('SUPABASE_SECRET_KEY', raising=False)
    store = SupabasePlatformStore()
    assert store.headers['apikey'] == 'legacy-token'
    assert store.headers['Authorization'] == 'Bearer legacy-token'
