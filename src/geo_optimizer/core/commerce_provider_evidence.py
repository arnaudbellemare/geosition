"""Attach operator-reported Vercel observations without claiming direct verification."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import urlsplit


def _time(value):
    if not isinstance(value, str):
        raise ValueError("Timestamps must be ISO 8601 strings with a timezone.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Invalid evidence timestamp.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Evidence timestamps require a timezone.")
    return parsed


def validate_vercel_evidence(evidence, audit_url):
    """Validate scope and correlation; never treat user-provided data as provider authentication."""
    if not isinstance(evidence, dict):
        raise ValueError("Provider evidence must be an object.")
    required = {
        "page_url",
        "request_id",
        "request_time",
        "window_start",
        "window_end",
        "total_requests",
        "verified_agent_requests",
        "dashboard_url",
        "attested",
    }
    if set(evidence) != required:
        raise ValueError("Provider evidence fields are missing or unsupported.")
    if not isinstance(evidence["page_url"], str) or not isinstance(evidence["dashboard_url"], str):
        raise ValueError("Evidence URLs must be strings.")
    page, audited = urlsplit(evidence["page_url"]), urlsplit(audit_url)
    if (
        page.scheme != "https"
        or not page.hostname
        or page.hostname != audited.hostname
        or page.port is not None
        or page.username
        or page.password
        or page.query
        or page.fragment
    ):
        raise ValueError("Evidence page must be an HTTPS page on the audited hostname without query parameters.")
    dashboard = urlsplit(evidence["dashboard_url"])
    if dashboard.scheme != "https" or dashboard.hostname != "vercel.com" or dashboard.username or dashboard.password:
        raise ValueError("Evidence dashboard must be an HTTPS vercel.com URL.")
    request_id = evidence["request_id"]
    if (
        not isinstance(request_id, str)
        or not 1 <= len(request_id) <= 128
        or not all(c.isalnum() or c in "-_" for c in request_id)
    ):
        raise ValueError("Invalid Vercel request ID.")
    start, request, end = (_time(evidence[k]) for k in ("window_start", "request_time", "window_end"))
    if not start <= request <= end or start >= end:
        raise ValueError("The request timestamp must fall inside the evidence window.")
    if (end - start).total_seconds() > 600:
        raise ValueError("Correlation window must be no longer than ten minutes.")
    total, verified = evidence["total_requests"], evidence["verified_agent_requests"]
    if type(total) is not int or type(verified) is not int or total < 1 or verified != total:
        raise ValueError("Correlated evidence requires all requests in the window to be in the verified-agent row.")
    if evidence["attested"] is not True:
        raise ValueError("The operator must attest that the Vercel verified badge and request record were observed.")
    return {
        **evidence,
        "provider": "Vercel",
        "agent": "chatgpt-operator",
        "classification": "operator_reported_correlated",
        "limit": "Operator-reported historical Vercel aggregate; GEOSITION did not authenticate the provider evidence or inspect the individual signature.",
    }


def attach_vercel_evidence(report, evidence):
    """Attach scoped historical evidence to an audit without changing its verification claim."""
    record = validate_vercel_evidence(evidence, report["url"])
    report.setdefault("browser_access", {})["provider_evidence"] = record
    for rec in report.get("recommendations", []):
        if rec.get("id") == "verify-browser-access":
            rec["evidence"] = (
                "An operator recorded correlated Vercel verified-agent traffic for a past visit; GEOSITION has not independently verified it."
            )
            rec["action"] = (
                "Review the attached historical evidence and repeat the verified browser test if current access is needed."
            )
            rec["verification"] = (
                "Confirm the provider observation and its scope; request per-request signature validation if needed."
            )
            rec["evidence_urls"] = [record["page_url"]]
    return report
