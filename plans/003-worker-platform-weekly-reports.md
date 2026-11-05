# Plan 003: Connect Weekly Evidence Runs To Workers And Platform Reports

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report. When done, update the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat c81730a..HEAD -- src/geo_optimizer/cli/geosition_cmd.py src/geo_optimizer/web/platform_routes.py src/geo_optimizer/web/templates/platform/dashboard.html src/geo_optimizer/web/templates/platform/site.css src/geo_optimizer/saas/service.py tests/test_geosition_cmd.py tests/test_platform_saas.py`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: L
- **Risk**: MED
- **Depends on**: `plans/001-weekly-evidence-run-model.md`, `plans/002-geosition-weekly-report-command.md`
- **Category**: direction
- **Planned at**: commit `c81730a`, 2026-06-12

## Why This Matters

The dashboard already promises growth over time, hosted collection, Index evidence, audits, benchmarks, and reports. But recurring proof still depends on manual actions and separate commands. This plan makes weekly reporting operational: workers can run it, platform APIs can list it, and users can see/download report history after domain verification.

## Current State

- The dashboard has locked "Reports" navigation but no real report history section at `src/geo_optimizer/web/templates/platform/dashboard.html:27-29`.
- The dashboard has "Growth over time" and Index panels at lines 94-169, but these are not tied to a weekly evidence report record.
- `PlatformService.dashboard` returns domains, competitors, prompts, benchmarks, runs, and index summary at `src/geo_optimizer/saas/service.py:231-246`.
- API routes expose dashboard, runs, audit, visibility summary, collection, retrieval probe, SERP check, Index events, and benchmark at `src/geo_optimizer/web/platform_routes.py:678-880`.
- `geosition worker start` currently runs only due benchmark schedules at `src/geo_optimizer/cli/geosition_cmd.py:844-904`.

## Commands You Will Need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Worker test | `pytest tests/test_geosition_cmd.py -q` | exits 0 |
| Platform test | `pytest tests/test_platform_saas.py -q` | exits 0 |
| Template smoke | `python3 -m geo_optimizer.cli.geosition_cmd --help` | exits 0 |
| Lint | `ruff check src/geo_optimizer/cli/geosition_cmd.py src/geo_optimizer/web/platform_routes.py src/geo_optimizer/saas/service.py tests/test_geosition_cmd.py tests/test_platform_saas.py` | exits 0 |

## Scope

**In scope**:
- `src/geo_optimizer/cli/geosition_cmd.py`
- `src/geo_optimizer/saas/service.py`
- `src/geo_optimizer/web/platform_routes.py`
- `src/geo_optimizer/web/templates/platform/dashboard.html`
- `src/geo_optimizer/web/templates/platform/site.css`
- `tests/test_geosition_cmd.py`
- `tests/test_platform_saas.py`

**Out of scope**:
- Billing.
- Email report delivery.
- Replacing the existing Index page.
- Building charts with a heavy frontend framework.

## Steps

### Step 1: Add Platform API Endpoints

In `src/geo_optimizer/web/platform_routes.py`, add endpoints:

- `GET /api/v1/reports/weekly?domain=...`
- `GET /api/v1/reports/weekly/latest?domain=...`
- `POST /api/v1/reports/weekly/run`

The POST endpoint should require the expensive write token, require verified domain ownership, and call the service method from Plan 002. It should return the weekly report payload and artifact URIs.

**Verify**: `pytest tests/test_platform_saas.py -q` exits 0 after tests are updated.

### Step 2: Add Reports To Dashboard Data

Update `PlatformService.dashboard` and `PlatformDashboard` if needed so the server-rendered dashboard has recent weekly report rows available. Keep the existing Index summary behavior unchanged.

**Verify**: `python3 -m geo_optimizer.cli.geosition_cmd --help` exits 0.

### Step 3: Add Dashboard Report History UI

In `dashboard.html`, replace the locked Reports placeholder with a real reports section after "Growth over time" or near "Recent platform runs". Show:

- latest weekly score and band
- deltas for GEO, Lighthouse SEO, benchmark citation rate, SERP/rank, crawler access
- artifact links for HTML and JSON when available
- "Run weekly report" button

Keep the UI consistent with current dashboard patterns: `dash-panel`, `visibility-metrics`, simple rows, no nested cards.

**Verify**: Existing platform page tests pass. If no visual tests exist, add a test that renders/replaces report placeholders without raw template variables leaking.

### Step 4: Extend Worker

Enhance `geosition worker start` so it can run weekly reports as a separate job mode:

- Add `--reports` or `--job benchmark|weekly-report|all`, default preserving existing behavior unless product owners prefer `all`.
- Add `--domain` filter if not already available.
- When a benchmark schedule is due and answers are available, run benchmark as today and then create a weekly report.
- If answers are missing, still create a partial weekly report with audit/Lighthouse/crawler metrics and a clear benchmark-unavailable status.

Do not reuse one answers file across multiple domains unless `--allow-shared-answers` is set; preserve the existing safety behavior at lines 878-883.

**Verify**: `pytest tests/test_geosition_cmd.py -q` exits 0.

### Step 5: Add Tests

Cover:

- API list/latest weekly reports requires auth and verified domain.
- POST weekly report run rejects unverified domains.
- Worker `--once --job weekly-report` creates/report-calls one due report with mocked sources.
- Existing worker benchmark tests still pass.

**Verify**: `pytest tests/test_geosition_cmd.py tests/test_platform_saas.py -q` exits 0.

## Done Criteria

- [ ] Platform API can list, fetch latest, and run weekly reports.
- [ ] Dashboard shows report history and latest deltas.
- [ ] Worker can produce weekly reports without manual browser actions.
- [ ] Existing benchmark worker behavior remains compatible.
- [ ] Tests and Ruff pass.

## STOP Conditions

- Plan 002 has not landed.
- Dashboard changes require a frontend framework migration.
- Worker report generation would need real network calls in tests.

## Maintenance Notes

The platform dashboard should remain an operational surface, not a marketing page. Keep report cards dense and evidence-oriented: metric, delta, source, status, artifact.
