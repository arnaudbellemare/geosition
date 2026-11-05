"""
CLI command: geo agent

Generates WebMCP / tool-calling ready endpoints so AI agents can use your
site as a tool. Future-proofs for the agent era.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

from geo_optimizer.core.agent_endpoints import run_agent_endpoint_generator
from geo_optimizer.utils.validators import validate_public_url


@click.command("agent")
@click.option("--url", required=True, help="URL of the site to prepare for AI agents")
@click.option(
    "--output-dir",
    default="./agent-endpoints",
    show_default=True,
    help="Directory to write generated endpoint files",
)
@click.option(
    "--apply",
    "do_apply",
    is_flag=True,
    help="Write files to output directory (default: preview only)",
)
def agent_cmd(url: str, output_dir: str, do_apply: bool) -> None:
    """Generate WebMCP / tool-calling endpoints for AI agent access.

    Makes your site callable as a tool by AI agents (Claude, ChatGPT,
    Perplexity, etc.). Generates the full endpoint stack:

    \b
      .well-known/ai.txt    — agent declaration
      ai/summary.json       — machine-readable site identity
      ai/faq.json           — answers agents can surface directly
      ai/service.json       — service capabilities
      ai/tools.json         — WebMCP tool definitions
      + potentialAction JSON-LD and WebMCP HTML snippets

    \b
    Examples:
      geo agent --url https://yoursite.com
      geo agent --url https://yoursite.com --apply
      geo agent --url https://yoursite.com --apply --output-dir ./public
    """
    # Validate URL
    safe, reason = validate_public_url(url)
    safe_url = url.rstrip("/")
    if not safe:
        click.echo(f"\n❌ Unsafe URL: {reason}", err=True)
        sys.exit(1)

    click.echo(f"🤖 Checking agent readiness for {safe_url} ...", err=True)

    result = run_agent_endpoint_generator(safe_url)

    # Status summary
    click.echo(f"\n📊 Agent Readiness — {result.endpoints_present}/5 endpoints present\n")

    checks = [
        ("/.well-known/ai.txt", result.has_well_known_ai),
        ("/ai/summary.json", result.has_summary),
        ("/ai/faq.json", result.has_faq),
        ("/ai/service.json", result.has_service),
        ("/ai/tools.json", result.has_tools),
    ]
    for path, present in checks:
        icon = "✅" if present else "❌"
        click.echo(f"  {icon}  {path}")

    if result.agent_ready:
        click.echo("\n✅ Site is agent-ready!\n")
    else:
        click.echo(f"\n⚠️  {5 - result.endpoints_present} endpoint(s) missing — generating now...\n")

    if not result.files:
        click.echo("Nothing to generate — all endpoints already present.")
        _show_snippets(result)
        return

    # List what will be generated
    click.echo(f"📋 {len(result.files)} file(s) to generate:\n")
    for f in result.files:
        click.echo(f"  → {f.path}")
        click.echo(f"     {f.description}\n")

    if not do_apply:
        # Preview mode
        click.echo("=" * 60)
        click.echo("PREVIEW (use --apply to write the files)")
        click.echo("=" * 60)
        for f in result.files:
            click.echo(f"\n{'─' * 40}")
            click.echo(f"📄 {f.path}")
            click.echo(f"{'─' * 40}")
            lines = f.content.splitlines()
            if len(lines) > 25:
                click.echo("\n".join(lines[:25]))
                click.echo(f"\n  ... ({len(lines) - 25} more lines)")
            else:
                click.echo(f.content)

        click.echo(f"\n💡 Run: geo agent --url {url} --apply")
    else:
        # Write files
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for f in result.files:
            dest = out / f.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(f.content, encoding="utf-8")
            click.echo(f"  ✅ {dest}")

        click.echo(f"\n✅ {len(result.files)} file(s) written to {out}/")
        click.echo("\n📁 Deploy these files to your web root so agents can reach them at:")
        for f in result.files:
            click.echo(f"   {safe_url}/{f.path}")

    _show_snippets(result)


def _show_snippets(result) -> None:
    """Print developer snippets (always shown, not written to disk)."""
    if not result.snippets:
        return

    click.echo("\n" + "=" * 60)
    click.echo("DEVELOPER SNIPPETS — add these to your site code")
    click.echo("=" * 60)

    for s in result.snippets:
        click.echo(f"\n{'─' * 40}")
        click.echo(f"📎 {s.path}")
        click.echo(f"   {s.description}")
        click.echo(f"{'─' * 40}")
        click.echo(s.content)
