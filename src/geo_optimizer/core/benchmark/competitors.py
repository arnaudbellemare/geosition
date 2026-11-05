"""Extract competitor citations and mentions from AI answers."""

from __future__ import annotations

import re

from geo_optimizer.core.benchmark.domains import normalize_benchmark_domain
from geo_optimizer.core.snapshots import extract_citations
from geo_optimizer.models.results.benchmark import CompetitorMentionRecord

_POSITIVE_RE = re.compile(r"\b(best|leading|recommended|top-rated|excellent|trusted)\b", re.I)
_NEGATIVE_RE = re.compile(r"\b(avoid|poor|unreliable|expensive|slow|bad|worse)\b", re.I)


def _sentiment_near(text: str, needle: str) -> str:
    """Rough sentiment from words near a brand/domain mention."""
    lowered = text.lower()
    idx = lowered.find(needle.lower())
    if idx < 0:
        return "neutral"
    window = text[max(0, idx - 80) : idx + 120]
    if _NEGATIVE_RE.search(window):
        return "negative"
    if _POSITIVE_RE.search(window):
        return "positive"
    return "neutral"


def extract_competitor_mentions(
    answer_text: str,
    *,
    target_domain: str,
    competitors: list[str],
    extra_urls: list[str] | None = None,
) -> list[CompetitorMentionRecord]:
    """Build mention records for target + each competitor domain."""
    target = normalize_benchmark_domain(target_domain)
    competitor_domains = [normalize_benchmark_domain(item) for item in competitors if item]
    citations = extract_citations(answer_text, extra_urls=extra_urls)
    domain_positions: dict[str, int] = {}
    for citation in citations:
        if citation.domain and citation.domain not in domain_positions:
            domain_positions[citation.domain] = citation.position

    records: list[CompetitorMentionRecord] = []
    all_domains = [target] + [d for d in competitor_domains if d != target]
    for domain in all_domains:
        name = domain.split(".")[0]
        cited = domain in domain_positions
        domain_mentioned = bool(re.search(r"(?<!\w)" + re.escape(domain) + r"(?!\w)", answer_text, re.I))
        # Very short domain labels are frequently ordinary words, not brand evidence.
        name_mentioned = len(name) >= 3 and bool(re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", answer_text, re.I))
        mentioned = domain_mentioned or name_mentioned
        records.append(
            CompetitorMentionRecord(
                competitor_domain=domain,
                competitor_name=name,
                cited=cited,
                mentioned=mentioned or cited,
                position=domain_positions.get(domain, 0),
                sentiment=_sentiment_near(answer_text, name if mentioned else domain),
            )
        )
    return records
