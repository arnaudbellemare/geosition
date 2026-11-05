"""Dataclasses for GEOSITION results."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from geo_optimizer.models.results.analytics import (
    BrandSentimentResult,
    ContentDecayResult,
    ContextWindowResult,
    InstructionReadinessResult,
    PlatformCitationResult,
)
from geo_optimizer.models.results.citability import (
    AiDiscoveryResult,
    CdnAiCrawlerResult,
    CitabilityResult,
    JsRenderingResult,
    MethodScore,
    WebMcpResult,
)
from geo_optimizer.models.results.core import (
    BrandEntityResult,
    ContentResult,
    LlmsTxtResult,
    MetaResult,
    RobotsResult,
    SchemaResult,
    SignalsResult,
)
from geo_optimizer.models.results.marketing import (
    AEOResult,
    ConversionResult,
    FreshnessResult,
    IndexabilityResult,
    IndexNowResult,
    LinksResult,
    NextAction,
    PerfResult,
    PluginCheckSummary,
    SXOResult,
    TrackingResult,
    VerticalAuditResult,
)
from geo_optimizer.models.results.rag import EmbeddingProximityResult, RagChunkResult
from geo_optimizer.models.results.trust import (
    NegativeSignalsResult,
    PromptInjectionResult,
    TrustStackResult,
)


@dataclass
class AuditResult:
    url: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    score: int = 0
    band: str = "critical"
    robots: RobotsResult = field(default_factory=RobotsResult)
    llms: LlmsTxtResult = field(default_factory=LlmsTxtResult)
    schema: SchemaResult = field(default_factory=SchemaResult)
    meta: MetaResult = field(default_factory=MetaResult)
    content: ContentResult = field(default_factory=ContentResult)
    recommendations: list[str] = field(default_factory=list)
    http_status: int = 0
    page_size: int = 0
    # Citability: score 0-100 based on the 9 Princeton KDD 2024 methods
    citability: CitabilityResult = field(default_factory=CitabilityResult)
    # Fix #104: CheckRegistry plugin results (do not affect the base score)
    extra_checks: dict[str, PluginCheckSummary] = field(default_factory=dict)
    # v4.0: technical signals (lang, RSS, freshness)
    signals: SignalsResult = field(default_factory=SignalsResult)
    # v4.1: AI discovery endpoints (geo-checklist.dev)
    ai_discovery: AiDiscoveryResult = field(default_factory=AiDiscoveryResult)
    # v4.0: score breakdown per category
    score_breakdown: dict[str, int] = field(default_factory=dict)
    # v4.0: connection error message (None = success)
    error: str | None = None
    # v4.2: CDN AI Crawler check (#225)
    cdn_check: CdnAiCrawlerResult = field(default_factory=CdnAiCrawlerResult)
    # v4.2: JS Rendering check (#226)
    js_rendering: JsRenderingResult = field(default_factory=JsRenderingResult)
    # v4.3: Brand & Entity signals
    brand_entity: BrandEntityResult = field(default_factory=BrandEntityResult)
    # v4.3: WebMCP Readiness check (#233)
    webmcp: WebMcpResult = field(default_factory=WebMcpResult)
    # v4.3: Negative Signals detection
    negative_signals: NegativeSignalsResult = field(default_factory=NegativeSignalsResult)
    # v4.4: Prompt Injection Pattern Detection (#276)
    prompt_injection: PromptInjectionResult = field(default_factory=PromptInjectionResult)
    # v4.5: Trust Stack Score — informational, does not affect GEO score (#273)
    trust_stack: TrustStackResult = field(default_factory=TrustStackResult)
    # v4.7: audit wall-clock duration in milliseconds (#290)
    audit_duration_ms: int | None = None
    # v4.7: RAG chunk readiness (#353)
    rag_chunk: RagChunkResult = field(default_factory=RagChunkResult)
    # v4.7: Embedding proximity score (#354)
    embedding_proximity: EmbeddingProximityResult = field(default_factory=EmbeddingProximityResult)
    # v4.7: Content decay prediction (#383)
    content_decay: ContentDecayResult = field(default_factory=ContentDecayResult)
    # v4.7: Multi-platform citation profile (#228)
    platform_citation: PlatformCitationResult = field(default_factory=PlatformCitationResult)
    # v4.7: Brand sentiment analysis (#378) — opt-in, requires LLM API key
    brand_sentiment: BrandSentimentResult = field(default_factory=BrandSentimentResult)
    # v4.9: Context window optimization (#370)
    context_window: ContextWindowResult = field(default_factory=ContextWindowResult)
    # v4.9: Instruction following readiness (#371)
    instruction_readiness: InstructionReadinessResult = field(default_factory=InstructionReadinessResult)
    # v4.10: buyer-facing vertical profile for local service businesses
    vertical_profile: VerticalAuditResult = field(default_factory=VerticalAuditResult)
    # v4.11: prioritized execution roadmap
    next_actions: list[NextAction] = field(default_factory=list)
    # v4.12: performance / Core Web Vitals signals — informational
    perf: PerfResult = field(default_factory=PerfResult)
    # v4.12: broken link + 404 detection — informational
    links: LinksResult = field(default_factory=LinksResult)
    # v4.12: conversion readiness checklist — informational
    conversion: ConversionResult = field(default_factory=ConversionResult)
    # v4.13: analytics / tracking presence — informational
    tracking: TrackingResult = field(default_factory=TrackingResult)
    # v4.14: indexability conflict detection — informational
    indexability: IndexabilityResult = field(default_factory=IndexabilityResult)
    # v4.14: freshness signals — informational
    freshness: FreshnessResult = field(default_factory=FreshnessResult)
    # v4.10: IndexNow protocol readiness
    indexnow: IndexNowResult = field(default_factory=IndexNowResult)
    # v4.10: Answer Engine Optimization (Featured Snippet / PAA / Knowledge Panel)
    aeo: AEOResult = field(default_factory=AEOResult)
    # v4.10: Search Experience Optimization (intent-content alignment)
    sxo: SXOResult = field(default_factory=SXOResult)
    recommendation_evidence: list[dict[str, str]] = field(default_factory=list)
    commerce: dict[str, object] = field(default_factory=dict)


# ─── Batch audit ─────────────────────────────────────────────────────────────


@dataclass
class BatchAuditPageResult:
    """Sintesi di un audit pagina all'interno di un audit batch da sitemap."""

    url: str
    score: int = 0
    band: str = "critical"
    http_status: int = 0
    error: str | None = None
    score_breakdown: dict[str, int] = field(default_factory=dict)
    recommendations_count: int = 0
    recommendations: list[str] = field(default_factory=list)


@dataclass
class BatchAuditResult:
    """Risultato aggregato di un audit batch eseguito su una sitemap."""

    sitemap_url: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    discovered_urls: int = 0
    audited_urls: int = 0
    successful_urls: int = 0
    failed_urls: int = 0
    average_score: float = 0.0
    average_band: str = "critical"
    band_counts: dict[str, int] = field(default_factory=dict)
    average_score_breakdown: dict[str, float] = field(default_factory=dict)
    pages: list[BatchAuditPageResult] = field(default_factory=list)
    top_pages: list[BatchAuditPageResult] = field(default_factory=list)
    worst_pages: list[BatchAuditPageResult] = field(default_factory=list)


# ─── Audit diff ──────────────────────────────────────────────────────────────


@dataclass
class CategoryDelta:
    """Delta di punteggio per una singola categoria GEO tra due audit."""

    category: str
    label: str
    before_score: int = 0
    after_score: int = 0
    delta: int = 0
    max_score: int = 0


@dataclass
class AuditDiffResult:
    """Confronto A/B tra due audit GEO della stessa o di due diverse pagine."""

    before_url: str
    after_url: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    before_score: int = 0
    after_score: int = 0
    score_delta: int = 0
    before_band: str = "critical"
    after_band: str = "critical"
    before_http_status: int = 0
    after_http_status: int = 0
    before_error: str | None = None
    after_error: str | None = None
    before_recommendations_count: int = 0
    after_recommendations_count: int = 0
    recommendations_delta: int = 0
    category_deltas: list[CategoryDelta] = field(default_factory=list)
    improved_categories: list[CategoryDelta] = field(default_factory=list)
    regressed_categories: list[CategoryDelta] = field(default_factory=list)
    unchanged_categories: list[CategoryDelta] = field(default_factory=list)


# ─── Gap analysis ────────────────────────────────────────────────────────────


@dataclass
class GapAction:
    """Azione consigliata per colmare un gap GEO rispetto a un competitor."""

    category: str
    title: str
    rationale: str
    impact_points: int = 0
    priority: str = "medium"
    command: str = ""


@dataclass
class GapAnalysisResult:
    """Gap analysis interpretativa tra due siti GEO."""

    weaker_url: str
    stronger_url: str
    weaker_score: int = 0
    stronger_score: int = 0
    score_gap: int = 0
    weaker_band: str = "critical"
    stronger_band: str = "critical"
    category_deltas: list[CategoryDelta] = field(default_factory=list)
    action_plan: list[GapAction] = field(default_factory=list)
    strengths: list[CategoryDelta] = field(default_factory=list)


# ─── Factual accuracy ────────────────────────────────────────────────────────


@dataclass
class FactualAccuracyResult:
    """Audit euristico di claims, fonti e incoerenze fattuali."""

    checked: bool = False
    claims_found: int = 0
    claims_sourced: int = 0
    claims_unsourced: int = 0
    unsourced_claims: list[str] = field(default_factory=list)
    unverifiable_claims: list[str] = field(default_factory=list)
    inconsistencies: list[str] = field(default_factory=list)
    broken_source_links: list[str] = field(default_factory=list)
    source_links_checked: int = 0
    severity: str = "clean"


# ─── Passive monitor ────────────────────────────────────────────────────────


@dataclass
class MonitorSignal:
    """Segnale sintetico per il monitoraggio passivo della visibilita' AI."""

    key: str
    label: str
    score: int = 0
    max_score: int = 0
    status: str = "missing"
    details: dict[str, object] = field(default_factory=dict)  # extension point


@dataclass
class MonitorResult:
    """Snapshot di visibilita' AI in modalita' passiva per un dominio."""

    domain: str
    url: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    mode: str = "passive"
    direct_mentions_checked: bool = False
    visibility_score: int = 0
    band: str = "low"
    total_snapshots: int = 0
    score_delta: int | None = None
    latest_geo_score: int | None = None
    latest_geo_band: str | None = None
    signals: list[MonitorSignal] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


# ─── Answer snapshots ───────────────────────────────────────────────────────


@dataclass
class AnswerCitation:
    """Citazione estratta o registrata per uno snapshot di risposta AI."""

    url: str
    position: int = 0
    domain: str = ""


@dataclass
class AnswerSnapshot:
    """Snapshot completo di una risposta AI archiviata localmente."""

    snapshot_id: int = 0
    query: str = ""
    prompt: str = ""
    model: str = ""
    provider: str = ""
    answer_text: str = ""
    recorded_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    citations: list[AnswerCitation] = field(default_factory=list)


@dataclass
class AnswerSnapshotArchive:
    """Risultato query sull'archivio locale di snapshot AI."""

    query: str = ""
    date_from: str | None = None
    date_to: str | None = None
    total_snapshots: int = 0
    entries: list[AnswerSnapshot] = field(default_factory=list)


# ─── Citation quality ───────────────────────────────────────────────────────


@dataclass
class CitationQualityResult:
    """Valutazione qualitativa di una singola citazione dentro una risposta AI."""

    url: str
    domain: str = ""
    position: int = 0
    tier: int = 5
    tier_label: str = "mentioned"
    cue: str = ""
    position_score: int = 0
    overall_score: int = 0
    context_snippet: str = ""


@dataclass
class CitationQualityReport:
    """Analisi qualitativa delle citazioni per uno snapshot archiviato."""

    snapshot_id: int = 0
    query: str = ""
    model: str = ""
    provider: str = ""
    recorded_at: str = ""
    target_domain: str = ""
    total_citations: int = 0
    analyzed_citations: int = 0
    entries: list[CitationQualityResult] = field(default_factory=list)


# ─── History / tracking ─────────────────────────────────────────────────────


@dataclass
class HistoryEntry:
    """Snapshot storico di un audit GEO salvato localmente."""

    url: str
    timestamp: str
    score: int = 0
    band: str = "critical"
    http_status: int = 0
    recommendations_count: int = 0
    score_breakdown: dict[str, int] = field(default_factory=dict)
    delta: int | None = None


@dataclass
class HistoryResult:
    """Serie temporale degli audit GEO salvati per una URL."""

    url: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    retention_days: int = 0
    total_snapshots: int = 0
    latest_score: int | None = None
    latest_band: str | None = None
    previous_score: int | None = None
    score_delta: int | None = None
    regression_detected: bool = False
    best_score: int | None = None
    worst_score: int | None = None
    entries: list[HistoryEntry] = field(default_factory=list)


# ─── Schema analysis ─────────────────────────────────────────────────────────


@dataclass
class SchemaAnalysis:
    found_schemas: list[dict] = field(default_factory=list)
    found_types: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extracted_faqs: list[dict[str, str]] = field(default_factory=list)
    duplicates: dict[str, int] = field(default_factory=dict)
    has_head: bool = False
    total_scripts: int = 0


# ─── llms.txt generation ─────────────────────────────────────────────────────


@dataclass
class SitemapUrl:
    url: str
    lastmod: str | None = None
    priority: float = 0.5
    title: str | None = None


# ─── Fix plan ───────────────────────────────────────────────────────────────


@dataclass
class FixItem:
    """Single fix generated by geo fix."""

    category: str  # "robots", "llms", "schema", "meta"
    description: str  # "Adds 5 missing AI bots to robots.txt"
    content: str  # Generated content (file text or HTML tag)
    file_name: str  # "robots.txt", "llms.txt", "schema-website.json"
    action: str  # "create", "append", "snippet"


@dataclass
class FixPlan:
    """Complete fix plan generated by geo fix."""

    url: str
    score_before: int = 0
    score_estimated_after: int = 0
    fixes: list[FixItem] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


# ─── Content workflow (keyword + E-E-A-T + entity) ─────────────────────────


@dataclass
class KeywordDensityItem:
    """Singolo termine/frase con frequenza e densita' percentuale."""

    keyword: str
    count: int = 0
    density_pct: float = 0.0


@dataclass
class ContentWorkflowResult:
    """Audit contenutistico operativo ispirato ai workflow SEO agentici."""

    source: str = ""
    analyzed_words: int = 0
    top_terms: list[KeywordDensityItem] = field(default_factory=list)
    target_keywords: list[KeywordDensityItem] = field(default_factory=list)
    keyword_stuffing: MethodScore = field(
        default_factory=lambda: MethodScore(name="keyword_stuffing", label="Keyword Stuffing")
    )
    eeat_signals: MethodScore = field(default_factory=lambda: MethodScore(name="eeat_signals", label="E-E-A-T Signals"))
    anchor_text_quality: MethodScore = field(
        default_factory=lambda: MethodScore(name="anchor_text_quality", label="Anchor Text Quality")
    )
    entity_resolution: MethodScore = field(
        default_factory=lambda: MethodScore(name="entity_resolution", label="Entity Resolution")
    )
    kg_density: MethodScore = field(
        default_factory=lambda: MethodScore(name="kg_density", label="Knowledge Graph Density")
    )
    recommendations: list[str] = field(default_factory=list)
    error: str = ""


__all__ = [
    "AuditResult",
    "BatchAuditPageResult",
    "BatchAuditResult",
    "CategoryDelta",
    "AuditDiffResult",
    "GapAction",
    "GapAnalysisResult",
    "FactualAccuracyResult",
    "MonitorSignal",
    "MonitorResult",
    "AnswerCitation",
    "AnswerSnapshot",
    "AnswerSnapshotArchive",
    "CitationQualityResult",
    "CitationQualityReport",
    "HistoryEntry",
    "HistoryResult",
    "SchemaAnalysis",
    "SitemapUrl",
    "FixItem",
    "FixPlan",
    "KeywordDensityItem",
    "ContentWorkflowResult",
]
