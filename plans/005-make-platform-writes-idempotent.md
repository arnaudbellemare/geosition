# Plan 005: Make Platform Writes Idempotent and Return JSON Errors

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report; do not improvise. When done, update the status row for this plan in
> `plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 6845682..HEAD -- src/geo_optimizer/saas/supabase_store.py src/geo_optimizer/saas/store.py src/geo_optimizer/web/platform_routes.py tests/test_platform_saas.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **State**: DONE
- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: none
- **Category**: bug
- **Planned at**: commit `6845682`, 2026-07-05

## Why This Matters

Production uses Supabase for durable platform state, but several write methods use plain `POST` into tables with unique constraints. Re-adding an existing domain, competitor, or prompt can raise `RuntimeError`, and several API routes do not catch that storage failure, producing generic 500 responses instead of useful JSON. This is exactly the failure class that makes users see "Internal Server Error" or invalid JSON while trying normal dashboard actions.

The fix should make Supabase behavior match the local SQLite store: duplicate user actions should update or no-op idempotently, and storage failures should become consistent JSON API errors.

## Current State

- `src/geo_optimizer/saas/supabase_store.py` — Supabase PostgREST store used in production.
- `src/geo_optimizer/saas/store.py` — local SQLite store; already has more idempotent behavior for some writes.
- `src/geo_optimizer/web/platform_routes.py` — FastAPI route layer that should normalize storage errors into JSON.
- `tests/test_platform_saas.py` — SaaS regression suite.

Current Supabase request helper raises `RuntimeError` for any PostgREST 4xx/5xx:

```python
# src/geo_optimizer/saas/supabase_store.py:81
def _request(..., prefer: str = "return=representation") -> list[dict]:
    ...
    response = requests.request(method, url, headers=headers, json=json_body, timeout=30)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase {method} {table} failed: {response.status_code} {response.text[:300]}")
```

Current Supabase writes use plain `POST` despite unique constraints on `(org_id, domain)` and `(org_id, external_id)`:

```python
# src/geo_optimizer/saas/supabase_store.py:300
def add_domain(self, org_id: int, domain: str, verify_token: str) -> VerifiedDomain:
    normalized = _normalize_domain(domain)
    rows = self._request(
        "POST",
        _TABLE_DOMAINS,
        json_body={...},
    )
    return self._row_domain(rows[0])

# src/geo_optimizer/saas/supabase_store.py:339
def add_competitor(self, org_id: int, domain: str) -> OrgCompetitor:
    normalized = _normalize_domain(domain)
    rows = self._request("POST", _TABLE_COMPETITORS, json_body={"org_id": org_id, "domain": normalized})

# src/geo_optimizer/saas/supabase_store.py:353
def add_prompt(...):
    ext = external_id or f"p{abs(hash(query_text)) % 10_000_000}"
    rows = self._request("POST", _TABLE_PROMPTS, json_body={...})
```

Current SQLite prompt ID generation has the same unstable `hash()` pattern, although SQLite hides duplicate write failures with `ON CONFLICT`:

```python
# src/geo_optimizer/saas/store.py:548
def add_prompt(...):
    ext = external_id or f"p{abs(hash(query_text)) % 10_000_000}"
```

Current route handling catches storage `RuntimeError` in some endpoints but not in others:

```python
# src/geo_optimizer/web/platform_routes.py:957
@router.post("/api/v1/domains")
async def api_add_domain(body: DomainBody, token: str = Depends(require_write_token)):
    try:
        return _get_service().add_website_domain(token, body.domain)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

# src/geo_optimizer/web/platform_routes.py:973
@router.post("/api/v1/competitors")
async def api_add_competitor(body: CompetitorBody, token: str = Depends(require_write_token)):
    return _get_service().add_competitor(token, body.domain)

# src/geo_optimizer/web/platform_routes.py:978
@router.post("/api/v1/prompts")
async def api_add_prompt(body: PromptBody, token: str = Depends(require_write_token)):
    return _get_service().add_prompt(...)
```

Relevant schema constraints:

```sql
-- supabase/migrations/002_geo_platform.sql:50
unique (org_id, domain)

-- supabase/migrations/002_geo_platform.sql:70
unique (org_id, external_id)
```

Repo conventions:

- Python code under `src/` must keep `from __future__ import annotations`.
- Web/API business logic should remain in `saas/service.py` and stores; route handlers should only validate/translate errors.
- Tests should use `pytest`, `unittest.mock`, and `TestClient`, following `tests/test_platform_saas.py`.
- Keep Python 3.9 compatibility; do not introduce 3.10-only type syntax beyond existing allowed patterns.

## Commands You Will Need

| Purpose | Command | Expected on success |
|---|---|---|
| Focused tests | `python3 -m pytest tests/test_platform_saas.py -q` | exit 0; all tests pass |
| Full tests | `python3 -m pytest tests/ -q` | exit 0; all tests pass |
| Lint touched files | `python3 -m ruff check src/geo_optimizer/saas/supabase_store.py src/geo_optimizer/saas/store.py src/geo_optimizer/web/platform_routes.py tests/test_platform_saas.py` | exit 0; no errors |
| Diff hygiene | `git diff --check` | exit 0; no whitespace errors |

## Scope

**In scope**:

- `src/geo_optimizer/saas/supabase_store.py`
- `src/geo_optimizer/saas/store.py`
- `src/geo_optimizer/web/platform_routes.py`
- `tests/test_platform_saas.py`

**Out of scope**:

- Supabase SQL migrations, unless a tested store change proves the existing unique constraints are insufficient.
- Authentication/session semantics.
- Dashboard UI redesign.
- Any dependency upgrades.

## Git Workflow

- Branch: `advisor/005-platform-write-idempotency`
- Commit message example matching repo style: `Harden platform write idempotency`
- Do not push unless the operator explicitly asks.

## Steps

### Step 1: Replace Unstable Prompt IDs

Add a small helper in both stores, or one shared helper in `src/geo_optimizer/saas/store.py` imported by `supabase_store.py`, that derives a deterministic prompt external ID from normalized prompt text.

Target shape:

```python
import hashlib

def _prompt_external_id(query_text: str) -> str:
    digest = hashlib.sha256(query_text.strip().lower().encode("utf-8")).hexdigest()[:16]
    return f"p{digest}"
```

Use it instead of `abs(hash(query_text)) % 10_000_000` in both `PlatformStore.add_prompt()` and `SupabasePlatformStore.add_prompt()`.

**Verify**: `rg -n "hash\\(query_text\\)" src/geo_optimizer/saas` -> no matches.

### Step 2: Make Supabase Unique Writes Idempotent

In `SupabasePlatformStore`, make `add_domain()`, `add_competitor()`, and `add_prompt()` idempotent.

Preferred implementation:

- For `add_domain()`, use PostgREST upsert with conflict target `org_id,domain`, updating `verify_token`, `status`, and `verify_method` so re-adding a pending domain refreshes instructions.
- For `add_competitor()`, either upsert on `org_id,domain` or read existing row on duplicate.
- For `add_prompt()`, upsert on `org_id,external_id`, matching the SQLite `ON CONFLICT` behavior.

If PostgREST conflict syntax is awkward in the existing `_request()` helper, implement a read-before-write fallback:

1. Try `GET` with the unique key.
2. If found, `PATCH` fields and return it.
3. If not found, `POST`.

Keep all org filters explicit.

**Verify**: add tests in Step 3, then run `python3 -m pytest tests/test_platform_saas.py -q`.

### Step 3: Add Store Regression Tests

In `tests/test_platform_saas.py`, add tests for the local SQLite store:

- Adding the same prompt text twice without an explicit `external_id` returns one logical prompt and does not create a second list row.
- Adding the same domain twice returns the same normalized domain with a refreshed verification token or a clearly idempotent result.
- Adding the same competitor twice does not create duplicate competitor rows.

For Supabase, avoid real network. Use `unittest.mock` to patch `SupabasePlatformStore._request()` and assert the store handles an existing row path or sends the expected upsert/prefer parameters.

**Verify**: `python3 -m pytest tests/test_platform_saas.py -q` -> all pass, including the new tests.

### Step 4: Normalize Runtime Storage Errors in API Routes

Update these endpoints to catch `RuntimeError` and route through `_platform_service_http_error()` or an endpoint-specific JSON error:

- `api_add_domain`
- `api_verify_domain`
- `api_add_competitor`
- `api_add_prompt`
- `api_index_event`
- `api_index_crawler_log`

Do not expose raw Supabase error bodies to clients.

Use existing route patterns as examples:

```python
# src/geo_optimizer/web/platform_routes.py:947
except RuntimeError as exc:
    raise _platform_service_http_error(exc) from exc
```

Add a test that monkeypatches `_get_service().add_competitor()` or `add_prompt()` to raise `RuntimeError("Supabase POST ...")` and asserts the endpoint returns JSON with a 503, not a plain 500.

**Verify**: `python3 -m pytest tests/test_platform_saas.py -q` -> all pass.

## Test Plan

Add tests in `tests/test_platform_saas.py`:

- `test_prompt_external_id_is_stable_and_idempotent`
- `test_duplicate_domain_add_is_idempotent`
- `test_duplicate_competitor_add_is_idempotent`
- `test_platform_write_routes_return_json_when_storage_fails`
- one Supabase store unit test using mocked `_request()` for duplicate/upsert behavior.

Model route-storage-failure tests after `test_auth_routes_return_json_when_platform_storage_is_unavailable`.

## Done Criteria

- [x] `rg -n "hash\\(query_text\\)" src/geo_optimizer/saas` returns no matches.
- [x] Duplicate prompt/domain/competitor tests exist and pass for SQLite behavior.
- [x] Supabase store behavior is covered without real network.
- [x] Write routes return JSON errors for storage `RuntimeError`.
- [x] `python3 -m pytest tests/test_platform_saas.py -q` passes.
- [x] `python3 -m pytest tests/ -q` passes.
- [x] `python3 -m ruff check src/geo_optimizer/saas/supabase_store.py src/geo_optimizer/saas/store.py src/geo_optimizer/web/platform_routes.py tests/test_platform_saas.py` passes.
- [x] `git diff --check` passes.
- [x] `plans/README.md` status row updated.

## STOP Conditions

Stop and report if:

- PostgREST upsert syntax requires a schema migration.
- Existing Supabase tests or fixtures assume duplicate writes fail.
- The route error contract is intentionally documented elsewhere as plain 500.
- Fixing the issue requires changing public auth/session behavior.

## Maintenance Notes

Any future store implementation must match both SQLite and Supabase semantics for idempotent workspace writes. Reviewers should check that error messages sent to clients stay generic while server logs retain enough detail for debugging.
