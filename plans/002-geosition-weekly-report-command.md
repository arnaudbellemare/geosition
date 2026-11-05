# Plan 002: Add `geosition weekly-report` Orchestration

> **Executor instructions**: Follow this plan step by step. Run every verification command and confirm the expected result before moving to the next step. If anything in the "STOP conditions" section occurs, stop and report. When done, update the status row for this plan in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat c81730a..HEAD -- src/geo_optimizer/cli/geosition_cmd.py src/geo_optimizer/saas/service.py src/geo_optimizer/cli/html_formatter.py tests/test_geosition_cmd.py tests/test_platform_saas.py`
> If any in-scope file changed since this plan was written, compare the "Current state" excerpts against the live code before proceeding; on a mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: `plans/001-weekly-evidence-run-model.md`
- **Category**: direction
- **Planned at**: commit `c81730a`, 2026-06-12

## Why This Matters

The `.sh` install story needs a command that an operator or AI agent can run after setup to produce a complete company report. Today `geosition run` saves only an audit artifact, while benchmark, Lighthouse, logs, and SERP are separate commands. `geosition weekly-report` should become the product-facing orchestration command that turns all available evidence into one JSON artifact and one HTML report.

## Current State

- `geosition run` validates a public URL, runs `run_full_audit`, and writes JSON plus HTML under `~/.geosition/runs` at `src/geo_optimizer/cli/geosition_cmd.py:633-661`.
- `geosition citation-report` currently accepts display values such as `--score` and `--citation-share`, then writes a static client report at lines 667-693. It is useful for demos but not enough for evidence-based weekly tracking.
- `geosition worker start` runs due benchmark schedules, but only prints benchmark outcome and does not produce weekly reports at lines 844-904.
- `geo seo lighthouse` is available through `run_lighthouse_audit`, wired at `src/geo_optimizer/cli/seo_cmd.py:200-240`.
- `geo logs` uses `analyze_log_file` to count AI crawler hits, wired at `src/geo_optimizer/cli/logs_cmd.py:13-35`.

## Commands You Will Need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| CLI help | `python3 -m geo_optimizer.cli.geosition_cmd --help` | exits 0 and lists `weekly-report` |
| Command help | `python3 -m geo_optimizer.cli.geosition_cmd weekly-report --help` | exits 0 |
| Tests | `pytest tests/test_geosition_cmd.py tests/test_platform_saas.py -q` | exits 0 |
| Lint | `ruff check src/geo_optimizer/cli/geosition_cmd.py src/geo_optimizer/saas/service.py tests/test_geosition_cmd.py tests/test_platform_saas.py` | exits 0 |

## Scope

**In scope**:
- `src/geo_optimizer/cli/geosition_cmd.py`
- `src/geo_optimizer/saas/service.py`
- `tests/test_geosition_cmd.py`
- `tests/test_platform_saas.py`
- A small formatter helper in `src/geo_optimizer/cli/geosition_cmd.py` or a new CLI formatter module if needed

**Out of scope**:
- New frontend dashboard UI.
- Real network tests.
- Replacing `geo track`, `geo benchmark`, `geo seo lighthouse`, or `geo logs`.
- Sending reports by email.

## Steps

### Step 1: Add Report Aggregation Service

In `src/geo_optimizer/saas/service.py`, add a method such as `run_weekly_evidence_report(...)`. It should accept:

- token optional for platform mode, or org/domain identifiers for local mode if service can support it cleanly
- domain
- answers_payload optional
- competitors optional
- keywords optional
- log_file optional
- lighthouse_provider defaulting to `pagespeed`
- output directory or artifact store options

For the first implementation, prefer a local CLI-friendly path if platform auth makes service use awkward. The method should still return a structured dict shaped like the `WeeklyEvidenceRun` model from Plan 001.

Use existing safe URL and domain helpers. For each optional metric, record a checked/unavailable status instead of failing the whole report.

**Verify**: `python3 -m geo_optimizer.cli.geosition_cmd --help` exits 0.

### Step 2: Compose Existing Evidence Sources

The report should call existing code rather than duplicating logic:

- GEO audit: `run_full_audit`
- history delta: `HistoryStore` or weekly evidence previous run
- benchmark: `run_domain_benchmark` only when answers are supplied
- Lighthouse: `run_lighthouse_audit`
- crawler log proof: `analyze_log_file` only when `--log-file` is supplied
- crawler access: use audit result fields and CDN check already included in `AuditResult`
- SERP: use the existing service `run_serp_check` path only in authenticated platform mode, or defer to Plan 004 provider work for local mode

Each metric should include key, label, current value, previous value if known, delta if known, status, and evidence reference.

**Verify**: Add or update tests with mocked helpers and run `pytest tests/test_geosition_cmd.py -q`.

### Step 3: Add The CLI Command

In `src/geo_optimizer/cli/geosition_cmd.py`, add:

```bash
geosition weekly-report DOMAIN_OR_URL
```

Recommended options:

- `--answers-file PATH`
- `--competitor DOMAIN`, multiple
- `--keyword TEXT`, multiple
- `--log-file PATH`
- `--lighthouse-provider pagespeed|cli|none`
- `--output-dir PATH`
- `--format html|json|both`, default `both`
- `--no-lighthouse`
- `--no-benchmark`

The command must write:

- `domain-weekly-report-<timestamp>.json`
- `domain-weekly-report-<timestamp>.html`

Print the artifact paths and the top 3 next actions.

**Verify**: `python3 -m geo_optimizer.cli.geosition_cmd weekly-report --help` exits 0.

### Step 4: Render An Agent-Ready Report

Add an HTML renderer for the weekly report. It must include:

- executive summary
- metric cards for GEO score, benchmark score, citation rate, Lighthouse SEO/performance, SERP rank, crawler access/log hits
- week-over-week deltas
- evidence table with source and artifact IDs/URIs
- "AI implementation plan" section with copy/paste prompt and embedded JSON script tag, matching the spirit of the existing audit HTML report

Keep the renderer self-contained and escaped. Do not put user-controlled values into HTML without escaping.

**Verify**: Unit test renders a known payload and asserts the expected sections exist.

### Step 5: Add Tests

In `tests/test_geosition_cmd.py`, mock all network-facing functions. Cover:

- command writes JSON and HTML
- missing answers file still produces a report with benchmark status `unavailable`
- log file option includes crawler metric
- Lighthouse unavailable does not fail the report
- unsafe private URL is rejected

**Verify**: `pytest tests/test_geosition_cmd.py tests/test_platform_saas.py -q` exits 0.

## Done Criteria

- [ ] `geosition weekly-report --help` exists.
- [ ] Running the command with mocked evidence writes JSON and HTML artifacts.
- [ ] Report includes GEO, benchmark, Lighthouse, crawler, and action-plan slots.
- [ ] Unavailable optional sources degrade gracefully.
- [ ] Tests and Ruff pass.

## STOP Conditions

- Plan 001 has not landed.
- The implementation would require bypassing `validate_public_url` or secure fetch protections.
- The report cannot be generated without real network calls in tests.

## Maintenance Notes

This command is the installed product proof loop. Keep it product-facing and stable; lower-level commands can remain more technical and specialized.
