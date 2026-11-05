"""
CLI command: geo autopilot

Autonomous loop: audit -> prioritize -> apply -> re-audit.
"""

from __future__ import annotations

from pathlib import Path

import click


@click.command(name="autopilot")
@click.argument("url_arg", required=False, default=None, metavar="URL")
@click.option("--url", "url_opt", default=None, help="Site URL to optimize (or pass as first positional arg).")
@click.option("--repo", "repo_path", default=".", show_default=True, help="Local repo path for applying fixes")
@click.option("--apply", "do_apply", is_flag=True, help="Apply generated file-safe fixes automatically")
@click.option(
    "--max-cycles",
    "--max-iterations",
    "max_cycles",
    default=1,
    type=click.IntRange(min=1),
    show_default=True,
    help="Safety guard for audit/apply cycles; each cycle generates every applicable fix.",
)
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
def autopilot(url_arg, url_opt, repo_path, do_apply, max_cycles, vertical, market_locale):
    """Run an autonomous GEO optimization cycle with actionable roadmap."""
    url = url_arg or url_opt
    if not url:
        raise click.UsageError("URL required. Usage:\n\n  geo autopilot https://yoursite.com")

    from geo_optimizer.core.audit import run_full_audit
    from geo_optimizer.core.fixer import run_all_fixes
    from geo_optimizer.core.site_integrator import apply_fix_plan_to_repo

    repo = Path(repo_path).resolve()
    previous_score = None
    final_result = None

    for i in range(max_cycles):
        click.echo(f"\n🚀 Autopilot cycle {i + 1}/{max_cycles}")
        result = run_full_audit(url, vertical=vertical, market_locale=market_locale)
        final_result = result
        click.echo(f"Score: {result.score}/100 ({result.band})")

        if result.next_actions:
            click.echo("Next best actions:")
            for action in result.next_actions:
                click.echo(f"  - {action.title} [{action.priority}] (+{action.expected_score_gain})")

        plan = run_all_fixes(url=url, audit_result=result)
        if not plan.fixes:
            click.echo("✅ No fixes generated. Optimization loop complete.")
            break

        click.echo(f"Generated fixes: {len(plan.fixes)} (all applicable fixes in this cycle)")
        if do_apply:
            outcome = apply_fix_plan_to_repo(repo, plan.fixes)
            click.echo(f"Applied files: {len(outcome.applied_files)} (stack={outcome.stack}; all file-safe fixes)")
        else:
            click.echo("Dry mode: pass --apply to patch file-safe artifacts automatically.")
            break

        previous_score = result.score

    if do_apply and final_result is not None and previous_score is not None:
        post = run_full_audit(url, vertical=vertical, market_locale=market_locale)
        delta = post.score - previous_score
        click.echo(f"\n📈 Post-apply score: {post.score}/100 ({post.band}) [{delta:+d}]")
