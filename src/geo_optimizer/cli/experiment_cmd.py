"""CLI for controlled memory/search experiments and evidence reports."""

from __future__ import annotations

import json
from pathlib import Path

import click
import requests

from geo_optimizer.cli.experiment_formatter import format_memory_search_text, write_memory_search_report
from geo_optimizer.core.benchmark.memory_search import build_memory_search_report, compare_memory_search_waves
from geo_optimizer.core.collection.experiments import collect_experiment, create_experiment
from geo_optimizer.core.collection.normalize import load_canonical_batch, write_canonical_batch
from geo_optimizer.core.collection.pipeline import load_prompt_specs
from geo_optimizer.core.collection.store import CollectionArtifactStore
from geo_optimizer.models.config import (
    EXPERIMENT_MAX_OUTPUT_TOKENS,
    EXPERIMENT_MAX_REQUESTS,
    EXPERIMENT_REPETITIONS,
    EXPERIMENT_TEMPERATURE,
)
from geo_optimizer.models.results.collection import ExperimentBrand


@click.group(name="experiment")
def experiment_group():
    """Measure unassisted brand recall separately from live-search visibility."""


def _new_output(path: Path) -> None:
    if path.exists():
        raise click.ClickException("Output already exists; choose a new path to preserve the baseline")


def _report_output(output_dir: Path, canonical_path: Path) -> Path:
    if canonical_path.resolve() in {
        (output_dir / "memory-search.json").resolve(),
        (output_dir / "memory-search.html").resolve(),
    }:
        raise click.ClickException("Report destination would overwrite canonical evidence; choose another directory")
    return output_dir


@experiment_group.command(name="create")
@click.argument("domain")
@click.option("--brand", required=True, help="Scoring-only brand name; not sent to the model")
@click.option("--alias", "aliases", multiple=True)
@click.option(
    "--competitors-file", type=click.Path(exists=True, path_type=Path), help="JSON list of name/domain/aliases"
)
@click.option("--prompts-file", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--model", required=True, help="Explicit Gemini model used in both conditions")
@click.option("--repetitions", type=click.IntRange(min=1), default=EXPERIMENT_REPETITIONS, show_default=True)
@click.option("--max-requests", type=click.IntRange(min=1), default=EXPERIMENT_MAX_REQUESTS, show_default=True)
@click.option(
    "--max-output-tokens", type=click.IntRange(min=1), default=EXPERIMENT_MAX_OUTPUT_TOKENS, show_default=True
)
@click.option(
    "--max-total-tokens", type=click.IntRange(min=1), default=None, help="Stop subsequent calls at observed token limit"
)
@click.option("--temperature", type=click.FloatRange(min=0, max=2), default=EXPERIMENT_TEMPERATURE)
@click.option("--output", required=True, type=click.Path(path_type=Path))
def experiment_create(
    domain,
    brand,
    aliases,
    competitors_file,
    prompts_file,
    model,
    repetitions,
    max_requests,
    max_output_tokens,
    max_total_tokens,
    temperature,
    output,
):
    """Freeze unbranded prompts and controls without calling a provider."""
    _new_output(output)
    try:
        competitors = []
        if competitors_file:
            competitors = [ExperimentBrand(**item) for item in json.loads(competitors_file.read_text(encoding="utf-8"))]
        batch = create_experiment(
            target=ExperimentBrand(name=brand, domain=domain, aliases=list(aliases)),
            competitors=competitors,
            prompts=load_prompt_specs(prompts_file),
            model=model,
            repetitions=repetitions,
            max_requests=max_requests,
            max_output_tokens=max_output_tokens,
            max_total_tokens=max_total_tokens,
            temperature=temperature,
        )
        write_canonical_batch(output, batch)
    except (ValueError, TypeError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Frozen experiment → {output}")
    click.echo(f"Planned generation requests: {len(batch.prompts) * repetitions * 2}; no requests made")


@experiment_group.command(name="run")
@click.option("--experiment", "experiment_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--output", required=True, type=click.Path(path_type=Path), help="New canonical answers file")
@click.option("--artifact-dir", type=click.Path(path_type=Path), default=None)
@click.option("--report-dir", type=click.Path(path_type=Path), default=None)
def experiment_run(experiment_path, output, artifact_dir, report_dir):
    """Collect a paid paired wave using GEMINI_API_KEY, then write JSON and HTML reports."""
    _new_output(output)
    report_dir = _report_output(report_dir or output.parent / (output.stem + ".report"), output)
    try:
        batch = load_canonical_batch(experiment_path)
        store = CollectionArtifactStore(
            base_dir=artifact_dir or output.parent / (output.stem + ".artifacts"),
            org_slug=batch.target_domain.replace(".", "-"),
        )
        collected = collect_experiment(batch, artifact_store=store, output_path=output)
        report = build_memory_search_report(collected)
        paths = write_memory_search_report(report, report_dir)
    except requests.RequestException as exc:
        raise click.ClickException("Provider capability check failed; no generation wave started") from exc
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Canonical evidence → {output}")
    click.echo(format_memory_search_text(report))
    for path in paths:
        click.echo(f"Report → {path}")
    if not any(a.status == "success" for a in collected.answers):
        raise click.ClickException("No successful answers; failed attempt evidence was saved")
    if not any(c.valid_answers for s in report.slices for c in s.conditions):
        raise click.ClickException("No classifiable answers; evidence was saved with unknown provenance")


@experiment_group.command(name="report")
@click.option("--input", "input_path", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--output-dir", required=True, type=click.Path(path_type=Path))
def experiment_report(input_path, output_dir):
    """Recompute metrics from saved evidence without network access."""
    _report_output(output_dir, input_path)
    try:
        report = build_memory_search_report(load_canonical_batch(input_path))
        paths = write_memory_search_report(report, output_dir)
    except (ValueError, TypeError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(format_memory_search_text(report))
    for path in paths:
        click.echo(f"Report → {path}")


@experiment_group.command(name="compare")
@click.option("--before", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--after", required=True, type=click.Path(exists=True, path_type=Path))
@click.option("--output", required=True, type=click.Path(path_type=Path))
def experiment_compare(before, after, output):
    """Compare saved waves, rejecting changed prompts or model controls."""
    _new_output(output)
    try:
        result = compare_memory_search_waves(load_canonical_batch(before), load_canonical_batch(after))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    except (ValueError, TypeError, OSError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wave comparison → {output}")
