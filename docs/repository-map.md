# Repository map

GEOSITION contains a Python toolkit, a web platform, and supporting documentation. Start with the directory that matches your task:

| Path | Purpose |
| --- | --- |
| `src/geo_optimizer/cli/` | Commands and output formatting |
| `src/geo_optimizer/core/` | Audit, scoring, fix generation, and benchmark logic |
| `src/geo_optimizer/models/` | Shared results and configuration |
| `src/geo_optimizer/utils/` | URL validation, HTTP, and parsing utilities |
| `src/geo_optimizer/web/` | FastAPI app, routes, and platform templates |
| `src/geo_optimizer/saas/` | Workspace, storage, and platform services |
| `src/geo_optimizer/mcp/` | MCP server |
| `tests/` | Automated tests |
| `docs/` and `site/` | Documentation, research references, plans, and the published documentation site |
| `docs/ai-context-files/` | Reusable instructions for AI tools |
| `docs/references/` | Research, crawler, and schema reference material |
| `docs/plans/` | Implementation plans and their status |
| `docs/marketing/` | Article drafts and publication notes |
| `examples/` | Sample configuration, benchmark data, and plugin |
| `apps/` | Additional applications, including the visibility tracker |
| `seo/` | Repository SEO program and illustrative keyword estimates |
| `scripts/` | Development and verification scripts |
| `supabase/migrations/` | Production database migrations |
| `assets/` | Repository branding |
| `deploy/` | Additional deployment files, including the web Dockerfile |

The root also contains configuration and entry points used by packaging, deployment, CI, and external integrations. Files such as `action.yml`, `main.py`, and `install.sh` are kept at their existing paths for compatibility. `SCORING_RUBRIC.md` is a compatibility pointer; the current rubric is in [`docs/scoring-rubric.md`](scoring-rubric.md).

For architectural boundaries and security-sensitive code, read [`AGENTS.md`](../AGENTS.md). For development setup and submitting changes, see [`CONTRIBUTING.md`](../CONTRIBUTING.md).
