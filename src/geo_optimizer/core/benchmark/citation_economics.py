"""Citation economics: selection premium, value concentration, and uniqueness.

These metrics extend raw citation share with demand-side economics, answering
three questions a domain owner cares about:

1. Selection premium  — "Am I chosen above my footprint?"
   citation share divided by surface (presence) share. A value above 1 means the
   domain converts presence into citations more efficiently than the field.

2. Value concentration — "Am I winning on high-value work?"
   the average task value of the answers that cite the domain, divided by the
   average task value across the whole sample. Above 1 means citations skew
   toward higher-value (deep research / decision) queries.

3. Uniqueness index    — "Could they have found that value elsewhere?"
   the domain's citation exclusivity (1 / distinct domains cited in the same
   answer) divided by the sample-wide average exclusivity. Above 1 means the
   domain tends to be cited in answers with fewer competing sources, i.e. it is
   harder to substitute.

The module is pure: it consumes ``CitationSnapshotRecord`` objects and returns a
``CitationEconomicsResult`` dataclass. No I/O, no formatting.
"""

from __future__ import annotations

from collections import defaultdict

from geo_optimizer.core.benchmark.domains import normalize_benchmark_domain
from geo_optimizer.models.config import (
    CITATION_ECONOMICS_THRESHOLDS,
    CITATION_ECONOMICS_TOP_PAGES,
    TASK_VALUE_DEFAULT,
    TASK_VALUE_WEIGHTS,
)
from geo_optimizer.models.results.benchmark import (
    CitationEconomicsResult,
    CitationSnapshotRecord,
    CitedPageRecord,
    CompetitorMentionRecord,
    DomainEconomics,
)


def _host_from_url(url: str) -> str:
    return normalize_benchmark_domain(url)


def _task_value(task: str) -> float:
    return TASK_VALUE_WEIGHTS.get(task, TASK_VALUE_DEFAULT)


def _round(value: float, digits: int = 3) -> float:
    return round(value, digits)


def compute_citation_economics(
    snapshots: list[CitationSnapshotRecord],
    *,
    target_domain: str,
    competitor_domains: list[str] | None = None,
    mentions_by_snapshot: dict[int, list[CompetitorMentionRecord]] | None = None,
) -> CitationEconomicsResult:
    """Compute selection / value / uniqueness economics for ``target_domain``.

    Args:
        snapshots: AI answer snapshots (one per provider/prompt response).
        target_domain: The domain whose economics we report on.
        competitor_domains: Optional tracked competitors (used for footprint via
            mentions, even when they are not cited via URL).
        mentions_by_snapshot: Optional competitor/target mention records keyed by
            ``snapshot_id``. Mentions enrich the "presence" footprint so a domain
            that is mentioned but not cited still counts toward surface share.
    """
    target = normalize_benchmark_domain(target_domain)
    competitors = [normalize_benchmark_domain(item) for item in (competitor_domains or []) if item]
    mentions_by_snapshot = mentions_by_snapshot or {}

    sample_size = len(snapshots)

    cited_count: dict[str, int] = defaultdict(int)
    present_count: dict[str, int] = defaultdict(int)
    exclusivity_sum: dict[str, float] = defaultdict(float)

    cited_value_sum: dict[str, float] = defaultdict(float)
    platform_value_sum = 0.0

    total_citations = 0
    sample_exclusivity_sum = 0.0
    sample_exclusivity_n = 0

    # Most-cited pages aggregation.
    page_count: dict[str, int] = defaultdict(int)
    page_positions: dict[str, list[int]] = defaultdict(list)
    page_tasks: dict[str, set] = defaultdict(set)

    for snapshot in snapshots:
        task_value = _task_value(snapshot.task)
        platform_value_sum += task_value

        cited_domains: list[str] = []
        positions_by_url = dict(zip(snapshot.cited_urls, snapshot.citation_positions))
        for url in snapshot.cited_urls:
            host = _host_from_url(url)
            if not host:
                continue
            cited_domains.append(host)
            total_citations += 1
            page_count[url] += 1
            position = positions_by_url.get(url, 0)
            if position:
                page_positions[url].append(position)
            if snapshot.task:
                page_tasks[url].add(snapshot.task)

        distinct_cited = set(cited_domains)
        n_distinct = len(distinct_cited)
        exclusivity = (1.0 / n_distinct) if n_distinct else 0.0

        # Presence footprint from mentions (cited OR mentioned).
        present_domains = set(distinct_cited)
        for mention in mentions_by_snapshot.get(snapshot.snapshot_id, []):
            if mention.cited or mention.mentioned:
                present_domains.add(normalize_benchmark_domain(mention.competitor_domain))

        for domain in present_domains:
            present_count[domain] += 1
        for domain in distinct_cited:
            cited_count[domain] += 1
            cited_value_sum[domain] += task_value
            exclusivity_sum[domain] += exclusivity
            sample_exclusivity_sum += exclusivity
            sample_exclusivity_n += 1

    total_cited_domain_hits = sum(cited_count.values())
    total_present_domain_hits = sum(present_count.values())
    platform_avg_value = (platform_value_sum / sample_size) if sample_size else 0.0
    platform_avg_exclusivity = sample_exclusivity_sum / sample_exclusivity_n if sample_exclusivity_n else 0.0

    domain_universe = set(cited_count) | set(present_count) | {target} | set(competitors)
    domain_universe.discard("")

    domains: list[DomainEconomics] = []
    for domain in sorted(domain_universe):
        cited = cited_count.get(domain, 0)
        present = present_count.get(domain, 0)
        citation_share = (cited / total_cited_domain_hits) if total_cited_domain_hits else 0.0
        surface_share = (present / total_present_domain_hits) if total_present_domain_hits else 0.0
        selection_premium = (citation_share / surface_share) if surface_share else 0.0

        cited_avg_value = (cited_value_sum.get(domain, 0.0) / cited) if cited else 0.0
        value_concentration = (cited_avg_value / platform_avg_value) if platform_avg_value else 0.0

        domain_avg_excl = (exclusivity_sum.get(domain, 0.0) / cited) if cited else 0.0
        uniqueness_index = (domain_avg_excl / platform_avg_exclusivity) if platform_avg_exclusivity else 0.0

        domains.append(
            DomainEconomics(
                domain=domain,
                is_target=(domain == target),
                cited_snapshots=cited,
                present_snapshots=present,
                citation_share=_round(citation_share),
                surface_share=_round(surface_share),
                selection_premium=_round(selection_premium, 2),
                value_concentration=_round(value_concentration, 2),
                uniqueness_index=_round(uniqueness_index, 2),
            )
        )

    domains.sort(key=lambda item: (not item.is_target, -item.citation_share, item.domain))

    target_econ = next((d for d in domains if d.is_target), None)

    most_cited_pages = _build_most_cited_pages(page_count, page_positions, page_tasks)

    result = CitationEconomicsResult(
        target_domain=target,
        sample_size=sample_size,
        total_citations=total_citations,
        domains=domains,
        most_cited_pages=most_cited_pages,
    )

    if target_econ is not None:
        result.selection_premium = target_econ.selection_premium
        result.value_concentration = target_econ.value_concentration
        result.uniqueness_index = target_econ.uniqueness_index

    _apply_labels_and_summaries(result, target_present=target_econ is not None and target_econ.cited_snapshots > 0)
    return result


def _build_most_cited_pages(
    page_count: dict[str, int],
    page_positions: dict[str, list[int]],
    page_tasks: dict[str, set],
) -> list[CitedPageRecord]:
    records: list[CitedPageRecord] = []
    for url, count in page_count.items():
        positions = page_positions.get(url, [])
        avg_position = round(sum(positions) / len(positions), 2) if positions else None
        records.append(
            CitedPageRecord(
                url=url,
                domain=_host_from_url(url),
                citation_count=count,
                avg_position=avg_position,
                tasks=sorted(page_tasks.get(url, set())),
            )
        )
    records.sort(key=lambda item: (-item.citation_count, item.url))
    return records[:CITATION_ECONOMICS_TOP_PAGES]


def _label(value: float, high: float, low: float, strong: str, middle: str, weak: str) -> str:
    if value >= high:
        return strong
    if value <= low:
        return weak
    return middle


def _apply_labels_and_summaries(result: CitationEconomicsResult, *, target_present: bool) -> None:
    thresholds = CITATION_ECONOMICS_THRESHOLDS
    domain = result.target_domain or "Your domain"

    if not target_present:
        result.selection_label = "overlooked"
        result.value_label = "undervalued"
        result.uniqueness_label = "substitutable"
        result.selection_summary = f"{domain} was not cited in this sample, so it earns no selection premium yet."
        result.value_summary = f"{domain} has no cited answers to weight by query value."
        result.uniqueness_summary = f"{domain} has no citations to assess for substitutability."
        return

    result.selection_label = _label(
        result.selection_premium,
        thresholds["selection_high"],
        thresholds["selection_low"],
        "selected",
        "neutral",
        "overlooked",
    )
    result.value_label = _label(
        result.value_concentration,
        thresholds["value_high"],
        thresholds["value_low"],
        "valued",
        "balanced",
        "undervalued",
    )
    result.uniqueness_label = _label(
        result.uniqueness_index,
        thresholds["uniqueness_high"],
        thresholds["uniqueness_low"],
        "unique",
        "defensible",
        "substitutable",
    )

    premium_pct = abs(result.selection_premium - 1.0) * 100
    if result.selection_label == "selected":
        result.selection_summary = (
            f"Agents cite {domain} at a {premium_pct:.0f}% premium above its presence footprint. "
            "Its content earns selection beyond where it merely appears, a strong credibility signal."
        )
    elif result.selection_label == "overlooked":
        result.selection_summary = (
            f"{domain} is cited {premium_pct:.0f}% below its presence footprint. It appears in the "
            "field more often than it gets chosen, so credibility or formatting may be holding it back."
        )
    else:
        result.selection_summary = f"{domain} is cited roughly in line with its presence footprint."

    if result.value_label == "valued":
        result.value_summary = (
            f"{domain}'s citations concentrate on higher-value queries than the sample average, "
            "so it is present where the work is hardest and most valuable."
        )
    elif result.value_label == "undervalued":
        result.value_summary = (
            f"{domain}'s citations skew toward lower-value queries than average. It shows up mostly "
            "in quick lookups rather than deep research; more depth could lift its high-value footprint."
        )
    else:
        result.value_summary = (
            f"{domain}'s citations are spread evenly across query value, tracking the sample average."
        )

    if result.uniqueness_label == "unique":
        result.uniqueness_summary = (
            f"{domain} is usually cited alongside few other sources, so its value is hard to find "
            "elsewhere. It reads as irreplaceable rather than one option among many."
        )
    elif result.uniqueness_label == "substitutable":
        result.uniqueness_summary = (
            f"{domain} is typically cited alongside many overlapping sources, so agents could likely "
            "find the same value elsewhere. It risks being treated as a commodity source."
        )
    else:
        result.uniqueness_summary = (
            f"{domain}'s exclusivity roughly tracks the sample average, which indicates its content is "
            "defensible and not easily substitutable."
        )
