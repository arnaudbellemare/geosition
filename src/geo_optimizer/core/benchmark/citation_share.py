"""Citation share and co-occurrence metrics per task and provider."""

from __future__ import annotations

from collections import defaultdict

from geo_optimizer.core.benchmark.domains import normalize_benchmark_domain
from geo_optimizer.models.results.benchmark import (
    CitationSnapshotRecord,
    CompetitorMentionRecord,
    TaskCitationMetrics,
)


def compute_task_citation_metrics(
    snapshots: list[CitationSnapshotRecord],
    mentions_by_snapshot: dict[int, list[CompetitorMentionRecord]],
    *,
    target_domain: str,
    competitor_domains: list[str],
) -> list[TaskCitationMetrics]:
    """Compute citation share metrics grouped by task and provider."""
    target = normalize_benchmark_domain(target_domain)
    competitors = [normalize_benchmark_domain(item) for item in competitor_domains]
    grouped: dict[tuple[str, str], list[CitationSnapshotRecord]] = defaultdict(list)
    for snapshot in snapshots:
        provider = snapshot.provider or "unknown"
        grouped[(snapshot.task, provider)].append(snapshot)

    metrics: list[TaskCitationMetrics] = []
    for (task, provider), group in sorted(grouped.items()):
        sample_size = len(group)
        target_cited = 0
        positions: list[int] = []
        url_freq: dict[str, int] = defaultdict(int)
        brand_mentions = 0
        competitor_counts: dict[str, int] = dict.fromkeys(competitors, 0)
        beside = 0
        instead = 0

        for snapshot in group:
            cited_domains = []
            for url in snapshot.cited_urls:
                host = normalize_benchmark_domain(url)
                if host:
                    cited_domains.append(host)
                    url_freq[url] += 1

            snapshot_mentions = mentions_by_snapshot.get(snapshot.snapshot_id, [])
            target_record = next(
                (m for m in snapshot_mentions if normalize_benchmark_domain(m.competitor_domain) == target),
                None,
            )
            if target_record and target_record.cited:
                target_cited += 1
                if target_record.position:
                    positions.append(target_record.position)
            if target_record and target_record.mentioned:
                brand_mentions += 1

            competitor_cited = [
                normalize_benchmark_domain(m.competitor_domain)
                for m in snapshot_mentions
                if normalize_benchmark_domain(m.competitor_domain) in competitors and m.cited
            ]
            for domain in competitor_cited:
                competitor_counts[domain] = competitor_counts.get(domain, 0) + 1

            if target in cited_domains and competitor_cited:
                beside += 1
            if competitor_cited and target not in cited_domains:
                instead += 1

        metrics.append(
            TaskCitationMetrics(
                task=task,
                provider=provider,
                sample_size=sample_size,
                target_cited_count=target_cited,
                citation_rate=round(target_cited / sample_size, 3) if sample_size else 0.0,
                avg_citation_position=round(sum(positions) / len(positions), 2) if positions else None,
                source_url_frequency=dict(url_freq),
                brand_mention_rate=round(brand_mentions / sample_size, 3) if sample_size else 0.0,
                competitor_mention_rates={
                    domain: round(competitor_counts.get(domain, 0) / sample_size, 3) if sample_size else 0.0
                    for domain in competitors
                },
                cited_beside_target=beside,
                cited_instead_of_target=instead,
            )
        )
    return metrics
