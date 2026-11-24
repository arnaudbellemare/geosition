from unittest.mock import Mock, patch

from click.testing import CliRunner

from geo_optimizer.cli.main import cli


def test_product_report_has_evidenced_recommendations_and_markdown():
    response = Mock(status_code=200, url="https://example.com/", text="<p>Store</p>")

    def fetch(url, **kwargs):
        if url.endswith("robots.txt"):
            return Mock(status_code=200, text="User-agent: *\nAllow: /"), None
        if url.endswith("sitemap.xml"):
            return None, "missing"
        return response, None

    html = '<div class="card"><h3>Painting</h3><div class="price">CAD $900</div></div><button>Cart</button>'
    with (
        patch("geo_optimizer.core.commerce_site.fetch_url", side_effect=fetch),
        patch("geo_optimizer.core.commerce_site.render_page", return_value=(html, [])),
    ):
        result = CliRunner().invoke(
            cli,
            [
                "commerce-audit",
                "--url",
                "https://example.com/",
                "--site",
                "--render",
                "--format",
                "json",
            ],
        )
    assert result.exit_code == 0, result.output
    import json

    report = json.loads(result.output)
    recs = {rec["id"]: rec for rec in report["recommendations"]}
    assert recs["catalog-structured-data"]["evidence_urls"] == ["https://example.com/"]
    assert "1" in recs["catalog-structured-data"]["evidence"]
    assert "verify-journey" in recs
    assert "review-product-feed" in recs
    assert "verify-browser-access" in recs
    with (
        patch("geo_optimizer.core.commerce_site.fetch_url", side_effect=fetch),
        patch("geo_optimizer.core.commerce_site.render_page", return_value=(html, [])),
    ):
        markdown = CliRunner().invoke(
            cli,
            [
                "commerce-audit",
                "--url",
                "https://example.com/",
                "--site",
                "--render",
                "--format",
                "markdown",
            ],
        )
    assert markdown.exit_code == 0, markdown.output
    assert "## Recommended actions" in markdown.output
    assert "https://example.com/" in markdown.output
    assert "not verified" in markdown.output.lower()


def test_service_report_does_not_assume_missing_products_are_failure():
    from geo_optimizer.core.commerce_recommendations import build_site_recommendations

    report = {
        "pages": [
            {
                "url": "https://example.com/services",
                "products": [],
                "catalog_signals": [],
                "services": ["Repair"],
                "journey_signals": [{"kind": "enquiry"}],
                "render_status": "rendered",
                "render_warnings": [],
            }
        ],
        "coverage": {"complete": False, "pending": 5, "pages_audited": 1},
        "failures": [],
        "skipped": [],
    }
    recs = {rec["id"]: rec for rec in build_site_recommendations(report)}
    assert "catalog-structured-data" not in recs
    assert "review-product-feed" not in recs
    assert "verify-journey" in recs
    assert "enquiry" in recs["verify-journey"]["evidence"]
    assert "purchase" not in recs["verify-journey"]["action"]
    assert "complete-coverage" in recs
    assert "5" in recs["complete-coverage"]["evidence"]
