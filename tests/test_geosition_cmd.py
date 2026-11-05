"""Tests for the branded geosition command center."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from geo_optimizer.cli.geosition_cmd import geosition


def test_geosition_demo_uses_fictional_workspace(tmp_path, monkeypatch):
    """The bundled demo runs locally without exposing a real customer's data."""
    monkeypatch.setenv("GEOSITION_HOME", str(tmp_path / "home"))

    result = CliRunner().invoke(geosition, ["demo", "--output-dir", str(tmp_path / "runs")])

    assert result.exit_code == 0, result.output
    demo_dir = tmp_path / "demo" / "example.com"
    workspace = json.loads((demo_dir / "workspace.json").read_text(encoding="utf-8"))
    answers = json.loads((demo_dir / "benchmark-answers.json").read_text(encoding="utf-8"))
    assert workspace["domain"] == "example.com"
    assert answers["target_domain"] == "example.com"
    assert (demo_dir / "benchmark-run.json").exists()
    assert (demo_dir / "ai-citation-report.html").exists()


def test_geosition_init_creates_local_config(tmp_path, monkeypatch):
    """`geosition init` prepares the local app home and next-step config."""
    monkeypatch.setenv("GEOSITION_HOME", str(tmp_path / "home"))
    runner = CliRunner()

    result = runner.invoke(geosition, ["init", "--port", "9090"])

    assert result.exit_code == 0
    config_path = tmp_path / "home" / "config.json"
    assert config_path.exists()
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    assert payload["platform"]["url"] == "http://127.0.0.1:9090/platform"
    assert "geosition start" in payload["next_commands"]
    assert "geosition worker start --once --answers-file answers.json" in payload["next_commands"]
    assert "geosition worker start --once --answers-file answers.json" in result.output
    assert (tmp_path / "home" / "runs").is_dir()
    assert (tmp_path / "home" / "telemetry").is_dir()


def test_geosition_worker_start_once_without_due_jobs(tmp_path, monkeypatch):
    """`geosition worker start --once` exits cleanly when no schedules are due."""
    monkeypatch.setenv("GEOSITION_HOME", str(tmp_path / "home"))
    db_path = tmp_path / "benchmark.db"
    runner = CliRunner()

    result = runner.invoke(geosition, ["worker", "start", "--once", "--benchmark-db", str(db_path)])

    assert result.exit_code == 0
    assert "GEOSITION worker started." in result.output
    assert "No due benchmark schedules." in result.output


def test_geosition_weekly_report_writes_json_and_html(tmp_path, monkeypatch):
    """Weekly report command writes portable JSON and HTML artifacts."""
    monkeypatch.setenv("GEOSITION_HOME", str(tmp_path / "home"))

    def fake_report(target, **kwargs):
        assert target == "https://example.com"
        assert kwargs["lighthouse_provider"] == "none"
        return {
            "schema_version": "weekly_evidence.v1",
            "domain": "example.com",
            "period_start": "2026-06-05T00:00:00+00:00",
            "period_end": "2026-06-12T00:00:00+00:00",
            "generated_at": "2026-06-12T00:00:00+00:00",
            "score": 82,
            "band": "good",
            "summary": "example.com is improving.",
            "metrics": [
                {
                    "key": "geo_audit_score",
                    "label": "GEO audit score",
                    "value": "82/100",
                    "status": "good",
                    "evidence_ref": "audit",
                }
            ],
            "sources": {"audit": {"checked": True}},
            "action_plan": {"actions": ["Keep improving."]},
        }

    monkeypatch.setattr("geo_optimizer.utils.validators.validate_public_url", lambda url: (True, None))
    monkeypatch.setattr("geo_optimizer.saas.weekly_evidence.build_weekly_evidence_report", fake_report)
    runner = CliRunner()
    result = runner.invoke(
        geosition,
        ["weekly-report", "https://example.com", "--no-lighthouse", "--output-dir", str(tmp_path / "runs")],
    )

    assert result.exit_code == 0
    json_files = list((tmp_path / "runs").glob("*weekly-evidence*.json"))
    html_files = list((tmp_path / "runs").glob("*weekly-evidence*.html"))
    assert len(json_files) == 1
    assert len(html_files) == 1
    assert json.loads(json_files[0].read_text(encoding="utf-8"))["score"] == 82
    assert "Weekly score: 82/100" in result.output


def test_geosition_weekly_report_rejects_unsafe_url(tmp_path, monkeypatch):
    """Weekly report command keeps the same SSRF guard as normal audit runs."""
    monkeypatch.setenv("GEOSITION_HOME", str(tmp_path / "home"))
    runner = CliRunner()

    result = runner.invoke(geosition, ["weekly-report", "http://127.0.0.1:8000"])

    assert result.exit_code != 0
    assert "Unsafe URL" in result.output


def test_install_scripts_point_to_current_package_and_one_shot_worker():
    """Install guidance should match the current PyPI package and first-run worker behavior."""
    root = Path(__file__).resolve().parents[1]
    install_sh = (root / "install.sh").read_text(encoding="utf-8")
    isolated_install_sh = (root / "scripts" / "install-geosition.sh").read_text(encoding="utf-8")
    pyproject = (root / "pyproject.toml").read_text(encoding="utf-8")

    assert 'app = "geo_optimizer.web.app:app"' not in pyproject
    assert "geo-optimizer-skill" not in install_sh
    assert "geo-optimizer-skill" not in isolated_install_sh
    assert "geosition[web]" in isolated_install_sh
    assert "geosition worker start --once --answers-file answers.json" in install_sh
    assert "geosition worker start --once --answers-file answers.json" in isolated_install_sh


def test_geo_mcp_without_optional_dependency_explains_extra(capsys):
    """A base install exposes geo-mcp, so missing optional deps need a helpful error."""
    import geo_optimizer.mcp.server as server

    if server._MCP_IMPORT_ERROR is None:
        return

    try:
        server.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("geo-mcp should exit when mcp SDK is missing")

    assert "pip install 'geosition[mcp]'" in capsys.readouterr().err
