"""CLI command: geo github."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

import click

from geo_optimizer.core.github_repo_audit import audit_github_repo, to_markdown_report


@click.command(name="github")
@click.option("--repo-path", default=None, help="Local repository path to audit")
@click.option("--repo-url", default=None, help="Remote Git repository URL to clone and audit")
@click.option("--branch", default=None, help="Optional branch name when using --repo-url")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["text", "json"]),
    default="text",
    show_default=True,
    help="Output format",
)
@click.option("--output", "output_file", default=None, help="Optional report output file")
@click.option("--write-reports", is_flag=True, help="Write GITHUB-SEO-REPORT.md and GITHUB-ACTION-PLAN.md")
def github_cmd(
    repo_path: str | None,
    repo_url: str | None,
    branch: str | None,
    output_format: str,
    output_file: str | None,
    write_reports: bool,
) -> None:
    """Audit SEO/GEO readiness for a local GitHub repository."""
    if bool(repo_path) == bool(repo_url):
        raise click.UsageError("Use exactly one source: '--repo-path' or '--repo-url'")

    cleanup_dir: str | None = None
    local_repo = repo_path
    if repo_url:
        cleanup_dir = tempfile.mkdtemp(prefix="geo-github-audit-")
        local_repo = _clone_repo(repo_url, cleanup_dir, branch=branch)
        click.echo(f"⏳ Cloned repository to {local_repo}", err=True)

    result = audit_github_repo(local_repo or "")

    if output_format == "json":
        payload = json.dumps(asdict(result), indent=2, ensure_ascii=False)
    else:
        payload = _format_text(result)

    if output_file:
        Path(output_file).write_text(payload + ("\n" if not payload.endswith("\n") else ""), encoding="utf-8")
        click.echo(f"✅ Report written to: {output_file}")
    else:
        click.echo(payload)

    if write_reports:
        report_md, plan_md = to_markdown_report(result)
        root = Path(local_repo or "").resolve()
        report_path = root / "GITHUB-SEO-REPORT.md"
        plan_path = root / "GITHUB-ACTION-PLAN.md"
        report_path.write_text(report_md, encoding="utf-8")
        plan_path.write_text(plan_md, encoding="utf-8")
        click.echo(f"✅ Wrote {report_path.name} and {plan_path.name}")

    if cleanup_dir:
        shutil.rmtree(cleanup_dir, ignore_errors=True)


def _format_text(result) -> str:
    lines = [
        "📦 GITHUB REPO SEO AUDIT",
        "=" * 64,
        f"Repository: {result.repo_path}",
        f"Score: {result.score}/100 ({result.grade})",
        f"README words: {result.readme_word_count}",
        f"README headings: {result.readme_heading_count}",
        "",
        "Recommendations:",
    ]
    lines.extend([f"  - {item}" for item in result.recommendations] or ["  - none"])
    return "\n".join(lines)


def _clone_repo(repo_url: str, workspace: str, branch: str | None = None) -> str:
    target = Path(workspace) / "repo"
    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd.extend(["--branch", branch])
    cmd.extend([repo_url, str(target)])
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise click.ClickException(f"git clone failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return str(target)
