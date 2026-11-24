from unittest.mock import Mock, patch

from click.testing import CliRunner

from geo_optimizer.cli.main import cli


def test_product_report_checks_each_product_and_marks_external_facts_unknown():
    html = """<script type="application/ld+json">{"@graph":[
      {"@type":"Product","name":"Hat","image":"hat.jpg","offers":{"price":0,"priceCurrency":"CAD","availability":"InStock"}},
      {"@type":"Product","name":"Coat","offers":{"price":"25"}}
    ]}</script><a href="/cart">Cart</a>"""
    response = Mock(status_code=200, text=html)
    with patch("geo_optimizer.core.commerce_readiness.fetch_url", return_value=(response, None)):
        result = CliRunner().invoke(cli, ["commerce-audit", "--url", "https://example.com/item", "--format", "json"])
    assert result.exit_code == 0, result.output
    import json

    report = json.loads(result.output)
    assert len(report["products"]) == 2
    assert report["products"][0]["fields"]["price"] is True
    assert report["products"][1]["fields"]["currency"] is False
    assert report["manual_checks"]["feed_submission"] == "unknown"
    assert report["manual_checks"]["verified_browser_access"] == "unknown"
    assert report["journey_signals"][0]["kind"] == "cart"


def test_service_page_does_not_fail_for_absent_products():
    html = '<script type="application/ld+json">{"@type":"Service","name":"Repair"}</script><a href="/book">Book</a>'
    response = Mock(status_code=200, text=html)
    with patch("geo_optimizer.core.commerce_readiness.fetch_url", return_value=(response, None)):
        result = CliRunner().invoke(cli, ["commerce-audit", "--url", "https://example.com", "--format", "json"])
    assert result.exit_code == 0, result.output
    import json

    report = json.loads(result.output)
    assert report["products"] == []
    assert report["services"] == ["Repair"]
    assert report["journey_signals"][0]["kind"] == "booking"


def test_failed_fetch_is_reported_and_never_analyzed():
    with patch("geo_optimizer.core.commerce_readiness.fetch_url", return_value=(None, "blocked")):
        result = CliRunner().invoke(cli, ["commerce-audit", "--url", "https://example.com"])
    assert result.exit_code != 0
    assert "blocked" in result.output


def test_local_addresses_are_rejected_by_public_command():
    result = CliRunner().invoke(cli, ["commerce-audit", "--url", "http://127.0.0.1/private"])
    assert result.exit_code != 0
    assert "Unsafe URL" in result.output


def test_nested_services_and_button_journey_signals_are_reported():
    html = """<script type="application/ld+json">{"@graph":[{"@type":"ItemList",
      "itemListElement":[{"@type":"ListItem","item":{"@type":"Service","name":"Gestion locative"}}]}]}</script>
      <button>Cart <span>0</span></button><button>Enquire / Checkout</button>
      <a href="/contact">Demande de proposition</a>"""
    response = Mock(status_code=200, text=html)
    with patch("geo_optimizer.core.commerce_readiness.fetch_url", return_value=(response, None)):
        result = CliRunner().invoke(cli, ["commerce-audit", "--url", "https://example.com", "--format", "json"])
    assert result.exit_code == 0, result.output
    import json

    report = json.loads(result.output)
    assert report["services"] == ["Gestion locative"]
    assert [(s["kind"], s["element"]) for s in report["journey_signals"]] == [
        ("cart", "button"),
        ("enquiry", "button"),
        ("enquiry", "link"),
    ]
    assert report["journey_signals"][0]["url"] is None


def test_nested_products_do_not_duplicate_and_unknown_is_not_missing():
    html = """<script type="application/ld+json">{"@graph":[{"@type":"ItemList",
      "itemListElement":[{"item":{"@type":"Product","name":"Painting"}}]}]}</script>"""
    response = Mock(status_code=200, text=html)
    with patch("geo_optimizer.core.commerce_readiness.fetch_url", return_value=(response, None)):
        result = CliRunner().invoke(cli, ["commerce-audit", "--url", "https://example.com", "--format", "json"])
    assert result.exit_code == 0, result.output
    import json

    report = json.loads(result.output)
    assert len(report["products"]) == 1
    assert report["products"][0]["fields"]["price"] is False
    assert report["manual_checks"]["prices_and_availability_current"] == "unknown"


def test_same_service_id_across_jsonld_scripts_is_reported_once():
    html = """<script type="application/ld+json">{"@type":"Service","@id":"https://example.com/#repair","name":"Repair"}</script>
    <script type="application/ld+json">{"@type":"Service","@id":"https://example.com/#repair","name":"Repair"}</script>"""
    response = Mock(status_code=200, text=html)
    with patch("geo_optimizer.core.commerce_readiness.fetch_url", return_value=(response, None)):
        result = CliRunner().invoke(cli, ["commerce-audit", "--url", "https://example.com", "--format", "json"])
    assert result.exit_code == 0, result.output
    import json

    assert json.loads(result.output)["services"] == ["Repair"]
