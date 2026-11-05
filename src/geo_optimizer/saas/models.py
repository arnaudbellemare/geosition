"""Dataclasses for GEO platform (SaaS) layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict


class IndexTrendPoint(TypedDict):
    date: str
    events: int
    cited: int
    top: int
    value_units: float


@dataclass
class PlatformUser:
    user_id: int = 0
    email: str = ""
    email_domain: str = ""
    created_at: str = ""


@dataclass
class Organization:
    org_id: int = 0
    name: str = ""
    email_domain: str = ""
    slug: str = ""
    created_at: str = ""


@dataclass
class SessionInfo:
    token: str = ""
    user_id: int = 0
    expires_at: str = ""


@dataclass
class VerifiedDomain:
    domain_id: int = 0
    org_id: int = 0
    domain: str = ""
    status: str = "pending"  # pending | verified
    verify_token: str = ""
    verify_method: str = ""  # dns | https
    verified_at: str | None = None
    created_at: str = ""


@dataclass
class OrgCompetitor:
    competitor_id: int = 0
    org_id: int = 0
    domain: str = ""


@dataclass
class OrgPrompt:
    prompt_id: int = 0
    org_id: int = 0
    external_id: str = ""
    query_text: str = ""
    query_class: str = ""
    keyword_topic: str = ""
    persona: str = ""
    country: str = ""


@dataclass
class OrgBenchmarkLink:
    link_id: int = 0
    org_id: int = 0
    domain: str = ""
    benchmark_run_id: int = 0
    benchmark_score: int = 0
    band: str = ""
    run_at: str = ""


@dataclass
class WeeklyEvidenceMetric:
    """One normalized metric in a weekly company evidence report."""

    key: str = ""
    label: str = ""
    value: str = ""
    previous_value: str = ""
    delta: str = ""
    unit: str = ""
    status: str = "unknown"
    evidence_ref: str = ""


@dataclass
class WeeklyEvidenceRun:
    """Durable weekly GEO/SEO/CRO evidence report for one verified domain."""

    report_id: int = 0
    org_id: int = 0
    domain: str = ""
    period_start: str = ""
    period_end: str = ""
    status: str = "completed"
    generated_at: str = ""
    score: int | None = None
    band: str = ""
    metrics: list[WeeklyEvidenceMetric] = field(default_factory=list)
    artifact_json_uri: str = ""
    artifact_html_uri: str = ""
    summary: str = ""
    action_plan: dict[str, object] = field(default_factory=dict)


@dataclass
class PlatformRun:
    """Durable platform job/run record for audits, benchmarks, and future collection work."""

    run_id: int = 0
    org_id: int = 0
    kind: str = ""  # audit | benchmark | collection | export
    domain: str = ""
    status: str = "queued"  # queued | running | completed | failed
    score: int | None = None
    band: str = ""
    external_run_id: str = ""
    error: str = ""
    result_summary: str = ""
    created_at: str = ""
    started_at: str | None = None
    completed_at: str | None = None


@dataclass
class PageAuditRecord:
    """Durable page-level audit result for sitemap/history views."""

    page_audit_id: int = 0
    org_id: int = 0
    run_id: int = 0
    domain: str = ""
    page_url: str = ""
    sitemap_url: str = ""
    score: int = 0
    band: str = ""
    http_status: int | None = None
    error: str = ""
    score_breakdown: dict[str, object] = field(default_factory=dict)
    title_issues: list[str] = field(default_factory=list)
    meta_issues: list[str] = field(default_factory=list)
    schema_issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    created_at: str = ""
    previous_score: int | None = None
    score_delta: int | None = None


@dataclass
class AgentUsageEvent:
    """Observed AI-agent answer usage for a verified content owner domain."""

    event_id: int = 0
    org_id: int = 0
    domain: str = ""
    page_url: str = ""
    source_type: str = "manual_ai_answer"
    # manual_ai_answer | benchmark | crawler_log | retrieval_probe | serp_check | partner_api
    agent: str = ""
    query: str = ""
    answer_excerpt: str = ""
    cited_url: str = ""
    cited_rank: int | None = None
    surfaced: bool = False
    cited: bool = False
    top_recommendation: bool = False
    confidence: float = 1.0
    value_units: float = 0.0
    evidence_artifact_id: str = ""
    evidence: dict[str, object] = field(default_factory=dict)
    created_at: str = ""


@dataclass
class IndexTelemetrySummary:
    """Aggregated demand-side visibility view for a content owner domain."""

    domain: str = ""
    total_events: int = 0
    surfaced_events: int = 0
    cited_events: int = 0
    top_recommendation_events: int = 0
    citation_rate: float = 0.0
    top_recommendation_rate: float = 0.0
    total_value_units: float = 0.0
    agent_coverage: dict[str, int] = field(default_factory=dict)
    source_coverage: dict[str, int] = field(default_factory=dict)
    top_queries: dict[str, int] = field(default_factory=dict)
    top_pages: dict[str, int] = field(default_factory=dict)
    top_cited_pages: dict[str, int] = field(default_factory=dict)
    missed_queries: dict[str, int] = field(default_factory=dict)
    trend_points: list[IndexTrendPoint] = field(default_factory=list)
    action_plan: dict[str, object] = field(default_factory=dict)
    recent_events: list[AgentUsageEvent] = field(default_factory=list)


@dataclass
class AgencyLoopStep:
    """One step in the agency operating loop shown in the SaaS dashboard."""

    step_id: str = ""
    number: str = ""
    title: str = ""
    description: str = ""
    state: str = "waiting"  # current | done | waiting
    label: str = "Waiting"
    action: str = ""
    proof: str = ""
    plan: str = "free"


@dataclass
class AgencyLoopState:
    """Current agency workflow state derived from verified data and saved evidence."""

    current_step: str = "verify"
    next_action: str = "Verify domain"
    next_action_target: str = "verify"
    summary: str = "Verify ownership before audits and benchmarks unlock."
    proof_focus: str = "No client proof yet."
    paid_boundary: str = "Paid access automates recurring audits, benchmarks, CLI runs, and weekly proof reports."
    steps: list[AgencyLoopStep] = field(default_factory=list)


@dataclass
class PlatformDashboard:
    """Aggregated workspace view for the client UI."""

    organization: Organization = field(default_factory=Organization)
    user: PlatformUser = field(default_factory=PlatformUser)
    domains: list[VerifiedDomain] = field(default_factory=list)
    competitors: list[OrgCompetitor] = field(default_factory=list)
    prompts: list[OrgPrompt] = field(default_factory=list)
    recent_benchmarks: list[OrgBenchmarkLink] = field(default_factory=list)
    recent_runs: list[PlatformRun] = field(default_factory=list)
    recent_page_audits: list[PageAuditRecord] = field(default_factory=list)
    recent_weekly_reports: list[WeeklyEvidenceRun] = field(default_factory=list)
    index_summary: IndexTelemetrySummary = field(default_factory=IndexTelemetrySummary)
    agency_loop: AgencyLoopState = field(default_factory=AgencyLoopState)
    primary_verified_domain: str = ""
    target_domain: str = ""
