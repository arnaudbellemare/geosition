# AI commerce readiness: platform and managed service

Status: single-page and bounded site audits implemented, including optional restricted JavaScript rendering; remaining phases are proposed. Updated 2026-11-13.

## Mission and boundaries

Help a business assess, prepare, connect and maintain its customer journey for AI-assisted discovery and commerce. Start with evidence, not a promise of ranking, traffic, provider approval or sales. The initial buyer is a small business selling physical products or accepting service enquiries. Pilot with an actual merchant and a service business only after obtaining their participation.

The audit can inspect one page or discover bounded same-origin pages via links and sitemaps. Optional rendering uses pre-fetched same-origin scripts with browser network requests blocked. Reports expose page coverage, failed and skipped URLs, rendering limitations, Product and Service JSON-LD, heuristic catalog cards, journey signals and unknowns. Discovery may miss pages; card signals are not a verified catalog. It is not a feed validator, verified provider-browser access check, transaction test or eligibility decision. It does not change the existing GEO score. Run `geo commerce-audit --url https://example.com/product --format json` or omit `--format json` for text. Product fields record presence only, not semantic correctness or current offers; audit representative product and service URLs separately.

## Delivery sequence and gates

| Phase | Work | Acceptance gate |
| --- | --- | --- |
| 1. Validate the audit | Review reports with owners of a physical-goods business and a service business. Add an operator checklist for inaccessible, JavaScript-only and misleading pages. Collect permission before storing reports. | Two reviewed reports identify specific, correct, actionable findings; unknowns remain visible. |
| 2. Managed assessment | Define an intake: representative URLs, business model, jurisdictions, ownership, catalog source, customer journey and consent. Deliver a human-reviewed fix sheet with evidence, owner, priority and estimate. | A complete audit can be delivered reproducibly with documented labor and corrections. |
| 3. Managed setup | Offer a fixed-scope package for documented site and catalog fixes; define exclusions and obtain the client's authorization for each external account or production change. Hand off business-profile and provider-approval steps to the account owner. | Before/after evidence, client sign-off and explicit unresolved dependencies; no guarantee of provider acceptance. |
| 4. Repeat audit and monitoring | Persist timestamped, versioned results with per-client access controls and retention; schedule read-only rechecks and report meaningful changes. | Test detection of a known change and recovery; distinguish fetch failure from a confirmed regression. |
| 5. First connector | Select one platform after reviewing actual paid-audit demand. Map client-authorized catalog data to the current provider schema, validate samples, track provenance and freshness, and provide a reviewable export. | A consented pilot validates mapping, omissions, inventory changes and provider feedback. Submission remains owner-controlled until an authorized integration exists. |
| 6. Journeys and actions | Based on demand, add supported booking, enquiry or cart integrations with explicit customer confirmation and business-controlled validation. Use test accounts or approved non-destructive checks for synthetic monitoring. | A sandbox or consented test demonstrates the entire supported journey and recovery; no real booking, enquiry or payment in routine checks. |
| 7. Self-service | Add workspace, access control, billing and a dashboard only when managed pilots demonstrate repeat demand and support economics. | Multiple unrelated customers complete onboarding and understand evidence and unknowns without operator intervention. |

## Service offer and operating model

- **Assessment:** fixed-scope paid report covering agreed pages and checks; record operator time and customer corrections.
- **Setup:** a separately scoped fixed-price package for a known platform and defined changes. Exclude unsupported custom integrations; quote them separately or decline.
- **Monitoring:** recurring read-only checks with an agreed cadence, escalation channel, retention period and support boundary. A failed fetch is an investigation signal, not proof of an outage.
- **Handoff:** client owns provider accounts, approvals, content, pricing and customer transactions. Track authorizations, evidence, open items and rollback steps for each change.
- Pricing, acquisition cost, target margins, customer segments and service levels are hypotheses until paid pilots supply evidence. Track audit hours, fixes accepted, repeat demand, connector frequency and gross margin; do not infer AI-driven revenue without attributable data.

## Architecture decisions to validate

Extend the existing Python audit core and secure fetch stack before adding a separate crawler. Store source URL, timestamp, rule version, observation, confidence and evidence provenance for every finding; distinguish observed, inferred, unknown and not applicable. Introduce a normalized business/catalog/service/journey model incrementally from real examples, preserving platform-specific fields and unknowns. Keep provider guidance versioned and linked; configuration can hold metadata while complex checks remain code. Do not build broad adapters, an autonomous fixer, dashboard or attribution model before pilot evidence justifies them.

Authenticated connectors require customer-scoped authorization, secret storage, least-privilege access, revocation and deletion procedures. Define privacy and retention for collected page evidence before enabling multi-tenant storage. Revalidate URLs through the existing protected HTTP stack, including redirects. Treat captured HTML and contact details as customer data.

## Source checks and open decisions

- [Product feeds](https://developers.openai.com/commerce/guides/submit-product-feeds): check current feed schema, onboarding, refresh and delivery requirements before implementing a connector.
- [Browser access](https://developers.openai.com/commerce/guides/enable-browser-access): verify access using the provider's current guidance; a spoofed user agent is not proof.
- [Commerce plugins](https://developers.openai.com/commerce/guides/build-a-plugin) and [plugin checkout](https://developers.openai.com/plugins/build/monetization): recheck supported actions, eligibility and checkout availability before a pilot.
- [Existing GEOSITION scoring rubric](scoring-rubric.md): keep the commerce report separate until a reviewed, evidence-based rubric is adopted.

Unknowns requiring customer evidence: which business platforms dominate, willingness to pay, provider access for each merchant and geography, effective monitoring cadence, and what data clients authorize GEOSITION to retain. Revisit this plan when pilot findings or provider rules change; do not claim unimplemented phases are available.
