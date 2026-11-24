"""Text and self-contained HTML presentation for memory/search experiments."""

from __future__ import annotations

import json
from dataclasses import asdict
from html import escape
from pathlib import Path

from geo_optimizer.models.results.experiment import MemorySearchReport


def _rate(value: float | None) -> str:
    return "Unavailable" if value is None else f"{value:.1f}%"


def format_memory_search_text(report: MemorySearchReport) -> str:
    """Render condition-specific rates with coverage and explicit metric names."""
    lines = [
        "Memory vs search",
        f"Generation requests made: {report.generation_requests_made} (requires explicit request evidence)",
        f"Attempt records: {report.total_attempts}; unclassified: {report.unclassified_attempts}; missing: {report.missing_attempts}",
        f"Statuses: {json.dumps(report.status_counts, sort_keys=True)}; errors: {json.dumps(report.error_counts, sort_keys=True)}",
        f"Observed tokens: {report.observed_tokens}; observed search queries: {report.observed_search_queries}; "
        f"attempts without token usage: {report.usage_unknown_attempts}",
    ]
    for cohort in report.slices:
        lines.append(
            f"{cohort.brand} · {cohort.provider} · {cohort.surface} · {cohort.returned_model or 'unknown version'}"
        )
        for metric in cohort.conditions:
            lines.append(
                f"  {metric.condition}: mention {_rate(metric.mention_rate)} ({metric.mentioned_answers} answers), "
                f"explicit recommendation {_rate(metric.recommendation_rate)}, "
                f"owned-domain citation {_rate(metric.owned_domain_citation_rate)} "
                f"({metric.valid_answers}/{metric.attempts} valid answers; {metric.prompt_count} prompts)"
            )
            if metric.condition == "search_enabled":
                lines.append(
                    f"  Observed search use {_rate(metric.search_use_rate)} "
                    f"({metric.search_observed_answers} known; {metric.search_unknown_answers} unknown); "
                    f"search-backed brand references {_rate(metric.search_backed_rate)}"
                )
        lines.append(f"  Unmatched valid answers: {cohort.unmatched_valid_answers}")
        for delta in cohort.paired_differences:
            value = "unavailable" if delta.delta_pp is None else f"{delta.delta_pp:+.1f} pp"
            lines.append(f"  Paired {delta.metric}: {value} ({delta.pair_count} pairs, {delta.prompt_count} prompts)")
    lines.extend(report.notes)
    return "\n".join(lines)


def render_memory_search_html(report: MemorySearchReport) -> str:
    """Escape all provider text and keep evidence visible without remote assets."""
    sections = []
    for cohort in report.slices:
        rows = []
        for metric in cohort.conditions:
            rows.append(
                "<tr>"
                + "".join(
                    f"<td>{escape(str(value))}</td>"
                    for value in (
                        metric.condition,
                        f"{metric.valid_answers}/{metric.attempts}",
                        metric.prompt_count,
                        _rate(metric.mention_rate),
                        _rate(metric.recommendation_rate),
                        _rate(metric.owned_domain_citation_rate),
                        _rate(metric.search_backed_rate),
                        _rate(metric.search_use_rate),
                        metric.search_unknown_answers,
                    )
                )
                + "</tr>"
            )
        sections.append(
            f"<section><h2>{escape(cohort.brand)}</h2>"
            f"<p>{escape(cohort.provider)} · {escape(cohort.surface)} · "
            f"{escape(cohort.returned_model or 'Unknown returned model version')}</p>"
            "<div class='table'><table><thead><tr><th>Condition</th><th>Valid/attempts</th><th>Prompts</th>"
            "<th>Mention</th><th>Explicit recommendation</th><th>Owned-domain citation</th>"
            "<th>Search-backed reference</th><th>Observed search use</th><th>Search unknown</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table></div>"
            f"<p>Unmatched valid answers: {cohort.unmatched_valid_answers}</p>"
            f"<details><summary>Paired differences and uncertainty</summary><pre>"
            f"{escape(json.dumps([asdict(d) for d in cohort.paired_differences], indent=2))}</pre></details></section>"
        )
    evidence = []
    for row in report.evidence:
        evidence.append(
            f"<details><summary>{escape(row['prompt_id'])} · {escape(row['condition'])} · "
            f"trial {row['repetition']} · {escape(row['status'])}</summary>"
            f"<p>{escape(row['query_text'])}</p><pre>{escape(row['answer_text'])}</pre>"
            f"<pre>{escape(json.dumps({k: v for k, v in row.items() if k != 'answer_text'}, indent=2, ensure_ascii=False))}</pre>"
            "</details>"
        )
    notes = "".join(f"<li>{escape(note)}</li>" for note in report.notes)
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'><title>Memory vs search — GEOSITION AI</title>"
        "<style>body{font:16px/1.6 system-ui,sans-serif;max-width:1120px;margin:40px auto;padding:0 24px;color:#20252b}"
        "h1,h2{line-height:1.2}section{margin:32px 0}.table{overflow-x:auto}table{border-collapse:collapse;width:100%}"
        "th,td{padding:10px;text-align:left;border-bottom:1px solid #d8dce0}th{background:#f2f4f5}"
        "pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f4f5;padding:16px}"
        "summary{cursor:pointer;padding:12px 0}summary:focus-visible{outline:2px solid #2456a6}</style></head><body>"
        "<h1>Memory vs search</h1><p>Unassisted brand recall and visibility when live search is available.</p>"
        f"<p>Generation requests made: {report.generation_requests_made} (explicit request evidence)</p>"
        f"<p>Attempt records: {report.total_attempts} · Unclassified: {report.unclassified_attempts} · "
        f"Missing: {report.missing_attempts}</p><p>Statuses: {escape(json.dumps(report.status_counts))} · "
        f"Errors: {escape(json.dumps(report.error_counts))}</p><p>Observed tokens: {report.observed_tokens} · "
        f"Observed search queries: {report.observed_search_queries} · "
        f"Attempts without token usage: {report.usage_unknown_attempts}</p><ul>{notes}</ul>{''.join(sections)}"
        f"<h2>Answer evidence</h2>{''.join(evidence)}</body></html>"
    )


def write_memory_search_report(report: MemorySearchReport, output_dir: Path) -> tuple[Path, Path]:
    """Write machine-readable results and a standalone evidence report."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path, html_path = output_dir / "memory-search.json", output_dir / "memory-search.html"
    json_path.write_text(json.dumps(asdict(report), indent=2, ensure_ascii=False), encoding="utf-8")
    html_path.write_text(render_memory_search_html(report), encoding="utf-8")
    return json_path, html_path
