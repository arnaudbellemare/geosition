# Direct Vercel evidence for a commerce audit

The local `geo commerce-audit` command can retrieve historical Vercel CDN request records and Vercel's verified AI-traffic aggregate through an authenticated Vercel CLI. Use a CLI version that supports `logs requests` and `metrics` (tested with 65.16.0). Sign into the intended account separately. GEOSITION invokes the local CLI and does not request, save, or print its access token. Access and metrics availability depend on the Vercel account and plan.

Start with a real ChatGPT browser visit and record its page URL, request ID, project, team scope, and a narrow minute-aligned UTC window. For example:

```sh
geo commerce-audit --site --url https://www.robel-art.com/shop.html --max-pages 3 --format json \
  --vercel-scope arnaud15 --vercel-project mom-art-shop \
  --vercel-request-id c5q9b-1794617263722-2a9af87c7479 \
  --vercel-since 2026-11-14T00:47:00Z --vercel-until 2026-11-14T00:49:00Z
```

If the executable is not named `vercel` on PATH, pass `--vercel-cli /path/to/vercel` or set `GEOSITION_VERCEL_CLI`. For another business, use its own scope, project, audited page and request ID. Do not enter secret tokens in command arguments.

The check requires complete, unpaginated request records for the same project and window, an allowed GET for the exact page and request ID, and a Vercel verified `chatgpt-operator` count equal to all request records in the window. If any data is unavailable, mixed or incomplete, it refuses to infer verification. A successful result is `provider_verified_correlated`: Vercel's historical verified-agent aggregate is correlated with a request, not individual signature validation or proof of current site-wide access. `verified_access` remains `unknown` for the ordinary audit.

This is a **local CLI connection**, not a hosted, multi-tenant Vercel account integration. The guided web setup does not inherit the host user's Vercel credentials; its existing operator-reported evidence flow remains separate. A hosted connection needs provider authorization and per-workspace credential management before it can safely provide direct retrieval.
