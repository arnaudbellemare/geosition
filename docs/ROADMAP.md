---
title: "Roadmap"
description: "Release cadence and upcoming milestones for GEOSITION. Focused waves, quality over velocity."
date: 2026-04-28
tags: [roadmap, releases, versioning]
---

# Roadmap

> geosition follows a deliberate release cadence. We ship in focused waves — each one validated, tested, and stable — rather than pushing frequent incremental patches. Quality over velocity.

## Current Direction

The project is entering its next phase of evolution. Focus areas for the upcoming cycle include:

- Deeper structural analysis of how content surfaces in AI-generated responses
- Expanded signal coverage across emerging retrieval and citation patterns
- Scoring model refinements informed by ongoing research validation
- Tighter integration between audit, remediation, and monitoring workflows
- Continued hardening of the skill system and plugin architecture

Some of these themes will span multiple releases. Specific scope may shift as research findings and community feedback inform priorities.

## Release Calendar

| Version | Window | Codename | Theme |
|---------|--------|----------|-------|
| v4.10.0 | Late May / Early Jun 2026 | **Veil** | Signal architecture refinement |
| v4.11.0 | Mid / Late Jul 2026 | **Static** | Expanded retrieval surface analysis |
| v4.12.0 | Sep 2026 | **Ledger** | Scoring model recalibration |
| v4.13.0 | Nov 2026 | **Quiet Glass** | Structural pattern recognition |
| v4.14.0-rc1 | Jan 2027 | **Threshold** | Pre-release validation cycle |
| v4.14.0-rc2 / v4.15.0 | Mar 2027 | **Pale Signal** | Stabilization and edge resolution |
| v5.0.0 | May 2027 | **Black Archive** | Next-generation audit framework |

Release windows are estimates. Dates may shift based on validation outcomes and testing discipline.

## Release Philosophy

Each release is a curated wave, not a deadline. We hold releases until they meet our quality bar:

- Full test coverage for new capabilities
- No regressions in existing audit checks
- Security review for any new network-facing surface
- Documentation updated before the tag is cut

This means some windows may be quiet. That silence is intentional.

## What's Ahead

The v4.10–v4.13 cycle focuses on deepening the analytical foundation. New signal categories, refined scoring weights, and improved detection heuristics are under active research. Not all of this work will be visible in public commits — some validation happens offline before it reaches the codebase.

The v4.14 release candidates mark the transition toward v5.0, which represents a broader architectural evolution. More details will surface as the earlier releases stabilize.

## What This Roadmap Does Not Cover

- Internal module-level implementation plans
- Exact detector or check lists per release
- Configuration migration specifics
- Experimental features under active research

For the skill system roadmap (internal skill catalog evolution), see [docs/skill-roadmap.md](skill-roadmap.md).

---

*This roadmap reflects current planning as of April 2026. Items may evolve as research and validation continue.*
