"""CLI command: geo pipeline."""

from __future__ import annotations

import json
from dataclasses import asdict

import click
from bs4 import BeautifulSoup

from geo_optimizer.core.audit import run_full_audit
from geo_optimizer.core.audit_marketing import audit_marketing
from geo_optimizer.core.github_repo_audit import audit_github_repo
from geo_optimizer.utils.http import fetch_url
from geo_optimizer.utils.validators import validate_public_url


@click.command(name="pipeline")
@click.option(
    "--mode",
    type=click.Choice(["cwv", "serp", "repo"]),
    required=True,
    help="Pipeline mode: cwv (performance), serp (competitor gaps), repo (GitHub workflow)",
)
@click.option("--url", default=None, help="Target URL for cwv/serp modes")
@click.option("--repo-path", default=None, help="Repository path for repo mode")
@click.option("--keyword", default=None, help="Keyword override for serp mode")
@click.option("--format", "output_format", type=click.Choice(["text", "json"]), default="text", show_default=True)
def pipeline_cmd(mode: str, url: str | None, repo_path: str | None, keyword: str | None, output_format: str) -> None:
    """Run niche SEO pipelines (CWV, SERP, repo SEO) in one command surface."""
    if mode in {"cwv", "serp"}:
        if not url:
            raise click.UsageError("--url is required for cwv/serp modes")
        ok, err = validate_public_url(url)
        if not ok:
            raise click.UsageError(f"Invalid URL: {err}")

    if mode == "repo":
        if not repo_path:
            raise click.UsageError("--repo-path is required for repo mode")
        result = audit_github_repo(repo_path)
        if output_format == "json":
            click.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
        else:
            click.echo(
                "\n".join(
                    [
                        "📦 REPO PIPELINE",
                        "=" * 64,
                        f"Repo: {result.repo_path}",
                        f"Score: {result.score}/100 ({result.grade})",
                        "Recommendations:",
                        *[f"  - {r}" for r in result.recommendations[:8]],
                    ]
                )
            )
        return

    audit = run_full_audit(url or "")
    if audit.error:
        raise click.ClickException(audit.error)

    if mode == "cwv":
        payload = {
            "url": url,
            "perf_score": getattr(audit.perf, "perf_score", 0),
            "issues": [asdict(i) for i in getattr(audit.perf, "issues", [])[:20]],
            "conversion_score": getattr(audit.conversion, "conversion_score", 0),
            "tracking_score": getattr(audit.tracking, "tracking_score", 0),
        }
        if output_format == "json":
            click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            click.echo(
                "\n".join(
                    [
                        "⚡ CWV PIPELINE",
                        "=" * 64,
                        f"URL: {url}",
                        f"Performance score: {payload['perf_score']}/100",
                        f"Conversion score: {payload['conversion_score']}/100",
                        f"Tracking score: {payload['tracking_score']}/100",
                    ]
                )
            )
        return

    # mode == serp
    response, err = fetch_url(url or "")
    if err or response is None:
        raise click.ClickException(err or "Unable to fetch page for SERP pipeline")
    soup = BeautifulSoup(response.text, "html.parser")
    marketing = audit_marketing(
        soup=soup,
        base_url=url or "",
        schema=audit.schema,
        meta=audit.meta,
        content=audit.content,
        conversion=audit.conversion,
        citability=audit.citability,
        run_serp=True,
        geo_result=audit,
        keyword=keyword,
    )
    serp = marketing.serp
    payload = {
        "url": url,
        "keyword": serp.keyword,
        "competitors": [asdict(c) for c in serp.competitors[:10]],
        "word_count_gap": serp.word_count_gap,
        "crowdedness_score": serp.crowdedness_score,
        "crowdedness_label": serp.crowdedness_label,
        "serp_features": serp.serp_features,
        "keyword_gaps": serp.keyword_gaps[:20],
        "page1_requirements": serp.page1_requirements[:20],
    }
    if output_format == "json":
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        click.echo(
            "\n".join(
                [
                    "🔎 SERP PIPELINE",
                    "=" * 64,
                    f"URL: {url}",
                    f"Keyword: {payload['keyword']}",
                    f"Competitors analyzed: {len(serp.competitors[:10])}",
                    f"SERP crowdedness: {payload['crowdedness_score']}/100 ({payload['crowdedness_label']})",
                    f"Word-count gap: {payload['word_count_gap']}",
                    "Top requirements:",
                    *[f"  - {item}" for item in serp.page1_requirements[:6]],
                ]
            )
        )
