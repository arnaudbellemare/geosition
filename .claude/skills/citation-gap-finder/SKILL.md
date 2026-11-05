---
name: citation-gap-finder
description: Find the exact pages AI assistants cite for a category's questions and identify which ones the client can get into. Clusters cited sources from geo snapshots, scores attainability, and outputs an outreach/content plan. Use after an AI visibility audit shows competitors out-citing the client, or when planning content/PR priorities.
---

# Citation Source Gap Finder

AI answers are built from a small set of sources — review sites, listicles, community threads, directories. This skill extracts which sources get cited for the client's category and which are worth pursuing.

## Workflow

### 1. Pull cited sources from archived answers

```bash
geo snapshots --from 2026-01-01 --format json --output snapshots.json
geo snapshots --quality --snapshot-id N --target-domain client-site.com
```

If no snapshots exist yet, run the `ai-visibility-audit` skill first (step 3 archives answers).

### 2. Extract and cluster

From the snapshot citations, extract every cited URL and cluster by type:

| Cluster | Examples (Montreal property mgmt context) | Typical tactic |
|---|---|---|
| Review platform | Google Business Profile, Yelp, Bureau en Gros listings | Review volume + profile completeness |
| Listicle / editorial | "Top 10 gestionnaires immobiliers Montréal" blog posts | Pitch an inclusion/update |
| Community | Reddit r/montrealhousing, condo-board forums | Genuine participation, no astroturf |
| Directory | CORPIQ, APQ, chambers of commerce | Get listed / fix NAP data |
| Owned | Client + competitor sites | Publish a page matching the citation pattern |

Count citation frequency per URL and per cluster — report citation share (e.g. "62% of citations come from 9 URLs").

### 3. Score attainability

For each top source: **High** (listable/pitchable this month) · **Medium** (needs content or review volume) · **Low** (Wikipedia-class, ignore). Recommended tactic per source, one line each.

### 4. Deliverables

- Ranked table: URL · cluster · citation count · attainability · tactic
- Draft outreach emails for pitchable listicles (fr or en to match the publication)
- Content briefs for owned-content plays — hand these to the `content-aeo-optimizer` or `programmatic-page-builder` skill
- Save to `plans/citation-gaps-<client>-<date>.md`

## Rules

- Only recommend community tactics that follow platform rules — flag, never fake, engagement.
- Verify each cited URL still exists before recommending outreach (fetch it).
- Cross-check gaps against `geo benchmark report` output when available so the plan ties to measured citation share.
