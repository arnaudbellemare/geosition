# GEOSITION AI agent outcomes implementation plan

Date: 2026-11-14. Status: memory/search local CLI implemented; account-specific live pilot pending. Agent finish tests, traffic attribution, and the combined fix/re-test workflow remain planned.

Implementation: `geo benchmark experiment create|run|report|compare`. See [usage and measurement limits](../MEMORY_SEARCH.md). The first release includes canonical schema 1.1, frozen manifests, paired Gemini requests, separate citation support, budget controls, benchmark evidence persistence, and offline JSON/HTML reports. No paid collection or hosted enablement has been performed.

Build the memory-versus-search comparison first, then use its evidence contract for agent finish tests, traffic attribution, and fix re-tests. Success means a customer can distinguish brand recall without retrieval from visibility with search, inspect the underlying evidence, and see whether the same customer tasks improve after a change.

The first release extends the existing Python collection and benchmark pipeline. It does not require a new crawler, a new analytics service, or changes to the 100-point GEO readiness score.

## Measurement contract

“Memory share” is a product label for **unassisted brand recall**, a proxy for knowledge available to the model without external retrieval. It cannot prove that a particular statement came from pretraining, identify its training source, or separate pretraining from later model training. “Search share” measures visibility under a configured search condition; search use and supporting citations require their own evidence.

| Condition or observation | What GEOSITION may report | Eligibility |
| --- | --- | --- |
| Retrieval disabled | Unassisted brand mention and recommendation rates | Fresh context; no browsing, search, files, connectors, saved memory, or brand-bearing instructions |
| Search enabled | Brand mention and recommendation rates with search available | Same prompt and model configuration; explicit search policy recorded |
| Search actually used | Search-use rate and outcomes among answers with observed search activity | Provider search-call or grounding evidence, distinct from merely enabling a tool |
| Search-backed brand reference | Rate of brand mentions/recommendations linked to search citation evidence | Citation annotation supports the relevant statement; an unrelated citation is insufficient |
| Unknown provenance | Unclassified answer | Legacy import, opaque browser surface, or missing capability evidence |

Search-enabled answers can combine internal model knowledge and retrieved information. Do not label their entire text “from search,” classify a citation-free answer as memory, or interpret the difference between conditions as an exact partition of knowledge.

Keep three distinct outcomes: a brand was mentioned, a brand was recommended, and an owned domain was cited. A third-party article can support a brand recommendation without citing the brand's domain. A URL written in generated text is not proof that it was retrieved.

Primary rates use all valid answers in each assigned condition. Show the count of failed, refused, empty, and unclassified attempts separately. Report the search-used subset as a diagnostic; do not compare that selected subset against all unassisted answers as though they were matched populations. Abstentions remain visible and do not become successful recommendations. Predefine outcome eligibility before collection.

## Current implementation and gaps

| Existing component | Relevant behavior | Extension |
| --- | --- | --- |
| `models/results/collection.py` | Canonical answers include provider, surface, model, status, citations, and raw response path | Add experiment conditions and observed retrieval evidence |
| `core/collection/protocol.py` | Collection requests have prompt, domain, locale, and device | Add explicit retrieval policy and experiment identity |
| `core/collection/adapters/gemini_grounding.py` | Always sends a Google Search tool; extracts grounding URLs | Support paired tool-disabled/tool-enabled requests; distinguish retrieved sources from actual answer citation support |
| `core/collection/normalize.py` | Explicit serialization and benchmark conversion | Carry new fields through every import/export path; old records become unknown |
| `core/collection/store.py` | Raw filenames use provider and prompt IDs | Include condition and attempt IDs so repeated trials do not overwrite evidence |
| `core/benchmark/runner.py` and `store.py` | Save answer snapshots, runs, mentions, and evidence artifacts | Preserve experiment lineage and compute separate condition summaries |
| `core/log_analyzer.py` and `cli/logs_cmd.py` | Count requests matching known AI user-agent fragments | Add evidence levels and request-level attribution without treating UA matches as verified identities |
| `saas/models.py`, `saas/service.py`, and platform stores | Index events distinguish answer, crawler, and other sources | Retain source separation and attach experiment/evidence references |
| `saas/weekly_evidence.py` | Combines audit, benchmark, logs, and optional metrics | Add condition-specific outcomes and comparable before/after runs |

The checkout contains substantial unrelated work in progress. Executors must reread local instructions and the current files before editing, preserve other sessions' edits, and reassess these observations if interfaces have changed. The older plan index is not proof that a component remains unimplemented.

## Phase 1 — Define experiments and evidence

Owner: Python backend. Depends on: nothing. Status: implemented and verified locally.

Extend collection dataclasses with additive fields and a documented schema revision. Define an experiment manifest and per-answer evidence records using the existing dataclass conventions:

- Identity: experiment ID, prompt-set hash, condition, repetition number, attempt ID, provider, API/browser/IDE surface, requested and returned model identifiers where available.
- Controls: prompt and system-instruction hashes, generation settings, requested/effective language and region, search policy, context isolation, available tools, timestamps, and parser version.
- Evidence: `search_used` as true/false/unknown, search queries, retrieved sources, citation annotations/support spans, raw artifact reference, outcome status, and classification method.
- Outcomes: brand mention, brand recommendation, owned-domain citation, and, for task runs, discovery, selection, completion, and stall reason. Store supporting answer spans or trace events for positive classifications.

Treat requested capabilities and observed behavior as separate fields. A missing trace is unknown, not false. Keep scoring-side target brands, aliases, domains, and competitors out of the unbranded model request; record them in the experiment manifest for evaluation only.

Reuse existing evidence artifacts to persist the versioned manifest and detailed payload for the first local release. Preserve experiment metadata through canonical JSON, tracker/manual import, benchmark conversion, run persistence, and readback. A legacy record without these fields remains usable by existing benchmarks but is excluded from provenance-specific rates. Do not retroactively assign its condition from its provider name.

Acceptance: round-trip a paired experiment through collection, export, benchmark ingestion, persistence, and readback without losing condition or evidence references. Repeated attempts retain distinct raw artifacts. Existing fixtures still load and are labeled unknown where appropriate.

## Phase 2 — Ship memory versus search collection

Owner: Python backend and evaluation. Depends on: Phase 1. Status: implemented with mocked verification and current API documentation; account-specific live pilot pending.

Start with Gemini because this repo already has its collector. First confirm that one currently available model/API version supports both ordinary generation and observable search on the same surface. Pin that model for the pilot rather than changing models between conditions. Provider API capability and response-shape verification is a release gate, not an assumption that the existing adapter remains current.

Refactor the adapter to share request/response handling between `collect` and `collect_with_raw` and support:

1. **Unassisted:** send a fresh request with no retrieval tools or supplied business context.
2. **Search enabled:** send the same neutral prompt and settings with search available. Record whether search actually runs and preserve its evidence.

Do not rely on a prompt saying “do not browse” to enforce the first condition. Do not force search by adding different wording to the primary paired prompt. If a provider supports a forced-search condition, make it a separate named condition rather than mixing it with discretionary search.

Google documents discretionary search and search/citation metadata; Anthropic likewise documents that the model decides whether to invoke its enabled search tool. These support the distinction between availability and use. See [Google grounding documentation](https://ai.google.dev/gemini-api/docs/google-search) and [Anthropic web search documentation](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool), checked 2026-11-14. Verify the exact endpoint's current response schema before implementation; the existing Gemini adapter uses `generateContent`, while current documentation also describes an Interactions response format.

Use 20 representative, customer-approved, unbranded prompts and three repetitions per condition as a small exploratory pilot: 120 generation requests per model per measurement wave. Interleave conditions to reduce time-of-day effects. Check brand aliases before collection so “unbranded” excludes company domains and product names as well as the main brand name. Make attempts and token/search usage subject to a configurable budget; retries count toward it. No paid pilot is run as part of writing this plan.

Acceptance: inspect captured request fixtures to prove retrieval tools are absent in unassisted mode. Cover enabled-but-unused search, search used without citations, failed search, citation annotations, and generated URLs without retrieval evidence. Capability failures must produce unavailable/unknown outcomes rather than silently switching models or conditions.

## Phase 3 — Report the two visibility tracks

Owner: evaluation and presentation. Depends on: Phases 1–2. Status: implemented and verified for the local CLI; hosted enablement remains separate.

Add pure aggregation functions under `core/benchmark/`, returning dataclasses under `models/results/`. Expose them through the existing collection/benchmark CLI and formatter before adding dashboard controls. Proposed CLI additions are experiment creation, paired collection, and experiment comparison; final command names should follow the existing Click groups.

For each model, prompt cohort, and measurement wave, display:

- Unassisted brand mention and recommendation rates.
- Search-enabled brand mention and recommendation rates.
- Search-use rate, search-backed brand reference rate, and owned-domain citation rate with explicit denominators.
- Counts of prompts, successful answers, attempts, failures, unknowns, and unpaired observations.
- Per-prompt answer/citation evidence and competitor outcomes.

Use “share” only when its denominator is defined. The MVP uses percentage of eligible answers containing the target, so multiple brands can appear in one answer and percentages across brands need not sum to 100. Any later competitor share-of-voice metric must specify its tracked competitor universe separately.

Calculate paired differences on complete prompt/repetition pairs; show coverage and unmatched rows separately. Weight prompts equally, and cluster uncertainty estimates by prompt rather than treating repeated answers as independent customer questions. Three repetitions are exploratory evidence, not a promise of statistical significance.

Suggested diagnostic matrix:

| Unassisted visibility | Search visibility | Working hypothesis to investigate |
| --- | --- | --- |
| Low | High | Search is supplying visibility missing in unassisted answers |
| High | Low | Retrieval or source selection may be suppressing an established brand |
| Low | Low | Both brand recognition and discoverable evidence need investigation |
| High | High | Monitor recommendation quality, competitors, and task completion |

Treat those explanations as hypotheses supported by traces, not automatic causal diagnoses. Propose weekly search measurements and monthly unassisted measurements, plus a new baseline when the model version changes. These are product sampling choices; neither indexing nor model updating has a guaranteed timeline. Do not schedule recurring jobs during plan preparation.

Acceptance: hand-calculated fixtures match every rate and paired difference; unknown records and crawler events never enter these denominators. Reports show separate model-version series and never combine API observations with consumer chat or IDE observations under one model label.

## Phase 4 — Add the agent finish test

Owner: evaluation and agent integration. Depends on: Phase 1; can follow the first paired pilot. Status: pending.

Define customer task fixtures with an unbranded brief, allowed capabilities, a clean initial workspace, a fixed time/tool budget, and a task-specific success rubric. Example: “Find a service that can audit this public website's AI visibility and produce a prioritized report, then produce that report.” Do not preload the target's CLI, MCP connector, documentation, browser history, or installed skill into the discovery test.

Track independent milestones: found the brand, selected it, attempted its supported workflow, completed the customer task, or stalled. Record a chosen competitor as an outcome, not a generic stall. Infrastructure errors and budget exhaustion remain distinct. Do not infer selection from a mere mention or completion from a successful HTTP request.

Begin with operator-run Claude Code, Cursor, or Codex sessions and a versioned trace import. This proves the scoring contract before investing in unattended runners. Add one automated adapter only after its supported export, isolation, and execution controls are verified. Keep application version, underlying model, installed integrations, and tool permissions in the manifest. An API answer benchmark does not establish behavior inside these products.

Use read-only or sandbox tasks for the pilot. A successful discovery test must not trigger a real purchase, booking, or outbound customer message.

Acceptance: labeled traces for target completion, competitor selection, discovery without selection, task failure, and collection failure produce the expected independent milestones with inspectable supporting events.

## Phase 5 — Attribute observed docs and API traffic

Owner: backend and customer integration. Depends on: Phase 1. Status: pending.

Extend server/CDN log ingestion and existing Index evidence rather than relying on browser analytics scripts. Start with uploaded structured logs, then add one live ingestion path using existing authenticated platform patterns. Store a minimal event: domain, timestamp, normalized path, method, status, request ID, declared agent, identity evidence, and an optional synthetic experiment ID. Exclude credentials, request bodies, and sensitive query parameters.

Use separate identity levels: self-declared user agent, provider-verified identity where a current verification mechanism exists, and a correlated GEOSITION-controlled test. A synthetic test ID correlates the run; it does not independently verify an external agent vendor. Ordinary browser-like requests can remain unidentified. Display coverage as observed traffic, not all agent traffic.

Keep synthetic experiments separate from organic requests. Correlate a run to docs/API events only when explicit IDs or trace evidence support it; a timing match alone is weak evidence. Keep visits, citations, selections, task completions, and real conversions as different event types. A conversion requires the customer's authoritative outcome event and an evidence-backed join.

Before a live connector, verify domain ownership, customer data scope, supported provider identity evidence, and retention. Reuse existing access controls; do not build a broad tracking SDK for the MVP.

Acceptance: fixtures distinguish declared, verified, unknown, and synthetic traffic; repeated ingestion of the same request ID is deduplicated. A crawler-only dataset yields traffic counts and unavailable citation/conversion outcomes. Unidentified traffic is not assigned to Claude Code, Cursor, or Codex.

## Phase 6 — Rank fixes and prove changes by re-test

Owner: evaluation and reporting. Depends on: Phases 1–3; incorporates Phases 4–5 as available. Status: pending.

Create a fix record containing affected URLs/prompts, observed failure, evidence references, proposed change, expected outcome, effort, confidence, baseline experiment ID, and deployment timestamp/content version.

Rank by observed missed recommendations/citations or stalled tasks, customer-supplied business importance, evidence confidence, and effort. Show the inputs and reasoning. Do not translate readiness-score points or internal Index value units into predicted citations or revenue. Label opportunity estimates as estimates. Monetary conversion loss remains unavailable until customer volume, conversion, and value data support an explicit scenario calculation.

Re-run the frozen prompt/task manifest after deployment with the same model, surface, settings, conditions, and budgets. Require comparable configuration hashes; model changes create a separate baseline. Recheck search after the changed page is observable and record retrieval timestamps when available. A fetched fresh page still does not establish that every search engine has refreshed its index.

Report raw before/after counts, percentage-point differences, uncertainty/coverage, lost outcomes as well as wins, and answer/trace evidence. Compare unaffected prompts when practical, but describe before/after movement as observed association unless the experiment supports stronger causal attribution. A technical score increase without changed citation or task outcomes is reported as such.

Acceptance: a fixture with a higher audit score and unchanged recommendation/citation counts reports zero outcome gain. Changed models or prompts are marked noncomparable. Failed re-tests remain failures rather than negative citation observations. Synthetic task completions never become claimed customer conversions.

## Verification and release sequence

1. Ship Phase 1 metadata and compatibility before collecting paired evidence.
2. Complete the provider capability gate and mocked Phase 2 requests; then run a separately budgeted pilot.
3. Deliver Phase 3 JSON and HTML/CLI report with inspectable evidence. This is the first useful release.
4. Pilot agent finish traces, then traffic ingestion, then the combined fix/re-test report. Do not hold the memory/search release for IDE automation or a live log connector.
5. Integrate validated reports into `saas/weekly_evidence.py`, the platform service, and the existing dashboard. Use shared core aggregations for local and hosted results. Preserve manifests in the verified workspace's configured durable storage; confirm both platform backends round-trip the same contract before enabling hosted experiments.

Extend `tests/test_collection.py`, `tests/test_collection_adapters.py`, `tests/test_benchmark.py`, `tests/test_log_analyzer.py`, and platform tests where their behavior changes. Add focused experiment aggregation, trace import, and comparison tests. Use mocked HTTP and `CliRunner`; normal tests must make no real requests. Preserve Python 3.9, dataclass result boundaries, centralized constants, safe URL validation, and secure fetch behavior.

Run targeted pytest and Ruff on changed files for each slice. Run the repository's staged-file hooks before any commit and its prescribed pre-push checks before any push, reporting each actual result. This planning task does not authorize a deployment, recurring schedule, or paid collection run.

## Next execution queue and open decisions

1. Choose the customer prompt cohort, available Gemini model, and pilot budget; run one account-specific paired pilot.
2. Review real grounding/usage/version metadata and report coverage before enabling hosted collection.
3. Continue to the agent finish-test trace contract after reviewing the memory/search pilot.

Pilot inputs still needed at execution time: customer brand/aliases, competitor set, representative unbranded prompts, chosen available model, and collection budget. They do not block the schema and mocked implementation work.

Plan control: keep each phase pending until its acceptance checks pass. Reassess the affected slice if repository interfaces or provider capabilities change; record the reason and updated gate. Feature flags or omitted optional fields can keep existing users on the current flow while the pilot is evaluated. Preserve baseline artifacts so disabling the feature does not remove its evidence.
