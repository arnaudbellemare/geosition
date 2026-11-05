"""
CLI command: geo rivalry

Implements a practical version of the "A vs B vs AB" GEO workflow:
- Incumbent (A): current site state
- Critic: extracts weaknesses
- Author (B): proposes aggressive alternative
- Synthesizer (AB): merges strengths
- Judge panel: selects winner and next moves
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast

import click

from geo_optimizer.core.action_intelligence import CATEGORY_MAX as _CATEGORY_MAX

_CATEGORY_ORDER = ["robots", "llms", "schema", "meta", "content", "signals", "ai_discovery", "brand_entity"]


def _derive_weights(geo: float, trust: float, citation: float) -> dict[str, float]:
    """Compute readiness weights from actual scores — no lookup table.

    The weakest dimension gets the highest weight. A site that scores 40/100
    on trust but 90/100 on GEO needs trust attention, so trust weight rises.
    All three weights sum to 1.0.
    """
    inverse = {
        "geo": 1.0 / max(geo, 1),
        "trust": 1.0 / max(trust, 1),
        "citation": 1.0 / max(citation, 1),
    }
    total = sum(inverse.values())
    return {k: round(v / total, 3) for k, v in inverse.items()}


def _category_summary(a_breakdown: dict, b_breakdown: dict | None) -> dict:
    """Derive a plain-language standing from category scores.

    Weakest category is determined by the largest gap to the category maximum
    (i.e. most points left on the table), not by the lowest absolute score.
    A category already at its ceiling is never flagged as weakest even if its
    absolute score is low — signals (6/6) should not beat llms (14/18).
    """
    if not a_breakdown:
        return {}

    def gap_ratio(k: str) -> float:
        score = a_breakdown.get(k, 0)
        max_score = _CATEGORY_MAX.get(k, score) or 1
        return cast(float, (max_score - score) / max_score)

    weakest_key = max(_CATEGORY_ORDER, key=gap_ratio)
    weakest_val = a_breakdown.get(weakest_key, 0)
    weakest_max = _CATEGORY_MAX.get(weakest_key, weakest_val)
    weakest_gap = weakest_max - weakest_val

    if not b_breakdown:
        return {
            "weakest": weakest_key,
            "weakest_score": weakest_val,
            "weakest_max": weakest_max,
            "weakest_gap": weakest_gap,
        }

    leads = sum(1 for k in _CATEGORY_ORDER if a_breakdown.get(k, 0) > b_breakdown.get(k, 0))
    trails = sum(1 for k in _CATEGORY_ORDER if a_breakdown.get(k, 0) < b_breakdown.get(k, 0))
    ties = len(_CATEGORY_ORDER) - leads - trails

    return {
        "leads": leads,
        "trails": trails,
        "ties": ties,
        "total": len(_CATEGORY_ORDER),
        "weakest": weakest_key,
        "weakest_score": weakest_val,
        "weakest_max": weakest_max,
        "weakest_gap": weakest_gap,
    }


def _build_candidates(audit_result, fix_plan, rival_audit=None):
    """Build A/B/AB candidate scores for the judging panel.

    When rival_audit is provided it is the result of a real competitor audit
    and is used as Candidate B verbatim. Otherwise a synthetic projection is
    built from the incumbent's own scores and fix plan.
    """
    a_trust = audit_result.trust_stack.composite_score * 4 if audit_result.trust_stack else 0
    a = {
        "name": "A",
        "label": "incumbent",
        "geo_score": audit_result.score,
        "citability_score": audit_result.citability.total_score,
        "trust_score": a_trust,
        "score_breakdown": audit_result.score_breakdown or {},
    }

    if rival_audit is not None:
        # Real competitor — use actual audit scores, not math.
        b_trust = rival_audit.trust_stack.composite_score * 4 if rival_audit.trust_stack else 0
        b = {
            "name": "B",
            "label": "rival (real)",
            "geo_score": rival_audit.score,
            "citability_score": rival_audit.citability.total_score,
            "trust_score": b_trust,
            "score_breakdown": rival_audit.score_breakdown or {},
        }
    else:
        # Synthetic projection: best-case after applying all recommendations.
        rec_boost = min(12, len(audit_result.recommendations) * 2)
        b = {
            "name": "B",
            "label": "rival (projected)",
            "geo_score": min(100, audit_result.score + max(4, rec_boost // 2)),
            "citability_score": min(100, audit_result.citability.total_score + max(6, rec_boost)),
            "trust_score": min(100, a_trust + 8),
            "score_breakdown": {},
        }

    # AB: per-category best of A and B, bounded by the fix plan estimate.
    ab_breakdown = {}
    if a["score_breakdown"] and b["score_breakdown"]:
        for k in a["score_breakdown"]:
            ab_breakdown[k] = max(a["score_breakdown"].get(k, 0), b["score_breakdown"].get(k, 0))
    ab = {
        "name": "AB",
        "label": "merged",
        "geo_score": max(audit_result.score, min(100, fix_plan.score_estimated_after)),
        "citability_score": min(100, max(audit_result.citability.total_score, b["citability_score"] - 2)),
        "trust_score": min(100, max(a["trust_score"], b["trust_score"])),
        "score_breakdown": ab_breakdown,
    }
    return [a, ab, b]


def _judge(candidates: list[dict], vertical: str = "generic") -> dict:
    """Score candidates and identify the overall leader.

    Weights are derived from the incumbent's own scores — the weakest
    dimension is weighted highest. No lookup table, no vertical assumption.
    The winner is whichever candidate scores highest on the composite.
    """
    by_name = {c["name"]: c for c in candidates}
    a = by_name["A"]

    weights = _derive_weights(a["geo_score"], a["trust_score"], a["citability_score"])
    geo_w, trust_w, cite_w = weights["geo"], weights["trust"], weights["citation"]

    def composite(c: dict) -> float:
        return cast(float, c["geo_score"] * geo_w + c["trust_score"] * trust_w + c["citability_score"] * cite_w)

    ranked = sorted(candidates, key=composite, reverse=True)
    winner = ranked[0]["name"]

    a_bd = a.get("score_breakdown", {})
    b_bd = by_name["B"].get("score_breakdown", {})
    summary = _category_summary(a_bd, b_bd if b_bd else None)

    return {
        "winner": winner,
        "composite_scores": {c["name"]: round(composite(c), 1) for c in candidates},
        "readiness_weights": weights,
        "category_summary": summary,
        "winner_snapshot": by_name[winner],
    }


def _render_terminal_report(
    audit_result,
    candidates: list[dict],
    panel: dict,
    critic_notes: list[str],
    top_actions: list,
    history_delta: int | None = None,
    page_rows: list[dict] | None = None,
    rival_url: str | None = None,
    mode: str = "projected",
) -> None:
    """Print rich rivalry analysis to terminal."""
    click.echo("")
    click.echo("⚔️  GEO RIVALRY ANALYSIS")
    click.echo("=" * 64)
    click.echo(f"URL: {audit_result.url}")
    if rival_url:
        tag = "real competitor" if mode == "real-competitor" else "projected"
        click.echo(f"Rival: {rival_url} ({tag})")
    click.echo(f"Incumbent score: {audit_result.score}/100 ({audit_result.band})")
    if history_delta is not None:
        click.echo(f"Trend vs previous run: {history_delta:+d}")
    if getattr(audit_result, "vertical_profile", None) and audit_result.vertical_profile.checked:
        vp = audit_result.vertical_profile
        click.echo(
            f"Vertical: {vp.vertical} (detected: {vp.detected_vertical}, confidence: {vp.detection_confidence:.2f})"
        )
        click.echo(f"Business readiness: {vp.business_readiness_score}/100")

    click.echo("")
    click.echo("Candidate scorecards:")
    for c in candidates:
        click.echo(
            f"  - {c['name']} ({c['label']}): "
            f"GEO={c['geo_score']} | Citability={c['citability_score']} | Trust={c['trust_score']}"
        )

    rw = panel.get("readiness_weights", {})
    cs = panel.get("composite_scores", {})
    summary = panel.get("category_summary", {})

    click.echo("")
    click.echo(f"Winner: {panel['winner']}")
    click.echo("Composite scores: " + " | ".join(f"{n}={v}" for n, v in cs.items()))
    click.echo(
        f"Weights (auto): geo={rw.get('geo', 0):.0%}  "
        f"trust={rw.get('trust', 0):.0%}  "
        f"citation={rw.get('citation', 0):.0%}  "
        f"← derived from weakest dimension"
    )
    if summary:
        if "leads" in summary:
            click.echo(
                f"Standing: leads {summary['leads']}/{summary['total']} categories, "
                f"trails {summary['trails']}, ties {summary['ties']}"
            )
        click.echo(
            f"Weakest category: {summary['weakest']} "
            f"({summary['weakest_score']}/{summary['weakest_max']}, "
            f"gap={summary['weakest_gap']})"
        )

    if page_rows:
        click.echo("")
        click.echo("Pages to prioritize (lowest scores first):")
        for row in page_rows[:8]:
            status = f"HTTP {row['http_status']}" if row["http_status"] else "n/a"
            err = f" | error={row['error']}" if row["error"] else ""
            click.echo(
                f"  - {row['score']:>3}/100 [{row['band']}] {status} "
                f"recs={row['recommendations_count']} :: {row['url']}{err}"
            )

    if audit_result.score_breakdown:
        click.echo("")
        click.echo("Incumbent breakdown:")
        ordered = ["robots", "llms", "schema", "meta", "content", "signals", "ai_discovery", "brand_entity"]
        for key in ordered:
            if key in audit_result.score_breakdown:
                click.echo(f"  - {key}: {audit_result.score_breakdown[key]}")

    if critic_notes:
        click.echo("")
        click.echo("Top critic findings:")
        for note in critic_notes[:5]:
            click.echo(f"  - {note}")

    if top_actions:
        click.echo("")
        click.echo("What to do next:")
        for action in top_actions[:5]:
            if isinstance(action, dict):
                click.echo(
                    f"  - {action.get('title', 'Action')} "
                    f"[{action.get('window', 'this_week')}] "
                    f"impact={action.get('impact', 'medium')} "
                    f"effort={action.get('effort', 'medium')} "
                    f"(+{action.get('expected_score_gain', 0)})"
                )
                why = action.get("why")
                if why:
                    click.echo(f"    why: {why}")
            else:
                click.echo(f"  - {action}")


@click.command(name="rivalry")
@click.option("--url", required=True, help="Target site URL (incumbent)")
@click.option("--vs", "rival_url", default=None, help="Real competitor URL to audit as Candidate B")
@click.option("--sitemap", default=None, help="Optional sitemap URL for per-page scoring in the rivalry report")
@click.option("--max-urls", default=20, type=int, show_default=True, help="Max sitemap pages to score")
@click.option(
    "--vertical",
    default="auto",
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
    show_default=True,
)
@click.option(
    "--market-locale",
    default="en",
    type=click.Choice(["en", "fr", "en-fr"], case_sensitive=False),
    show_default=True,
)
@click.option("--output", "output_file", default=None, help="Write rivalry report to file (.json or .md)")
@click.option("--verbose", is_flag=True, help="Show internal audit warnings/log details")
@click.option("--save-history", is_flag=True, help="Save run and show delta vs previous run")
@click.option("--history-db", default=None, help="Optional writable SQLite path for rivalry history")
def rivalry(url, rival_url, sitemap, max_urls, vertical, market_locale, output_file, verbose, save_history, history_db):
    """Run A-vs-B-vs-AB GEO rivalry workflow and pick a winner.

    Pass --vs to audit a real competitor instead of a synthetic projection.
    """
    from geo_optimizer.core.audit import run_full_audit
    from geo_optimizer.core.batch_audit import run_batch_audit
    from geo_optimizer.core.fixer import run_all_fixes
    from geo_optimizer.core.history import HistoryStore
    from geo_optimizer.core.llms_generator import discover_sitemap

    if not verbose:
        logging.getLogger("geo_optimizer.core.audit").setLevel(logging.ERROR)

    click.echo("⏳ Running incumbent audit...", err=True)
    audit_result = run_full_audit(url, vertical=vertical, market_locale=market_locale)
    fix_plan = run_all_fixes(url=url, audit_result=audit_result)

    rival_audit = None
    if rival_url:
        click.echo(f"⏳ Running competitor audit: {rival_url}", err=True)
        rival_audit = run_full_audit(rival_url, vertical=vertical, market_locale=market_locale)

    resolved_vertical = (
        audit_result.vertical_profile.vertical
        if getattr(audit_result, "vertical_profile", None) and audit_result.vertical_profile.checked
        else vertical
        if vertical != "auto"
        else "generic"
    )

    candidates = _build_candidates(audit_result, fix_plan, rival_audit=rival_audit)
    panel = _judge(candidates, vertical=resolved_vertical)

    top_critic_notes = audit_result.recommendations[:5]
    top_actions = [
        {
            "title": a.title,
            "window": a.priority,
            "impact": a.impact,
            "effort": a.effort,
            "expected_score_gain": a.expected_score_gain,
            "why": a.why,
        }
        for a in getattr(audit_result, "next_actions", [])[:5]
    ]

    history_delta = None
    if save_history:
        try:
            store = HistoryStore(Path(history_db) if history_db else None)
            entry = store.save_audit_result(audit_result)
            history_delta = entry.delta
        except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as exc:
            click.echo(f"⚠️  Could not save history: {type(exc).__name__}", err=True)

    page_rows = []
    sitemap_url = sitemap
    if not sitemap_url:
        try:
            sitemap_url = discover_sitemap(audit_result.url)
        except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError):
            sitemap_url = None
    if sitemap_url:
        try:
            batch = run_batch_audit(sitemap_url, max_urls=max_urls, concurrency=5)
            for p in batch.worst_pages:
                page_rows.append(
                    {
                        "url": p.url,
                        "score": p.score,
                        "band": p.band,
                        "http_status": p.http_status,
                        "recommendations_count": p.recommendations_count,
                        "error": p.error,
                    }
                )
        except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError):
            # rivalry report should still work even if sitemap analysis fails
            page_rows = []

    report = {
        "url": audit_result.url,
        "rival_url": rival_url,
        "vertical": resolved_vertical,
        "mode": "real-competitor" if rival_audit else "projected",
        "incumbent": {
            "score": audit_result.score,
            "band": audit_result.band,
            "score_breakdown": audit_result.score_breakdown,
            "history_delta": history_delta,
            "business_readiness": audit_result.vertical_profile.business_readiness_score
            if audit_result.vertical_profile
            else 0,
        },
        "rival": {
            "url": rival_url,
            "score": rival_audit.score if rival_audit else None,
            "band": rival_audit.band if rival_audit else None,
            "score_breakdown": rival_audit.score_breakdown if rival_audit else None,
        }
        if rival_url
        else None,
        "candidates": candidates,
        "judge_panel": panel,
        "critic_notes": top_critic_notes,
        "next_actions": top_actions,
        "pages": page_rows,
    }

    if output_file:
        p = Path(output_file)
        if p.suffix.lower() == ".json":
            p.write_text(json.dumps(report, indent=2), encoding="utf-8")
        else:
            rw = panel.get("readiness_weights", {})
            lines = [
                "# GEO Rivalry Report",
                "",
                f"URL: {report['url']}",
            ]
            if report.get("rival_url"):
                lines.append(f"Rival: {report['rival_url']} ({report['mode']})")
            lines.extend(
                [
                    f"Vertical: {report['vertical']}",
                    f"Incumbent score: {report['incumbent']['score']}/100 ({report['incumbent']['band']})",
                    (
                        f"Trend vs previous run: {report['incumbent']['history_delta']:+d}"
                        if report["incumbent"]["history_delta"] is not None
                        else "Trend vs previous run: n/a"
                    ),
                    f"Business readiness: {report['incumbent']['business_readiness']}/100",
                    "",
                    "## Candidates",
                ]
            )
            rw = panel.get("readiness_weights", {})
            cs = panel.get("composite_scores", {})
            summary = panel.get("category_summary", {})

            for c in candidates:
                lines.append(
                    f"- {c['name']} ({c['label']}): GEO {c['geo_score']}, "
                    f"Citability {c['citability_score']}, Trust {c['trust_score']}"
                )

            lines.extend(
                [
                    "",
                    "## Standing",
                    f"- Winner: **{panel['winner']}** (composite: {' | '.join(f'{n}={v}' for n, v in cs.items())})",
                    f"- Weights (auto-derived): geo={rw.get('geo', 0):.0%}  "
                    f"trust={rw.get('trust', 0):.0%}  "
                    f"citation={rw.get('citation', 0):.0%}",
                ]
            )
            if summary:
                if "leads" in summary:
                    lines.append(
                        f"- Category standing: leads {summary['leads']}/{summary['total']}, "
                        f"trails {summary['trails']}, ties {summary['ties']}"
                    )
                lines.append(
                    f"- Weakest category: **{summary['weakest']}** "
                    f"({summary['weakest_score']}/{summary['weakest_max']}, gap={summary['weakest_gap']}) — fix this first"
                )

            # Per-category diff when real competitor data is available
            a_bd = next((c["score_breakdown"] for c in candidates if c["name"] == "A"), {})
            b_bd = next((c["score_breakdown"] for c in candidates if c["name"] == "B"), {})
            if a_bd and b_bd and report.get("mode") == "real-competitor":
                lines.extend(["", "## Category Breakdown vs Competitor"])
                lines.append("| Category | You | Rival | Delta |")
                lines.append("|----------|-----|-------|-------|")
                for k in _CATEGORY_ORDER:
                    a_val = a_bd.get(k, "-")
                    b_val = b_bd.get(k, "-")
                    if isinstance(a_val, int) and isinstance(b_val, int):
                        delta = b_val - a_val
                        delta_str = f"{delta:+d}" if delta != 0 else "="
                    else:
                        delta_str = "n/a"
                    lines.append(f"| {k} | {a_val} | {b_val} | {delta_str} |")

            lines.extend(["", "## Critic Notes"])
            lines.extend(f"- {r}" for r in top_critic_notes)
            lines.extend(["", "## Next Actions"])
            for action in top_actions:
                lines.append(
                    f"- {action['title']} [{action['window']}] "
                    f"impact={action['impact']} effort={action['effort']} (+{action['expected_score_gain']})"
                )
                if action.get("why"):
                    lines.append(f"  - why: {action['why']}")
            if page_rows:
                lines.extend(["", "## Pages To Prioritize (lowest scores)"])
                for row in page_rows[:12]:
                    lines.append(
                        f"- {row['score']}/100 [{row['band']}] recs={row['recommendations_count']} {row['url']}"
                    )
            p.write_text("\n".join(lines), encoding="utf-8")
        click.echo(f"✅ Rivalry report written to: {output_file}")

    _render_terminal_report(
        audit_result,
        candidates,
        panel,
        top_critic_notes,
        top_actions,
        history_delta=history_delta,
        page_rows=page_rows,
        rival_url=rival_url,
        mode=report["mode"],
    )
