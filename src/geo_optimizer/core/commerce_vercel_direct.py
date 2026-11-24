"""Retrieve scoped provider evidence using a locally authenticated Vercel CLI.

The CLI owns authentication; GEOSITION never receives or stores a Vercel token.
"""

from __future__ import annotations

import json
import subprocess
from urllib.parse import urlsplit

from geo_optimizer.core.commerce_provider_evidence import _time


def _run(executable, arguments):
    try:
        proc = subprocess.run([executable, *arguments], capture_output=True, text=True, timeout=45, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("Vercel CLI unavailable or timed out; check installation and sign-in.") from exc
    if proc.returncode:
        raise ValueError("Vercel query failed; check CLI version, account access, project, and observability plan.")
    return proc.stdout


def fetch_vercel_correlation(audit_url, *, executable, scope, project, request_id, since, until, runner=_run):
    """Correlate one CDN request with authenticated, verified AI-traffic aggregates."""
    start, end = _time(since), _time(until)
    if start >= end or (end - start).total_seconds() > 600:
        raise ValueError("Vercel correlation window must be positive and no longer than ten minutes.")
    if start.second or end.second or start.microsecond or end.microsecond:
        raise ValueError("Vercel correlation windows must begin and end on whole minutes.")
    if not all(
        isinstance(x, str) and x and len(x) <= 128 and all(c.isalnum() or c in "-_" for c in x)
        for x in (scope, project, request_id)
    ):
        raise ValueError("Invalid Vercel scope, project, or request ID.")
    parsed = urlsplit(audit_url)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("The audited page must use HTTPS without credentials, port, query, or fragment.")
    common = ["--scope", scope, "--project", project, "--since", since, "--until", until, "--json"]
    try:
        lines = [
            json.loads(line)
            for line in runner(
                executable, ["logs", "requests", *common, "--limit", "1000", "--non-interactive"]
            ).splitlines()
            if line.strip()
        ]
        metrics = json.loads(
            runner(executable, ["metrics", "vercel.ai_traffic.count", *common, "--group-by", "botName"])
        )
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Vercel returned an unreadable response.") from exc
    records = [line["data"] for line in lines if line.get("type") == "request"]
    summaries = [line for line in lines if line.get("type") == "summary"]
    if len(summaries) != 1:
        raise ValueError("Vercel request-log summary is missing.")
    summary = summaries[0]
    if (
        summary.get("pagination", {}).get("hasMore") is not False
        or summary.get("excludedIntervals") != []
        or summary.get("recordsReturned") != len(records)
    ):
        raise ValueError("Vercel request data is incomplete or paginated; cannot correlate.")
    log_range = summary.get("timeRange", {})
    metric_range = metrics.get("meta", {}).get("effectiveTimeRange", {})
    if not all(
        _time(x) == y
        for x, y in [
            (log_range.get("start"), start),
            (log_range.get("end"), end),
            (metric_range.get("start"), start),
            (metric_range.get("end"), end),
        ]
    ):
        raise ValueError("Vercel returned a different time window; cannot correlate.")
    matching = [r for r in records if r.get("requestId") == request_id]
    if len(matching) != 1:
        raise ValueError("The request ID was not uniquely present in this project and time window.")
    request = matching[0]
    if (
        request.get("requestHostname") != parsed.hostname
        or request.get("requestPath") != (parsed.path or "/")
        or request.get("requestMethod") != "GET"
    ):
        raise ValueError("The Vercel request does not match the audited page.")
    if not start <= _time(request.get("timestamp")) < end:
        raise ValueError("The Vercel request lies outside the time window.")
    if request.get("wafAction") != "allow" or request.get("httpStatus") not in (200, 203, 304):
        raise ValueError("The Vercel request was not an allowed successful page response.")
    query = metrics.get("query", {})
    if (
        query.get("metric") != "vercel.ai_traffic.count"
        or query.get("aggregation") != "count"
        or query.get("groupBy") != ["botName"]
    ):
        raise ValueError("Vercel returned a different AI-traffic metric; cannot correlate.")
    rows = metrics.get("summary")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise ValueError("Vercel AI-traffic summary is missing.")
    counts = [row.get("vercel_ai_traffic_count_count") for row in rows if row.get("botName") == "chatgpt-operator"]
    other_counts = [
        row.get("vercel_ai_traffic_count_count") for row in rows if row.get("botName") != "chatgpt-operator"
    ]
    if (
        len(counts) != 1
        or type(counts[0]) is not int
        or counts[0] < 1
        or counts[0] != len(records)
        or any(type(value) is not int or value != 0 for value in other_counts)
    ):
        raise ValueError("Verified ChatGPT aggregate does not cover every CDN request in this window.")
    return {
        "provider": "Vercel",
        "agent": "chatgpt-operator",
        "classification": "provider_verified_correlated",
        "page_url": audit_url,
        "request_id": request_id,
        "request_time": request["timestamp"],
        "window_start": since,
        "window_end": until,
        "total_requests": len(records),
        "verified_agent_requests": counts[0],
        "http_status": request["httpStatus"],
        "firewall_action": "allow",
        "metric_query_id": metrics.get("queryId"),
        "limit": "Authenticated Vercel request logs and verified AI-traffic aggregate correlate for this historical window. Individual signature bytes and verification method were not returned; this does not establish current or site-wide access.",
    }


def attach_direct_vercel(report, evidence):
    report.setdefault("browser_access", {})["provider_evidence"] = evidence
    for rec in report.get("recommendations", []):
        if rec.get("id") == "verify-browser-access":
            rec["evidence"] = (
                "Vercel authenticated request logs and verified-agent aggregate correlate for a previous page visit."
            )
            rec["action"] = (
                "Review the dated provider evidence and repeat the browser test when current access is needed."
            )
            rec["verification"] = (
                "Request per-request signature-validation details from Vercel if cryptographic proof is needed."
            )
            rec["evidence_urls"] = [evidence["page_url"]]
    return report
