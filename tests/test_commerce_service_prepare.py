import json

from click.testing import CliRunner

from geo_optimizer.cli.main import cli


def test_service_and_enquiry_drafts_preserve_observations_and_unverified_state(tmp_path):
    audit = {
        "url": "https://example.com/",
        "pages": [
            {
                "url": "https://example.com/",
                "services": ["Management", "Management"],
                "journey_signals": [
                    {
                        "kind": "enquiry",
                        "label": "Get a proposal",
                        "element": "link",
                        "url": "https://example.com/contact",
                    }
                ],
            },
            {
                "url": "https://example.com/services",
                "services": ["Management"],
                "journey_signals": [
                    {
                        "kind": "enquiry",
                        "label": "Get a proposal",
                        "element": "link",
                        "url": "https://example.com/contact",
                    }
                ],
            },
        ],
    }
    source = tmp_path / "audit.json"
    source.write_text(json.dumps(audit))
    target = tmp_path / "draft"
    result = CliRunner().invoke(cli, ["commerce-service-prepare", "--audit", str(source), "--output-dir", str(target)])
    assert result.exit_code == 0, result.output
    review = json.loads((target / "service-review.json").read_text())
    assert len(review["services"]) == 1
    assert len(review["services"][0]["evidence_pages"]) == 2
    assert review["services"][0]["owner_reviewed"] is False
    assert review["services"][0]["service_url"] == ""
    assert review["journeys"][0]["observed_url"] == "https://example.com/contact"
    assert len(review["journeys"][0]["evidence_pages"]) == 2
    assert review["journeys"][0]["tested"] is False
    schema = json.loads((target / "service-structured-data.draft.jsonld").read_text())
    assert schema["@graph"] == [{"@type": "Service", "name": "Management"}]
    plan = (target / "enquiry-test-plan.md").read_text()
    assert "https://example.com/contact" in plan
    assert "not verified" in plan.lower()
    assert "without sending" in plan.lower()


def test_reviewed_service_regenerates_markup_without_overwriting_input(tmp_path):
    review = {
        "services": [
            {
                "name": "Management",
                "description": "Property management",
                "service_url": "https://example.com/service",
                "area_served": "Montreal",
                "provider_name": "Example",
                "owner_reviewed": True,
            }
        ],
        "journeys": [],
    }
    source = tmp_path / "review.json"
    original = json.dumps(review)
    source.write_text(original)
    target = tmp_path / "draft"
    result = CliRunner().invoke(cli, ["commerce-service-prepare", "--review", str(source), "--output-dir", str(target)])
    assert result.exit_code == 0, result.output
    item = json.loads((target / "service-structured-data.draft.jsonld").read_text())["@graph"][0]
    assert item["areaServed"] == "Montreal"
    assert item["provider"] == {"@type": "Organization", "name": "Example"}
    assert not json.loads((target / "validation.json").read_text())["services"][0]["issues"]
    assert source.read_text() == original
    assert (
        CliRunner()
        .invoke(cli, ["commerce-service-prepare", "--review", str(source), "--output-dir", str(target)])
        .exit_code
        != 0
    )


def test_empty_audit_is_rejected_and_product_recommendations_unchanged(tmp_path):
    source = tmp_path / "audit.json"
    source.write_text('{"pages":[{"services":[], "journey_signals":[]}]}')
    target = tmp_path / "draft"
    result = CliRunner().invoke(cli, ["commerce-service-prepare", "--audit", str(source), "--output-dir", str(target)])
    assert result.exit_code != 0
    assert "No service or enquiry signals" in result.output
    assert not target.exists()


def test_journey_only_review_does_not_claim_tested_and_links_from_recommendation(tmp_path):
    from geo_optimizer.core.commerce_recommendations import build_site_recommendations

    page = {
        "url": "https://example.com/",
        "services": [],
        "products": [],
        "catalog_signals": [],
        "journey_signals": [{"kind": "enquiry", "label": "Contact", "element": "button", "url": None}],
        "render_status": "rendered",
    }
    source = tmp_path / "audit.json"
    source.write_text(json.dumps({"pages": [page], "coverage": {"complete": True}}))
    target = tmp_path / "draft"
    result = CliRunner().invoke(cli, ["commerce-service-prepare", "--audit", str(source), "--output-dir", str(target)])
    assert result.exit_code == 0, result.output
    validation = json.loads((target / "validation.json").read_text())
    assert validation["journeys"][0]["issues"] == ["journey has not been marked tested"]
    assert "none captured" in (target / "enquiry-test-plan.md").read_text()
    recs = build_site_recommendations({"pages": [page], "coverage": {"complete": True}})
    journey = next(rec for rec in recs if rec["id"] == "verify-journey")
    assert "commerce-service-prepare" in journey["guided_fix"]
