# Changelog

All notable changes to GEO/AEO Tracker are documented here.

---

## [1.2.0] — 2026-04-17

### ✨ New: Optional Supabase cloud persistence

Local-first storage (IndexedDB) remains the default. When you supply three env vars, all app state is automatically synced to your own free Supabase project — across devices, deploys, and browser clears.

**What changed**

- **`app/api/state/route.ts`** — new `GET / PUT / DELETE` route that proxies reads and writes to Supabase using the `service_role` key server-side. The client never calls Supabase directly. Returns `501` gracefully when cloud is not configured.
- **`lib/server/supabase.ts`** — `getServerSupabase()` singleton; reads `SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY`.
- **`lib/server/kv-store.ts`** — `kvGet` / `kvSet` / `kvDelete` helpers used by the route.
- **`lib/client/cloud-mode.ts`** — `isCloudAvailable()` (build-time env flag) and `isCloudEnabledByUser()` (per-browser localStorage toggle, defaults to `true` when cloud is available).
- **`lib/client/sovereign-store.ts`** — rewired to branch on `isCloudActive()`. IDB becomes a local cache when cloud is active; IDB is the authoritative fallback if the cloud route fails. Public API (`loadSovereignValue` / `saveSovereignValue` / `clearSovereignStore`) is unchanged — all existing callers work without modification.
- **`components/dashboard/tabs/project-settings-tab.tsx`** — new **Cloud Sync** card in Project Settings. Shows setup instructions when cloud is not configured; shows an enable/disable toggle when it is.
- **`supabase/migrations/001_kv_store.sql`** — single-table `kv_store` schema (`key TEXT PK, value JSONB, created_at, updated_at`) with an `updated_at` trigger. Paste and run in your Supabase SQL editor to set up.
- **`package.json`** — added `@supabase/supabase-js ^2.103.3`.
- **`README.md`** — new "☁️ Optional: Cloud persistence with Supabase" section with 5-step setup guide; architecture tree updated; API routes table updated; Cloud Sync added to nav.

**Env vars needed (all optional)**

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key   # server-side only, never exposed to client
NEXT_PUBLIC_CLOUD_STORAGE_ENABLED=true
```

**What is NOT synced (intentionally local)**

- Theme preference
- Workspace list / active workspace
- The `sovereign-cloud-sync` toggle state itself

---

## [1.1.0] — 2026-03-22

### ✨ Features

- **Prompt tags** — inline tag editing on prompts; filter bar to narrow prompt list by tag
- **Delete individual responses** — confirmation dialog guards accidental deletes
- **Multiple website URLs** — chip-based input supporting multiple URLs per brand
- **Structured competitors** — `Competitor` type with name, aliases, and websites fields

### 🐛 Fixes

- Increase Bright Data scraper timeout with exponential backoff to reduce timeout failures (#3)
- Backward-compatible data migrations for all new data types

---

## [1.0.0] — 2026-03-13

### ✨ Features

- **SRO Analysis** — full 6-stage pipeline: Gemini Grounding → Cross-Platform Citations → SERP → Page Scraping → Site Context → LLM Analysis. Produces SRO Score (0–100) with prioritized recommendations.
- **Parallel batch runs** — all prompt × model combos execute simultaneously via `Promise.allSettled()`
- **Mobile-responsive** — collapsible sidebar (hamburger at `md:` breakpoint), backdrop overlay, responsive KPI grid and model toolbar

### 🆕 New API routes

`/api/sro-analyze`, `/api/bulk-sro` (SSE), `/api/serp`, `/api/site-context`, `/api/unlocker`, `/api/brightdata-platforms`

### 🐛 Fix

- Grok badge invisible in light mode (#1)

---

## [0.1.0] — 2026-02-14

Initial release — 12-tab dashboard, 6 AI model tracking, local-first storage, demo mode, Bright Data + OpenRouter integration.
