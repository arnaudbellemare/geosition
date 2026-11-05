# SEO program folder (repository)

Versioned artifacts that tie **live GEO analysis** (`geo full`, `geo orchestrate`) to **program governance**: prioritized issues, validation URLs, GSC discipline, and PR hygiene.

## Index

| Artifact | Path |
|----------|------|
| 13-phase map + deploy log + stale-tactics rejection | `../seo-changelog.md` |
| Prioritized issues + evidence + rollback + GEO scaled-content risk | `audit-issues.json` |
| Minimal validation URL set (FR/EN) | `representative-urls.json` |
| Decision cards (confidence + recheck 2026-08-01) | `decision-cards.md` |
| GSC operator handbook (segments, annotations, exports — no fake metrics) | `gsc-dashboard-handbook.md` |
| Accretive backlog (pruning first) | `BACKLOG.md` |
| PR checklist | `PR_TEMPLATE.md` |

## Policy

- Replace `example.com` URLs in `representative-urls.json` with production hosts before relying on them for deploy checks.
- Run **`npm run seo:verify`** in CI or before merging SEO-facing PRs.

## Relation to GEO Optimizer CLI

After a full audit, the CLI reminds operators to align numeric findings with `seo/audit-issues.json` and to keep artifacts validated. Automation checks structure only — not ranking outcomes.
