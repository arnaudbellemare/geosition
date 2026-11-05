---
name: e2e-seo-assistant
description: Full SEO workflow in one pass — technical audit, on-page issues, content gaps, backlink opportunities, keyword mapping, and a ready-to-write content brief. Use when given a site and target keywords for complete classic-SEO analysis alongside the GEO pipeline.
---

# E2E SEO Assistant

Classic SEO companion to the GEO pipeline: audit → gaps → brief, powered by `geo seo`, `geo content`, and `geo links`.

## Workflow

### 1. Technical + on-page audit

```bash
geo audit --url https://SITE --format json
geo seo lighthouse --url https://SITE                      # Core Web Vitals, accessibility, SEO score (PageSpeed by default)
geo seo domain --url SITE.com --competitor COMPETITOR.com  # authority, top pages, ranked keywords, keyword gap
geo links --sitemap https://SITE/sitemap.xml --max-pages 30  # internal link graph, orphan pages
```

Checklist highlights: robots.txt not blocking key pages (and AI bots allowed — see SKILL.md step 2), sitemap present, crawl depth <4, no noindex accidents, canonical correctness, one H1 per page with primary keyword, titles <60 chars, metas <155 chars, LCP <2.5s / INP <200ms / CLS <0.1.

### 2. Content gaps

```bash
geo content --url https://SITE/page --keywords "..." --top-terms 20
geo rivalry --url https://SITE --vs https://COMPETITOR --sitemap https://COMPETITOR/sitemap.xml
```

Find gaps by: competitor keywords they rank for, missing funnel stages (TOFU/MOFU/BOFU), missing topic-cluster spokes. Prioritize by volume × business value, preferring keyword difficulty <40. Cross-reference `keywords.csv` and `seo/BACKLOG.md` — append new gaps to the backlog rather than a parallel list.

### 3. Backlink opportunities

| Type | How to find | Effort |
|---|---|---|
| Resource pages | "[topic] + ressources/resources" | Low |
| Directories | CORPIQ, APQ, local chambers | Low |
| Unlinked mentions | Brand monitoring (see `brand-answer-monitoring`) | Low |
| Guest posts | "[industry] + write for us / collaborez" | Medium |
| Competitor backlinks | From rivalry reports | Medium |

### 4. Content brief (per priority keyword)

Target + secondary keywords · search intent · target word count (from SERP analysis) · full H1–H3 outline · People-Also-Ask questions to answer · internal links with anchor text · competitor table (word count, unique angle) · your differentiating angle. Bilingual keywords get one brief per language, not a translation.

### 5. Output

Single report: technical health score, critical issues table, content gap table, backlink table, one full content brief, and a prioritized action plan (impact × effort). Save as `seo/audit-<client>-<date>.md`; follow `seo/PR_TEMPLATE.md` when the fixes become a PR.

## Rules

- Quick wins first: high impact, low effort at the top of the action plan.
- Every recommendation maps to a concrete fix or brief — no vague "improve content" items.
- Ask for target keywords if not provided; note missing data sources (GSC, Ahrefs) explicitly instead of guessing metrics.
