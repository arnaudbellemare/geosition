"""Competitor substitution matrix across tasks."""

from __future__ import annotations

from geo_optimizer.models.results.benchmark import (
    CompetitorMatrixRow,
    CompetitorSubstitutionMatrix,
    TaskCitationMetrics,
)


def build_competitor_substitution_matrix(
    task_metrics: list[TaskCitationMetrics],
    *,
    target_domain: str,
    competitor_domains: list[str],
    demand_threshold: float = 0.15,
) -> CompetitorSubstitutionMatrix:
    """Aggregate per-task citation rates into a substitution matrix."""
    by_task: dict[str, list[TaskCitationMetrics]] = {}
    for metric in task_metrics:
        by_task.setdefault(metric.task, []).append(metric)

    rows: list[CompetitorMatrixRow] = []
    for task in sorted(by_task):
        group = by_task[task]
        sample = sum(item.sample_size for item in group) or 1
        target_count = sum(item.target_cited_count for item in group)
        target_rate = round(target_count / sample, 3)

        competitor_rates: dict[str, float] = {}
        for domain in competitor_domains:
            cited = 0
            for item in group:
                cited += int(item.competitor_mention_rates.get(domain, 0.0) * item.sample_size)
            competitor_rates[domain] = round(cited / sample, 3)

        avg_demand = sum(item.citation_rate + sum(item.competitor_mention_rates.values()) for item in group) / len(
            group
        )
        absent = target_rate < demand_threshold and avg_demand >= demand_threshold

        rows.append(
            CompetitorMatrixRow(
                task=task,
                target_rate=target_rate,
                competitor_rates=competitor_rates,
                target_absent_should_present=absent,
            )
        )

    return CompetitorSubstitutionMatrix(
        target_domain=target_domain,
        competitor_domains=list(competitor_domains),
        rows=rows,
    )
