---
name: content-aeo-optimizer
description: Rewrite an existing page so AI assistants can extract, quote, and cite it — front-loaded answers, comparison tables, attributable claims, FAQ blocks, and JSON-LD schema via the geo CLI. Use when a page ranks in Google but never gets cited by AI, or when optimizing high-intent pages for answer engines.
---

# Content AEO Optimizer

Restructures a page for answer engines without wrecking the human reading experience. Uses `geo content` to diagnose and `geo schema` to generate/inject markup.

## Workflow

### 1. Diagnose

```bash
geo content --url https://SITE/page --keywords "kw1,kw2" --format json
geo schema --file page.html --analyze
geo coherence --sitemap https://SITE/sitemap.xml --max-pages 20   # terminology consistency across the site when relevant
```

Audit the page against extraction patterns:

- Does the first paragraph directly answer the target question in ≤40 words?
- Are claims specific and attributable ("manages 4,200 units across 60 buildings" vs "extensive experience")?
- Are comparisons in structured tables, not prose?
- Is the brand named consistently (exact same entity string everywhere — check `geo coherence`)?
- Is there an FAQ block matching real buyer phrasing?

### 2. Rewrite weak sections

- Move a direct answer block to the top of the page.
- Convert prose comparisons into tables with concrete numbers.
- Rewrite vague claims into stat callouts with attribution.
- Add an FAQ section using the phrasing from the saved prompt panel (`runs/prompt-panel-*.md`) — bilingual pages get fr and en FAQ variants.
- Keep the human narrative intact: answer blocks first, story after.

### 3. Generate and inject schema

```bash
geo schema --file page.html --type faq --url https://SITE/page --auto-extract --inject
geo schema --file page.html --type article --name "..." --author "..." --inject
```

`--inject` backs up the file by default. Validate before shipping (validation runs unless `--no-validate`).

### 4. Verify

```bash
geo audit --url https://SITE/page
geo diff --before https://SITE/old-page --after https://SITE/new-page   # A/B when both versions are reachable
```

Log the change in `seo-changelog.md` with date, page, and expected effect.

## Rules

- Never fabricate stats or reviews to make claims "specific" — pull real numbers from the client or mark as TODO-for-client.
- One page per pass; re-audit after each to confirm the score moved.
- Preserve existing schema — analyze before injecting to avoid duplicate JSON-LD blocks.
