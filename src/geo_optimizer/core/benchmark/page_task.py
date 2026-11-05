"""Map site pages to supported user tasks."""

from __future__ import annotations

from geo_optimizer.core.benchmark.task_classifier import classify_page
from geo_optimizer.models.config import TASK_CLASSIFIER_SIGNALS
from geo_optimizer.models.results import AuditResult
from geo_optimizer.models.results.benchmark import PageTaskCoverageRecord, TaskGap


def _page_text_from_audit(audit: AuditResult) -> str:
    parts = [
        audit.url,
        audit.meta.title_text if audit.meta else "",
        audit.meta.description_text if audit.meta else "",
    ]
    if audit.content and audit.content.h1_text:
        parts.append(audit.content.h1_text)
    return " ".join(part for part in parts if part)


def map_audit_to_page_coverage(audit: AuditResult) -> PageTaskCoverageRecord:
    """Derive task coverage for the audited URL from on-page signals."""
    page_text = _page_text_from_audit(audit)
    primary = classify_page(page_text)
    supported: list[str] = [primary.task]
    missing: list[str] = []

    if audit.schema and audit.schema.any_schema_found:
        schema_ok = True
    else:
        schema_ok = False
        missing.append("structured data (JSON-LD)")

    citation_readiness = audit.citability.total_score if audit.citability else 0
    if citation_readiness < 50:
        missing.append("citation-ready structure (lists, sources, specifics)")

    serp_alignment = 50
    if audit.meta and audit.meta.title_text and audit.meta.description_text:
        serp_alignment = 75

    performance_blockers: list[str] = []
    if audit.url.lower().startswith("http://"):
        performance_blockers.append("HTTPS not enforced")

    lowered = page_text.lower()
    for task_hint in ("pricing", "local", "comparison", "implementation"):
        signals = TASK_CLASSIFIER_SIGNALS.get(task_hint, [])
        if any(sig in lowered for sig in signals) and task_hint not in supported:
            supported.append(task_hint)
    supported = supported[:4]

    confidence = round(min(0.95, primary.confidence * 0.7 + (citation_readiness / 100) * 0.3), 2)
    return PageTaskCoverageRecord(
        url=audit.url,
        supported_tasks=supported,
        confidence=confidence,
        missing_evidence=missing,
        schema_support=schema_ok,
        citation_readiness=citation_readiness,
        serp_alignment=serp_alignment,
        backlink_support=0,
        performance_blockers=performance_blockers,
    )


def build_task_gaps(
    page_coverage: list[PageTaskCoverageRecord],
    task_metrics: list,
    *,
    demand_threshold: float = 0.2,
) -> list[TaskGap]:
    """Identify tasks with AI demand but weak on-site coverage."""
    demand_by_task: dict[str, float] = {}
    for metric in task_metrics:
        demand_by_task[metric.task] = max(
            demand_by_task.get(metric.task, 0.0),
            metric.citation_rate + sum(metric.competitor_mention_rates.values()),
        )

    covered: dict[str, float] = {}
    for page in page_coverage:
        for task in page.supported_tasks:
            covered[task] = max(covered.get(task, 0.0), page.confidence)

    gaps: list[TaskGap] = []
    for task, demand in sorted(demand_by_task.items()):
        coverage = covered.get(task, 0.0)
        if demand < demand_threshold:
            continue
        if coverage >= demand:
            continue
        severity = "high" if demand - coverage > 0.4 else "medium" if demand - coverage > 0.2 else "low"
        gaps.append(
            TaskGap(
                task=task,
                ai_demand_rate=round(demand, 3),
                page_coverage_score=round(coverage, 3),
                gap_severity=severity,
                recommendation=(
                    f"Create or strengthen a page for '{task}' — AI demand is {demand:.0%} "
                    f"but on-site coverage is only {coverage:.0%}."
                ),
            )
        )
    gaps.sort(key=lambda item: item.ai_demand_rate - item.page_coverage_score, reverse=True)
    return gaps
