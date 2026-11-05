# GEOSITION Platform (SaaS MVP)

Multi-tenant workspace: account-email signup, domain verification, GEO audit, AI benchmark runs, and GEOSITION
Index telemetry for observed AI answer usage.

## Storage tiers

See **[STORAGE.md](STORAGE.md)** — MVP (`data/` + SQLite), production (Supabase), blobs (Fil One / S3).

For hosted Vercel deployments, signup/login uses Supabase when the Supabase environment variables are present.
That is the recommended free durable production path. If Supabase is missing and `GEO_PLATFORM_BACKEND` is not set,
GEOSITION falls back to SQLite under `/tmp` so auth routes do not crash during a first deploy, but serverless `/tmp`
is temporary and can lose newly registered users between cold starts or function instances.

```bash
SUPABASE_URL=https://your-project.supabase.co
# or NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=...
# recommended explicit durable backend:
GEO_PLATFORM_BACKEND=supabase
```

Set `GEO_PLATFORM_BACKEND=supabase` to make missing Supabase config fail fast instead of using temporary SQLite.
Apply every Supabase migration in order before opening registration in production:

```bash
for migration in supabase/migrations/*.sql; do
  psql "$POSTGRES_URL_NON_POOLING" -v ON_ERROR_STOP=1 -f "$migration"
done
```

The current required platform migrations are:

- `002_geo_platform.sql` — accounts, sessions, domains, benchmarks, runs, Index events.
- `003_weekly_evidence_runs.sql` — durable weekly evidence reports.
- `004_platform_feature_storage_backfill.sql` — idempotent backfill for projects that ran an older `002` before
  page-audit and weekly-report storage existed.

Password reset email in production can use Plunk (open-source email), a no-SMTP automation webhook, or SMTP fallback.
For Plunk, use Plunk Cloud or a self-hosted Plunk instance:

```bash
GEOSITION_PLUNK_API_KEY=...
GEOSITION_PASSWORD_RESET_FROM=support@example.com
# optional for self-hosted Plunk:
GEOSITION_PLUNK_API_URL=https://plunk.example.com/v1/send
```

For a generic open-source automation such as n8n, Activepieces, Node-RED, or a small serverless function, point
GEOSITION at an HTTP webhook:

```bash
GEOSITION_PASSWORD_RESET_WEBHOOK_URL=https://your-mail-service.example/reset
# optional bearer token sent as Authorization: Bearer ...
GEOSITION_PASSWORD_RESET_WEBHOOK_SECRET=...
GEOSITION_PASSWORD_RESET_FROM=support@example.com
```

The automation webhook receives JSON with `to`, `from`, `subject`, `text`, `html`, and `reset_url`.

SMTP is still supported as a fallback:

```bash
GEOSITION_SMTP_HOST=smtp.example.com
GEOSITION_SMTP_PORT=587
GEOSITION_SMTP_USERNAME=...
GEOSITION_SMTP_PASSWORD=...
GEOSITION_SMTP_FROM=support@example.com
# optional:
GEOSITION_SMTP_TLS=1
GEOSITION_SMTP_SSL=0
```

Without webhook or SMTP delivery, local development still shows a one-time reset URL on the page. Hosted Vercel
deployments do not expose development reset links.

## Production deploy smoke

After every production deploy, run the protected platform health checklist first:

```bash
curl -fsS \
  -H "X-GEOSITION-Worker-Token: $GEOSITION_WORKER_TOKEN" \
  https://geositionai.com/api/v1/platform/health
```

The response reports Supabase table readiness, service-role configuration, password reset delivery, worker-token
configuration, and hosted collection provider readiness. `ok: true` means the critical production path is ready:
durable storage, password reset delivery, and worker authentication.

Then run the live smoke runner:

```bash
python scripts/platform-production-smoke.py \
  --base-url https://geositionai.com \
  --domain "$GEOSITION_SMOKE_DOMAIN" \
  --worker-token "$GEOSITION_WORKER_TOKEN" \
  --require-reset-delivery
```

For the full verification/audit KPI, use a controlled smoke domain and provision the printed DNS TXT or HTTPS file
token, then run:

```bash
python scripts/platform-production-smoke.py \
  --base-url https://geositionai.com \
  --domain "$GEOSITION_SMOKE_DOMAIN" \
  --worker-token "$GEOSITION_WORKER_TOKEN" \
  --verify-method dns \
  --require-verified \
  --require-reset-delivery
```

The smoke covers signup, login, add domain, dashboard render, optional domain verification, optional audit after
verification, and forgot-password delivery status. It does not bypass ownership verification.

For browser dashboard regression coverage against a running local or production deployment:

```bash
GEOSITION_BASE_URL=https://geositionai.com npm run test:dashboard
```

Set `GEOSITION_PLAYWRIGHT_VERIFIED_EMAIL`, `GEOSITION_PLAYWRIGHT_VERIFIED_PASSWORD`, and
`GEOSITION_PLAYWRIGHT_VERIFIED_DOMAIN` to enable the unlocked-dashboard portion of the Playwright test.

## Fictional demo

See **`examples/demo/README.md`** for fictional benchmark prompts and answers.

```bash
geosition demo
```

## Run locally

```bash
pip install -e ".[web]"
geo-web
# or: uvicorn geo_optimizer.web.app:app --reload --port 8000
```

Open:

- **https://localhost:8000/platform** — register / dashboard
- **https://localhost:8000/docs** — OpenAPI (includes `/api/v1/*`)

## Guided public first audit

When the public audit API is enabled (no `GEO_API_TOKEN` configured), a visitor can enter a website on the landing
page and run a first check without creating an account. The existing URL validation, secure fetch, and rate limits
still apply. The public check covers the submitted page and supporting public site signals; it does not establish
Google rankings, AI answer mentions, site-wide coverage, or private analytics. Results show up to three suggested
actions, which the visitor can copy for their developer. If the API is token-protected, the public page explains
that access is required instead of bypassing authentication.

The benchmark uses the `evidence-v2` scoring model for new runs: unavailable components are excluded rather than
assigned placeholder scores, and the result includes the proportion of configured component weight measured.
Legacy scores remain labeled `legacy` and should not be compared directly with the new model. Failed collection
attempts are not treated as answers or non-citations. API collection can record a requested prompt language, but
the Gemini and Perplexity API lanes do not claim an effective country where it was not enforced.

## Flow

1. **Register** with any email you can access, including Gmail, Outlook, or a company email.
2. Workspace is created for that account email.
3. **Add website** `yourcompany.com`; it does not need to match the account email domain.
4. **Verify** via DNS TXT on `_geo-verify.yourcompany.com` or HTTPS `/.well-known/geo-verify.txt`.
5. Add **competitors** and **prompts**.
6. Paste **answers.json** (from `geo benchmark collect` or geo-aeo-tracker export) and **Run benchmark**.
7. Review **GEOSITION Index** usage events created from the benchmark, or record observed AI answers manually.
8. Optional: **Run audit** for on-site GEO score.

## Hosted collection after verification

Hosted deployments can queue answer collection automatically after DNS/HTTPS verification:

```bash
export GEOSITION_AUTO_COLLECTION_ON_VERIFY=1
export PERPLEXITY_API_KEY=...
export GEOSITION_WORKER_TOKEN=...
# optional:
export GEMINI_API_KEY=...
export GEOSITION_COLLECTION_PROVIDERS=perplexity,gemini
```

When enabled, successful domain verification creates a queued `collection` platform run. If provider credentials are
available, a hosted worker can collect starter prompts, run the benchmark, and write benchmark-derived Index events. If
no provider credentials are configured, the run completes with `no_provider_credentials` so the dashboard can show the
next setup step instead of pretending telemetry exists.

API:

- `GET /api/v1/collection/status?domain=example.com` — provider readiness and latest collection runs.
- `POST /api/v1/collection/start` — manually queue hosted collection for a verified domain.
- `POST /api/v1/collection/run` — execute the next queued hosted collection from a worker context. Requires
  `X-GEOSITION-Worker-Token: $GEOSITION_WORKER_TOKEN`; normal browser/session users can only queue work.

## GEOSITION Index telemetry

The Index layer is the content-owner usage ledger. It records how a verified domain is surfaced, cited, or
recommended in AI answers, then rolls those observations into citation rate, top recommendation rate, agent coverage,
top queries, top pages, and estimated value units.

Each event stores:

- `source_type`: `manual_ai_answer`, `benchmark`, `crawler_log`, `retrieval_probe`, `serp_check`, or `partner_api`
- agent/provider, query, answer excerpt, cited URL, citation rank
- surfaced/cited/top-recommendation booleans
- confidence, evidence metadata, and estimated value units

Current feeds:

- `/platform` benchmark runs automatically create `benchmark` events.
- Hosted collection can be queued automatically after verification when providers are configured; a worker-token-gated
  hosted worker then collects answers, runs the benchmark, and creates `benchmark` events.
- `/api/v1/index/events` records manually observed AI answers for verified domains.
- `/api/v1/index/summary` returns the content-owner dashboard contract.
- `/platform/index/check?domain=example.com` provides the public domain preview/claim funnel.

Value units are an internal attribution estimate, not a payout or legal valuation. They are the stable bridge toward
retrieval probes, data partnerships, and future compensation experiments.

## API (Bearer session token)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Login |
| GET | `/api/v1/me` | Current user + org |
| GET | `/api/v1/dashboard` | Full workspace |
| POST | `/api/v1/domains` | Add website + verify instructions |
| POST | `/api/v1/domains/{id}/verify` | Check DNS/HTTPS verification |
| POST | `/api/v1/competitors` | Add competitor domain |
| POST | `/api/v1/prompts` | Add tracking prompt |
| POST | `/api/v1/audit` | GEO audit (verified domain) |
| POST | `/api/v1/benchmark/run` | Benchmark from answers JSON |
| GET | `/api/v1/index/preview` | Public Index preview for a domain |
| GET | `/api/v1/index/summary` | Verified-domain agent usage summary |
| POST | `/api/v1/index/events` | Record observed AI answer usage |

Session token: response `session.token` or cookie `geo_session`.

## Data storage

- Platform DB: `~/.geo-optimizer/platform.db`
- Benchmark DB: `~/.geo-optimizer/benchmark.db`
- Hosted auth/workspaces: Supabase when `SUPABASE_URL`/`NEXT_PUBLIC_SUPABASE_URL` and
  `SUPABASE_SERVICE_ROLE_KEY` are configured on Vercel. Without those variables, Vercel uses temporary SQLite
  under `/tmp` as a crash-prevention fallback only; configure Supabase for durable user accounts.

Override:

```bash
export GEO_PLATFORM_DB=/path/to/platform.db
export GEO_BENCHMARK_DB=/path/to/benchmark.db
```

## Next steps (not in MVP)

- Stripe billing, email magic link, scheduled collection workers
- Hosted `geo benchmark collect pipeline` per org
- Supabase Auth + RLS instead of SQLite sessions
