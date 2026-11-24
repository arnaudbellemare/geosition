"""Derive reviewable commerce recommendations from observed site evidence."""

from __future__ import annotations


def _rec(key, priority, title, evidence, action, verification, urls, source=""):
    return {
        "id": key,
        "priority": priority,
        "title": title,
        "evidence": evidence,
        "action": action,
        "verification": verification,
        "evidence_urls": urls,
        "guidance_url": source,
    }


def build_site_recommendations(report: dict) -> list[dict]:
    """Recommend next steps; unknowns are never presented as failed checks."""
    pages = report.get("pages", [])
    coverage = report.get("coverage", {})
    recommendations = []
    catalog_pages = [p for p in pages if p.get("catalog_signals") and not p.get("products")]
    if catalog_pages:
        count = sum(len(p["catalog_signals"]) for p in catalog_pages)
        recommendations.append(
            _rec(
                "catalog-structured-data",
                "high",
                "Make the product catalog machine-readable",
                f"The audit observed {count} product-like cards on {len(catalog_pages)} page(s) without Product JSON-LD on those pages. Cards are heuristic signals.",
                "Review the real catalog and publish accurate Product and Offer structured data for each applicable item; include name, description, image, price, currency and availability where available.",
                "Re-audit representative product pages and compare structured values with the live catalog; review feed eligibility separately.",
                [p["url"] for p in catalog_pages],
                "https://developers.google.com/search/docs/appearance/structured-data/product",
            )
        )
    incomplete_products = []
    for page in pages:
        for product in page.get("products", []):
            missing = [key for key, value in product.get("fields", {}).items() if not value]
            if missing:
                incomplete_products.append((page["url"], product.get("name", "Unnamed product"), missing))
    if incomplete_products:
        fields = sorted({field for _, _, missing in incomplete_products for field in missing})
        recommendations.append(
            _rec(
                "complete-product-fields",
                "medium",
                "Review missing product fields",
                f"{len(incomplete_products)} observed Product record(s) omit one or more checked fields: {', '.join(fields)}. Some fields may not apply.",
                "Add applicable missing values to the relevant Product and Offer records, using current source-of-truth data.",
                "Re-audit the affected pages and check the fields against the real catalog.",
                list(dict.fromkeys(url for url, _, _ in incomplete_products)),
                "https://developers.openai.com/commerce/guides/submit-product-feeds",
            )
        )
    product_pages = [p for p in pages if p.get("catalog_signals") or p.get("products")]
    if product_pages:
        recommendations.append(
            _rec(
                "review-product-feed",
                "medium",
                "Review product feed readiness",
                f"Product-like cards or structured product records were observed on {len(product_pages)} page(s). Feed submission and eligibility were not checked.",
                "Confirm which products the business sells, verify catalog data and rights, and review current provider onboarding and feed requirements with the account owner.",
                "Validate a sample feed against the current provider schema and record the owner's onboarding status; do not assume acceptance.",
                [p["url"] for p in product_pages[:3]],
                "https://developers.openai.com/commerce/guides/submit-product-feeds",
            )
        )
    if not coverage.get("complete", False):
        recommendations.append(
            _rec(
                "complete-coverage",
                "high",
                "Review the pages the scan did not reach",
                f"The scan audited {coverage.get('pages_audited', len(pages))} pages; {coverage.get('pending', 0)} discovered URLs remained pending, with {len(report.get('failures', []))} failed and {len(report.get('skipped', []))} skipped.",
                "Re-run with a suitable page limit or audit representative product, service and contact pages individually; inspect failures and skipped URLs.",
                "Confirm the intended key pages appear in the next report and review any remaining gaps.",
                [],
            )
        )
    partial = [p for p in pages if p.get("render_status") in ("failed", "partial")]
    if partial:
        recommendations.append(
            _rec(
                "render-coverage",
                "medium",
                "Review pages with incomplete rendering",
                f"Rendering failed or was partial on {len(partial)} audited page(s).",
                "Inspect these pages in a normal browser and determine whether important content depends on scripts or API calls unavailable to the audit.",
                "Compare visible catalog and journey information with the report and record any missing evidence.",
                [p["url"] for p in partial],
            )
        )
    services = [p for p in pages if p.get("services")]
    if services:
        recommendations.append(
            _rec(
                "review-services",
                "medium",
                "Review service descriptions and proposal details",
                f"Service structured-data records were observed on {len(services)} audited page(s); some records may repeat.",
                "Confirm service descriptions, coverage area, pricing approach and the route to a proposal are clear and current on representative pages.",
                "Review each key service page with the business owner; validate descriptions and contact details against the actual offer.",
                [p["url"] for p in services[:3]],
            )
        )
    journey_pages = [p for p in pages if p.get("journey_signals")]
    if journey_pages:
        kinds = sorted({signal.get("kind", "unknown") for page in journey_pages for signal in page["journey_signals"]})
        kind_text = ", ".join(kinds)
        recommendations.append(
            _rec(
                "verify-journey",
                "high",
                "Verify the customer journey",
                f"The audit observed {kind_text} controls on {len(journey_pages)} page(s); it did not activate them.",
                f"With the owner, walk through the observed {kind_text} journey using an agreed test method; check required steps, handoff and confirmation.",
                "Record the outcome and any blocked step without creating a real transaction or sending a real enquiry unless explicitly authorized.",
                [p["url"] for p in journey_pages[:3]],
            )
        )
    recommendations.append(
        _rec(
            "verify-browser-access",
            "medium",
            "Check verified ChatGPT browser access",
            "This audit fetched pages with GEOSITION and did not test verified ChatGPT browser access.",
            "Test representative journeys with a verified ChatGPT cloud browser, then use the provider-specific guided fix only if the administrator confirms a block.",
            "Record the time and outcome of a real verified visit, correlate CDN or firewall logs, and repeat the same visit after any changes.",
            [],
            "https://developers.openai.com/commerce/agent-access",
        )
    )
    for recommendation in recommendations:
        if recommendation["id"] in {"catalog-structured-data", "complete-product-fields", "review-product-feed"}:
            recommendation["guided_fix"] = "geo commerce-prepare --audit <site-audit.json> --output-dir <new-directory>"
        elif recommendation["id"] in {"review-services", "verify-journey"} and (
            services
            or any(signal.get("kind") == "enquiry" for page in journey_pages for signal in page["journey_signals"])
        ):
            recommendation["guided_fix"] = (
                "geo commerce-service-prepare --audit <site-audit.json> --output-dir <new-directory>"
            )
    return sorted(
        recommendations,
        key=lambda rec: {"high": 0, "medium": 1}.get(rec["priority"], 2),
    )
