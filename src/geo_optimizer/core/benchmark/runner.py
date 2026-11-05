"""Orchestrate a full domain benchmark run."""

from __future__ import annotations

import json

from geo_optimizer.core.audit import run_full_audit
from geo_optimizer.core.benchmark.citation_economics import compute_citation_economics
from geo_optimizer.core.benchmark.citation_share import compute_task_citation_metrics
from geo_optimizer.core.benchmark.competitor_matrix import build_competitor_substitution_matrix
from geo_optimizer.core.benchmark.competitors import extract_competitor_mentions
from geo_optimizer.core.benchmark.domains import normalize_benchmark_domain
from geo_optimizer.core.benchmark.page_task import build_task_gaps, map_audit_to_page_coverage
from geo_optimizer.core.benchmark.score import aggregate_benchmark_score
from geo_optimizer.core.benchmark.store import BenchmarkStore
from geo_optimizer.core.benchmark.task_classifier import classify_prompt
from geo_optimizer.core.benchmark.unique_value import assess_unique_value
from geo_optimizer.core.snapshots import extract_citations
from geo_optimizer.models.results import AuditResult
from geo_optimizer.models.results.benchmark import (
    BenchmarkRunResult,
    CitationSnapshotRecord,
    NegotiationReportData,
    UniqueValueAssessment,
)


def _domain_url(domain: str) -> str:
    normalized = normalize_benchmark_domain(domain)
    return f"https://{normalized}"


def _memory_snapshots(
    pending_rows: list[dict],
    *,
    target: str,
    competitors: list[str],
) -> tuple[list[CitationSnapshotRecord], dict[int, list]]:
    """Build in-memory snapshots and mentions for scoring before persistence."""
    snapshots: list[CitationSnapshotRecord] = []
    mentions_by_snapshot: dict[int, list] = {}
    for index, pending in enumerate(pending_rows, start=1):
        snapshots.append(
            CitationSnapshotRecord(
                snapshot_id=index,
                provider=pending["provider"],
                model=pending["model"],
                prompt_text=pending["prompt_text"],
                task=pending["task"],
                task_confidence=pending["task_confidence"],
                answer_text=pending["answer_text"],
                cited_urls=[item[0] for item in pending["cited_triples"]],
                citation_positions=[item[2] for item in pending["cited_triples"]],
            )
        )
        mentions_by_snapshot[index] = extract_competitor_mentions(
            pending["answer_text"],
            target_domain=target,
            competitors=competitors,
            extra_urls=pending.get("extra_urls"),
        )
    return snapshots, mentions_by_snapshot


def run_domain_benchmark(
    domain: str,
    *,
    competitors: list[str] | None = None,
    answers: list[dict] | None = None,
    schedule: str = "manual",
    audit_url: str | None = None,
    use_cache: bool = False,
    store: BenchmarkStore | None = None,
    save_prompts: bool = True,
) -> BenchmarkRunResult:
    """Run benchmark pipeline: ingest answers, classify, score, persist.

    Each answer dict supports:
        prompt (str), answer_text (str), provider (str), model (str),
        task (optional hint), keyword_topic, persona, citation_urls (list)
    """
    benchmark_store = store or BenchmarkStore()
    target = normalize_benchmark_domain(domain)
    competitor_list = [normalize_benchmark_domain(item) for item in (competitors or []) if item]
    answer_rows = list(answers or [])
    if not answer_rows:
        raise ValueError("At least one AI answer is required to run a benchmark")

    pending_rows: list[dict] = []

    for row in answer_rows:
        prompt_text = str(row.get("prompt", "")).strip()
        answer_text = str(row.get("answer_text", "")).strip()
        if (
            not prompt_text
            or not answer_text
            or row.get("status", "success") != "success"
            or answer_text.startswith("[collection error:")
        ):
            continue
        provider = str(row.get("provider", "unknown"))
        model = str(row.get("model", ""))
        hint_task = str(row.get("task", ""))
        classification = classify_prompt(prompt_text, hint_task=hint_task)

        prompt_record = None
        if save_prompts:
            prompt_record = benchmark_store.upsert_tracked_prompt(
                prompt_text,
                target,
                task=classification.task,
                keyword_topic=str(row.get("keyword_topic", "")),
                persona=str(row.get("persona", "")),
            )

        citations = extract_citations(answer_text, extra_urls=row.get("citation_urls"))
        pending_rows.append(
            {
                "provider": provider,
                "model": model,
                "prompt_text": prompt_text,
                "task": classification.task,
                "task_confidence": classification.confidence,
                "answer_text": answer_text,
                "cited_triples": [(c.url, c.domain, c.position) for c in citations],
                "prompt_id": prompt_record.prompt_id if prompt_record else None,
                "extra_urls": row.get("citation_urls"),
            }
        )
    if not pending_rows:
        raise ValueError("At least one valid AI answer (prompt + answer_text) is required")

    audit_result: AuditResult | None = None
    page_coverage = []
    if audit_url or domain:
        try:
            audit_result = run_full_audit(audit_url or _domain_url(domain), use_cache=use_cache)
            if audit_result.error:
                audit_result = None
            else:
                page_coverage = [map_audit_to_page_coverage(audit_result)]
        except Exception:
            audit_result = None

    snapshot_records, mentions_by_snapshot = _memory_snapshots(
        pending_rows,
        target=target,
        competitors=competitor_list,
    )

    task_metrics = compute_task_citation_metrics(
        snapshot_records,
        mentions_by_snapshot,
        target_domain=target,
        competitor_domains=competitor_list,
    )
    matrix = build_competitor_substitution_matrix(
        task_metrics,
        target_domain=target,
        competitor_domains=competitor_list,
    )
    citation_economics = compute_citation_economics(
        snapshot_records,
        target_domain=target,
        competitor_domains=competitor_list,
        mentions_by_snapshot=mentions_by_snapshot,
    )
    task_gaps = build_task_gaps(page_coverage, task_metrics)
    unique_value = assess_unique_value(audit_result, page_coverage)

    score, band, breakdown = aggregate_benchmark_score(
        task_metrics=task_metrics,
        matrix=matrix,
        unique_value=unique_value,
        unique_value_measured=audit_result is not None,
        gap_count=len(task_gaps),
    )

    provider_coverage: dict[str, int] = {}
    for metric in task_metrics:
        provider_coverage[metric.provider] = provider_coverage.get(metric.provider, 0) + metric.sample_size

    run_record = benchmark_store.save_benchmark_run(
        target,
        schedule=schedule,
        benchmark_score=score,
        band=band,
        breakdown=breakdown,
        provider_coverage=provider_coverage,
    )
    run_id = run_record.run_id

    if page_coverage:
        benchmark_store.save_page_task_coverage(run_id, page_coverage)

    for pending, memory_snap in zip(pending_rows, snapshot_records):
        persisted = benchmark_store.save_citation_snapshot(
            run_id=run_id,
            provider=pending["provider"],
            model=pending["model"],
            prompt_text=pending["prompt_text"],
            task=pending["task"],
            task_confidence=pending["task_confidence"],
            answer_text=pending["answer_text"],
            cited_urls=pending["cited_triples"],
            prompt_id=pending["prompt_id"],
        )
        benchmark_store.save_competitor_mentions(
            persisted.snapshot_id,
            mentions_by_snapshot[memory_snap.snapshot_id],
        )
        benchmark_store.save_evidence_artifact(
            run_id,
            "answer",
            label=f"{persisted.provider}:{persisted.task}",
            payload=json.dumps(
                {
                    "prompt": persisted.prompt_text,
                    "answer": persisted.answer_text[:4000],
                    "cited_urls": persisted.cited_urls,
                }
            ),
        )
    if audit_result and not audit_result.error:
        benchmark_store.save_evidence_artifact(
            run_id,
            "audit",
            label="site_audit",
            payload=json.dumps({"url": audit_result.url, "score": audit_result.score, "band": audit_result.band}),
        )

    avg_citation = sum(m.citation_rate for m in task_metrics) / len(task_metrics) if task_metrics else 0.0
    executive = (
        f"GEO Benchmark {score}/100 ({band}). "
        f"AI citation share ~{avg_citation:.0%} across {len(task_metrics)} task/provider slices. "
        f"{len(task_gaps)} task gap(s); commodity risk {unique_value.commodity_risk}."
    )

    return BenchmarkRunResult(
        domain=target,
        run_id=run_id,
        run_at=run_record.run_at,
        schedule=schedule,
        benchmark_score=score,
        band=band,
        breakdown=breakdown,
        task_metrics=task_metrics,
        provider_coverage=provider_coverage,
        competitor_matrix=matrix,
        page_coverage=page_coverage,
        task_gaps=task_gaps,
        unique_value=unique_value,
        citation_economics=citation_economics,
        snapshots_stored=len(pending_rows),
        evidence_artifacts=[],
        executive_summary=executive,
    )


def build_negotiation_report(result: BenchmarkRunResult) -> NegotiationReportData:
    """Package benchmark output for export."""
    strongest = []
    weakest = []
    for page in result.page_coverage:
        if page.confidence >= 0.7:
            strongest.append(page.url)
        elif page.confidence < 0.45:
            weakest.append(page.url)

    actions: list[str] = []
    for gap in result.task_gaps[:5]:
        actions.append(gap.recommendation)
    if result.unique_value.negative_signals:
        actions.append(f"Reduce commodity risk: address {result.unique_value.negative_signals[0]}")
    for row in result.competitor_matrix.rows:
        if row.target_absent_should_present:
            actions.append(f"Close competitor gap on task '{row.task}' — you are under-cited vs demand.")

    return NegotiationReportData(
        result=result,
        strongest_pages=strongest,
        weakest_pages=weakest,
        recommended_actions=actions,
    )


def load_benchmark_run_result(
    run_id: int,
    *,
    store: BenchmarkStore | None = None,
) -> BenchmarkRunResult | None:
    """Rehydrate a benchmark run from persistence for reporting."""
    benchmark_store = store or BenchmarkStore()
    run_record = benchmark_store.get_benchmark_run(run_id)
    if run_record is None:
        return None

    snapshots = benchmark_store.get_snapshots_for_run(run_id)
    mentions = benchmark_store.get_competitor_mentions_for_run(run_id)
    mentions_by_snapshot: dict[int, list] = {}
    for mention in mentions:
        mentions_by_snapshot.setdefault(mention.snapshot_id, []).append(mention)

    schedule_row = benchmark_store.get_schedule(run_record.domain)
    competitors = schedule_row.competitor_domains if schedule_row else []

    task_metrics = compute_task_citation_metrics(
        snapshots,
        mentions_by_snapshot,
        target_domain=run_record.domain,
        competitor_domains=competitors,
    )
    matrix = build_competitor_substitution_matrix(
        task_metrics,
        target_domain=run_record.domain,
        competitor_domains=competitors,
    )
    citation_economics = compute_citation_economics(
        snapshots,
        target_domain=run_record.domain,
        competitor_domains=competitors,
        mentions_by_snapshot=mentions_by_snapshot,
    )

    return BenchmarkRunResult(
        domain=run_record.domain,
        run_id=run_record.run_id,
        run_at=run_record.run_at,
        schedule=run_record.schedule,
        benchmark_score=run_record.benchmark_score,
        band=run_record.band,
        breakdown=run_record.breakdown,
        task_metrics=task_metrics,
        competitor_matrix=matrix,
        page_coverage=[],
        task_gaps=[],
        unique_value=UniqueValueAssessment(unique_value_score=run_record.breakdown.unique_value),
        citation_economics=citation_economics,
        snapshots_stored=len(snapshots),
        executive_summary=f"GEO Benchmark {run_record.benchmark_score}/100 ({run_record.band}).",
    )
