from __future__ import annotations

import json
from unittest.mock import Mock, patch

import pytest
from bs4 import BeautifulSoup

from geo_optimizer.core.audit_commerce import audit_commerce
from geo_optimizer.core.search_measurement import fetch_search_measurement, validate_property


@pytest.mark.parametrize(
    "provider,property_id", [("google", "sc-domain:example.com"), ("bing", "https://example.com/")]
)
def test_property_must_match_verified_domain(provider, property_id):
    validate_property(provider, property_id, "example.com")
    with pytest.raises(ValueError):
        validate_property(provider, property_id, "other.example")


def test_google_search_data_uses_read_only_fixed_endpoint_without_redirects():
    response = Mock(status_code=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.iter_content.return_value = [json.dumps({"rows": [{"clicks": 3, "impressions": 12}]}).encode()]
    with patch("geo_optimizer.core.search_measurement.requests.post", return_value=response) as post:
        result = fetch_search_measurement(
            "google", "sc-domain:example.com", "temporary-token", "2026-01-01", "2026-01-30"
        )
    assert result["metric_scope"] == "search_traffic_not_ai_citations"
    assert result["rows"][0]["clicks"] == 3
    assert "temporary-token" not in json.dumps(result)
    assert post.call_args.kwargs["allow_redirects"] is False
    assert post.call_args.kwargs["headers"]["Authorization"] == "Bearer temporary-token"
    assert post.call_args.args[0].startswith("https://www.googleapis.com/")


def test_bing_search_data_not_mislabelled_as_ai_citations():
    response = Mock(status_code=200)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.iter_content.return_value = [b'{"d":[{"Clicks":2,"Impressions":10}]}']
    with patch("geo_optimizer.core.search_measurement.requests.get", return_value=response) as get:
        result = fetch_search_measurement("bing", "https://example.com/", "temporary-token", "2026-01-01", "2026-01-30")
    assert result["metric_scope"] == "search_traffic_not_ai_citations"
    assert result["rows"][0]["Clicks"] == 2
    assert get.call_args.kwargs["allow_redirects"] is False


def test_commerce_checks_do_not_fabricate_feed_status_or_reviews():
    soup = BeautifulSoup(
        '<script type="application/ld+json">'
        '{"@type":"Product","name":"Hat","image":"https://example.com/hat.jpg",'
        '"offers":{"price":0,"priceCurrency":"USD","availability":"InStock"}}'
        "</script>",
        "html.parser",
    )
    result = audit_commerce(soup)
    checks = {row["key"]: row for row in result["checks"]}
    assert checks["price"]["present"]
    assert checks["currency"]["present"]
    assert checks["availability"]["present"]
    assert result["feed_status"] == "not_checked"
    assert all("review" not in recommendation.lower() for recommendation in result["recommendations"])


def test_non_product_page_is_not_reported_as_failed_commerce():
    result = audit_commerce(BeautifulSoup("<h1>About</h1>", "html.parser"))
    assert result["applicable"] is False
    assert result["checks"] == []


def test_measurement_route_checks_verified_domain_before_calling_provider():
    from fastapi.testclient import TestClient

    from geo_optimizer.web.app import app
    from geo_optimizer.web.platform_routes import require_expensive_write_token

    app.dependency_overrides[require_expensive_write_token] = lambda: "session-token"
    service = Mock()
    service.require_verified_domain.side_effect = ValueError("Domain not verified")
    body = {
        "domain": "example.com",
        "provider": "google",
        "property_id": "sc-domain:example.com",
        "access_token": "temporary-token",
        "start_date": "2026-01-01",
        "end_date": "2026-01-30",
    }
    try:
        with (
            patch("geo_optimizer.web.platform_routes._get_service", return_value=service),
            patch("geo_optimizer.core.search_measurement.fetch_search_measurement") as fetch,
            TestClient(app) as client,
        ):
            response = client.post("/api/v1/measurement/search", json=body)
        assert response.status_code == 400
        fetch.assert_not_called()
    finally:
        app.dependency_overrides.pop(require_expensive_write_token, None)


def test_measurement_route_returns_uncached_provider_results():
    from fastapi.testclient import TestClient

    from geo_optimizer.web.app import app
    from geo_optimizer.web.platform_routes import require_expensive_write_token

    app.dependency_overrides[require_expensive_write_token] = lambda: "session-token"
    service = Mock()
    service.require_verified_domain.return_value = "example.com"
    body = {
        "domain": "example.com",
        "provider": "google",
        "property_id": "sc-domain:example.com",
        "access_token": "temporary-token",
        "start_date": "2026-01-01",
        "end_date": "2026-01-30",
    }
    try:
        with (
            patch("geo_optimizer.web.platform_routes._get_service", return_value=service),
            patch("geo_optimizer.core.search_measurement.fetch_search_measurement", return_value={"rows": []}) as fetch,
            TestClient(app) as client,
        ):
            response = client.post("/api/v1/measurement/search", json=body)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "temporary-token" not in response.text
        fetch.assert_called_once()
    finally:
        app.dependency_overrides.pop(require_expensive_write_token, None)
