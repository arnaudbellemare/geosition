"""Formatters for domain GEO benchmark output."""

from __future__ import annotations

import csv
import io
import json
from dataclasses import asdict
from html import escape
from typing import cast

from geo_optimizer.models.results.benchmark import BenchmarkRunResult, NegotiationReportData


def build_benchmark_decision_plan(result: BenchmarkRunResult) -> dict[str, object]:
    """Return the 2026 answer-engine decision loop for a benchmark result."""
    cited_count = sum(metric.target_cited_count for metric in result.task_metrics)
    sample_size = sum(metric.sample_size for metric in result.task_metrics)
    positions = [
        metric.avg_citation_position
        for metric in result.task_metrics
        if metric.target_cited_count > 0 and metric.avg_citation_position is not None
    ]
    best_position = min(positions) if positions else None
    base: dict[str, object] = {
        "source": "arXiv:2605.25517",
        "workflow": "citation evidence -> review sources -> improve content -> retest",
        "sample_size": sample_size,
        "target_cited_count": cited_count,
        "best_citation_position": best_position,
        "rerun": "Rerun the benchmark after the fixes are shipped.",
    }
    if not sample_size:
        return {
            **base,
            "status": "unmeasured",
            "priority": "Collect usable answers",
            "next_step": "Collect usable answers before evaluating citation visibility.",
            "fix_order": ["collect_answers"],
        }
    if cited_count > 0:
        return {
            **base,
            "status": "cited",
            "priority": "Review citation evidence",
            "next_step": (
                "Your site was cited in sampled answers. Review the cited pages and repeat the same prompts to track changes."
            ),
            "fix_order": ["review_citations", "improve_relevant_pages", "retest"],
        }
    return {
        **base,
        "status": "not_cited",
        "priority": "Fix retrieval first",
        "next_step": (
            "You are not cited. Fix crawlability, indexability, ranking, and query-page match before content polish."
        ),
        "fix_order": ["crawlability", "indexability", "ranking", "query_page_match"],
    }


def format_benchmark_text(result: BenchmarkRunResult) -> str:
    """Human-readable benchmark summary."""
    plan = build_benchmark_decision_plan(result)

    def measured(value):
        return f"{value}/100" if value is not None else "Not measured"

    lines = [
        f"GEO Benchmark: {result.benchmark_score}/100 ({result.band})",
        f"Domain: {result.domain} | Run #{result.run_id} | {result.run_at}",
        "",
        result.executive_summary,
        "",
        "Score breakdown:",
        f"  Citation share:        {result.breakdown.citation_share}/100",
        f"  Task coverage:         {result.breakdown.task_coverage}/100",
        f"  Competitor position:   {measured(result.breakdown.competitor_position)}",
        f"  Unique value:          {measured(result.breakdown.unique_value)}",
        f"  Domain/backlink:       {measured(result.breakdown.domain_backlink)}",
        f"  SERP/rank:             {measured(result.breakdown.serp_rank)}",
        f"  Technical performance: {measured(result.breakdown.technical_performance)}",
        f"  Evidence coverage:     {result.breakdown.measured_weight:.0%} (model: {result.breakdown.scoring_version})",
        "",
        f"Unique Value: {measured(result.unique_value.unique_value_score)}"
        f" | Commodity risk: {result.unique_value.commodity_risk}",
        f"  {result.unique_value.summary}",
        "",
        "Citation share by task/provider:",
    ]
    for metric in result.task_metrics:
        pos = metric.avg_citation_position
        pos_label = f"#{pos}" if pos is not None else "n/a"
        lines.append(
            f"  [{metric.task} / {metric.provider}] "
            f"{metric.target_cited_count}/{metric.sample_size} cited "
            f"({metric.citation_rate:.0%}), avg position {pos_label}"
        )
        for domain, rate in metric.competitor_mention_rates.items():
            lines.append(f"    competitor {domain}: {rate:.0%}")

    if result.competitor_matrix.rows:
        lines.extend(["", "Competitor substitution matrix:"])
        header_domains = [result.competitor_matrix.target_domain] + result.competitor_matrix.competitor_domains
        lines.append("  Task".ljust(22) + "".join(domain[:14].ljust(16) for domain in header_domains))
        for row in result.competitor_matrix.rows:
            cells = [f"{row.target_rate:.0%}"] + [f"{row.competitor_rates.get(d, 0):.0%}" for d in header_domains[1:]]
            lines.append("  " + row.task[:20].ljust(20) + "".join(cell.ljust(16) for cell in cells))

    if result.task_gaps:
        lines.extend(["", "Task gaps:"])
        for gap in result.task_gaps:
            lines.append(
                f"  - {gap.task}: demand {gap.ai_demand_rate:.0%}, coverage {gap.page_coverage_score:.0%} ({gap.gap_severity})"
            )
            lines.append(f"    {gap.recommendation}")

    econ = result.citation_economics
    if econ.sample_size:
        lines.extend(
            [
                "",
                "Citation economics:",
                f"  Selection premium: {econ.selection_premium:.2f}x ({econ.selection_label.upper()})",
                f"    {econ.selection_summary}",
                f"  Value concentration: {econ.value_concentration:.2f}x ({econ.value_label.upper()})",
                f"    {econ.value_summary}",
                f"  Uniqueness: {econ.uniqueness_index:.2f}x ({econ.uniqueness_label.upper()})",
                f"    {econ.uniqueness_summary}",
            ]
        )
        if econ.most_cited_pages:
            lines.extend(["", "Most cited pages:"])
            for rank, page in enumerate(econ.most_cited_pages[:10], start=1):
                page_position = f", avg position {page.avg_position}" if page.avg_position is not None else ""
                lines.append(f"  {rank}. {page.url} ({page.citation_count} citations{page_position})")

    fix_order = cast(list[str], plan["fix_order"])
    lines.extend(
        [
            "",
            "Benchmark decision plan:",
            f"  Status: {plan['status']}",
            f"  Priority: {plan['priority']}",
            f"  Next: {plan['next_step']}",
            f"  Fix order: {', '.join(str(item) for item in fix_order)}",
            f"  Then: {plan['rerun']}",
            f"  Source: {plan['source']}",
        ]
    )

    return "\n".join(lines)


def format_benchmark_json(result: BenchmarkRunResult) -> str:
    """JSON serialization of benchmark result."""
    payload = asdict(result)
    payload["decision_plan"] = build_benchmark_decision_plan(result)
    return json.dumps(payload, indent=2, default=str)


def format_negotiation_csv(report: NegotiationReportData) -> str:
    """CSV export for negotiation workflows."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    result = report.result
    writer.writerow(["section", "key", "value"])
    writer.writerow(["summary", "benchmark_score", result.benchmark_score])
    writer.writerow(["summary", "band", result.band])
    writer.writerow(["summary", "domain", result.domain])
    writer.writerow(["summary", "executive_summary", result.executive_summary])
    for metric in result.task_metrics:
        writer.writerow(
            [
                "citation",
                f"{metric.task}/{metric.provider}",
                f"rate={metric.citation_rate}; cited={metric.target_cited_count}/{metric.sample_size}",
            ]
        )
    for row in result.competitor_matrix.rows:
        writer.writerow(["matrix", row.task, f"target={row.target_rate}; competitors={row.competitor_rates}"])
    for gap in result.task_gaps:
        writer.writerow(["gap", gap.task, gap.recommendation])
    for action in report.recommended_actions:
        writer.writerow(["action", "", action])
    return buffer.getvalue()


def format_negotiation_html(report: NegotiationReportData) -> str:
    """Self-contained HTML negotiation report."""
    result = report.result

    def _h(value: object) -> str:
        return escape(str(value), quote=True)

    matrix_rows = ""
    for row in result.competitor_matrix.rows:
        comp_cells = "".join(
            f"<td>{row.competitor_rates.get(domain, 0):.0%}</td>"
            for domain in result.competitor_matrix.competitor_domains
        )
        matrix_rows += f"<tr><td>{_h(row.task)}</td><td>{row.target_rate:.0%}</td>{comp_cells}</tr>"
    comp_headers = "".join(f"<th>{_h(domain)}</th>" for domain in result.competitor_matrix.competitor_domains)
    actions = "".join(f"<li>{_h(item)}</li>" for item in report.recommended_actions)
    gaps = "".join(f"<li><strong>{_h(g.task)}</strong>: {_h(g.recommendation)}</li>" for g in result.task_gaps)
    strongest = ", ".join(_h(page) for page in report.strongest_pages) or "n/a"
    weakest = ", ".join(_h(page) for page in report.weakest_pages) or "n/a"
    unique_score = result.unique_value.unique_value_score
    unique_label = f"{unique_score}/100" if unique_score is not None else "Not measured"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>GEO Benchmark Report — {_h(result.domain)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 2rem; color: #111; }}
    h1 {{ font-size: 1.75rem; }}
    .score {{ font-size: 2.5rem; font-weight: 700; }}
    table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
    th, td {{ border: 1px solid #ddd; padding: 0.5rem; text-align: left; }}
    th {{ background: #f5f5f5; }}
  </style>
</head>
<body>
  <h1>GEO Benchmark Negotiation Report</h1>
  <p class="score">{result.benchmark_score}/100 — {_h(result.band)}</p>
  <p><strong>Domain:</strong> {_h(result.domain)} | <strong>Run:</strong> #{result.run_id} | {_h(result.run_at)}</p>
  <p>{_h(result.executive_summary)}</p>
  <h2>Executive summary</h2>
  <ul>
    <li>Citation share component: {result.breakdown.citation_share}/100</li>
    <li>Task coverage: {result.breakdown.task_coverage}/100</li>
    <li>Unique value: {_h(unique_label)} ({_h(result.unique_value.commodity_risk)} commodity risk)</li>
  </ul>
  <h2>Competitor matrix</h2>
  <table>
    <tr><th>Task</th><th>{_h(result.domain)}</th>{comp_headers}</tr>
    {matrix_rows}
  </table>
  <h2>Task gaps</h2>
  <ul>{gaps or "<li>No critical gaps detected.</li>"}</ul>
  <h2>Recommended actions</h2>
  <ul>{actions or "<li>Maintain citation momentum across high-intent tasks.</li>"}</ul>
  <h2>Strongest / weakest pages</h2>
  <p><strong>Strongest:</strong> {strongest}</p>
  <p><strong>Weakest:</strong> {weakest}</p>
</body>
</html>"""
