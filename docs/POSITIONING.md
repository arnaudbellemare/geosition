# GEOSITION Platform positioning

## Thesis

The web was built for humans. Clicks and eyeballs shaped discovery and monetization — and unlocked unprecedented knowledge, commerce, and connection.

The primary user is changing. **AI agents** are taking over information work that search used to route to human attention, without replacing the **revenue** that sustained publishers and experts.

**GEOSITION Platform exists to close that gap.**

## Current marketing target

Lead with the **source-available GEOSITION CLI** as the launch-ready product. The CLI, audit/fix loop, benchmark command, local reports, and self-hosted workflow are close enough to market as an source-available developer/operator toolkit.

Position the hosted SaaS as **early access / roadmap**, not the primary promise yet. Before it can be sold as a production hosted platform, it still needs hardened auth and email flows, billing, scheduled runs, production storage operations, and clearer managed-service reliability guarantees.

## Three pillars (product mapping)

| Pillar | Promise | What we ship today | Roadmap |
|--------|---------|-------------------|---------|
| **Distribution** | Reach agents at scale | Multi-provider collection (API + browser), task taxonomy, geo-aeo-tracker bridge | Scheduled runs, agent marketplace integrations |
| **Monetization** | Paid when content matters | Citation share %, position, competitor matrix (evidence for licensing) | Shapley-style attribution payouts, partner settlement |
| **Data** | Prove worth in negotiations | GEO benchmark score, unique vs commodity, HTML/CSV reports, audit score | Live dashboard trends, Fil One artifact archive |

## How it works (customer journey)

1. **Join** — Account email → workspace → verify website ownership (DNS/HTTPS).
2. **Agents retrieve** — Fixed prompt set → collect answers → classify tasks → extract citations & competitors.
3. **Get paid & get insights** — Benchmark run + site audit + exportable report (monetization rails TBD).

## Audiences

- **Independent creators** — Niche authority can win per-task citation share vs commodity big publishers.
- **Content & data providers** — Any verified domain (e.g. gestionvelora.com).
- **Agencies / operators** — CLI + API + platform for client delivery.

## Relation to “Index”-style products

GEOSITION Platform is the **open, self-hostable** stack for the GEOSITION CLI, API, and dashboard:

- You own data (`data/`, Supabase, Fil One blobs).
- You run collection and benchmark locally or in your cloud.
- Negotiation reports are first-class outputs, not a black box.

Commercial settlement layers (automatic micropayments, agent network distribution) are **optional extensions** on top of measured citation contribution.

## Demo examples

The fictional demo workspace and benchmark fixtures are in `examples/demo/`.
