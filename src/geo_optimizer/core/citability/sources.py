"""Citability: source citation, quotation, statistics, attribution, social proof,
first-party data detection functions."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from geo_optimizer.core.citability._helpers import (
    _AUTHORITATIVE_DOMAINS,
    _AUTHORITATIVE_TLDS,
    _AUTHORITY_RE,
    _QUOTE_ATTRIBUTION_RE,
    _STAT_RE,
    _get_clean_text,
    _iter_jsonld_items,
)
from geo_optimizer.models.results import MethodScore

# ─── 1. Cite Sources (+27%) ──────────────────────────────────────────────────


def detect_cite_sources(soup, base_url: str) -> MethodScore:
    """Detect citations to authoritative sources (.edu, .gov, Wikipedia, etc.)."""
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.replace("www.", "")

    authoritative_count = 0
    external_count = 0

    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not href.startswith("http"):
            continue
        link_domain = urlparse(href).netloc.replace("www.", "")
        if link_domain == base_domain:
            continue
        external_count += 1
        tld = "." + link_domain.split(".")[-1] if "." in link_domain else ""
        if tld in _AUTHORITATIVE_TLDS or any(d in link_domain for d in _AUTHORITATIVE_DOMAINS):
            authoritative_count += 1

    # References/bibliography section
    ref_headings = [
        h
        for h in soup.find_all(["h2", "h3", "h4"])
        if re.search(r"references?|sources?|bibliograph|citazion", h.get_text(), re.I)
    ]
    cite_tags = len(soup.find_all("cite"))

    score = min(authoritative_count * 2 + external_count + cite_tags * 2 + len(ref_headings) * 2, 6)
    detected = authoritative_count >= 2 or bool(ref_headings) or cite_tags >= 1

    return MethodScore(
        name="cite_sources",
        label="Cite Sources",
        detected=detected,
        score=score,
        max_score=6,
        impact="+27%",
        details={
            "authoritative_links": authoritative_count,
            "external_links": external_count,
            "cite_tags": cite_tags,
            "has_reference_section": bool(ref_headings),
        },
    )


# ─── 2. Quotation Addition (+41%) ────────────────────────────────────────────


def detect_quotations(soup, clean_text: str | None = None) -> MethodScore:
    """Detect attributed quotes (blockquote, attributed quoted text)."""
    blockquotes = soup.find_all("blockquote")
    q_tags = soup.find_all("q")

    # Blockquote with cite attribute = formal citation
    bq_with_cite = [bq for bq in blockquotes if bq.get("cite") or bq.find("cite")]

    # Text pattern "..." — Author (fix #29: use clean_text to avoid noise)
    body_text = clean_text or _get_clean_text(soup)
    text_attributions = _QUOTE_ATTRIBUTION_RE.findall(body_text)

    # Pull quotes (CSS class)
    pull_quotes = soup.find_all(
        ["figure", "aside", "div"],
        class_=re.compile(r"pull.?quote|blockquote|testimonial", re.I),
    )

    total = len(blockquotes) + len(q_tags) + len(text_attributions) + len(pull_quotes)
    score = min(total * 2 + len(bq_with_cite) * 2, 6)

    return MethodScore(
        name="quotation_addition",
        label="Quotation Addition",
        detected=total >= 1,
        score=score,
        max_score=6,
        impact="+41%",
        details={
            "blockquotes": len(blockquotes),
            "q_tags": len(q_tags),
            "attributed_quotes": len(text_attributions),
            "pull_quotes": len(pull_quotes),
        },
    )


# ─── 3. Statistics Addition (+33%) ───────────────────────────────────────────


def detect_statistics(soup, clean_text: str | None = None) -> MethodScore:
    """Detect statistical and quantitative data in content."""
    body_text = clean_text or _get_clean_text(soup)
    matches = _STAT_RE.findall(body_text)

    # Tables with numerical data (separator=" " to avoid concatenation without spaces)
    tables_with_data = sum(1 for t in soup.find_all("table") if _STAT_RE.search(t.get_text(separator=" ")))

    # HTML5 data elements
    data_elements = len(soup.find_all(["data", "meter", "progress"]))

    word_count = max(len(body_text.split()), 1)
    density = len(matches) / word_count * 1000

    score = min(int(density * 2) + tables_with_data * 2 + data_elements, 6)

    return MethodScore(
        name="statistics_addition",
        label="Statistics Addition",
        detected=len(matches) >= 3,
        score=score,
        max_score=6,
        impact="+33%",
        details={
            "stat_matches": len(matches),
            "density_per_1000_words": round(density, 2),
            "tables_with_data": tables_with_data,
        },
    )


# ─── 19. Attribution Completeness (+12%) — Quality Signal Batch 2 ─────────────

# Pattern for inline attribution: "according to X", "X (2024) found that", etc.
_ATTRIBUTION_INLINE_RE = re.compile(
    r"\b(?:according to|as reported by|as noted by|as stated by"
    r"|secondo|come riportato da|come indicato da)\b"
    r"|(?:\w+\s+\(\d{4}\)\s+(?:found|showed|reported|demonstrated|noted|argued|claimed))",
    re.IGNORECASE,
)

# Pattern for footnotes: [1], [2], {1} — Fix #417: removed <sup> (counted separately below)
_FOOTNOTE_RE = re.compile(r"\[(\d{1,3})\]|\{\d{1,3}\}")


def detect_attribution(soup, clean_text: str | None = None) -> MethodScore:
    """Detect attribution completeness: inline citations, footnotes, sourced claims."""
    body_text = clean_text or _get_clean_text(soup)

    # Inline citations (close to the claim)
    inline_attributions = _ATTRIBUTION_INLINE_RE.findall(body_text)

    # Inline links near claim text (paragraphs with links + authoritative pattern)
    inline_link_citations = 0
    for p in soup.find_all("p"):
        p_text = p.get_text(strip=True)
        links_in_p = p.find_all("a", href=True)
        if links_in_p and _AUTHORITY_RE.search(p_text):
            inline_link_citations += 1

    # Footnotes (end of page)
    raw_html = str(soup)
    footnotes = _FOOTNOTE_RE.findall(raw_html)

    # Count sup tags with numbers (HTML footnotes)
    sup_footnotes = 0
    for sup in soup.find_all("sup"):
        sup_text = sup.get_text(strip=True)
        if sup_text.isdigit():
            sup_footnotes += 1

    total_inline = len(inline_attributions) + inline_link_citations
    total_footnotes = len(footnotes) + sup_footnotes

    # Score: inline citations weigh more than footnotes
    score = min(total_inline * 2 + total_footnotes, 5)

    return MethodScore(
        name="attribution_completeness",
        label="Attribution Completeness",
        detected=total_inline >= 1 or total_footnotes >= 2,
        score=min(score, 5),
        max_score=5,
        impact="+12%",
        details={
            "inline_attributions": total_inline,
            "footnotes": total_footnotes,
            "inline_link_citations": inline_link_citations,
        },
    )


# ─── Social Proof (+8%) — Batch A v3.16.0 ────────────────────────────────────


def detect_social_proof(soup, clean_text: str | None = None) -> MethodScore:
    """Detect social proof signals: testimonials, ratings, trust badges."""
    score = 0

    # 1. Testimonial: class="testimonial", blockquote with attribution, "as seen in"
    has_testimonial = False
    testimonial_divs = soup.find_all(
        ["div", "section", "aside"],
        class_=re.compile(r"testimonial|review|customer-quote", re.I),
    )
    if testimonial_divs:
        has_testimonial = True

    # Blockquote with attribution (person's name)
    blockquotes = soup.find_all("blockquote")
    for bq in blockquotes:
        # Look for cite or footer inside blockquote
        cite = bq.find(["cite", "footer", "figcaption"])
        if cite:
            has_testimonial = True
            break

    # Pattern "as seen in" / "as featured in"
    body_text = clean_text or _get_clean_text(soup)
    if re.search(r"\b(?:as\s+seen\s+in|as\s+featured\s+in|featured\s+by|trusted\s+by)\b", body_text, re.I):
        has_testimonial = True

    if has_testimonial:
        score += 1

    # 2. AggregateRating in schema with reviewCount > 10
    has_rating = False
    for item in _iter_jsonld_items(soup):
        try:
            rating = item.get("aggregateRating", {})
            if isinstance(rating, dict):
                review_count = int(rating.get("reviewCount", 0))
                if review_count > 10:
                    has_rating = True
        except (TypeError, ValueError):
            continue

    if has_rating:
        score += 1

    # 3. Trust badges, partner logos
    has_trust_badges = False
    badge_imgs = soup.find_all(
        "img",
        attrs={
            "alt": re.compile(r"badge|certified|partner|award|trust|seal|logo", re.I),
        },
    )
    if badge_imgs:
        has_trust_badges = True

    # Trust/partner section
    trust_sections = soup.find_all(
        ["div", "section"],
        class_=re.compile(r"partner|trust|badge|certified|award|client-logo", re.I),
    )
    if trust_sections:
        has_trust_badges = True

    if has_trust_badges:
        score += 1

    return MethodScore(
        name="social_proof",
        label="Social Proof",
        detected=score >= 1,
        score=min(score, 3),
        max_score=3,
        impact="+8%",
        details={
            "has_testimonial": has_testimonial,
            "has_aggregate_rating": has_rating,
            "has_trust_badges": has_trust_badges,
        },
    )


# ─── First-Party Data (+12%) — Batch A v3.16.0 ──────────────────────────────

# Pattern for first-party data signals
_FIRST_PARTY_PATTERNS = re.compile(
    r"\b(?:our\s+research|we\s+analyzed|our\s+data\s+shows?"
    r"|our\s+study|we\s+found|our\s+analysis|we\s+discovered"
    r"|we\s+tested|our\s+findings|we\s+measured"
    r"|la\s+nostra\s+ricerca|abbiamo\s+analizzato|i\s+nostri\s+dati)\b",
    re.IGNORECASE,
)

# Pattern for specific numbers attributed to the site itself (not external citations)
_OWN_DATA_RE = re.compile(
    r"\b(?:we|our\s+team|our\s+company)\s+\w+\s+\d+",
    re.IGNORECASE,
)


def detect_first_party_data(soup, clean_text: str | None = None) -> MethodScore:
    """Detect first-party data and original research signals."""
    body_text = clean_text or _get_clean_text(soup)
    score = 0

    # 1. Original research patterns
    first_party_matches = _FIRST_PARTY_PATTERNS.findall(body_text)
    if len(first_party_matches) >= 2:
        score += 2
    elif len(first_party_matches) >= 1:
        score += 1

    # 2. Specific numbers attributed to the site itself
    own_data_matches = _OWN_DATA_RE.findall(body_text)
    if own_data_matches:
        score += 1

    # 3. "Methodology" or "Methods" section
    has_methodology = False
    for h in soup.find_all(re.compile(r"^h[1-6]$", re.I)):
        h_text = h.get_text(strip=True).lower()
        if h_text in (
            "methodology",
            "methods",
            "our methodology",
            "research methodology",
            "metodologia",
            "metodo",
            "la nostra metodologia",
        ):
            has_methodology = True
            break
    if has_methodology:
        score += 1

    return MethodScore(
        name="first_party_data",
        label="First-Party Data",
        detected=score >= 2,
        score=min(score, 4),
        max_score=4,
        impact="+12%",
        details={
            "first_party_patterns": len(first_party_matches),
            "own_data_signals": len(own_data_matches),
            "has_methodology_section": has_methodology,
        },
    )
