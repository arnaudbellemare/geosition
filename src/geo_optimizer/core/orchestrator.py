"""Multi-workflow orchestrator for GEO/SEO tasks."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from geo_optimizer.core.audit import run_full_audit
from geo_optimizer.core.audit_marketing import audit_marketing
from geo_optimizer.core.content_workflow import analyze_content_workflow_url
from geo_optimizer.core.link_graph import analyze_link_graph
from geo_optimizer.utils.http import fetch_url


@dataclass
class OrchestrationJob:
    """Single orchestration subtask status."""

    name: str
    status: str = "pending"  # pending|ok|error
    summary: str = ""
    started_at: str = ""
    finished_at: str = ""


@dataclass
class OrchestrationResult:
    """Combined output from multiple SEO/GEO workflows."""

    target: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    jobs: list[OrchestrationJob] = field(default_factory=list)
    geo_score: int | None = None
    marketing_score: int | None = None
    content_recommendations: list[str] = field(default_factory=list)
    orphan_pages: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def run_orchestration(
    url: str,
    *,
    run_marketing: bool = True,
    run_content: bool = True,
    run_links: bool = False,
    sitemap: str | None = None,
    max_pages: int = 30,
) -> OrchestrationResult:
    """Run multiple SEO/GEO workflows in parallel and aggregate outputs."""
    result = OrchestrationResult(target=url)

    futures = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures[pool.submit(_run_geo_job, url)] = "geo"
        if run_marketing:
            futures[pool.submit(_run_marketing_job, url)] = "marketing"
        if run_content:
            futures[pool.submit(_run_content_job, url)] = "content"
        if run_links and sitemap:
            futures[pool.submit(_run_links_job, sitemap, max_pages)] = "links"

        for future in as_completed(futures):
            job_type = futures[future]
            job = OrchestrationJob(name=job_type, started_at=datetime.now(timezone.utc).isoformat())
            try:
                payload = future.result()
            except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
                job.status = "error"
                job.summary = f"{job_type} failed: {exc}"
                result.errors.append(job.summary)
                job.finished_at = datetime.now(timezone.utc).isoformat()
                result.jobs.append(job)
                continue

            job.status = "ok"
            job.summary = payload.get("summary", "")
            job.finished_at = datetime.now(timezone.utc).isoformat()
            result.jobs.append(job)

            if job_type == "geo":
                result.geo_score = payload.get("score")
            elif job_type == "marketing":
                result.marketing_score = payload.get("score")
            elif job_type == "content":
                result.content_recommendations = payload.get("recommendations", [])
            elif job_type == "links":
                result.orphan_pages = payload.get("orphans", [])

    return result


def _run_geo_job(url: str) -> dict:
    audit = run_full_audit(url)
    if audit.error:
        return {"summary": f"GEO error: {audit.error}", "score": None}
    return {"summary": f"GEO {audit.score}/100", "score": audit.score}


def _run_marketing_job(url: str) -> dict:
    audit = run_full_audit(url)
    if audit.error:
        return {"summary": f"Marketing skipped (audit error: {audit.error})", "score": None}

    response, err = fetch_url(url)
    if err or response is None:
        return {"summary": f"Marketing fetch error: {err}", "score": None}
    soup = BeautifulSoup(response.text, "html.parser")
    mkt = audit_marketing(
        soup=soup,
        base_url=url,
        schema=audit.schema,
        meta=audit.meta,
        content=audit.content,
        conversion=audit.conversion,
        citability=audit.citability,
    )
    return {"summary": f"Marketing {mkt.marketing_score}/100", "score": mkt.marketing_score}


def _run_content_job(url: str) -> dict:
    content = analyze_content_workflow_url(url)
    if content.error:
        return {"summary": f"Content error: {content.error}", "recommendations": []}
    return {
        "summary": f"Content recommendations: {len(content.recommendations)}",
        "recommendations": content.recommendations,
    }


def _run_links_job(sitemap: str, max_pages: int) -> dict:
    links = analyze_link_graph(sitemap, max_pages=max_pages)
    if links.error:
        return {"summary": f"Links error: {links.error}", "orphans": []}
    return {"summary": f"Orphans: {len(links.orphan_pages)}", "orphans": links.orphan_pages}
