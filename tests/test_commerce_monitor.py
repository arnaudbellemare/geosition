from dataclasses import dataclass
from unittest.mock import patch

from click.testing import CliRunner

from geo_optimizer.cli.main import cli


@dataclass
class Report:
    url: str
    pages: list
    coverage: dict
    recommendations: list
    failures: list
    skipped: list
    warnings: list


def sample(price="CAD $20", label="Contact", complete=True, render="rendered"):
    return Report(
        "https://example.com/",
        [
            {
                "url": "https://example.com/",
                "render_status": render,
                "catalog_signals": [{"name": "Hat", "price_text": price}],
                "products": [],
                "journey_signals": [
                    {"kind": "enquiry", "label": label, "element": "link", "url": "https://example.com/contact"}
                ],
            }
        ],
        {
            "complete": complete,
            "pending": 0 if complete else 5,
            "render_requested": True,
            "pages_audited": 1,
            "max_pages": 10,
        },
        [{"id": "verify-journey"}],
        [],
        [],
        [],
    )


def test_monitor_persists_baseline_and_reports_observed_changes(tmp_path):
    db = tmp_path / "history.db"
    args = [
        "commerce-monitor",
        "--url",
        "https://example.com/",
        "--db",
        str(db),
        "--max-pages",
        "10",
        "--render",
        "--format",
        "json",
    ]
    with (
        patch("geo_optimizer.core.commerce_monitor.run_site_audit", side_effect=[sample(), sample("CAD $25")]),
        patch("geo_optimizer.core.commerce_monitor.probe_journey_destinations", return_value=[]),
    ):
        first = CliRunner().invoke(cli, args)
        second = CliRunner().invoke(cli, args)
    assert first.exit_code == second.exit_code == 0, first.output + second.output
    import json

    assert json.loads(first.output)["baseline"] is True
    change = json.loads(second.output)["changes"][0]
    assert change["type"] == "displayed_price_changed"
    assert change["before"] == "CAD $20" and change["after"] == "CAD $25"


def test_incomplete_render_or_missing_page_is_unknown_not_regression():
    from dataclasses import asdict

    from geo_optimizer.core.commerce_monitor import compare_reports

    previous = asdict(sample())
    current = asdict(sample(label="Different", complete=False, render="failed"))
    result = compare_reports(previous, current)
    assert not result["changes"]
    assert result["unknowns"]
    current["pages"] = []
    result = compare_reports(previous, current)
    assert not result["changes"]
    assert result["unknowns"]


def test_failed_scan_does_not_replace_last_good_snapshot(tmp_path):
    import json

    db = tmp_path / "history.db"
    args = [
        "commerce-monitor",
        "--url",
        "https://example.com/",
        "--db",
        str(db),
        "--max-pages",
        "10",
        "--render",
        "--format",
        "json",
    ]
    with (
        patch(
            "geo_optimizer.core.commerce_monitor.run_site_audit",
            side_effect=[sample(), ValueError("timeout"), sample("CAD $25")],
        ),
        patch("geo_optimizer.core.commerce_monitor.probe_journey_destinations", return_value=[]),
    ):
        assert CliRunner().invoke(cli, args).exit_code == 0
        failed = CliRunner().invoke(cli, args)
        recovered = CliRunner().invoke(cli, args)
    assert failed.exit_code != 0
    assert "timeout" in failed.output
    assert json.loads(recovered.output)["changes"][0]["before"] == "CAD $20"


def test_contact_probe_only_fetches_same_origin_contact_links():
    from unittest.mock import Mock

    from geo_optimizer.core.commerce_monitor import probe_journey_destinations

    report = {
        "url": "https://example.com/",
        "pages": [
            {
                "journey_signals": [
                    {"kind": "enquiry", "element": "link", "url": "https://example.com/contact"},
                    {"kind": "enquiry", "element": "link", "url": "https://example.com/contact?send=yes"},
                    {"kind": "enquiry", "element": "link", "url": "https://other.example/contact"},
                    {"kind": "enquiry", "element": "link", "url": "https://example.com/checkout"},
                    {"kind": "enquiry", "element": "button", "url": None},
                ]
            }
        ],
    }
    with patch(
        "geo_optimizer.core.commerce_monitor.fetch_url",
        return_value=(Mock(status_code=200, url="https://example.com/contact"), None),
    ) as fetch:
        probes = probe_journey_destinations(report)
    assert fetch.call_count == 1
    assert fetch.call_args.args[0] == "https://example.com/contact"
    assert probes[0]["status"] == "reachable"
    assert "delivery not tested" in probes[0]["detail"]


def test_product_field_presence_change_uses_matching_page_and_name():
    from dataclasses import asdict

    from geo_optimizer.core.commerce_monitor import compare_reports

    previous, current = asdict(sample()), asdict(sample())
    previous["pages"][0]["products"] = [{"name": "Hat", "fields": {"price": True, "availability": True}}]
    current["pages"][0]["products"] = [{"name": "Hat", "fields": {"price": True, "availability": False}}]
    changes = compare_reports(previous, current)["changes"]
    assert any(c["type"] == "product_field_no_longer_observed" and c["field"] == "availability" for c in changes)


def test_watch_retries_after_a_transient_scan_failure(tmp_path):
    from geo_optimizer.core.commerce_monitor import MonitorScanError
    from geo_optimizer.models.results.commerce_monitor import CommerceMonitorResult

    result = CommerceMonitorResult("https://example.com/", "now", True, {"complete": True})
    with (
        patch(
            "geo_optimizer.cli.commerce_monitor_cmd.run_commerce_monitor",
            side_effect=[MonitorScanError("temporary timeout"), result],
        ) as run,
        patch("geo_optimizer.cli.commerce_monitor_cmd.time.sleep", side_effect=[None, KeyboardInterrupt]),
    ):
        output = CliRunner().invoke(
            cli,
            [
                "commerce-monitor",
                "--url",
                "https://example.com/",
                "--db",
                str(tmp_path / "db"),
                "--watch",
                "--interval-seconds",
                "60",
            ],
        )
    assert run.call_count == 2
    assert "temporary timeout" in output.output
    assert "Baseline recorded" in output.output


def test_monitor_compares_contact_reachability_without_claiming_delivery(tmp_path):
    import json

    db = tmp_path / "history.db"
    args = [
        "commerce-monitor",
        "--url",
        "https://example.com/",
        "--db",
        str(db),
        "--max-pages",
        "10",
        "--render",
        "--format",
        "json",
    ]
    first_probe = [
        {
            "url": "https://example.com/contact",
            "status": "reachable",
            "detail": "GET returned a page; delivery not tested",
        }
    ]
    second_probe = [{"url": "https://example.com/contact", "status": "not_verified", "detail": "timeout"}]
    with (
        patch("geo_optimizer.core.commerce_monitor.run_site_audit", side_effect=[sample(), sample()]),
        patch(
            "geo_optimizer.core.commerce_monitor.probe_journey_destinations", side_effect=[first_probe, second_probe]
        ),
    ):
        assert CliRunner().invoke(cli, args).exit_code == 0
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    report = json.loads(result.output)
    assert any(item["type"] == "contact_page_no_longer_verified" for item in report["changes"])
    assert any("could not be verified" in item for item in report["unknowns"])


def test_first_snapshot_reports_incomplete_coverage_and_render_failure(tmp_path):
    import json

    db = tmp_path / "history.db"
    args = [
        "commerce-monitor",
        "--url",
        "https://example.com/",
        "--db",
        str(db),
        "--max-pages",
        "10",
        "--render",
        "--format",
        "json",
    ]
    with (
        patch(
            "geo_optimizer.core.commerce_monitor.run_site_audit", return_value=sample(complete=False, render="failed")
        ),
        patch("geo_optimizer.core.commerce_monitor.probe_journey_destinations", return_value=[]),
    ):
        result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    unknowns = json.loads(result.output)["unknowns"]
    assert any("coverage" in item.lower() for item in unknowns)
    assert any("render" in item.lower() for item in unknowns)


def test_monitor_reports_catalog_card_disappearance_as_an_observation():
    from dataclasses import asdict

    from geo_optimizer.core.commerce_monitor import compare_reports

    previous, current = asdict(sample()), asdict(sample())
    current["pages"][0]["catalog_signals"] = []
    changes = compare_reports(previous, current)["changes"]
    assert any(item["type"] == "catalog_card_not_observed" and item["item"] == "Hat" for item in changes)
