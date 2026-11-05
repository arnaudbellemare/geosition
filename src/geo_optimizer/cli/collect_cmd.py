"""CLI: geo benchmark collect — hybrid answer collection pipeline."""

from __future__ import annotations

from pathlib import Path

import click

from geo_optimizer.core.benchmark.runner import run_domain_benchmark
from geo_optimizer.core.collection.normalize import (
    batch_to_benchmark_answers,
    export_benchmark_answers_file,
    write_canonical_batch,
)
from geo_optimizer.core.collection.pipeline import (
    collect_and_normalize,
    import_tracker_export,
    load_prompt_specs,
    normalize_raw_directory,
)
from geo_optimizer.core.collection.store import COLLECTION_HOME
from geo_optimizer.core.monitor import normalize_monitor_domain


@click.group(name="collect")
def collect_group():
    """Collect AI answers (API / browser / manual) → canonical answers.json."""


@collect_group.command(name="run")
@click.argument("domain")
@click.option("--prompts-file", required=True, type=click.Path(path_type=Path), help="Prompt set JSON")
@click.option(
    "--provider",
    "providers",
    multiple=True,
    required=True,
    help="Adapter id: perplexity, gemini_grounding, google_ai, chatgpt, brightdata, manual",
)
@click.option("--country", default="", help="Locale country code for collection")
@click.option("--output", "output_file", type=click.Path(path_type=Path), help="Canonical answers.json path")
@click.option("--platform", default="google_ai", help="Browser lane platform when using brightdata/google_ai")
@click.option("--tracker-url", default=None, help="geo-aeo-tracker base URL (or GEO_AEO_TRACKER_URL)")
@click.option("--manual-file", type=click.Path(path_type=Path), help="Manual lane source JSON")
def collect_run(domain, prompts_file, providers, country, output_file, platform, tracker_url, manual_file):
    """Stage 1+2: collect raw answers and write canonical answers.json."""
    prompts = load_prompt_specs(prompts_file)
    if not prompts:
        raise click.UsageError("No prompts found in prompts file")

    adapter_kwargs: dict = {}
    if tracker_url:
        adapter_kwargs["google_ai"] = {"platform": platform, "tracker_base_url": tracker_url}
        adapter_kwargs["brightdata"] = {"platform": platform, "tracker_base_url": tracker_url}
        adapter_kwargs["chatgpt"] = {"platform": "chatgpt", "tracker_base_url": tracker_url}
    if manual_file:
        adapter_kwargs["manual"] = {"source_path": manual_file}

    batch = collect_and_normalize(
        target_domain=domain,
        prompts=prompts,
        providers=list(providers),
        country=country,
        adapter_kwargs=adapter_kwargs,
    )

    out = output_file or (COLLECTION_HOME / "canonical" / f"{batch.collection_run_id}.json")
    write_canonical_batch(out, batch)
    click.echo(f"Collected {len(batch.answers)} answers → {out}")
    click.echo(f"Collection run id: {batch.collection_run_id}")


@collect_group.command(name="normalize")
@click.option("--raw-dir", required=True, type=click.Path(path_type=Path, exists=True, file_okay=False))
@click.option("--domain", default="", help="Target domain metadata")
@click.option("--output", "output_file", required=True, type=click.Path(path_type=Path))
def collect_normalize(raw_dir, domain, output_file):
    """Stage 2 only: normalize saved raw payloads to canonical answers.json."""
    batch = normalize_raw_directory(raw_dir, target_domain=domain)
    write_canonical_batch(output_file, batch)
    click.echo(f"Normalized {len(batch.answers)} answers → {output_file}")


@collect_group.command(name="from-tracker")
@click.option("--input", "input_file", required=True, type=click.Path(path_type=Path, dir_okay=False))
@click.option("--domain", required=True, help="Target domain for batch metadata")
@click.option("--output", "output_file", required=True, type=click.Path(path_type=Path))
def collect_from_tracker(input_file, domain, output_file):
    """Import geo-aeo-tracker bulk/SRO export into canonical answers.json."""
    batch = import_tracker_export(input_file, target_domain=domain)
    write_canonical_batch(output_file, batch)
    click.echo(f"Imported {len(batch.answers)} answers from tracker export → {output_file}")


@collect_group.command(name="to-benchmark")
@click.option("--canonical", "canonical_file", required=True, type=click.Path(path_type=Path, dir_okay=False))
@click.option("--output", "output_file", type=click.Path(path_type=Path), help="Legacy benchmark answers JSON")
def collect_to_benchmark(canonical_file, output_file):
    """Export canonical file to legacy benchmark runner format."""
    out = output_file or canonical_file.with_suffix(".benchmark.json")
    rows = export_benchmark_answers_file(canonical_file, out)
    click.echo(f"Wrote {len(rows)} benchmark rows → {out}")


@collect_group.command(name="pipeline")
@click.argument("domain")
@click.option("--prompts-file", required=True, type=click.Path(path_type=Path))
@click.option("--provider", "providers", multiple=True, required=True)
@click.option("--competitor", "competitors", multiple=True)
@click.option("--canonical-output", type=click.Path(path_type=Path), help="Canonical answers path")
@click.option("--no-audit", is_flag=True)
@click.option("--tracker-url", default=None)
@click.option("--platform", default="google_ai")
def collect_pipeline(domain, prompts_file, providers, competitors, canonical_output, no_audit, tracker_url, platform):
    """End-to-end: collect → canonical → benchmark run."""
    adapter_kwargs: dict = {}
    if tracker_url:
        for key in ("google_ai", "brightdata", "chatgpt"):
            adapter_kwargs[key] = {"platform": platform, "tracker_base_url": tracker_url}

    prompts = load_prompt_specs(prompts_file)
    batch = collect_and_normalize(
        target_domain=domain,
        prompts=prompts,
        providers=list(providers),
        adapter_kwargs=adapter_kwargs,
    )
    canonical_path = canonical_output or (COLLECTION_HOME / "canonical" / f"{batch.collection_run_id}.json")
    write_canonical_batch(canonical_path, batch)

    answers = batch_to_benchmark_answers(batch)
    result = run_domain_benchmark(
        domain,
        competitors=list(competitors),
        answers=answers,
        audit_url=None if no_audit else normalize_monitor_domain(domain),
        use_cache=True,
    )
    click.echo(f"Collection: {len(batch.answers)} answers → {canonical_path}")
    click.echo(f"Benchmark run #{result.run_id}: {result.benchmark_score}/100 ({result.band})")
    click.echo(result.executive_summary)
