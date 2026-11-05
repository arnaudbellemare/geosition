from __future__ import annotations

from click.testing import CliRunner

from geo_optimizer.cli.pipeline_cmd import pipeline_cmd
from geo_optimizer.cli.playbook_cmd import playbook_cmd


def test_playbook_list_text() -> None:
    runner = CliRunner()
    result = runner.invoke(playbook_cmd, ["--list"])
    assert result.exit_code == 0
    assert "PLAYBOOK LIBRARY" in result.output
    assert "technical-seo-audit" in result.output


def test_playbook_show_json() -> None:
    runner = CliRunner()
    result = runner.invoke(playbook_cmd, ["--name", "github-repo-seo", "--format", "json"])
    assert result.exit_code == 0
    assert '"name": "github-repo-seo"' in result.output


def test_pipeline_repo_mode(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Demo\n", encoding="utf-8")
    (repo / "LICENSE").write_text("MIT", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(pipeline_cmd, ["--mode", "repo", "--repo-path", str(repo)])
    assert result.exit_code == 0
    assert "REPO PIPELINE" in result.output

