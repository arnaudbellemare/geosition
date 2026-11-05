"""Breve riferimento al programma SEO documentale nel repository (cartella `seo/`)."""

from __future__ import annotations

# Usato da CLI full/orchestrate per collegare l’analisi runtime agli artefatti versionati.
REPO_SEO_PROGRAM_FOOTER = (
    "Repository SEO program: backlog, validation URLs, GSC handbook → seo/README.md  |  verify: npm run seo:verify"
)

MARKDOWN_SEO_SECTION = """## Repository SEO program

Cross-reference `seo/audit-issues.json`, `seo/representative-urls.json`, decision cards, and backlog with this audit.
Validate artifact shape in CI or locally: `npm run seo:verify`.
"""
