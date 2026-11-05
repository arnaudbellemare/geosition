"""Dataclasses for domain GEO benchmark layer."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TaskClassification:
    """Rule-based or LLM-assisted task label."""

    task: str = ""
    confidence: float = 0.0
    signals: list[str] = field(default_factory=list)
    source: str = "rules"  # rules | llm


@dataclass
class TrackedPromptRecord:
    """Persisted prompt tracked for benchmark runs."""

    prompt_id: int = 0
    prompt_text: str = ""
    task: str = ""
    keyword_topic: str = ""
    persona: str = ""
    target_domain: str = ""
    created_at: str = ""


@dataclass
class CitationSnapshotRecord:
    """Single AI answer with citations for benchmark analysis."""

    snapshot_id: int = 0
    provider: str = ""
    model: str = ""
    prompt_id: int = 0
    prompt_text: str = ""
    task: str = ""
    task_confidence: float = 0.0
    answer_text: str = ""
    recorded_at: str = ""
    cited_urls: list[str] = field(default_factory=list)
    citation_positions: list[int] = field(default_factory=list)


@dataclass
class CompetitorMentionRecord:
    """Competitor presence in one citation snapshot."""

    mention_id: int = 0
    snapshot_id: int = 0
    competitor_domain: str = ""
    competitor_name: str = ""
    cited: bool = False
    mentioned: bool = False
    position: int = 0
    sentiment: str = "neutral"  # positive | neutral | negative


@dataclass
class PageTaskCoverageRecord:
    """Page-level support for user tasks."""

    url: str = ""
    supported_tasks: list[str] = field(default_factory=list)
    confidence: float = 0.0
    missing_evidence: list[str] = field(default_factory=list)
    schema_support: bool = False
    citation_readiness: int = 0
    serp_alignment: int = 0
    backlink_support: int = 0
    performance_blockers: list[str] = field(default_factory=list)


@dataclass
class EvidenceArtifactRecord:
    """Exportable proof attached to a benchmark run."""

    artifact_id: int = 0
    run_id: int = 0
    artifact_type: str = ""  # answer | serp | pagespeed | backlink | audit
    label: str = ""
    payload: str = ""
    recorded_at: str = ""


@dataclass
class TaskCitationMetrics:
    """Citation share metrics for one task (optionally per provider)."""

    task: str = ""
    provider: str = ""
    sample_size: int = 0
    target_cited_count: int = 0
    citation_rate: float = 0.0
    avg_citation_position: float | None = None
    source_url_frequency: dict[str, int] = field(default_factory=dict)
    brand_mention_rate: float = 0.0
    competitor_mention_rates: dict[str, float] = field(default_factory=dict)
    cited_beside_target: int = 0
    cited_instead_of_target: int = 0


@dataclass
class CompetitorMatrixRow:
    """One row in the competitor substitution matrix."""

    task: str = ""
    target_rate: float = 0.0
    competitor_rates: dict[str, float] = field(default_factory=dict)
    target_absent_should_present: bool = False


@dataclass
class CompetitorSubstitutionMatrix:
    """Task × competitor citation share matrix."""

    target_domain: str = ""
    competitor_domains: list[str] = field(default_factory=list)
    rows: list[CompetitorMatrixRow] = field(default_factory=list)


@dataclass
class UniqueValueAssessment:
    """Explainable unique value vs commodity risk."""

    unique_value_score: int | None = None
    commodity_risk: str = "unknown"  # low | medium | high | unknown
    positive_signals: list[str] = field(default_factory=list)
    negative_signals: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class CitedPageRecord:
    """A single page ranked by how often AI answers cite it."""

    url: str = ""
    domain: str = ""
    citation_count: int = 0
    avg_position: float | None = None
    tasks: list[str] = field(default_factory=list)


@dataclass
class DomainEconomics:
    """Per-domain citation economics, used for side-by-side comparison charts."""

    domain: str = ""
    is_target: bool = False
    cited_snapshots: int = 0
    present_snapshots: int = 0
    citation_share: float = 0.0
    surface_share: float = 0.0
    selection_premium: float = 0.0
    value_concentration: float = 0.0
    uniqueness_index: float = 0.0


@dataclass
class CitationEconomicsResult:
    """Selection premium, value concentration, and uniqueness for a domain.

    These are demand-side metrics that go beyond raw citation share: they ask
    whether a domain earns selection above its footprint (selection premium),
    whether it wins on high-value queries (value concentration), and whether it
    is hard to substitute (uniqueness).
    """

    target_domain: str = ""
    sample_size: int = 0
    total_citations: int = 0

    selection_premium: float = 0.0
    selection_label: str = "neutral"  # selected | neutral | overlooked
    selection_summary: str = ""

    value_concentration: float = 0.0
    value_label: str = "balanced"  # valued | balanced | undervalued
    value_summary: str = ""

    uniqueness_index: float = 0.0
    uniqueness_label: str = "defensible"  # unique | defensible | substitutable
    uniqueness_summary: str = ""

    domains: list[DomainEconomics] = field(default_factory=list)
    most_cited_pages: list[CitedPageRecord] = field(default_factory=list)


@dataclass
class BenchmarkScoreBreakdown:
    """Weighted components of the aggregate GEO benchmark."""

    citation_share: int = 0
    task_coverage: int = 0
    competitor_position: int | None = None
    unique_value: int | None = None
    domain_backlink: int | None = None
    serp_rank: int | None = None
    technical_performance: int | None = None
    scoring_version: str = "legacy"
    measured_weight: float = 1.0


@dataclass
class BenchmarkRunRecord:
    """Persisted benchmark run summary."""

    run_id: int = 0
    domain: str = ""
    run_at: str = ""
    schedule: str = "manual"
    benchmark_score: int = 0
    band: str = ""
    breakdown: BenchmarkScoreBreakdown = field(default_factory=BenchmarkScoreBreakdown)
    provider_coverage: dict[str, int] = field(default_factory=dict)


@dataclass
class BenchmarkScheduleRecord:
    """Scheduled benchmark configuration."""

    schedule_id: int = 0
    domain: str = ""
    frequency: str = "weekly"  # daily | weekly | manual
    competitor_domains: list[str] = field(default_factory=list)
    last_run_at: str | None = None
    next_run_at: str | None = None
    enabled: bool = True


@dataclass
class TaskGap:
    """Demand vs on-site coverage gap."""

    task: str = ""
    ai_demand_rate: float = 0.0
    page_coverage_score: float = 0.0
    gap_severity: str = "medium"  # low | medium | high
    recommendation: str = ""


@dataclass
class BenchmarkRunResult:
    """Full result of a benchmark run (returned by core, formatted by CLI)."""

    domain: str = ""
    run_id: int = 0
    run_at: str = ""
    schedule: str = "manual"
    benchmark_score: int = 0
    band: str = ""
    breakdown: BenchmarkScoreBreakdown = field(default_factory=BenchmarkScoreBreakdown)
    task_metrics: list[TaskCitationMetrics] = field(default_factory=list)
    provider_coverage: dict[str, int] = field(default_factory=dict)
    competitor_matrix: CompetitorSubstitutionMatrix = field(default_factory=CompetitorSubstitutionMatrix)
    page_coverage: list[PageTaskCoverageRecord] = field(default_factory=list)
    task_gaps: list[TaskGap] = field(default_factory=list)
    unique_value: UniqueValueAssessment = field(default_factory=UniqueValueAssessment)
    citation_economics: CitationEconomicsResult = field(default_factory=CitationEconomicsResult)
    snapshots_stored: int = 0
    evidence_artifacts: list[EvidenceArtifactRecord] = field(default_factory=list)
    executive_summary: str = ""


@dataclass
class BenchmarkTrendPoint:
    """Time-series point for dashboard / scheduling."""

    run_at: str = ""
    benchmark_score: int = 0
    citation_share_score: int = 0
    task_coverage_score: int = 0
    competitor_position_score: int = 0


@dataclass
class CitationShareSummary:
    """Latest AI-answer monitoring summary for one benchmark run."""

    domain: str = ""
    run_id: int = 0
    run_at: str = ""
    benchmark_score: int = 0
    band: str = ""
    scoring_version: str = "legacy"
    evidence_coverage: float = 1.0
    sample_size: int = 0
    target_cited_count: int = 0
    target_citation_rate: float = 0.0
    provider_coverage: dict[str, int] = field(default_factory=dict)
    competitor_citation_rates: dict[str, float] = field(default_factory=dict)
    competitor_mention_rates: dict[str, float] = field(default_factory=dict)
    top_cited_sources: dict[str, int] = field(default_factory=dict)


@dataclass
class NegotiationReportData:
    """Structured payload for HTML/CSV/PDF export."""

    result: BenchmarkRunResult = field(default_factory=BenchmarkRunResult)
    strongest_pages: list[str] = field(default_factory=list)
    weakest_pages: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)


__all__ = [
    "TaskClassification",
    "TrackedPromptRecord",
    "CitationSnapshotRecord",
    "CompetitorMentionRecord",
    "PageTaskCoverageRecord",
    "EvidenceArtifactRecord",
    "TaskCitationMetrics",
    "CompetitorMatrixRow",
    "CompetitorSubstitutionMatrix",
    "UniqueValueAssessment",
    "CitedPageRecord",
    "DomainEconomics",
    "CitationEconomicsResult",
    "BenchmarkScoreBreakdown",
    "BenchmarkRunRecord",
    "BenchmarkScheduleRecord",
    "TaskGap",
    "BenchmarkRunResult",
    "BenchmarkTrendPoint",
    "CitationShareSummary",
    "NegotiationReportData",
]
