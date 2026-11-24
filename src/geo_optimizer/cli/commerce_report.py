"""Client-facing Markdown formatting for commerce site audit results."""

from __future__ import annotations

from urllib.parse import urlsplit


def _safe(value):
    return str(value).replace("\n", " ").replace("\r", " ").replace("<", "&lt;").replace("]", "\\]")


def format_commerce_report(report: dict, title: str = "AI commerce readiness report", audit_date: str = "") -> str:
    """Format evidence and recommendations for review and sharing."""
    coverage = report["coverage"]
    date_line = f"\n**Audit date:** {_safe(audit_date)}  " if audit_date else ""
    lines = [
        f"# {_safe(title)}",
        "",
        f"**Website:** {_safe(report['url'])}  {date_line}",
        f"**Coverage:** {coverage['pages_audited']} pages audited; {coverage['pending']} discovered pages pending.",
        "",
        "## What we observed",
        "",
    ]
    cards = sum(len(p.get("catalog_signals", [])) for p in report["pages"])
    products = sum(len(p.get("products", [])) for p in report["pages"])
    service_pages = sum(bool(p.get("services")) for p in report["pages"])
    journey_pages = sum(bool(p.get("journey_signals")) for p in report["pages"])
    if cards or products:
        lines.append(f"- {cards} product-like cards and {products} Product structured-data records were observed.")
    if service_pages:
        lines.append(f"- Service structured-data records were observed on {service_pages} pages; records may repeat.")
    if journey_pages:
        lines.append(f"- Possible customer-journey controls were observed on {journey_pages} pages.")
    lines.extend(
        [
            "- These are page signals, not verified inventory, completed transactions, or proof of provider eligibility.",
            "",
            "## Recommended actions",
            "",
        ]
    )
    for index, rec in enumerate(report.get("recommendations", []), 1):
        lines.extend(
            [
                f"### {index}. {_safe(rec['title'])} — {_safe(rec['priority']).title()} priority",
                "",
                f"**Evidence:** {_safe(rec['evidence'])}",
                "",
                f"**Action:** {_safe(rec['action'])}",
                "",
                f"**How to verify:** {_safe(rec['verification'])}",
                "",
            ]
        )
        for url in rec.get("evidence_urls", []):
            if urlsplit(url).scheme in ("https", "http"):
                lines.append(f"- Evidence page: <{url}>")
        if rec.get("guidance_url"):
            lines.append(f"- Guidance: <{rec['guidance_url']}>")
        if rec.get("guided_fix"):
            lines.append(f"- Guided preparation: `{rec['guided_fix']}`")
        lines.append("")
    access = report.get("browser_access")
    if access:
        lines.extend(["## Cloud-browser access", "", "Verified ChatGPT browser access: **unknown**.", ""])
        provider = access.get("provider_evidence")
        if provider:
            lines.extend(
                [
                    f"**Historical provider evidence:** {_safe(provider['classification'])} for {_safe(provider['page_url'])} at {_safe(provider['request_time'])}.",
                    "",
                    _safe(provider["limit"]),
                    "",
                ]
            )
        for item in access.get("observations", []):
            lines.append(
                f"- Ordinary fetch: <{item['url']}> — {_safe(item['fetch_status'])}; HTTP {_safe(item.get('http_status') or 'unavailable')}."
            )
        lines.extend(["", _safe(access.get("provider_hint_note", "")), "", "Next steps:", ""])
        lines.extend(f"{index}. {_safe(step)}" for index, step in enumerate(access.get("test_steps", []), 1))
        lines.extend(["", f"Guidance: <{access['guidance_url']}>", ""])
    lines.extend(
        [
            "## Coverage and limits",
            "",
            coverage.get("scope", "The scan covers discovered pages only."),
            "",
            "JavaScript rendering, when requested, blocks browser network requests; content depending on APIs, third-party scripts or interaction may be missing. Feed submission, eligibility, current site-wide verified ChatGPT browser access, current inventory and completed transactions were not verified.",
            "",
            "Pages reviewed:",
            "",
        ]
    )
    for page in report["pages"]:
        lines.append(f"- <{page['url']}> — rendering: {_safe(page.get('render_status', 'unknown'))}")
    if report.get("warnings"):
        lines.extend(["", "Scan warnings:", ""] + [f"- {_safe(warning)}" for warning in report["warnings"]])
    if report.get("failures") or report.get("skipped"):
        lines.extend(
            [
                "",
                f"The scan recorded {len(report.get('failures', []))} failed and {len(report.get('skipped', []))} skipped URLs; see the machine-readable audit for details.",
            ]
        )
    lines.extend(
        [
            "",
            "Prepared from an automated audit for human review. Results do not guarantee discovery, rankings, or sales.",
            "",
        ]
    )
    return "\n".join(lines)
