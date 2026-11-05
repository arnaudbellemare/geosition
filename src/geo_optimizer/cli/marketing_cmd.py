"""
geo marketing — Combined GEO + Marketing audit command.

Runs a full GEO audit then layers on marketing analysis drawn from the
marketingskills framework (github.com/coreyhaines31/marketingskills):

  - Copywriting quality   (page-cro + copywriting skills)
  - Content strategy      (content-strategy + ai-seo skills)
  - Conversion readiness  (page-cro skill)
  - Performance signals   (Core Web Vitals)

Usage:
    geo marketing --url https://example.com
    geo marketing --url https://example.com --vs https://competitor.com
    geo marketing --url https://example.com --output report.md
"""

from __future__ import annotations

import click

# Score band labels + colours
_BANDS = [
    (80, "excellent", "green"),
    (60, "good", "yellow"),
    (40, "moderate", "yellow"),
    (0, "needs work", "red"),
]


def _band(score: int) -> tuple[str, str]:
    for threshold, label, colour in _BANDS:
        if score >= threshold:
            return label, colour
    return "needs work", "red"


@click.command(name="marketing")
@click.argument("url_arg", required=False, default=None, metavar="URL")
@click.option("--url", "url_opt", default=None, help="Site URL to audit (or pass as first positional arg).")
@click.option("--vs", "rival_url", default=None, help="Optional competitor URL to benchmark against.")
@click.option(
    "--vertical",
    default="auto",
    show_default=True,
    help="Vertical override (e.g. real-estate-proptech, saas, e-commerce).",
)
@click.option("--output", default=None, help="Save markdown report to this file.")
@click.option(
    "--no-links",
    "skip_links",
    is_flag=True,
    default=False,
    help="Skip the broken-link crawl (faster for large sites).",
)
def marketing(
    url_arg: str | None, url_opt: str | None, rival_url: str | None, vertical: str, output: str | None, skip_links: bool
):
    """Run GEO audit + marketing analysis (copywriting, content strategy, CRO, performance)."""
    url = url_arg or url_opt
    if not url:
        raise click.UsageError("URL required. Usage:\n\n  geo marketing https://yoursite.com")

    from geo_optimizer.core.audit import run_full_audit
    from geo_optimizer.core.audit_marketing import audit_marketing

    # ── Run GEO audit ─────────────────────────────────────────────────────────
    click.echo(f"⏳ Auditing {url}…", err=True)
    result = run_full_audit(url, vertical=vertical)

    if result.error:
        click.echo(f"✗ Could not reach {url}: {result.error}", err=True)
        raise click.Abort()

    # Auto-detect output language from the audited site (respects --lang override)
    from geo_optimizer.i18n import auto_detect_lang

    html_lang = getattr(getattr(result, "signals", None), "lang_value", "") or ""
    auto_detect_lang(html_lang=html_lang, url=url)

    # ── Run marketing analysis ────────────────────────────────────────────────
    from bs4 import BeautifulSoup

    from geo_optimizer.utils.http import fetch_url

    click.echo("⏳ Running marketing analysis…", err=True)
    r, _ = fetch_url(url)
    soup = BeautifulSoup(r.text, "html.parser") if r else None
    marketing_result = audit_marketing(
        soup=soup,
        base_url=url,
        schema=result.schema,
        meta=result.meta,
        content=result.content,
        conversion=result.conversion,
        citability=result.citability,
    )

    # ── Optionally audit rival ─────────────────────────────────────────────────
    rival_result = None
    rival_marketing = None
    if rival_url:
        click.echo(f"⏳ Auditing rival {rival_url}…", err=True)
        rival_result = run_full_audit(rival_url, vertical=vertical)
        if not rival_result.error:
            r2, _ = fetch_url(rival_url)
            soup2 = BeautifulSoup(r2.text, "html.parser") if r2 else None
            rival_marketing = audit_marketing(
                soup=soup2,
                base_url=rival_url,
                schema=rival_result.schema,
                meta=rival_result.meta,
                content=rival_result.content,
                conversion=rival_result.conversion,
                citability=rival_result.citability,
            )

    # ── Terminal output (rich if available, plain text fallback) ───────────────
    try:
        from rich.console import Console as _Console

        _print_terminal_rich(_Console(), url, result, marketing_result, rival_url, rival_result, rival_marketing)
    except ImportError:
        _print_terminal_plain(url, result, marketing_result, rival_url, rival_result, rival_marketing)

    # ── Markdown output ────────────────────────────────────────────────────────
    if output:
        md = _build_markdown(url, result, marketing_result, rival_url, rival_result, rival_marketing)
        with open(output, "w", encoding="utf-8") as f:
            f.write(md)
        click.echo(f"\n✓ Report saved to {output}")


# ─── Terminal renderer ────────────────────────────────────────────────────────


def _print_terminal_plain(url, result, marketing_result, rival_url, rival_result, rival_marketing):
    """Plain click.echo fallback when rich is not installed."""
    geo = result.score
    mkt = marketing_result.marketing_score
    copy = marketing_result.copywriting
    strat = marketing_result.content_strategy
    conv = result.conversion.conversion_score if result.conversion.checked else 0
    perf = result.perf.perf_score if result.perf.checked else 0

    click.echo(f"\n{'=' * 60}")
    click.echo(f"  MARKETING AUDIT  —  {url}")
    click.echo(f"{'=' * 60}")
    click.echo(f"  GEO (AI Visibility)   {geo}/100  {_band(geo)[0]}")
    click.echo(f"  Marketing Readiness   {mkt}/100  {_band(mkt)[0]}")
    click.echo(f"  Copywriting Quality   {copy.copy_score}/100")
    click.echo(f"  Content Strategy      {strat.content_score}/100")
    click.echo(f"  AI Presence           {marketing_result.ai_presence.presence_score}/100")
    click.echo(f"  Conversion (CRO)      {conv}/100")
    click.echo(f"  Performance           {perf}/100")

    if rival_result and not rival_result.error and rival_marketing:
        click.echo(f"\n  Rival: {rival_url}")
        click.echo(
            f"  GEO delta: {geo - rival_result.score:+d}  Mktg delta: {mkt - rival_marketing.marketing_score:+d}"
        )

    click.echo(f"\n── COPYWRITING  {copy.copy_score}/100")
    click.echo(f'  {"✓" if copy.h1_is_outcome_focused else "✗"} H1: "{copy.h1_text[:70]}"')
    click.echo(f"  {'✓' if copy.has_value_prop_in_hero else '✗'} Value prop above fold")
    if copy.strong_ctas:
        click.echo(f"  ✓ Strong CTAs: {', '.join(copy.strong_ctas[:3])}")
    if copy.weak_ctas:
        click.echo(f"  ✗ Weak CTAs: {', '.join(copy.weak_ctas[:3])}")
    click.echo(f"  {'✓' if copy.benefit_ratio >= 0.4 else '✗'} Benefit language: {round(copy.benefit_ratio * 100)}%")

    presence = marketing_result.ai_presence
    if presence.checked:
        click.echo(f"\n── AI PRESENCE  {presence.presence_score}/100")
        if presence.robots_txt_fetched:
            click.echo(
                f"  {'✗' if presence.blocked_ai_bots else '✓'} robots.txt: "
                + (
                    f"blocked: {', '.join(presence.blocked_ai_bots)}"
                    if presence.blocked_ai_bots
                    else "AI crawlers allowed"
                )
            )
        click.echo(f"  {'✓' if presence.has_definition_block else '✗'} Definition block in first 300 words")
        click.echo(f"  {'✓' if presence.has_attributed_stats else '✗'} Attributed statistics")
        if presence.unattributed_stat_count:
            click.echo(f"    ({presence.unattributed_stat_count} unattributed stats found)")
        click.echo(f"  {'✓' if not presence.js_heavy else '✗'} Server-rendered content")
        click.echo(f"  {'✓' if presence.has_location_pages else '✗'} Location pages ({presence.location_page_count})")
        click.echo(f"  {'✓' if presence.has_org_sameas else '✗'} Organization sameAs schema")

    click.echo(f"\n── CONTENT STRATEGY  {strat.content_score}/100")
    for detected, label in [
        (strat.has_blog, f"Blog ({strat.estimated_article_count} articles)"),
        (strat.has_faq_section, "FAQ section"),
        (strat.has_comparison_pages, "Comparison pages"),
        (strat.has_pricing_page, "Pricing page"),
        (strat.has_email_capture, "Email capture"),
        (strat.has_numbers_proof, "Quantified social proof"),
    ]:
        click.echo(f"  {'✓' if detected else '✗'} {label}")

    if marketing_result.priority_actions:
        click.echo("\n── TOP MARKETING ACTIONS")
        for i, action in enumerate(marketing_result.priority_actions[:6], 1):
            click.echo(f"  {i}. [{action.priority}] {action.title}")
            click.echo(
                f"     impact={action.impact}  effort={action.effort}  skill={action.skill}"
                + (f"  {action.estimated_lift}" if action.estimated_lift else "")
            )

    if result.next_actions:
        click.echo("\n── GEO NEXT ACTIONS")
        for action in result.next_actions[:4]:
            click.echo(f"  [{action.priority}] {action.title}  ({action.why[:60]}…)")
    click.echo()


def _print_terminal_rich(con, url, result, marketing_result, rival_url, rival_result, rival_marketing):
    from rich import box
    from rich.panel import Panel
    from rich.table import Table

    geo_score = result.score
    mkt_score = marketing_result.marketing_score
    conv_score = result.conversion.conversion_score if result.conversion.checked else 0
    perf_score = result.perf.perf_score if result.perf.checked else 0

    geo_label, geo_colour = _band(geo_score)
    mkt_label, mkt_colour = _band(mkt_score)

    # ── Header panel ────────────────────────────────────────────────────────
    con.print()
    con.print(
        Panel(
            f"[bold white]{url}[/bold white]\n"
            f"GEO Score: [{geo_colour}]{geo_score}/100 ({geo_label})[/{geo_colour}]   "
            f"Marketing: [{mkt_colour}]{mkt_score}/100 ({mkt_label})[/{mkt_colour}]",
            title="[bold cyan]Marketing Audit[/bold cyan]",
            border_style="cyan",
        )
    )

    # ── Score summary table ──────────────────────────────────────────────────
    t = Table(box=box.SIMPLE, show_header=False, padding=(0, 1))
    t.add_column("Dimension", style="bold")
    t.add_column("Score", justify="right")
    t.add_column("Band")

    _add_row(t, "GEO (AI Visibility)", geo_score, geo_colour)
    _add_row(t, "Marketing Readiness", mkt_score, mkt_colour)
    _add_row(t, "Copywriting Quality", marketing_result.copywriting.copy_score, None)
    _add_row(t, "Content Strategy", marketing_result.content_strategy.content_score, None)
    _add_row(t, "AI Presence", marketing_result.ai_presence.presence_score, None)
    _add_row(t, "Conversion (CRO)", conv_score, None)
    _add_row(t, "Performance", perf_score, None)

    con.print(t)

    # ── Rival comparison ─────────────────────────────────────────────────────
    if rival_result and not rival_result.error and rival_marketing:
        con.print("\n[bold]Rival Benchmark:[/bold]", rival_url)
        rt = Table(box=box.SIMPLE, show_header=True, padding=(0, 1))
        rt.add_column("Dimension")
        rt.add_column("You", justify="right")
        rt.add_column("Rival", justify="right")
        rt.add_column("Delta", justify="right")
        for dim, yours, theirs in [
            ("GEO", geo_score, rival_result.score),
            ("Marketing", mkt_score, rival_marketing.marketing_score),
            ("Copywriting", marketing_result.copywriting.copy_score, rival_marketing.copywriting.copy_score),
            (
                "Content Strategy",
                marketing_result.content_strategy.content_score,
                rival_marketing.content_strategy.content_score,
            ),
            ("CRO", conv_score, rival_result.conversion.conversion_score),
        ]:
            delta = yours - theirs
            delta_str = f"[green]+{delta}[/green]" if delta > 0 else (f"[red]{delta}[/red]" if delta < 0 else "0")
            rt.add_row(dim, str(yours), str(theirs), delta_str)
        con.print(rt)

    # ── Copywriting findings ─────────────────────────────────────────────────
    copy = marketing_result.copywriting
    con.print(f"\n[bold cyan]── COPYWRITING[/bold cyan]  {copy.copy_score}/100")
    if copy.h1_text:
        icon = "✓" if copy.h1_is_outcome_focused else ("✗" if copy.h1_is_generic else "~")
        colour = "green" if copy.h1_is_outcome_focused else "red"
        con.print(f'  [{colour}]{icon}[/{colour}] H1: "{copy.h1_text[:70]}"')
    if copy.has_value_prop_in_hero:
        con.print("  [green]✓[/green] Value prop detected above fold")
    else:
        con.print("  [red]✗[/red] No value proposition above fold")

    if copy.strong_ctas:
        con.print(f"  [green]✓[/green] Strong CTAs: {', '.join(copy.strong_ctas[:3])}")
    if copy.weak_ctas:
        con.print(f"  [red]✗[/red] Weak CTAs: {', '.join(copy.weak_ctas[:3])}")

    if copy.benefit_ratio > 0:
        colour = "green" if copy.benefit_ratio >= 0.4 else "yellow" if copy.benefit_ratio >= 0.25 else "red"
        con.print(
            f"  [{colour}]{'✓' if copy.benefit_ratio >= 0.4 else '~' if copy.benefit_ratio >= 0.25 else '✗'}[/{colour}] "
            f"Benefit/feature ratio: {round(copy.benefit_ratio * 100)}% benefit-focused"
        )

    # ── Content strategy findings ────────────────────────────────────────────
    strat = marketing_result.content_strategy
    con.print(f"\n[bold cyan]── CONTENT STRATEGY[/bold cyan]  {strat.content_score}/100")
    _signal_row(
        con,
        strat.has_blog,
        f"Blog/content hub ({strat.estimated_article_count} articles found)" if strat.has_blog else "No blog found",
    )
    _signal_row(con, strat.has_faq_section, "FAQ section detected" if strat.has_faq_section else "No FAQ section")
    _signal_row(
        con,
        strat.has_comparison_pages,
        "Comparison pages found" if strat.has_comparison_pages else "No comparison/alternatives pages",
    )
    _signal_row(con, strat.has_pricing_page, "Pricing page linked" if strat.has_pricing_page else "No pricing page")
    _signal_row(
        con, strat.has_email_capture, "Email capture / lead magnet" if strat.has_email_capture else "No email capture"
    )
    _signal_row(
        con,
        strat.has_numbers_proof,
        "Quantified social proof present" if strat.has_numbers_proof else "No quantified social proof",
    )

    # ── AI presence findings ─────────────────────────────────────────────────
    presence = marketing_result.ai_presence
    if presence.checked:
        con.print(f"\n[bold cyan]── AI PRESENCE[/bold cyan]  {presence.presence_score}/100")
        if presence.robots_txt_fetched:
            if presence.blocked_ai_bots:
                con.print(f"  [red]✗[/red] AI bots blocked: {', '.join(presence.blocked_ai_bots)}")
            else:
                con.print("  [green]✓[/green] AI crawlers allowed in robots.txt")
        else:
            con.print("  [dim]~[/dim] robots.txt not checked")
        _signal_row(
            con,
            presence.has_definition_block,
            f'Definition block found: "{presence.definition_snippet[:60]}…"'
            if presence.definition_snippet
            else "Definition block found",
        )
        if presence.unattributed_stat_count > 0:
            attr_icon = "[green]✓[/green]" if presence.has_attributed_stats else "[yellow]~[/yellow]"
            con.print(
                f"  {attr_icon} Stats: {presence.unattributed_stat_count} unattributed"
                + (" (some attributed ✓)" if presence.has_attributed_stats else "")
            )
        elif presence.has_attributed_stats:
            con.print("  [green]✓[/green] Statistics have source attribution")
        _signal_row(
            con,
            not presence.js_heavy,
            "Content server-rendered (AI-readable)"
            if not presence.js_heavy
            else "JS-heavy — AI crawlers may miss content",
        )
        _signal_row(
            con,
            presence.has_location_pages,
            f"Location pages found ({presence.location_page_count})"
            if presence.has_location_pages
            else "No location-specific pages",
        )
        _signal_row(
            con,
            presence.has_org_sameas,
            "Organization sameAs links present"
            if presence.has_org_sameas
            else "No Organization sameAs links in schema",
        )

    # ── Top marketing actions ─────────────────────────────────────────────────
    if marketing_result.priority_actions:
        con.print("\n[bold cyan]── TOP MARKETING ACTIONS[/bold cyan]")
        for i, action in enumerate(marketing_result.priority_actions[:6], 1):
            window_colour = "green" if action.priority == "P1" else "yellow" if action.priority == "P2" else "dim"
            impact_colour = "green" if action.impact == "high" else "yellow"
            con.print(f"  {i}. [{window_colour}][{action.priority}][/{window_colour}] [bold]{action.title}[/bold]")
            con.print(
                f"     [{impact_colour}]impact={action.impact}[/{impact_colour}] "
                f"effort={action.effort}  skill=[dim]{action.skill}[/dim]"
                + (f"  [green]{action.estimated_lift}[/green]" if action.estimated_lift else "")
            )

    # ── Next GEO actions ─────────────────────────────────────────────────────
    if result.next_actions:
        con.print("\n[bold cyan]── GEO NEXT ACTIONS[/bold cyan]")
        for action in result.next_actions[:4]:
            window_colour = "green" if action.priority == "P1" else "yellow" if action.priority == "P2" else "dim"
            con.print(
                f"  [{window_colour}][{action.priority}][/{window_colour}] "
                f"[bold]{action.title}[/bold]  [dim]({action.why[:60]}…)[/dim]"
            )

    con.print()


def _add_row(table, label: str, score: int, colour: str | None):
    band_label, auto_colour = _band(score)
    colour = colour or auto_colour
    bar = "█" * (score // 5)
    table.add_row(label, f"{score}/100", f"[{colour}]{bar} {band_label}[/{colour}]")


def _signal_row(con, detected: bool, text: str):
    icon = "[green]✓[/green]" if detected else "[red]✗[/red]"
    con.print(f"  {icon} {text}")


# ─── Markdown renderer ────────────────────────────────────────────────────────


def _build_markdown(url, result, marketing_result, rival_url, rival_result, rival_marketing) -> str:
    from datetime import datetime, timezone

    geo = result.score
    mkt = marketing_result.marketing_score
    copy = marketing_result.copywriting
    strat = marketing_result.content_strategy
    presence = marketing_result.ai_presence
    conv = result.conversion
    perf = result.perf
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        "# Marketing Audit Report",
        "",
        f"URL: {url}",
        f"Date: {now}",
        f"GEO Score: {geo}/100",
        f"Marketing Score: {mkt}/100",
        "",
        "## Score Summary",
        "",
        "| Dimension | Score | Band |",
        "|-----------|------:|------|",
        f"| GEO (AI Visibility) | {geo}/100 | {_band(geo)[0]} |",
        f"| Marketing Readiness | {mkt}/100 | {_band(mkt)[0]} |",
        f"| Copywriting Quality | {copy.copy_score}/100 | {_band(copy.copy_score)[0]} |",
        f"| Content Strategy | {strat.content_score}/100 | {_band(strat.content_score)[0]} |",
        f"| AI Presence | {presence.presence_score}/100 | {_band(presence.presence_score)[0]} |",
        f"| Conversion (CRO) | {conv.conversion_score}/100 | {_band(conv.conversion_score)[0]} |",
        f"| Performance | {perf.perf_score}/100 | {_band(perf.perf_score)[0]} |",
        "",
    ]

    # Rival comparison
    if rival_result and not rival_result.error and rival_marketing:
        lines += [
            "## Rival Benchmark",
            "",
            f"Rival: {rival_url}",
            "",
            "| Dimension | You | Rival | Delta |",
            "|-----------|----:|------:|------:|",
        ]
        for dim, yours, theirs in [
            ("GEO", geo, rival_result.score),
            ("Marketing", mkt, rival_marketing.marketing_score),
            ("Copywriting", copy.copy_score, rival_marketing.copywriting.copy_score),
            ("Content Strategy", strat.content_score, rival_marketing.content_strategy.content_score),
            ("CRO", conv.conversion_score, rival_result.conversion.conversion_score),
        ]:
            delta = yours - theirs
            sign = "+" if delta > 0 else ""
            lines.append(f"| {dim} | {yours} | {theirs} | {sign}{delta} |")
        lines.append("")

    # Copywriting
    lines += [
        "## Copywriting Analysis",
        "",
        f"Score: {copy.copy_score}/100",
        "",
    ]
    if copy.h1_text:
        icon = "✓" if copy.h1_is_outcome_focused else "✗"
        lines.append(f'- {icon} H1: "{copy.h1_text}"')
    lines.append(f"- {'✓' if copy.has_value_prop_in_hero else '✗'} Value proposition above fold")
    if copy.strong_ctas:
        lines.append(f"- ✓ Strong CTAs: {', '.join(copy.strong_ctas[:3])}")
    if copy.weak_ctas:
        lines.append(f"- ✗ Weak CTAs: {', '.join(copy.weak_ctas[:3])}")
    lines.append(f"- Benefit/feature ratio: {round(copy.benefit_ratio * 100)}% benefit-focused")
    if copy.issues:
        lines += ["", "**Issues:**"]
        for issue in copy.issues:
            lines.append(f"- {issue}")
    if copy.suggestions:
        lines += ["", "**Suggestions:**"]
        for s in copy.suggestions:
            lines.append(f"- {s}")
    lines.append("")

    # Content strategy
    lines += [
        "## Content Strategy",
        "",
        f"Score: {strat.content_score}/100",
        "",
    ]
    for detected, label in [
        (strat.has_blog, f"Blog ({strat.estimated_article_count} articles)" if strat.has_blog else "Blog"),
        (strat.has_faq_section, "FAQ section"),
        (strat.has_comparison_pages, "Comparison/alternatives pages"),
        (strat.has_pricing_page, "Pricing page"),
        (strat.has_email_capture, "Email capture / lead magnet"),
        (strat.has_numbers_proof, "Quantified social proof"),
        (strat.has_case_studies, "Case studies"),
    ]:
        lines.append(f"- {'✓' if detected else '✗'} {label}")
    if strat.issues:
        lines += ["", "**Issues:**"]
        for issue in strat.issues:
            lines.append(f"- {issue}")
    if strat.suggestions:
        lines += ["", "**Suggestions:**"]
        for s in strat.suggestions:
            lines.append(f"- {s}")
    lines.append("")

    # AI Presence
    if presence.checked:
        lines += [
            "## AI Presence",
            "",
            f"Score: {presence.presence_score}/100",
            "",
        ]
        if presence.robots_txt_fetched:
            if presence.blocked_ai_bots:
                lines.append(f"- ✗ AI bots blocked in robots.txt: {', '.join(presence.blocked_ai_bots)}")
            else:
                lines.append("- ✓ AI crawlers allowed in robots.txt")
        lines.append(
            f"- {'✓' if presence.has_definition_block else '✗'} Definition block in first 300 words"
            + (f': "{presence.definition_snippet[:80]}…"' if presence.definition_snippet else "")
        )
        if presence.has_attributed_stats:
            lines.append(
                "- ✓ Attributed statistics present"
                + (
                    f" ({presence.unattributed_stat_count} unattributed also found)"
                    if presence.unattributed_stat_count
                    else ""
                )
            )
        elif presence.unattributed_stat_count:
            lines.append(f"- ✗ {presence.unattributed_stat_count} unattributed statistic(s) — add source citations")
        lines.append(f"- {'✓' if not presence.js_heavy else '✗'} Server-rendered content")
        lines.append(
            f"- {'✓' if presence.has_location_pages else '✗'} Location pages ({presence.location_page_count} found)"
        )
        lines.append(f"- {'✓' if presence.has_org_sameas else '✗'} Organization sameAs schema")
        if presence.has_author_schema:
            lines.append("- ✓ Author/Person schema with sameAs")
        if presence.issues:
            lines += ["", "**Issues:**"]
            for issue in presence.issues:
                lines.append(f"- {issue}")
        if presence.suggestions:
            lines += ["", "**Suggestions:**"]
            for s in presence.suggestions:
                lines.append(f"- {s}")
        lines.append("")

    # Conversion
    lines += [
        "## Conversion Readiness (CRO)",
        "",
        f"Score: {conv.conversion_score}/100",
        "",
    ]
    for s in conv.signals:
        lines.append(f"- {'✓' if s.detected else '✗'} {s.label}")
    if conv.priority_fixes:
        lines += ["", "**Priority fixes:**"]
        for fix in conv.priority_fixes:
            lines.append(f"- {fix}")
    lines.append("")

    # Performance
    lines += [
        "## Performance",
        "",
        f"Score: {perf.perf_score}/100",
        "",
        f"- Render-blocking scripts: {perf.render_blocking_scripts}",
        f"- Render-blocking stylesheets: {perf.render_blocking_styles}",
        f"- Images missing dimensions: {perf.images_missing_dimensions}",
        f"- Images missing lazy-load: {perf.images_missing_lazy}",
        f"- Missing font-display swap: {perf.missing_font_display_swap}",
        "",
    ]

    # Priority marketing actions
    if marketing_result.priority_actions:
        lines += [
            "## Priority Marketing Actions",
            "",
        ]
        for i, action in enumerate(marketing_result.priority_actions[:8], 1):
            lines.append(f"### {i}. {action.title}" + (f" [{action.priority}]" if action.priority else ""))
            lines += [
                f"- **Why**: {action.why}",
                f"- **Impact**: {action.impact}  **Effort**: {action.effort}",
                f"- **Skill**: [{action.skill}](https://github.com/coreyhaines31/marketingskills/tree/main/skills/{action.skill})",
            ]
            if action.estimated_lift:
                lines.append(f"- **Estimated lift**: {action.estimated_lift}")
            lines.append("")

    # GEO next actions
    if result.next_actions:
        lines += [
            "## GEO Next Actions",
            "",
        ]
        for action in result.next_actions[:5]:
            lines.append(
                f"- **{action.title}** [{action.priority}] impact={action.impact} effort={action.effort} (+{action.expected_score_gain} pts)"
            )
            lines.append(f"  - why: {action.why}")
        lines.append("")

    return "\n".join(lines)
