"""Built-in SEO/GEO playbook library inspired by external skill packs."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Playbook:
    """Single reusable playbook template."""

    name: str
    category: str
    description: str
    template: str


_PLAYBOOKS = {
    "technical-seo-audit": Playbook(
        name="technical-seo-audit",
        category="audit",
        description="Crawlability, indexability, performance, schema, and AI-discovery checks.",
        template=(
            "Goal: run full technical audit for {target}.\n"
            "Steps:\n"
            "1. Run GEO audit and capture score/breakdown.\n"
            "2. Run links/orphan analysis from sitemap.\n"
            "3. Validate schema, robots, llms, and noindex/nofollow conflicts.\n"
            "4. Return P1/P2/P3 action plan with owner and ETA."
        ),
    ),
    "geo-content-optimization": Playbook(
        name="geo-content-optimization",
        category="content",
        description="Keyword density + E-E-A-T + entity extraction workflow.",
        template=(
            "Optimize content for {target_keywords} on {target}.\n"
            "1. Measure top terms and target keyword density.\n"
            "2. Flag stuffing/under-coverage ranges.\n"
            "3. Improve E-E-A-T and entity disambiguation cues.\n"
            "4. Add internal anchors and source citations."
        ),
    ),
    "serp-gap-analysis": Playbook(
        name="serp-gap-analysis",
        category="research",
        description="SERP competitor gaps using GEO + marketing signals.",
        template=(
            "Run SERP gap analysis for {target}.\n"
            "1. Compare top ranking pages and extract missing topics.\n"
            "2. Measure schema/FAQ/video/location coverage deltas.\n"
            "3. Produce page-level content briefs for top 5 opportunities."
        ),
    ),
    "github-repo-seo": Playbook(
        name="github-repo-seo",
        category="repo",
        description="Repository discoverability/trust workflow with report artifacts.",
        template=(
            "Audit repository {target_repo}.\n"
            "1. Check trust docs (README, SECURITY, CONTRIBUTING, LICENSE).\n"
            "2. Score README structure and command examples.\n"
            "3. Generate GITHUB-SEO-REPORT.md + GITHUB-ACTION-PLAN.md."
        ),
    ),
    "internal-link-sculpting": Playbook(
        name="internal-link-sculpting",
        category="architecture",
        description="Sitemap graph review to remove orphan pages and weak clusters.",
        template=(
            "For sitemap {sitemap}:\n"
            "1. Build in-degree/out-degree graph.\n"
            "2. Identify orphan and weakly linked pages.\n"
            "3. Propose hub-to-spoke and contextual link additions."
        ),
    ),
    "ai-discovery-hardening": Playbook(
        name="ai-discovery-hardening",
        category="geo",
        description="Hardening checklist for AI crawler discoverability.",
        template=(
            "Validate AI discovery surfaces for {target}.\n"
            "Checklist: robots bot-allow rules, llms.txt depth, ai/*.json presence,\n"
            "heading anchors, and anti-cloaking/no hidden text patterns."
        ),
    ),
}


def list_playbooks() -> list[Playbook]:
    """Return all playbooks sorted by name."""
    return [pb for _, pb in sorted(_PLAYBOOKS.items(), key=lambda item: item[0])]


def get_playbook(name: str) -> Playbook | None:
    """Return a playbook by name (exact key)."""
    return _PLAYBOOKS.get(name.strip().lower())
