from __future__ import annotations

from click.testing import CliRunner

from geo_optimizer.cli.main import cli
from geo_optimizer.core.scoring import compute_score_breakdown
from geo_optimizer.models.results import (
    AiDiscoveryResult,
    AuditResult,
    BrandEntityResult,
    ContentResult,
    LlmsTxtResult,
    MetaResult,
    NegativeSignalsResult,
    RobotsResult,
    SchemaResult,
    SignalsResult,
    TrustStackResult,
)


def test_scoring_breakdown_keeps_core_categories():
    breakdown = compute_score_breakdown(
        robots=RobotsResult(),
        llms=LlmsTxtResult(),
        schema=SchemaResult(),
        meta=MetaResult(),
        content=ContentResult(),
        signals=SignalsResult(),
        ai_discovery=AiDiscoveryResult(),
        brand_entity=BrandEntityResult(),
    )
    assert set(breakdown.keys()) == {
        "robots",
        "llms",
        "schema",
        "meta",
        "content",
        "signals",
        "ai_discovery",
        "brand_entity",
    }


def test_audit_result_exposes_ai_discovery_trust_and_negative_sections():
    result = AuditResult(url="https://example.com")
    assert isinstance(result.ai_discovery, AiDiscoveryResult)
    assert isinstance(result.trust_stack, TrustStackResult)
    assert isinstance(result.negative_signals, NegativeSignalsResult)


def test_cli_help_keeps_audit_and_fix_flow():
    runner = CliRunner()
    out = runner.invoke(cli, ["--help"])
    assert out.exit_code == 0
    assert "audit" in out.output
    assert "fix" in out.output


def test_cli_keeps_upstream_baseline_commands():
    """Guard: preserve canonical upstream user workflow commands."""
    runner = CliRunner()
    out = runner.invoke(cli, ["--help"])
    assert out.exit_code == 0

    for cmd in (
        "audit",
        "diff",
        "history",
        "monitor",
        "snapshots",
        "track",
        "fix",
        "llms",
        "schema",
    ):
        assert cmd in out.output


def test_cli_is_superset_with_enhanced_commands():
    """Guard: ensure our branch remains strictly more capable than baseline."""
    runner = CliRunner()
    out = runner.invoke(cli, ["--help"])
    assert out.exit_code == 0

    for cmd in (
        "autopilot",
        "apply",
        "rivalry",
        "visibility-audit",
        "citation-optimizer",
        "presence-monitor",
    ):
        assert cmd in out.output


def test_audit_formats_cover_ci_and_human_use_cases():
    runner = CliRunner()
    out = runner.invoke(cli, ["audit", "--help"])
    assert out.exit_code == 0

    for fmt in ("text", "json", "rich", "html", "github", "sarif", "junit"):
        assert fmt in out.output
