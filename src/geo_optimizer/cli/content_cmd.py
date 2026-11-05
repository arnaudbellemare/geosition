"""CLI command: geo content."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

import click

from geo_optimizer.core.content_workflow import analyze_content_workflow_file, analyze_content_workflow_url
from geo_optimizer.utils.validators import validate_public_url, validate_safe_path


@click.command(name="content")
@click.option("--url", default=None, help="Public URL to analyze")
@click.option("--file", "file_path", default=None, help="Local HTML file to analyze")
@click.option("--keywords", default="", help="Comma-separated target keywords or entities")
@click.option("--top-terms", default=15, show_default=True, help="How many top terms to show")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
@click.option("--output", "output_file", default=None, help="Optional output file path")
def content_cmd(
    url: str | None,
    file_path: str | None,
    keywords: str,
    top_terms: int,
    output_format: str,
    output_file: str | None,
) -> None:
    """Run keyword + E-E-A-T + entity content workflow audit."""
    if bool(url) == bool(file_path):
        raise click.UsageError("Use exactly one source: '--url' or '--file'")

    targets = [k.strip() for k in keywords.split(",") if k.strip()]

    if url:
        ok, err = validate_public_url(url)
        if not ok:
            click.echo(f"❌ Invalid URL: {err}", err=True)
            sys.exit(1)
        result = analyze_content_workflow_url(url, target_keywords=targets, top_terms=top_terms)
    else:
        ok, err = validate_safe_path(file_path or "", allowed_extensions={".html", ".htm"}, must_exist=True)
        if not ok:
            click.echo(f"❌ Invalid file path: {err}", err=True)
            sys.exit(1)
        result = analyze_content_workflow_file(file_path or "", target_keywords=targets, top_terms=top_terms)

    if output_format == "json":
        payload = json.dumps(asdict(result), indent=2, ensure_ascii=False)
    else:
        payload = _format_text(result)

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(payload)
        click.echo(f"✅ Report written to: {output_file}")
    else:
        click.echo(payload)

    if result.error:
        sys.exit(1)


def _format_text(result) -> str:
    lines = [
        "🧭 CONTENT WORKFLOW AUDIT",
        "=" * 64,
        f"Source: {result.source}",
        f"Words analyzed: {result.analyzed_words}",
        "",
        "Top terms:",
    ]

    if result.top_terms:
        for item in result.top_terms:
            lines.append(f"  - {item.keyword}: {item.count} ({item.density_pct}%)")
    else:
        lines.append("  - none")

    if result.target_keywords:
        lines.extend(["", "Target keyword density:"])
        for item in result.target_keywords:
            lines.append(f"  - {item.keyword}: {item.count} ({item.density_pct}%)")

    lines.extend(
        [
            "",
            "Signal scores:",
            f"  - Keyword stuffing: {result.keyword_stuffing.score}/{result.keyword_stuffing.max_score}",
            f"  - E-E-A-T signals: {result.eeat_signals.score}/{result.eeat_signals.max_score}",
            f"  - Anchor text quality: {result.anchor_text_quality.score}/{result.anchor_text_quality.max_score}",
            f"  - Entity resolution: {result.entity_resolution.score}/{result.entity_resolution.max_score}",
            f"  - KG density: {result.kg_density.score}/{result.kg_density.max_score}",
            "",
            "Recommendations:",
        ]
    )
    for rec in result.recommendations:
        lines.append(f"  - {rec}")

    if result.error:
        lines.extend(["", f"❌ Error: {result.error}"])

    return "\n".join(lines)
