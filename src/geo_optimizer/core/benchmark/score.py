"""Aggregate GEO domain benchmark score."""

from __future__ import annotations

from geo_optimizer.models.config import BENCHMARK_BANDS, BENCHMARK_SCORE_WEIGHTS
from geo_optimizer.models.results.benchmark import (
    BenchmarkScoreBreakdown,
    CompetitorSubstitutionMatrix,
    TaskCitationMetrics,
    UniqueValueAssessment,
)


def _band_for_score(score: int) -> str:
    for band, (low, high) in BENCHMARK_BANDS.items():
        if low <= score <= high:
            return band
    return "vulnerable"


def _avg_citation_rate(metrics: list[TaskCitationMetrics]) -> float:
    if not metrics:
        return 0.0
    total = sum(item.citation_rate for item in metrics)
    return total / len(metrics)


def _competitor_position_score(matrix: CompetitorSubstitutionMatrix) -> int | None:
    rows = [
        row
        for row in matrix.rows
        if row.competitor_rates and (row.target_rate > 0 or any(rate > 0 for rate in row.competitor_rates.values()))
    ]
    if not rows:
        return None
    wins = 0
    for row in rows:
        competitor_max = max(row.competitor_rates.values())
        if row.target_rate > 0 and row.target_rate >= competitor_max:
            wins += 1
    return int(round(100 * wins / len(rows)))


def _task_coverage_score(metrics: list[TaskCitationMetrics], gap_count: int) -> int:
    tasks = {item.task for item in metrics}
    base = min(100, len(tasks) * 12)
    penalty = min(40, gap_count * 8)
    return max(0, base - penalty)


def aggregate_benchmark_score(
    *,
    task_metrics: list[TaskCitationMetrics],
    matrix: CompetitorSubstitutionMatrix,
    unique_value: UniqueValueAssessment,
    gap_count: int = 0,
    domain_backlink_score: int | None = None,
    serp_rank_score: int | None = None,
    technical_score: int | None = None,
    unique_value_measured: bool = True,
) -> tuple[int, str, BenchmarkScoreBreakdown]:
    """Compute weighted GEO benchmark score with optional component overrides."""
    breakdown = BenchmarkScoreBreakdown(
        citation_share=int(round(_avg_citation_rate(task_metrics) * 100)),
        task_coverage=_task_coverage_score(task_metrics, gap_count),
        competitor_position=_competitor_position_score(matrix),
        unique_value=unique_value.unique_value_score if unique_value_measured else None,
        domain_backlink=domain_backlink_score,
        serp_rank=serp_rank_score,
        technical_performance=technical_score,
        scoring_version="evidence-v2",
    )

    components = {
        "citation_share": breakdown.citation_share,
        "task_coverage": breakdown.task_coverage,
        "competitor_position": breakdown.competitor_position,
        "unique_value": breakdown.unique_value,
        "domain_backlink": breakdown.domain_backlink,
        "serp_rank": breakdown.serp_rank,
        "technical_performance": breakdown.technical_performance,
    }
    measured_weight = sum(weight for key, weight in BENCHMARK_SCORE_WEIGHTS.items() if components[key] is not None)
    breakdown.measured_weight = round(measured_weight, 4)
    total = sum(value * BENCHMARK_SCORE_WEIGHTS[key] for key, value in components.items() if value is not None)
    score = int(round(total / measured_weight)) if measured_weight else 0
    return score, _band_for_score(score), breakdown
