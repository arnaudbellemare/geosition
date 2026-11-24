from unittest.mock import Mock, patch

from click.testing import CliRunner

from geo_optimizer.cli.main import cli


def response(text, url="https://example.com/"):
    return Mock(status_code=200, text=text, url=url, headers={})


def test_site_audit_follows_same_origin_sitemap_and_links_with_coverage():
    pages = {
        "https://example.com/robots.txt": response("User-agent: *\nDisallow: /private\n"),
        "https://example.com/sitemap.xml": response(
            "<urlset><url><loc>https://example.com/service</loc></url></urlset>"
        ),
        "https://example.com/": response(
            '<a href="/shop">Shop</a><a href="/private">Private</a><a href="https://other.example/">Other</a>'
        ),
        "https://example.com/service": response(
            '<script type="application/ld+json">{"@type":"Service","name":"Repair"}</script>',
            "https://example.com/service",
        ),
        "https://example.com/shop": response("<button>Cart</button>", "https://example.com/shop"),
    }

    def fetch(url, **kwargs):
        return (pages[url], None) if url in pages else (None, "unexpected")

    with patch("geo_optimizer.core.commerce_site.fetch_url", side_effect=fetch):
        result = CliRunner().invoke(
            cli, ["commerce-audit", "--url", "https://example.com/", "--site", "--max-pages", "3", "--format", "json"]
        )
    assert result.exit_code == 0, result.output
    import json

    report = json.loads(result.output)
    assert len(report["pages"]) == 3
    assert any(page["services"] == ["Repair"] for page in report["pages"])
    assert all("other.example" not in page["url"] and "/private" not in page["url"] for page in report["pages"])
    assert report["coverage"]["pages_audited"] == 3


def test_site_audit_includes_rendered_catalog_signals_and_render_failure():
    pages = {
        "https://example.com/robots.txt": response("User-agent: *\nAllow: /"),
        "https://example.com/sitemap.xml": (None, "missing"),
        "https://example.com/": response('<div id="grid"></div>'),
    }

    def fetch(url, **kwargs):
        value = pages.get(url, (None, "unexpected"))
        return value if isinstance(value, tuple) else (value, None)

    rendered = '<div class="card"><h3>Painting</h3><div class="price">CAD $900</div></div>'
    with (
        patch("geo_optimizer.core.commerce_site.fetch_url", side_effect=fetch),
        patch("geo_optimizer.core.commerce_site.render_page", return_value=(rendered, [])),
    ):
        result = CliRunner().invoke(
            cli,
            [
                "commerce-audit",
                "--url",
                "https://example.com/",
                "--site",
                "--render",
                "--max-pages",
                "1",
                "--format",
                "json",
            ],
        )
    assert result.exit_code == 0, result.output
    import json

    report = json.loads(result.output)
    assert report["pages"][0]["render_status"] == "rendered"
    assert report["pages"][0]["catalog_signals"][0]["name"] == "Painting"
    with (
        patch("geo_optimizer.core.commerce_site.fetch_url", side_effect=fetch),
        patch("geo_optimizer.core.commerce_site.render_page", return_value=(None, ["browser unavailable"])),
    ):
        result = CliRunner().invoke(
            cli,
            [
                "commerce-audit",
                "--url",
                "https://example.com/",
                "--site",
                "--render",
                "--max-pages",
                "1",
                "--format",
                "json",
            ],
        )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["pages"][0]["render_status"] == "failed"


def test_renderer_fetches_only_same_origin_scripts_and_reports_missing_assets():
    from geo_optimizer.core.commerce_site import render_page

    html = '<script src="https://other.example/track.js"></script><script src="/app.js"></script>'
    proc = Mock(returncode=0, stdout='{"html":"<p>rendered</p>"}')
    with (
        patch(
            "geo_optimizer.core.commerce_site.fetch_url",
            return_value=(response("code", "https://example.com/app.js"), None),
        ) as fetch,
        patch("geo_optimizer.core.commerce_site.subprocess.run", return_value=proc),
    ):
        rendered, warnings = render_page("https://example.com/", html)
    assert rendered == "<p>rendered</p>"
    assert fetch.call_count == 1
    assert fetch.call_args.args[0] == "https://example.com/app.js"
    assert "Cross-origin scripts were not loaded." in warnings


def test_site_fetch_failure_returns_nonzero():
    with patch("geo_optimizer.core.commerce_site.fetch_url", return_value=(None, "DNS failed")):
        result = CliRunner().invoke(cli, ["commerce-audit", "--url", "https://example.com/", "--site"])
    assert result.exit_code != 0
    assert "DNS failed" in result.output
