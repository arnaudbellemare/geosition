"""CLI command group for classic SEO intelligence."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from geo_optimizer.core.seo_intelligence import (
    RankTracker,
    analyze_backlinks,
    analyze_domain,
    research_keywords,
    run_lighthouse_audit,
)


@click.group(name="seo")
def seo_cmd() -> None:
    """Classic SEO intelligence: keywords, domains, backlinks, ranks, Lighthouse."""


@seo_cmd.command(name="keywords")
@click.option("--seed", required=True, help="Seed keyword or topic")
@click.option("--limit", default=20, show_default=True, type=int, help="Maximum keyword ideas")
@click.option("--save-list", default=None, help="Save metrics to a named local keyword list")
@click.option("--csv", "csv_path", default=None, help="Export metrics to a CSV path")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def keywords_cmd(seed: str, limit: int, save_list: str | None, csv_path: str | None, output_format: str) -> None:
    """Research keyword metrics: volume, CPC, competition, difficulty, intent, trend."""
    result = research_keywords(seed=seed, limit=limit, save_list=save_list, csv_path=csv_path)
    if output_format == "json":
        click.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return
    lines = [
        "🔑 KEYWORD RESEARCH",
        "=" * 64,
        f"Seed: {result.seed}",
        f"Provider: {result.provider}",
    ]
    if result.saved_list_path:
        lines.append(f"Saved list: {result.saved_list_path}")
    if result.csv_path:
        lines.append(f"CSV export: {result.csv_path}")
    lines.extend(["", "Keyword | Volume | CPC | Competition | Difficulty | Intent"])
    for item in result.metrics:
        lines.append(
            f"{item.keyword} | {item.volume} | ${item.cpc:.2f} | {item.competition:.2f} | "
            f"{item.difficulty} | {item.intent}"
        )
    if result.warnings:
        lines.extend(["", *[f"Warning: {warning}" for warning in result.warnings]])
    click.echo("\n".join(lines))


@seo_cmd.command(name="domain")
@click.option("--url", required=True, help="Domain or URL to profile")
@click.option("--competitor", "competitors", multiple=True, help="Competitor domain/URL for keyword-gap analysis")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def domain_cmd(url: str, competitors: tuple[str, ...], output_format: str) -> None:
    """Profile authority, traffic, top pages, ranked keywords, competitors, and gaps."""
    target = _normalize_url(url)
    result = analyze_domain(target, competitors=[_normalize_url(item) for item in competitors])
    if output_format == "json":
        click.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return
    lines = [
        "🏛 DOMAIN ANALYSIS",
        "=" * 64,
        f"Domain: {result.domain}",
        f"Provider: {result.provider}",
        f"Authority: {result.authority}/100",
        f"Estimated traffic: {result.estimated_traffic}",
        "",
        "Top pages:",
        *[
            f"  - {page.url} ({page.estimated_traffic} visits est., {page.keyword_count} keywords)"
            for page in result.top_pages
        ],
        "",
        "Ranked keywords:",
        *[f"  - #{kw.position} {kw.keyword} ({kw.volume}/mo)" for kw in result.ranked_keywords[:10]],
    ]
    if result.competitors:
        lines.extend(
            [
                "",
                "Competitors:",
                *[f"  - {c.domain}: authority {c.authority}, overlap {c.overlap_keywords}" for c in result.competitors],
            ]
        )
    if result.keyword_gaps:
        lines.extend(
            [
                "",
                "Keyword gaps:",
                *[
                    f"  - {gap.keyword}: {gap.competitor_domain} ranks #{gap.competitor_position} "
                    f"({gap.volume}/mo, difficulty {gap.difficulty})"
                    for gap in result.keyword_gaps[:12]
                ],
            ]
        )
    if result.warnings:
        lines.extend(["", *[f"Warning: {warning}" for warning in result.warnings]])
    click.echo("\n".join(lines))


@seo_cmd.command(name="backlinks")
@click.option("--domain", "domain_name", required=True, help="Domain to analyze")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def backlinks_cmd(domain_name: str, output_format: str) -> None:
    """Analyze backlinks, referring domains, anchors, strength, and new/lost history."""
    result = analyze_backlinks(domain_name)
    if output_format == "json":
        click.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return
    lines = [
        "🔗 BACKLINK ANALYSIS",
        "=" * 64,
        f"Domain: {result.domain}",
        f"Provider: {result.provider}",
        f"Backlinks: {len(result.backlinks)}",
        f"Referring domains: {len(result.referring_domains)}",
        "",
        "Top referring domains:",
        *[
            f"  - {item.domain}: {item.backlinks} links, authority {item.authority}"
            for item in result.referring_domains[:10]
        ],
        "",
        "Top anchors:",
        *[f"  - {anchor}: {count}" for anchor, count in list(result.anchors.items())[:10]],
    ]
    if result.new_lost_history:
        lines.extend(
            [
                "",
                "New/lost history:",
                *[f"  - {p.date}: +{p.new_links} / -{p.lost_links}" for p in result.new_lost_history[-12:]],
            ]
        )
    if result.warnings:
        lines.extend(["", *[f"Warning: {warning}" for warning in result.warnings]])
    click.echo("\n".join(lines))


@seo_cmd.group(name="rank")
def rank_cmd() -> None:
    """Classic rank tracking with local SQLite snapshots."""


@rank_cmd.command(name="add")
@click.option("--keyword", required=True, help="Keyword to track")
@click.option("--url", required=True, help="Target URL to track")
@click.option("--db", "db_path", default=None, help="Override rank-tracking DB path")
def rank_add_cmd(keyword: str, url: str, db_path: str | None) -> None:
    """Add a tracked keyword/URL pair."""
    tracker = RankTracker(Path(db_path) if db_path else None)
    item = tracker.add_keyword(keyword, _normalize_url(url))
    click.echo(f"✅ Tracking '{item.keyword}' for {item.url}")


@rank_cmd.command(name="list")
@click.option("--db", "db_path", default=None, help="Override rank-tracking DB path")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def rank_list_cmd(db_path: str | None, output_format: str) -> None:
    """List tracked keywords and recent analytics."""
    result = RankTracker(Path(db_path) if db_path else None).analytics()
    if output_format == "json":
        click.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return
    lines = [
        "📍 RANK TRACKING",
        "=" * 64,
        f"DB: {result.db_path}",
        f"Tracked keywords: {len(result.tracked_keywords)}",
        f"Snapshots: {len(result.snapshots)}",
        f"Average rank: {result.average_rank or 'n/a'}",
        f"Best rank: {result.best_rank or 'n/a'}",
        "",
        "Tracked:",
        *[f"  - {item.keyword} → {item.url}" for item in result.tracked_keywords],
    ]
    click.echo("\n".join(lines))


@rank_cmd.command(name="snapshot")
@click.option("--db", "db_path", default=None, help="Override rank-tracking DB path")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def rank_snapshot_cmd(db_path: str | None, output_format: str) -> None:
    """Run one rank snapshot for every tracked keyword."""
    try:
        result = RankTracker(Path(db_path) if db_path else None).snapshot_all()
    except Exception as exc:  # noqa: BLE001 - keep CLI failure readable across provider/network errors
        raise click.ClickException(str(exc)) from exc
    if output_format == "json":
        click.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return
    lines = [
        "📍 RANK SNAPSHOT",
        "=" * 64,
        f"Snapshots stored: {len(result.snapshots)}",
        f"Average rank: {result.average_rank or 'n/a'}",
        f"Best rank: {result.best_rank or 'n/a'}",
        "",
        *[
            f"  - {snap.keyword}: {('#' + str(snap.rank)) if snap.rank else 'not found'} "
            f"for {snap.domain} at {snap.checked_at}"
            for snap in result.snapshots
        ],
    ]
    click.echo("\n".join(lines))


@seo_cmd.command(name="lighthouse")
@click.option("--url", required=True, help="URL to audit")
@click.option("--provider", type=click.Choice(["pagespeed", "cli"]), default="pagespeed", show_default=True)
@click.option("--report-path", default=None, help="Path for local lighthouse CLI JSON report")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def lighthouse_cmd(url: str, provider: str, report_path: str | None, output_format: str) -> None:
    """Run Google Lighthouse/PageSpeed performance, accessibility, best-practices, and SEO audit."""
    result = run_lighthouse_audit(_normalize_url(url), provider=provider, report_path=report_path)
    if output_format == "json":
        click.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        return
    if not result.checked:
        lines = [
            "⚡ LIGHTHOUSE",
            "=" * 64,
            f"URL: {result.url}",
            f"Provider: {result.provider}",
            "Status: unavailable",
        ]
        if result.warnings:
            lines.extend(["", *[f"Warning: {warning}" for warning in result.warnings]])
        click.echo("\n".join(lines))
        return
    lines = [
        "⚡ LIGHTHOUSE",
        "=" * 64,
        f"URL: {result.url}",
        f"Provider: {result.provider}",
        f"Performance: {result.performance_score}/100",
        f"Accessibility: {result.accessibility_score}/100",
        f"Best practices: {result.best_practices_score}/100",
        f"SEO: {result.seo_score}/100",
        f"Page load metric: {result.page_load_ms} ms",
        f"Image rendering metric: {result.image_rendering_ms} ms",
        f"Video rendering metric: {result.video_rendering_ms} ms",
    ]
    if result.report_path:
        lines.append(f"Report: {result.report_path}")
    if result.metrics:
        lines.extend(["", "Metrics:", *[f"  - {m.name}: {m.value}" for m in result.metrics]])
    if result.warnings:
        lines.extend(["", *[f"Warning: {warning}" for warning in result.warnings]])
    click.echo("\n".join(lines))


def _normalize_url(value: str) -> str:
    return value if value.startswith(("http://", "https://")) else f"https://{value}"
