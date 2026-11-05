"""
Search Experience Optimization (SXO) audit.

SXO checks whether the page content and structure match the search intent
implied by the URL slug and visible content signals.  A transactional page
that reads like a blog post, or an informational guide crammed with hard-sell
CTAs, creates a mismatch that hurts both ranking and citation quality.

Intent categories (TISN model):
    T  — Transactional   (buy, price, hire, quote, order)
    I  — Informational   (what is, how to, guide, learn, tips)
    S  — Commercial investigation (vs, review, best, compare, alternative)
    N  — Navigational    (brand name, login, contact, about)

No SERP API required — all signals are inferred from the URL and HTML.
"""

from __future__ import annotations

import re

from geo_optimizer.models.results import SXOResult

# ─── Intent signal lexicons ───────────────────────────────────────────────────

_TRANSACTIONAL_URL = re.compile(
    r"\b(price|pricing|tarif|buy|order|hire|get-quote|contact|book|booking|shop|checkout|devis)\b",
    re.IGNORECASE,
)
_TRANSACTIONAL_CONTENT = re.compile(
    r"\b(free quote|get started|contact us|buy now|order now|schedule|book a|sign up|get a quote"
    r"|tarif|devis|prix|nous contacter|réserver)\b",
    re.IGNORECASE,
)
_INFORMATIONAL_URL = re.compile(
    r"\b(guide|how-to|what-is|tutorial|tips|learn|blog|article|faq|glossary|resources"
    r"|conseils|guide-pratique|comment)\b",
    re.IGNORECASE,
)
_INFORMATIONAL_CONTENT = re.compile(
    r"\b(this article|in this guide|you will learn|step by step|how to|what is|why|overview"
    r"|dans cet article|dans ce guide|comment|pourquoi|étapes)\b",
    re.IGNORECASE,
)
_COMMERCIAL_URL = re.compile(
    r"\b(vs|versus|compare|review|best|top-\d|alternative|comparison"
    r"|comparatif|meilleur|avis)\b",
    re.IGNORECASE,
)
_COMMERCIAL_CONTENT = re.compile(
    r"\b(pros and cons|vs\.|versus|compared to|our rating|stars|out of \d"
    r"|avantages|inconvénients|comparaison|par rapport à)\b",
    re.IGNORECASE,
)
_CTA_TAGS = re.compile(r"\b(contact|book|buy|order|get quote|sign up|schedule|devis|réserver)\b", re.IGNORECASE)

_MIN_INFORMATIONAL_WORDS = 300  # informational pages need real depth


def audit_sxo(soup, url: str = "") -> SXOResult:
    """Detect search intent and audit content-intent alignment.

    Args:
        soup: BeautifulSoup of the page HTML.
        url: Page URL — slug keywords inform intent detection.

    Returns:
        SXOResult with detected intent, content signals, alignment score,
        and recommendations.
    """
    result = SXOResult(checked=True, page_url=url)
    slug = _extract_slug(url)
    body_text = _extract_body_text(soup)
    word_count = len(body_text.split())

    # ── Detect URL intent ────────────────────────────────────────────────────
    url_intents: list[str] = []
    if _TRANSACTIONAL_URL.search(slug):
        url_intents.append("transactional")
    if _INFORMATIONAL_URL.search(slug):
        url_intents.append("informational")
    if _COMMERCIAL_URL.search(slug):
        url_intents.append("commercial")
    result.url_intent_signals = url_intents

    # ── Detect content intent ────────────────────────────────────────────────
    content_intents: list[str] = []
    cta_matches = len(_CTA_TAGS.findall(body_text))
    info_matches = len(_INFORMATIONAL_CONTENT.findall(body_text))
    commercial_matches = len(_COMMERCIAL_CONTENT.findall(body_text))

    if cta_matches >= 2:
        content_intents.append("transactional")
    if info_matches >= 2:
        content_intents.append("informational")
    if commercial_matches >= 2:
        content_intents.append("commercial")

    result.content_intent_signals = content_intents
    result.cta_count = cta_matches
    result.word_count = word_count

    # ── Alignment check ──────────────────────────────────────────────────────
    url_set = set(url_intents)
    content_set = set(content_intents)

    if url_set and content_set:
        overlap = url_set & content_set
        result.intent_aligned = bool(overlap)
        if overlap:
            result.matched_intent = sorted(overlap)[0]
    elif not url_set:
        # No strong URL signal — informational default if long-form content
        result.intent_aligned = True
        result.matched_intent = "informational" if word_count >= _MIN_INFORMATIONAL_WORDS else "unclear"
    else:
        # URL intent is clear but content doesn't match
        result.intent_aligned = False
        result.matched_intent = "mismatch"

    # ── Specific mismatch patterns ───────────────────────────────────────────
    if "transactional" in url_set and "informational" in content_set and "transactional" not in content_set:
        result.mismatch_type = "transactional_url_informational_content"
        result.mismatch_detail = (
            "URL signals a service/pricing page but content reads like an article. "
            "Add pricing, CTAs, and trust signals above the fold."
        )
    elif "informational" in url_set and "transactional" in content_set and "informational" not in content_set:
        result.mismatch_type = "informational_url_transactional_content"
        result.mismatch_detail = (
            "URL signals a guide/blog page but content is dominated by CTAs. "
            "Educational content should lead; CTAs can follow after value delivery."
        )
    elif url_set and content_set and not (url_set & content_set):
        result.mismatch_type = "intent_conflict"
        result.mismatch_detail = (
            f"URL intent ({', '.join(url_set)}) conflicts with content intent "
            f"({', '.join(content_set)}). Align the page structure with what searchers expect."
        )

    # ── Informational depth check ────────────────────────────────────────────
    if "informational" in content_set or "informational" in url_set:
        result.informational_depth_ok = word_count >= _MIN_INFORMATIONAL_WORDS
        if not result.informational_depth_ok:
            result.recommendations.append(
                f"Informational page has only {word_count} words — aim for ≥300 to provide enough "
                "depth for AI citation and featured snippet capture."
            )

    # ── Score (0–3) ──────────────────────────────────────────────────────────
    result.sxo_score = sum(
        [
            result.intent_aligned,
            not bool(result.mismatch_type),
            result.informational_depth_ok if ("informational" in content_set or "informational" in url_set) else True,
        ]
    )

    # ── Recommendations ──────────────────────────────────────────────────────
    if result.mismatch_detail:
        result.recommendations.append(result.mismatch_detail)
    if not result.intent_aligned and not result.mismatch_detail:
        result.recommendations.append(
            "Detected intent mismatch between URL keywords and page content. "
            "Ensure the page structure (headings, CTAs, depth) matches what searchers expect for this URL."
        )

    return result


def _extract_slug(url: str) -> str:
    """Return the URL path portion for intent keyword matching."""
    try:
        from urllib.parse import urlparse

        return urlparse(url).path.replace("/", " ").replace("-", " ").replace("_", " ")
    except ValueError:
        return url


def _extract_body_text(soup) -> str:
    body = soup.find("body")
    return body.get_text(separator=" ", strip=True) if body else ""
