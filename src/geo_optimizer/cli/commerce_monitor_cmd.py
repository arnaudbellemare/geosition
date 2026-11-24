"""Repeatable read-only commerce monitor command."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

import click

from geo_optimizer.core.commerce_monitor import MonitorScanError, run_commerce_monitor
from geo_optimizer.models.config import GEO_OPTIMIZER_HOME


@click.command(name="commerce-monitor")
@click.option("--url", required=True, help="Site URL to monitor.")
@click.option("--db", type=click.Path(path_type=Path), default=None, help="SQLite history path.")
@click.option("--max-pages", type=click.IntRange(1, 500), default=25, show_default=True)
@click.option("--render", is_flag=True, help="Enable restricted JavaScript rendering.")
@click.option(
    "--baseline",
    type=click.Path(path_type=Path, exists=True, dir_okay=False),
    default=None,
    help="Import a compatible site-audit JSON only on the first run.",
)
@click.option("--watch", is_flag=True, help="Repeat while this process runs; stop with Ctrl-C.")
@click.option("--interval-seconds", type=click.IntRange(min=60), default=86400, show_default=True)
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
def commerce_monitor(url, db, max_pages, render, baseline, watch, interval_seconds, output_format):
    """Monitor audit changes and read-only contact-page signals."""
    db_path = db or GEO_OPTIMIZER_HOME / "commerce-monitor.db"
    try:
        seed = json.loads(baseline.read_text(encoding="utf-8")) if baseline else None
        while True:
            try:
                result = run_commerce_monitor(url, db_path, max_pages=max_pages, render=render, baseline=seed)
            except MonitorScanError as exc:
                if not watch:
                    raise
                click.echo(f"Scan unavailable: {exc}; retrying after the interval.", err=True)
                time.sleep(interval_seconds)
                continue
            seed = None
            if output_format == "json":
                click.echo(json.dumps(asdict(result), ensure_ascii=False))
            else:
                click.echo(f"Commerce monitor: {result.url} — {result.checked_at}")
                click.echo(
                    f"{'Baseline recorded' if result.baseline else 'Compared with previous snapshot'}; {len(result.changes)} changes; {len(result.unknowns)} unknowns."
                )
                for change in result.changes:
                    click.echo("  Change: " + json.dumps(change, ensure_ascii=False))
                for unknown in result.unknowns:
                    click.echo(f"  Unknown: {unknown}")
                for probe in result.journey_probes:
                    click.echo(f"  Contact page: {probe['url']} — {probe['status']}")
                click.echo("Signals do not establish completed transactions or verified ChatGPT access.")
            if not watch:
                return
            time.sleep(interval_seconds)
    except (OSError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
