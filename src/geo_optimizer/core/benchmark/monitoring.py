"""AI answer monitoring summaries for benchmark runs."""

from __future__ import annotations

from geo_optimizer.core.benchmark.domains import normalize_benchmark_domain
from geo_optimizer.models.results.benchmark import (
    BenchmarkRunRecord,
    CitationShareSummary,
    CitationSnapshotRecord,
    CompetitorMentionRecord,
)


def _matches_domain(url_or_domain: str, domain: str) -> bool:
    candidate = normalize_benchmark_domain(url_or_domain)
    normalized = normalize_benchmark_domain(domain)
    return candidate == normalized or candidate.endswith(f".{normalized}")


def build_citation_share_summary(
    run: BenchmarkRunRecord,
    snapshots: list[CitationSnapshotRecord],
    mentions: list[CompetitorMentionRecord],
) -> CitationShareSummary:
    """Build a founder-friendly latest-run summary from stored benchmark data."""
    sample_size = len(snapshots)
    target_cited_count = sum(
        1 for snapshot in snapshots if any(_matches_domain(url, run.domain) for url in snapshot.cited_urls)
    )

    top_sources: dict[str, int] = {}
    for snapshot in snapshots:
        for url in snapshot.cited_urls:
            source_domain = normalize_benchmark_domain(url)
            if not source_domain:
                continue
            top_sources[source_domain] = top_sources.get(source_domain, 0) + 1
    top_sources = dict(sorted(top_sources.items(), key=lambda item: (-item[1], item[0]))[:10])

    cited_by_domain: dict[str, int] = {}
    mentioned_by_domain: dict[str, int] = {}
    for mention in mentions:
        domain = normalize_benchmark_domain(mention.competitor_domain)
        if domain == run.domain:
            continue
        if mention.cited:
            cited_by_domain[domain] = cited_by_domain.get(domain, 0) + 1
        if mention.mentioned:
            mentioned_by_domain[domain] = mentioned_by_domain.get(domain, 0) + 1

    denominator = float(sample_size or 1)
    competitor_domains = sorted(set(cited_by_domain) | set(mentioned_by_domain))
    competitor_citation_rates = {domain: cited_by_domain.get(domain, 0) / denominator for domain in competitor_domains}
    competitor_mention_rates = {
        domain: mentioned_by_domain.get(domain, 0) / denominator for domain in competitor_domains
    }

    return CitationShareSummary(
        domain=run.domain,
        run_id=run.run_id,
        run_at=run.run_at,
        benchmark_score=run.benchmark_score,
        band=run.band,
        scoring_version=run.breakdown.scoring_version,
        evidence_coverage=run.breakdown.measured_weight,
        sample_size=sample_size,
        target_cited_count=target_cited_count,
        target_citation_rate=target_cited_count / denominator,
        provider_coverage=run.provider_coverage,
        competitor_citation_rates=competitor_citation_rates,
        competitor_mention_rates=competitor_mention_rates,
        top_cited_sources=top_sources,
    )
