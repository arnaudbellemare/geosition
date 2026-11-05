"""CLI command: geo links."""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

import click

from geo_optimizer.core.link_graph import analyze_link_graph
from geo_optimizer.utils.validators import validate_public_url


@click.command(name="links")
@click.option("--sitemap", required=True, help="Sitemap URL to analyze")
@click.option("--max-pages", default=30, show_default=True, help="Maximum pages to fetch from sitemap")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
@click.option("--output", "output_file", default=None, help="Optional output file path")
def links_cmd(sitemap: str, max_pages: int, output_format: str, output_file: str | None) -> None:
    """Analyze internal link graph and orphan pages from a sitemap."""
    ok, err = validate_public_url(sitemap)
    if not ok:
        click.echo(f"❌ Invalid sitemap URL: {err}", err=True)
        sys.exit(1)

    result = analyze_link_graph(sitemap_url=sitemap, max_pages=max_pages)
    payload = (
        json.dumps(asdict(result), indent=2, ensure_ascii=False) if output_format == "json" else _format_text(result)
    )

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(payload + ("\n" if not payload.endswith("\n") else ""))
        click.echo(f"✅ Report written to: {output_file}")
    else:
        click.echo(payload)

    if result.error:
        sys.exit(1)


def _format_text(result) -> str:
    lines = [
        "🕸️ INTERNAL LINK GRAPH",
        "=" * 64,
        f"Sitemap: {result.sitemap}",
        f"Pages discovered: {result.pages_discovered}",
        f"Pages analyzed: {result.pages_analyzed}",
        f"Internal edges: {result.internal_edges}",
        f"Orphan pages: {len(result.orphan_pages)}",
        "",
    ]

    if result.orphan_pages:
        lines.append("Top orphan pages:")
        lines.extend([f"  - {url}" for url in result.orphan_pages[:20]])
        lines.append("")

    if result.weakly_linked_pages:
        lines.append("Weakly linked pages (<=1 outgoing links):")
        lines.extend([f"  - {url}" for url in result.weakly_linked_pages[:20]])
        lines.append("")

    lines.append("Recommendations:")
    lines.extend([f"  - {item}" for item in result.recommendations] or ["  - none"])

    if result.error:
        lines.extend(["", f"❌ Error: {result.error}"])
    return "\n".join(lines)
