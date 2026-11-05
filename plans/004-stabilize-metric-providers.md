# Plan 004: Stabilize SERP, Lighthouse, And Crawler Evidence Providers

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report. When done, update the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat c81730a..HEAD -- src/geo_optimizer/core/audit_serp.py src/geo_optimizer/core/seo_intelligence.py src/geo_optimizer/core/log_analyzer.py src/geo_optimizer/saas/service.py src/geo_optimizer/storage/artifacts.py tests/test_seo_intelligence.py tests/test_platform_saas.py`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: `plans/001-weekly-evidence-run-model.md`
- **Category**: direction
- **Planned at**: commit `c81730a`, 2026-06-12

## Why This Matters

Weekly company reports need metrics that are repeatable and explainable. Current Lighthouse support is already provider-shaped, crawler logs are local and deterministic, but SERP checking still uses live public search scraping and direct parsing. That is acceptable as a fallback, not as the primary proof engine for recurring business reports. This plan adds provider contracts and artifact capture so weekly deltas can be trusted.

## Current State

- `src/geo_optimizer/core/audit_serp.py` describes public Google/Bing/DDG HTML fetching at lines 1-10 and uses `requests.get(... allow_redirects=True)` for search engine pages at lines 248-251.
- `src/geo_optimizer/core/seo_intelligence.py` has `run_lighthouse_audit(url, provider="pagespeed", api_key=None, report_path=None)` at lines 647-660. This is already close to the desired provider contract.
- `src/geo_optimizer/core/log_analyzer.py` parses Apache/Nginx combined logs and JSON lines without network at lines 33-81.
- `src/geo_optimizer/storage/artifacts.py` provides local/S3 artifact storage for raw answers, reports, and exports.
- `PlatformService.run_serp_check` records SERP results as Index events at `src/geo_optimizer/saas/service.py:843-958`.

## Commands You Will Need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| SEO tests | `pytest tests/test_seo_intelligence.py -q` | exits 0 |
| Platform tests | `pytest tests/test_platform_saas.py -q` | exits 0 |
| Focused test suite | `pytest tests/test_seo_intelligence.py tests/test_platform_saas.py -q` | exits 0 |
| Lint | `ruff check src/geo_optimizer/core/audit_serp.py src/geo_optimizer/core/seo_intelligence.py src/geo_optimizer/core/log_analyzer.py src/geo_optimizer/saas/service.py tests/test_seo_intelligence.py tests/test_platform_saas.py` | exits 0 |

## Scope

**In scope**:
- `src/geo_optimizer/core/audit_serp.py`
- `src/geo_optimizer/core/seo_intelligence.py`
- `src/geo_optimizer/core/log_analyzer.py`
- `src/geo_optimizer/saas/service.py`
- Tests for mocked provider behavior

**Out of scope**:
- Buying or hardcoding third-party API keys.
- Real external network tests.
- Removing the existing no-key SERP fallback before a provider replacement is working.
- Changing score weights in `models/config.py`.

## Steps

### Step 1: Add SERP Provider Protocol

Introduce a small provider protocol in `src/geo_optimizer/core/audit_serp.py` or a new `src/geo_optimizer/core/serp_provider.py`:

- input: keyword, locale/country, result limit
- output: normalized organic results with rank, url, title, description, provider, raw_artifact_ref optional

Implement providers:

- `LocalHtmlSerpProvider`: wraps current DDG/Bing/Google fallback behavior.
- `StaticSerpProvider`: test-only/in-memory provider for deterministic tests.
- Optional environment-driven provider placeholder for future APIs, returning unavailable when not configured.

Keep user-controlled result URLs flowing through existing safe fetch logic before competitor analysis.

**Verify**: Existing SERP tests and `pytest tests/test_seo_intelligence.py -q` pass.

### Step 2: Store Raw Evidence Artifacts

When a provider returns raw HTML/JSON, store a sanitized evidence artifact using `get_optional_artifact_store()` or an injected artifact store. Store only bounded payloads and only safe relative object keys. Record the returned URI in the normalized result.

Do not store secrets, request headers containing API keys, or full provider credentials.

**Verify**: Add unit tests that artifact store is called with safe keys and bounded content.

### Step 3: Normalize Lighthouse Artifacts

Extend `run_lighthouse_audit` or the weekly report integration so Lighthouse raw JSON report paths/URIs are captured as evidence references. Keep `pagespeed` and `cli` behavior intact:

- `pagespeed`: parse provider response and optionally store raw JSON when artifact store is configured.
- `cli`: keep report_path behavior and expose it as evidence.
- unavailable providers: return checked false with warnings.

**Verify**: `pytest tests/test_seo_intelligence.py -q` exits 0.

### Step 4: Normalize Crawler Log Evidence

Extend log analysis output or service import so weekly reports can include:

- total AI requests
- bot coverage count
- citation bot hits
- top crawled pages
- period start/end
- artifact reference to the imported log summary, not the raw sensitive log by default

Keep `geo logs --file ... --format json` backward compatible.

**Verify**: Add or update log analyzer tests if they exist; otherwise add focused tests for JSON and combined log fixtures.

### Step 5: Use Providers In Platform SERP Check

Update `PlatformService.run_serp_check` to call the new provider-backed SERP path and record the provider/artifact in `evidence`. Preserve the API response fields: domain, keyword, organic_rank, top_list_position_pass, search_engine, issues, event, run, summary.

**Verify**: `pytest tests/test_platform_saas.py -q` exits 0.

## Done Criteria

- [ ] SERP checks can run against a deterministic provider in tests.
- [ ] Local public-search fallback still exists but is behind the provider contract.
- [ ] Lighthouse and SERP evidence can include artifact references.
- [ ] Crawler log summaries are weekly-report-ready without storing raw sensitive logs by default.
- [ ] Tests and Ruff pass.

## STOP Conditions

- The provider abstraction would require removing existing SERP functionality before replacement tests pass.
- Any implementation needs live provider credentials in normal tests.
- Artifact storage would risk writing outside the configured artifact root.

## Maintenance Notes

For weekly business reporting, "metric provenance" matters as much as the value. Every metric should have a provider, timestamp, and evidence reference so users can explain why the number moved.
