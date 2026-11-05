"""Citability package — public API.

All public names from the original ``citability.py`` are re-exported here so
that every existing import continues to work unchanged:

    from geo_optimizer.core.citability import detect_X
    from geo_optimizer.core.citability import audit_citability
    from geo_optimizer.core.citability import _IMPROVEMENT_SUGGESTIONS
    from geo_optimizer.core.citability import CitabilityResult, MethodScore
"""

from __future__ import annotations

# entity.py
from geo_optimizer.core.citability.entity import (  # noqa: F401
    detect_eeat,
    detect_entity_disambiguation,
    detect_entity_resolution,
    detect_kg_density,
    detect_retrieval_triggers,
)

# freshness.py
from geo_optimizer.core.citability.freshness import (  # noqa: F401
    _compute_freshness_level,
    _freshness_citability_score,
    _parse_date_flexible,
    detect_content_decay,
    detect_content_freshness,
    detect_stale_data,
    detect_temporal_coherence,
)

# platform.py
from geo_optimizer.core.citability.platform import (  # noqa: F401
    detect_accessibility_signals,
    detect_anchor_text_quality,
    detect_chatgpt_shopping,
    detect_conversion_funnel,
    detect_crawl_budget,
    detect_image_alt_quality,
    detect_international_geo,
    detect_multi_platform,
    detect_shopping_readiness,
    detect_voice_search,
)

# signals.py
from geo_optimizer.core.citability.signals import (  # noqa: F401
    detect_authoritative_tone,
    detect_boilerplate_ratio,
    detect_citability_density,
    detect_comparison_content,
    detect_definition_patterns,
    detect_easy_to_understand,
    detect_fluency,
    detect_keyword_stuffing,
    detect_negative_signals,
    detect_nuance_signals,
    detect_technical_terms,
    detect_token_efficiency,
    detect_unique_words,
)

# ─── Re-export from submodules ───────────────────────────────────────────────
# sources.py
from geo_optimizer.core.citability.sources import (  # noqa: F401
    detect_attribution,
    detect_cite_sources,
    detect_first_party_data,
    detect_quotations,
    detect_social_proof,
    detect_statistics,
)

# structure.py
from geo_optimizer.core.citability.structure import (  # noqa: F401
    _count_syllables,
    detect_ai_search_content_brief,
    detect_answer_capsule,
    detect_answer_first,
    detect_blog_structure,
    detect_chunk_quotability,
    detect_faq_in_content,
    detect_format_mix,
    detect_passage_density,
    detect_readability,
    detect_snippet_ready,
    resolve_ai_search_content_brief_context,
)

# ─── Re-export model types ───────────────────────────────────────────────────
from geo_optimizer.models.results import CitabilityResult, MethodScore  # noqa: F401

# ─── Orchestrator constants ───────────────────────────────────────────────────

# Improvement suggestions for each undetected method
_IMPROVEMENT_SUGGESTIONS = {
    "quotation_addition": "Add attributed quotes in <blockquote> (+41% AI visibility)",
    "statistics_addition": "Include quantitative data: percentages, figures, metrics (+33%)",
    "fluency_optimization": "Improve fluency with longer paragraphs and logical connectives (+29%)",
    "cite_sources": "Cite authoritative sources (.edu, .gov, Wikipedia) with external links (+27%)",
    "answer_first": "Start each section with a concrete fact in the first sentence (+25% AI citation)",
    "passage_density": "Write self-contained paragraphs of 50-150 words with numeric data (+23%)",
    "technical_terms": "Use domain-specific technical terminology (+18%)",
    "authoritative_tone": "Add author bio with credentials and assertive tone (+16%)",
    "readability": "Target Flesch-Kincaid Grade 6-8 with 100-150 word sections (+15% AI citation)",
    "citability_density": "Add 2+ citable facts (numbers, names, dates) per paragraph (+15%)",
    "easy_to_understand": "Improve readability: short sentences, hierarchical headings, FAQ (+14%)",
    "faq_in_content": "Add FAQ patterns in content: headings ending with '?' followed by answers (+12%)",
    "content_freshness": "Add dateModified in JSON-LD and reference current year in content (+10%)",
    "definition_patterns": "Start sections with definitions: 'X is...', 'X refers to...' (+10%)",
    "image_alt_quality": "Write descriptive alt text (>10 chars, not generic) for all images (+8%)",
    "format_mix": "Mix content formats: paragraphs + bullet lists + tables (+8%)",
    "unique_words": "Vary vocabulary: use synonyms, avoid repetitions (+7%)",
    "keyword_stuffing": "Reduce density of repeated keywords (-9% if present)",
    # Quality Signals Batch 2
    "attribution_completeness": "Add inline attributions: 'according to X', 'Y (2024) found that' (+12%)",
    "no_negative_signals": "Remove excessive CTAs, add author info, avoid repetitive phrases (-15%)",
    "comparison_content": "Add comparison tables, pro/con sections, or 'X vs Y' headings (+10%)",
    "eeat_signals": "Add privacy policy, terms, about page, and contact links for E-E-A-T trust (+15%)",
    "no_content_decay": "Update old year references and add recent dateModified (-10%)",
    "boilerplate_ratio": "Ensure main content is >60% of page text; use <main> or <article> tags (+8%)",
    "nuance_signals": "Add nuance: 'however', 'limitations include', 'on the other hand' (+5%)",
    # Quality Signals Batch 3+4
    "snippet_ready": "Add snippet-ready definitions after headings: 'X is...', 'X refers to...' (+10%)",
    "chunk_quotability": "Write self-contained paragraphs (50-150 words) with concrete data for AI quoting (+10%)",
    "blog_structure": "Add Article/BlogPosting schema with datePublished, author, and categories (+8%)",
    "shopping_readiness": "Add Product schema with price, availability, and AggregateRating (+8%)",
    "chatgpt_shopping": "Complete Product schema with name, price, image, availability, brand for ChatGPT Shopping (+8%)",
    # Quality Signals Batch A v3.16.0
    "voice_search_ready": "Add question-format headings with concise answers for voice search (+5%)",
    "multi_platform": "Add 3+ platform links in sameAs schema (GitHub, LinkedIn, Twitter, etc.) (+10%)",
    "entity_disambiguation": "Use consistent naming across title, og:title, and schema; add explicit definition (+8%)",
    "first_party_data": "Include original research signals: 'our data shows', methodology section (+12%)",
    "no_stale_data": "Remove stale year references and update copyright year (-10%)",
    "social_proof": "Add testimonials, AggregateRating with reviews, or trust badges (+8%)",
    "accessibility_signals": "Use semantic HTML (<main>, <nav>), ARIA landmarks, and skip links (+5%)",
    "conversion_funnel": "Add visible CTAs, pricing page link, and contact information (+8%)",
    # Quality Signals Batch B v3.16.0
    "temporal_coherence": "Add coherent date signals: schema dateModified, visible 'Last updated' dates within 30 days (+8%)",
    "anchor_text_quality": "Use descriptive anchor text for internal links instead of 'click here' or 'read more' (+5%)",
    "international_geo": "Add hreflang tags and schema inLanguage for multilingual sites (+5%)",
    "crawl_budget": "Remove meta robots noindex/nofollow to allow AI crawlers to index content (+5%)",
    # RAG Readiness Batch v4.1.0
    "answer_capsule": "Write self-contained answer paragraphs (30-120 words) with concrete facts for RAG extraction (+12%)",
    "token_efficiency": "Increase content-to-noise ratio: use <main>/<article> tags, reduce boilerplate (+8%)",
    "entity_resolution": "Define entities at first use and add schema.org with name + description + sameAs (+10%)",
    "kg_density": "Add explicit relationship statements ('X is a Y', 'founded by Z') for knowledge graph extraction (+10%)",
    "retrieval_triggers": "Use RAG trigger phrases: 'research shows', 'best practice', 'how to', question headings (+10%)",
    "ai_search_content_brief": "Pass the AI-era content brief: price/detail, freshness, comparisons, proof, answer-first, snippets, evidence, and indexability",
}

_NEGATIVE_METHODS = frozenset(
    {
        "keyword_stuffing",
        "no_negative_signals",
        "no_content_decay",
        "no_stale_data",
    }
)

# Order by decreasing impact (excluding penalties)
_METHOD_ORDER = [
    "quotation_addition",
    "statistics_addition",
    "fluency_optimization",
    "cite_sources",
    "answer_first",
    "passage_density",
    "technical_terms",
    "authoritative_tone",
    "eeat_signals",
    "readability",
    "citability_density",
    "easy_to_understand",
    "attribution_completeness",
    "faq_in_content",
    "content_freshness",
    "comparison_content",
    "definition_patterns",
    "image_alt_quality",
    "boilerplate_ratio",
    "format_mix",
    "unique_words",
    "nuance_signals",
    "snippet_ready",
    "chunk_quotability",
    "ai_search_content_brief",
    "blog_structure",
    "shopping_readiness",
    "chatgpt_shopping",
    # Quality Signals Batch A v3.16.0
    "first_party_data",
    "multi_platform",
    "entity_disambiguation",
    "social_proof",
    "conversion_funnel",
    "voice_search_ready",
    "accessibility_signals",
    # Quality Signals Batch B v3.16.0
    "temporal_coherence",
    "anchor_text_quality",
    "international_geo",
    "crawl_budget",
    # RAG Readiness Batch v4.1.0
    "answer_capsule",
    "retrieval_triggers",
    "kg_density",
    "entity_resolution",
    "token_efficiency",
    # Penalties
    "keyword_stuffing",
    "no_negative_signals",
    "no_content_decay",
    "no_stale_data",
]


# ─── Grade computation ────────────────────────────────────────────────────────


def _compute_grade(total: int) -> str:
    """Calculate the citability grade from the total score.

    Fix #26: usa le stesse bande di SCORE_BANDS in config.py
    per coerenza con il GEO score.
    """
    if total >= 86:
        return "excellent"
    if total >= 68:
        return "good"
    if total >= 36:
        return "foundation"
    return "critical"


# ─── Main orchestrator ────────────────────────────────────────────────────────

from geo_optimizer.core.citability._helpers import _get_clean_text  # noqa: E402


def audit_citability(soup, base_url: str, soup_clean=None) -> CitabilityResult:
    """Analyze content citability with 48 methods (Princeton GEO + AutoGEO + RAG readiness).

    Args:
        soup: BeautifulSoup of the HTML page.
        base_url: Base URL of the site.
        soup_clean: (optional) soup pre-cleaned from script/style (fix #285).

    Returns:
        CitabilityResult with score 0-100 and per-method detail.
    """
    # Fix #285: pass soup_clean to _get_clean_text to avoid re-parsing
    clean_text = _get_clean_text(soup, soup_clean=soup_clean)

    methods = [
        # Original Princeton GEO methods (recalibrated)
        detect_quotations(soup, clean_text=clean_text),
        detect_statistics(soup, clean_text=clean_text),
        detect_fluency(soup, clean_text=clean_text),
        detect_cite_sources(soup, base_url),
        detect_answer_first(soup),
        detect_passage_density(soup),
        detect_technical_terms(soup, clean_text=clean_text),
        detect_authoritative_tone(soup, clean_text=clean_text),
        detect_easy_to_understand(soup),
        detect_unique_words(soup, clean_text=clean_text),
        detect_keyword_stuffing(soup, clean_text=clean_text),
        # New content analysis methods v3.15
        detect_readability(soup, clean_text=clean_text),
        detect_faq_in_content(soup),
        detect_image_alt_quality(soup),
        detect_content_freshness(soup, clean_text=clean_text),
        detect_citability_density(soup, clean_text=clean_text),
        detect_definition_patterns(soup),
        detect_format_mix(soup),
        # Quality Signals Batch 2 (bonus — capped at 100 total)
        detect_attribution(soup, clean_text=clean_text),
        detect_negative_signals(soup, clean_text=clean_text),
        detect_comparison_content(soup, clean_text=clean_text),
        detect_eeat(soup),
        detect_content_decay(soup, clean_text=clean_text),
        detect_boilerplate_ratio(soup),
        detect_nuance_signals(soup, clean_text=clean_text),
        # Quality Signals Batch 3+4 (bonus — capped at 100 total)
        detect_snippet_ready(soup),
        detect_chunk_quotability(soup),
        detect_ai_search_content_brief(soup, clean_text=clean_text),
        detect_blog_structure(soup),
        detect_shopping_readiness(soup),
        detect_chatgpt_shopping(soup),
        # Quality Signals Batch A v3.16.0 (bonus — capped at 100 total)
        detect_voice_search(soup),
        detect_multi_platform(soup),
        detect_entity_disambiguation(soup),
        detect_first_party_data(soup, clean_text=clean_text),
        detect_stale_data(soup, clean_text=clean_text),
        detect_social_proof(soup, clean_text=clean_text),
        detect_accessibility_signals(soup),
        detect_conversion_funnel(soup),
        # Quality Signals Batch B v3.16.0
        detect_temporal_coherence(soup, clean_text=clean_text),
        detect_anchor_text_quality(soup, base_url),
        detect_international_geo(soup),
        detect_crawl_budget(soup),
        # RAG Readiness Batch v4.1.0 (#372, #365, #373, #366, #374)
        detect_answer_capsule(soup, clean_text=clean_text),
        detect_token_efficiency(soup, clean_text=clean_text),
        detect_entity_resolution(soup),
        detect_kg_density(soup, clean_text=clean_text),
        detect_retrieval_triggers(soup, clean_text=clean_text),
    ]

    # Sum scores (max possible = 100)
    total = sum(m.score for m in methods)
    total = max(min(total, 100), 0)

    # Top 3 improvements: undetected methods, ordered by impact
    improvements = []
    for method_name in _METHOD_ORDER:
        method = next((m for m in methods if m.name == method_name), None)
        if not method or method_name not in _IMPROVEMENT_SUGGESTIONS:
            continue
        needs_improvement = method.detected if method_name in _NEGATIVE_METHODS else not method.detected
        if needs_improvement:
            improvements.append(_IMPROVEMENT_SUGGESTIONS[method_name])
        if len(improvements) >= 3:
            break

    return CitabilityResult(
        methods=methods,
        total_score=total,
        grade=_compute_grade(total),
        top_improvements=improvements[:3],
    )


__all__ = [
    # Types
    "CitabilityResult",
    "MethodScore",
    # Orchestrator
    "audit_citability",
    "_IMPROVEMENT_SUGGESTIONS",
    "_compute_grade",
    # sources
    "detect_cite_sources",
    "detect_quotations",
    "detect_statistics",
    "detect_attribution",
    "detect_social_proof",
    "detect_first_party_data",
    # structure
    "detect_answer_first",
    "detect_passage_density",
    "detect_readability",
    "_count_syllables",
    "detect_faq_in_content",
    "detect_format_mix",
    "detect_snippet_ready",
    "detect_chunk_quotability",
    "detect_ai_search_content_brief",
    "resolve_ai_search_content_brief_context",
    "detect_blog_structure",
    "detect_answer_capsule",
    # signals
    "detect_fluency",
    "detect_technical_terms",
    "detect_authoritative_tone",
    "detect_easy_to_understand",
    "detect_unique_words",
    "detect_keyword_stuffing",
    "detect_definition_patterns",
    "detect_nuance_signals",
    "detect_citability_density",
    "detect_negative_signals",
    "detect_comparison_content",
    "detect_boilerplate_ratio",
    "detect_token_efficiency",
    # freshness
    "detect_content_freshness",
    "detect_content_decay",
    "detect_stale_data",
    "detect_temporal_coherence",
    "_compute_freshness_level",
    "_freshness_citability_score",
    "_parse_date_flexible",
    # entity
    "detect_entity_disambiguation",
    "detect_entity_resolution",
    "detect_kg_density",
    "detect_retrieval_triggers",
    "detect_eeat",
    # platform
    "detect_shopping_readiness",
    "detect_chatgpt_shopping",
    "detect_voice_search",
    "detect_multi_platform",
    "detect_international_geo",
    "detect_accessibility_signals",
    "detect_conversion_funnel",
    "detect_crawl_budget",
    "detect_anchor_text_quality",
    "detect_image_alt_quality",
]
