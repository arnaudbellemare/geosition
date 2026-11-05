"""Dataclasses for GEOSITION results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class VerticalSignal:
    """Single buyer-facing readiness signal for a vertical profile."""

    key: str = ""
    label: str = ""
    detected: bool = False
    evidence: list[str] = field(default_factory=list)


@dataclass
class VerticalAuditResult:
    """Business-facing readiness layer for local service verticals."""

    checked: bool = False
    vertical: str = "generic"
    detected_vertical: str = "generic"
    detection_confidence: float = 0.0
    market_locale: str = "en"
    trust_signals: int = 0
    conversion_signals: int = 0
    locality_signals: int = 0
    vertical_signals: int = 0
    bilingual_ready: bool = False
    business_readiness_score: int = 0
    signals: list[VerticalSignal] = field(default_factory=list)
    priority_actions: list[str] = field(default_factory=list)


# ─── Action Intelligence ──────────────────────────────────────────────────────


@dataclass
class NextAction:
    """Prioritized execution item generated from score gaps."""

    key: str = ""
    title: str = ""
    why: str = ""
    impact: str = "medium"  # low | medium | high
    effort: str = "medium"  # low | medium | high
    priority: str = "P2"  # P1 | P2 | P3
    expected_score_gain: int = 0
    evidence_level: str = "product_heuristic"
    evidence_note: str = "Score impact reflects GEOSITION's rubric, not a predicted change in citations."


# ─── Marketing audit (v4.12) ─────────────────────────────────────────────────


@dataclass
class CopywritingResult:
    """Copywriting quality analysis — headline, value prop, CTAs, benefit language."""

    checked: bool = False
    # Headline (H1)
    h1_text: str = ""
    h1_is_outcome_focused: bool = False  # mentions what customer gets/achieves
    h1_is_feature_focused: bool = False  # talks about what we do/offer
    h1_is_generic: bool = False  # vague/empty ("Welcome", "Home", etc.)
    # Value proposition
    has_value_prop_in_hero: bool = False  # clear "you get X" framing above fold
    value_prop_snippet: str = ""
    # CTA copy quality
    weak_ctas: list[str] = field(default_factory=list)  # "Submit", "Learn More", etc.
    strong_ctas: list[str] = field(default_factory=list)  # "Start Free Trial", etc.
    # Benefit vs. feature language
    benefit_phrases: int = 0  # "you get", "your", outcome language
    feature_phrases: int = 0  # "we offer", "our product", "we provide"
    benefit_ratio: float = 0.0  # benefit / (benefit + feature), 0.0–1.0
    # H2 heading quality
    h2_count: int = 0
    h2_keyword_quality: str = ""  # "good" | "generic" | "ai-focused"
    h2_service_count: int = 0  # H2s containing real service/location keywords
    h2_samples: list[str] = field(default_factory=list)  # first 5 H2 texts
    # Issues and suggestions
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    copy_score: int = 0  # 0-100


@dataclass
class ImageAuditResult:
    """On-page image SEO audit."""

    checked: bool = False
    total_images: int = 0
    images_missing_alt: int = 0  # <img> with no alt attribute
    images_empty_alt: int = 0  # alt="" (decorative — ok if intentional)
    images_keyword_alt: int = 0  # alt text contains service/location keyword
    images_keyword_filename: int = 0  # filename contains service/location keyword
    images_webp: int = 0  # .webp format
    images_missing_dimensions: int = 0  # missing width or height attribute
    images_missing_lazy: int = 0  # missing loading="lazy"
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    image_score: int = 0  # 0-100


@dataclass
class ContentStrategyResult:
    """Content strategy signals — blog, FAQ, comparisons, pricing, lead capture."""

    checked: bool = False
    # Blog / content hub
    has_blog: bool = False
    blog_url: str = ""
    estimated_article_count: int = 0  # links to /blog/* found on homepage
    # FAQ
    has_faq_section: bool = False
    has_faq_schema: bool = False
    # Comparison / alternatives pages
    has_comparison_pages: bool = False
    comparison_urls: list[str] = field(default_factory=list)  # /vs/, /alternatives/
    # Pricing transparency
    has_pricing_page: bool = False
    has_pricing_md: bool = False  # /pricing.md for AI agents
    # Lead capture
    has_email_capture: bool = False  # newsletter, lead magnet, email input
    has_lead_magnet: bool = False  # free guide, template, tool mentioned
    # Case studies / proof
    has_case_studies: bool = False
    has_numbers_proof: bool = False  # "10,000 customers", "3× faster" etc.
    # Internal link depth
    internal_link_count: int = 0  # total same-domain links on page
    # LocalBusiness schema completeness
    has_local_business_schema: bool = False
    local_business_has_address: bool = False
    local_business_has_phone: bool = False
    local_business_has_hours: bool = False
    local_business_has_geo: bool = False
    # Industry trust / backlink signals
    has_industry_memberships: bool = False  # RGCQ / CORPIQ / APCHQ / BBB mentions
    industry_membership_names: list[str] = field(default_factory=list)
    # Issues and suggestions
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    content_score: int = 0  # 0-100


@dataclass
class MarketingAction:
    """Single prioritised marketing action."""

    key: str = ""
    title: str = ""
    why: str = ""
    skill: str = ""  # which marketingskill this maps to
    impact: str = "medium"  # low | medium | high
    effort: str = "medium"
    priority: str = "P2"  # P1 | P2 | P3
    estimated_lift: str = ""  # e.g. "+15-25% conversion"


@dataclass
class AIPresenceResult:
    """AI search presence checks — from the ai-seo, schema-markup, and programmatic-seo skills."""

    checked: bool = False
    # robots.txt — AI bot access (ai-seo skill: immediate visibility killer)
    robots_txt_fetched: bool = False
    blocked_ai_bots: list[str] = field(default_factory=list)  # bots with Disallow: /
    # Content extractability (ai-seo skill: Pillar 1 — Structure)
    has_definition_block: bool = False  # self-contained definition in first 300 words
    definition_snippet: str = ""
    # Statistics attribution (ai-seo skill: attributed stats > naked stats)
    has_attributed_stats: bool = False  # stats with "According to X" / "(Source, Year)"
    unattributed_stat_count: int = 0  # bare % numbers without a source
    # Technical presence (ai-seo skill: Pillar 3 — Discoverable)
    js_heavy: bool = False  # high script:text ratio → likely JS-rendered SPA
    # Programmatic SEO — location pages (programmatic-seo skill: Locations playbook)
    has_location_pages: bool = False
    location_page_count: int = 0
    # Entity authority (schema-markup skill: Organization sameAs + author attribution)
    has_org_sameas: bool = False  # Organization schema with sameAs links
    has_author_schema: bool = False  # Person schema with credentials / sameAs
    # Issues and suggestions
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    presence_score: int = 0  # 0-100


@dataclass
class MediaAsset:
    """Single video or audio asset found on the page."""

    url: str = ""
    media_type: str = ""  # "video" | "audio"
    format: str = ""  # "mp4" | "webm" | "mp3" | "ogg" | "unknown"
    size_bytes: int = -1  # -1 = not checked
    has_lazy_load: bool = False
    has_poster: bool = False  # video: poster= attribute
    autoplay_unmuted: bool = False  # video: autoplay without muted
    has_dimensions: bool = False  # width + height attributes present
    has_responsive_sources: bool = False  # <source media="(max-width:…)"> variants
    has_webm_source: bool = False  # WebM <source> present as fallback


@dataclass
class MediaResult:
    """Media optimization audit — video/audio assets on the page."""

    checked: bool = False
    video_count: int = 0
    audio_count: int = 0
    assets: list[MediaAsset] = field(default_factory=list)
    large_videos: int = 0  # videos > 5 MB
    large_audios: int = 0  # audio > 2 MB
    missing_lazy: int = 0  # media without lazy-load
    missing_poster: int = 0  # videos without poster frame
    autoplay_unmuted: int = 0  # autoplay without muted (bad UX + layout shift)
    non_mp4_videos: int = 0  # videos not served as mp4/webm
    missing_responsive_sources: int = 0  # videos without mobile/desktop <source media=...>
    no_webm_fallback: int = 0  # MP4-only videos with no WebM <source>
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    media_score: int = 100  # starts at 100, deductions per issue


@dataclass
class SerpCompetitor:
    """Single competitor page from SERP analysis."""

    rank: int = 0
    url: str = ""
    title: str = ""
    description: str = ""
    word_count: int = 0
    h1: str = ""
    h2_count: int = 0
    h2_texts: list[str] = field(default_factory=list)  # actual H2 text for keyword gap analysis
    has_location_pages: bool = False  # competitor has /location/ or /cities/ pattern
    has_schema: bool = False
    schema_types: list[str] = field(default_factory=list)
    has_faq: bool = False
    has_video: bool = False
    has_images: bool = False
    internal_links: int = 0
    content_snippet: str = ""  # first 200 chars of body text


@dataclass
class SerpResult:
    """SERP keyword competitor analysis."""

    checked: bool = False
    keyword: str = ""
    search_engine: str = "duckduckgo"
    competitors: list[SerpCompetitor] = field(default_factory=list)
    # Gap analysis vs audited site
    avg_competitor_word_count: int = 0
    your_word_count: int = 0
    word_count_gap: int = 0  # how many words behind top competitors
    avg_competitor_h2s: float = 0.0
    competitors_with_schema: int = 0
    competitors_with_faq: int = 0
    competitors_with_video: int = 0
    # Suggested location pages (service × city combos)
    location_page_suggestions: list[str] = field(default_factory=list)
    # Keyword gap vs first-page competitors
    keyword_gaps: list[str] = field(default_factory=list)  # topics in competitor H2s not on your page
    page1_requirements: list[str] = field(default_factory=list)  # actionable "to rank page 1 you need X" list
    competitors_with_location_pages: int = 0
    crowdedness_score: int = 0
    crowdedness_label: str = "unknown"
    serp_features: list[str] = field(default_factory=list)
    # Issues and action items
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)


@dataclass
class MarketingResult:
    """Combined marketing audit result — copywriting + content strategy + AI presence."""

    checked: bool = False
    marketing_score: int = 0  # 0-100 composite
    copywriting: CopywritingResult = field(default_factory=CopywritingResult)
    content_strategy: ContentStrategyResult = field(default_factory=ContentStrategyResult)
    ai_presence: AIPresenceResult = field(default_factory=AIPresenceResult)
    image_audit: ImageAuditResult = field(default_factory=ImageAuditResult)
    media: MediaResult = field(default_factory=MediaResult)
    serp: SerpResult = field(default_factory=SerpResult)
    priority_actions: list[MarketingAction] = field(default_factory=list)


# ─── Performance audit (v4.12) ───────────────────────────────────────────────


@dataclass
class PerfIssue:
    """Single performance / load-speed issue."""

    check: str = ""  # e.g. "img_missing_dimensions"
    severity: str = "warning"  # warning | error
    element: str = ""  # short HTML snippet or URL fragment
    fix: str = ""  # one-line remediation hint


@dataclass
class PerfResult:
    """Core Web Vitals / performance audit result. Informational — does not affect GEO score."""

    checked: bool = False
    images_missing_dimensions: int = 0  # <img> without width + height
    images_missing_lazy: int = 0  # <img> without loading="lazy"
    render_blocking_scripts: int = 0  # <script> without async/defer
    render_blocking_styles: int = 0  # <link rel="stylesheet"> in <head>
    missing_font_display_swap: bool = False  # @font-face without font-display:swap
    issues: list[PerfIssue] = field(default_factory=list)
    perf_score: int = 0  # 0-100 (higher = fewer issues)


# ─── Broken link / 404 audit (v4.12) ─────────────────────────────────────────


@dataclass
class LinkIssue:
    """Single broken or redirected internal link."""

    url: str = ""
    status: int = 0  # HTTP status code (404, 500, 0 = timeout)
    anchor_text: str = ""
    source_page: str = ""  # which page contained this link


@dataclass
class LinksResult:
    """Broken link + 404 audit result. Informational — does not affect GEO score."""

    checked: bool = False
    total_internal_links: int = 0
    broken_links: list[LinkIssue] = field(default_factory=list)
    redirect_chains: list[LinkIssue] = field(default_factory=list)  # 301/302 chains
    broken_count: int = 0
    vercel_redirects_block: str = ""  # Ready-to-paste JSON for vercel.json
    # External link checking (opt-in via --check-external)
    external_broken_links: list[LinkIssue] = field(default_factory=list)
    external_broken_count: int = 0
    # Canonical-redirect conflict: canonical points to a URL that then redirects
    canonical_redirect_conflict: bool = False
    canonical_url: str = ""  # value of <link rel="canonical">
    canonical_redirects_to: str = ""  # final URL after redirect (if conflict)
    # Breadcrumb detection
    has_breadcrumbs: bool = False
    breadcrumb_type: str = ""  # "schema", "nav", "aria" or ""


# ─── Conversion readiness audit (v4.12) ──────────────────────────────────────


@dataclass
class ConversionSignal:
    """Single conversion readiness signal."""

    key: str = ""
    label: str = ""
    detected: bool = False
    evidence: str = ""  # snippet or selector that triggered detection
    fix: str = ""  # actionable one-liner if not detected


@dataclass
class ConversionResult:
    """Conversion readiness checklist. Informational — does not affect GEO score."""

    checked: bool = False
    cta_above_fold: bool = False  # primary CTA visible without scrolling
    has_contact_form: bool = False  # <form> with email/tel input
    has_phone_number: bool = False  # tel: link or phone-like text
    has_testimonials: bool = False  # review/testimonial section
    has_aggregate_rating: bool = False  # AggregateRating schema
    has_trust_badges: bool = False  # SSL, guarantee, award mentions
    cta_count: int = 0  # total CTA buttons/links
    signals: list[ConversionSignal] = field(default_factory=list)
    conversion_score: int = 0  # 0-100
    priority_fixes: list[str] = field(default_factory=list)  # top 3 copy suggestions
    # form-cro extensions (v4.13)
    max_form_fields: int = 0  # highest field count across all forms
    has_strong_submit_copy: bool = False  # submit button uses action-oriented copy
    has_privacy_near_form: bool = False  # privacy/no-spam text near form
    has_social_auth: bool = False  # Google/Apple/Microsoft OAuth buttons present
    has_mobile_viewport: bool = False  # <meta name="viewport"> present


# ─── Analytics / tracking audit (v4.13) ─────────────────────────────────────


@dataclass
class TrackingSignal:
    """Single analytics/tracking tool detection."""

    key: str = ""
    label: str = ""
    detected: bool = False
    evidence: str = ""  # script src snippet or trigger
    fix: str = ""


@dataclass
class TrackingResult:
    """Analytics and conversion tracking audit. Informational — does not affect GEO score."""

    checked: bool = False
    has_analytics: bool = False  # any analytics tool detected
    has_conversion_tracking: bool = False  # conversion pixel or goal tracking
    has_ga4: bool = False  # Google Analytics 4
    has_gtm: bool = False  # Google Tag Manager
    has_meta_pixel: bool = False  # Meta/Facebook Pixel
    has_other_analytics: bool = False  # Plausible, Fathom, Matomo, Segment, etc.
    has_heatmap: bool = False  # Hotjar, Microsoft Clarity, etc.
    signals: list[TrackingSignal] = field(default_factory=list)
    tracking_score: int = 0  # 0-100
    priority_fixes: list[str] = field(default_factory=list)


# ─── Indexability conflict audit ─────────────────────────────────────────────


@dataclass
class IndexabilityResult:
    """Three-layer indexability conflict check. Informational — generates critical recommendations."""

    checked: bool = False
    # Layer 1: robots.txt (already in RobotsResult — cross-reference only)
    # Layer 2: <meta name="robots"> page-level directive
    meta_robots_content: str = ""  # raw content string e.g. "noindex, nosnippet"
    meta_noindex: bool = False
    meta_nosnippet: bool = False  # blocks AI Overviews and AI Mode (Google-documented)
    meta_max_snippet: int = -1  # -1 = unrestricted; 0 = no snippet
    # Layer 3: X-Robots-Tag response header
    x_robots_content: str = ""
    x_robots_noindex: bool = False
    x_robots_nosnippet: bool = False
    x_robots_max_snippet: int = -1
    # Conflict detection
    has_nosnippet: bool = False  # either meta or header
    has_noindex: bool = False  # either meta or header
    # robots.txt allows but page-level says noindex — silent suppression
    robots_meta_conflict: bool = False
    conflict_detail: str = ""


# ─── Freshness audit ──────────────────────────────────────────────────────────


@dataclass
class FreshnessResult:
    """Freshness signals audit. Informational — supplements signals.has_freshness."""

    checked: bool = False
    # Visible date in HTML body (human-readable, near top of page)
    visible_date_text: str = ""  # e.g. "January 15, 2025"
    visible_date_near_top: bool = False  # within first 500 words
    # HTTP Last-Modified header
    last_modified_header: str = ""
    has_last_modified: bool = False
    # Schema dateModified (already in SchemaResult — cross-reference for agreement)
    schema_date: str = ""
    # Agreement: schema date and visible date agree (within 7 days)
    date_agreement: bool = False
    date_conflict: bool = False  # schema and visible dates contradict each other
    conflict_detail: str = ""
    # datetime attributes on <time> elements
    has_time_element: bool = False
    time_datetime: str = ""


# ─── IndexNow ────────────────────────────────────────────────────────────────


@dataclass
class IndexNowResult:
    """IndexNow protocol readiness check."""

    checked: bool = False
    is_configured: bool = False
    has_meta_tag: bool = False  # <meta name="indexnow-key">
    has_link_element: bool = False  # <link rel="indexnow">
    key_value: str = ""  # raw key string found
    key_looks_valid: bool = False  # matches 32–128 hex chars
    key_url: str = ""  # expected key file URL
    recommendations: list[str] = field(default_factory=list)


# ─── AEO (Answer Engine Optimization) ────────────────────────────────────────


@dataclass
class AEOResult:
    """Answer Engine Optimization audit: Featured Snippets, PAA, Knowledge Panel."""

    checked: bool = False

    # Featured Snippet
    has_paragraph_snippet_candidate: bool = False
    snippet_candidate_word_count: int = 0
    has_list_snippet_candidate: bool = False
    list_snippet_item_count: int = 0
    has_table_snippet_candidate: bool = False
    featured_snippet_score: int = 0  # 0–3

    # People Also Ask
    question_heading_count: int = 0
    has_question_headings: bool = False
    faq_schema_item_count: int = 0
    has_faq_schema: bool = False
    paa_question_types_covered: list[str] = field(default_factory=list)
    paa_score: int = 0  # 0–3

    # Knowledge Panel
    kg_same_as_count: int = 0
    kg_authoritative_same_as: int = 0
    has_wikidata_link: bool = False
    has_wikipedia_link: bool = False
    has_org_schema: bool = False
    has_nap_consistency: bool = False
    has_founder_entity: bool = False
    knowledge_panel_score: int = 0  # 0–4

    recommendations: list[str] = field(default_factory=list)


# ─── SXO (Search Experience Optimization) ────────────────────────────────────


@dataclass
class SXOResult:
    """Search Experience Optimization: intent-content alignment audit."""

    checked: bool = False
    page_url: str = ""

    # Detected signals
    url_intent_signals: list[str] = field(default_factory=list)  # e.g. ["transactional"]
    content_intent_signals: list[str] = field(default_factory=list)  # e.g. ["informational"]
    cta_count: int = 0
    word_count: int = 0

    # Alignment result
    intent_aligned: bool = True
    matched_intent: str = ""  # dominant intent when aligned
    mismatch_type: str = ""  # e.g. "transactional_url_informational_content"
    mismatch_detail: str = ""  # human-readable explanation

    # Dimension checks
    informational_depth_ok: bool = True

    sxo_score: int = 0  # 0–3
    recommendations: list[str] = field(default_factory=list)


# ─── Plugin check summary ────────────────────────────────────────────────────


@dataclass
class PluginCheckSummary:
    """Typed summary of a single plugin check result stored in AuditResult.extra_checks."""

    score: int = 0
    max_score: int = 0
    passed: bool = False
    message: str = ""
    details: dict[str, object] = field(default_factory=dict)


__all__ = [
    "VerticalSignal",
    "VerticalAuditResult",
    "NextAction",
    "CopywritingResult",
    "ImageAuditResult",
    "ContentStrategyResult",
    "MarketingAction",
    "AIPresenceResult",
    "MediaAsset",
    "MediaResult",
    "SerpCompetitor",
    "SerpResult",
    "MarketingResult",
    "PerfIssue",
    "PerfResult",
    "LinkIssue",
    "LinksResult",
    "ConversionSignal",
    "ConversionResult",
    "TrackingSignal",
    "TrackingResult",
    "IndexabilityResult",
    "FreshnessResult",
    "IndexNowResult",
    "AEOResult",
    "SXOResult",
    "PluginCheckSummary",
]
