import csv
import json

from click.testing import CliRunner

from geo_optimizer.cli.main import cli


def test_guided_preparation_keeps_observed_prices_separate_and_creates_review_artifacts(
    tmp_path,
):
    audit = {
        "url": "https://shop.example/",
        "audit_date": "2026-11-13",
        "pages": [
            {
                "url": "https://shop.example/shop",
                "catalog_signals": [{"name": "Painting", "price_text": "CAD $900.00"}],
            }
        ],
    }
    source = tmp_path / "audit.json"
    source.write_text(json.dumps(audit))
    output = tmp_path / "draft"
    result = CliRunner().invoke(cli, ["commerce-prepare", "--audit", str(source), "--output-dir", str(output)])
    assert result.exit_code == 0, result.output
    catalog = json.loads((output / "catalog-review.json").read_text())
    item = catalog["items"][0]
    assert item["name"] == "Painting"
    assert item["observed_price_text"] == "CAD $900.00"
    assert item["price"] == "" and item["availability"] == "" and item["rights_confirmed"] is False
    schema = json.loads((output / "product-structured-data.draft.jsonld").read_text())
    assert schema["@graph"][0]["name"] == "Painting"
    assert "offers" not in schema["@graph"][0]
    validation = json.loads((output / "validation.json").read_text())
    assert validation["items"][0]["issues"]
    assert "not a provider feed" in (output / "README.md").read_text().lower()
    with (output / "feed-worksheet.csv").open(newline="") as file:
        assert list(csv.DictReader(file))[0]["observed_price_text"] == "CAD $900.00"


def test_reviewed_catalog_can_be_regenerated_without_overwriting_source(tmp_path):
    catalog = {
        "items": [
            {
                "name": "Painting",
                "source_url": "https://shop.example/",
                "observed_price_text": "$90",
                "item_id": "123",
                "product_url": "https://shop.example/product/123",
                "description": "Original art",
                "image_url": "https://shop.example/a.jpg",
                "price": "90.00",
                "currency": "CAD",
                "availability": "InStock",
                "owner_reviewed": True,
                "rights_confirmed": True,
            }
        ]
    }
    source = tmp_path / "review.json"
    original = json.dumps(catalog)
    source.write_text(original)
    target = tmp_path / "draft"
    result = CliRunner().invoke(cli, ["commerce-prepare", "--catalog", str(source), "--output-dir", str(target)])
    assert result.exit_code == 0, result.output
    schema = json.loads((target / "product-structured-data.draft.jsonld").read_text())
    assert schema["@graph"][0]["offers"]["price"] == "90.00"
    assert schema["@graph"][0]["offers"]["availability"] == "https://schema.org/InStock"
    assert source.read_text() == original
    assert not json.loads((target / "validation.json").read_text())["items"][0]["issues"]
    rerun = CliRunner().invoke(cli, ["commerce-prepare", "--catalog", str(source), "--output-dir", str(target)])
    assert rerun.exit_code != 0


def test_no_catalog_signals_returns_explanation_without_creating_output(tmp_path):
    source = tmp_path / "empty.json"
    source.write_text('{"pages":[{"url":"https://example.com","catalog_signals":[]}]}')
    target = tmp_path / "draft"
    result = CliRunner().invoke(cli, ["commerce-prepare", "--audit", str(source), "--output-dir", str(target)])
    assert result.exit_code != 0
    assert "No product-card signals found" in result.output
    assert not target.exists()


def test_duplicate_id_invalid_price_and_unknown_stock_remain_blocked(tmp_path):
    item = {"name": "=Artwork", "item_id": "same", "price": "9,00", "availability": "available"}
    source = tmp_path / "review.json"
    source.write_text(json.dumps({"items": [item, item]}))
    target = tmp_path / "draft"
    result = CliRunner().invoke(cli, ["commerce-prepare", "--catalog", str(source), "--output-dir", str(target)])
    assert result.exit_code == 0, result.output
    issues = json.loads((target / "validation.json").read_text())["items"][0]["issues"]
    assert any("duplicated" in issue for issue in issues)
    assert any("decimal" in issue for issue in issues)
    assert any("availability" in issue for issue in issues)
    schema = json.loads((target / "product-structured-data.draft.jsonld").read_text())
    assert "offers" not in schema["@graph"][0]
    assert "sku" not in schema["@graph"][0]
    with (target / "feed-worksheet.csv").open(newline="") as file:
        assert next(csv.DictReader(file))["name"] == "'=Artwork"


def test_product_recommendation_links_to_guided_preparation():
    from geo_optimizer.core.commerce_recommendations import build_site_recommendations

    report = {
        "pages": [
            {
                "url": "https://example.com",
                "products": [],
                "catalog_signals": [{"name": "Item"}],
                "services": [],
                "journey_signals": [],
            }
        ],
        "coverage": {"complete": True},
    }
    recs = build_site_recommendations(report)
    product_rec = next(rec for rec in recs if rec["id"] == "catalog-structured-data")
    assert "geo commerce-prepare" in product_rec["guided_fix"]
