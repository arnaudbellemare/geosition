# Plan 007: Unblock Tracker NPM Audit

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report; do not improvise. When done, update the status row for this plan in
> `docs/plans/README.md`.
>
> **Drift check (run first)**:
> `git diff --stat 6845682..HEAD -- apps/geo-aeo-tracker/package.json apps/geo-aeo-tracker/package-lock.json .github/workflows/ci.yml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **State**: DONE
- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: dependencies
- **Planned at**: commit `6845682`, 2026-07-05

## Why This Matters

The tracker CI job runs `npm audit --audit-level=moderate`, and the current dependency tree fails that gate because of a transitive moderate `js-yaml` advisory. That means otherwise good commits can fail CI before the tracker build runs. The fix should update or override the affected transitive dependency without weakening the audit threshold.

## Current State

- `.github/workflows/ci.yml` — tracker CI gate.
- `apps/geo-aeo-tracker/package.json` — tracker dependency manifest.
- `apps/geo-aeo-tracker/package-lock.json` — tracker lockfile.

Current CI command:

```yaml
# .github/workflows/ci.yml:102
- name: Install and build tracker app
  run: |
    cd apps/geo-aeo-tracker
    npm ci
    npm audit --audit-level=moderate
    npm run build
```

Current tracker manifest has one override, but not for `js-yaml`:

```json
// apps/geo-aeo-tracker/package.json:33
"overrides": {
  "postcss": "8.5.15"
}
```

Current lockfile includes the affected transitive package:

```json
// apps/geo-aeo-tracker/package-lock.json:5190
"node_modules/js-yaml": {
  "version": "4.1.1",
  ...
}
```

During this audit, `npm audit --audit-level=moderate --json` in `apps/geo-aeo-tracker` exited 1 and reported:

- `js-yaml` moderate advisory: quadratic-complexity DoS in merge key handling.
- `@babel/core` low advisory: below the configured moderate threshold, but should be rechecked after dependency refresh.

Repo conventions:

- The tracker app uses npm, Next, and `package-lock.json`.
- Do not weaken CI security gates to hide advisories.
- Keep Node 22 compatibility; CI uses `actions/setup-node@v6` with `node-version: "22"`.

## Commands You Will Need

| Purpose | Command | Expected on success |
|---|---|---|
| Install/refresh lockfile | `npm install` from `apps/geo-aeo-tracker` | exit 0; lockfile updated if needed |
| Audit tracker | `npm audit --audit-level=moderate` from `apps/geo-aeo-tracker` | exit 0 |
| Build tracker | `npm run build` from `apps/geo-aeo-tracker` | exit 0 |
| Root SEO check | `npm run seo:verify` from repo root | exit 0 |
| Diff hygiene | `git diff --check` | exit 0 |

## Scope

**In scope**:

- `apps/geo-aeo-tracker/package.json`
- `apps/geo-aeo-tracker/package-lock.json`
- `apps/geo-aeo-tracker/next.config.ts` for Turbopack workspace-root build stability.
- `.github/workflows/ci.yml` only if the CI command must be clarified without weakening it.

**Out of scope**:

- Disabling `npm audit`.
- Lowering the audit threshold.
- Broad Next/React upgrades unrelated to the advisory.
- Python dependencies.

## Git Workflow

- Branch: `advisor/007-tracker-npm-audit`
- Commit message example: `Refresh tracker audit dependencies`
- Do not push unless the operator explicitly asks.

## Steps

### Step 1: Identify the Dependency Path

Run:

```bash
cd apps/geo-aeo-tracker
npm ls js-yaml
npm ls @babel/core
```

Record which direct dependency brings in `js-yaml`.

**Verify**: commands exit 0 or print the dependency path; if they exit nonzero only because npm reports invalid peer state, STOP and report.

### Step 2: Prefer a Dependency Refresh

First try a lockfile refresh without changing direct dependency ranges:

```bash
cd apps/geo-aeo-tracker
npm update js-yaml @babel/core
npm audit --audit-level=moderate
```

If that resolves the moderate advisory and `npm run build` passes, keep the minimal lockfile update.

**Verify**: `npm audit --audit-level=moderate` exits 0.

### Step 3: Add a Narrow Override Only If Needed

If `npm update` cannot resolve `js-yaml`, add the narrowest `overrides` entry in `apps/geo-aeo-tracker/package.json` that npm supports for the affected transitive dependency. Keep the existing `postcss` override.

Example target shape, only if a patched version exists:

```json
"overrides": {
  "postcss": "8.5.15",
  "js-yaml": "<patched-version>"
}
```

Then run `npm install` to update `package-lock.json`.

**Verify**: `npm audit --audit-level=moderate` exits 0.

### Step 4: Build and Check the Tracker

Run:

```bash
cd apps/geo-aeo-tracker
npm run build
```

If the build fails due to dependency resolution changes, revert the override/update and STOP. Do not start broad framework upgrades inside this plan.

**Verify**: `npm run build` exits 0.

## Test Plan

This is a dependency/CI gate plan. Verification is command-based:

- `npm audit --audit-level=moderate` must exit 0 in `apps/geo-aeo-tracker`.
- `npm run build` must exit 0 in `apps/geo-aeo-tracker`.
- `npm run seo:verify` must still exit 0 from the repo root.

## Done Criteria

- [x] Tracker `npm audit --audit-level=moderate` exits 0.
- [x] Tracker `npm run build` exits 0.
- [x] Root `npm run seo:verify` exits 0.
- [x] No CI audit threshold was weakened.
- [x] Only in-scope files changed.
- [x] `git diff --check` passes.
- [x] `docs/plans/README.md` status row updated.

## STOP Conditions

Stop and report if:

- No patched `js-yaml` version is available through npm.
- Fixing the advisory requires a major Next/React upgrade.
- `npm install` rewrites unrelated dependency ranges unexpectedly.
- The tracker build fails after the dependency refresh.

## Maintenance Notes

Keep the tracker audit command strict. If an advisory is build-only and temporarily unavoidable, document a narrow, dated exception in CI rather than removing the audit gate wholesale.
