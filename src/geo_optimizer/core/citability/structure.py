"""Citability: structural content analysis functions.

Covers: answer-first structure, passage density, readability, FAQ detection,
format mix, snippet readiness, chunk quotability, blog structure,
answer capsule detection.
"""

from __future__ import annotations

import functools
import re
from datetime import datetime, timezone

from geo_optimizer.core.citability._helpers import (
    _extract_dates_from_soup,
    _get_clean_text,
    _iter_jsonld_items,
    _jsonld_types,
)
from geo_optimizer.models.results import MethodScore

# ─── Shared regex used across multiple functions ──────────────────────────────

# Pattern for concrete facts: numbers, percentages, assertive statements
_FACT_RE = re.compile(
    r"\b\d+(?:\.\d+)?%"  # percentages
    r"|\$\d+"  # currency
    r"|\b\d{2,}\b"  # numbers with 2+ digits
    r"|\b(?:is|are|was|were|has|have|can|will|must|should"
    r"|è|sono|ha|hanno|può|deve)\b",  # assertive verbs EN+IT
    re.IGNORECASE,
)

# Pattern for citable facts: numbers, dates, specific claims (NO IGNORECASE)
_CITABLE_FACT_NUMERIC_RE = re.compile(
    r"\b\d+(?:\.\d+)?%"  # percentages
    r"|\$\d+(?:[.,]\d+)*"  # currency $
    r"|€\d+(?:[.,]\d+)*"  # currency €
    r"|\b\d{4}\b"  # years
    r"|\b\d+(?:\.\d+)?\s*(?:million|billion|thousand|miliardi|milioni)\b"  # large numbers
    r"|\b\d+(?:\.\d+)?\s*(?:x|times|volte)\b",  # multipliers
    re.IGNORECASE,
)

# Regex: sentence-ending punctuation (period, question mark, exclamation)
_SENTENCE_END_RE = re.compile(r"[.!?](?:\s|$)")

# Explicit definitions in first 150 chars after a heading
_SNIPPET_DEF_RE = re.compile(
    r"\b(?:is|are|refers?\s+to|means?|can\s+be\s+defined\s+as"
    r"|è|sono|si\s+riferisce\s+a|significa)\b",
    re.IGNORECASE,
)

_PRICE_RE = re.compile(
    r"(?:[$€£]\s?\d+(?:[.,]\d+)*(?:\s?/\s?(?:mo|month|yr|year))?)"
    r"|\b(?:price|pricing|costs?|starts? at|from|plans?|tarif|tarification)\b.{0,48}\b\d+",
    re.IGNORECASE,
)

_VALUE_RE = re.compile(
    r"\b(?:helps?|for|built for|designed for|so you can|you get|unlock|save|increase|reduce|improve|"
    r"customers?|reviews?|case stud(?:y|ies)|testimonial|trusted by|rated|stars?)\b",
    re.IGNORECASE,
)

_SPEC_RE = re.compile(
    r"\b(?:specifications?|technical|api|schema|json-ld|sla|uptime|latency|gb|mb|ms|seconds?|version|"
    r"features?|supported|integration|compliance|soc\s?2|gdpr)\b",
    re.IGNORECASE,
)

_CONFIDENT_RE = re.compile(
    r"\b(?:is|are|will|must|does|provides|delivers|supports|includes|prevents|improves|reduces|"
    r"wins?|beats?|ranks?|cites?)\b",
    re.IGNORECASE,
)

_HEDGE_BRIEF_RE = re.compile(
    r"\b(?:might|may|could|possibly|probably|generally|often|usually|seems?|appears?|"
    r"we think|we believe|in many cases)\b",
    re.IGNORECASE,
)

_EVIDENCE_RE = re.compile(
    r"\b(?:according to|study|research|survey|data|report|trial|benchmark|tested|measured|found that|"
    r"source|citation|evidence|methodology)\b",
    re.IGNORECASE,
)

_CONTRADICTION_RE = re.compile(
    r"\b(?:contradicts?|conflicting|inconsistent|on the contrary|cannot both|but not|except when)\b",
    re.IGNORECASE,
)

_SOCIAL_PROOF_RE = re.compile(
    r"\b(?:testimonial|review|rated|stars?|trusted by|customers?|case stud(?:y|ies)|"
    r"used by|adopted by|recommended by)\b",
    re.IGNORECASE,
)

_INDEXABLE_RE = re.compile(r"\b(?:noindex|nofollow)\b", re.IGNORECASE)


def _has_product_price_schema(items: list[dict]) -> bool:
    """Detect Product schema with offer pricing."""
    for item in items:
        if "Product" not in _jsonld_types(item):
            continue
        offers = item.get("offers") or item.get("offer") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        if isinstance(offers, dict) and bool(offers.get("price") or offers.get("lowPrice")):
            return True
    return False


def _has_rating_schema(items: list[dict]) -> bool:
    """Detect aggregate rating/review schema used as social proof."""
    for item in items:
        if item.get("aggregateRating") or item.get("review"):
            return True
        if any(schema_type in ("AggregateRating", "Review") for schema_type in _jsonld_types(item)):
            return True
    return False


def _schema_has_dates(items: list[dict]) -> bool:
    """Detect content date fields in JSON-LD."""
    return any(bool(item.get("dateModified") or item.get("datePublished")) for item in items)


def _has_indexable_meta(soup) -> bool:
    """Return True when robots meta tags do not block indexing."""
    robots_meta = soup.find_all("meta", attrs={"name": re.compile(r"robots", re.I)})
    return not any(_INDEXABLE_RE.search(meta.get("content", "")) for meta in robots_meta)


def _pass_fail(value: bool) -> str:
    """Normalize a readiness boolean to a stable status string."""
    return "pass" if value else "fail"


def _manual_status(value: bool | None) -> str:
    """Normalize a query-aware factor that may still need external context."""
    if value is None:
        return "manual_review"
    return _pass_fail(value)


def _factor(name: str, status: str, detail: str, evidence: object | None = None) -> dict[str, object]:
    """Build a stable content-brief factor payload."""
    payload: dict[str, object] = {"name": name, "status": status, "detail": detail}
    if evidence is not None:
        payload["evidence"] = evidence
    return payload


def _brief_details(details: object) -> dict:
    """Return MethodScore details as a plain dict for downstream composition."""
    if isinstance(details, dict):
        return details
    extra = getattr(details, "extra", None)
    return extra if isinstance(extra, dict) else {}


def _tokens(text: str) -> set[str]:
    """Extract significant lowercase tokens for query/source matching."""
    stop = {
        "about",
        "after",
        "and",
        "are",
        "best",
        "for",
        "from",
        "how",
        "into",
        "the",
        "this",
        "top",
        "what",
        "when",
        "where",
        "which",
        "with",
        "your",
    }
    return {token for token in re.findall(r"[a-z0-9][a-z0-9-]{2,}", text.lower()) if token not in stop}


def _extract_response_sources(ai_response: str) -> list[str]:
    """Extract URL-like sources from an AI response."""
    return re.findall(r"https?://[^\s)\]\"']+", ai_response)


def _contains_source(text: str, source: str) -> bool:
    """Case-insensitive source/brand containment check."""
    source_norm = source.strip().lower()
    if not source_norm:
        return False
    return source_norm in text.lower()


def _first_ranked_candidate(ai_response: str) -> str:
    """Return the first ranked/bulleted answer line, falling back to the opening text."""
    for line in ai_response.splitlines():
        cleaned = line.strip()
        if not cleaned:
            continue
        if re.match(r"^(?:1[\).:-]|\#1\b|[-*•])\s*", cleaned):
            return cleaned
    return ai_response.strip()[:500]


def _topic_match(target_query: str, text: str) -> tuple[bool | None, float]:
    """Estimate whether response context overlaps the target query."""
    query_terms = _tokens(target_query)
    if not query_terms:
        return None, 0.0
    text_terms = _tokens(text)
    overlap = len(query_terms & text_terms) / max(len(query_terms), 1)
    return overlap >= 0.5, round(overlap, 2)


# ─── 10. Answer-First Structure (+25%) — AutoGEO ICLR 2026 ───────────────────


def detect_answer_first(soup) -> MethodScore:
    """Detect answer-first structure: H2 followed by paragraph with concrete fact.

    AutoGEO (ICLR 2026) identifies AnswerFirst as one of the most effective
    strategies for AI citation. For each H2, checks if the first paragraph
    contains a concrete fact (number, assertive statement) in the first 150 chars.
    """
    h2_tags = soup.find_all("h2")
    if not h2_tags:
        return MethodScore(name="answer_first", label="Answer-First Structure", max_score=5, impact="+25%")

    answer_first_count = 0
    for h2 in h2_tags:
        # Fix #400: find the first text after H2 in p, div, li (WordPress/Elementor wraps
        # content in <div><p>...</p></div>, so direct sibling <p> is not always present)
        next_el = h2.find_next(["p", "div", "li"])
        if not next_el:
            continue
        # Skip empty elements (empty divs without text content)
        first_text = next_el.get_text(strip=True)[:150]
        if not first_text:
            continue
        if _FACT_RE.search(first_text):
            answer_first_count += 1

    total_h2 = len(h2_tags)
    ratio = answer_first_count / total_h2 if total_h2 > 0 else 0

    # Score proportional to the percentage of H2s with answer-first
    score = min(int(ratio * 8), 5)

    return MethodScore(
        name="answer_first",
        label="Answer-First Structure",
        detected=ratio >= 0.3,
        score=score,
        max_score=5,
        impact="+25%",
        details={
            "h2_count": total_h2,
            "answer_first_count": answer_first_count,
            "ratio": round(ratio, 2),
        },
    )


# ─── 11. Passage Density (+23%) — Stanford Nature Communications 2025 ────────


def detect_passage_density(soup) -> MethodScore:
    """Detect self-contained dense passages (50-150 words with numeric data).

    Stanford Nature Communications 2025: paragraphs of 50-150 words containing
    concrete data have 2.3x citation rate compared to generic paragraphs.
    """
    paragraphs = soup.find_all("p")
    if not paragraphs:
        return MethodScore(name="passage_density", label="Passage Density", max_score=5, impact="+23%")

    total_paras = 0
    dense_paras = 0

    for p in paragraphs:
        text = p.get_text(strip=True)
        word_count = len(text.split())
        if word_count < 10:
            # Paragraphs that are too short are skipped
            continue
        total_paras += 1
        # Dense paragraph: 50-150 words with at least one numeric data point
        if 50 <= word_count <= 150 and re.search(r"\b\d+(?:\.\d+)?[%$€]?|\b\d{3,}\b", text):
            dense_paras += 1

    ratio = dense_paras / total_paras if total_paras > 0 else 0

    # Score proportional to the percentage of dense paragraphs
    score = min(int(ratio * 10), 5)

    return MethodScore(
        name="passage_density",
        label="Passage Density",
        detected=dense_paras >= 2,
        score=score,
        max_score=5,
        impact="+23%",
        details={
            "total_paragraphs": total_paras,
            "dense_paragraphs": dense_paras,
            "ratio": round(ratio, 2),
        },
    )


# ─── 12. Readability Score (+15%) — SE Ranking 2025 ───────────────────────────


@functools.lru_cache(maxsize=512)
def _count_syllables(word: str) -> int:
    """Approximate syllable count for English/Italian words (cached)."""
    word = word.lower().strip()
    if len(word) <= 3:
        return 1
    # Count vowel groups as an approximation
    vowels = "aeiouyàèéìòùü"
    count = 0
    prev_vowel = False
    for ch in word:
        is_vowel = ch in vowels
        if is_vowel and not prev_vowel:
            count += 1
        prev_vowel = is_vowel
    # At least 1 syllable
    return max(count, 1)


def detect_readability(soup, clean_text: str | None = None) -> MethodScore:
    """Detect readability using Flesch-Kincaid Grade Level and section length."""
    body_text = clean_text or _get_clean_text(soup)
    words = body_text.split()
    if len(words) < 30:
        return MethodScore(name="readability", label="Readability Score", max_score=8, impact="+15%")

    # Count sentences
    sentences = [s.strip() for s in re.split(r"[.!?]+", body_text) if len(s.strip().split()) >= 3]
    num_sentences = max(len(sentences), 1)
    num_words = len(words)

    # Count total syllables
    total_syllables = sum(_count_syllables(w) for w in words)

    # Flesch-Kincaid Grade Level
    fk_grade = 0.39 * (num_words / num_sentences) + 11.8 * (total_syllables / num_words) - 15.59

    # Check section length between headings
    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    section_lengths = []
    for _i, h in enumerate(headings):
        # Count words between this heading and the next
        section_text = []
        sibling = h.find_next_sibling()
        while sibling and sibling.name not in ["h1", "h2", "h3", "h4"]:
            if sibling.name in ["p", "li", "td"]:
                section_text.append(sibling.get_text(strip=True))
            sibling = sibling.find_next_sibling()
        section_word_count = len(" ".join(section_text).split())
        if section_word_count > 0:
            section_lengths.append(section_word_count)

    # Sections with optimal length (100-150 words)
    optimal_sections = sum(1 for sl in section_lengths if 100 <= sl <= 150) if section_lengths else 0
    section_ratio = optimal_sections / max(len(section_lengths), 1)

    # Score calculation
    score = 0

    # Sweet spot Grade 6-8: maximum AI citations
    if 6 <= fk_grade <= 8:
        score += 5
    elif 5 <= fk_grade <= 10:
        score += 3
    elif 4 <= fk_grade <= 12:
        score += 1

    # Bonus for sections with optimal length
    score += min(int(section_ratio * 3), 3)

    return MethodScore(
        name="readability",
        label="Readability Score",
        detected=6 <= fk_grade <= 10,
        score=min(score, 8),
        max_score=8,
        impact="+15%",
        details={
            "flesch_kincaid_grade": round(fk_grade, 1),
            "avg_words_per_sentence": round(num_words / num_sentences, 1),
            "avg_syllables_per_word": round(total_syllables / num_words, 2),
            "optimal_sections": optimal_sections,
            "total_sections": len(section_lengths),
        },
    )


# ─── 13. FAQ-in-Content Check (+12%) — SE Ranking 2025 ───────────────────────


def detect_faq_in_content(soup) -> MethodScore:
    """Detect FAQ patterns in content (not FAQPage schema, which has zero impact)."""
    faq_count = 0

    # Pattern 1: heading ending with "?" followed by a paragraph
    for heading in soup.find_all(["h2", "h3", "h4"]):
        heading_text = heading.get_text(strip=True)
        if heading_text.endswith("?"):
            # Look for an answer paragraph after the heading
            next_elem = heading.find_next_sibling()
            if next_elem and next_elem.name in ["p", "div", "ul", "ol"]:
                answer_text = next_elem.get_text(strip=True)
                if len(answer_text) >= 20:
                    faq_count += 1

    # Pattern 2: <details><summary> FAQ pattern
    details_elements = soup.find_all("details")
    for detail in details_elements:
        summary = detail.find("summary")
        if summary:
            summary_text = summary.get_text(strip=True)
            # Verify there is content after the summary
            detail_text = detail.get_text(strip=True).replace(summary_text, "").strip()
            if len(detail_text) >= 20:
                faq_count += 1

    # Pattern 3: dt/dd (definition list come FAQ)
    dt_elements = soup.find_all("dt")
    for dt in dt_elements:
        dd = dt.find_next_sibling("dd")
        if dd and "?" in dt.get_text():
            faq_count += 1

    # Score based on the number of FAQ patterns found
    if faq_count >= 5:
        score = 6
    elif faq_count >= 3:
        score = 4
    elif faq_count >= 1:
        score = 2
    else:
        score = 0

    return MethodScore(
        name="faq_in_content",
        label="FAQ-in-Content",
        detected=faq_count >= 1,
        score=min(score, 6),
        max_score=6,
        impact="+12%",
        details={
            "faq_patterns_found": faq_count,
        },
    )


# ─── 18. Response Format Mix (+8%) ───────────────────────────────────────────


def detect_format_mix(soup) -> MethodScore:
    """Detect mix of content formats: paragraphs, lists, tables."""
    has_paragraphs = len(soup.find_all("p")) >= 3
    has_lists = len(soup.find_all(["ul", "ol"])) >= 1
    has_tables = len(soup.find_all("table")) >= 1

    # Additional formats (bonus)
    has_code = len(soup.find_all(["pre", "code"])) >= 1
    has_blockquote = len(soup.find_all("blockquote")) >= 1

    # Count formats present
    base_formats = sum([has_paragraphs, has_lists, has_tables])
    bonus_formats = sum([has_code, has_blockquote])

    # Score: full if all 3 base formats are present
    if base_formats == 3:
        score = 4 + min(bonus_formats, 1)  # max 5
    elif base_formats == 2:
        score = 2 + min(bonus_formats, 1)  # max 3
    elif base_formats == 1:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="format_mix",
        label="Response Format Mix",
        detected=base_formats >= 2,
        score=min(score, 5),
        max_score=5,
        impact="+8%",
        details={
            "has_paragraphs": has_paragraphs,
            "has_lists": has_lists,
            "has_tables": has_tables,
            "has_code": has_code,
            "has_blockquote": has_blockquote,
            "format_count": base_formats + bonus_formats,
        },
    )


# ─── 26. Snippet-Ready / Zero-Click (#249) ────────────────────────────────────


def detect_snippet_ready(soup) -> MethodScore:
    """Detect zero-click / snippet-ready content sections.

    Checks if headings are followed by concise definitions (first 150 chars)
    or if question headings (ending with '?') have direct answers under 60 words.
    """
    headings = soup.find_all(["h2", "h3", "h4"])
    if not headings:
        return MethodScore(name="snippet_ready", label="Snippet-Ready Content", max_score=4, impact="+10%")

    snippet_ready_count = 0

    for heading in headings:
        heading_text = heading.get_text(strip=True)
        # Find the first paragraph after the heading
        next_p = heading.find_next("p")
        if not next_p:
            continue
        p_text = next_p.get_text(strip=True)

        # Pattern 1: heading with "?" → direct answer under 60 words
        if heading_text.endswith("?"):
            word_count = len(p_text.split())
            if 5 <= word_count <= 60:
                snippet_ready_count += 1
                continue

        # Pattern 2: explicit definition in the first 150 chars after heading
        first_150 = p_text[:150]
        if _SNIPPET_DEF_RE.search(first_150):
            snippet_ready_count += 1

    total_headings = len(headings)
    ratio = snippet_ready_count / total_headings if total_headings > 0 else 0

    # Proportional score
    if ratio >= 0.5:
        score = 4
    elif ratio >= 0.3:
        score = 3
    elif ratio >= 0.15:
        score = 2
    elif snippet_ready_count >= 1:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="snippet_ready",
        label="Snippet-Ready Content",
        detected=snippet_ready_count >= 1,
        score=min(score, 4),
        max_score=4,
        impact="+10%",
        details={
            "snippet_ready_sections": snippet_ready_count,
            "total_headings": total_headings,
            "ratio": round(ratio, 2),
        },
    )


# ─── 27. Chunk Quotability (#229) ────────────────────────────────────────────


def detect_chunk_quotability(soup) -> MethodScore:
    """Detect quotable content chunks: self-contained paragraphs with concrete data.

    For each paragraph of 50-150 words, checks if it contains concrete data
    (numbers, percentages, dates) making it independently quotable by AI.
    """
    paragraphs = soup.find_all("p")
    if not paragraphs:
        return MethodScore(name="chunk_quotability", label="Chunk Quotability", max_score=4, impact="+10%")

    candidate_count = 0
    quotable_count = 0

    for p in paragraphs:
        text = p.get_text(strip=True)
        word_count = len(text.split())
        # Only paragraphs in the 50-150 word range
        if word_count < 50 or word_count > 150:
            continue
        candidate_count += 1
        # Verify concrete data
        if _CITABLE_FACT_NUMERIC_RE.search(text):  # fix #7: unified regex
            quotable_count += 1

    ratio = quotable_count / candidate_count if candidate_count > 0 else 0

    # Score proportional to the % of quotable paragraphs
    if ratio >= 0.5:
        score = 4
    elif ratio >= 0.3:
        score = 3
    elif ratio >= 0.15:
        score = 2
    elif quotable_count >= 1:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="chunk_quotability",
        label="Chunk Quotability",
        detected=quotable_count >= 1,
        score=min(score, 4),
        max_score=4,
        impact="+10%",
        details={
            "candidate_paragraphs": candidate_count,
            "quotable_paragraphs": quotable_count,
            "ratio": round(ratio, 2),
        },
    )


# ─── AI-era Content Brief Readiness ──────────────────────────────────────────


def detect_ai_search_content_brief(soup, clean_text: str | None = None) -> MethodScore:
    """Roll up AI-era content-brief gatekeepers into one readiness view.

    This check intentionally reuses the same evidence families as the individual
    citability methods, then groups them the way the 2026 answer-engine workflow
    does: gatekeepers first, differentiators second, formatting last. Topic
    match and top recommendation/list position require query + AI-answer context,
    so static HTML audits expose them as manual-review factors.
    """
    body_text = clean_text or _get_clean_text(soup)
    words = re.findall(r"\b[\w'-]+\b", body_text.lower())
    word_count = len(words)
    jsonld_items = _iter_jsonld_items(soup)
    dates = _extract_dates_from_soup(soup)

    headings = soup.find_all(["h2", "h3", "h4"])
    answer_first_sections = 0
    snippet_sections = 0
    question_headings = 0
    comparison_headings = 0
    for heading in headings:
        heading_text = heading.get_text(" ", strip=True)
        next_p = heading.find_next("p")
        if not next_p:
            continue
        p_text = next_p.get_text(" ", strip=True)
        first_150 = p_text[:150]
        if _FACT_RE.search(first_150):
            answer_first_sections += 1
        if heading_text.endswith("?"):
            question_headings += 1
            if 5 <= len(p_text.split()) <= 60:
                snippet_sections += 1
        elif _SNIPPET_DEF_RE.search(first_150):
            snippet_sections += 1
        if re.search(
            r"\b(?:vs\.?|versus|compare|comparison|alternatives?|pros?\s+(?:and|&)\s+cons?)\b", heading_text, re.I
        ):
            comparison_headings += 1

    quotable_paragraphs = 0
    evidence_paragraphs = 0
    for paragraph in soup.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        paragraph_words = len(text.split())
        if 50 <= paragraph_words <= 150 and _CITABLE_FACT_NUMERIC_RE.search(text):
            quotable_paragraphs += 1
        if _EVIDENCE_RE.search(text) or paragraph.find("a", href=True):
            evidence_paragraphs += 1

    confident_markers = len(_CONFIDENT_RE.findall(body_text))
    hedge_markers = len(_HEDGE_BRIEF_RE.findall(body_text))
    confident_language = confident_markers >= max(2, hedge_markers + 1)
    contradiction_markers = len(_CONTRADICTION_RE.findall(body_text))
    technical_specs = bool(_SPEC_RE.search(body_text) or soup.find("table") or soup.find(["code", "pre"]))

    repeated_terms = 0
    stuffing_detected = False
    if word_count >= 50:
        stop_words = {
            "about",
            "after",
            "again",
            "also",
            "because",
            "between",
            "content",
            "from",
            "have",
            "into",
            "that",
            "their",
            "there",
            "this",
            "with",
            "your",
        }
        counts: dict[str, int] = {}
        for word in words:
            if len(word) < 4 or word in stop_words:
                continue
            counts[word] = counts.get(word, 0) + 1
        repeated_terms = sum(1 for count in counts.values() if count / word_count > 0.05 and count >= 8)
        stuffing_detected = repeated_terms >= 2

    price_schema = _has_product_price_schema(jsonld_items)
    price_text = bool(_PRICE_RE.search(body_text))
    fresh_date = bool(dates["dateModified"] or dates["datePublished"] or _schema_has_dates(jsonld_items))
    current_year = datetime.now(tz=timezone.utc).year
    current_year_reference = bool(re.search(rf"\b{current_year}\b", body_text))
    comparison_text = bool(
        comparison_headings
        or re.search(
            r"\b(?:vs\.?|versus|compare|comparison|alternatives?|pros?\s+(?:and|&)\s+cons?)\b", body_text, re.I
        )
    )
    value_proposition = bool(_VALUE_RE.search(body_text))
    social_proof_schema = _has_rating_schema(jsonld_items)
    social_proof = bool(_SOCIAL_PROOF_RE.search(body_text) or social_proof_schema)
    crawlable = _has_indexable_meta(soup)
    retrieval_structure = bool(
        soup.find(["main", "article"])
        or len(headings) >= 2
        or re.search(r"\b(?:research shows|best practice|how to|what is|why does)\b", body_text, re.I)
    )
    formatting_structure = bool(len(headings) >= 2 or soup.find(["ul", "ol", "table"]))

    checks = {
        "price_or_product_detail": price_schema or price_text,
        "fresh_or_temporally_current": fresh_date or current_year_reference,
        "technical_specifications": technical_specs,
        "comparison_ready": comparison_text,
        "confident_language": confident_language,
        "evidence_backed": evidence_paragraphs >= 1 or bool(_EVIDENCE_RE.search(body_text)),
        "no_internal_contradictions": contradiction_markers == 0,
        "social_proof_present": social_proof,
        "value_proposition": value_proposition,
        "answer_first_sections": answer_first_sections >= 1,
        "snippet_ready_sections": snippet_sections >= 1,
        "quotable_chunks": quotable_paragraphs >= 1,
        "no_keyword_stuffing": not stuffing_detected,
        "retrievable_and_indexable": crawlable and retrieval_structure,
        "formatting_structure": formatting_structure,
    }
    passed = sum(1 for value in checks.values() if value)
    total = len(checks)
    missing = [name for name, value in checks.items() if not value]
    static_gatekeepers_pass = checks["price_or_product_detail"] and checks["fresh_or_temporally_current"]
    readiness = (
        "pass"
        if passed >= 10
        and static_gatekeepers_pass
        and checks["no_keyword_stuffing"]
        and checks["retrievable_and_indexable"]
        else "fail"
    )
    full_readiness = "manual_review" if readiness == "pass" else "fail"

    factor_groups = {
        "gatekeepers": [
            _factor(
                "topic_match",
                "manual_review",
                "Requires the target query/topic and AI response context; static HTML cannot prove perfect topic match.",
            ),
            _factor(
                "explicit_price_info",
                _pass_fail(checks["price_or_product_detail"]),
                "Product/service price is present in Product schema or visible pricing text.",
                {"has_product_price_schema": price_schema, "has_price_text": price_text},
            ),
            _factor(
                "recent_timestamp",
                _pass_fail(checks["fresh_or_temporally_current"]),
                "Recent date signal or current-year reference is present.",
                {
                    "date_modified": dates["dateModified"],
                    "date_published": dates["datePublished"],
                    "has_current_year_reference": current_year_reference,
                },
            ),
            _factor(
                "top_list_position",
                "manual_review",
                "Requires querying the answer engine and checking whether this source/brand is ranked first.",
            ),
        ],
        "differentiators": [
            _factor(
                "technical_specifications",
                _pass_fail(checks["technical_specifications"]),
                "Specs, feature tables, technical terms, or code-like detail are present.",
            ),
            _factor(
                "comparisons",
                _pass_fail(checks["comparison_ready"]),
                "Comparison, alternatives, vs, or pros/cons language is present.",
                {"comparison_headings": comparison_headings},
            ),
            _factor(
                "confident_language",
                _pass_fail(checks["confident_language"]),
                "Assertive claims outnumber hedging markers.",
                {"confident_markers": confident_markers, "hedge_markers": hedge_markers},
            ),
            _factor(
                "evidence_backed_claims",
                _pass_fail(checks["evidence_backed"]),
                "Claims are supported by sources, data, research, methodology, or outbound evidence links.",
                {"evidence_paragraphs": evidence_paragraphs},
            ),
            _factor(
                "no_internal_contradictions",
                _pass_fail(checks["no_internal_contradictions"]),
                "No contradiction/conflict markers were detected in the page text.",
                {"contradiction_markers": contradiction_markers},
            ),
            _factor(
                "value_proposition_and_social_proof",
                _pass_fail(checks["value_proposition"] and checks["social_proof_present"]),
                "Value proposition and trust/social proof signals are present.",
                {"has_value_proposition": value_proposition, "has_social_proof": social_proof},
            ),
        ],
        "low_priority": [
            _factor(
                "formatting_structure_only",
                _pass_fail(checks["formatting_structure"]),
                "Headings, lists, or tables help readability, but formatting alone is low impact.",
            )
        ],
        "retrieval_path": [
            _factor(
                "retrievable_and_indexable",
                _pass_fail(checks["retrievable_and_indexable"]),
                "Page appears indexable and has enough semantic structure for retrieval.",
                {"indexable": crawlable, "retrieval_structure": retrieval_structure},
            )
        ],
    }

    return MethodScore(
        name="ai_search_content_brief",
        label="AI Search Content Brief",
        detected=readiness == "pass",
        score=min(passed, 10),
        max_score=10,
        impact="readiness",
        details={
            "readiness": readiness,
            "full_readiness": full_readiness,
            "passed": passed,
            "total": total,
            "checks": {name: _pass_fail(value) for name, value in checks.items()},
            "factor_groups": factor_groups,
            "manual_review_required": ["topic_match", "top_list_position"],
            "missing": missing,
            "answer_first_sections": answer_first_sections,
            "snippet_ready_sections": snippet_sections,
            "question_headings": question_headings,
            "comparison_headings": comparison_headings,
            "quotable_paragraphs": quotable_paragraphs,
            "evidence_paragraphs": evidence_paragraphs,
            "confident_markers": confident_markers,
            "hedge_markers": hedge_markers,
            "contradiction_markers": contradiction_markers,
            "has_product_price_schema": price_schema,
            "has_price_text": price_text,
            "has_date_signal": fresh_date,
            "has_current_year_reference": current_year_reference,
            "has_social_proof_schema": social_proof_schema,
            "has_value_proposition": value_proposition,
            "repeated_terms": repeated_terms,
            "indexable": crawlable,
            "retrieval_structure": retrieval_structure,
            "source": "arXiv:2605.25517",
        },
    )


def resolve_ai_search_content_brief_context(
    brief: MethodScore,
    *,
    target_query: str,
    source: str,
    ai_response: str,
    cited_sources: list[str] | None = None,
) -> MethodScore:
    """Resolve query-aware AI-search brief factors from answer-engine context.

    Static page analysis cannot know whether a page perfectly matches the
    user's query or appears first in an AI answer. This second-stage resolver
    accepts the AI response/citation context and fills those factors without
    performing any network access or model calls.
    """
    explicit_sources = [item for item in (cited_sources or []) if item]
    response_sources = _extract_response_sources(ai_response)
    all_sources = explicit_sources + [item for item in response_sources if item not in explicit_sources]

    source_text = " ".join(all_sources)
    source_cited = _contains_source(source_text, source) or _contains_source(ai_response, source)
    first_candidate = _first_ranked_candidate(ai_response)
    top_recommendation = _contains_source(first_candidate, source)
    topic_match, topic_overlap = _topic_match(target_query, ai_response)

    brief_data = _brief_details(brief.details)
    factor_groups = dict(brief_data.get("factor_groups", {}))
    gatekeepers = list(factor_groups.get("gatekeepers", []))
    updated_gatekeepers = []
    for factor in gatekeepers:
        if not isinstance(factor, dict):
            updated_gatekeepers.append(factor)
            continue
        factor = dict(factor)
        if factor.get("name") == "topic_match":
            factor["status"] = _manual_status(topic_match)
            factor["evidence"] = {
                "target_query": target_query,
                "query_overlap": topic_overlap,
            }
        elif factor.get("name") == "top_list_position":
            factor["status"] = _pass_fail(top_recommendation)
            factor["evidence"] = {
                "first_candidate": first_candidate,
                "source": source,
            }
        updated_gatekeepers.append(factor)
    factor_groups["gatekeepers"] = updated_gatekeepers

    if not source_cited:
        readiness = "retrieval_gap"
        next_step = (
            "Focus on retrieval: improve traditional SEO, ranking, and crawl/indexability before content-factor tuning."
        )
    elif top_recommendation and topic_match is not False:
        readiness = "top_recommendation"
        next_step = "High GEO visibility reached; re-test periodically and track factor deltas."
    else:
        readiness = "content_gap"
        next_step = "Fix failed gatekeepers and differentiators, then re-query the answer engine."

    return MethodScore(
        name="ai_search_query_readiness",
        label="AI Search Query Readiness",
        detected=readiness == "top_recommendation",
        score=3 if readiness == "top_recommendation" else 1 if source_cited else 0,
        max_score=3,
        impact="query-aware readiness",
        details={
            "readiness": readiness,
            "target_query": target_query,
            "source": source,
            "source_cited": source_cited,
            "top_recommendation": top_recommendation,
            "topic_match": topic_match,
            "topic_overlap": topic_overlap,
            "first_candidate": first_candidate,
            "cited_sources": all_sources,
            "factor_groups": factor_groups,
            "next_step": next_step,
            "source_brief_readiness": brief_data.get("readiness"),
            "source_brief_missing": brief_data.get("missing", []),
        },
    )


# ─── 28. Blog Structure (#230) ───────────────────────────────────────────────


def detect_blog_structure(soup) -> MethodScore:
    """Detect blog structure signals in Article/BlogPosting schema.

    Checks: datePublished/dateModified, author bio, categories/tags.
    Only scores if Article or BlogPosting schema is present (non-blog pages get 0).
    """
    # Look for Article or BlogPosting schema in JSON-LD
    article_schema = None
    for item in _iter_jsonld_items(soup):
        if any(t in ("Article", "BlogPosting", "NewsArticle") for t in _jsonld_types(item)):
            article_schema = item
            break

    # If no Article/BlogPosting schema, score 0 without penalty
    if not article_schema:
        return MethodScore(
            name="blog_structure",
            label="Blog Structure",
            detected=False,
            score=0,
            max_score=4,
            impact="+8%",
            details={"has_article_schema": False},
        )

    score = 0
    has_dates = bool(article_schema.get("datePublished") or article_schema.get("dateModified"))
    has_author = bool(article_schema.get("author"))
    # Look for categories/tags in meta tags or schema
    has_categories = bool(
        article_schema.get("articleSection")
        or article_schema.get("keywords")
        or soup.find("meta", attrs={"property": "article:tag"})
    )
    # Look for author bio in the DOM
    author_bio = soup.find_all(
        ["div", "section", "aside"],
        class_=re.compile(r"author|bio|about-author|byline", re.I),
    )
    has_author_bio = bool(author_bio)

    if has_dates:
        score += 1
    if has_author:
        score += 1
    if has_author_bio:
        score += 1
    if has_categories:
        score += 1

    return MethodScore(
        name="blog_structure",
        label="Blog Structure",
        detected=score >= 2,
        score=min(score, 4),
        max_score=4,
        impact="+8%",
        details={
            "has_article_schema": True,
            "has_dates": has_dates,
            "has_author": has_author,
            "has_author_bio": has_author_bio,
            "has_categories": has_categories,
        },
    )


# ─── Answer Capsule Detection (#372) ─────────────────────────────────────────


def detect_answer_capsule(soup, clean_text: str | None = None) -> MethodScore:
    """Detect self-contained answer paragraphs extractable by RAG systems (#372).

    An answer capsule is a paragraph that:
    1. Starts with a direct statement (not a question or transition)
    2. Contains a concrete fact (number, name, date)
    3. Is 30-120 words (fits in a single RAG chunk)
    4. Ends with a complete sentence (not truncated)
    """
    paragraphs = soup.find_all("p")
    if not paragraphs:
        return MethodScore(
            name="answer_capsule",
            label="Answer Capsule Detection",
            max_score=4,
            impact="+12%",
        )

    capsule_count = 0
    total_candidates = 0

    for p in paragraphs:
        text = p.get_text(strip=True)
        words = text.split()
        word_count = len(words)

        # Only paragraphs in the 30-120 word range (RAG chunk sweet spot)
        if word_count < 30 or word_count > 120:
            continue
        total_candidates += 1

        # Must end with sentence-ending punctuation
        if not _SENTENCE_END_RE.search(text[-3:]):
            continue

        # Must contain a concrete fact (number, percentage, date, proper noun)
        if not _CITABLE_FACT_NUMERIC_RE.search(text):
            continue

        # Must start with a direct statement (not a question or weak opener)
        first_word = words[0].lower().rstrip(",:")
        if first_word in (
            "however",
            "but",
            "although",
            "moreover",
            "furthermore",
            "additionally",
            "nevertheless",
            "meanwhile",
        ):
            continue

        capsule_count += 1

    ratio = capsule_count / total_candidates if total_candidates > 0 else 0

    if ratio >= 0.4:
        score = 4
    elif ratio >= 0.25:
        score = 3
    elif ratio >= 0.15:
        score = 2
    elif capsule_count >= 1:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="answer_capsule",
        label="Answer Capsule Detection",
        detected=capsule_count >= 2,
        score=min(score, 4),
        max_score=4,
        impact="+12%",
        details={
            "capsule_count": capsule_count,
            "total_candidates": total_candidates,
            "ratio": round(ratio, 2),
        },
    )
