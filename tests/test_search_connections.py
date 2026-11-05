from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from geo_optimizer.saas.search_connections import begin_connection, save_connection, sync_connection, verify_state
from geo_optimizer.saas.store import PlatformStore


@pytest.fixture
def oauth_config(monkeypatch):
    monkeypatch.setenv("GEOSITION_PUBLIC_BASE_URL", "https://example.test")
    monkeypatch.setenv("GEOSITION_OAUTH_ENCRYPTION_KEY", Fernet.generate_key().decode())
    for provider in ("GOOGLE", "BING"):
        monkeypatch.setenv(f"GEOSITION_{provider}_OAUTH_CLIENT_ID", "client-id")
        monkeypatch.setenv(f"GEOSITION_{provider}_OAUTH_CLIENT_SECRET", "client-secret")


def test_oauth_state_bound_to_session_and_provider(oauth_config):
    url, state = begin_connection("google", "example.com", "session-a")
    query = parse_qs(urlparse(url).query)
    assert query["scope"] == ["https://www.googleapis.com/auth/webmasters.readonly"]
    assert query["access_type"] == ["offline"]
    assert verify_state("google", state, state, "session-a")["domain"] == "example.com"
    with pytest.raises(ValueError):
        verify_state("google", state, state, "session-b")
    with pytest.raises(ValueError):
        verify_state("bing", state, state, "session-a")
    with pytest.raises(ValueError):
        verify_state("google", state, "wrong-cookie", "session-a")


def test_connection_encrypted_and_tenant_scoped(tmp_path, oauth_config):
    store = PlatformStore(tmp_path / "platform.db")
    sites = {"siteEntry": [{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"}]}
    with patch("geo_optimizer.saas.search_connections._provider_json", return_value=sites):
        save_connection(
            store, 1, "example.com", "google", {"access_token": "access", "refresh_token": "secret-refresh"}
        )
    row = store.list_search_connections(1)[0]
    assert "secret-refresh" not in row["encrypted_refresh_token"]
    assert row["property_id"] == "sc-domain:example.com"
    assert store.list_search_connections(2) == []
    store.delete_search_connection(2, "example.com", "google")
    assert len(store.list_search_connections(1)) == 1
    store.delete_search_connection(1, "example.com", "google")
    assert store.list_search_connections(1) == []


def test_sync_preserves_rotated_token_if_analytics_fails(tmp_path, oauth_config):
    store = PlatformStore(tmp_path / "platform.db")
    sites = {"siteEntry": [{"siteUrl": "sc-domain:example.com", "permissionLevel": "siteOwner"}]}
    with patch("geo_optimizer.saas.search_connections._provider_json", return_value=sites):
        save_connection(store, 1, "example.com", "google", {"access_token": "access", "refresh_token": "old"})
    row = store.list_search_connections(1)[0]
    with (
        patch(
            "geo_optimizer.saas.search_connections._provider_json",
            return_value={"access_token": "new-access", "refresh_token": "rotated"},
        ),
        patch("geo_optimizer.saas.search_connections.fetch_search_measurement", side_effect=ValueError("failed")),
        pytest.raises(ValueError),
    ):
        sync_connection(store, row)
    saved = store.list_search_connections(1)[0]
    cipher = Fernet(__import__("os").environ["GEOSITION_OAUTH_ENCRYPTION_KEY"].encode())
    assert cipher.decrypt(saved["encrypted_refresh_token"].encode()) == b"rotated"
    assert saved["status"] == "sync_error"


def test_successful_sync_stores_labelled_results(tmp_path, oauth_config):
    store = PlatformStore(tmp_path / "platform.db")
    sites = {"d": [{"Url": "https://example.com/", "IsVerified": True}]}
    with patch("geo_optimizer.saas.search_connections._provider_json", return_value=sites):
        save_connection(store, 1, "example.com", "bing", {"access_token": "access", "refresh_token": "refresh"})
    row = store.list_search_connections(1)[0]
    with (
        patch("geo_optimizer.saas.search_connections._provider_json", return_value={"access_token": "new-access"}),
        patch(
            "geo_optimizer.saas.search_connections.fetch_search_measurement",
            return_value={"metric_scope": "search_traffic_not_ai_citations", "rows": []},
        ),
    ):
        sync_connection(store, row)
    saved = store.list_search_connections(1)[0]
    assert json.loads(saved["last_result_json"])["metric_scope"] == "search_traffic_not_ai_citations"
    assert datetime.fromisoformat(saved["last_synced_at"]).tzinfo == timezone.utc


def test_scheduler_requires_configured_secret(monkeypatch):
    from geo_optimizer.web.app import app

    monkeypatch.delenv("CRON_SECRET", raising=False)
    with TestClient(app) as client:
        assert client.get("/api/v1/search-connections/scheduled-sync").status_code == 403
        assert (
            client.get("/api/v1/search-connections/scheduled-sync", headers={"Authorization": "Bearer "}).status_code
            == 403
        )


def test_scheduler_syncs_only_due_verified_connections(monkeypatch, oauth_config):
    from geo_optimizer.web.app import app

    monkeypatch.setenv("CRON_SECRET", "scheduler-secret")
    store = Mock()
    store.list_search_connections.return_value = [
        {"org_id": 1, "domain": "example.com", "provider": "google", "last_synced_at": None},
        {
            "org_id": 2,
            "domain": "example.net",
            "provider": "bing",
            "last_synced_at": datetime.now(timezone.utc).isoformat(),
        },
    ]
    service = Mock(store=store)
    with (
        patch("geo_optimizer.web.platform_routes._get_service", return_value=service),
        patch("geo_optimizer.saas.search_connections.sync_connection") as sync,
        TestClient(app) as client,
    ):
        response = client.get(
            "/api/v1/search-connections/scheduled-sync", headers={"Authorization": "Bearer scheduler-secret"}
        )
    assert response.json() == {"synced": 1, "failed": 0}
    service._require_verified.assert_called_once_with(1, "example.com")
    sync.assert_called_once()


def test_oauth_callback_requires_state_and_stores_no_plaintext(tmp_path, oauth_config):
    from geo_optimizer.web.app import app
    from geo_optimizer.web.platform_routes import require_token, require_write_token

    store = PlatformStore(tmp_path / "platform.db")
    service = Mock(store=store)
    service.require_verified_domain.return_value = "example.com"
    service.require_session.return_value = (Mock(), Mock(org_id=1))
    app.dependency_overrides[require_token] = lambda: "session-token"
    app.dependency_overrides[require_write_token] = lambda: "session-token"
    try:
        with (
            patch("geo_optimizer.web.platform_routes._get_service", return_value=service),
            patch(
                "geo_optimizer.saas.search_connections.exchange_code",
                return_value={"access_token": "access", "refresh_token": "refresh-secret"},
            ),
            patch("geo_optimizer.saas.search_connections.select_property", return_value="sc-domain:example.com"),
            patch("geo_optimizer.saas.search_connections.sync_connection"),
            TestClient(app, base_url="https://example.test") as client,
        ):
            start = client.post(
                "/api/v1/search-connections/start", json={"domain": "example.com", "provider": "google"}
            )
            assert start.status_code == 200
            bad = client.get(
                "/api/v1/search-connections/callback/google",
                params={"code": "code", "state": "wrong"},
                follow_redirects=False,
            )
            assert bad.headers["location"].endswith("search_connection=failed")
            assert store.list_search_connections(1) == []
            start = client.post(
                "/api/v1/search-connections/start", json={"domain": "example.com", "provider": "google"}
            )
            state = parse_qs(urlparse(start.json()["authorization_url"]).query)["state"][0]
            result = client.get(
                "/api/v1/search-connections/callback/google",
                params={"code": "code", "state": state},
                follow_redirects=False,
            )
            assert result.headers["location"].endswith("search_connection=connected")
            assert "refresh-secret" not in store.list_search_connections(1)[0]["encrypted_refresh_token"]
            assert "refresh-secret" not in result.text
    finally:
        app.dependency_overrides.pop(require_token, None)
        app.dependency_overrides.pop(require_write_token, None)
