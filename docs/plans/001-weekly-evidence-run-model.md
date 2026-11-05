# Plan 001: Add A Unified Weekly Evidence Run Model

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report. When done, update the status row for this plan in `docs/plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat c81730a..HEAD -- src/geo_optimizer/saas/models.py src/geo_optimizer/saas/store.py src/geo_optimizer/saas/supabase_store.py src/geo_optimizer/saas/service.py tests/test_platform_saas.py`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: direction
- **Planned at**: commit `c81730a`, 2026-06-12

## Why This Matters

GEOSITION already records audits, benchmarks, SERP checks, and Index events, but a company cannot yet point at one durable weekly object and say, "this is the evidence for this week." A unified weekly evidence run gives the CLI, worker, platform dashboard, and report exporter a single contract for trend charts and client-ready proof. It also prevents new report code from stitching together unrelated latest rows with weak timestamp alignment.

## Current State

- `src/geo_optimizer/saas/models.py` defines `PlatformRun` and `IndexTelemetrySummary`, but no company weekly report/run dataclass. `PlatformRun.kind` is currently documented as `audit | benchmark | collection | export` at line 80.
- `src/geo_optimizer/saas/store.py` has `platform_runs` at lines 154-169 and `agent_usage_events` at lines 171-191. These store job status and Index evidence, but not one cross-metric report record.
- `src/geo_optimizer/saas/store.py` has `create_run`, `complete_run`, and `list_runs` at lines 554-668, which are good patterns for adding a parallel weekly report persistence API.
- `src/geo_optimizer/saas/supabase_store.py` mirrors the SQLite store API. Any new persistence method must be added to both backends.
- `src/geo_optimizer/saas/service.py` imports core audit, SERP, benchmark, and monitor helpers at lines 16-23 and already has `run_site_audit`, `run_benchmark`, `run_serp_check`, and `index_summary`.

## Commands You Will Need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Tests | `pytest tests/test_platform_saas.py -q` | exits 0 |
| Focused import check | `python3 -m geo_optimizer.cli.geosition_cmd --help` | exits 0 and lists commands |
| Lint | `ruff check src/geo_optimizer/saas tests/test_platform_saas.py` | exits 0 |

## Scope

**In scope**:
- `src/geo_optimizer/saas/models.py`
- `src/geo_optimizer/saas/store.py`
- `src/geo_optimizer/saas/supabase_store.py`
- `src/geo_optimizer/saas/service.py`
- `tests/test_platform_saas.py`
- `supabase/migrations/*.sql` if the current migrations directory exists and already contains platform schema

**Out of scope**:
- New UI rendering.
- Running external Lighthouse/PageSpeed/SERP providers.
- Changing auth, password reset, sessions, or domain verification behavior.
- Moving existing benchmark/audit storage tables.

## Steps

### Step 1: Add Weekly Evidence Dataclasses

Add dataclasses in `src/geo_optimizer/saas/models.py`:

- `WeeklyEvidenceMetric`: key, label, value, previous_value, delta, unit, status, evidence_ref.
- `WeeklyEvidenceRun`: report_id, org_id, domain, period_start, period_end, status, generated_at, score, band, metrics, artifact_json_uri, artifact_html_uri, summary, action_plan.

Keep Python 3.9 compatibility and include `from __future__ import annotations`.

**Verify**: `python3 -m geo_optimizer.cli.geosition_cmd --help` exits 0.

### Step 2: Add SQLite Persistence

In `src/geo_optimizer/saas/store.py`, create a table such as `weekly_evidence_runs` with:

- id, org_id, domain, period_start, period_end, status, score, band
- metrics_json, action_plan_json, artifact_json_uri, artifact_html_uri
- summary, generated_at, created_at

Add methods:

- `create_weekly_evidence_run(...) -> WeeklyEvidenceRun`
- `complete_weekly_evidence_run(...) -> WeeklyEvidenceRun | None`
- `list_weekly_evidence_runs(org_id, domain="", limit=12) -> list[WeeklyEvidenceRun]`
- `get_latest_weekly_evidence_run(org_id, domain="") -> WeeklyEvidenceRun | None`

Follow the existing `create_run`/`complete_run` style and normalize domains with `_normalize_domain`.

**Verify**: `pytest tests/test_platform_saas.py -q` still passes or fails only because tests must be updated in the next step.

### Step 3: Mirror Supabase Persistence

In `src/geo_optimizer/saas/supabase_store.py`, add the same public methods. Add table constant `_TABLE_WEEKLY_EVIDENCE = "geo_weekly_evidence_runs"`. Use `_request` like the existing `_TABLE_RUNS` and `_TABLE_AGENT_USAGE` code.

If migrations exist, add a new migration that creates `geo_weekly_evidence_runs` with matching columns. Do not include secrets or environment values in migrations.

**Verify**: `python3 -m geo_optimizer.cli.geosition_cmd --help` exits 0.

### Step 4: Expose Service Read Methods

In `src/geo_optimizer/saas/service.py`, add:

- `list_weekly_reports(token, domain="") -> dict`
- `latest_weekly_report(token, domain="") -> dict`

Require a valid session and verified domain when a domain is supplied. Use `asdict` for output, matching existing dashboard/API patterns.

**Verify**: `pytest tests/test_platform_saas.py -q` exits 0 after tests are added.

### Step 5: Add Tests

Extend `tests/test_platform_saas.py` with coverage for:

- creating and listing a weekly evidence run in SQLite store
- service listing rejects unverified domain
- service listing succeeds for a verified domain
- Supabase method shape if existing tests mock Supabase store methods

Use existing platform SaaS tests as the pattern; do not use real network.

**Verify**: `pytest tests/test_platform_saas.py -q` exits 0.

## Done Criteria

- [ ] SQLite and Supabase store expose the same weekly evidence run API.
- [ ] A weekly evidence run can persist metric JSON and artifact URIs.
- [ ] Service can list latest weekly reports for a verified domain.
- [ ] `pytest tests/test_platform_saas.py -q` passes.
- [ ] `ruff check src/geo_optimizer/saas tests/test_platform_saas.py` passes.

## STOP Conditions

- The live store APIs have drifted so the new SQLite and Supabase methods cannot share one service contract.
- Adding this model requires changing auth/session behavior.
- Existing platform tests depend on exact table schemas in a way that makes migration behavior ambiguous.

## Maintenance Notes

This model becomes the stable contract for CLI report export, scheduled worker runs, and dashboard report history. Reviewers should check that future metrics are added as metric payloads first, not as one-off dashboard-only fields.
