"""
Action intelligence: turn audit output into a prioritized execution roadmap.
"""

from __future__ import annotations

from geo_optimizer.core.scoring import CATEGORY_MAX_SCORES
from geo_optimizer.models.results import NextAction

# Single source of truth for category ceilings — also used by rivalry_cmd.
CATEGORY_MAX: dict[str, int] = dict(CATEGORY_MAX_SCORES)

_CATEGORY_LABELS = {
    "robots": "AI crawler access",
    "llms": "llms.txt readiness",
    "schema": "structured data",
    "meta": "metadata coverage",
    "content": "citation-ready content",
    "signals": "technical discoverability",
    "ai_discovery": "AI discovery endpoints",
    "brand_entity": "entity trust and KG signals",
}

_CATEGORY_EFFORT = {
    "robots": "low",
    "llms": "low",
    "schema": "medium",
    "meta": "low",
    "content": "high",
    "signals": "low",
    "ai_discovery": "medium",
    "brand_entity": "medium",
}

_CATEGORY_MATCH_KEYWORDS = {
    "robots": ("robots.txt", "gptbot", "claudebot", "perplexitybot", "ai bots", "crawler"),
    "llms": ("llms.txt", "llms-full.txt"),
    "schema": ("schema", "json-ld", "faqpage", "organization", "website", "product"),
    "meta": ("meta", "canonical", "og:", "open graph", "<title>", "description"),
    "content": ("h1", "content", "words", "statistics", "external links", "subheadings"),
    "signals": ("lang attribute", "rss", "atom", "freshness", "dateModified"),
    "ai_discovery": ("/.well-known/ai.txt", "/ai/summary.json", "/ai/faq.json", "/ai/service.json", "ai discovery"),
    "brand_entity": ("sameas", "knowledge graph", "about", "contactpoint", "entity", "brand name"),
}

_CATEGORY_DEFAULT_WHY = {
    "robots": "Allow key AI crawlers in robots.txt and verify access headers.",
    "llms": "Improve llms.txt structure (sections, depth, and linked key pages).",
    "schema": "Expand JSON-LD coverage with complete, valid business and FAQ schema.",
    "meta": "Tighten title, meta description, canonical, and Open Graph consistency.",
    "content": "Strengthen page substance, scannability, and citation-ready evidence.",
    "signals": "Improve machine-readable signals (lang, feed, and freshness metadata).",
    "ai_discovery": "Complete and validate all AI discovery endpoints under /.well-known and /ai/.",
    "brand_entity": "Reinforce entity trust signals with consistent brand, about/contact, and sameAs links.",
}


def _impact_bucket(gap: int) -> str:
    if gap >= 8:
        return "high"
    if gap >= 4:
        return "medium"
    return "low"


def _build_title(category: str, gap: int) -> str:
    label = _CATEGORY_LABELS.get(category, category.replace("_", " ").title())
    return f"Improve {label} (+{gap} potential points)"


def _window_from_rank(idx: int) -> str:
    if idx == 0:
        return "P1"
    if idx <= 2:
        return "P2"
    return "P3"


def _match_recommendation_for_category(category: str, recommendations: list[str]) -> str | None:
    keywords = _CATEGORY_MATCH_KEYWORDS.get(category, ())
    for rec in recommendations:
        rec_l = rec.lower()
        if any(keyword.lower() in rec_l for keyword in keywords):
            return rec
    return None


def build_next_actions(
    score_breakdown: dict[str, int], recommendations: list[str], max_items: int = 5
) -> list[NextAction]:
    """Create prioritized next-step actions from score gaps + recommendations."""
    candidates: list[tuple[str, int]] = []
    for category, current in score_breakdown.items():
        max_score = CATEGORY_MAX.get(category, current)
        gap = max(0, max_score - current)
        if gap > 0:
            candidates.append((category, gap))

    candidates.sort(key=lambda item: item[1], reverse=True)
    actions: list[NextAction] = []
    for idx, (category, gap) in enumerate(candidates[:max_items]):
        matching = _match_recommendation_for_category(category, recommendations) or _CATEGORY_DEFAULT_WHY.get(
            category, "Apply generated fix templates and validate delta."
        )
        actions.append(
            NextAction(
                key=category,
                title=_build_title(category, gap),
                why=matching,
                impact=_impact_bucket(gap),
                effort=_CATEGORY_EFFORT.get(category, "medium"),
                priority=_window_from_rank(idx),
                expected_score_gain=min(gap, 12),
            )
        )

    if not actions and recommendations:
        actions.append(
            NextAction(
                key="maintenance",
                title="Maintain current score and monitor drift",
                why=recommendations[0],
                impact="low",
                effort="low",
                priority="P3",
                expected_score_gain=0,
            )
        )

    return actions
