# AI commerce platform: implementation review

Reviewed 2026-11-13 against the Partner Playbook and current GEOSITION commerce modules. This is a technical review of local capabilities, not proof of partner eligibility or production readiness.

## Fit and boundary

GEOSITION remains a reasonable home for the cross-business readiness and managed-service layer: the project inventory identifies it as an AI-search website toolkit, and it already has site-audit and reporting code. Company OS could later provide operational workflows; the current code does not establish that integration. Mom’s Art Shop and Gestion Velora are useful retail and service test cases, not proof that the solution generalizes to every business.

## What is implemented

- Bounded site audit of discoverable same-origin pages with optional restricted JavaScript rendering; heuristic catalog and journey signals, service/Product structured data observations, and coverage limits.
- Evidence-linked recommendations and reviewable Markdown reports.
- Local product and service preparation drafts. The feed CSV is explicitly an operator worksheet; the internal completeness checks are not a provider schema validator.
- Read-only recurring monitoring with local snapshot comparison and optional contact-page fetches. It does not execute a purchase, submit an enquiry, or verify ChatGPT browser access.

## Material gaps to resolve before selling the complete managed service

1. **Feed connection and validation:** no provider-compatible feed generator, schema validator, upload, identity workflow, inventory synchronization or confirmed merchant onboarding. OpenAI's [feed guide](https://developers.openai.com/commerce/guides/submit-product-feeds) specifies merchant onboarding and current schema requirements. The present product-preparation input only extracts catalog card signals; a site whose products are visible solely as Product JSON-LD cannot yet produce drafts from those records.
2. **Browser access:** the restricted local renderer is an observation tool. It does not test a verified ChatGPT browser or the merchant's CDN policy. Implement a documented verification and evidence workflow using the current [browser-access guide](https://developers.openai.com/commerce/guides/enable-browser-access).
3. **Real customer journeys:** visible controls and successful GETs do not prove cart, booking, payment or enquiry completion. A consented sandbox and explicit merchant confirmation are needed to test those workflows end to end. Plugins require a real backend that owns availability, transaction state and confirmation; see the [plugin guide](https://developers.openai.com/commerce/guides/build-a-plugin).
4. **Accounts, payments and business profile:** no ChatGPT Wallet, Sign in with ChatGPT, Business Hub claim, or account-linking implementation exists in these modules. Eligibility, geography and merchant permissions still need verification.
5. **Operational maturity:** the CLI monitor needs an external scheduler or a running watch process. No hosted multi-tenant scheduling, alert delivery, customer authorization, retention policy, service-level agreement or production deployment is provided. Rendering can omit API and third-party content, and large site audits may be incomplete.

## Next useful validation

Run a paid or explicitly consented pilot with a business that has a real, authorized catalog or service system. Verify business identity and platform eligibility, obtain sample authoritative data, implement one provider/platform adapter, validate a sample against the current schema, and demonstrate a sandbox journey. Track owner-review time, data-quality issues, false positives, actual coverage and support cost. Do not promise placement or sales lift from the audit score.
