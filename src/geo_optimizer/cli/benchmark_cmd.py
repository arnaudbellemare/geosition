"""CLI: geo benchmark — domain citation benchmark and negotiation reports."""

from __future__ import annotations

import json
from pathlib import Path

import click

from geo_optimizer.cli.benchmark_formatter import (
    format_benchmark_json,
    format_benchmark_text,
    format_negotiation_csv,
    format_negotiation_html,
)
from geo_optimizer.core.benchmark.runner import (
    build_negotiation_report,
    load_benchmark_run_result,
    run_domain_benchmark,
)
from geo_optimizer.core.benchmark.schedule import due_schedules, mark_schedule_run
from geo_optimizer.core.benchmark.store import BenchmarkStore
from geo_optimizer.core.collection.normalize import batch_to_benchmark_answers, load_canonical_batch
from geo_optimizer.core.monitor import normalize_monitor_domain
from geo_optimizer.models.config import BENCHMARK_SCHEDULES


def _load_answers_file(path: Path) -> list[dict]:
    """Load canonical or legacy answers JSON for benchmark run."""
    batch = load_canonical_batch(path)
    if batch.answers:
        return batch_to_benchmark_answers(batch)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "answers" in payload:
        return list(payload["answers"])
    if isinstance(payload, list):
        return payload
    raise click.UsageError('Answers file must be canonical v1, a list, or {"answers": [...]}')


@click.group(name="benchmark")
def benchmark_group():
    """Domain GEO benchmark: citation share, competitors, task gaps, export."""


@benchmark_group.command(name="run")
@click.argument("domain")
@click.option("--competitor", "competitors", multiple=True, help="Competitor domain to track")
@click.option("--answers-file", type=click.Path(path_type=Path), help="JSON file with AI answers")
@click.option("--no-audit", is_flag=True, help="Skip on-site audit for page-task and unique value")
@click.option("--schedule", default="manual", type=click.Choice(list(BENCHMARK_SCHEDULES)))
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text")
@click.option("--output", "output_file", type=click.Path(path_type=Path), default=None)
@click.option("--benchmark-db", default=None, hidden=True, type=click.Path(path_type=Path))
def benchmark_run(domain, competitors, answers_file, no_audit, schedule, output_format, output_file, benchmark_db):
    """Run a domain benchmark from collected AI answers."""
    if not answers_file:
        raise click.UsageError("--answers-file is required (JSON list of prompt/answer snapshots)")

    store = BenchmarkStore(benchmark_db) if benchmark_db else BenchmarkStore()
    answers = _load_answers_file(answers_file)
    result = run_domain_benchmark(
        domain,
        competitors=list(competitors),
        answers=answers,
        schedule=schedule,
        audit_url=None if no_audit else normalize_monitor_domain(domain),
        store=store,
        use_cache=True,
    )
    if schedule != "manual":
        mark_schedule_run(domain, store=store, frequency=schedule)

    payload = format_benchmark_json(result) if output_format == "json" else format_benchmark_text(result)
    if output_file:
        output_file.write_text(payload, encoding="utf-8")
        click.echo(f"Wrote benchmark result to {output_file}")
    else:
        click.echo(payload)


@benchmark_group.command(name="report")
@click.option("--run-id", required=True, type=int, help="Benchmark run ID to export")
@click.option("--format", "output_format", type=click.Choice(["html", "csv", "text", "json"]), default="html")
@click.option("--output", "output_file", type=click.Path(path_type=Path), required=True)
@click.option("--benchmark-db", default=None, hidden=True, type=click.Path(path_type=Path))
def benchmark_report(run_id, output_format, output_file, benchmark_db):
    """Export negotiation-ready HTML/CSV/text report for a benchmark run."""
    store = BenchmarkStore(benchmark_db) if benchmark_db else BenchmarkStore()
    result = load_benchmark_run_result(run_id, store=store)
    if result is None:
        raise click.ClickException(f"Benchmark run #{run_id} not found")

    report = build_negotiation_report(result)
    if output_format == "html":
        payload = format_negotiation_html(report)
    elif output_format == "csv":
        payload = format_negotiation_csv(report)
    elif output_format == "json":
        payload = format_benchmark_json(result)
    else:
        payload = format_benchmark_text(result)

    output_file.write_text(payload, encoding="utf-8")
    click.echo(f"Wrote {output_format} report to {output_file}")


@benchmark_group.command(name="schedule")
@click.argument("domain")
@click.option("--frequency", default="weekly", type=click.Choice(list(BENCHMARK_SCHEDULES)))
@click.option("--competitor", "competitors", multiple=True)
@click.option("--disable", is_flag=True, help="Disable schedule without deleting row")
@click.option("--benchmark-db", default=None, hidden=True, type=click.Path(path_type=Path))
def benchmark_schedule(domain, frequency, competitors, disable, benchmark_db):
    """Configure daily/weekly/manual benchmark schedule for a domain."""
    store = BenchmarkStore(benchmark_db) if benchmark_db else BenchmarkStore()
    record = store.upsert_schedule(
        domain,
        frequency,
        list(competitors),
        enabled=not disable,
    )
    click.echo(
        f"Schedule for {record.domain}: {record.frequency}, "
        f"competitors={record.competitor_domains}, enabled={record.enabled}"
    )


@benchmark_group.command(name="due")
@click.option("--benchmark-db", default=None, hidden=True, type=click.Path(path_type=Path))
def benchmark_due(benchmark_db):
    """List domains with benchmark schedules that are due."""
    store = BenchmarkStore(benchmark_db) if benchmark_db else BenchmarkStore()
    rows = due_schedules(store=store)
    if not rows:
        click.echo("No benchmark schedules are due.")
        return
    for row in rows:
        click.echo(f"{row.domain} ({row.frequency}) competitors={row.competitor_domains}")


@benchmark_group.command(name="history")
@click.argument("domain")
@click.option("--limit", default=10, show_default=True, type=int)
@click.option("--benchmark-db", default=None, hidden=True, type=click.Path(path_type=Path))
def benchmark_history(domain, limit, benchmark_db):
    """List recent benchmark runs for a domain."""
    store = BenchmarkStore(benchmark_db) if benchmark_db else BenchmarkStore()
    runs = store.list_benchmark_runs(domain, limit=limit)
    if not runs:
        click.echo(f"No benchmark runs for {domain}")
        return
    for run in runs:
        click.echo(f"#{run.run_id} {run.run_at} score={run.benchmark_score} band={run.band} schedule={run.schedule}")


from geo_optimizer.cli.collect_cmd import collect_group  # noqa: E402

benchmark_group.add_command(collect_group)
