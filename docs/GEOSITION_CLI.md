> **Scoring update:** Examples and point totals below reflect the previous scoring model. See the [current scoring rubric](scoring-rubric.md). Scores from the two models are not directly comparable.

# GEOSITION CLI Product Entry

GEOSITION is the product-facing command for the open GEOSITION core. It keeps the audit engine free and local, then layers paid hosted workflow around monitoring, scheduled runs, team access, managed collection, and client-ready reporting.

## Primary Commands

```bash
geosition start
geosition wizard
geosition run example.com
geosition autopilot example.com
geosition demo
geosition citation-report example.com
geosition status
geosition doctor
```

## First-Run Flow

`geosition wizard` guides a user through the path agencies and operators expect:

1. Domain
2. Account email
3. Domain verification instructions
4. Audit run
5. Competitor list
6. Benchmark run from collected answers

The wizard can complete offline. It validates and fetches only when the user chooses to run the audit.

## Local Reports

`geosition run domain.com` saves two artifacts under `~/.geosition/runs`:

- JSON evidence for machines and reproducibility
- HTML AI citation readiness report for humans

`geosition citation-report domain.com` creates a one-page client report that agencies can send after discovery calls or monthly review.

## Autopilot Output

`geosition autopilot domain.com` produces a portable run artifact with:

- audit score
- complete generated fix plan
- generated files when `--apply` is used
- before score and planned-after score

The planned-after score comes from the existing fixer estimate. A live post-deploy score should be measured with another `geosition run domain.com` after the site is published.

## Seeded Demo

`geosition demo` installs a fictional demo workspace for `example.com`:

- benchmark prompts
- seeded AI answer snapshots
- local benchmark JSON
- one-page AI citation report
- workspace metadata

This lets a buyer see the full workflow without API keys or provider accounts.

## Pricing Positioning

Keep the source-available core free:

- local audits
- local fix generation
- local reports
- manual benchmark imports
- transparent score rubric

Charge for hosted and operational workflow:

- recurring monitoring
- scheduled benchmark runs
- managed answer collection
- team workspaces
- client report history
- alerts when citation share changes
- artifact storage and client portals

The source-available core proves the method. The hosted product sells time, reliability, collaboration, and recurring evidence.

## Score Transparency

GEOSITION should always show how scores are calculated. The current GEO score is 100 points:

| Category | Points |
| --- | ---: |
| Robots.txt | 18 |
| llms.txt | 18 |
| Schema JSON-LD | 16 |
| Meta tags | 14 |
| Content | 12 |
| Signals | 6 |
| AI discovery | 6 |
| Brand and entity | 10 |

Score bands:

| Band | Range |
| --- | ---: |
| Excellent | 86-100 |
| Good | 68-85 |
| Foundation | 36-67 |
| Critical | 0-35 |

The full evidence trail is stored in the JSON artifact next to each HTML report. The full rubric lives in [scoring-rubric.md](scoring-rubric.md).
