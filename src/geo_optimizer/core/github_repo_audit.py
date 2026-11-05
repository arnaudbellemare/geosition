"""Audit SEO/GEO readiness for a local GitHub repository."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class GithubRepoAuditResult:
    """Risultato sintetico dell'audit SEO per repository GitHub."""

    repo_path: str
    score: int = 0
    grade: str = "foundation"
    found_files: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    readme_word_count: int = 0
    readme_heading_count: int = 0
    has_ai_files: bool = False
    has_web_seo_files: bool = False
    recommendations: list[str] = field(default_factory=list)


_REQUIRED_FILES = [
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "SECURITY.md",
]

_OPTIONAL_TRUST_FILES = [
    "CODE_OF_CONDUCT.md",
    "CHANGELOG.md",
    "CITATION.cff",
]

_AI_FILES = [
    "llms.txt",
    "llms-full.txt",
    ".well-known/ai.txt",
    "ai/summary.json",
    "ai/faq.json",
    "ai/service.json",
]

_WEB_SEO_FILES = [
    "public/robots.txt",
    "public/sitemap.xml",
    "robots.txt",
    "sitemap.xml",
]


def audit_github_repo(repo_path: str) -> GithubRepoAuditResult:
    """Esegue un audit SEO/GEO orientato a repository e documentazione."""
    root = Path(repo_path).resolve()
    result = GithubRepoAuditResult(repo_path=str(root))
    if not root.exists() or not root.is_dir():
        result.recommendations.append("Repository path is not a readable directory.")
        return result

    score = 0

    # Base files
    for rel in _REQUIRED_FILES:
        candidates = (rel, f".github/{rel}", f"docs/{rel}") if rel in {"CONTRIBUTING.md", "SECURITY.md"} else (rel,)
        found = next((candidate for candidate in candidates if (root / candidate).is_file()), None)
        if found:
            score += 10
            result.found_files.append(found)
        else:
            result.missing_files.append(rel)

    for rel in _OPTIONAL_TRUST_FILES:
        candidates = (rel, f"docs/{rel}") if rel == "CHANGELOG.md" else (rel,)
        found = next((candidate for candidate in candidates if (root / candidate).is_file()), None)
        if found:
            score += 5
            result.found_files.append(found)
        else:
            result.missing_files.append(rel)

    # README quality
    readme = _resolve_readme(root)
    if readme is not None:
        content = _safe_read_text(readme)
        words = _word_count(content)
        headings = len(re.findall(r"(?m)^#{1,3}\s+", content))
        result.readme_word_count = words
        result.readme_heading_count = headings

        if words >= 400:
            score += 12
        elif words >= 180:
            score += 8
        elif words > 0:
            score += 4

        if headings >= 6:
            score += 8
        elif headings >= 3:
            score += 5
        elif headings > 0:
            score += 2

    # AI/GEO files
    ai_found = [rel for rel in _AI_FILES if (root / rel).exists()]
    if ai_found:
        result.has_ai_files = True
        result.found_files.extend(ai_found)
        score += min(20, len(ai_found) * 5)
    else:
        result.missing_files.extend(_AI_FILES)

    # Web SEO files
    web_found = [rel for rel in _WEB_SEO_FILES if (root / rel).exists()]
    if web_found:
        result.has_web_seo_files = True
        result.found_files.extend(web_found)
        score += min(15, len(web_found) * 7)
    else:
        result.missing_files.extend(_WEB_SEO_FILES)

    result.score = min(score, 100)
    result.grade = _grade(result.score)
    result.recommendations = _recommend(result)
    return result


def to_markdown_report(result: GithubRepoAuditResult) -> tuple[str, str]:
    """Genera report e action plan in Markdown stile GitHub workflow."""
    report_lines = [
        "# GITHUB-SEO-REPORT",
        "",
        f"- Repository: `{result.repo_path}`",
        f"- Score: **{result.score}/100** ({result.grade})",
        f"- README words: {result.readme_word_count}",
        f"- README headings: {result.readme_heading_count}",
        "",
        "## Found Files",
    ]
    if result.found_files:
        report_lines.extend([f"- `{item}`" for item in sorted(set(result.found_files))])
    else:
        report_lines.append("- none")

    report_lines.extend(["", "## Missing Files"])
    if result.missing_files:
        report_lines.extend([f"- `{item}`" for item in sorted(set(result.missing_files))])
    else:
        report_lines.append("- none")

    report_lines.extend(["", "## Recommendations"])
    report_lines.extend([f"- {r}" for r in result.recommendations] or ["- none"])

    action_lines = [
        "# GITHUB-ACTION-PLAN",
        "",
        "## Priority Actions",
    ]
    action_lines.extend([f"1. {r}" for r in result.recommendations[:8]] or ["1. Keep monitoring monthly."])
    return "\n".join(report_lines).strip() + "\n", "\n".join(action_lines).strip() + "\n"


def _resolve_readme(root: Path) -> Path | None:
    for candidate in ("README.md", "README.MD", "readme.md"):
        p = root / candidate
        if p.exists() and p.is_file():
            return p
    return None


def _safe_read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="latin-1", errors="replace")
    except OSError:
        return ""


def _word_count(text: str) -> int:
    return len(re.findall(r"\b[\wÀ-ÖØ-öø-ÿ-]{2,}\b", text or ""))


def _grade(score: int) -> str:
    if score >= 86:
        return "excellent"
    if score >= 68:
        return "good"
    if score >= 36:
        return "foundation"
    return "critical"


def _recommend(result: GithubRepoAuditResult) -> list[str]:
    recs: list[str] = []
    missing = set(result.missing_files)

    for rel in _REQUIRED_FILES:
        if rel in missing:
            recs.append(f"Add `{rel}` to strengthen repository trust and discoverability.")

    if result.readme_word_count < 180:
        recs.append("Expand README with clear use cases, commands, and examples.")
    if result.readme_heading_count < 3:
        recs.append("Structure README with H2/H3 sections for easier AI extraction.")

    if not result.has_ai_files:
        recs.append("Add AI discovery files (llms.txt and .well-known/ai.txt).")
    if not result.has_web_seo_files:
        recs.append("Add robots.txt and sitemap.xml if the repo ships a public website.")

    if not recs:
        recs.append("Repository SEO baseline is strong. Keep docs freshness checks on each release.")
    return recs
