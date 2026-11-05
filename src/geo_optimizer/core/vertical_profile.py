"""Vertical market profiling and auto-detection for GEO audits."""

from __future__ import annotations

import re
from typing import cast

from geo_optimizer.models.results import (
    BrandEntityResult,
    ContentResult,
    MetaResult,
    SchemaResult,
    VerticalAuditResult,
    VerticalSignal,
)

SUPPORTED_VERTICALS = {
    "auto",
    "generic",
    "ecommerce-retail",
    "travel-hospitality",
    "healthcare-dental",
    "real-estate-proptech",
    "legal-professional-services",
    "manufacturing-industrial-b2b",
    "financial-services-insurance",
    "saas-technology",
    "education-edtech-k12",
    "local-home-services",
}

_VERTICAL_ALIASES = {
    "property-management": "real-estate-proptech",
    "law-firm": "legal-professional-services",
    "accounting": "legal-professional-services",
    "contractor": "local-home-services",
    "clinic": "healthcare-dental",
}


def _extract_text(soup) -> str:
    if soup is None:
        return ""
    return cast(str, soup.get_text(" ", strip=True).lower())


def _find_anchor_patterns(soup, patterns: list[str]) -> list[str]:
    matches: list[str] = []
    if soup is None:
        return matches
    for anchor in soup.find_all("a", href=True):
        href = (anchor.get("href") or "").lower()
        label = anchor.get_text(" ", strip=True).lower()
        joined = f"{label} {href}"
        for pattern in patterns:
            if pattern in joined:
                snippet = label or href
                if snippet and snippet not in matches:
                    matches.append(snippet)
                break
    return matches


def _has_pattern(text: str, patterns: list[str]) -> bool:
    return any(pattern in text for pattern in patterns)


def _regex_count(text: str, pattern: str) -> int:
    return len(re.findall(pattern, text, flags=re.IGNORECASE))


def _vertical_keywords(vertical: str) -> list[str]:
    return {
        "ecommerce-retail": [
            "add to cart",
            "shop now",
            "size guide",
            "sku",
            "product details",
            "shipping",
            "returns",
        ],
        "travel-hospitality": [
            "itinerary",
            "travel guide",
            "book now",
            "hotel",
            "vacation",
            "things to do",
            "near me",
        ],
        "healthcare-dental": [
            "clinic",
            "patient",
            "book appointment",
            "treatment",
            "dental",
            "crown",
            "insurance accepted",
        ],
        "real-estate-proptech": [
            "property management",
            "realtor",
            "listing",
            "buying guide",
            "selling guide",
            "tenant",
            "landlord",
            "neighborhood",
        ],
        "legal-professional-services": [
            "law firm",
            "attorney",
            "lawyer",
            "legal counsel",
            "financial advisory",
            "tax planning",
            "consultation",
        ],
        "manufacturing-industrial-b2b": [
            "specifications",
            "precision machining",
            "industrial",
            "robotics",
            "datasheet",
            "rfq",
            "case study",
        ],
        "financial-services-insurance": [
            "insurance quote",
            "premium",
            "coverage",
            "financial planning",
            "apr",
            "rates",
            "policy",
        ],
        "saas-technology": [
            "start free trial",
            "book demo",
            "api",
            "integration",
            "platform",
            "use cases",
            "product update",
        ],
        "education-edtech-k12": [
            "curriculum",
            "lesson plan",
            "k-12",
            "teacher",
            "student",
            "parent",
            "enrollment",
        ],
        "local-home-services": [
            "hvac",
            "plumbing",
            "roofing",
            "pool builder",
            "free estimate",
            "service area",
            "licensed and insured",
        ],
    }.get(vertical, [])


def infer_business_vertical(soup, base_url: str, meta: MetaResult) -> tuple[str, float]:
    """Infer business type from URL, title, and on-page text."""
    text = _extract_text(soup)
    combined = f"{base_url.lower()} {(meta.title_text or '').lower()} {text[:5000]}"

    scores: dict[str, int] = {v: 0 for v in SUPPORTED_VERTICALS if v not in {"auto", "generic"}}
    for vertical in scores:
        for kw in _vertical_keywords(vertical):
            if kw in combined:
                scores[vertical] += 1

    if "/shop" in combined or "product" in combined or "category" in combined:
        scores["ecommerce-retail"] += 2
    if "/properties" in combined or "/listings" in combined:
        scores["real-estate-proptech"] += 2
    if "/demo" in combined or "/pricing" in combined:
        scores["saas-technology"] += 1

    best_vertical = "generic"
    best_score = 0
    for vertical, score in scores.items():
        if score > best_score:
            best_vertical = vertical
            best_score = score

    if best_score <= 1:
        return "generic", 0.2
    confidence = min(0.95, 0.4 + (best_score * 0.1))
    return best_vertical, confidence


def audit_vertical_profile(
    soup,
    base_url: str,
    schema: SchemaResult,
    meta: MetaResult,
    content: ContentResult,
    brand_entity: BrandEntityResult,
    vertical: str = "auto",
    market_locale: str = "en",
) -> VerticalAuditResult:
    """Builds a market-facing readiness profile from existing audit data."""
    requested_vertical = _VERTICAL_ALIASES.get(vertical, vertical)
    if requested_vertical == "auto":
        detected_vertical, confidence = infer_business_vertical(soup, base_url=base_url, meta=meta)
        effective_vertical = detected_vertical
    else:
        detected_vertical, confidence = requested_vertical, 1.0
        effective_vertical = requested_vertical if requested_vertical in SUPPORTED_VERTICALS else "generic"
    effective_locale = market_locale.lower().strip() if market_locale else "en"

    result = VerticalAuditResult(
        checked=True,
        vertical=effective_vertical,
        detected_vertical=detected_vertical,
        detection_confidence=confidence,
        market_locale=effective_locale,
    )
    text = _extract_text(soup)

    trust_patterns = [
        "licensed",
        "insured",
        "certified",
        "accredited",
        "testimonials",
        "reviews",
        "case study",
        "years of experience",
        "trusted by",
    ]
    conversion_patterns = [
        "book",
        "schedule",
        "get quote",
        "request quote",
        "request estimate",
        "contact us",
        "call now",
        "free consultation",
    ]
    locality_patterns = ["serving", "located in", "local", "nearby", "montreal", "quebec", "toronto", "vancouver"]

    trust_hits = [p for p in trust_patterns if p in text]
    cta_hits = [p for p in conversion_patterns if p in text]
    locality_hits = [p for p in locality_patterns if p in text]

    service_pages = _find_anchor_patterns(
        soup,
        ["/services", "/service", "/practice", "/areas", "/solutions", "/pricing", "/book", "/contact"],
    )
    has_contact_schema = bool(brand_entity and brand_entity.has_contact_info)
    has_local_schema = bool(brand_entity and brand_entity.has_geo_schema)
    has_locality_schema = has_local_schema or bool(schema and schema.has_organization and schema.raw_schemas)
    testimonial_count = _regex_count(text, r"\breviews?\b|\btestimonials?\b|\brating\b")

    if trust_hits or testimonial_count > 0 or has_contact_schema:
        result.signals.append(
            VerticalSignal(
                key="trust_proof",
                label="Trust proof",
                detected=True,
                evidence=(trust_hits[:2] or [])
                + ([f"{testimonial_count} review signals"] if testimonial_count else []),
            )
        )
        result.trust_signals = min(
            5, len(trust_hits) + (1 if testimonial_count > 0 else 0) + (1 if has_contact_schema else 0)
        )
    else:
        result.signals.append(VerticalSignal(key="trust_proof", label="Trust proof", detected=False, evidence=[]))

    if cta_hits or service_pages:
        result.signals.append(
            VerticalSignal(
                key="conversion_path",
                label="Conversion path",
                detected=True,
                evidence=(cta_hits[:2] or []) + service_pages[:2],
            )
        )
        result.conversion_signals = min(5, len(cta_hits) + min(2, len(service_pages)))
    else:
        result.signals.append(
            VerticalSignal(key="conversion_path", label="Conversion path", detected=False, evidence=[])
        )

    if locality_hits or has_locality_schema:
        result.signals.append(
            VerticalSignal(
                key="local_entity",
                label="Local entity clarity",
                detected=True,
                evidence=locality_hits[:2] + (["schema address/areaServed"] if has_locality_schema else []),
            )
        )
        result.locality_signals = min(5, len(locality_hits) + (2 if has_locality_schema else 0))
    else:
        result.signals.append(
            VerticalSignal(key="local_entity", label="Local entity clarity", detected=False, evidence=[])
        )

    vertical_keywords = _vertical_keywords(effective_vertical)
    vertical_hits = [k for k in vertical_keywords if _has_pattern(text, [k])]
    if effective_vertical not in {"generic", "auto"}:
        result.signals.append(
            VerticalSignal(
                key="vertical_language",
                label=f"{effective_vertical} relevance",
                detected=bool(vertical_hits),
                evidence=vertical_hits[:3],
            )
        )
        result.vertical_signals = min(5, len(vertical_hits))

    if effective_locale == "en-fr":
        bilingual_signals = 0
        if _has_pattern(text, ["francais", "french", "english", "anglais"]):
            bilingual_signals += 1
        if brand_entity and brand_entity.hreflang_count >= 2:
            bilingual_signals += 1
        result.bilingual_ready = bilingual_signals >= 1
        result.signals.append(
            VerticalSignal(
                key="bilingual_readiness",
                label="Bilingual readiness",
                detected=result.bilingual_ready,
                evidence=["hreflang multi-language"] if brand_entity and brand_entity.hreflang_count >= 2 else [],
            )
        )

    score = 0
    score += min(30, result.trust_signals * 6)
    score += min(30, result.conversion_signals * 6)
    score += min(20, result.locality_signals * 4)
    score += min(20, result.vertical_signals * 4)
    if effective_locale == "en-fr" and result.bilingual_ready:
        score = min(100, score + 5)
    result.business_readiness_score = min(100, score)

    if result.trust_signals < 2:
        result.priority_actions.append("Add proof assets: certifications, reviews, guarantees, and team credibility.")
    if result.conversion_signals < 2:
        result.priority_actions.append("Add conversion CTAs: quote, consultation, or booking flow on key pages.")
    if result.locality_signals < 2:
        result.priority_actions.append(
            "Strengthen local entity signals with areaServed/address schema and locality copy."
        )
    if effective_vertical != "generic" and result.vertical_signals < 2:
        result.priority_actions.append(
            f"Add dedicated {effective_vertical} service language, proof points, and entity-specific FAQ blocks."
        )
    if effective_locale == "en-fr" and not result.bilingual_ready:
        result.priority_actions.append("Add bilingual navigation, hreflang, and mirrored trust/service pages.")

    # Fallback recommendation so output never feels empty for buyers.
    if not result.priority_actions:
        result.priority_actions.append(
            "Maintain signal consistency and monitor monthly for trust/citation regressions."
        )

    # Use existing metadata to improve deterministic behavior.
    if meta and not meta.has_title:
        result.priority_actions.append("Add a clear title tag aligned with the buyer intent of your primary service.")
    if content and content.word_count < 300:
        result.priority_actions.append("Expand core service pages with evidence-backed, citation-ready detail.")

    return result
