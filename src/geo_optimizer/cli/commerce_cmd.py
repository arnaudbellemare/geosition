"""CLI presentation for the commerce readiness audit."""

from __future__ import annotations

import json
from dataclasses import asdict

import click

from geo_optimizer.core.commerce_readiness import run_commerce_readiness


@click.command(name="commerce-audit")
@click.option(
    "--url",
    required=True,
    help="Public page URL; use a product or service page for detailed evidence.",
)
@click.option("--site", is_flag=True, help="Audit linked same-origin pages and the root sitemap.")
@click.option("--max-pages", type=click.IntRange(1, 500), default=25, show_default=True)
@click.option(
    "--render",
    is_flag=True,
    help="Render JavaScript using an isolated browser (requires Node and Playwright).",
)
@click.option("--vercel-project", help="Vercel project name or ID for direct evidence.")
@click.option("--vercel-scope", help="Vercel team scope for direct evidence.")
@click.option("--vercel-request-id", help="Request ID from a timestamped browser visit.")
@click.option("--vercel-since", help="UTC ISO start of a minute-aligned correlation window.")
@click.option("--vercel-until", help="UTC ISO end of a minute-aligned correlation window.")
@click.option(
    "--vercel-cli", default="vercel", envvar="GEOSITION_VERCEL_CLI", help="Authenticated Vercel CLI executable."
)
@click.option(
    "--browser-evidence",
    type=click.Path(exists=True, dir_okay=False),
    help="Operator-reported Vercel evidence JSON (site audits only).",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json", "markdown"]),
    default="text",
)
def commerce_audit(
    url: str,
    output_format: str,
    site: bool,
    max_pages: int,
    render: bool,
    browser_evidence: str,
    vercel_project: str,
    vercel_scope: str,
    vercel_request_id: str,
    vercel_since: str,
    vercel_until: str,
    vercel_cli: str,
) -> None:
    """Inspect observable AI commerce signals on a single page."""
    vercel_args = (vercel_project, vercel_scope, vercel_request_id, vercel_since, vercel_until)
    if any(vercel_args) and (not all(vercel_args) or not site or browser_evidence):
        raise click.UsageError(
            "Direct Vercel evidence requires --site, all five --vercel options, and no --browser-evidence."
        )
    if browser_evidence and not site:
        raise click.UsageError("--browser-evidence requires --site")
    if output_format == "markdown" and not site:
        raise click.UsageError("--format markdown requires --site")
    if render and not site:
        raise click.UsageError("--render requires --site")
    try:
        if site:
            from geo_optimizer.core.commerce_site import run_site_audit

            report = run_site_audit(url, max_pages=max_pages, render=render)
        else:
            report = run_commerce_readiness(url)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    data = asdict(report)
    if browser_evidence:
        from geo_optimizer.core.commerce_provider_evidence import attach_vercel_evidence

        try:
            with open(browser_evidence, encoding="utf-8") as evidence_file:
                attach_vercel_evidence(data, json.load(evidence_file))
        except (ValueError, OSError) as exc:
            raise click.ClickException(str(exc)) from exc
    if all(vercel_args):
        from geo_optimizer.core.commerce_vercel_direct import attach_direct_vercel, fetch_vercel_correlation

        try:
            record = fetch_vercel_correlation(
                url,
                executable=vercel_cli,
                scope=vercel_scope,
                project=vercel_project,
                request_id=vercel_request_id,
                since=vercel_since,
                until=vercel_until,
            )
            attach_direct_vercel(data, record)
        except ValueError as exc:
            raise click.ClickException(str(exc)) from exc
    if output_format == "markdown":
        from datetime import datetime, timezone

        from geo_optimizer.cli.commerce_report import format_commerce_report

        click.echo(format_commerce_report(data, audit_date=datetime.now(timezone.utc).date().isoformat()))
        return
    if output_format == "json":
        click.echo(json.dumps(data, indent=2, ensure_ascii=False))
        return
    if site:
        click.echo(f"AI commerce site audit — {report.url}")
        click.echo(
            f"Pages audited: {report.coverage['pages_audited']}; pending: {report.coverage['pending']}; discovered queue complete: {report.coverage['complete']}"
        )
        click.echo(report.coverage["scope"])
        for page in report.pages:
            click.echo(f"\n{page['url']} (render: {page['render_status']})")
            click.echo(
                f"  Products: {len(page['products'])}; catalog card signals: {len(page['catalog_signals'])}; service records: {len(page['services'])}; journey signals: {len(page['journey_signals'])}"
            )
            for service in page["services"]:
                click.echo(f"  Service record: {service}")
            for signal in page["journey_signals"]:
                click.echo(f"  Journey signal: {signal['kind']} — {signal['label']}")
            for item in page["catalog_signals"]:
                click.echo(f"  Catalog signal: {item['name']} — {item['price_text']}")
            for warning in page["render_warnings"]:
                click.echo(f"  Warning: {warning}")
        for failure in report.failures:
            click.echo(f"  Failed: {failure['url']} — {failure['error']}")
        for skipped in report.skipped:
            click.echo(f"  Skipped: {skipped['url']} — {skipped['reason']}")
        for warning in report.warnings:
            click.echo(f"  Warning: {warning}")
        if data.get("browser_access", {}).get("provider_evidence"):
            click.echo(
                f"Vercel evidence: {data['browser_access']['provider_evidence']['classification']}; individual signature not verified."
            )
        click.echo("Recommended actions:")
        for rec in data["recommendations"]:
            click.echo(f"  {rec['priority'].upper()}: {rec['title']} — {rec['action']}")
            if rec.get("guided_fix"):
                click.echo(f"    Guided fix: {rec['guided_fix']}")
        click.echo("Catalog cards and journey controls are signals, not verified transactions or provider eligibility.")
        if render:
            click.echo("Browser requests are blocked; API and third-party content may be missing.")
        return
    click.echo(f"AI commerce readiness — {report.url}")
    click.echo(f"Product structured data: {len(report.products)} item(s)")
    for product in report.products:
        missing = [key for key, present in product["fields"].items() if not present]
        click.echo(f"  {product['name']}: " + ("missing " + ", ".join(missing) if missing else "fields present"))
    click.echo(f"Service structured-data records: {', '.join(report.services) or 'none observed'}")
    click.echo("Journey links and buttons (signals only):")
    for signal in report.journey_signals:
        destination = f" — {signal['url']}" if signal["url"] else ""
        click.echo(f"  {signal['kind']} ({signal['element']}): {signal['label']}{destination}")
    if not report.journey_signals:
        click.echo("  None observed on this page.")
    click.echo("Not verified: " + ", ".join(report.manual_checks))
    for limitation in report.limitations:
        click.echo(f"  Note: {limitation}")
