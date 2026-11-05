---
name: brand-answer-monitoring
description: Track how AI assistants describe a brand over time and catch wrong, outdated, or damaging claims. Uses geo monitor/track/snapshots to diff runs week over week and drafts the correction plan when answers drift. Use for ongoing monitoring after an audit, after pricing/service changes, or after negative press.
---

# Brand Answer Monitoring

Repeatable monitoring routine: fixed prompt panel → scheduled runs → diff against the last run → correction plan for drift and misinformation.

## Workflow

### 1. Fixed brand panel (create once, never regenerate)

Prompts of the form: "what is [brand]", "[brand] pricing/fees", "[brand] vs [competitor]", "is [brand] good for [use case]", "[brand] alternatives", "avis sur [brand]". Store in `runs/brand-panel-<client>.md`. Bilingual clients get fr + en versions of each prompt.

### 2. Scheduled run

```bash
geo monitor --domain client-site.com --save-history
geo track --url https://client-site.com --report
geo benchmark schedule client-site.com --frequency weekly --competitor competitor.com
geo benchmark due            # see which domains are due
```

Archive each collected answer:

```bash
geo snapshots --query "PROMPT" --provider OpenAI --model gpt-x --answer-file ans.txt
```

### 3. Diff against previous run

```bash
geo snapshots --from PREV-DATE --to TODAY --format json
geo history --url https://client-site.com --limit 12   # saved GEO score trend
```

Flag: new claims, dropped mentions, sentiment shifts, factual errors (old pricing, killed services, competitor positioning attached to the brand's name).

### 4. Trace and correct

For each wrong claim, trace the likely source (stale third-party article, outdated review, old docs page), then draft:

- Publisher correction request (in the publication's language)
- An owned-content fix: FAQ entry stating the correct fact explicitly, or a changelog-style page AI crawlers pick up — hand to `content-aeo-optimizer` for extraction-ready formatting
- Schema refresh if entity data is stale: `geo schema --type organization ... --inject`

### 5. Deliverable

Weekly diff report appended to `runs/brand-monitor-<client>.md`: new/changed/dropped claims table, error log with likely source per claim, correction actions with owners.

## Rules

- The panel is frozen — additions go in a dated "extended" section so historical diffs stay valid.
- Never dispute subjective negative opinions with publishers; only factual errors.
- Rivalry drift belongs in `geo rivalry --save-history` (see `rivalry-history.db`), not in this report.
