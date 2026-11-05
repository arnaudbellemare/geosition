from __future__ import annotations

from click.testing import CliRunner

from geo_optimizer.cli.github_cmd import github_cmd
from geo_optimizer.core.github_repo_audit import audit_github_repo


def test_github_repo_audit_detects_missing_files(tmp_path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Demo\n\nA short README for testing.", encoding="utf-8")
    (repo / "LICENSE").write_text("MIT", encoding="utf-8")

    result = audit_github_repo(str(repo))

    assert result.score > 0
    assert "CONTRIBUTING.md" in result.missing_files
    assert result.readme_word_count > 0
    assert result.recommendations


def test_github_cmd_writes_reports(tmp_path) -> None:
    repo = tmp_path / "repo2"
    repo.mkdir()
    (repo / "README.md").write_text("# Demo\n\n" + ("content " * 250), encoding="utf-8")
    (repo / "LICENSE").write_text("MIT", encoding="utf-8")
    (repo / "CONTRIBUTING.md").write_text("how to contribute", encoding="utf-8")
    (repo / "SECURITY.md").write_text("security policy", encoding="utf-8")

    runner = CliRunner()
    cmd = runner.invoke(github_cmd, ["--repo-path", str(repo), "--write-reports"])
    assert cmd.exit_code == 0
    assert (repo / "GITHUB-SEO-REPORT.md").exists()
    assert (repo / "GITHUB-ACTION-PLAN.md").exists()


def test_github_cmd_requires_exactly_one_source(tmp_path) -> None:
    repo = tmp_path / "repo3"
    repo.mkdir()
    runner = CliRunner()
    both = runner.invoke(github_cmd, ["--repo-path", str(repo), "--repo-url", "https://example.com/repo.git"])
    none = runner.invoke(github_cmd, [])
    assert both.exit_code != 0
    assert none.exit_code != 0
