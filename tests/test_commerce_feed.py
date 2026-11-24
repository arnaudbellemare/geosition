import json

from click.testing import CliRunner

from geo_optimizer.cli.main import cli


def candidate():
    return {
        "market_confirmed": False,
        "items": [
            {
                "record": {
                    "item_id": "demo-1",
                    "title": "Test painting",
                    "description": "Synthetic fixture",
                    "url": "https://example.com/shop?open=1",
                    "brand": "Example",
                    "seller_name": "Example",
                    "image_url": "https://example.com/art.jpg",
                    "price": "90.00 CAD",
                    "availability": "unknown",
                    "target_countries": ["CA"],
                    "store_country": "CA",
                },
                "owner_reviewed": False,
                "rights_confirmed": False,
            }
        ],
    }


def test_preview_emits_disabled_records_and_separate_readiness(tmp_path):
    source = tmp_path / "candidate.json"
    source.write_text(json.dumps(candidate()))
    output = tmp_path / "out"
    result = CliRunner().invoke(cli, ["commerce-feed", "--input", str(source), "--output-dir", str(output)])
    assert result.exit_code == 0, result.output
    row = json.loads((output / "discovery-feed.preview.jsonl").read_text())
    assert row["is_eligible_search"] is False
    assert row["target_countries"] == ["CA"]
    report = json.loads((output / "validation.json").read_text())
    assert report["basic_checks_passed"] is True
    assert report["ready_for_enabled_export"] is False
    assert report["limitations"]


def test_enabled_export_is_blocked_until_owner_rights_and_market_confirmed(tmp_path):
    source = tmp_path / "candidate.json"
    data = candidate()
    source.write_text(json.dumps(data))
    output = tmp_path / "out"
    result = CliRunner().invoke(
        cli, ["commerce-feed", "--input", str(source), "--output-dir", str(output), "--enable-search"]
    )
    assert result.exit_code != 0
    assert not (output / "discovery-feed.jsonl").exists()
    data["market_confirmed"] = True
    data["items"][0]["owner_reviewed"] = True
    data["items"][0]["rights_confirmed"] = True
    source.write_text(json.dumps(data))
    result = CliRunner().invoke(
        cli, ["commerce-feed", "--input", str(source), "--output-dir", str(tmp_path / "reviewed"), "--enable-search"]
    )
    assert result.exit_code == 0, result.output
    assert json.loads((tmp_path / "reviewed" / "discovery-feed.jsonl").read_text())["is_eligible_search"] is True


def test_invalid_and_duplicate_records_do_not_produce_a_feed(tmp_path):
    data = candidate()
    data["items"][0]["record"]["price"] = "CAD $0"
    data["items"].append(data["items"][0].copy())
    source = tmp_path / "bad.json"
    source.write_text(json.dumps(data))
    output = tmp_path / "out"
    result = CliRunner().invoke(cli, ["commerce-feed", "--input", str(source), "--output-dir", str(output)])
    assert result.exit_code != 0
    assert not (output / "discovery-feed.preview.jsonl").exists()
    assert "duplicate" in result.output.lower() or "duplicate" in (output / "validation.json").read_text().lower()
