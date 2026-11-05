"""CLI command: geo playbook."""

from __future__ import annotations

import json
from dataclasses import asdict

import click

from geo_optimizer.core.playbooks import get_playbook, list_playbooks


@click.command(name="playbook")
@click.option("--list", "list_mode", is_flag=True, help="List all built-in playbooks")
@click.option("--name", default=None, help="Playbook name to show")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
@click.option("--output", "output_file", default=None, help="Optional output file")
def playbook_cmd(list_mode: bool, name: str | None, output_format: str, output_file: str | None) -> None:
    """List/export built-in SEO/GEO playbooks."""
    if not list_mode and not name:
        raise click.UsageError("Use either '--list' or '--name <playbook>'")

    if list_mode:
        payload = list_playbooks()
        if output_format == "json":
            text = json.dumps([asdict(x) for x in payload], indent=2, ensure_ascii=False)
        else:
            lines = ["📚 PLAYBOOK LIBRARY", "=" * 64]
            for item in payload:
                lines.append(f"- {item.name} [{item.category}] — {item.description}")
            text = "\n".join(lines)
    else:
        pb = get_playbook(name or "")
        if pb is None:
            raise click.UsageError(f"Unknown playbook: {name}")
        if output_format == "json":
            text = json.dumps(asdict(pb), indent=2, ensure_ascii=False)
        else:
            text = "\n".join(
                [
                    f"# {pb.name}",
                    "",
                    f"- Category: {pb.category}",
                    f"- Description: {pb.description}",
                    "",
                    "## Template",
                    pb.template,
                ]
            )

    if output_file:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(text + ("\n" if not text.endswith("\n") else ""))
        click.echo(f"✅ Report written to: {output_file}")
    else:
        click.echo(text)
