"""Offline discovery feed preview and local export."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from geo_optimizer.core.commerce_feed import feed_rows, validate_feed


@click.command(name="commerce-feed")
@click.option(
    "--input",
    "input_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Candidate JSON with records and review confirmations.",
)
@click.option("--output-dir", required=True, type=click.Path(path_type=Path), help="New output directory.")
@click.option(
    "--enable-search", is_flag=True, help="Create enabled local feed only after owner, rights and market confirmations."
)
def commerce_feed(input_file: Path, output_dir: Path, enable_search: bool) -> None:
    """Validate basic discovery fields and create a local JSONL feed."""
    try:
        candidate = json.loads(input_file.read_text(encoding="utf-8"))
        validation = validate_feed(candidate)
        output_dir.mkdir(parents=True, exist_ok=False)
        (output_dir / "validation.json").write_text(
            json.dumps(asdict(validation), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        rows = feed_rows(candidate, enable_search)
        name = "discovery-feed.jsonl" if enable_search else "discovery-feed.preview.jsonl"
        (output_dir / name).write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
        )
    except (OSError, TypeError, ValueError) as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f"Created {len(rows)} local rows; search eligibility {'enabled' if enable_search else 'disabled'}. Review validation.json; no feed was submitted."
    )
