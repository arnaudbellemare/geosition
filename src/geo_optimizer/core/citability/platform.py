"""Citability: platform and distribution readiness detection functions.

Covers: shopping readiness, ChatGPT shopping, voice search, multi-platform
presence, international GEO, accessibility signals, conversion funnel,
crawl budget, anchor text quality, image alt quality.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from geo_optimizer.core.citability._helpers import _iter_jsonld_items, _jsonld_types
from geo_optimizer.models.results import MethodScore

# ─── Constants for this module ───────────────────────────────────────────────

# Generic anchor text to penalize
_GENERIC_ANCHORS = {
    "click here",
    "read more",
    "learn more",
    "here",
    "this",
    "link",
    "more",
    "continue",
    "go",
    "see more",
    "clicca qui",
    "leggi di più",
    "scopri di più",
    "qui",
    "questo",
}

# Recognized platforms for multi-platform presence
_PLATFORM_DOMAINS = {
    "github.com": "GitHub",
    "linkedin.com": "LinkedIn",
    "twitter.com": "Twitter/X",
    "x.com": "Twitter/X",
    "youtube.com": "YouTube",
    "reddit.com": "Reddit",
    "wikipedia.org": "Wikipedia",
    "medium.com": "Medium",
    "facebook.com": "Facebook",
}

# Pattern for headings in natural question format (EN + IT)
_QUESTION_HEADING_RE = re.compile(
    r"^(?:how\s+(?:do|can|to|does)|what\s+is|what\s+are|why\s+(?:do|is|are|does)"
    r"|when\s+(?:do|is|should)|where\s+(?:do|can|is)|which\s+(?:is|are)"
    r"|come\s+(?:funziona|fare|si)|cosa\s+(?:è|sono)|perché\s+(?:è|si)"
    r"|qual\s+è|quali\s+sono|quando\s+(?:è|si))",
    re.IGNORECASE,
)

# Pattern for generic alt text to penalize
_GENERIC_ALT_RE = re.compile(
    r"^(?:image|photo|picture|img|foto|immagine|screenshot|banner|icon|logo"
    r"|img\d+|image\d+|photo\d+|dsc\d+|pic\d+|untitled)$",
    re.IGNORECASE,
)

# Positive CTA patterns for conversion funnel (fix #25: renamed to avoid overwriting aggressive _CTA_RE)
_CTA_FUNNEL_RE = re.compile(
    r"\b(?:try\s+(?:it\s+)?(?:free|now)|start\s+(?:free|now|your)"
    r"|sign\s+up|get\s+started|request\s+(?:a\s+)?demo"
    r"|free\s+trial|book\s+(?:a\s+)?demo|inizia\s+(?:ora|gratis)"
    r"|provalo?\s+(?:gratis|ora)|registrati)\b",
    re.IGNORECASE,
)


# ─── 14. Image Alt Text Quality (+8%) ────────────────────────────────────────


def detect_image_alt_quality(soup) -> MethodScore:
    """Detect image alt text quality: penalize missing or generic alt text."""
    images = soup.find_all("img")
    if not images:
        # No images = neutral score
        return MethodScore(
            name="image_alt_quality",
            label="Image Alt Quality",
            detected=False,
            score=3,
            max_score=5,
            impact="+8%",
            details={"total_images": 0, "with_alt": 0, "descriptive_alt": 0, "generic_alt": 0, "missing_alt": 0},
        )

    missing_alt = 0
    generic_alt = 0
    descriptive_alt = 0

    for img in images:
        alt = img.get("alt")
        if alt is None or alt.strip() == "":
            missing_alt += 1
        elif _GENERIC_ALT_RE.match(alt.strip()):
            generic_alt += 1
        elif len(alt.strip()) > 10:
            descriptive_alt += 1
        else:
            # Short alt text but not generic — counts as partial
            generic_alt += 1

    total = len(images)
    descriptive_ratio = descriptive_alt / total if total > 0 else 0

    # Score based on alt text quality
    score = 0
    if descriptive_ratio >= 0.8:
        score = 5
    elif descriptive_ratio >= 0.5:
        score = 3
    elif descriptive_ratio >= 0.2:
        score = 2
    elif missing_alt == 0:
        score = 1

    return MethodScore(
        name="image_alt_quality",
        label="Image Alt Quality",
        detected=descriptive_ratio >= 0.5,
        score=min(score, 5),
        max_score=5,
        impact="+8%",
        details={
            "total_images": total,
            "with_alt": total - missing_alt,
            "descriptive_alt": descriptive_alt,
            "generic_alt": generic_alt,
            "missing_alt": missing_alt,
        },
    )


# ─── 29. AI Shopping Readiness (#277) ────────────────────────────────────────


def detect_shopping_readiness(soup) -> MethodScore:
    """Detect AI shopping readiness from Product schema.

    Checks: Product schema with price + availability, AggregateRating, review count.
    Only scores if Product schema is present (non-ecommerce pages get 0).
    """
    product_schema = None
    for item in _iter_jsonld_items(soup):
        if "Product" in _jsonld_types(item):
            product_schema = item
            break

    if not product_schema:
        return MethodScore(
            name="shopping_readiness",
            label="AI Shopping Readiness",
            detected=False,
            score=0,
            max_score=3,
            impact="+8%",
            details={"has_product_schema": False},
        )

    score = 0
    # Verify price + availability in the offer
    offers = product_schema.get("offers") or product_schema.get("offer", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    has_price = bool(offers.get("price") or offers.get("lowPrice"))
    has_availability = bool(offers.get("availability"))

    if has_price and has_availability:
        score += 1

    # AggregateRating
    has_rating = bool(product_schema.get("aggregateRating"))
    if has_rating:
        score += 1

    # Review count
    rating_data = product_schema.get("aggregateRating", {})
    has_review_count = bool(rating_data.get("reviewCount") or rating_data.get("ratingCount"))
    if has_review_count:
        score += 1

    return MethodScore(
        name="shopping_readiness",
        label="AI Shopping Readiness",
        detected=score >= 1,
        score=min(score, 3),
        max_score=3,
        impact="+8%",
        details={
            "has_product_schema": True,
            "has_price": has_price,
            "has_availability": has_availability,
            "has_rating": has_rating,
            "has_review_count": has_review_count,
        },
    )


# ─── 30. ChatGPT Shopping Feed (#275) ────────────────────────────────────────


def detect_chatgpt_shopping(soup) -> MethodScore:
    """Detect ChatGPT Shopping integration signals from Product schema.

    Checks required fields for ChatGPT Shopping: name, price, image, availability, brand.
    Cannot verify chatgpt.com/merchants registration, but verifies field completeness.
    """
    product_schema = None
    for item in _iter_jsonld_items(soup):
        if "Product" in _jsonld_types(item):
            product_schema = item
            break

    if not product_schema:
        return MethodScore(
            name="chatgpt_shopping",
            label="ChatGPT Shopping Feed",
            detected=False,
            score=0,
            max_score=3,
            impact="+8%",
            details={"has_product_schema": False},
        )

    # Required fields for ChatGPT Shopping
    has_name = bool(product_schema.get("name"))
    has_image = bool(product_schema.get("image"))
    has_brand = bool(product_schema.get("brand"))

    offers = product_schema.get("offers") or product_schema.get("offer", {})
    if isinstance(offers, list):
        offers = offers[0] if offers else {}
    has_price = bool(offers.get("price") or offers.get("lowPrice"))
    has_availability = bool(offers.get("availability"))

    # Count fields present out of 5 required
    fields_present = sum([has_name, has_image, has_brand, has_price, has_availability])

    if fields_present >= 5:
        score = 3
    elif fields_present >= 3:
        score = 2
    elif fields_present >= 1:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="chatgpt_shopping",
        label="ChatGPT Shopping Feed",
        detected=fields_present >= 3,
        score=min(score, 3),
        max_score=3,
        impact="+8%",
        details={
            "has_product_schema": True,
            "has_name": has_name,
            "has_image": has_image,
            "has_brand": has_brand,
            "has_price": has_price,
            "has_availability": has_availability,
            "fields_present": fields_present,
            "fields_required": 5,
        },
    )


# ─── Voice/Conversational Search (+5%) — Batch A v3.16.0 ─────────────────────


def detect_voice_search(soup) -> MethodScore:
    """Detect voice/conversational search readiness signals."""
    score = 0
    question_headings = 0
    concise_answers = 0
    has_speakable = False

    # 1. Look for headings in natural question format
    headings = soup.find_all(re.compile(r"^h[1-6]$", re.I))
    for h in headings:
        text = h.get_text(strip=True)
        if "?" in text or _QUESTION_HEADING_RE.search(text):
            question_headings += 1
            # Look for a concise answer after a "?" heading
            if "?" in text:
                next_p = h.find_next("p")
                if next_p:
                    words = next_p.get_text(strip=True).split()
                    if 0 < len(words) < 60:
                        concise_answers += 1

    if question_headings >= 2:
        score += 1
    if concise_answers >= 1:
        score += 1

    # 2. Look for speakable schema in any JSON-LD
    for item in _iter_jsonld_items(soup):
        if "speakable" in item:
            has_speakable = True
            break

    if has_speakable:
        score += 1

    return MethodScore(
        name="voice_search_ready",
        label="Voice/Conversational Search",
        detected=question_headings >= 2 or has_speakable,
        score=min(score, 3),
        max_score=3,
        impact="+5%",
        details={
            "question_headings": question_headings,
            "concise_answers": concise_answers,
            "has_speakable_schema": has_speakable,
        },
    )


# ─── Multi-Platform Presence (+10%) — Batch A v3.16.0 ────────────────────────


def detect_multi_platform(soup) -> MethodScore:
    """Detect multi-platform presence via sameAs URLs in schema."""
    platforms_found: set[str] = set()

    # Extract sameAs from all JSON-LD schemas
    for item in _iter_jsonld_items(soup):
        same_as = item.get("sameAs", [])
        if isinstance(same_as, str):
            same_as = [same_as]
        for url in same_as:
            if not isinstance(url, str):
                continue
            parsed = urlparse(url)
            domain = parsed.netloc.lower().removeprefix("www.")
            for plat_domain, plat_name in _PLATFORM_DOMAINS.items():
                if domain.endswith(plat_domain):
                    platforms_found.add(plat_name)

    count = len(platforms_found)
    if count >= 5:
        score = 4
    elif count >= 3:
        score = 2
    else:
        score = 0

    return MethodScore(
        name="multi_platform",
        label="Multi-Platform Presence",
        detected=count >= 3,
        score=min(score, 4),
        max_score=4,
        impact="+10%",
        details={
            "platforms_found": sorted(platforms_found),
            "platform_count": count,
        },
    )


# ─── Accessibility as Signal (+5%) — Batch A v3.16.0 ─────────────────────────


def detect_accessibility_signals(soup) -> MethodScore:
    """Detect accessibility signals: semantic HTML, ARIA landmarks, skip links."""
    score = 0

    # 1. Semantic HTML tags
    semantic_tags = {"main", "nav", "header", "footer"}
    found_semantic = set()
    for tag_name in semantic_tags:
        if soup.find(tag_name):
            found_semantic.add(tag_name)

    if len(found_semantic) >= 3:
        score += 1

    # 2. ARIA landmarks
    aria_roles = {"main", "navigation", "banner", "contentinfo"}
    found_aria = set()
    for role in aria_roles:
        if soup.find(attrs={"role": role}):
            found_aria.add(role)

    if found_aria:
        score += 1

    # 3. Skip link
    has_skip_link = False
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if href in ("#main", "#content", "#main-content", "#maincontent"):
            has_skip_link = True
            break
        # Also check for "skip to" text
        link_text = a.get_text(strip=True).lower()
        if "skip to" in link_text or "vai al contenuto" in link_text:
            has_skip_link = True
            break

    if has_skip_link:
        score += 1

    return MethodScore(
        name="accessibility_signals",
        label="Accessibility Signals",
        detected=score >= 1,
        score=min(score, 3),
        max_score=3,
        impact="+5%",
        details={
            "semantic_tags": sorted(found_semantic),
            "aria_landmarks": sorted(found_aria),
            "has_skip_link": has_skip_link,
        },
    )


# ─── AI Conversion Funnel (+8%) — Batch A v3.16.0 ────────────────────────────


def detect_conversion_funnel(soup) -> MethodScore:
    """Detect AI conversion funnel signals: CTAs, pricing links, contact info."""
    score = 0

    # 1. Visible CTA (button/link with CTA pattern)
    has_cta = False
    for tag in soup.find_all(["a", "button"]):
        text = tag.get_text(strip=True)
        if _CTA_FUNNEL_RE.search(text):
            has_cta = True
            break

    if has_cta:
        score += 1

    # 2. Pricing page link
    has_pricing = False
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if "pricing" in href or "plans" in href or "prezzi" in href:
            has_pricing = True
            break

    if has_pricing:
        score += 1

    # 3. Contact info (href with "contact", "mailto:")
    has_contact = False
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        if "contact" in href or "mailto:" in href or "contatti" in href:
            has_contact = True
            break

    if has_contact:
        score += 1

    return MethodScore(
        name="conversion_funnel",
        label="AI Conversion Funnel",
        detected=score >= 1,
        score=min(score, 3),
        max_score=3,
        impact="+8%",
        details={
            "has_cta": has_cta,
            "has_pricing_link": has_pricing,
            "has_contact": has_contact,
        },
    )


# ─── International GEO (+5%) — Batch B v3.16.0 ─────────────────────────────


def detect_international_geo(soup) -> MethodScore:
    """Detect international GEO signals: hreflang tags, html lang, schema inLanguage.

    Only scores if the site HAS hreflang tags — does not penalize monolingual sites.
    """
    score = 0

    # 1. <html lang="...">
    html_tag = soup.find("html")
    html_lang = html_tag.get("lang", "").strip() if html_tag else ""

    # 2. <link rel="alternate" hreflang="..."> tags
    hreflang_tags = soup.find_all("link", attrs={"rel": "alternate", "hreflang": True})
    hreflang_langs = [tag.get("hreflang", "") for tag in hreflang_tags if tag.get("hreflang")]

    # 3. Schema inLanguage
    in_language = None
    for item in _iter_jsonld_items(soup):
        if "inLanguage" in item:
            in_language = item["inLanguage"]
            break

    # Only assign a score if the site has hreflang
    has_hreflang = len(hreflang_langs) > 0

    if not has_hreflang:
        # Monolingual site: neutral score (0), do not penalize
        return MethodScore(
            name="international_geo",
            label="International GEO",
            detected=False,
            score=0,
            max_score=3,
            impact="+5%",
            details={
                "html_lang": html_lang,
                "hreflang_count": 0,
                "hreflang_langs": [],
                "schema_inLanguage": in_language,
                "is_multilingual": False,
            },
        )

    # Has hreflang: assign score
    if len(hreflang_langs) >= 3:
        score += 2
    elif len(hreflang_langs) >= 1:
        score += 1

    if in_language:
        score += 1

    return MethodScore(
        name="international_geo",
        label="International GEO",
        detected=True,
        score=min(score, 3),
        max_score=3,
        impact="+5%",
        details={
            "html_lang": html_lang,
            "hreflang_count": len(hreflang_langs),
            "hreflang_langs": hreflang_langs,
            "schema_inLanguage": in_language,
            "is_multilingual": True,
        },
    )


# ─── AI Crawl Budget (+5%) — Batch B v3.16.0 ────────────────────────────────


def detect_crawl_budget(soup) -> MethodScore:
    """Detect AI crawl budget signals from HTML meta tags and head links.

    Since citability analysis only has access to HTML (not robots.txt),
    checks: link rel='sitemap' in head, meta robots noindex/nofollow penalties.
    """
    score = 3  # Full score by default, with penalties
    penalties = []

    # 1. Check meta robots for noindex/nofollow
    meta_robots = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.I)})
    has_noindex = False
    has_nofollow = False
    if meta_robots:
        content = (meta_robots.get("content") or "").lower()
        if "noindex" in content:
            has_noindex = True
            penalties.append("meta robots noindex")
            score -= 2
        if "nofollow" in content:
            has_nofollow = True
            penalties.append("meta robots nofollow")
            score -= 1

    # 2. Check X-Robots-Tag meta (alternative)
    meta_x_robots = soup.find("meta", attrs={"http-equiv": re.compile(r"x-robots-tag", re.I)})
    if meta_x_robots:
        content = (meta_x_robots.get("content") or "").lower()
        if "noindex" in content and not has_noindex:
            has_noindex = True
            penalties.append("X-Robots-Tag noindex")
            score -= 2
        if "nofollow" in content and not has_nofollow:
            has_nofollow = True
            penalties.append("X-Robots-Tag nofollow")
            score -= 1

    # 3. Look for link rel="sitemap" in <head>
    has_sitemap_link = False
    sitemap_link = soup.find("link", attrs={"rel": "sitemap"})
    if sitemap_link and sitemap_link.get("href"):
        has_sitemap_link = True

    # Bonus if sitemap is referenced in head (positive signal for AI crawlers)
    if not has_sitemap_link and score > 0:
        # No penalty, but no bonus either
        pass

    score = max(score, 0)

    return MethodScore(
        name="crawl_budget",
        label="AI Crawl Budget",
        detected=not has_noindex and not has_nofollow,
        score=min(score, 3),
        max_score=3,
        impact="+5%",
        details={
            "has_noindex": has_noindex,
            "has_nofollow": has_nofollow,
            "has_sitemap_link": has_sitemap_link,
            "penalties": penalties,
        },
    )


# ─── Internal Link Anchor Text (+5%) — Batch B v3.16.0 ──────────────────────


def detect_anchor_text_quality(soup, base_url: str) -> MethodScore:
    """Detect internal link anchor text quality.

    Counts internal links with generic anchor text ('click here', 'read more',
    'here', etc.) vs descriptive anchor text (> 3 words, not generic).
    Score: > 80% descriptive = full, < 50% = 0.
    """
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.replace("www.", "")

    generic_count = 0
    descriptive_count = 0
    total_internal = 0

    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Determine if it's an internal link
        if href.startswith("http"):
            link_domain = urlparse(href).netloc.replace("www.", "")
            if link_domain != base_domain:
                continue  # External link, skip
        elif href.startswith("#") or href.startswith("mailto:") or href.startswith("tel:"):
            continue  # Internal anchor or mailto/tel, skip

        # Internal link
        anchor_text = a.get_text(strip=True).lower()
        if not anchor_text:
            continue

        total_internal += 1

        # Check if it's generic
        if anchor_text in _GENERIC_ANCHORS:
            generic_count += 1
        elif len(anchor_text.split()) > 3:
            descriptive_count += 1
        else:
            # Short anchor (1-3 words) but not generic — counts as partial
            descriptive_count += 1

    if total_internal == 0:
        # No internal links: neutral score
        return MethodScore(
            name="anchor_text_quality",
            label="Anchor Text Quality",
            detected=False,
            score=2,
            max_score=3,
            impact="+5%",
            details={
                "total_internal_links": 0,
                "generic_count": 0,
                "descriptive_count": 0,
                "descriptive_ratio": 0,
            },
        )

    descriptive_ratio = descriptive_count / total_internal

    if descriptive_ratio >= 0.8:
        score = 3
    elif descriptive_ratio >= 0.5:
        score = 2
    elif descriptive_ratio > 0:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="anchor_text_quality",
        label="Anchor Text Quality",
        detected=descriptive_ratio >= 0.8,
        score=min(score, 3),
        max_score=3,
        impact="+5%",
        details={
            "total_internal_links": total_internal,
            "generic_count": generic_count,
            "descriptive_count": descriptive_count,
            "descriptive_ratio": round(descriptive_ratio, 2),
        },
    )
