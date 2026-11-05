# Plan 006: Separate Target Domain from Verified Domain in Platform API

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report; do not improvise. When done, update the status row for this plan in
> `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 6845682..HEAD -- src/geo_optimizer/saas/models.py src/geo_optimizer/saas/service.py src/geo_optimizer/web/platform_routes.py src/geo_optimizer/web/templates/platform/dashboard.html tests/test_platform_saas.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **State**: DONE
- **Priority**: P1
- **Effort**: S
- **Risk**: MED
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `6845682`, 2026-07-05

## Why This Matters

The platform API field `primary_verified_domain` currently contains the first pending domain when no domain has been verified. The dashboard template works around this by recomputing display state, but API consumers can read a pending domain from a field whose name promises verification. That creates confusing onboarding state and can lead clients or future automation to unlock/report against a domain that is not actually verified.

The fix should make the contract explicit: one field for the current target/display domain, and one field for the verified domain that is empty until verification succeeds.

## Current State

- `src/geo_optimizer/saas/models.py` — `PlatformDashboard` response model.
- `src/geo_optimizer/saas/service.py` — chooses the dashboard domain.
- `src/geo_optimizer/web/platform_routes.py` — serializes the API and renders the dashboard page.
- `src/geo_optimizer/web/templates/platform/dashboard.html` — already has `{{DISPLAY_DOMAIN}}` placeholders.
- `tests/test_platform_saas.py` — has locked-dashboard tests but does not assert API semantics for pending domains.

Current `dashboard()` implementation:

```python
# src/geo_optimizer/saas/service.py:278
def dashboard(self, token: str) -> PlatformDashboard:
    user, org = self.require_session(token)
    domains = self.store.list_domains(org.org_id)
    verified = [d for d in domains if d.status == "verified"]
    primary = verified[0].domain if verified else (domains[0].domain if domains else "")
    ...
    return PlatformDashboard(..., primary_verified_domain=primary)
```

Current HTML route works around the ambiguity:

```python
# src/geo_optimizer/web/platform_routes.py:715
has_verified_domain = any(domain.status == "verified" for domain in dash.domains)
display_domain = dash.primary_verified_domain or (dash.domains[0].domain if dash.domains else "")
```

Current API serialization exposes only the ambiguous field:

```python
# src/geo_optimizer/web/platform_routes.py:895
return {
    "domains": [asdict(d) for d in dash.domains],
    "primary_verified_domain": dash.primary_verified_domain,
    ...
}
```

Existing tests prove the pending dashboard UI is visible, but not that the API keeps verified and pending states separate:

```python
# tests/test_platform_saas.py:1142
domains = client.get("/api/v1/dashboard", headers={"Authorization": f"Bearer {token}"}).json()["domains"]
assert domains[0]["domain"] == "flowco.test"
assert domains[0]["status"] == "pending"
```

Repo conventions:

- Keep core platform state in `saas/models.py` and `saas/service.py`.
- Route handlers should serialize the service model without inventing business rules.
- Preserve backward compatibility where practical; adding a new field is safer than immediately removing an old one.

## Commands You Will Need

| Purpose | Command | Expected on success |
|---|---|---|
| Focused tests | `python3 -m pytest tests/test_platform_saas.py -q` | exit 0; all tests pass |
| Full tests | `python3 -m pytest tests/ -q` | exit 0; all tests pass |
| Lint touched files | `python3 -m ruff check src/geo_optimizer/saas/models.py src/geo_optimizer/saas/service.py src/geo_optimizer/web/platform_routes.py tests/test_platform_saas.py` | exit 0; no errors |
| Diff hygiene | `git diff --check` | exit 0; no whitespace errors |

## Scope

**In scope**:

- `src/geo_optimizer/saas/models.py`
- `src/geo_optimizer/saas/service.py`
- `src/geo_optimizer/web/platform_routes.py`
- `src/geo_optimizer/web/templates/platform/dashboard.html` only if needed
- `tests/test_platform_saas.py`

**Out of scope**:

- Domain verification mechanics.
- Dashboard visual redesign.
- Any billing, worker, benchmark, or Supabase migration changes.

## Git Workflow

- Branch: `advisor/006-domain-state-contract`
- Commit message example: `Clarify platform domain state contract`
- Do not push unless the operator explicitly asks.

## Steps

### Step 1: Add an Explicit Target Domain Field

Add a new `target_domain: str = ""` or `display_domain: str = ""` field to `PlatformDashboard` in `src/geo_optimizer/saas/models.py`.

In `PlatformService.dashboard()`:

- Compute `verified_domain = verified[0].domain if verified else ""`.
- Compute `target_domain = verified_domain or (domains[0].domain if domains else "")`.
- Use `target_domain` for best-effort dashboard page-audit/report/index lookups only if that is still desired for pending-domain displays.
- Set `primary_verified_domain=verified_domain`.
- Set `target_domain=target_domain`.

**Verify**: `python3 -m pytest tests/test_platform_saas.py -q` may fail until Step 2 updates expectations; continue to Step 2.

### Step 2: Serialize Both Fields

Update `api_me()` and `api_dashboard()` in `src/geo_optimizer/web/platform_routes.py`:

- Keep `primary_verified_domain` for backward compatibility, but make it empty when no domain is verified.
- Add `target_domain` to both responses.

Update the dashboard HTML route:

```python
display_domain = dash.target_domain
```

Do not reintroduce fallback to `organization.email_domain` for website fields.

**Verify**: `rg -n "primary_verified_domain or \\(dash\\.domains\\[0\\]" src/geo_optimizer/web/platform_routes.py` -> no matches.

### Step 3: Add Pending and Verified API Tests

In `tests/test_platform_saas.py`, extend the Gmail/pending-domain flow:

- Register with `lead@gmail.com` and `domain="flowco.test"`.
- Call `/api/v1/dashboard`.
- Assert `target_domain == "flowco.test"`.
- Assert `primary_verified_domain == ""`.
- Assert the domain row status is still `pending`.

Add or update a verified-domain test:

- Mark the domain verified using the existing test helper/mocked verifier pattern.
- Assert both `target_domain` and `primary_verified_domain` equal the verified domain.

**Verify**: `python3 -m pytest tests/test_platform_saas.py -q` -> all pass.

## Test Plan

Add or update tests in `tests/test_platform_saas.py`:

- `test_dashboard_api_separates_pending_target_from_verified_domain`
- `test_dashboard_api_sets_primary_verified_domain_after_verification`

Use the existing `test_platform_first_run_website_field_and_locked_dashboard_flow` and `test_platform_dashboard_prefers_pending_website_domain_over_account_email_domain` as structural patterns.

## Done Criteria

- [x] Pending domains appear as `target_domain`, not `primary_verified_domain`.
- [x] Verified domains appear in both `target_domain` and `primary_verified_domain`.
- [x] Dashboard HTML still displays the website domain, not the Gmail/Outlook account domain.
- [x] `python3 -m pytest tests/test_platform_saas.py -q` passes.
- [x] `python3 -m pytest tests/ -q` passes.
- [x] `python3 -m ruff check src/geo_optimizer/saas/models.py src/geo_optimizer/saas/service.py src/geo_optimizer/web/platform_routes.py tests/test_platform_saas.py` passes.
- [x] `git diff --check` passes.
- [x] `plans/README.md` status row updated.

## STOP Conditions

Stop and report if:

- External clients are documented as depending on `primary_verified_domain` containing pending domains.
- The fix requires changing database schema.
- The dashboard cannot render the locked/pending state without treating pending as verified.

## Maintenance Notes

Future dashboard and worker code should ask two different questions explicitly: "what domain should the user see next?" and "what domain is verified enough to unlock expensive features?" A reviewer should scrutinize any future code that uses `primary_verified_domain` to ensure it does not accidentally include pending domains again.
