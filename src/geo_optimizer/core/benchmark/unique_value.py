"""Explainable unique value vs commodity risk scoring."""

from __future__ import annotations

import re

from geo_optimizer.models.results import AuditResult
from geo_optimizer.models.results.benchmark import PageTaskCoverageRecord, UniqueValueAssessment

_GENERIC_RE = re.compile(
    r"\b(industry-leading|world-class|cutting-edge|best-in-class|innovative solution|trusted partner)\b",
    re.I,
)
_SPECIFIC_RE = re.compile(
    r"\b(\d{4}|\d+%|\$\d|case study|testimonial|review|team|certified|licensed|warranty|guarantee)\b",
    re.I,
)
_LOCAL_RE = re.compile(r"\b(city|local|neighborhood|region|serving|near)\b", re.I)


def assess_unique_value(
    audit: AuditResult | None,
    page_coverage: list[PageTaskCoverageRecord],
) -> UniqueValueAssessment:
    """Score differentiated value from audit and page-task coverage."""
    positive: list[str] = []
    negative: list[str] = []
    score = 50

    if audit is None:
        return UniqueValueAssessment(
            unique_value_score=None,
            commodity_risk="unknown",
            positive_signals=positive,
            negative_signals=["no site audit available"],
            summary="Run with --audit-url to score on-site proof and structure.",
        )

    text_blob = ""
    if audit.content and audit.content.h1_text:
        text_blob = audit.content.h1_text
    if audit.meta:
        text_blob += f" {audit.meta.title_text} {audit.meta.description_text}"

    if audit.schema and audit.schema.any_schema_found:
        score += 8
        positive.append("structured schema present")
    else:
        score -= 6
        negative.append("weak or missing schema")

    if audit.citability and audit.citability.total_score >= 60:
        score += 10
        positive.append("citation-ready content structure")
    elif audit.citability:
        score -= 5
        negative.append("low citation readiness")

    if audit.brand_entity and (audit.brand_entity.names_found or audit.brand_entity.kg_pillar_count):
        score += 6
        positive.append("entity/organization signals")
    else:
        negative.append("weak entity signals")

    if _SPECIFIC_RE.search(text_blob):
        score += 8
        positive.append("specific proof (numbers, case studies, or credentials)")
    if _LOCAL_RE.search(text_blob):
        score += 5
        positive.append("local proof or service area specificity")
    if _GENERIC_RE.search(text_blob):
        score -= 10
        negative.append("generic marketing copy")

    task_count = len({task for page in page_coverage for task in page.supported_tasks})
    if task_count >= 3:
        score += 6
        positive.append("multi-task page coverage")
    elif task_count <= 1:
        score -= 8
        negative.append("narrow task-specific coverage")

    pricing_pages = any("pricing" in page.supported_tasks for page in page_coverage)
    if not pricing_pages:
        negative.append("weak pricing/task coverage")

    score = max(0, min(100, score))
    if score >= 70:
        risk = "low"
    elif score >= 45:
        risk = "medium"
    else:
        risk = "high"

    summary_parts = []
    if positive:
        summary_parts.append("strong " + positive[0])
    if negative:
        summary_parts.append("but " + negative[0])
    summary = ", ".join(summary_parts) if summary_parts else "balanced proof and coverage signals"

    return UniqueValueAssessment(
        unique_value_score=score,
        commodity_risk=risk,
        positive_signals=positive,
        negative_signals=negative,
        summary=summary.capitalize(),
    )
