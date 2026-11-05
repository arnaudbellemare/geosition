"""Tests for applying generated fixes into local repositories."""

from __future__ import annotations

from geo_optimizer.core.site_integrator import apply_fix_plan_to_repo
from geo_optimizer.models.results import FixItem


def test_apply_fix_plan_skips_unsafe_generated_file_name(tmp_path):
    """Repository apply should never write a generated fix outside the repo."""
    repo = tmp_path / "repo"
    repo.mkdir()
    outside = tmp_path / "outside.txt"

    outcome = apply_fix_plan_to_repo(
        repo,
        [
            FixItem(
                category="robots",
                description="Unsafe generated path",
                content="User-agent: *\nAllow: /",
                file_name="../outside.txt",
                action="create",
            )
        ],
    )

    assert not outside.exists()
    assert not outcome.applied_files
    assert any("Unsafe fix file path" in item for item in outcome.skipped)
