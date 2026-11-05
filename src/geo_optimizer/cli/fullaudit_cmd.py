"""
geo full — All-in-one GEO + Marketing Full Report.

Runs the complete audit stack in a single command:
  - GEO (AI Visibility): robots, llms.txt, schema, meta, content, signals, brand entity
  - Marketing: copywriting quality, content strategy, AI presence
  - Conversion readiness (CRO)
  - Performance signals
  - Rival comparison (optional)

Usage:
    geo full --url https://example.com
    geo full --url https://example.com --vs https://competitor.com
    geo full --url https://example.com --output report.md
    geo full --url https://example.com --vertical real-estate-proptech
"""

from __future__ import annotations

import io
import os
from datetime import datetime, timezone

import click

from geo_optimizer.core.scoring import get_score_band
from geo_optimizer.utils.seo_program_note import MARKDOWN_SEO_SECTION, REPO_SEO_PROGRAM_FOOTER

# ─── Score helpers ────────────────────────────────────────────────────────────

_COLORS = {
    "excellent": "#22c55e",
    "good": "#06b6d4",
    "foundation": "#f59e0b",
    "critical": "#ef4444",
    "accent": "#8b5cf6",
    "dim": "#475569",
    "brand_1": "#3b82f6",
    "brand_2": "#06b6d4",
    "brand_3": "#8b5cf6",
}

_BAND_CONFIG = {
    "excellent": {"icon": "🏆", "label": "EXCELLENT", "desc": "AI-ready — fully optimized"},
    "good": {"icon": "✅", "label": "GOOD", "desc": "Solid foundation"},
    "foundation": {"icon": "⚡", "label": "FOUNDATION", "desc": "Key elements missing"},
    "critical": {"icon": "🚨", "label": "CRITICAL", "desc": "Not visible to AI engines"},
}

# 5-row ASCII digit art (matches rich_formatter.py)
_DIGITS = {
    "0": ["╭━╮", "┃ ┃", "┃ ┃", "┃ ┃", "╰━╯"],
    "1": [" ╻ ", "╺┃ ", " ┃ ", " ┃ ", "╺┻╸"],
    "2": ["╭━╮", "╰━┃", "╭━╯", "┃  ", "╰━━"],
    "3": ["╭━╮", "╰━┃", " ━┃", "╭━┃", "╰━╯"],
    "4": ["╻ ╻", "┃ ┃", "╰━┃", "  ┃", "  ╹"],
    "5": ["╭━━", "┃  ", "╰━╮", "╭━┃", "╰━╯"],
    "6": ["╭━╮", "┃  ", "┣━╮", "┃ ┃", "╰━╯"],
    "7": ["━━╮", "  ┃", " ╻╯", " ┃ ", " ╹ "],
    "8": ["╭━╮", "┃ ┃", "┣━┫", "┃ ┃", "╰━╯"],
    "9": ["╭━╮", "┃ ┃", "╰━┃", "  ┃", "╰━╯"],
}


def _score_color(score: int) -> str:
    return _COLORS.get(get_score_band(score), _COLORS["critical"])


def _band(score: int) -> tuple[str, str]:
    """Return (band_key, label) for a 0-100 score."""
    band_key = get_score_band(score)
    label = "moderate" if band_key == "foundation" else "needs work" if band_key == "critical" else band_key
    return band_key, label


def _micro_bar(score: int, max_score: int = 100, width: int = 22):
    """Return a Rich Text micro progress bar."""
    try:
        from rich.text import Text

        pct = score / max_score if max_score > 0 else 0
        filled = int(pct * width)
        empty = width - filled
        color = _score_color(int(pct * 100))
        bar = Text()
        bar.append("▓" * filled, style=color)
        bar.append("░" * empty, style=_COLORS["dim"])
        bar.append(f"  {score}/{max_score}", style=f"bold {color}")
        return bar
    except ImportError:
        return None


def _big_number_lines(number: int, color: str):
    """Return 5 Rich Text rows for an ASCII-art number."""
    try:
        from rich.text import Text

        digits = str(number)
        rows = []
        for row in range(5):
            line = Text()
            for i, d in enumerate(digits):
                if i > 0:
                    line.append(" ")
                line.append(_DIGITS.get(d, _DIGITS["0"])[row], style=f"bold {color}")
            rows.append(line)
        return rows
    except ImportError:
        return []


# ─── Click command ────────────────────────────────────────────────────────────


@click.command(name="full")
@click.argument("url_arg", required=False, default=None, metavar="URL")
@click.option("--url", "url_opt", default=None, help="Site URL to audit (or pass as first positional arg).")
@click.option("--vs", "rival_url", default=None, help="Competitor URL to benchmark against.")
@click.option(
    "--vertical",
    default="auto",
    show_default=True,
    type=click.Choice(
        [
            "auto",
            "generic",
            "ecommerce-retail",
            "travel-hospitality",
            "healthcare-dental",
            "real-estate-proptech",
            "legal-professional-services",
            "manufacturing-industrial-b2b",
            "financial-services-insurance",
            "saas-technology",
            "education-edtech-k12",
            "local-home-services",
        ],
        case_sensitive=False,
    ),
    help="Vertical override.",
)
@click.option("--output", default=None, help="Save full markdown report to this file.")
@click.option(
    "--no-links",
    "skip_links",
    is_flag=True,
    default=False,
    help="Skip broken-link crawl (faster).",
)
@click.option(
    "--check-external",
    "check_external",
    is_flag=True,
    default=False,
    help="Also HEAD-check external links for broken URLs (adds ~30 s).",
)
@click.option(
    "--serp",
    "run_serp",
    is_flag=True,
    default=False,
    help="Run Google first-page competitor analysis (adds ~30 s).",
)
@click.option(
    "--keyword", default=None, help="Override keyword for SERP analysis (default: auto-detected from title/H1)."
)
@click.option(
    "--rivals",
    "rivals_csv",
    default=None,
    help=(
        "Comma-separated list of real Google competitor URLs to analyse directly "
        "(e.g. condostrategis.ca,laucandrique.ca,solutioncondo.com). "
        "Enables --serp automatically."
    ),
)
def full(
    url_arg: str | None,
    url_opt: str | None,
    rival_url: str | None,
    vertical: str,
    output: str | None,
    skip_links: bool,
    check_external: bool,
    run_serp: bool,
    keyword: str | None,
    rivals_csv: str | None,
):
    """Run the complete GEO + Marketing + AI Presence + SERP audit in one command."""
    url = url_arg or url_opt
    if not url:
        raise click.UsageError(
            "URL required. Usage:\n\n  geo full https://yoursite.com\n\n"
            "Optional rival comparison:\n\n  geo full https://yoursite.com --vs https://competitor.com"
        )

    from bs4 import BeautifulSoup

    from geo_optimizer.core.audit import run_full_audit
    from geo_optimizer.core.audit_marketing import audit_marketing
    from geo_optimizer.utils.http import fetch_url

    # ── GEO audit ────────────────────────────────────────────────────────────
    if check_external:
        click.echo(f"⏳  Auditing {url} (+ external link check)…", err=True)
    else:
        click.echo(f"⏳  Auditing {url}…", err=True)
    result = run_full_audit(url, vertical=vertical, check_external_links=check_external)

    if result.error:
        click.echo(f"✗  Could not reach {url}: {result.error}", err=True)
        raise click.Abort()

    # Auto-detect output language from the audited site (respects --lang override)
    from geo_optimizer.i18n import auto_detect_lang

    html_lang = getattr(getattr(result, "signals", None), "lang_value", "") or ""
    auto_detect_lang(html_lang=html_lang, url=url)

    # ── Marketing audit ───────────────────────────────────────────────────────
    click.echo("⏳  Running marketing + media + AI presence analysis…", err=True)
    r, _ = fetch_url(url)
    soup = BeautifulSoup(r.text, "html.parser") if r else None

    # Parse manual rival URLs from --rivals flag
    rival_urls: list[str] | None = None
    if rivals_csv:
        rival_urls = [u.strip() for u in rivals_csv.split(",") if u.strip()]
        click.echo(f"⏳  Analysing {len(rival_urls)} real Google competitor(s)…", err=True)
    elif run_serp:
        click.echo("⏳  Fetching Google first-page competitors…", err=True)

    mkt = audit_marketing(
        soup=soup,
        base_url=url,
        schema=result.schema,
        meta=result.meta,
        content=result.content,
        conversion=result.conversion,
        citability=result.citability,
        run_serp=run_serp,
        vertical=vertical,
        geo_result=result,
        rival_urls=rival_urls,
        keyword=keyword,
    )

    # ── Optional rival ────────────────────────────────────────────────────────
    rival_result = None
    rival_mkt = None
    if rival_url:
        click.echo(f"⏳  Auditing rival {rival_url}…", err=True)
        rival_result = run_full_audit(rival_url, vertical=vertical)
        if not rival_result.error:
            r2, _ = fetch_url(rival_url)
            soup2 = BeautifulSoup(r2.text, "html.parser") if r2 else None
            rival_mkt = audit_marketing(
                soup=soup2,
                base_url=rival_url,
                schema=rival_result.schema,
                meta=rival_result.meta,
                content=rival_result.content,
                conversion=rival_result.conversion,
                citability=rival_result.citability,
            )

    # ── Terminal output ───────────────────────────────────────────────────────
    _print_rich(url, result, mkt, rival_url, rival_result, rival_mkt)

    # ── AI analysis (requires GEO_LLM_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY) ──
    ai_narrative = _run_ai_analysis(url, result, mkt)
    if ai_narrative:
        _print_ai_analysis(ai_narrative)

    # ── Markdown file ─────────────────────────────────────────────────────────
    if output:
        md = _build_markdown(url, result, mkt, rival_url, rival_result, rival_mkt)
        if ai_narrative:
            md += f"\n\n## AI Analysis\n\n{ai_narrative}\n"
        with open(output, "w", encoding="utf-8") as f:
            f.write(md)
        click.echo(f"\n✓  Report saved → {output}")


# ─── AI analysis helpers ──────────────────────────────────────────────────────


def _run_ai_analysis(url: str, result, mkt) -> str | None:
    """Call an LLM to produce a strategic narrative from the audit results.

    Returns the analysis text, or None if no LLM provider is configured or the
    call fails.  Never raises — always degrades gracefully.
    """
    try:
        from geo_optimizer.core.llm_client import detect_provider, query_llm
    except ImportError:
        return None

    provider, _ = detect_provider()
    if not provider:
        return None

    # Build a compact audit digest for the prompt
    geo_score = result.score
    geo_band = result.band
    recs = result.recommendations or []
    top_geo_issues = "\n".join(f"- {r}" for r in recs[:5]) or "- None detected"

    copy_score = getattr(mkt.copywriting, "score", "N/A")
    strategy_score = getattr(mkt.content_strategy, "score", "N/A")
    presence_score = getattr(mkt.ai_presence, "score", "N/A")
    cro_score = getattr(result, "conversion", None)
    cro_val = getattr(cro_score, "score", "N/A") if cro_score else "N/A"
    perf_score = getattr(result, "perf", None)
    perf_val = getattr(perf_score, "score", "N/A") if perf_score else "N/A"

    copy_issues = getattr(mkt.copywriting, "issues", []) or []
    strat_issues = getattr(mkt.content_strategy, "issues", []) or []
    mkt_issues = "\n".join(f"- {i}" for i in (copy_issues + strat_issues)[:5]) or "- None detected"

    prompt = f"""You are a GEO (Generative Engine Optimization) and digital marketing expert.

A website has just been audited. Here are the results:

Site: {url}

SCORES
  GEO (AI Visibility): {geo_score}/100 — {geo_band}
  Copywriting:         {copy_score}/100
  Content Strategy:    {strategy_score}/100
  AI Presence:         {presence_score}/100
  Conversion (CRO):    {cro_val}/100
  Performance:         {perf_val}/100

TOP GEO ISSUES
{top_geo_issues}

TOP MARKETING ISSUES
{mkt_issues}

Write a concise strategic analysis (150–200 words) for the site owner. Structure it as:
1. One sentence overall assessment.
2. Three prioritized actions (most impactful first), each with a brief reason why.
3. One sentence on the biggest opportunity if they fix the top issue.

Be direct and specific. No fluff.
"""

    click.echo("⏳  Running AI analysis…", err=True)
    resp = query_llm(prompt, system="You are a concise, expert GEO and marketing analyst.", max_tokens=400)
    if resp.error or not resp.text:
        return None
    return resp.text.strip()


def _print_ai_analysis(narrative: str) -> None:
    """Print the AI analysis panel to the terminal."""
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.text import Text

        con = Console()
        body = Text(narrative, style="white")
        con.print(
            Panel(
                body,
                title="[bold cyan]✦ AI Analysis[/bold cyan]",
                border_style="cyan",
                padding=(1, 2),
            )
        )
    except ImportError:
        click.echo("\n── AI Analysis ──────────────────────────────────────────")
        click.echo(narrative)
        click.echo("─────────────────────────────────────────────────────────\n")


# ─── Rich terminal renderer ────────────────────────────────────────────────────


def _print_rich(url, result, mkt, rival_url, rival_result, rival_mkt):
    try:
        from rich import box
        from rich.align import Align
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
    except ImportError as exc:
        click.echo(f"Install 'rich' for a visual report: pip install rich  ({exc})", err=True)
        return

    buf = io.StringIO()
    con = Console(file=buf, width=82, force_terminal=True, no_color="NO_COLOR" in os.environ)

    def _flush():
        """Emit whatever has been written to the buffer so far."""
        chunk = buf.getvalue()
        if chunk:
            click.echo(chunk, nl=False)
        buf.truncate(0)
        buf.seek(0)

    def _section_error(label: str, exc: Exception) -> None:
        click.echo(f"  [render error in {label}: {exc}]", err=True)

    geo_score = result.score
    mkt_score = mkt.marketing_score
    geo_band_key, _ = _band(geo_score)
    mkt_band_key, _ = _band(mkt_score)
    geo_color = _score_color(geo_score)
    mkt_color = _score_color(mkt_score)
    geo_cfg = _BAND_CONFIG.get(geo_band_key, _BAND_CONFIG["critical"])
    mkt_cfg = _BAND_CONFIG.get(mkt_band_key, _BAND_CONFIG["critical"])

    # ── Header ──────────────────────────────────────────────────────────────
    try:
        con.print()
        logo_lines = [
            ("  ╔══╗  ╔══╗  ╔══╗  ", _COLORS["brand_1"]),
            ("  ║ ═╣  ║╔═╝  ║  ║  ", _COLORS["brand_2"]),
            ("  ║ ╔╣  ║╚═╗  ║  ║  ", _COLORS["accent"]),
            ("  ╚══╝  ╚══╝  ╚══╝  ", _COLORS["brand_1"]),
        ]
        for txt, col in logo_lines:
            con.print(Align.center(Text(txt, style=f"bold {col}")))
        con.print(Align.center(Text("F U L L   R E P O R T", style=f"bold {_COLORS['dim']}")))
        con.print()

        # ── URL info panel ───────────────────────────────────────────────────────
        info = Text()
        info.append("  🌐  ", style="default")
        info.append(url, style=f"bold {_COLORS['brand_2']} underline")
        info.append(f"\n  ⚡  HTTP {result.http_status}", style="bold")
        _vert = getattr(result.vertical_profile, "vertical", None) or "auto"
        info.append(f"  •  {result.page_size:,} bytes  •  {_vert} vertical", style=_COLORS["dim"])
        con.print(Panel(info, box=box.ROUNDED, border_style=_COLORS["brand_1"], padding=(0, 1)))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
        _section_error("header", exc)
    _flush()

    # ── Two-score gauge ──────────────────────────────────────────────────────
    try:
        con.print()
        scores_table = Table(show_header=False, box=None, expand=True, padding=(0, 3))
        scores_table.add_column(ratio=1, justify="center")
        scores_table.add_column(ratio=1, justify="center")

        def _score_block(label: str, score: int, color: str, cfg: dict) -> Text:
            block = Text(justify="center")
            block.append(f"\n{label}\n", style=f"bold {_COLORS['dim']}")
            for row in _big_number_lines(score, color):
                block.append_text(row)
                block.append("\n")
            block.append("\n")
            bar_width = 22
            filled = int(score * bar_width / 100)
            block.append("█" * filled, style=f"bold {color}")
            block.append("░" * (bar_width - filled), style=_COLORS["dim"])
            block.append(f"\n{cfg['icon']} {cfg['label']}", style=f"bold {color}")
            block.append(f"  —  {cfg['desc']}", style=f"italic {_COLORS['dim']}")
            return block

        scores_table.add_row(
            _score_block("GEO  (AI Visibility)", geo_score, geo_color, geo_cfg),
            _score_block("Marketing Readiness", mkt_score, mkt_color, mkt_cfg),
        )
        con.print(
            Panel(
                scores_table,
                title="[bold]📊 Score Overview[/]",
                title_align="left",
                border_style=_COLORS["brand_1"],
                box=box.ROUNDED,
                padding=(1, 1),
            )
        )
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
        _section_error("score overview", exc)
    _flush()

    # ── Rival comparison ─────────────────────────────────────────────────────
    if rival_result and not rival_result.error and rival_mkt:
        try:
            con.print()
            rt = Table(box=box.SIMPLE_HEAVY, show_header=True, padding=(0, 1))
            rt.add_column("Dimension", style="bold")
            rt.add_column("You", justify="right")
            rt.add_column("Rival", justify="right")
            rt.add_column("Delta", justify="right")

            def _delta(y, r):
                d = y - r
                if d > 0:
                    return Text(f"+{d}", style=_COLORS["excellent"])
                if d < 0:
                    return Text(str(d), style=_COLORS["critical"])
                return Text("=", style=_COLORS["dim"])

            rt.add_row(
                "GEO (AI Visibility)", str(geo_score), str(rival_result.score), _delta(geo_score, rival_result.score)
            )
            rt.add_row(
                "Marketing Readiness",
                str(mkt_score),
                str(rival_mkt.marketing_score),
                _delta(mkt_score, rival_mkt.marketing_score),
            )
            rt.add_row(
                "  Copywriting",
                str(mkt.copywriting.copy_score),
                str(rival_mkt.copywriting.copy_score),
                _delta(mkt.copywriting.copy_score, rival_mkt.copywriting.copy_score),
            )
            rt.add_row(
                "  Content Strategy",
                str(mkt.content_strategy.content_score),
                str(rival_mkt.content_strategy.content_score),
                _delta(mkt.content_strategy.content_score, rival_mkt.content_strategy.content_score),
            )
            rt.add_row(
                "  AI Presence",
                str(mkt.ai_presence.presence_score),
                str(rival_mkt.ai_presence.presence_score),
                _delta(mkt.ai_presence.presence_score, rival_mkt.ai_presence.presence_score),
            )
            rt.add_row(
                "Conversion (CRO)",
                str(result.conversion.conversion_score),
                str(rival_result.conversion.conversion_score),
                _delta(result.conversion.conversion_score, rival_result.conversion.conversion_score),
            )

            con.print(
                Panel(
                    rt,
                    title=f"[bold]🏁 vs {rival_url}[/]",
                    title_align="left",
                    border_style=_COLORS["accent"],
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
        except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
            _section_error("rival comparison", exc)
        _flush()

    # ── GEO category breakdown ────────────────────────────────────────────────
    geo_cats = []
    try:
        from geo_optimizer.cli.scoring_helpers import (
            brand_entity_score as _be_score,
        )
        from geo_optimizer.cli.scoring_helpers import (
            content_score as _c_score,
        )
        from geo_optimizer.cli.scoring_helpers import (
            llms_score as _l_score,
        )
        from geo_optimizer.cli.scoring_helpers import (
            meta_score as _m_score,
        )
        from geo_optimizer.cli.scoring_helpers import (
            robots_score as _r_score,
        )
        from geo_optimizer.cli.scoring_helpers import (
            schema_score as _s_score,
        )
        from geo_optimizer.cli.scoring_helpers import (
            signals_score as _sig_score,
        )
        from geo_optimizer.core.scoring import _score_ai_discovery

        geo_cats = [
            ("Robots", _r_score(result), 18),
            ("llms.txt", _l_score(result), 18),
            ("Schema", _s_score(result), 16),
            ("Meta", _m_score(result), 14),
            ("Content", _c_score(result), 12),
            ("Signals", _sig_score(result), 6),
            ("Brand", _be_score(result), 10),
            ("AI Disc.", _score_ai_discovery(result.ai_discovery) if result.ai_discovery else 0, 6),
        ]
        seg_colors = [
            _COLORS["brand_1"],
            _COLORS["brand_2"],
            _COLORS["accent"],
            _COLORS["excellent"],
            _COLORS["foundation"],
            _COLORS["good"],
            _COLORS["brand_3"],
            _COLORS["muted"] if "muted" in _COLORS else _COLORS["dim"],
        ]

        geo_bar = Text()
        total_geo = sum(s for _, s, _ in geo_cats)
        bar_width = 64
        remaining = bar_width
        for i, (_, score, _) in enumerate(geo_cats):
            seg_w = max(1, round(score / total_geo * bar_width)) if total_geo and score else 0
            if i == len(geo_cats) - 1:
                seg_w = remaining
            remaining -= seg_w
            if seg_w > 0:
                geo_bar.append("━" * seg_w, style=f"bold {seg_colors[i % len(seg_colors)]}")
        if remaining > 0:
            geo_bar.append("╌" * remaining, style=_COLORS["dim"])

        geo_legend = Text()
        for i, (name, score, max_s) in enumerate(geo_cats):
            if i > 0:
                geo_legend.append("  ")
            color = seg_colors[i % len(seg_colors)]
            geo_legend.append("━━", style=f"bold {color}")
            geo_legend.append(f" {name} ", style="dim")
            geo_legend.append(f"{score}", style=f"bold {color}")
            geo_legend.append(f"/{max_s}", style="dim")

        mkt_legend = Text()
        mkt_cats = [
            ("Copy", mkt.copywriting.copy_score, 100, _COLORS["excellent"]),
            ("Strategy", mkt.content_strategy.content_score, 100, _COLORS["foundation"]),
            ("AI Pres.", mkt.ai_presence.presence_score, 100, _COLORS["accent"]),
            ("CRO", result.conversion.conversion_score, 100, _COLORS["brand_2"]),
            ("Perf", result.perf.perf_score, 100, _COLORS["brand_3"]),
        ]
        for i, (name, score, max_s, color) in enumerate(mkt_cats):
            if i > 0:
                mkt_legend.append("  ")
            mkt_legend.append("━━", style=f"bold {color}")
            mkt_legend.append(f" {name} ", style="dim")
            mkt_legend.append(f"{score}", style=f"bold {color}")
            mkt_legend.append(f"/{max_s}", style="dim")

        breakdown_t = Table(show_header=False, box=None, expand=True, padding=0)
        breakdown_t.add_column(ratio=1)
        breakdown_t.add_row(Align.center(Text("GEO", style=f"bold {_COLORS['brand_1']}")))
        breakdown_t.add_row(Align.center(geo_bar))
        breakdown_t.add_row(Align.center(geo_legend))
        breakdown_t.add_row(Text())
        breakdown_t.add_row(Align.center(Text("Marketing", style=f"bold {_COLORS['foundation']}")))
        breakdown_t.add_row(Align.center(mkt_legend))

        con.print()
        con.print(
            Panel(
                breakdown_t,
                title="[bold]📊 Score Breakdown[/]",
                title_align="left",
                border_style=_COLORS["brand_1"],
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
        _section_error("score breakdown", exc)
    _flush()

    # ── GEO check cards (compact) ─────────────────────────────────────────────
    try:
        con.print()
        con.print(_geo_compact_card(result, geo_cats, con))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
        _section_error("GEO card", exc)
    _flush()

    # ── Copywriting card ─────────────────────────────────────────────────────
    try:
        con.print(_copy_card(mkt.copywriting))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
        _section_error("copywriting card", exc)
    _flush()

    # ── Content Strategy card ────────────────────────────────────────────────
    try:
        con.print(_strategy_card(mkt.content_strategy))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
        _section_error("content strategy card", exc)
    _flush()

    # ── AI Presence card ─────────────────────────────────────────────────────
    try:
        con.print(_presence_card(mkt.ai_presence))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
        _section_error("AI presence card", exc)
    _flush()

    # ── Media card ────────────────────────────────────────────────────────────
    try:
        con.print(_media_card(mkt.media))
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
        _section_error("media card", exc)
    _flush()

    # ── SERP competitor card ───────────────────────────────────────────────────
    if mkt.serp.checked and mkt.serp.competitors:
        try:
            con.print(_serp_card(mkt.serp))
        except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
            _section_error("SERP card", exc)
        _flush()

    # ── CRO + Performance card ────────────────────────────────────────────────
    if result.conversion.checked or result.perf.checked:
        try:
            con.print(_cro_perf_card(result))
        except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
            _section_error("CRO/perf card", exc)
        _flush()

    # ── Broken links card ─────────────────────────────────────────────────────
    links = result.links
    if links.checked and (links.broken_count or links.external_broken_count):
        try:
            con.print(_links_card(links))
        except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
            _section_error("links card", exc)
        _flush()

    # ── Priority actions ──────────────────────────────────────────────────────
    try:
        actions = mkt.priority_actions
        geo_actions = result.next_actions or []

        if actions or geo_actions:
            con.print()
            actions_t = Table(show_header=False, box=None, expand=True, padding=0)
            actions_t.add_column(ratio=1)

            if actions:
                for i, a in enumerate(actions[:10], 1):
                    w_color = (
                        _COLORS["excellent"]
                        if a.priority == "P1"
                        else _COLORS["foundation"]
                        if a.priority == "P2"
                        else _COLORS["dim"]
                    )
                    imp_color = _COLORS["excellent"] if a.impact == "high" else _COLORS["foundation"]
                    row1 = Text()
                    row1.append(f"  {i:2}. ", style=f"bold {_COLORS['dim']}")
                    row1.append(f"[{a.priority}]", style=f"bold {w_color}")
                    row1.append(f"  {a.title}", style="bold white")
                    row2 = Text()
                    row2.append("      impact=", style=_COLORS["dim"])
                    row2.append(a.impact, style=f"bold {imp_color}")
                    row2.append(f"  effort={a.effort}", style=_COLORS["dim"])
                    row2.append("  skill=", style=_COLORS["dim"])
                    row2.append(a.skill, style=_COLORS["accent"])
                    if a.estimated_lift:
                        row2.append(f"  {a.estimated_lift}", style=_COLORS["excellent"])
                    actions_t.add_row(row1)
                    actions_t.add_row(row2)
                    if a.why:
                        why_t = Text()
                        why_t.append(f"      {a.why[:90]}", style=f"italic {_COLORS['dim']}")
                        actions_t.add_row(why_t)
                    actions_t.add_row(Text())

            if geo_actions:
                actions_t.add_row(Text("  — GEO Next Actions —", style=f"dim {_COLORS['dim']}"))
                actions_t.add_row(Text())
                for a in geo_actions[:5]:
                    w_color = _COLORS["excellent"] if a.priority == "P1" else _COLORS["foundation"]
                    row = Text()
                    row.append(f"  ▸  [{a.priority}]", style=f"bold {w_color}")
                    row.append(f"  {a.title}", style="bold white")
                    row.append(f"  (+{a.expected_score_gain} pts)", style=_COLORS["excellent"])
                    actions_t.add_row(row)
                    if a.why:
                        why_t = Text()
                        why_t.append(f"      {a.why[:90]}", style=f"italic {_COLORS['dim']}")
                        actions_t.add_row(why_t)
                    actions_t.add_row(Text())

            con.print(
                Panel(
                    actions_t,
                    title="[bold]💡 Priority Actions[/]",
                    title_align="left",
                    border_style=_COLORS["foundation"],
                    box=box.ROUNDED,
                    padding=(1, 1),
                )
            )
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
        _section_error("priority actions", exc)
    _flush()

    # ── Footer ───────────────────────────────────────────────────────────────
    try:
        con.print()
        motiv = {
            "excellent": "Your site is AI-ready and marketing-strong. Keep it up! 🚀",
            "good": "Great foundation. A few marketing tweaks to reach excellence.",
            "foundation": "Follow the priority actions — every point counts.",
            "critical": "Start with the [now] actions — quick wins unlock visibility fast.",
        }.get(geo_band_key, "")
        if motiv:
            con.print(Align.center(Text(motiv, style=f"italic {_COLORS['dim']}")))
        con.print()
        con.print(Align.center(Text(REPO_SEO_PROGRAM_FOOTER, style=_COLORS["dim"])))
        con.print(
            Align.center(
                Text("GEOSITION  •  github.com/arnaudbellemare/geosition", style=f"{_COLORS['dim']} underline")
            )
        )
        con.print()
    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
        _section_error("footer", exc)
    _flush()


# ─── Detail cards ─────────────────────────────────────────────────────────────


def _geo_compact_card(result, cats, _con=None):
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    seg_colors = [
        _COLORS["brand_1"],
        _COLORS["brand_2"],
        _COLORS["accent"],
        _COLORS["excellent"],
        _COLORS["foundation"],
        _COLORS["good"],
        _COLORS["brand_3"],
        _COLORS["dim"],
    ]

    t = Table(show_header=False, box=None, expand=True, padding=0)
    t.add_column(ratio=1)

    bar = _micro_bar(result.score)
    if bar:
        t.add_row(bar)
        t.add_row(Text())

    # Category grid 4-per-row
    row = Text("  ")
    for i, (name, score, max_s) in enumerate(cats):
        color = seg_colors[i % len(seg_colors)]
        icon = "✓" if score >= max_s * 0.6 else ("~" if score >= max_s * 0.3 else "✗")
        icon_color = (
            _COLORS["excellent"] if icon == "✓" else _COLORS["foundation"] if icon == "~" else _COLORS["critical"]
        )
        row.append(f"{icon} ", style=icon_color)
        row.append(f"{name} ", style="white")
        row.append(f"{score}/{max_s}", style=f"bold {color}")
        row.append("   ")
        if (i + 1) % 4 == 0 and i < len(cats) - 1:
            t.add_row(row)
            row = Text("  ")
    if row.plain.strip():
        t.add_row(row)

    # robots.txt quick flags
    if result.robots.found:
        rob = Text("  ")
        for label, ok in [
            ("robots.txt", result.robots.found),
            ("sitemap.xml", getattr(result.robots, "has_sitemap", False)),
        ]:
            rob.append("✓ " if ok else "✗ ", style=_COLORS["excellent"] if ok else _COLORS["dim"])
            rob.append(f"{label}  ", style=_COLORS["dim"])
        t.add_row(Text())
        t.add_row(rob)

    color = _score_color(result.score)
    return Panel(
        t,
        title="[bold]🤖 GEO — AI Visibility[/]",
        title_align="left",
        subtitle=f"[bold {color}]{result.score}/100[/]",
        subtitle_align="right",
        border_style=color,
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _copy_card(copy):
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    t = Table(show_header=False, box=None, expand=True, padding=0)
    t.add_column(ratio=1)

    bar = _micro_bar(copy.copy_score)
    if bar:
        t.add_row(bar)
        t.add_row(Text())

    def _row(ok, label):
        icon = "✓" if ok else "✗"
        color = _COLORS["excellent"] if ok else _COLORS["critical"]
        line = Text("  ")
        line.append(f"{icon} ", style=color)
        line.append(label, style="white" if ok else _COLORS["dim"])
        t.add_row(line)

    h1_label = f'H1: "{copy.h1_text[:55]}"' if copy.h1_text else "H1: (missing)"
    _row(copy.h1_is_outcome_focused, h1_label)
    _row(copy.has_value_prop_in_hero, "Value proposition above fold")

    # CTAs
    cta_line = Text("  ")
    if copy.strong_ctas:
        cta_line.append("✓ ", style=_COLORS["excellent"])
        cta_line.append(f"Strong CTAs: {', '.join(copy.strong_ctas[:3])}", style=_COLORS["excellent"])
    elif copy.weak_ctas:
        cta_line.append("✗ ", style=_COLORS["critical"])
        cta_line.append(f"Weak CTAs only: {', '.join(copy.weak_ctas[:3])}", style=_COLORS["dim"])
    else:
        cta_line.append("~ ", style=_COLORS["foundation"])
        cta_line.append("No CTAs detected", style=_COLORS["dim"])
    t.add_row(cta_line)

    # Benefit ratio
    pct = round(copy.benefit_ratio * 100)
    ratio_ok = copy.benefit_ratio >= 0.4
    ratio_mid = copy.benefit_ratio >= 0.25
    r_line = Text("  ")
    r_line.append(
        "✓ " if ratio_ok else ("~ " if ratio_mid else "✗ "),
        style=_COLORS["excellent"] if ratio_ok else _COLORS["foundation"] if ratio_mid else _COLORS["critical"],
    )
    r_line.append(f"Benefit language: {pct}%  ", style="white")
    r_line.append(f"(you/your: {copy.benefit_phrases}  •  we/our: {copy.feature_phrases})", style=_COLORS["dim"])
    t.add_row(r_line)

    color = _score_color(copy.copy_score)
    return Panel(
        t,
        title="[bold]✍️  Copywriting[/]",
        title_align="left",
        subtitle=f"[bold {color}]{copy.copy_score}/100[/]",
        subtitle_align="right",
        border_style=color,
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _strategy_card(strat):
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    t = Table(show_header=False, box=None, expand=True, padding=0)
    t.add_column(ratio=1)

    bar = _micro_bar(strat.content_score)
    if bar:
        t.add_row(bar)
        t.add_row(Text())

    checks = [
        (
            strat.has_blog,
            f"Blog / content hub  ({strat.estimated_article_count} articles)"
            if strat.has_blog
            else "No blog / content hub found",
        ),
        (
            strat.has_faq_section,
            f"FAQ section{'  +FAQPage schema' if strat.has_faq_schema else ''}"
            if strat.has_faq_section
            else "No FAQ section",
        ),
        (
            strat.has_comparison_pages,
            f"Comparison pages ({len(strat.comparison_urls)} found)"
            if strat.has_comparison_pages
            else "No comparison / alternatives pages",
        ),
        (strat.has_pricing_page, "Pricing page linked" if strat.has_pricing_page else "No pricing page"),
        (
            strat.has_email_capture,
            "Email capture / lead magnet present" if strat.has_email_capture else "No email capture",
        ),
        (
            strat.has_numbers_proof,
            "Quantified social proof present"
            if strat.has_numbers_proof
            else "No quantified social proof  (customer counts, improvement %)",
        ),
        (
            strat.has_case_studies,
            "Case studies / success stories" if strat.has_case_studies else "No case studies detected",
        ),
    ]
    for ok, label in checks:
        line = Text("  ")
        line.append("✓ " if ok else "✗ ", style=_COLORS["excellent"] if ok else _COLORS["critical"])
        line.append(label, style="white" if ok else _COLORS["dim"])
        t.add_row(line)

    color = _score_color(strat.content_score)
    return Panel(
        t,
        title="[bold]📋 Content Strategy[/]",
        title_align="left",
        subtitle=f"[bold {color}]{strat.content_score}/100[/]",
        subtitle_align="right",
        border_style=color,
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _presence_card(presence):
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    t = Table(show_header=False, box=None, expand=True, padding=0)
    t.add_column(ratio=1)

    bar = _micro_bar(presence.presence_score)
    if bar:
        t.add_row(bar)
        t.add_row(Text())

    # robots.txt
    if presence.robots_txt_fetched:
        ok = not presence.blocked_ai_bots
        line = Text("  ")
        line.append("✓ " if ok else "✗ ", style=_COLORS["excellent"] if ok else _COLORS["critical"])
        if ok:
            line.append("AI crawlers allowed in robots.txt", style="white")
        else:
            line.append(f"AI bots BLOCKED: {', '.join(presence.blocked_ai_bots)}", style=_COLORS["critical"])
        t.add_row(line)
    else:
        skip = Text("  ")
        skip.append("~  robots.txt not checked", style=_COLORS["dim"])
        t.add_row(skip)

    # Definition block
    def_line = Text("  ")
    if presence.has_definition_block:
        def_line.append("✓ ", style=_COLORS["excellent"])
        snippet = f'"{presence.definition_snippet[:60]}…"' if presence.definition_snippet else ""
        def_line.append(f"Definition block found  {snippet}", style="white")
    else:
        def_line.append("✗ ", style=_COLORS["critical"])
        def_line.append("No definition block in first 300 words", style=_COLORS["dim"])
    t.add_row(def_line)

    # Statistics attribution
    stat_line = Text("  ")
    if presence.has_attributed_stats and presence.unattributed_stat_count == 0:
        stat_line.append("✓ ", style=_COLORS["excellent"])
        stat_line.append("Statistics attributed with source/year", style="white")
    elif presence.has_attributed_stats:
        stat_line.append("~ ", style=_COLORS["foundation"])
        stat_line.append(
            f"Some stats attributed  •  {presence.unattributed_stat_count} unattributed", style=_COLORS["foundation"]
        )
    elif presence.unattributed_stat_count > 0:
        stat_line.append("✗ ", style=_COLORS["critical"])
        stat_line.append(
            f"{presence.unattributed_stat_count} bare stat(s) — add source citations", style=_COLORS["dim"]
        )
    else:
        stat_line.append("~  No statistics found (add cited data for AI citability)", style=_COLORS["dim"])
    t.add_row(stat_line)

    # JS rendering
    js_line = Text("  ")
    js_line.append(
        "✗ " if presence.js_heavy else "✓ ", style=_COLORS["critical"] if presence.js_heavy else _COLORS["excellent"]
    )
    js_line.append(
        "JS-heavy — AI crawlers may miss content" if presence.js_heavy else "Content server-rendered (AI-readable)",
        style=_COLORS["dim"] if presence.js_heavy else "white",
    )
    t.add_row(js_line)

    # Location pages
    loc_line = Text("  ")
    if presence.has_location_pages:
        loc_line.append("✓ ", style=_COLORS["excellent"])
        loc_line.append(f"Location pages: {presence.location_page_count} found", style="white")
    else:
        loc_line.append("✗ ", style=_COLORS["critical"])
        loc_line.append("No location-specific pages  (/[service]-montreal/, etc.)", style=_COLORS["dim"])
    t.add_row(loc_line)

    # Entity schema
    schema_line = Text("  ")
    schema_line.append(
        "✓ " if presence.has_org_sameas else "✗ ",
        style=_COLORS["excellent"] if presence.has_org_sameas else _COLORS["critical"],
    )
    schema_line.append(
        "Organization sameAs links in schema"
        if presence.has_org_sameas
        else "No Organization sameAs  (LinkedIn, Google Business, Wikidata)",
        style="white" if presence.has_org_sameas else _COLORS["dim"],
    )
    t.add_row(schema_line)

    color = _score_color(presence.presence_score)
    return Panel(
        t,
        title="[bold]🔍 AI Presence[/]",
        title_align="left",
        subtitle=f"[bold {color}]{presence.presence_score}/100[/]",
        subtitle_align="right",
        border_style=color,
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _cro_perf_card(result):
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    t = Table(show_header=False, box=None, expand=True, padding=0)
    t.add_column(ratio=1)
    t.add_column(ratio=1)

    conv = result.conversion
    perf = result.perf

    # CRO column
    conv_parts = [_micro_bar(conv.conversion_score) or Text(f"{conv.conversion_score}/100")]
    conv_parts.append(Text())
    for s in (conv.signals or [])[:6]:
        line = Text("  ")
        line.append("✓ " if s.detected else "✗ ", style=_COLORS["excellent"] if s.detected else _COLORS["critical"])
        line.append(s.label[:40], style="white" if s.detected else _COLORS["dim"])
        conv_parts.append(line)

    # Perf column
    perf_parts = [_micro_bar(perf.perf_score) or Text(f"{perf.perf_score}/100")]
    perf_parts.append(Text())
    for label, val in [
        ("Render-blocking scripts", perf.render_blocking_scripts),
        ("Render-blocking styles", perf.render_blocking_styles),
        ("Images missing dimensions", perf.images_missing_dimensions),
        ("Images missing lazy-load", perf.images_missing_lazy),
    ]:
        ok = val == 0
        line = Text("  ")
        line.append("✓ " if ok else "✗ ", style=_COLORS["excellent"] if ok else _COLORS["critical"])
        line.append(f"{label}: {val}", style="white" if ok else _COLORS["dim"])
        perf_parts.append(line)

    # Build inner tables for each column
    conv_t = Table(show_header=False, box=None, expand=True, padding=0)
    conv_t.add_column(ratio=1)
    for p in conv_parts:
        conv_t.add_row(p)

    perf_t = Table(show_header=False, box=None, expand=True, padding=0)
    perf_t.add_column(ratio=1)
    for p in perf_parts:
        perf_t.add_row(p)

    t.add_row(conv_t, perf_t)

    conv_color = _score_color(conv.conversion_score)
    perf_color = _score_color(perf.perf_score)
    return Panel(
        t,
        title=f"[bold]🎯 Conversion[/]  [{conv_color}]{conv.conversion_score}/100[/{conv_color}]"
        f"   [bold]⚡ Performance[/]  [{perf_color}]{perf.perf_score}/100[/{perf_color}]",
        title_align="left",
        border_style=_score_color(min(conv.conversion_score, perf.perf_score)),
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _media_card(media):
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    t = Table(show_header=False, box=None, expand=True, padding=0)
    t.add_column(ratio=1)

    bar = _micro_bar(media.media_score)
    if bar:
        t.add_row(bar)
        t.add_row(Text())

    if not media.checked or (media.video_count == 0 and media.audio_count == 0):
        line = Text("  ")
        line.append("~  ", style=_COLORS["dim"])
        line.append("No video or audio found on page.", style=_COLORS["dim"])
        t.add_row(line)
        if media.suggestions:
            sug = Text("  ")
            sug.append("💡 ", style=_COLORS["accent"])
            sug.append(media.suggestions[0][:90], style=_COLORS["dim"])
            t.add_row(sug)
    else:
        # Summary line
        summary = Text("  ")
        summary.append(f"🎬 {media.video_count} video(s)", style="bold white")
        summary.append("  ", style="default")
        summary.append(f"🔊 {media.audio_count} audio file(s)", style="bold white")
        t.add_row(summary)
        t.add_row(Text())

        for issue in media.issues:
            line = Text("  ")
            line.append("✗  ", style=_COLORS["critical"])
            line.append(issue[:100], style=_COLORS["dim"])
            t.add_row(line)

        if not media.issues:
            ok = Text("  ")
            ok.append("✓  ", style=_COLORS["excellent"])
            ok.append("All media assets appear optimized for mobile.", style="white")
            t.add_row(ok)

    color = _score_color(media.media_score)
    return Panel(
        t,
        title="[bold]🎬 Media Optimization[/]",
        title_align="left",
        subtitle=f"[bold {color}]{media.media_score}/100[/]",
        subtitle_align="right",
        border_style=color,
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _serp_card(serp):
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    t = Table(show_header=False, box=None, expand=True, padding=0)
    t.add_column(ratio=1)

    # Keyword line
    kw_line = Text("  ")
    kw_line.append("🔑 Keyword: ", style=f"bold {_COLORS['brand_2']}")
    kw_line.append(serp.keyword, style="bold white")
    kw_line.append(f"  ({serp.search_engine} first page)", style=_COLORS["dim"])
    t.add_row(kw_line)
    t.add_row(Text())

    # Word count gap
    wc_ok = serp.word_count_gap <= 100
    wc_line = Text("  ")
    wc_line.append("✓ " if wc_ok else "✗ ", style=_COLORS["excellent"] if wc_ok else _COLORS["critical"])
    wc_line.append(
        f"Your content: {serp.your_word_count} words  "
        f"│  Competitor avg: {serp.avg_competitor_word_count} words"
        + (f"  │  Gap: {serp.word_count_gap} words" if serp.word_count_gap > 0 else ""),
        style="white" if wc_ok else _COLORS["dim"],
    )
    t.add_row(wc_line)

    # Schema / FAQ / Video
    for label, count, total in [
        ("Schema", serp.competitors_with_schema, 10),
        ("FAQ", serp.competitors_with_faq, 10),
        ("Video", serp.competitors_with_video, 10),
    ]:
        bad = count >= total // 2
        line = Text("  ")
        line.append("✗ " if bad else "~  ", style=_COLORS["critical"] if bad else _COLORS["foundation"])
        line.append(f"{count}/{total} competitors use {label}", style=_COLORS["dim"])
        if bad:
            line.append("  ← you need this", style=f"italic {_COLORS['critical']}")
        t.add_row(line)

    t.add_row(Text())

    # Top competitor table
    top_t = Table(show_header=True, box=box.SIMPLE, padding=(0, 1))
    top_t.add_column("#", width=3, style=_COLORS["dim"])
    top_t.add_column("URL", width=36, no_wrap=True)
    top_t.add_column("Words", width=7, justify="right")
    top_t.add_column("H2s", width=5, justify="right")
    top_t.add_column("Schema", width=7, justify="center")
    top_t.add_column("FAQ", width=5, justify="center")

    for c in serp.competitors[:10]:
        domain = c.url.split("/")[2] if "/" in c.url else c.url
        schema_str = "✓" if c.has_schema else "✗"
        faq_str = "✓" if c.has_faq else "✗"
        top_t.add_row(
            str(c.rank),
            domain[:36],
            str(c.word_count) if c.word_count else "—",
            str(c.h2_count) if c.h2_count else "—",
            schema_str,
            faq_str,
        )
    t.add_row(top_t)

    # Location page suggestions
    if serp.location_page_suggestions:
        t.add_row(Text())
        loc_hdr = Text("  ")
        loc_hdr.append("📍 Location pages to create:", style=f"bold {_COLORS['accent']}")
        t.add_row(loc_hdr)
        chunks = serp.location_page_suggestions[:12]
        row_text = Text("  ")
        for i, slug in enumerate(chunks):
            row_text.append(slug, style=_COLORS["brand_2"])
            row_text.append("  ")
            if (i + 1) % 3 == 0:
                t.add_row(row_text)
                row_text = Text("  ")
        if row_text.plain.strip():
            t.add_row(row_text)

    return Panel(
        t,
        title="[bold]🔍 Google First-Page Competitor Analysis[/]",
        title_align="left",
        border_style=_COLORS["accent"],
        box=box.ROUNDED,
        padding=(1, 2),
    )


def _links_card(links):
    from rich import box
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text

    t = Table(show_header=False, box=None, expand=True, padding=0)
    t.add_column(ratio=1)

    def _issue_row(issue, label_prefix=""):
        line = Text("  ")
        line.append("✗ ", style=_COLORS["critical"])
        domain = issue.url[:60]
        line.append(f"{label_prefix}HTTP {issue.status}  ", style=_COLORS["critical"])
        line.append(domain, style=_COLORS["dim"])
        if issue.anchor_text:
            line.append(f'  ("{issue.anchor_text[:40]}")', style=_COLORS["dim"])
        return line

    if links.broken_count:
        hdr = Text("  ")
        hdr.append(f"⚠  {links.broken_count} internal broken link(s)", style=f"bold {_COLORS['critical']}")
        t.add_row(hdr)
        for issue in links.broken_links[:10]:
            t.add_row(_issue_row(issue))
        t.add_row(Text())

    if links.external_broken_count:
        hdr = Text("  ")
        hdr.append(f"⚠  {links.external_broken_count} external broken link(s)", style=f"bold {_COLORS['foundation']}")
        t.add_row(hdr)
        for issue in links.external_broken_links[:10]:
            t.add_row(_issue_row(issue, "ext "))
        t.add_row(Text())

    total = links.broken_count + links.external_broken_count
    color = _COLORS["critical"] if links.broken_count else _COLORS["foundation"]
    return Panel(
        t,
        title="[bold]🔗 Broken Links[/]",
        title_align="left",
        subtitle=f"[bold {color}]{total} broken[/]",
        subtitle_align="right",
        border_style=color,
        box=box.ROUNDED,
        padding=(1, 2),
    )


# ─── Plain fallback ───────────────────────────────────────────────────────────


def _print_plain(url, result, mkt, rival_url, rival_result, rival_mkt):
    from geo_optimizer.cli.scoring_helpers import (
        brand_entity_score as _be_score,
    )
    from geo_optimizer.cli.scoring_helpers import (
        content_score as _c_score,
    )
    from geo_optimizer.cli.scoring_helpers import (
        llms_score as _l_score,
    )
    from geo_optimizer.cli.scoring_helpers import (
        meta_score as _m_score,
    )
    from geo_optimizer.cli.scoring_helpers import (
        robots_score as _r_score,
    )
    from geo_optimizer.cli.scoring_helpers import (
        schema_score as _s_score,
    )
    from geo_optimizer.cli.scoring_helpers import (
        signals_score as _sig_score,
    )
    from geo_optimizer.core.scoring import _score_ai_discovery

    w = 66
    copy = mkt.copywriting
    strat = mkt.content_strategy
    pres = mkt.ai_presence
    conv = result.conversion
    perf = result.perf

    geo_cats = [
        ("Robots", _r_score(result), 18),
        ("llms.txt", _l_score(result), 18),
        ("Schema", _s_score(result), 16),
        ("Meta", _m_score(result), 14),
        ("Content", _c_score(result), 12),
        ("Signals", _sig_score(result), 6),
        ("Brand", _be_score(result), 10),
        ("AI Disc.", _score_ai_discovery(result.ai_discovery) if result.ai_discovery else 0, 6),
    ]

    def section(title):
        click.echo(f"\n{'─' * w}")
        click.echo(f"  {title}")
        click.echo("─" * w)

    def check(ok, label):
        click.echo(f"  {'✓' if ok else '✗'}  {label}")

    def bar(score, width=20):
        filled = int(score * width / 100)
        return "█" * filled + "░" * (width - filled)

    # ── Score summary ─────────────────────────────────────────────────────────
    click.echo(f"\n{'=' * w}")
    click.echo(f"  FULL AUDIT — {url}")
    click.echo("=" * w)
    click.echo(f"  GEO (AI Visibility)     {result.score:>3}/100  {bar(result.score)}  {_band(result.score)[1]}")
    click.echo(
        f"  Marketing Readiness     {mkt.marketing_score:>3}/100  {bar(mkt.marketing_score)}  {_band(mkt.marketing_score)[1]}"
    )
    click.echo(f"    Copywriting           {copy.copy_score:>3}/100")
    click.echo(f"    Content Strategy      {strat.content_score:>3}/100")
    click.echo(f"    AI Presence           {pres.presence_score:>3}/100")
    click.echo(f"  Conversion (CRO)        {conv.conversion_score:>3}/100  {bar(conv.conversion_score)}")
    click.echo(f"  Performance             {perf.perf_score:>3}/100  {bar(perf.perf_score)}")

    # ── Rival comparison ──────────────────────────────────────────────────────
    if rival_result and not rival_result.error and rival_mkt:
        section(f"🏁  VS  {rival_url}")
        r_copy = rival_mkt.copywriting
        r_strat = rival_mkt.content_strategy
        r_pres = rival_mkt.ai_presence
        rows = [
            ("GEO (AI Visibility)", result.score, rival_result.score),
            ("Marketing Readiness", mkt.marketing_score, rival_mkt.marketing_score),
            ("  Copywriting", copy.copy_score, r_copy.copy_score),
            ("  Content Strategy", strat.content_score, r_strat.content_score),
            ("  AI Presence", pres.presence_score, r_pres.presence_score),
            ("Conversion (CRO)", conv.conversion_score, rival_result.conversion.conversion_score),
            ("Performance", perf.perf_score, rival_result.perf.perf_score),
        ]
        click.echo(f"  {'Dimension':<24}  {'You':>5}  {'Rival':>5}  {'Delta':>6}")
        click.echo(f"  {'─' * 24}  {'─' * 5}  {'─' * 5}  {'─' * 6}")
        for dim, you, rival in rows:
            d = you - rival
            delta = f"{'+' if d > 0 else ''}{d}"
            flag = "▲" if d > 0 else ("▼" if d < 0 else "=")
            click.echo(f"  {dim:<24}  {you:>5}  {rival:>5}  {flag} {delta:>4}")

    # ── GEO breakdown ─────────────────────────────────────────────────────────
    section("🤖  GEO — AI VISIBILITY BREAKDOWN")
    click.echo(f"  {'Category':<12}  {'Score':>5}  {'Max':>4}  {'Bar':<16}  Status")
    click.echo(f"  {'─' * 12}  {'─' * 5}  {'─' * 4}  {'─' * 16}  {'─' * 10}")
    for name, score, max_s in geo_cats:
        cat_bar_w = 16
        filled = int(score / max_s * cat_bar_w) if max_s else 0
        cat_bar = "█" * filled + "░" * (cat_bar_w - filled)
        pct = score / max_s if max_s else 0
        status = "excellent" if pct >= 0.8 else ("good" if pct >= 0.6 else ("partial" if pct >= 0.3 else "missing"))
        click.echo(f"  {name:<12}  {score:>5}  {max_s:>4}  {cat_bar}  {status}")

    if result.recommendations:
        click.echo("\n  Recommendations:")
        for rec in result.recommendations[:5]:
            click.echo(f"    • {rec}")

    # ── Copywriting ───────────────────────────────────────────────────────────
    section("✍️  COPYWRITING")
    check(copy.h1_is_outcome_focused, f'H1: "{copy.h1_text[:55]}"' if copy.h1_text else "H1: (missing)")
    check(copy.has_value_prop_in_hero, "Value proposition above fold")
    if copy.strong_ctas:
        click.echo(f"  ✓  Strong CTAs: {', '.join(copy.strong_ctas[:3])}")
    if copy.weak_ctas:
        click.echo(f"  ✗  Weak CTAs:   {', '.join(copy.weak_ctas[:3])}")
    click.echo(
        f"  {'✓' if copy.benefit_ratio >= 0.4 else '✗'}  Benefit language: {round(copy.benefit_ratio * 100)}%"
        f"  (benefit phrases: {copy.benefit_phrases}  feature/we phrases: {copy.feature_phrases})"
    )
    # H2 quality
    h2q = copy.h2_keyword_quality
    h2_icon = "✓" if h2q == "good" else ("✗" if h2q in ("ai-focused", "missing") else "~")
    h2_label = {
        "good": f"H2 headings keyword-focused ({copy.h2_service_count}/{copy.h2_count} with service keywords)",
        "generic": f"H2 headings generic — {copy.h2_service_count}/{copy.h2_count} with service keywords",
        "ai-focused": f"H2 headings AI-optimised, not Google-keyword-focused ({copy.h2_count} H2s)",
        "missing": "No H2 headings found",
    }.get(h2q, f"H2 headings: {copy.h2_count}")
    click.echo(f"  {h2_icon}  {h2_label}")
    if copy.h2_samples and h2q in ("ai-focused", "generic"):
        click.echo(f'     e.g. "{copy.h2_samples[0][:60]}"')

    # ── Images ────────────────────────────────────────────────────────────────
    img = mkt.image_audit
    section(f"🖼️   IMAGES  ({img.image_score}/100)")
    if img.total_images == 0:
        click.echo("  ✗  No images on page — missing a major Google ranking signal")
    else:
        click.echo(f"  📷  {img.total_images} image(s) found")
        check(
            img.images_missing_alt == 0,
            f"Alt text: {img.total_images - img.images_missing_alt}/{img.total_images} have alt",
        )
        check(
            img.images_keyword_filename > 0,
            f"Keyword filenames: {img.images_keyword_filename}/{img.total_images} match service/city",
        )
        check(img.images_webp > 0, f"WebP format: {img.images_webp}/{img.total_images} use WebP")
        check(
            img.images_keyword_alt > 0,
            f"Keyword alt text: {img.images_keyword_alt}/{img.total_images} mention service/city",
        )
        check(
            img.images_missing_dimensions == 0,
            f"Dimensions set: {img.total_images - img.images_missing_dimensions}/{img.total_images}",
        )

    # ── Content Strategy ──────────────────────────────────────────────────────
    section("📋  CONTENT STRATEGY")
    check(
        strat.has_blog,
        f"Blog — {strat.estimated_article_count} articles" if strat.has_blog else "No blog / content hub",
    )
    check(strat.has_faq_section, "FAQ section" + (" + FAQPage schema" if strat.has_faq_schema else ""))
    check(strat.has_comparison_pages, "Comparison / alternatives pages")
    check(strat.has_pricing_page, "Pricing page")
    check(strat.has_email_capture, "Email capture / lead magnet")
    check(strat.has_numbers_proof, "Quantified social proof")
    check(strat.has_case_studies, "Case studies / success stories")
    # Internal links
    il = strat.internal_link_count
    il_ok = il >= 10
    click.echo(
        f"  {'✓' if il_ok else '✗'}  Internal links: {il} found{'  (need 10+ for healthy site structure)' if not il_ok else ''}"
    )
    # LocalBusiness schema
    lb = "✓" if strat.has_local_business_schema else "✗"
    lb_detail = ""
    if strat.has_local_business_schema:
        missing_fields = [
            f
            for f, v in [
                ("address", strat.local_business_has_address),
                ("phone", strat.local_business_has_phone),
                ("hours", strat.local_business_has_hours),
                ("geo", strat.local_business_has_geo),
            ]
            if not v
        ]
        lb_detail = "  ✓ complete" if not missing_fields else f"  missing: {', '.join(missing_fields)}"
    click.echo(f"  {lb}  LocalBusiness schema{lb_detail}")
    # Industry memberships
    if strat.has_industry_memberships:
        click.echo(f"  ✓  Industry memberships: {', '.join(strat.industry_membership_names)}")
    else:
        click.echo("  ✗  No industry association memberships found (trust + backlink source)")

    # ── AI Presence ───────────────────────────────────────────────────────────
    section("🔍  AI PRESENCE")
    if pres.robots_txt_fetched:
        check(
            not pres.blocked_ai_bots,
            "AI crawlers allowed (GPTBot, PerplexityBot, ClaudeBot, Google-Extended)"
            if not pres.blocked_ai_bots
            else f"AI bots BLOCKED: {', '.join(pres.blocked_ai_bots)}",
        )
    else:
        click.echo("  ~  robots.txt not checked")
    check(
        pres.has_definition_block,
        "Definition block in first 300 words"
        + (f': "{pres.definition_snippet[:60]}…"' if pres.definition_snippet else ""),
    )
    if pres.unattributed_stat_count:
        check(
            pres.has_attributed_stats,
            f"Attributed statistics  ({pres.unattributed_stat_count} unattributed also found)",
        )
    else:
        check(pres.has_attributed_stats, "Attributed statistics with source/year")
    check(not pres.js_heavy, "Server-rendered content (AI-readable)")
    check(
        pres.has_location_pages,
        f"Location pages — {pres.location_page_count} found"
        if pres.has_location_pages
        else "No location-specific pages",
    )
    check(pres.has_org_sameas, "Organization sameAs schema (LinkedIn, Wikidata, etc.)")

    # ── Media optimization ───────────────────────────────────────────────────
    media = mkt.media
    section(f"🎬  MEDIA OPTIMIZATION  ({media.media_score}/100)")
    if not media.checked or (media.video_count == 0 and media.audio_count == 0):
        click.echo("  ~  No video or audio found on page.")
        if media.suggestions:
            click.echo(f"  💡 {media.suggestions[0][:90]}")
    else:
        click.echo(f"  🎬  {media.video_count} video(s)   🔊 {media.audio_count} audio file(s)")
        for issue in media.issues:
            click.echo(f"  ✗  {issue[:100]}")
        if not media.issues:
            click.echo("  ✓  All media assets appear optimized for mobile.")

    # ── SERP competitor analysis ──────────────────────────────────────────────
    serp = mkt.serp
    if serp.checked and serp.competitors:
        section(f'🔍  GOOGLE FIRST-PAGE COMPETITORS  —  "{serp.keyword}"')
        click.echo(
            f"  Your content: {serp.your_word_count} words  │  "
            f"Competitor avg: {serp.avg_competitor_word_count} words  │  "
            f"Gap: {serp.word_count_gap} words"
        )
        click.echo()
        click.echo(f"  {'#':<3}  {'Domain':<36}  {'Words':>6}  {'H2s':>4}  {'Schema':>7}  {'FAQ':>4}")
        click.echo(f"  {'─' * 3}  {'─' * 36}  {'─' * 6}  {'─' * 4}  {'─' * 7}  {'─' * 4}")
        for c in serp.competitors[:10]:
            domain = c.url.split("/")[2] if "/" in c.url else c.url
            click.echo(
                f"  {c.rank:<3}  {domain[:36]:<36}  {c.word_count:>6}  "
                f"{c.h2_count:>4}  {'✓' if c.has_schema else '✗':>7}  {'✓' if c.has_faq else '✗':>4}"
            )
        if serp.location_page_suggestions:
            click.echo("\n  📍 Location pages to create:")
            for i, slug in enumerate(serp.location_page_suggestions[:12]):
                click.echo(f"    {slug}", nl=(i + 1) % 4 == 0)
            click.echo()

    # ── CRO + Performance ─────────────────────────────────────────────────────
    section("🎯  CONVERSION (CRO)  &  ⚡ PERFORMANCE")
    if conv.signals:
        for s in conv.signals[:8]:
            check(s.detected, s.label)
    click.echo()
    for label, val in [
        ("Render-blocking scripts", perf.render_blocking_scripts),
        ("Render-blocking styles", perf.render_blocking_styles),
        ("Images missing dimensions", perf.images_missing_dimensions),
        ("Images missing lazy-load", perf.images_missing_lazy),
    ]:
        check(val == 0, f"{label}: {val}")

    # ── Broken links ──────────────────────────────────────────────────────────
    links = result.links
    if links.checked and (links.broken_count or links.external_broken_count):
        section("🔗  BROKEN LINKS")
        if links.broken_count:
            click.echo(f"  Internal: {links.broken_count} broken")
            for issue in links.broken_links[:10]:
                click.echo(f"    ✗  HTTP {issue.status}  {issue.url[:70]}")
        if links.external_broken_count:
            click.echo(f"  External: {links.external_broken_count} broken")
            for issue in links.external_broken_links[:10]:
                click.echo(f"    ✗  HTTP {issue.status}  {issue.url[:70]}")

    # ── Priority Actions ──────────────────────────────────────────────────────
    section("💡  PRIORITY ACTIONS")
    for i, a in enumerate(mkt.priority_actions[:10], 1):
        click.echo(f"  {i:2}. [{a.priority}] {a.title}")
        click.echo(
            f"      impact={a.impact}  effort={a.effort}  skill={a.skill}"
            + (f"  {a.estimated_lift}" if a.estimated_lift else "")
        )
        if a.why:
            click.echo(f"      {a.why[:80]}")

    if result.next_actions:
        click.echo("\n  — GEO Next Actions —")
        for a in result.next_actions[:5]:
            click.echo(f"  ▸  [{a.priority}] {a.title}  (+{a.expected_score_gain} pts)")
            if a.why:
                click.echo(f"      {a.why[:80]}")

    click.echo()
    click.echo(f"  {REPO_SEO_PROGRAM_FOOTER}")
    click.echo()


# ─── Markdown export ──────────────────────────────────────────────────────────


def _build_markdown(url, result, mkt, rival_url, rival_result, rival_mkt) -> str:
    copy = mkt.copywriting
    strat = mkt.content_strategy
    pres = mkt.ai_presence
    conv = result.conversion
    perf = result.perf
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def score_row(label, score, max_s=100):
        band_key, band_label = _band(score)
        bar = "█" * (score // 10) + "░" * (10 - score // 10)
        return f"| {label} | {score}/{max_s} | {bar} | {band_label} |"

    lines = [
        "# Full Audit Report",
        "",
        f"**URL**: {url}",
        f"**Date**: {now}",
        f"**Vertical**: {getattr(result.vertical_profile, 'vertical', None) or 'auto'}",
        "",
        "## Score Summary",
        "",
        "| Dimension | Score | Bar | Band |",
        "|-----------|------:|-----|------|",
        score_row("GEO (AI Visibility)", result.score),
        score_row("Marketing Readiness", mkt.marketing_score),
        score_row("  Copywriting", copy.copy_score),
        score_row("  Content Strategy", strat.content_score),
        score_row("  AI Presence", pres.presence_score),
        score_row("Conversion (CRO)", conv.conversion_score),
        score_row("Performance", perf.perf_score),
        "",
    ]

    # Rival
    if rival_result and not rival_result.error and rival_mkt:
        lines += [
            "## Rival Benchmark",
            "",
            f"**Rival**: {rival_url}",
            "",
            "| Dimension | You | Rival | Delta |",
            "|-----------|----:|------:|------:|",
        ]
        for dim, y, r in [
            ("GEO", result.score, rival_result.score),
            ("Marketing", mkt.marketing_score, rival_mkt.marketing_score),
            ("  Copywriting", copy.copy_score, rival_mkt.copywriting.copy_score),
            ("  Content Strat.", strat.content_score, rival_mkt.content_strategy.content_score),
            ("  AI Presence", pres.presence_score, rival_mkt.ai_presence.presence_score),
            ("CRO", conv.conversion_score, rival_result.conversion.conversion_score),
        ]:
            d = y - r
            lines.append(f"| {dim} | {y} | {r} | {'+' if d > 0 else ''}{d} |")
        lines.append("")

    # GEO breakdown
    lines += ["## GEO — AI Visibility", "", f"Score: **{result.score}/100**", ""]
    from geo_optimizer.cli.scoring_helpers import (
        brand_entity_score as _be,
    )
    from geo_optimizer.cli.scoring_helpers import (
        content_score as _c,
    )
    from geo_optimizer.cli.scoring_helpers import (
        llms_score as _l,
    )
    from geo_optimizer.cli.scoring_helpers import (
        meta_score as _m,
    )
    from geo_optimizer.cli.scoring_helpers import (
        robots_score as _r,
    )
    from geo_optimizer.cli.scoring_helpers import (
        schema_score as _s,
    )
    from geo_optimizer.cli.scoring_helpers import (
        signals_score as _sig,
    )
    from geo_optimizer.core.scoring import _score_ai_discovery

    geo_cats = [
        ("Robots", _r(result), 18),
        ("llms.txt", _l(result), 18),
        ("Schema", _s(result), 16),
        ("Meta", _m(result), 14),
        ("Content", _c(result), 12),
        ("Signals", _sig(result), 6),
        ("Brand", _be(result), 10),
        ("AI Disc.", _score_ai_discovery(result.ai_discovery) if result.ai_discovery else 0, 6),
    ]
    lines.append("| Category | Score | Max |")
    lines.append("|----------|------:|----:|")
    for name, score, max_s in geo_cats:
        lines.append(f"| {name} | {score} | {max_s} |")
    lines.append("")

    if result.recommendations:
        lines += ["**Recommendations:**", ""]
        for rec in result.recommendations[:6]:
            lines.append(f"- {rec}")
        lines.append("")

    # Copywriting
    lines += [
        "## Copywriting",
        "",
        f"Score: **{copy.copy_score}/100**",
        "",
        f'- {"✓" if copy.h1_is_outcome_focused else "✗"} H1: "{copy.h1_text}"',
        f"- {'✓' if copy.has_value_prop_in_hero else '✗'} Value proposition above fold",
    ]
    if copy.strong_ctas:
        lines.append(f"- ✓ Strong CTAs: {', '.join(copy.strong_ctas[:3])}")
    if copy.weak_ctas:
        lines.append(f"- ✗ Weak CTAs: {', '.join(copy.weak_ctas[:3])}")
    lines.append(f"- {'✓' if copy.benefit_ratio >= 0.4 else '✗'} Benefit language: {round(copy.benefit_ratio * 100)}%")
    # H2 quality
    h2q = copy.h2_keyword_quality
    h2_icon = "✓" if h2q == "good" else "✗"
    h2_label = {
        "good": f"H2 headings keyword-focused ({copy.h2_service_count}/{copy.h2_count} with service keywords)",
        "generic": f"H2 headings generic — only {copy.h2_service_count}/{copy.h2_count} with service keywords",
        "ai-focused": f"H2 headings are AI/generic labels, not Google-keyword-focused ({copy.h2_count} H2s)",
        "missing": "No H2 headings found",
    }.get(h2q, f"H2 headings: {copy.h2_count}")
    lines.append(f"- {h2_icon} {h2_label}")
    if copy.issues:
        lines += ["", "**Issues:**"]
        for i in copy.issues:
            lines.append(f"- {i}")
    if copy.suggestions:
        lines += ["", "**Suggestions:**"]
        for s in copy.suggestions:
            lines.append(f"- {s}")
    lines.append("")

    # Images
    img = mkt.image_audit
    lines += ["## Images & Visual SEO", "", f"Score: **{img.image_score}/100**", ""]
    if img.total_images == 0:
        lines.append("- ✗ **No images found** — missing a major Google ranking signal")
    else:
        lines += [
            f"- 📷 {img.total_images} image(s) found",
            f"- {'✓' if img.images_missing_alt == 0 else '✗'} Alt text: {img.total_images - img.images_missing_alt}/{img.total_images} images have alt",
            f"- {'✓' if img.images_keyword_alt > 0 else '✗'} Keyword alt text: {img.images_keyword_alt}/{img.total_images} mention service/city",
            f"- {'✓' if img.images_keyword_filename > 0 else '✗'} Keyword filenames: {img.images_keyword_filename}/{img.total_images} match service/city",
            f"- {'✓' if img.images_webp > 0 else '✗'} WebP format: {img.images_webp}/{img.total_images} use WebP",
            f"- {'✓' if img.images_missing_dimensions == 0 else '✗'} Dimensions set (CLS prevention): {img.total_images - img.images_missing_dimensions}/{img.total_images}",
        ]
    if img.issues:
        lines += ["", "**Issues:**"]
        for i in img.issues:
            lines.append(f"- {i}")
    if img.suggestions:
        lines += ["", "**Suggestions:**"]
        for s in img.suggestions:
            lines.append(f"- {s}")
    lines.append("")

    # Content Strategy
    lines += [
        "## Content Strategy",
        "",
        f"Score: **{strat.content_score}/100**",
        "",
    ]
    for ok, label in [
        (
            strat.has_blog,
            f"Blog ({strat.estimated_article_count} articles)" if strat.has_blog else "Blog / content hub",
        ),
        (strat.has_faq_section, "FAQ section" + (" + FAQPage schema" if strat.has_faq_schema else "")),
        (strat.has_comparison_pages, "Comparison / alternatives pages"),
        (strat.has_pricing_page, "Pricing page"),
        (strat.has_email_capture, "Email capture / lead magnet"),
        (strat.has_numbers_proof, "Quantified social proof"),
        (strat.has_case_studies, "Case studies / success stories"),
    ]:
        lines.append(f"- {'✓' if ok else '✗'} {label}")
    # New checks
    il = strat.internal_link_count
    lines.append(f"- {'✓' if il >= 10 else '✗'} Internal links: {il} (need 10+)")
    lb_ok = strat.has_local_business_schema
    lb_complete = all(
        [
            strat.local_business_has_address,
            strat.local_business_has_phone,
            strat.local_business_has_hours,
            strat.local_business_has_geo,
        ]
    )
    if lb_ok and lb_complete:
        lines.append("- ✓ LocalBusiness schema complete")
    elif lb_ok:
        missing = [
            f
            for f, v in [
                ("address", strat.local_business_has_address),
                ("phone", strat.local_business_has_phone),
                ("hours", strat.local_business_has_hours),
                ("geo", strat.local_business_has_geo),
            ]
            if not v
        ]
        lines.append(f"- ~ LocalBusiness schema present but missing: {', '.join(missing)}")
    else:
        lines.append("- ✗ No LocalBusiness schema (required for Google Maps / Local Pack)")
    if strat.has_industry_memberships:
        lines.append(f"- ✓ Industry memberships: {', '.join(strat.industry_membership_names)}")
    else:
        lines.append("- ✗ No industry association memberships (trust signals + free backlinks)")
    if strat.issues:
        lines += ["", "**Issues:**"]
        for i in strat.issues:
            lines.append(f"- {i}")
    if strat.suggestions:
        lines += ["", "**Suggestions:**"]
        for s in strat.suggestions:
            lines.append(f"- {s}")
    lines.append("")

    # AI Presence
    lines += [
        "## AI Presence",
        "",
        f"Score: **{pres.presence_score}/100**",
        "",
    ]
    if pres.robots_txt_fetched:
        if pres.blocked_ai_bots:
            lines.append(f"- ✗ AI bots blocked: {', '.join(pres.blocked_ai_bots)}")
        else:
            lines.append("- ✓ AI crawlers allowed in robots.txt")
    lines.append(
        f"- {'✓' if pres.has_definition_block else '✗'} Definition block in first 300 words"
        + (f': "{pres.definition_snippet[:80]}…"' if pres.definition_snippet else "")
    )
    if pres.has_attributed_stats:
        lines.append(
            "- ✓ Attributed statistics"
            + (f" ({pres.unattributed_stat_count} unattributed also found)" if pres.unattributed_stat_count else "")
        )
    elif pres.unattributed_stat_count:
        lines.append(f"- ✗ {pres.unattributed_stat_count} unattributed stat(s) — add source citations")
    lines += [
        f"- {'✓' if not pres.js_heavy else '✗'} Server-rendered content",
        f"- {'✓' if pres.has_location_pages else '✗'} Location pages ({pres.location_page_count} found)",
        f"- {'✓' if pres.has_org_sameas else '✗'} Organization sameAs schema",
    ]
    if pres.has_author_schema:
        lines.append("- ✓ Author/Person schema with sameAs")
    if pres.issues:
        lines += ["", "**Issues:**"]
        for i in pres.issues:
            lines.append(f"- {i}")
    if pres.suggestions:
        lines += ["", "**Suggestions:**"]
        for s in pres.suggestions:
            lines.append(f"- {s}")
    lines.append("")

    # Media
    media = mkt.media
    lines += ["## Media Optimization", "", f"Score: **{media.media_score}/100**", ""]
    if not media.checked or (media.video_count == 0 and media.audio_count == 0):
        lines.append("- ~ No video or audio found on page.")
    else:
        lines += [f"- 🎬 {media.video_count} video(s)  🔊 {media.audio_count} audio file(s)", ""]
        for issue in media.issues:
            lines.append(f"- ✗ {issue}")
        if not media.issues:
            lines.append("- ✓ All media assets appear optimized for mobile.")
    if media.suggestions:
        lines += ["", "**Recommendations:**"]
        for s in media.suggestions[:3]:
            lines.append(f"- {s}")
    lines.append("")

    # SERP competitor analysis
    serp = mkt.serp
    if serp.checked and serp.competitors:
        lines += [
            "## Google First-Page Competitor Analysis",
            "",
            f"**Keyword**: {serp.keyword}",
            f"**Your word count**: {serp.your_word_count}  |  "
            f"**Competitor avg**: {serp.avg_competitor_word_count}  |  "
            f"**Gap**: {serp.word_count_gap} words",
            "",
            f"- {serp.competitors_with_schema}/10 competitors use schema markup",
            f"- {serp.competitors_with_faq}/10 competitors have FAQ sections",
            f"- {serp.competitors_with_video}/10 competitors embed video",
            "",
            "| # | Domain | Words | H2s | Schema | FAQ |",
            "|---|--------|------:|----:|:------:|:---:|",
        ]
        for c in serp.competitors[:10]:
            domain = c.url.split("/")[2] if "/" in c.url else c.url
            lines.append(
                f"| {c.rank} | {domain} | {c.word_count or '—'} | {c.h2_count or '—'} "
                f"| {'✓' if c.has_schema else '✗'} | {'✓' if c.has_faq else '✗'} |"
            )
        lines.append("")
        if serp.issues:
            lines += ["**Gaps identified:**"]
            for issue in serp.issues:
                lines.append(f"- {issue}")
            lines.append("")
        if serp.location_page_suggestions:
            lines += ["**Location pages to create:**", ""]
            for slug in serp.location_page_suggestions[:24]:
                lines.append(f"- `{slug}`")
            lines.append("")

    # Conversion
    lines += ["## Conversion Readiness (CRO)", "", f"Score: **{conv.conversion_score}/100**", ""]
    for s in conv.signals:
        lines.append(f"- {'✓' if s.detected else '✗'} {s.label}")
    if conv.priority_fixes:
        lines += ["", "**Priority fixes:**"]
        for f in conv.priority_fixes:
            lines.append(f"- {f}")
    lines.append("")

    # Performance
    lines += [
        "## Performance",
        "",
        f"Score: **{perf.perf_score}/100**",
        "",
        f"- Render-blocking scripts: {perf.render_blocking_scripts}",
        f"- Render-blocking stylesheets: {perf.render_blocking_styles}",
        f"- Images missing dimensions: {perf.images_missing_dimensions}",
        f"- Images missing lazy-load: {perf.images_missing_lazy}",
        "",
    ]

    # Broken links
    links = result.links
    if links.checked and (links.broken_count or links.external_broken_count):
        lines += ["## Broken Links", ""]
        if links.broken_count:
            lines.append(f"**{links.broken_count} internal broken link(s):**")
            lines.append("")
            lines.append("| Status | URL | Anchor |")
            lines.append("|--------|-----|--------|")
            for issue in links.broken_links[:20]:
                lines.append(f"| {issue.status} | {issue.url} | {issue.anchor_text} |")
            lines.append("")
        if links.external_broken_count:
            lines.append(f"**{links.external_broken_count} external broken link(s):**")
            lines.append("")
            lines.append("| Status | URL | Anchor |")
            lines.append("|--------|-----|--------|")
            for issue in links.external_broken_links[:20]:
                lines.append(f"| {issue.status} | {issue.url} | {issue.anchor_text} |")
            lines.append("")

    # Priority Actions
    if mkt.priority_actions:
        lines += ["## Priority Marketing Actions", ""]
        for i, a in enumerate(mkt.priority_actions[:10], 1):
            lines.append(f"### {i}. {a.title}  [{a.priority}]")
            lines += [
                f"- **Why**: {a.why}",
                f"- **Impact**: {a.impact}  |  **Effort**: {a.effort}",
                f"- **Skill**: `{a.skill}`",
            ]
            if a.estimated_lift:
                lines.append(f"- **Estimated lift**: {a.estimated_lift}")
            lines.append("")

    if result.next_actions:
        lines += ["## GEO Next Actions", ""]
        for a in result.next_actions[:6]:
            lines.append(f"- **{a.title}** [{a.priority}] +{a.expected_score_gain} pts — {a.why}")
        lines.append("")

    lines.append(MARKDOWN_SEO_SECTION.rstrip())
    lines.append("")

    return "\n".join(lines)
