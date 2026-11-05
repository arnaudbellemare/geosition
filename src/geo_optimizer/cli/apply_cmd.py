"""
CLI command: geo apply

Apply generated GEO fixes directly to a local repository with stack-aware routing.
"""

from __future__ import annotations

from pathlib import Path

import click


@click.command(name="apply")
@click.option("--url", required=True, help="Site URL to audit and generate fixes from")
@click.option("--repo", "repo_path", default=".", show_default=True, help="Local repo path to apply fixes into")
@click.option(
    "--only",
    default=None,
    help="Filter categories: robots,llms,schema,meta,ai_discovery,content,vertical",
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
def apply_cmd(url, repo_path, only, vertical, market_locale):
    """Run audit+fix and apply file-safe fixes to a local project."""
    from geo_optimizer.core.audit import run_full_audit
    from geo_optimizer.core.fixer import run_all_fixes
    from geo_optimizer.core.site_integrator import apply_fix_plan_to_repo

    only_set = {c.strip().lower() for c in only.split(",")} if only else None

    click.echo("⏳ Running audit and generating fix plan...", err=True)
    result = run_full_audit(url, vertical=vertical, market_locale=market_locale)
    plan = run_all_fixes(url=url, audit_result=result, only=only_set)

    if not plan.fixes:
        click.echo("✅ No applicable fixes generated.")
        return

    repo = Path(repo_path).resolve()
    outcome = apply_fix_plan_to_repo(repo, plan.fixes)

    click.echo(f"✅ Applied GEO fixes into: {repo}")
    click.echo(f"Stack detected: {outcome.stack}")
    click.echo(f"Applied files: {len(outcome.applied_files)}")
    for p in outcome.applied_files[:20]:
        click.echo(f"  - {p}")
    if outcome.manual_steps:
        click.echo("⚠️  Manual snippet steps recorded in geo-manual-steps.md")
