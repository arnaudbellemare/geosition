"""CLI command: geo orchestrate."""

from __future__ import annotations

import json
from dataclasses import asdict

import click

from geo_optimizer.core.orchestrator import run_orchestration
from geo_optimizer.utils.seo_program_note import REPO_SEO_PROGRAM_FOOTER
from geo_optimizer.utils.validators import validate_public_url


@click.command(name="orchestrate")
@click.option("--url", required=True, help="Target URL")
@click.option("--with-marketing/--no-marketing", default=True, show_default=True)
@click.option("--with-content/--no-content", default=True, show_default=True)
@click.option("--sitemap", default=None, help="Optional sitemap URL to run link graph analysis")
@click.option("--max-pages", default=30, show_default=True, help="Max sitemap pages for link analysis")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def orchestrate_cmd(
    url: str,
    with_marketing: bool,
    with_content: bool,
    sitemap: str | None,
    max_pages: int,
    output_format: str,
) -> None:
    """Run multiple SEO/GEO workflows in one orchestrated execution."""
    ok, err = validate_public_url(url)
    if not ok:
        raise click.UsageError(f"Invalid URL: {err}")
    if sitemap:
        ok, err = validate_public_url(sitemap)
        if not ok:
            raise click.UsageError(f"Invalid sitemap URL: {err}")

    result = run_orchestration(
        url=url,
        run_marketing=with_marketing,
        run_content=with_content,
        run_links=bool(sitemap),
        sitemap=sitemap,
        max_pages=max_pages,
    )

    if output_format == "json":
        payload = asdict(result)
        payload["seo_program_note"] = REPO_SEO_PROGRAM_FOOTER
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        lines = [
            "🧩 ORCHESTRATION REPORT",
            "=" * 64,
            f"Target: {result.target}",
            f"GEO score: {result.geo_score if result.geo_score is not None else 'n/a'}",
            f"Marketing score: {result.marketing_score if result.marketing_score is not None else 'n/a'}",
            f"Orphan pages: {len(result.orphan_pages)}",
            "",
            "Jobs:",
        ]
        for job in result.jobs:
            lines.append(f"  - {job.name}: {job.status} — {job.summary}")
        if result.content_recommendations:
            lines.extend(["", "Top content recommendations:"])
            lines.extend([f"  - {r}" for r in result.content_recommendations[:6]])
        if result.errors:
            lines.extend(["", "Errors:"])
            lines.extend([f"  - {e}" for e in result.errors])
        lines.extend(["", REPO_SEO_PROGRAM_FOOTER])
        click.echo("\n".join(lines))
