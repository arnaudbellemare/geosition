"""Weekly evidence report generation for platform and local GEOSITION runs."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from geo_optimizer.core.audit import run_full_audit
from geo_optimizer.core.benchmark.runner import run_domain_benchmark
from geo_optimizer.core.benchmark.store import BenchmarkStore
from geo_optimizer.core.collection.normalize import batch_from_dict, batch_to_benchmark_answers
from geo_optimizer.core.log_analyzer import analyze_log_file
from geo_optimizer.core.monitor import normalize_monitor_domain
from geo_optimizer.core.seo_intelligence import run_lighthouse_audit
from geo_optimizer.saas.models import WeeklyEvidenceMetric


def build_weekly_evidence_report(
    domain: str,
    *,
    answers_payload: dict[str, Any] | list[Any] | None = None,
    competitors: list[str] | None = None,
    log_file: str | Path | None = None,
    lighthouse_provider: str = "pagespeed",
    benchmark_store: BenchmarkStore | None = None,
    generated_at: str = "",
    period_days: int = 7,
) -> dict[str, Any]:
    """Collect audit, optional benchmark, Lighthouse, and crawler evidence."""
    normalized_domain = _normalize_domain(domain)
    url = normalize_monitor_domain(normalized_domain)
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    period_end = generated
    period_start = (datetime.fromisoformat(generated.replace("Z", "+00:00")) - timedelta(days=period_days)).isoformat()

    metrics: list[WeeklyEvidenceMetric] = []
    sources: dict[str, Any] = {}
    action_items: list[str] = []

    audit = run_full_audit(url, use_cache=False)
    metrics.append(
        WeeklyEvidenceMetric(
            key="geo_audit_score",
            label="GEO audit score",
            value=f"{int(audit.score)}/100",
            unit="score",
            status=_status_for_score(int(audit.score)),
            evidence_ref="audit",
        )
    )
    metrics.append(
        WeeklyEvidenceMetric(
            key="audit_recommendations",
            label="Open audit recommendations",
            value=str(len(getattr(audit, "recommendations", []) or [])),
            unit="count",
            status="good" if not getattr(audit, "recommendations", []) else "watch",
            evidence_ref="audit",
        )
    )
    sources["audit"] = {
        "url": getattr(audit, "url", url),
        "score": int(getattr(audit, "score", 0) or 0),
        "band": getattr(audit, "band", ""),
        "error": getattr(audit, "error", None),
        "score_breakdown": getattr(audit, "score_breakdown", {}) or {},
        "recommendations": list((getattr(audit, "recommendations", []) or [])[:12]),
    }
    action_items.extend(str(item) for item in (getattr(audit, "recommendations", []) or [])[:5])

    if answers_payload:
        benchmark = _run_optional_benchmark(
            normalized_domain,
            url=url,
            answers_payload=answers_payload,
            competitors=competitors or [],
            benchmark_store=benchmark_store,
        )
        sources["benchmark"] = benchmark
        if benchmark.get("checked"):
            metrics.append(
                WeeklyEvidenceMetric(
                    key="benchmark_score",
                    label="AI benchmark score",
                    value=f"{int(benchmark.get('score', 0))}/100",
                    unit="score",
                    status=_status_for_score(int(benchmark.get("score", 0) or 0)),
                    evidence_ref="benchmark",
                )
            )
            metrics.append(
                WeeklyEvidenceMetric(
                    key="citation_share",
                    label="Citation share score",
                    value=f"{int(benchmark.get('citation_share', 0))}%",
                    unit="percent",
                    status=_status_for_score(int(benchmark.get("citation_share", 0) or 0)),
                    evidence_ref="benchmark",
                )
            )
            action_items.extend(str(item.get("recommendation", "")) for item in benchmark.get("task_gaps", [])[:5])
    else:
        sources["benchmark"] = {"checked": False, "reason": "answers_payload_not_provided"}

    if lighthouse_provider and lighthouse_provider != "none":
        lighthouse = run_lighthouse_audit(url, provider=lighthouse_provider)
        sources["lighthouse"] = {
            "checked": bool(lighthouse.checked),
            "provider": lighthouse.provider,
            "performance_score": lighthouse.performance_score,
            "accessibility_score": lighthouse.accessibility_score,
            "best_practices_score": lighthouse.best_practices_score,
            "seo_score": lighthouse.seo_score,
            "page_load_ms": lighthouse.page_load_ms,
            "warnings": lighthouse.warnings,
        }
        for key, label, value in (
            ("lighthouse_performance", "Lighthouse performance", lighthouse.performance_score),
            ("lighthouse_accessibility", "Lighthouse accessibility", lighthouse.accessibility_score),
            ("lighthouse_seo", "Lighthouse SEO", lighthouse.seo_score),
        ):
            if lighthouse.checked:
                metrics.append(
                    WeeklyEvidenceMetric(
                        key=key,
                        label=label,
                        value=f"{int(value)}/100",
                        unit="score",
                        status=_status_for_score(int(value)),
                        evidence_ref="lighthouse",
                    )
                )
    else:
        sources["lighthouse"] = {"checked": False, "reason": "disabled"}

    if log_file:
        log_result = analyze_log_file(log_file)
        bot_visits = sum(int(bot.visits) for bot in log_result.bots)
        metrics.append(
            WeeklyEvidenceMetric(
                key="ai_crawler_visits",
                label="AI crawler visits",
                value=str(bot_visits),
                unit="visits",
                status="good" if bot_visits else "watch",
                evidence_ref="crawler_log",
            )
        )
        metrics.append(
            WeeklyEvidenceMetric(
                key="ai_crawler_unique_bots",
                label="AI crawler agents",
                value=str(len(log_result.bots)),
                unit="bots",
                status="good" if log_result.bots else "watch",
                evidence_ref="crawler_log",
            )
        )
        sources["crawler_log"] = {
            "checked": bool(log_result.checked),
            "log_file": str(log_result.log_file),
            "total_lines": int(log_result.total_lines),
            "bots": [asdict(bot) for bot in log_result.bots],
            "top_pages": [asdict(page) for page in log_result.top_pages[:10]],
        }
    else:
        sources["crawler_log"] = {"checked": False, "reason": "log_file_not_provided"}

    action_plan = _build_action_plan(action_items, sources)
    score = _weekly_score(metrics)
    summary = _summary(normalized_domain, score, metrics, sources)
    return {
        "schema_version": "weekly_evidence.v1",
        "domain": normalized_domain,
        "url": url,
        "period_start": period_start,
        "period_end": period_end,
        "generated_at": generated,
        "score": score,
        "band": _band(score),
        "summary": summary,
        "metrics": [asdict(metric) for metric in metrics],
        "sources": sources,
        "action_plan": action_plan,
    }


def render_weekly_evidence_html(report: dict[str, Any]) -> str:
    """Render a portable, agent-ready weekly report artifact."""
    metrics_html = "\n".join(
        "<tr>"
        f"<td>{escape(str(metric.get('label', metric.get('key', 'Metric'))))}</td>"
        f"<td><strong>{escape(str(metric.get('value', '')))}</strong></td>"
        f"<td>{escape(str(metric.get('status', 'unknown')))}</td>"
        f"<td>{escape(str(metric.get('evidence_ref', '')))}</td>"
        "</tr>"
        for metric in report.get("metrics", [])
    )
    actions = report.get("action_plan", {}).get("actions", [])
    actions_html = "\n".join(f"<li>{escape(str(action))}</li>" for action in actions)
    sources = report.get("sources", {})
    source_html = "\n".join(
        f"<li><strong>{escape(str(name))}</strong>: {escape(_source_status(payload))}</li>"
        for name, payload in sources.items()
    )
    score = int(report.get("score", 0) or 0)
    color = "#1f8a4c" if score >= 86 else "#2563eb" if score >= 68 else "#b54708" if score >= 36 else "#b42318"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GEOSITION Weekly Evidence · {escape(str(report.get("domain", "")))}</title>
  <style>
    body {{ margin: 0; font-family: Inter, Arial, sans-serif; color: #191a1f; background: #f5f4ef; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 40px 20px 64px; }}
    header {{ border-bottom: 1px solid #d7d3c8; padding-bottom: 24px; margin-bottom: 24px; }}
    .eyebrow {{ font-size: 12px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; color: #696a70; }}
    h1 {{ font-size: 42px; line-height: 1.05; margin: 8px 0; }}
    .summary {{ font-size: 18px; line-height: 1.55; max-width: 760px; }}
    .score {{ display: inline-flex; align-items: baseline; gap: 8px; margin-top: 16px; color: {color}; }}
    .score strong {{ font-size: 56px; line-height: 1; }}
    section {{ margin-top: 28px; }}
    table {{ width: 100%; border-collapse: collapse; background: #fffdf7; border: 1px solid #d7d3c8; }}
    th, td {{ text-align: left; border-bottom: 1px solid #e5e0d5; padding: 12px 14px; vertical-align: top; }}
    th {{ font-size: 12px; text-transform: uppercase; letter-spacing: .08em; color: #696a70; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
    .panel {{ border: 1px solid #d7d3c8; background: #fffdf7; padding: 18px; }}
    li {{ margin: 0 0 10px; line-height: 1.45; }}
    code {{ background: #ebe6da; padding: 2px 5px; }}
    @media (max-width: 760px) {{ .grid {{ grid-template-columns: 1fr; }} h1 {{ font-size: 32px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <div class="eyebrow">GEOSITION weekly company evidence</div>
      <h1>{escape(str(report.get("domain", "")))}</h1>
      <p class="summary">{escape(str(report.get("summary", "")))}</p>
      <div class="score"><strong>{score}</strong><span>/100 · {escape(str(report.get("band", "")))}</span></div>
      <p><code>{escape(str(report.get("period_start", "")))}</code> to <code>{escape(str(report.get("period_end", "")))}</code></p>
    </header>
    <section>
      <h2>Metrics</h2>
      <table>
        <thead><tr><th>Metric</th><th>Value</th><th>Status</th><th>Evidence</th></tr></thead>
        <tbody>{metrics_html}</tbody>
      </table>
    </section>
    <section class="grid">
      <div class="panel">
        <h2>Agent Action Plan</h2>
        <ol>{actions_html}</ol>
      </div>
      <div class="panel">
        <h2>Evidence Sources</h2>
        <ul>{source_html}</ul>
      </div>
    </section>
  </main>
</body>
</html>
"""


def metric_objects(metrics: list[dict[str, Any]]) -> list[WeeklyEvidenceMetric]:
    """Convert JSON-ready metric dictionaries back to dataclasses for stores."""
    return [
        WeeklyEvidenceMetric(
            key=str(item.get("key", "")),
            label=str(item.get("label", "")),
            value=str(item.get("value", "")),
            previous_value=str(item.get("previous_value", "")),
            delta=str(item.get("delta", "")),
            unit=str(item.get("unit", "")),
            status=str(item.get("status", "unknown")),
            evidence_ref=str(item.get("evidence_ref", "")),
        )
        for item in metrics
        if isinstance(item, dict)
    ]


def _run_optional_benchmark(
    domain: str,
    *,
    url: str,
    answers_payload: dict[str, Any] | list[Any],
    competitors: list[str],
    benchmark_store: BenchmarkStore | None,
) -> dict[str, Any]:
    payload = {"answers": answers_payload} if isinstance(answers_payload, list) else answers_payload
    batch = batch_from_dict(payload)
    answer_rows = batch_to_benchmark_answers(batch)
    if not answer_rows:
        return {"checked": False, "reason": "no_valid_answers"}
    result = run_domain_benchmark(
        domain,
        competitors=competitors,
        answers=answer_rows,
        audit_url=url,
        use_cache=False,
        store=benchmark_store,
    )
    return {
        "checked": True,
        "run_id": result.run_id,
        "score": int(result.benchmark_score),
        "band": result.band,
        "citation_share": int(result.breakdown.citation_share),
        "task_coverage": int(result.breakdown.task_coverage),
        "competitor_position": result.breakdown.competitor_position,
        "provider_coverage": dict(result.provider_coverage),
        "task_gaps": [asdict(gap) for gap in result.task_gaps[:10]],
        "executive_summary": result.executive_summary,
    }


def _normalize_domain(target: str) -> str:
    parsed = urlparse(target if "://" in target else normalize_monitor_domain(target))
    host = parsed.netloc or parsed.path
    return host.lower().split("@")[-1].split(":")[0].strip().strip("/")


def _status_for_score(score: int) -> str:
    if score >= 86:
        return "excellent"
    if score >= 68:
        return "good"
    if score >= 36:
        return "watch"
    return "critical"


def _band(score: int) -> str:
    if score >= 86:
        return "excellent"
    if score >= 68:
        return "good"
    if score >= 36:
        return "foundation"
    return "critical"


def _weekly_score(metrics: list[WeeklyEvidenceMetric]) -> int:
    score_values: list[int] = []
    for metric in metrics:
        if metric.unit == "score" and metric.value.endswith("/100"):
            try:
                score_values.append(int(metric.value.split("/", 1)[0]))
            except ValueError:
                continue
        if metric.key == "citation_share" and metric.value.endswith("%"):
            try:
                score_values.append(int(metric.value.rstrip("%")))
            except ValueError:
                continue
    if not score_values:
        return 0
    return round(sum(score_values) / len(score_values))


def _build_action_plan(action_items: list[str], sources: dict[str, Any]) -> dict[str, Any]:
    actions = [item.strip() for item in action_items if item and item.strip()]
    if not sources.get("benchmark", {}).get("checked"):
        actions.append("Run the same prompt answer set against the target and competitors to measure citation share.")
    if not sources.get("crawler_log", {}).get("checked"):
        actions.append("Import server logs weekly to prove AI crawler access and discover crawl gaps.")
    if not sources.get("lighthouse", {}).get("checked"):
        actions.append("Enable Lighthouse collection to track Core Web Vitals, accessibility, and SEO health.")
    deduped = list(dict.fromkeys(actions))[:8]
    return {
        "priority": deduped[0] if deduped else "Keep weekly monitoring active.",
        "actions": deduped or ["Keep weekly monitoring active and compare report deltas over time."],
        "cadence": "weekly",
    }


def _summary(domain: str, score: int, metrics: list[WeeklyEvidenceMetric], sources: dict[str, Any]) -> str:
    checked = [name for name, payload in sources.items() if isinstance(payload, dict) and payload.get("checked")]
    source_copy = ", ".join(checked) if checked else "audit only"
    risk_count = sum(1 for metric in metrics if metric.status in {"watch", "critical"})
    return (
        f"{domain} is at {score}/100 for this weekly evidence run using {source_copy}. "
        f"{risk_count} metric(s) need attention before the next benchmark window."
    )


def _source_status(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "available"
    if payload.get("checked"):
        return "checked"
    return str(payload.get("reason") or payload.get("warnings") or "not checked")
