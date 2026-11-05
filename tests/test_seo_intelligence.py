from __future__ import annotations

import csv

from click.testing import CliRunner

from geo_optimizer.cli.main import cli
from geo_optimizer.core.seo_intelligence import (
    CsvBacklinkProvider,
    LocalBacklinkDiscoveryProvider,
    RankTracker,
    _parse_lighthouse_json,
    research_keywords,
    score_serp_crowdedness,
)


def test_research_keywords_exports_metrics_and_csv(tmp_path):
    csv_path = tmp_path / "keywords.csv"

    result = research_keywords("ai visibility", limit=3, csv_path=str(csv_path))

    assert result.checked is True
    assert len(result.metrics) == 3
    assert result.metrics[0].volume > 0
    assert result.metrics[0].intent in {"informational", "commercial", "transactional", "navigational"}
    assert csv_path.exists()
    assert "keyword,volume,cpc,competition,difficulty,intent,trend,source" in csv_path.read_text()


def test_score_serp_crowdedness_labels_competitive_serp():
    result = score_serp_crowdedness(
        keyword="best seo software",
        organic_results=10,
        competitor_domains=[f"competitor{i}.example" for i in range(8)],
        serp_features=["faq", "video", "images"],
        ads_count=2,
    )

    assert result.checked is True
    assert result.score >= 75
    assert result.label == "very crowded"


def test_csv_backlink_provider_aggregates_referring_domains_and_anchors(tmp_path):
    path = tmp_path / "backlinks.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["source_url", "target_url", "anchor", "link_strength", "first_seen", "last_seen", "status"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "source_url": "https://partner.example/post",
                "target_url": "https://brand.example/page",
                "anchor": "brand guide",
                "link_strength": "42",
                "first_seen": "2026-01-01",
                "last_seen": "2026-01-02",
                "status": "live",
            }
        )
        writer.writerow(
            {
                "source_url": "https://partner.example/old",
                "target_url": "https://brand.example/page",
                "anchor": "brand guide",
                "link_strength": "10",
                "first_seen": "2026-01-01",
                "last_seen": "2026-02-01",
                "status": "lost",
            }
        )

    result = CsvBacklinkProvider(str(path)).analyze("brand.example")

    assert result.checked is True
    assert len(result.backlinks) == 2
    assert result.referring_domains[0].domain == "partner.example"
    assert result.referring_domains[0].backlinks == 2
    assert result.anchors["brand guide"] == 2
    assert result.new_lost_history[-1].lost_links == 1


def test_local_backlink_discovery_lists_candidate_mentions(monkeypatch):
    class Response:
        text = """
        <html><body>
          <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fpartner.example%2Fvelora-review">
            Gestion Velora review
          </a>
        </body></html>
        """

    monkeypatch.setattr("geo_optimizer.core.seo_intelligence.fetch_url", lambda url, timeout=15: (Response(), None))

    result = LocalBacklinkDiscoveryProvider().analyze("gestionvelora.com")

    assert result.checked is True
    assert result.provider == "local-discovery"
    assert len(result.backlinks) == 1
    assert result.backlinks[0].source_domain == "partner.example"
    assert result.backlinks[0].status == "candidate"


def test_pagespeed_error_does_not_parse_as_zero_scores():
    result = _parse_lighthouse_json(
        "https://example.com",
        {
            "error": {
                "code": 429,
                "status": "RESOURCE_EXHAUSTED",
                "message": "Quota exceeded",
            }
        },
        provider="pagespeed",
    )

    assert result.checked is False
    assert result.performance_score == 0
    assert "Quota exceeded" in result.warnings[0]


def test_rank_tracker_adds_keywords_and_reports_analytics(tmp_path, monkeypatch):
    monkeypatch.setattr("geo_optimizer.core.seo_intelligence.validate_public_url", lambda url: (True, None))
    tracker = RankTracker(tmp_path / "rank.db")

    tracker.add_keyword("geosition", "https://example.com/page")
    result = tracker.analytics()

    assert result.checked is True
    assert len(result.tracked_keywords) == 1
    assert result.tracked_keywords[0].keyword == "geosition"
    assert result.db_path.endswith("rank.db")


def test_cli_seo_keywords_outputs_json(tmp_path):
    runner = CliRunner()
    csv_path = tmp_path / "kw.csv"

    result = runner.invoke(cli, ["seo", "keywords", "--seed", "geo audit", "--limit", "2", "--csv", str(csv_path), "--format", "json"])

    assert result.exit_code == 0
    assert '"seed": "geo audit"' in result.output
    assert csv_path.exists()
