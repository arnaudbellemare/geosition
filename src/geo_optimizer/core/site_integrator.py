"""
Framework-aware integration layer to apply generated fixes into repositories.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from geo_optimizer.models.results import FixItem


@dataclass
class ApplyOutcome:
    stack: str = "generic"
    applied_files: list[str] = field(default_factory=list)
    manual_steps: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def detect_stack(repo_path: Path) -> str:
    """Detect common web stack heuristically."""
    if (repo_path / "next.config.js").exists() or (repo_path / "next.config.mjs").exists():
        return "nextjs"
    if (repo_path / "astro.config.mjs").exists() or (repo_path / "astro.config.ts").exists():
        return "astro"
    if (repo_path / "wp-content").exists():
        return "wordpress"
    if (repo_path / "package.json").exists():
        return "node-static"
    return "generic"


def _public_root_for_stack(repo_path: Path, stack: str) -> Path:
    if stack in {"nextjs", "astro"} and (repo_path / "public").exists():
        return repo_path / "public"
    if (repo_path / "public").exists():
        return repo_path / "public"
    return repo_path


def resolve_fix_target(base_dir: Path, file_name: str) -> Path:
    """Resolve a generated fix path and ensure it stays under the target directory."""
    relative = Path(file_name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"Unsafe fix file path: {file_name}")
    target = (base_dir / relative).resolve()
    base = base_dir.resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Unsafe fix file path: {file_name}") from exc
    return target


def apply_fix_plan_to_repo(repo_path: Path, fixes: list[FixItem]) -> ApplyOutcome:
    """Apply file-based fixes with stack-aware routing and manual guidance."""
    outcome = ApplyOutcome()
    outcome.stack = detect_stack(repo_path)
    public_root = _public_root_for_stack(repo_path, outcome.stack)
    manual_notes: list[str] = []

    for item in fixes:
        # Snippet items need human-aware placement unless they are clearly file-based.
        if item.action == "snippet" and not item.file_name.startswith("vertical/"):
            manual_notes.append(f"{item.file_name}: {item.description}")
            outcome.skipped.append(item.file_name)
            continue

        try:
            target = resolve_fix_target(public_root, item.file_name)
        except ValueError as exc:
            outcome.skipped.append(str(exc))
            continue
        target.parent.mkdir(parents=True, exist_ok=True)

        if item.action == "append" and target.exists():
            target.write_text(target.read_text(encoding="utf-8") + "\n" + item.content, encoding="utf-8")
        else:
            target.write_text(item.content, encoding="utf-8")
        outcome.applied_files.append(str(target))

    if manual_notes:
        manual_path = repo_path / "geo-manual-steps.md"
        manual_content = "# GEO Manual Steps\n\nThe following snippets need manual placement:\n\n"
        manual_content += "\n".join(f"- {note}" for note in manual_notes)
        manual_path.write_text(manual_content, encoding="utf-8")
        outcome.manual_steps = manual_notes
        outcome.applied_files.append(str(manual_path))

    return outcome
