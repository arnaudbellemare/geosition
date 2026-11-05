"""Dataclasses for classic SEO intelligence features."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class KeywordMetric:
    """Metrics for a single researched keyword."""

    keyword: str = ""
    volume: int = 0
    cpc: float = 0.0
    competition: float = 0.0
    difficulty: int = 0
    intent: str = "informational"
    trend: list[int] = field(default_factory=list)
    source: str = "local-estimate"


@dataclass
class KeywordResearchResult:
    """Keyword research result with optional persistence/export metadata."""

    checked: bool = False
    seed: str = ""
    provider: str = "local-estimate"
    metrics: list[KeywordMetric] = field(default_factory=list)
    saved_list_path: str = ""
    csv_path: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class SerpCrowdednessResult:
    """Crowdedness score for a keyword SERP."""

    checked: bool = False
    keyword: str = ""
    score: int = 0
    label: str = "unknown"
    organic_results: int = 0
    ads_count: int = 0
    serp_features: list[str] = field(default_factory=list)
    competitor_domains: list[str] = field(default_factory=list)
    factors: list[str] = field(default_factory=list)


@dataclass
class DomainTopPage:
    """Estimated high-value page for a profiled domain."""

    url: str = ""
    title: str = ""
    estimated_traffic: int = 0
    keyword_count: int = 0


@dataclass
class DomainKeyword:
    """Keyword a domain appears to target or rank for."""

    keyword: str = ""
    position: int = 0
    volume: int = 0
    url: str = ""


@dataclass
class DomainCompetitor:
    """Competing domain found from SERP or provider data."""

    domain: str = ""
    overlap_keywords: int = 0
    authority: int = 0


@dataclass
class KeywordGap:
    """Keyword opportunity where a competitor is visible and target is not."""

    keyword: str = ""
    competitor_domain: str = ""
    competitor_position: int = 0
    volume: int = 0
    difficulty: int = 0


@dataclass
class DomainAnalysisResult:
    """Domain profile, competitors, and keyword-gap analysis."""

    checked: bool = False
    domain: str = ""
    provider: str = "local-estimate"
    authority: int = 0
    estimated_traffic: int = 0
    top_pages: list[DomainTopPage] = field(default_factory=list)
    ranked_keywords: list[DomainKeyword] = field(default_factory=list)
    competitors: list[DomainCompetitor] = field(default_factory=list)
    keyword_gaps: list[KeywordGap] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class BacklinkRecord:
    """Single backlink record from a provider."""

    source_url: str = ""
    source_domain: str = ""
    target_url: str = ""
    anchor: str = ""
    link_strength: int = 0
    first_seen: str = ""
    last_seen: str = ""
    status: str = "live"


@dataclass
class ReferringDomainRecord:
    """Aggregated referring-domain strength."""

    domain: str = ""
    backlinks: int = 0
    authority: int = 0


@dataclass
class BacklinkHistoryPoint:
    """New/lost backlink history point."""

    date: str = ""
    new_links: int = 0
    lost_links: int = 0


@dataclass
class BacklinkAnalysisResult:
    """Backlink analysis behind a vendor-neutral provider seam."""

    checked: bool = False
    domain: str = ""
    provider: str = "local-empty"
    backlinks: list[BacklinkRecord] = field(default_factory=list)
    referring_domains: list[ReferringDomainRecord] = field(default_factory=list)
    anchors: dict[str, int] = field(default_factory=dict)
    new_lost_history: list[BacklinkHistoryPoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class RankSnapshot:
    """One organic rank snapshot for a tracked keyword."""

    keyword: str = ""
    url: str = ""
    domain: str = ""
    rank: int | None = None
    checked_at: str = ""
    search_engine: str = "google"


@dataclass
class TrackedKeyword:
    """Tracked organic keyword configuration."""

    keyword: str = ""
    url: str = ""
    domain: str = ""
    created_at: str = ""


@dataclass
class RankTrackingResult:
    """Classic organic rank-tracking result."""

    checked: bool = False
    db_path: str = ""
    tracked_keywords: list[TrackedKeyword] = field(default_factory=list)
    snapshots: list[RankSnapshot] = field(default_factory=list)
    average_rank: float = 0.0
    best_rank: int | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class LighthouseMetric:
    """Single Lighthouse/PageSpeed metric."""

    name: str = ""
    value: str = ""
    score: float | None = None


@dataclass
class LighthouseResult:
    """Google Lighthouse/PageSpeed performance audit result."""

    checked: bool = False
    url: str = ""
    provider: str = ""
    performance_score: int = 0
    accessibility_score: int = 0
    best_practices_score: int = 0
    seo_score: int = 0
    metrics: list[LighthouseMetric] = field(default_factory=list)
    image_rendering_ms: int = 0
    video_rendering_ms: int = 0
    page_load_ms: int = 0
    report_path: str = ""
    warnings: list[str] = field(default_factory=list)
