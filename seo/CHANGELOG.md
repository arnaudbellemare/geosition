# SEO / GEO program changelog

Structured map of the execution phases, deploy logging, and explicit rejection of outdated tactics. Update this file when a phase completes or a tactic is retired.

## 13-phase map (rolling)

| Phase | Focus | Exit criteria (examples) |
|------:|--------|--------------------------|
| 1 | Baseline + inventory | sitemap, templates, critical URLs listed |
| 2 | Technical crawl hygiene | 4xx/5xx, redirect chains, indexation blockers |
| 3 | Core templates | single URL pattern per intent; no duplicate thin doors |
| 4 | International / locale | `hreflang` or clear locale routing; EN/FR parity where required |
| 5 | Schema + entity | valid JSON-LD; Organization/local where applicable |
| 6 | On-page + IA | H1/H2, internal links, canonical intent clear |
| 7 | llms.txt + AI discovery | policy files aligned with product stance |
| 8 | Content quality | factuality, sources, not generic scaled filler |
| 9 | Media + CWV | LCP/CLS where measured; images sized and labeled |
| 10 | GSC + measurement | properties, segments, annotation discipline |
| 11 | Off-site / brand | NAP/entity consistency (if local), reputable citations |
| 12 | Experiments + learning | hypothèses; no vanity metrics |
| 13 | Sustain + prune | remove losers; accretion over volume |

## Deploy log

| Date (UTC) | Change | Owner | Rollback ref |
|------------|--------|-------|--------------|
| 2026-05-01 | Initial program scaffold in repo | — | — |

## Stale tactics (do not reintroduce)

- **AI-only sludge pages**: mass-generated “SEO articles” with no unique evidence or utility.
- **Fake metrics in reports**: any number not from GSC, logs, or an agreed data source.
- **Keyword stuffing** in titles/body/alt that does not match page purpose.
- **Cloaking** or different content for bots vs users.

When a tactic is retired, add a one-line reason and link the replacement approach in `seo/decision-cards.md`.
