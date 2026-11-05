"""Dataclasses for GEOSITION results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CachedResponse:
    """Synthetic HTTP response built from the on-disk cache (fix #83).

    Used by run_full_audit() when use_cache=True and the response
    is already in the FileCache, avoiding a new HTTP request.
    """

    status_code: int
    text: str
    content: bytes
    headers: dict[str, str] = field(default_factory=dict)


# ─── Robots.txt ──────────────────────────────────────────────────────────────


@dataclass
class RobotsResult:
    found: bool = False
    bots_allowed: list[str] = field(default_factory=list)
    bots_missing: list[str] = field(default_factory=list)
    bots_blocked: list[str] = field(default_factory=list)
    # Partially blocked bots (Disallow: / + specific Allows — #106)
    bots_partial: list[str] = field(default_factory=list)
    citation_bots_ok: bool = False
    # True if citation bots are explicitly allowed (not just via wildcard — #111)
    citation_bots_explicit: bool = False


# ─── llms.txt ────────────────────────────────────────────────────────────────


@dataclass
class LlmsTxtResult:
    found: bool = False
    has_h1: bool = False
    has_description: bool = False  # alias for has_blockquote, kept for API backward compatibility
    has_sections: bool = False
    has_links: bool = False
    word_count: int = 0
    has_full: bool = False  # /llms-full.txt present
    # #247: llms.txt Policy Intelligence — content analysis
    sections_count: int = 0
    links_count: int = 0
    # #39: llms.txt v2 validation — full spec conformance
    has_blockquote: bool = False  # > blockquote description present
    has_optional_section: bool = False  # ## Optional section present
    companion_files_hint: bool = False  # link to companion .md files
    validation_warnings: list[str] = field(default_factory=list)  # conformance warnings
    # Coverage quality: are important pages (about, services, pricing…) linked?
    coverage_score: int = 0  # 0-100
    important_pages_linked: list[str] = field(default_factory=list)
    important_pages_missing: list[str] = field(default_factory=list)


# ─── Schema JSON-LD ──────────────────────────────────────────────────────────


@dataclass
class SchemaResult:
    found_types: list[str] = field(default_factory=list)
    has_website: bool = False
    has_webapp: bool = False
    has_faq: bool = False
    has_article: bool = False
    has_organization: bool = False
    has_howto: bool = False
    has_person: bool = False
    has_product: bool = False
    raw_schemas: list[dict] = field(default_factory=list)
    any_schema_found: bool = False  # True if ANY valid JSON-LD was found
    has_sameas: bool = False  # sameAs property found
    sameas_urls: list[str] = field(default_factory=list)
    has_date_modified: bool = False  # dateModified in any schema
    # Schema richness (Growth Marshal Feb 2026): schema con 5+ attributi rilevanti
    schema_richness_score: int = 0
    avg_attributes_per_schema: float = 0.0
    # #232: E-commerce GEO Profile — analisi ricchezza Product schema
    ecommerce_signals: dict = field(default_factory=dict)
    # Fix #399: conteggio errori di parsing JSON-LD
    json_parse_errors: int = 0
    # WebApplication on a non-app site triggers Rich Result validation errors
    webapp_invalid: bool = False  # True when WebApplication + no tool/calculator signals


# ─── Meta tags ───────────────────────────────────────────────────────────────


@dataclass
class MetaResult:
    has_title: bool = False
    has_description: bool = False
    has_canonical: bool = False
    has_og_title: bool = False
    has_og_description: bool = False
    has_og_image: bool = False
    has_twitter_card: bool = False
    has_twitter_title: bool = False
    title_text: str = ""
    description_text: str = ""
    description_length: int = 0
    title_length: int = 0
    canonical_url: str = ""


# ─── Content quality ─────────────────────────────────────────────────────────


@dataclass
class ContentResult:
    has_h1: bool = False
    h1_count: int = 0
    heading_count: int = 0
    has_numbers: bool = False
    has_links: bool = False
    word_count: int = 0
    h1_text: str = ""
    numbers_count: int = 0
    external_links_count: int = 0
    has_heading_hierarchy: bool = False  # H2+H3 present in correct hierarchy
    has_lists_or_tables: bool = False  # <ul>/<ol>/<table> found
    has_front_loading: bool = False  # key info in the first 30%
    # Stable anchors: headings with id= for section-level citations
    headings_with_id: int = 0
    heading_id_ratio: float = 0.0  # fraction of h2/h3 with id attribute
    # Definition-first: opening paragraph answers the topic in 1-3 sentences
    has_definition_first: bool = False
    # Text-to-HTML ratio: visible text bytes / raw HTML bytes (0.0–1.0)
    text_html_ratio: float = 0.0
    # External links with rel="nofollow" on the <a> tag
    external_nofollow_count: int = 0
    all_external_nofollow: bool = False  # True when every outgoing external link is nofollowed


# ─── Signals tecnici (v4.0) ──────────────────────────────────────────────────


@dataclass
class SignalsResult:
    """Technical signals for AI discoverability."""

    has_lang: bool = False
    lang_value: str = ""
    has_rss: bool = False
    rss_url: str = ""
    has_freshness: bool = False
    freshness_date: str = ""


# ─── Brand & Entity (v4.3) ────────────────────────────────────────────────────


@dataclass
class BrandEntityResult:
    """Brand and entity identity signals for AI perception."""

    # Entity Coherence (3 points)
    brand_name_consistent: bool = False
    names_found: list[str] = field(default_factory=list)
    schema_desc_matches_meta: bool = False

    # Knowledge Graph Readiness (3 points)
    kg_pillar_count: int = 0
    kg_pillar_urls: list[str] = field(default_factory=list)
    has_wikipedia: bool = False
    has_wikidata: bool = False
    has_linkedin: bool = False
    has_crunchbase: bool = False

    # About/Contact Signals (2 points)
    has_about_link: bool = False
    has_contact_info: bool = False  # Organization with address/telephone/email or Person with jobTitle

    # Geographic Identity (1 point)
    has_geo_schema: bool = False  # address/areaServed/LocalBusiness
    has_hreflang: bool = False
    hreflang_count: int = 0

    # Topic Authority (1 point)
    faq_depth: int = 0  # number of FAQs in the FAQPage schema
    has_recent_articles: bool = False  # Article/BlogPosting with dateModified


# ─── Citability (Princeton GEO Methods) ─────────────────────────────────────

__all__ = [
    "CachedResponse",
    "RobotsResult",
    "LlmsTxtResult",
    "SchemaResult",
    "MetaResult",
    "ContentResult",
    "SignalsResult",
    "BrandEntityResult",
]
