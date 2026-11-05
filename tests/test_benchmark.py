"""Tests for domain GEO benchmark layer."""

from __future__ import annotations

import json
from unittest.mock import patch

from click.testing import CliRunner

from geo_optimizer.cli.benchmark_formatter import (
    build_benchmark_decision_plan,
    format_benchmark_json,
    format_benchmark_text,
)
from geo_optimizer.core.benchmark.citation_share import compute_task_citation_metrics
from geo_optimizer.core.benchmark.competitor_matrix import build_competitor_substitution_matrix
from geo_optimizer.core.benchmark.runner import build_negotiation_report, run_domain_benchmark
from geo_optimizer.core.benchmark.store import BenchmarkStore
from geo_optimizer.core.benchmark.task_classifier import classify_prompt
from geo_optimizer.models.results import AuditResult
from geo_optimizer.models.results.benchmark import (
    BenchmarkRunResult,
    CitationSnapshotRecord,
    CompetitorMentionRecord,
    TaskCitationMetrics,
)


def test_task_classifier_vendor_selection():
    """Vendor-selection prompts match expected task with signals."""
    result = classify_prompt("Which provider is best to compare condo management vendors?")
    assert result.task == "vendor_selection"
    assert result.confidence >= 0.5
    assert result.signals


def test_benchmark_store_run_persistence(tmp_path):
    """Full benchmark run persists snapshots and aggregate run."""
    store = BenchmarkStore(tmp_path / "benchmark.db")
    answers = [
        {
            "prompt": "Best condo management company in Montreal?",
            "answer_text": "Velora https://velora.example is strong. Also see https://rivala.example and https://rivalb.example.",
            "provider": "perplexity",
            "model": "sonar",
            "citation_urls": ["https://velora.example", "https://rivala.example"],
        },
        {
            "prompt": "Compare condo management pricing providers",
            "answer_text": "For pricing, https://rivala.example leads; https://velora.example is mentioned.",
            "provider": "chatgpt",
            "model": "gpt-4",
        },
    ]
    with patch("geo_optimizer.core.benchmark.runner.run_full_audit") as mock_audit:
        mock_audit.return_value = AuditResult(url="https://velora.example", error="skip")
        result = run_domain_benchmark(
            "velora.example",
            competitors=["rivala.example", "rivalb.example"],
            answers=answers,
            store=store,
            save_prompts=True,
        )

    assert result.run_id > 0
    assert 0 <= result.benchmark_score <= 100
    assert result.task_metrics
    assert result.provider_coverage == {"chatgpt": 1, "perplexity": 1}
    assert result.competitor_matrix.rows
    assert result.citation_economics.sample_size == 2
    assert store.get_benchmark_run(result.run_id) is not None
    snapshots = store.get_snapshots_for_run(result.run_id)
    assert len(snapshots) == 2

    summary = store.get_latest_citation_share_summary("velora.example")
    assert summary is not None
    assert summary.scoring_version == "evidence-v2"
    assert summary.evidence_coverage == result.breakdown.measured_weight
    assert summary.sample_size == 2
    assert summary.target_cited_count == 2
    assert summary.target_citation_rate == 1.0
    assert summary.provider_coverage == {"chatgpt": 1, "perplexity": 1}
    assert summary.competitor_citation_rates["rivala.example"] == 1.0
    assert summary.top_cited_sources["rivala.example"] == 2


def test_citation_share_metrics_target_and_competitors():
    """Citation rate and competitor rates reflect snapshot mentions."""
    snapshots = [
        CitationSnapshotRecord(
            snapshot_id=1,
            provider="p1",
            task="recommendation",
            cited_urls=["https://velora.example"],
            prompt_text="best tool",
            answer_text="",
        ),
        CitationSnapshotRecord(
            snapshot_id=2,
            provider="p1",
            task="recommendation",
            cited_urls=["https://rivala.example"],
            prompt_text="best tool",
            answer_text="",
        ),
    ]
    mentions = {
        1: [
            CompetitorMentionRecord(competitor_domain="velora.example", cited=True, mentioned=True, position=1),
            CompetitorMentionRecord(competitor_domain="rivala.example", cited=False, mentioned=False, position=0),
        ],
        2: [
            CompetitorMentionRecord(competitor_domain="velora.example", cited=False, mentioned=True, position=0),
            CompetitorMentionRecord(competitor_domain="rivala.example", cited=True, mentioned=True, position=1),
        ],
    }
    metrics = compute_task_citation_metrics(
        snapshots,
        mentions,
        target_domain="velora.example",
        competitor_domains=["rivala.example"],
    )
    assert len(metrics) == 1
    assert metrics[0].sample_size == 2
    assert metrics[0].target_cited_count == 1
    assert metrics[0].citation_rate == 0.5


def test_citation_share_normalizes_www_apex_for_target_and_competitors():
    """Apex and leading-www hosts count as the same benchmark domain."""
    snapshots = [
        CitationSnapshotRecord(
            snapshot_id=1,
            provider="p1",
            task="recommendation",
            cited_urls=["https://www.velora.example/page"],
            prompt_text="best tool",
            answer_text="",
        ),
        CitationSnapshotRecord(
            snapshot_id=2,
            provider="p1",
            task="recommendation",
            cited_urls=["https://www.rivala.example/page"],
            prompt_text="best tool",
            answer_text="",
        ),
    ]
    mentions = {
        1: [
            CompetitorMentionRecord(competitor_domain="www.velora.example", cited=True, mentioned=True, position=1),
            CompetitorMentionRecord(competitor_domain="www.rivala.example", cited=False, mentioned=False, position=0),
        ],
        2: [
            CompetitorMentionRecord(competitor_domain="www.velora.example", cited=False, mentioned=True, position=0),
            CompetitorMentionRecord(competitor_domain="www.rivala.example", cited=True, mentioned=True, position=1),
        ],
    }

    metrics = compute_task_citation_metrics(
        snapshots,
        mentions,
        target_domain="velora.example",
        competitor_domains=["rivala.example"],
    )

    assert metrics[0].target_cited_count == 1
    assert metrics[0].competitor_mention_rates["rivala.example"] == 0.5


def test_competitor_matrix_rows():
    """Matrix rows expose target vs competitor rates per task."""
    from geo_optimizer.models.results.benchmark import TaskCitationMetrics

    metrics = [
        TaskCitationMetrics(
            task="local",
            provider="all",
            sample_size=10,
            target_cited_count=4,
            citation_rate=0.4,
            competitor_mention_rates={"rivala.example": 0.7},
        )
    ]
    matrix = build_competitor_substitution_matrix(
        metrics,
        target_domain="velora.example",
        competitor_domains=["rivala.example"],
    )
    assert matrix.rows[0].target_rate == 0.4
    assert matrix.rows[0].competitor_rates["rivala.example"] == 0.7


def test_negotiation_report_actions():
    """Report builder surfaces gaps and competitor absence flags."""
    from geo_optimizer.models.results.benchmark import (
        BenchmarkRunResult,
        CompetitorMatrixRow,
        CompetitorSubstitutionMatrix,
        TaskGap,
    )

    result = BenchmarkRunResult(
        domain="velora.example",
        task_gaps=[
            TaskGap(task="pricing", ai_demand_rate=0.5, page_coverage_score=0.1, gap_severity="high", recommendation="Add pricing page")
        ],
        competitor_matrix=CompetitorSubstitutionMatrix(
            target_domain="velora.example",
            competitor_domains=["rivala.example"],
            rows=[
                CompetitorMatrixRow(
                    task="pricing",
                    target_rate=0.0,
                    competitor_rates={"rivala.example": 0.5},
                    target_absent_should_present=True,
                )
            ],
        ),
    )
    report = build_negotiation_report(result)
    assert any("pricing" in action for action in report.recommended_actions)


def test_benchmark_cli_run_json(tmp_path):
    """CLI run accepts answers file and emits JSON."""
    db_path = tmp_path / "bench.db"
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(
        json.dumps(
            [
                {
                    "prompt": "Best GEO optimizer?",
                    "answer_text": "Try https://velora.example for GEO.",
                    "provider": "test",
                    "model": "mock",
                }
            ]
        ),
        encoding="utf-8",
    )
    from geo_optimizer.cli.main import cli

    runner = CliRunner()
    from geo_optimizer.models.results.benchmark import (
        BenchmarkRunResult,
        BenchmarkScoreBreakdown,
        CompetitorSubstitutionMatrix,
        UniqueValueAssessment,
    )

    with patch("geo_optimizer.cli.benchmark_cmd.run_domain_benchmark") as mock_run:
        mock_run.return_value = BenchmarkRunResult(
            benchmark_score=68,
            band="visible",
            domain="velora.example",
            run_id=1,
            run_at="2026-06-03",
            executive_summary="test",
            breakdown=BenchmarkScoreBreakdown(
                citation_share=25,
                task_coverage=20,
                competitor_position=15,
                unique_value=15,
                domain_backlink=10,
                serp_rank=10,
                technical_performance=5,
            ),
            competitor_matrix=CompetitorSubstitutionMatrix(target_domain="velora.example"),
            unique_value=UniqueValueAssessment(unique_value_score=60, commodity_risk="medium", summary="ok"),
        )
        result = runner.invoke(
            cli,
            [
                "benchmark",
                "run",
                "velora.example",
                "--answers-file",
                str(answers_path),
                "--no-audit",
                "--format",
                "json",
                "--benchmark-db",
                str(db_path),
            ],
        )
    assert result.exit_code == 0
    assert json.loads(result.output)["decision_plan"]["status"] == "unmeasured"


def test_benchmark_decision_plan_branches():
    """Benchmark output tells users whether to monitor, fix gatekeepers, or fix retrieval."""
    top = BenchmarkRunResult(
        task_metrics=[
            TaskCitationMetrics(sample_size=1, target_cited_count=1, citation_rate=1.0, avg_citation_position=1.0)
        ]
    )
    cited = BenchmarkRunResult(
        task_metrics=[
            TaskCitationMetrics(sample_size=1, target_cited_count=1, citation_rate=1.0, avg_citation_position=3.0)
        ]
    )
    uncited = BenchmarkRunResult(
        task_metrics=[TaskCitationMetrics(sample_size=1, target_cited_count=0, citation_rate=0.0)]
    )

    assert build_benchmark_decision_plan(top)["status"] == "cited"
    assert build_benchmark_decision_plan(cited)["fix_order"] == [
        "review_citations",
        "improve_relevant_pages",
        "retest",
    ]
    assert build_benchmark_decision_plan(uncited)["fix_order"] == [
        "crawlability",
        "indexability",
        "ranking",
        "query_page_match",
    ]
    assert "Benchmark decision plan" in format_benchmark_text(cited)
    assert json.loads(format_benchmark_json(uncited))["decision_plan"]["status"] == "not_cited"


def test_citation_economics_selection_premium():
    """Target cited more often than its presence footprint earns a selection premium."""
    from geo_optimizer.core.benchmark.citation_economics import compute_citation_economics

    snapshots = [
        CitationSnapshotRecord(
            snapshot_id=1,
            task="vendor_selection",
            cited_urls=["https://velora.example/page-a"],
            prompt_text="best vendor",
            answer_text="",
        ),
        CitationSnapshotRecord(
            snapshot_id=2,
            task="vendor_selection",
            cited_urls=["https://velora.example/page-a"],
            prompt_text="choose vendor",
            answer_text="",
        ),
        CitationSnapshotRecord(
            snapshot_id=3,
            task="discovery",
            cited_urls=["https://rivala.example/page-b"],
            prompt_text="what is",
            answer_text="",
        ),
        CitationSnapshotRecord(
            snapshot_id=4,
            task="discovery",
            cited_urls=[],
            prompt_text="overview",
            answer_text="",
        ),
    ]
    mentions = {
        4: [
            CompetitorMentionRecord(competitor_domain="rivala.example", cited=False, mentioned=True, position=0),
        ],
    }

    result = compute_citation_economics(
        snapshots,
        target_domain="velora.example",
        competitor_domains=["rivala.example"],
        mentions_by_snapshot=mentions,
    )

    assert result.sample_size == 4
    assert result.selection_premium > 1.0
    assert result.selection_label == "selected"
    assert result.most_cited_pages[0].url == "https://velora.example/page-a"
    assert result.most_cited_pages[0].citation_count == 2


def test_citation_economics_value_concentration_high_value_task():
    """Citations on high-value tasks raise value concentration above 1."""
    from geo_optimizer.core.benchmark.citation_economics import compute_citation_economics

    snapshots = [
        CitationSnapshotRecord(
            snapshot_id=1,
            task="vendor_selection",
            cited_urls=["https://velora.example"],
            prompt_text="choose vendor",
            answer_text="",
        ),
        CitationSnapshotRecord(
            snapshot_id=2,
            task="discovery",
            cited_urls=["https://rivala.example"],
            prompt_text="what is",
            answer_text="",
        ),
    ]

    result = compute_citation_economics(
        snapshots,
        target_domain="velora.example",
        competitor_domains=["rivala.example"],
    )

    assert result.value_concentration > 1.0
    assert result.value_label == "valued"


def test_citation_economics_uniqueness_solo_citation():
    """Solo citations in an answer raise uniqueness above the sample average."""
    from geo_optimizer.core.benchmark.citation_economics import compute_citation_economics

    snapshots = [
        CitationSnapshotRecord(
            snapshot_id=1,
            task="comparison",
            cited_urls=["https://velora.example"],
            prompt_text="compare",
            answer_text="",
        ),
        CitationSnapshotRecord(
            snapshot_id=2,
            task="comparison",
            cited_urls=["https://rivala.example", "https://rivalb.example"],
            prompt_text="compare",
            answer_text="",
        ),
    ]

    result = compute_citation_economics(
        snapshots,
        target_domain="velora.example",
        competitor_domains=["rivala.example", "rivalb.example"],
    )

    assert result.uniqueness_index > 1.0
    assert result.uniqueness_label in {"unique", "defensible"}


def test_benchmark_formatter_includes_citation_economics():
    """Text formatter surfaces the three economics ratios."""
    from geo_optimizer.cli.benchmark_formatter import format_benchmark_text
    from geo_optimizer.models.results.benchmark import BenchmarkRunResult, CitationEconomicsResult

    text = format_benchmark_text(
        BenchmarkRunResult(
            domain="velora.example",
            citation_economics=CitationEconomicsResult(
                target_domain="velora.example",
                sample_size=5,
                selection_premium=1.14,
                selection_label="selected",
                selection_summary="Agents cite velora.example at a premium.",
                value_concentration=0.79,
                value_label="undervalued",
                value_summary="Citations skew toward lower-value queries.",
                uniqueness_index=1.06,
                uniqueness_label="defensible",
                uniqueness_summary="Content is defensible.",
                most_cited_pages=[],
            ),
        )
    )

    assert "Citation economics:" in text
    assert "Selection premium: 1.14x (SELECTED)" in text
    assert "Value concentration: 0.79x (UNDERVALUED)" in text


def test_collection_error_is_safe_and_excluded_from_benchmark(tmp_path):
    from geo_optimizer.core.collection.normalize import batch_to_benchmark_answers, load_canonical_batch
    from geo_optimizer.core.collection.pipeline import collect_and_normalize
    from geo_optimizer.core.collection.store import CollectionArtifactStore
    from geo_optimizer.models.results.collection import PromptSpec

    class FailingAdapter:
        provider_id = "gemini"
        surface = "gemini_grounding"
        collection_mode = "api"

        def collect(self, request):
            assert request.language == "fr"
            raise RuntimeError("sensitive-test-value")

    with patch("geo_optimizer.core.collection.pipeline.get_adapter", return_value=FailingAdapter()):
        batch = collect_and_normalize(
            target_domain="example.com",
            prompts=[PromptSpec(prompt_id="p1", query_text="Bonjour", language="fr")],
            providers=["gemini"],
            artifact_store=CollectionArtifactStore(base_dir=tmp_path, org_slug="test"),
        )
    assert batch.answers[0].status == "error"
    assert batch.answers[0].language == "fr"
    assert batch_to_benchmark_answers(batch) == []
    saved = next(tmp_path.rglob("*.json"))
    assert "sensitive-test-value" not in saved.read_text()
    assert load_canonical_batch(saved).answers[0].error_code == "collection_failed"


def test_benchmark_legacy_error_and_word_substrings_are_not_evidence():
    from geo_optimizer.core.benchmark.competitors import extract_competitor_mentions
    from geo_optimizer.core.collection.normalize import batch_from_dict, batch_to_benchmark_answers

    batch = batch_from_dict({"answers": [{"prompt": "question", "answer_text": "[collection error: secret]"}]})
    assert batch.answers[0].status == "error"
    assert batch.answers[0].answer_text == ""
    assert batch_to_benchmark_answers(batch) == []
    mentions = extract_competitor_mentions("This is a good option.", target_domain="on.com", competitors=[])
    assert not mentions[0].mentioned
    mentions = extract_competitor_mentions("Put the product on the shelf.", target_domain="on.com", competitors=[])
    assert not mentions[0].mentioned


def test_benchmark_scoring_excludes_unmeasured_components():
    from geo_optimizer.core.benchmark.score import aggregate_benchmark_score
    from geo_optimizer.models.results.benchmark import CompetitorSubstitutionMatrix, UniqueValueAssessment

    score, _, breakdown = aggregate_benchmark_score(
        task_metrics=[TaskCitationMetrics(task="discovery", provider="test", sample_size=1, citation_rate=0.5)],
        matrix=CompetitorSubstitutionMatrix(),
        unique_value=UniqueValueAssessment(unique_value_score=40),
    )
    assert breakdown.domain_backlink is None
    assert breakdown.serp_rank is None
    assert breakdown.technical_performance is None
    assert breakdown.competitor_position is None
    assert breakdown.scoring_version == "evidence-v2"
    assert breakdown.measured_weight == 0.6
    assert score == round((50 * 0.25 + 12 * 0.2 + 40 * 0.15) / 0.6)


def test_collection_provider_alias_targets_requested_surface():
    from geo_optimizer.core.collection.adapters import get_adapter

    assert get_adapter("chatgpt").platform == "chatgpt"
    assert get_adapter("google_ai").platform == "google_ai"


def test_benchmark_empty_or_zero_citations_never_claim_top_recommendation():
    from geo_optimizer.core.benchmark.score import _competitor_position_score
    from geo_optimizer.models.results.benchmark import CompetitorMatrixRow, CompetitorSubstitutionMatrix

    matrix = CompetitorSubstitutionMatrix(
        competitor_domains=["rival.example"],
        rows=[CompetitorMatrixRow(task="discovery", target_rate=0, competitor_rates={"rival.example": 0})],
    )
    assert _competitor_position_score(matrix) is None
    assert build_benchmark_decision_plan(BenchmarkRunResult())["status"] == "unmeasured"


def test_no_site_audit_does_not_invent_unique_value():
    from geo_optimizer.core.benchmark.unique_value import assess_unique_value

    result = assess_unique_value(None, [])
    assert result.unique_value_score is None
    assert result.commodity_risk == "unknown"


def test_benchmark_uses_actual_audit_result_fields():
    from geo_optimizer.core.benchmark.page_task import map_audit_to_page_coverage
    from geo_optimizer.core.benchmark.unique_value import assess_unique_value

    audit = AuditResult(url="http://example.com/pricing")
    audit.meta.title_text = "Local pricing"
    audit.meta.description_text = "Compare plans for your business"
    audit.schema.any_schema_found = True
    audit.brand_entity.names_found = ["Example"]

    page = map_audit_to_page_coverage(audit)
    assessment = assess_unique_value(audit, [page])

    assert page.schema_support is True
    assert page.serp_alignment == 75
    assert "HTTPS not enforced" in page.performance_blockers
    assert "structured schema present" in assessment.positive_signals
    assert "entity/organization signals" in assessment.positive_signals
