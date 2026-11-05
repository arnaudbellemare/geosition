---
name: programmatic-page-builder
description: Design scalable service × location page templates with title patterns, hub-and-spoke internal linking, JSON-LD schema, and thin-content safeguards. Use when scaling keyword coverage with service pages and location pages, or building comparison/directory page sets.
---

# Programmatic Page Builder

Scalable page templates that rank and get cited without reading as auto-generated. Core scaling principle for this project: **more service pages × more location pages = more keyword coverage**.

## Page types and URL patterns

| Type | URL Pattern | Example (property mgmt context) |
|---|---|---|
| Service × Location | /[service]-[city-or-borough] | /gestion-condo-plateau-mont-royal |
| Comparison | /[brand]-vs-[competitor] | /gestion-velora-vs-solutioncondo |
| Directory | /best-[category]-for-[use-case] | /meilleure-gestion-pour-petits-syndicats |
| Definition | /what-is-[term] | /quest-ce-que-la-gestion-de-copropriete |

Title formula for local service: `[Service] à [Quartier/Ville] — [Brand]`. Bilingual sites: separate fr and en URL trees with hreflang, never machine-swapped text.

## Template spec (produce this for every page set)

1. **Page type + URL pattern + page count** (services × locations — enumerate the actual matrix)
2. **Title + meta description templates** with 2 concrete examples
3. **Section structure**, marking each section Static / Variable / Mixed. Required variable sections:
   - Intro unique to the location (borough-specific housing stock, building age, tenant law nuances)
   - Local data points (unit counts, neighborhoods served, real client examples)
   - FAQ with location-specific questions (feed phrasing from `runs/prompt-panel-*.md`)
4. **Internal linking (hub & spoke)**: every spoke links to its service hub + 2–3 sibling locations; hubs list all spokes
5. **Schema per page**: LocalBusiness (name, address, telephone, areaServed) + BreadcrumbList — generate with `geo schema --type ...`; FAQPage when an FAQ section exists

## Thin-content safeguards (mandatory)

- ≥300–500 words unique content per page — never just name-swapping
- 2–3 unique sections beyond the template
- Each page answers its specific query with location-specific facts
- Flag the plan as at-risk if the data source can't support uniqueness at the proposed scale

## Verify

After generating a batch:

```bash
geo audit --sitemap https://SITE/sitemap.xml --max-urls 25
geo links --sitemap https://SITE/sitemap.xml --max-pages 30       # internal link graph + orphan pages
geo coherence --sitemap https://SITE/sitemap.xml --max-pages 20   # terminology consistency across the new pages
```

No orphans, consistent entity naming, and every new page in `llms.txt` sections (`geo llms`). Log the batch in `seo-changelog.md`.

## Rules

- Enumerate the real keyword matrix from `keywords.csv` before proposing page counts.
- Quality over count: if uniqueness data exists for only 8 boroughs, build 8 pages, not 19.
- Always deliver the spec in the Output Format: type overview → title/meta templates → section structure → linking rules → schema JSON-LD → uniqueness checklist → one fully worked example page.
