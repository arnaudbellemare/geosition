"""GEOSITION branded local command center.

This CLI wraps the existing GEOSITION audit and web surfaces with a product
command that can be installed as `geosition`.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

import click

from geo_optimizer import __version__

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001
DEFAULT_PLATFORM_PATH = "/platform"
DEFAULT_PACKAGE_SOURCE = "geosition[web]"
DEMO_DOMAIN = "example.com"


def _geosition_home() -> Path:
    return Path(os.environ.get("GEOSITION_HOME", "~/.geosition")).expanduser()


def _geosition_config_path() -> Path:
    return _geosition_home() / "config.json"


def _runs_dir(output_dir: Optional[str] = None) -> Path:
    if output_dir:
        return Path(output_dir).expanduser()
    return _geosition_home() / "runs"


def _platform_url(host: str, port: int, path: str = DEFAULT_PLATFORM_PATH) -> str:
    clean_path = path if path.startswith("/") else f"/{path}"
    return f"http://{host}:{port}{clean_path}"


def _health_url(host: str, port: int) -> str:
    return f"http://{host}:{port}/health"


def _platform_api_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _server_reachable(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with urlopen(_health_url(host, port), timeout=timeout) as response:  # noqa: S310 - localhost health check only
            return 200 <= int(response.status) < 500
    except (OSError, URLError, ValueError):
        return False


def _port_listening(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _normalize_url(target: str) -> str:
    value = target.strip()
    if value.startswith(("http://", "https://")):
        return value
    return f"https://{value}"


def _slug_from_target(target: str) -> str:
    slug = re.sub(r"^https?://", "", target.strip().lower())
    slug = re.sub(r"[^a-z0-9.-]+", "-", slug).strip("-")
    return slug or "domain"


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _open_when_ready(host: str, port: int, url: str, timeout: float = 12.0) -> None:
    def _poll() -> None:
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _server_reachable(host, port):
                webbrowser.open(url)
                return
            time.sleep(0.25)

    timer = threading.Thread(target=_poll, daemon=True)
    timer.daemon = True
    timer.start()


def _require_safe_url(target: str) -> str:
    from geo_optimizer.utils.validators import validate_public_url

    url = _normalize_url(target)
    safe, reason = validate_public_url(url)
    if not safe:
        raise click.ClickException(f"Unsafe URL: {reason}")
    return url


def _score_color(score: int) -> str:
    if score >= 86:
        return "#1f8a4c"
    if score >= 68:
        return "#2563eb"
    if score >= 36:
        return "#b7791f"
    return "#b42318"


def _top_actions(result: Any, limit: int = 5) -> list[str]:
    actions = []
    for action in getattr(result, "next_actions", [])[:limit]:
        gain = getattr(action, "expected_score_gain", "")
        suffix = f" (+{gain})" if gain != "" else ""
        actions.append(f"{getattr(action, 'title', 'Next action')}{suffix}")
    if actions:
        return actions
    return [str(item) for item in getattr(result, "recommendations", [])[:limit]]


def _render_audit_report_html(result: Any, payload: Dict[str, Any]) -> str:
    actions = "".join(f"<li>{escape(item)}</li>" for item in _top_actions(result, limit=5))
    breakdown = payload.get("score_breakdown", {})
    rows = "".join(
        f"<tr><td>{escape(str(key).replace('_', ' ').title())}</td><td>{escape(str(value))}</td></tr>"
        for key, value in breakdown.items()
    )
    score = int(getattr(result, "score", 0) or 0)
    color = _score_color(score)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GEOSITION AI Citation Readiness - {escape(getattr(result, "url", ""))}</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ margin: 0; background: #f7f7f4; color: #111113; }}
    main {{ max-width: 980px; margin: 0 auto; padding: 56px 24px; }}
    .sheet {{ background: #fff; border: 1px solid #e5e1d8; padding: clamp(28px, 5vw, 56px); }}
    .eyebrow {{ color: #6f6f76; text-transform: uppercase; letter-spacing: .14em; font-size: 12px; font-weight: 700; }}
    h1 {{ max-width: 720px; margin: 18px 0; font-family: Georgia, "Times New Roman", serif; font-size: clamp(38px, 7vw, 76px); line-height: .96; font-weight: 400; }}
    .url {{ color: #6f6f76; font-size: 18px; }}
    .score {{ display: flex; align-items: end; gap: 16px; margin: 44px 0 28px; }}
    .score strong {{ color: {color}; font-size: clamp(72px, 14vw, 148px); line-height: .8; letter-spacing: -.08em; }}
    .score span {{ color: #55565d; font-size: 22px; padding-bottom: 8px; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 28px; margin-top: 36px; }}
    h2 {{ font-size: 14px; text-transform: uppercase; letter-spacing: .12em; color: #6f6f76; }}
    li {{ margin: 12px 0; line-height: 1.45; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 14px; }}
    td {{ padding: 12px 0; border-bottom: 1px solid #ece8df; }}
    td:last-child {{ text-align: right; font-weight: 700; }}
    .note {{ margin-top: 42px; color: #6f6f76; font-size: 14px; line-height: 1.55; }}
    @media (max-width: 760px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <section class="sheet">
      <div class="eyebrow">GEOSITION AI citation readiness</div>
      <h1>Will agents choose this domain?</h1>
      <p class="url">{escape(getattr(result, "url", ""))}</p>
      <div class="score"><strong>{score}</strong><span>/100 - {escape(str(getattr(result, "band", "")))}</span></div>
      <div class="grid">
        <section>
          <h2>Top fixes</h2>
          <ol>{actions or "<li>Keep monitoring citation readiness after content updates.</li>"}</ol>
        </section>
        <section>
          <h2>Score calculation</h2>
          <table>{rows}</table>
        </section>
      </div>
      <p class="note">Scores are computed from the open GEOSITION rubric: robots access, llms.txt, schema, metadata, content, technical signals, AI discovery, and brand/entity clarity. The JSON artifact next to this report contains the full evidence trail.</p>
    </section>
  </main>
</body>
</html>"""


def _render_autopilot_report_html(artifact: Dict[str, Any]) -> str:
    iterations = artifact.get("iterations", [])
    first = iterations[0] if iterations else {}
    last = iterations[-1] if iterations else {}
    first_score = int(first.get("audit", {}).get("score", 0) or 0)
    planned_score = int(
        last.get("post_audit", {}).get(
            "score",
            last.get("fix_plan", {}).get("score_estimated_after", last.get("audit", {}).get("score", 0)),
        )
        or 0
    )
    fixes = first.get("fix_plan", {}).get("fixes", [])
    fix_items = "".join(
        f"<li><strong>{escape(str(item.get('file_name', 'generated')))}</strong><br>{escape(str(item.get('description', '')))}</li>"
        for item in fixes
    )
    generated: list[str] = []
    for iteration in iterations:
        applied = iteration.get("applied") or {}
        generated.extend(applied.get("applied_files", []) or [])
    generated_items = "".join(f"<li>{escape(path)}</li>" for path in generated[:20])
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>GEOSITION Autopilot Run</title>
  <style>
    body {{ margin: 0; background: #0f1115; color: #f5f5f0; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    main {{ max-width: 1040px; margin: 0 auto; padding: 56px 24px; }}
    .panel {{ border: 1px solid rgba(255,255,255,.16); padding: clamp(28px, 5vw, 56px); background: linear-gradient(135deg, #151821, #0f1115); }}
    h1 {{ max-width: 800px; font-family: Georgia, "Times New Roman", serif; font-size: clamp(42px, 7vw, 86px); line-height: .95; font-weight: 400; margin: 0 0 32px; }}
    .scores {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 34px; }}
    .score {{ min-width: 180px; padding: 22px; border: 1px solid rgba(255,255,255,.14); }}
    .score span {{ color: #a8abb4; font-size: 12px; text-transform: uppercase; letter-spacing: .12em; }}
    .score strong {{ display: block; font-size: 64px; line-height: .9; }}
    .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 28px; }}
    h2 {{ color: #a8abb4; font-size: 13px; text-transform: uppercase; letter-spacing: .12em; }}
    li {{ margin: 12px 0; line-height: 1.45; color: #e8e8e2; }}
    @media (max-width: 760px) {{ .grid {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <main>
    <section class="panel">
      <h1>Autopilot evidence run</h1>
      <div class="scores">
        <div class="score"><span>Before</span><strong>{first_score}</strong></div>
        <div class="score"><span>Planned after</span><strong>{planned_score}</strong></div>
        <div class="score"><span>Delta</span><strong>{planned_score - first_score:+d}</strong></div>
      </div>
      <div class="grid">
        <section><h2>Generated fix plan</h2><ol>{fix_items or "<li>No file-safe fixes generated.</li>"}</ol></section>
        <section><h2>Generated files</h2><ol>{generated_items or "<li>Dry run. Add --apply to write generated files.</li>"}</ol></section>
      </div>
    </section>
  </main>
</body>
</html>"""


def _render_citation_report_html(payload: Dict[str, Any]) -> str:
    title = payload.get("title", "AI Citation Report")
    domain = payload.get("domain", "")
    metrics = payload.get("metrics", [])
    rows = "".join(
        f"<article><span>{escape(str(item.get('label', 'Metric')))}</span><strong>{escape(str(item.get('value', '')))}</strong><p>{escape(str(item.get('note', '')))}</p></article>"
        for item in metrics
    )
    actions = "".join(f"<li>{escape(item)}</li>" for item in payload.get("actions", []))
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(title)} - {escape(domain)}</title>
  <style>
    body {{ margin: 0; background: #fff; color: #111113; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    main {{ max-width: 1120px; margin: 0 auto; padding: 56px 24px; }}
    h1 {{ max-width: 760px; font-family: Georgia, "Times New Roman", serif; font-size: clamp(42px, 7vw, 88px); line-height: .94; font-weight: 400; margin: 0; }}
    .domain {{ margin: 20px 0 40px; color: #696a70; font-size: 20px; }}
    .metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); border: 1px solid #e7e2d8; }}
    article {{ min-height: 180px; padding: 28px; border-right: 1px solid #e7e2d8; border-bottom: 1px solid #e7e2d8; }}
    article span {{ color: #696a70; font-size: 12px; text-transform: uppercase; letter-spacing: .12em; }}
    article strong {{ display: block; margin: 22px 0; font-size: clamp(42px, 7vw, 76px); line-height: .8; letter-spacing: -.06em; }}
    article p, li {{ color: #696a70; line-height: 1.5; }}
    .actions {{ margin-top: 40px; display: grid; grid-template-columns: .7fr 1fr; gap: 40px; }}
    h2 {{ font-size: 13px; text-transform: uppercase; letter-spacing: .12em; color: #696a70; }}
    @media (max-width: 860px) {{ .metrics, .actions {{ grid-template-columns: 1fr; }} article {{ border-right: 0; }} }}
  </style>
</head>
<body>
  <main>
    <h1>{escape(title)}</h1>
    <p class="domain">{escape(domain)}</p>
    <section class="metrics">{rows}</section>
    <section class="actions"><h2>Agency next steps</h2><ol>{actions}</ol></section>
  </main>
</body>
</html>"""


def _examples_dir() -> Path:
    return Path(__file__).resolve().parents[3] / "examples" / "demo"


def _starter_competitors() -> list[str]:
    return ["rival-one.example", "rival-two.example"]


def _citation_report_payload(
    domain: str,
    audit_score: int = 72,
    citation_share: str = "34%",
    provider_coverage: str = "4",
    prompt_count: str = "128",
) -> Dict[str, Any]:
    return {
        "title": "AI Citation Report",
        "domain": domain,
        "metrics": [
            {
                "label": "Audit score",
                "value": f"{audit_score}/100",
                "note": "GEOSITION GEO score across robots, llms.txt, schema, metadata, content, signals, AI discovery, and entity clarity.",
            },
            {
                "label": "Citation share",
                "value": citation_share,
                "note": "How often agents cite the target domain across the current prompt set.",
            },
            {
                "label": "Provider coverage",
                "value": provider_coverage,
                "note": "Providers compared side by side for the same buyer and category prompts.",
            },
            {
                "label": "Prompt set",
                "value": prompt_count,
                "note": "Repeatable questions across buyer journeys, local searches, and category research.",
            },
            {
                "label": "Collection model",
                "value": "Local",
                "note": "Artifacts stay portable: JSON evidence, HTML client reports, and generated fix files.",
            },
            {
                "label": "Next review",
                "value": "Weekly",
                "note": "Hosted teams can schedule recurring monitoring and managed collection.",
            },
        ],
        "actions": [
            "Verify domain ownership and attach all future runs to the workspace.",
            "Fix the top five score gaps before expanding prompt coverage.",
            "Run the same prompt set against nearby competitors every week.",
            "Send this report with the JSON artifact as the client evidence trail.",
        ],
    }


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="geosition")
def geosition() -> None:
    """GEOSITION local AI citation command center."""


@geosition.command(name="init")
@click.option("--host", default=DEFAULT_HOST, show_default=True, help="Default platform host.")
@click.option("--port", default=DEFAULT_PORT, show_default=True, help="Default platform port.")
@click.option("--force", is_flag=True, help="Overwrite the existing local config.")
def init_command(host: str, port: int, force: bool) -> None:
    """Initialize local GEOSITION directories and platform config."""
    home = _geosition_home()
    config_path = _geosition_config_path()
    if config_path.exists() and not force:
        click.echo(f"GEOSITION is already initialized: {config_path}")
        click.echo("Next: geosition start")
        return

    for directory in (home, home / "runs", home / "workspace", home / "logs", home / "telemetry"):
        directory.mkdir(parents=True, exist_ok=True)

    config = {
        "version": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "platform": {
            "host": host,
            "port": port,
            "url": _platform_url(host, port),
        },
        "storage": {
            "home": str(home),
            "runs": str(home / "runs"),
            "workspace": str(home / "workspace"),
            "telemetry": str(home / "telemetry"),
        },
        "worker": {
            "answers_file_env": "GEOSITION_WORKER_ANSWERS_FILE",
            "benchmark_db_env": "GEO_BENCHMARK_DB",
            "note": "DNS verification unlocks trust; benchmark answers or telemetry integrations provide evidence.",
        },
        "next_commands": [
            "geosition start",
            "geosition worker start --once --answers-file answers.json",
        ],
    }
    _write_json(config_path, config)
    click.echo(f"Initialized GEOSITION: {config_path}")
    click.echo(f"Platform: {_platform_url(host, port)}")
    click.echo("Next:")
    click.echo("  geosition start")
    click.echo("  # after domain verification and answers collection:")
    click.echo("  geosition worker start --once --answers-file answers.json")


@geosition.command()
@click.option("--host", default=DEFAULT_HOST, show_default=True, help="Host to listen on.")
@click.option("--port", default=DEFAULT_PORT, show_default=True, help="Port to listen on.")
@click.option(
    "--path", "platform_path", default=DEFAULT_PLATFORM_PATH, show_default=True, help="Initial platform path."
)
@click.option("--reload", is_flag=True, help="Enable uvicorn reload for local development.")
@click.option("--no-open", is_flag=True, help="Do not open the browser automatically.")
def start(host: str, port: int, platform_path: str, reload: bool, no_open: bool) -> None:
    """Start the local GEOSITION platform in the foreground."""
    try:
        import uvicorn
    except ImportError as exc:
        raise click.ClickException("uvicorn is not installed. Reinstall with: geosition update") from exc

    url = _platform_url(host, port, platform_path)
    if _server_reachable(host, port):
        click.echo(f"GEOSITION platform is already running: {url}")
        if not no_open:
            webbrowser.open(url)
            click.echo(f"Opened {url}")
        return

    if _port_listening(host, port):
        raise click.ClickException(
            f"Port {port} is already in use, but GEOSITION health is not reachable. "
            f"Stop that process or run: geosition start --port {port + 1}"
        )

    click.echo(f"GEOSITION platform: {url}")
    click.echo("Server is foreground-only. Press Ctrl+C to stop it.")
    if not no_open:
        _open_when_ready(host, port, url)
    uvicorn.run("geo_optimizer.web.app:app", host=host, port=port, reload=reload)


@geosition.command()
@click.option("--host", default=DEFAULT_HOST, show_default=True, help="Host to check.")
@click.option("--port", default=DEFAULT_PORT, show_default=True, help="Port to check.")
def status(host: str, port: int) -> None:
    """Show local GEOSITION install and server status."""
    home = _geosition_home()
    reachable = _server_reachable(host, port)
    listening = _port_listening(host, port)

    click.echo(f"GEOSITION home: {home} ({'present' if home.exists() else 'missing'})")
    click.echo(f"Runs: {home / 'runs'} ({'present' if (home / 'runs').exists() else 'missing'})")
    click.echo(f"Platform URL: {_platform_url(host, port)}")
    click.echo(f"Port {port}: {'listening' if listening else 'not listening'}")
    click.echo(f"Platform health: {'reachable' if reachable else 'not reachable'}")
    if not reachable:
        click.echo(f"Start it with: geosition start --port {port}")


@geosition.command()
@click.option("--host", default=DEFAULT_HOST, show_default=True, help="Host to check.")
@click.option("--port", default=DEFAULT_PORT, show_default=True, help="Port to check.")
def doctor(host: str, port: int) -> None:
    """Check the local GEOSITION runtime."""
    from geo_optimizer.storage.paths import resolve_collection_home, resolve_data_dir, resolve_platform_db_path

    checks = [
        ("Python", sys.version.split()[0], sys.version_info >= (3, 9)),
        ("click", "installed", importlib.util.find_spec("click") is not None),
        ("fastapi", "installed", importlib.util.find_spec("fastapi") is not None),
        ("uvicorn", "installed", importlib.util.find_spec("uvicorn") is not None),
        (
            "platform templates",
            "present",
            (Path(__file__).resolve().parents[1] / "web" / "templates" / "platform").is_dir(),
        ),
        ("data dir", str(resolve_data_dir()), True),
        ("collection dir", str(resolve_collection_home()), True),
        ("platform db", str(resolve_platform_db_path()), True),
    ]
    server_ok = _server_reachable(host, port)

    failed = False
    for name, detail, ok in checks:
        failed = failed or not ok
        click.echo(f"{'OK' if ok else 'MISSING'}  {name}: {detail}")

    click.echo(f"{'OK' if server_ok else 'OFFLINE'}  local server: {_health_url(host, port)}")

    if failed:
        raise click.ClickException("GEOSITION doctor found issues. See rows marked MISSING.")
    click.echo("GEOSITION doctor passed.")


@geosition.command()
@click.pass_context
@click.option("--host", default=DEFAULT_HOST, show_default=True, help="Host to open.")
@click.option("--port", default=DEFAULT_PORT, show_default=True, help="Port to open.")
@click.option(
    "--path", "platform_path", default=DEFAULT_PLATFORM_PATH, show_default=True, help="Platform path to open."
)
@click.option("--start-if-missing", is_flag=True, help="Start the foreground server if it is not running.")
def dashboard(ctx: click.Context, host: str, port: int, platform_path: str, start_if_missing: bool) -> None:
    """Open the local GEOSITION dashboard."""
    url = _platform_url(host, port, platform_path)
    if not _server_reachable(host, port):
        if start_if_missing:
            ctx.invoke(start, host=host, port=port, platform_path=platform_path, reload=False, no_open=False)
            return
        raise click.ClickException(f"GEOSITION is not running. Start it with: geosition start --port {port}")
    webbrowser.open(url)
    click.echo(f"Opened {url}")


@geosition.command(name="wizard")
@click.pass_context
@click.option("--output-dir", default=None, help="Directory for first-run artifacts.")
@click.option("--demo", is_flag=True, help="Use the seeded demo domain and answers.")
def wizard(ctx: click.Context, output_dir: Optional[str], demo: bool) -> None:
    """Run the first GEOSITION setup flow."""
    workspace_dir = _geosition_home() / "workspace"
    runs_dir = _runs_dir(output_dir)

    click.echo("GEOSITION first-run wizard")
    domain_default = DEMO_DOMAIN if demo else ""
    if domain_default:
        domain = click.prompt("Domain", default=domain_default)
    else:
        domain = click.prompt("Domain")
    email = click.prompt("Account email")
    url = _normalize_url(domain)
    slug = _slug_from_target(url)
    token = f"geosition-verify-{secrets.token_hex(8)}"

    click.echo("\nVerify ownership")
    click.echo(f"DNS TXT: _geosition.{slug} = {token}")
    click.echo(f"HTTPS file: https://{slug}/.well-known/geosition.txt with body: {token}")
    verified = click.confirm("Mark this domain verified for the local workspace?", default=demo)

    click.echo("\nAudit")
    run_audit = click.confirm("Run audit now?", default=True)
    audit_json = None
    if run_audit:
        ctx.invoke(
            run_command,
            target=url,
            output_dir=str(runs_dir),
            open_dashboard=False,
            host=DEFAULT_HOST,
            port=DEFAULT_PORT,
        )
        newest = sorted(runs_dir.glob(f"{slug}-*.json"))
        audit_json = str(newest[-1]) if newest else None

    click.echo("\nCompetitors")
    default_competitors = ", ".join(_starter_competitors() if demo else [])
    competitors_raw = click.prompt("Competitor domains, comma-separated", default=default_competitors)
    competitors = [item.strip() for item in competitors_raw.split(",") if item.strip()]

    click.echo("\nBenchmark")
    answers_file = ""
    if demo:
        answers_file = str(_examples_dir() / "benchmark-answers.json")
    else:
        answers_file = click.prompt("Answers JSON path (leave blank to create the benchmark plan only)", default="")

    benchmark_json = None
    if answers_file:
        from geo_optimizer.cli.benchmark_cmd import _load_answers_file
        from geo_optimizer.cli.benchmark_formatter import format_benchmark_json
        from geo_optimizer.core.benchmark.runner import run_domain_benchmark
        from geo_optimizer.core.benchmark.store import BenchmarkStore

        answers_path = Path(answers_file).expanduser()
        answers = _load_answers_file(answers_path)
        result = run_domain_benchmark(
            slug,
            competitors=competitors,
            answers=answers,
            audit_url=None,
            store=BenchmarkStore(runs_dir / f"{slug}-benchmark.sqlite"),
            use_cache=True,
        )
        benchmark_json_path = runs_dir / f"{slug}-benchmark-{_utc_stamp()}.json"
        _write_json(benchmark_json_path, json.loads(format_benchmark_json(result)))
        benchmark_json = str(benchmark_json_path)
        click.echo(f"Benchmark score: {result.benchmark_score}/100 ({result.band})")
        click.echo(f"Saved benchmark: {benchmark_json_path}")
    else:
        click.echo("Benchmark plan saved. Add collected answers later with: geo benchmark collect")

    workspace = {
        "domain": slug,
        "url": url,
        "work_email": email,
        "verified": verified,
        "verification_token": token,
        "competitors": competitors,
        "audit_artifact": audit_json,
        "benchmark_artifact": benchmark_json,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "next_commands": [
            "geosition start",
            f"geosition run {slug}",
            f"geosition autopilot {slug}",
            f"geosition citation-report {slug}",
        ],
    }
    workspace_path = workspace_dir / f"{slug}-workspace.json"
    _write_json(workspace_path, workspace)
    click.echo(f"\nSaved workspace: {workspace_path}")
    click.echo("Next: geosition start")


@geosition.command(name="first-run")
@click.pass_context
@click.option("--output-dir", default=None, help="Directory for first-run artifacts.")
@click.option("--demo", is_flag=True, help="Use the seeded demo domain and answers.")
def first_run(ctx: click.Context, output_dir: Optional[str], demo: bool) -> None:
    """Alias for the first-run wizard."""
    ctx.invoke(wizard, output_dir=output_dir, demo=demo)


@geosition.command(name="run")
@click.argument("target", metavar="DOMAIN_OR_URL")
@click.option("--output-dir", default=None, help="Directory for JSON run artifacts.")
@click.option("--open-dashboard", is_flag=True, help="Open /platform if the local server is already running.")
@click.option("--host", default=DEFAULT_HOST, show_default=True, help="Dashboard host.")
@click.option("--port", default=DEFAULT_PORT, show_default=True, help="Dashboard port.")
def run_command(target: str, output_dir: Optional[str], open_dashboard: bool, host: str, port: int) -> None:
    """Audit a domain and save a portable GEOSITION run artifact."""
    from geo_optimizer.cli.formatters import format_audit_json
    from geo_optimizer.core.audit import run_full_audit

    url = _require_safe_url(target)
    click.echo(f"Running GEOSITION audit for {url}")
    result = run_full_audit(url)
    payload = json.loads(format_audit_json(result))
    payload["geosition"] = {"command": "run", "created_at": datetime.now(timezone.utc).isoformat()}

    out = _runs_dir(output_dir) / f"{_slug_from_target(url)}-{_utc_stamp()}.json"
    html_out = out.with_suffix(".html")
    _write_json(out, payload)
    _write_text(html_out, _render_audit_report_html(result, payload))

    click.echo(f"Score: {result.score}/100 ({result.band})")
    if getattr(result, "next_actions", None):
        click.echo("Next actions:")
        for action in result.next_actions[:3]:
            click.echo(f"  - {action.title} [{action.priority}]")
    click.echo(f"Saved run: {out}")
    click.echo(f"Saved local report: {html_out}")

    if open_dashboard and _server_reachable(host, port):
        webbrowser.open(_platform_url(host, port))


@geosition.command(name="weekly-report")
@click.argument("target", metavar="DOMAIN_OR_URL")
@click.option("--answers-file", type=click.Path(path_type=Path), help="Canonical benchmark answers JSON.")
@click.option("--competitor", "competitors", multiple=True, help="Competitor domain to compare in benchmark evidence.")
@click.option(
    "--log-file", type=click.Path(path_type=Path), help="Apache/Nginx/JSON server log for AI crawler evidence."
)
@click.option(
    "--lighthouse-provider",
    type=click.Choice(["pagespeed", "cli", "none"]),
    default="pagespeed",
    show_default=True,
    help="Lighthouse provider for weekly SEO/performance evidence.",
)
@click.option("--no-lighthouse", is_flag=True, help="Skip Lighthouse collection.")
@click.option("--benchmark-db", type=click.Path(path_type=Path), help="Benchmark SQLite database path.")
@click.option("--output-dir", default=None, help="Directory for JSON/HTML report artifacts.")
@click.option(
    "--format", "output_format", type=click.Choice(["json", "html", "both"]), default="both", show_default=True
)
def weekly_report(
    target: str,
    answers_file: Optional[Path],
    competitors: tuple[str, ...],
    log_file: Optional[Path],
    lighthouse_provider: str,
    no_lighthouse: bool,
    benchmark_db: Optional[Path],
    output_dir: Optional[str],
    output_format: str,
) -> None:
    """Run a weekly company evidence report for AI, SEO, CRO, and crawler access."""
    from geo_optimizer.cli.benchmark_cmd import _load_answers_file
    from geo_optimizer.core.benchmark.store import BenchmarkStore
    from geo_optimizer.saas.weekly_evidence import build_weekly_evidence_report, render_weekly_evidence_html

    url = _require_safe_url(target)
    answers_payload: dict[str, Any] | list[Any] | None = None
    if answers_file:
        answers_payload = _load_answers_file(answers_file)

    provider = "none" if no_lighthouse else lighthouse_provider
    store = BenchmarkStore(benchmark_db) if benchmark_db else None
    click.echo(f"Running weekly evidence report for {url}")
    report = build_weekly_evidence_report(
        url,
        answers_payload=answers_payload,
        competitors=list(competitors),
        log_file=log_file,
        lighthouse_provider=provider,
        benchmark_store=store,
    )

    out = _runs_dir(output_dir) / f"{_slug_from_target(url)}-weekly-evidence-{_utc_stamp()}.json"
    html_out = out.with_suffix(".html")
    if output_format in {"json", "both"}:
        _write_json(out, report)
        click.echo(f"Saved weekly JSON: {out}")
    if output_format in {"html", "both"}:
        _write_text(html_out, render_weekly_evidence_html(report))
        click.echo(f"Saved weekly HTML: {html_out}")
    click.echo(f"Weekly score: {report['score']}/100 ({report['band']})")
    click.echo(str(report["summary"]))


@geosition.command(name="citation-report")
@click.argument("domain")
@click.option("--score", "audit_score", default=72, show_default=True, type=int, help="Audit score to display.")
@click.option("--citation-share", default="34%", show_default=True, help="Citation share to display.")
@click.option("--provider-coverage", default="4", show_default=True, help="Provider coverage to display.")
@click.option("--prompt-count", default="128", show_default=True, help="Prompt count to display.")
@click.option("--output", "output_file", default=None, help="HTML output path.")
def citation_report(
    domain: str,
    audit_score: int,
    citation_share: str,
    provider_coverage: str,
    prompt_count: str,
    output_file: Optional[str],
) -> None:
    """Create a one-page AI citation report for clients."""
    slug = _slug_from_target(domain)
    payload = _citation_report_payload(
        slug,
        audit_score=max(0, min(100, audit_score)),
        citation_share=citation_share,
        provider_coverage=provider_coverage,
        prompt_count=prompt_count,
    )
    out = (
        Path(output_file).expanduser()
        if output_file
        else _runs_dir() / f"{slug}-ai-citation-report-{_utc_stamp()}.html"
    )
    _write_text(out, _render_citation_report_html(payload))
    click.echo(f"Saved AI citation report: {out}")


@geosition.command()
@click.argument("target", metavar="DOMAIN_OR_URL")
@click.option("--repo", "repo_path", default=".", show_default=True, help="Local repo path for file-safe fixes.")
@click.option("--apply", "do_apply", is_flag=True, help="Apply generated file-safe fixes.")
@click.option("--max-iterations", default=1, show_default=True, type=int, help="Optimization cycles.")
@click.option("--output-dir", default=None, help="Directory for JSON run artifacts.")
def autopilot(target: str, repo_path: str, do_apply: bool, max_iterations: int, output_dir: Optional[str]) -> None:
    """Run audit, generate fixes, optionally apply them, and save the run."""
    from geo_optimizer.cli.formatters import format_audit_json
    from geo_optimizer.core.audit import run_full_audit
    from geo_optimizer.core.fixer import run_all_fixes
    from geo_optimizer.core.site_integrator import apply_fix_plan_to_repo

    url = _require_safe_url(target)
    repo = Path(repo_path).resolve()
    artifact: Dict[str, Any] = {
        "geosition": {
            "command": "autopilot",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "repo": str(repo),
            "apply": do_apply,
        },
        "iterations": [],
    }

    for index in range(max(1, max_iterations)):
        click.echo(f"Iteration {index + 1}/{max(1, max_iterations)}: {url}")
        audit_result = run_full_audit(url)
        fix_plan = run_all_fixes(url=url, audit_result=audit_result)
        iteration: Dict[str, Any] = {
            "audit": json.loads(format_audit_json(audit_result)),
            "fix_plan": asdict(fix_plan),
            "generated_fixes": [item.description for item in fix_plan.fixes],
            "applied": None,
            "post_audit": None,
        }
        click.echo(f"Score: {audit_result.score}/100 ({audit_result.band})")
        click.echo(f"Generated fixes: {len(fix_plan.fixes)}")

        if do_apply and fix_plan.fixes:
            outcome = apply_fix_plan_to_repo(repo, fix_plan.fixes)
            iteration["applied"] = asdict(outcome)
            click.echo(f"Applied files: {len(outcome.applied_files)}")
        elif not do_apply:
            click.echo("Dry run. Add --apply to patch file-safe artifacts.")

        artifact["iterations"].append(iteration)
        if not do_apply:
            break

    out = _runs_dir(output_dir) / f"{_slug_from_target(url)}-autopilot-{_utc_stamp()}.json"
    html_out = out.with_suffix(".html")
    _write_json(out, artifact)
    _write_text(html_out, _render_autopilot_report_html(artifact))
    click.echo(f"Saved autopilot run: {out}")
    click.echo(f"Saved autopilot report: {html_out}")


@geosition.command()
@click.option("--output-dir", default=None, help="Directory for seeded demo artifacts.")
def demo(output_dir: Optional[str]) -> None:
    """Install a seeded demo domain with answers, benchmark, and client report."""
    from geo_optimizer.cli.benchmark_cmd import _load_answers_file
    from geo_optimizer.cli.benchmark_formatter import format_benchmark_json
    from geo_optimizer.core.benchmark.runner import run_domain_benchmark
    from geo_optimizer.core.benchmark.store import BenchmarkStore

    source = _examples_dir()
    if not source.exists():
        raise click.ClickException(f"Demo fixtures not found: {source}")

    demo_dir = (
        (_runs_dir(output_dir).parent / "demo" / DEMO_DOMAIN)
        if output_dir
        else (_geosition_home() / "demo" / DEMO_DOMAIN)
    )
    demo_dir.mkdir(parents=True, exist_ok=True)
    for name in ("README.md", "benchmark-prompts.json", "benchmark-answers.json"):
        shutil.copyfile(source / name, demo_dir / name)

    competitors = _starter_competitors()
    answers = _load_answers_file(demo_dir / "benchmark-answers.json")
    benchmark = run_domain_benchmark(
        DEMO_DOMAIN,
        competitors=competitors,
        answers=answers,
        audit_url=None,
        store=BenchmarkStore(demo_dir / "benchmark.sqlite"),
        use_cache=True,
    )
    benchmark_path = demo_dir / "benchmark-run.json"
    _write_json(benchmark_path, json.loads(format_benchmark_json(benchmark)))

    providers = {metric.provider for metric in benchmark.task_metrics if metric.provider}
    report_payload = _citation_report_payload(
        DEMO_DOMAIN,
        audit_score=78,
        citation_share=f"{benchmark.breakdown.citation_share}%",
        provider_coverage=str(len(providers) or 4),
        prompt_count=str(len(answers)),
    )
    report_path = demo_dir / "ai-citation-report.html"
    _write_text(report_path, _render_citation_report_html(report_payload))

    workspace_path = demo_dir / "workspace.json"
    _write_json(
        workspace_path,
        {
            "domain": DEMO_DOMAIN,
            "work_email": "owner@example.com",
            "verified": True,
            "competitors": competitors,
            "benchmark_artifact": str(benchmark_path),
            "client_report": str(report_path),
            "commands": [
                "geosition start",
                f"geosition run {DEMO_DOMAIN}",
                f"geosition citation-report {DEMO_DOMAIN}",
                f"geo benchmark run {DEMO_DOMAIN} --answers-file {demo_dir / 'benchmark-answers.json'} --no-audit",
            ],
        },
    )
    click.echo(f"Seeded demo workspace: {workspace_path}")
    click.echo(f"Demo benchmark: {benchmark_path}")
    click.echo(f"Client report: {report_path}")


@geosition.command()
@click.option("--source", default=None, help="Package source to install. Defaults to geosition[web].")
def update(source: Optional[str]) -> None:
    """Upgrade the installed GEOSITION app package."""
    package_source = source or os.environ.get("GEOSITION_INSTALL_SOURCE") or DEFAULT_PACKAGE_SOURCE
    click.echo(f"Updating GEOSITION from {package_source}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", package_source])


def _run_hosted_platform_worker_once(*, platform_url: str, worker_token: str, domain: str = "") -> None:
    """Poll hosted GEOSITION worker queues once."""
    for path, label in (
        ("/api/v1/audit/sitemap/run", "page audit"),
        ("/api/v1/collection/run", "hosted collection"),
    ):
        payload = json.dumps({"domain": domain, "providers": []}).encode("utf-8")
        request = Request(  # noqa: S310 - operator-configured platform URL for hosted worker mode.
            _platform_api_url(platform_url, path),
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-GEOSITION-Worker-Token": worker_token,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:  # noqa: S310 - see Request construction above.
                body = response.read().decode("utf-8")
        except (OSError, URLError, ValueError) as exc:
            click.echo(f"Hosted {label} poll failed: {exc}")
            continue
        try:
            data = json.loads(body or "{}")
        except json.JSONDecodeError:
            click.echo(f"Hosted {label} poll returned non-JSON response.")
            continue
        status = str(data.get("status") or data.get("run", {}).get("status") or "unknown")
        reason = str(data.get("reason") or data.get("next_step") or "")
        suffix = f" ({reason})" if reason else ""
        click.echo(f"Hosted {label}: {status}{suffix}")


@geosition.group()
def worker() -> None:
    """Run scheduled benchmark and telemetry jobs."""


@worker.command(name="start")
@click.option("--once", is_flag=True, help="Run due jobs once and exit.")
@click.option("--interval", default=300, show_default=True, type=int, help="Seconds between worker polls.")
@click.option(
    "--answers-file",
    type=click.Path(path_type=Path),
    default=None,
    help="Canonical or legacy answers JSON for due benchmarks.",
)
@click.option("--benchmark-db", type=click.Path(path_type=Path), default=None, help="Benchmark database path.")
@click.option("--platform-url", default="", help="Hosted GEOSITION platform URL, e.g. https://geositionai.com.")
@click.option("--worker-token", default="", help="Hosted worker token. Defaults to GEOSITION_WORKER_TOKEN.")
@click.option("--domain", default="", help="Optional verified domain filter for hosted worker jobs.")
@click.option("--no-audit", is_flag=True, help="Skip site audit during scheduled benchmark runs.")
@click.option(
    "--allow-shared-answers",
    is_flag=True,
    help="Allow one answers file to be reused for multiple due domains. Intended for demos only.",
)
def worker_start(
    once: bool,
    interval: int,
    answers_file: Optional[Path],
    benchmark_db: Optional[Path],
    platform_url: str,
    worker_token: str,
    domain: str,
    no_audit: bool,
    allow_shared_answers: bool,
) -> None:
    """Run due scheduled benchmarks in the foreground."""
    from geo_optimizer.cli.benchmark_cmd import _load_answers_file
    from geo_optimizer.cli.benchmark_formatter import build_benchmark_decision_plan
    from geo_optimizer.core.benchmark.runner import run_domain_benchmark
    from geo_optimizer.core.benchmark.schedule import due_schedules, mark_schedule_run
    from geo_optimizer.core.benchmark.store import BenchmarkStore
    from geo_optimizer.core.monitor import normalize_monitor_domain

    env_answers = os.environ.get("GEOSITION_WORKER_ANSWERS_FILE", "").strip()
    answers_path = answers_file or (Path(env_answers).expanduser() if env_answers else None)
    store = BenchmarkStore(benchmark_db) if benchmark_db else BenchmarkStore()
    hosted_platform_url = platform_url.strip() or os.environ.get("GEOSITION_PLATFORM_URL", "").strip()
    hosted_worker_token = worker_token.strip() or os.environ.get("GEOSITION_WORKER_TOKEN", "").strip()
    hosted_domain = domain.strip() or os.environ.get("GEOSITION_WORKER_DOMAIN", "").strip()

    click.echo("GEOSITION worker started.")
    click.echo("DNS verification permits the workspace; answers/log integrations provide telemetry evidence.")

    while True:
        if hosted_platform_url and hosted_worker_token:
            _run_hosted_platform_worker_once(
                platform_url=hosted_platform_url,
                worker_token=hosted_worker_token,
                domain=hosted_domain,
            )

        rows = due_schedules(store=store)
        if not rows:
            click.echo("No due benchmark schedules.")
        elif answers_path is None:
            click.echo(
                "Due benchmark schedules found, but no answers file is configured. "
                "Use --answers-file or GEOSITION_WORKER_ANSWERS_FILE."
            )
            for row in rows:
                click.echo(f"  - {row.domain} ({row.frequency})")
        elif len(rows) > 1 and not allow_shared_answers:
            click.echo(
                "Multiple due benchmark schedules found. Refusing to reuse one answers file across domains because "
                "that can mix telemetry evidence. Run domain-specific collection jobs or pass --allow-shared-answers "
                "for a demo-only run."
            )
            for row in rows:
                click.echo(f"  - {row.domain} ({row.frequency})")
        else:
            answers = _load_answers_file(answers_path)
            for row in rows:
                click.echo(f"Running scheduled benchmark: {row.domain} ({row.frequency})")
                result = run_domain_benchmark(
                    row.domain,
                    competitors=row.competitor_domains,
                    answers=answers,
                    schedule=row.frequency,
                    audit_url=None if no_audit else normalize_monitor_domain(row.domain),
                    store=store,
                    use_cache=True,
                )
                mark_schedule_run(row.domain, store=store, frequency=row.frequency)
                plan = build_benchmark_decision_plan(result)
                click.echo(
                    f"  score={result.benchmark_score}/100 ({result.band}) "
                    f"status={plan['status']} next={plan['priority']}"
                )

        if once:
            return
        time.sleep(max(5, interval))


if __name__ == "__main__":
    geosition()
