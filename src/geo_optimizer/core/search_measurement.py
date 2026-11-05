"""Read-only first-party search metrics. Provider credentials are never persisted."""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import quote, urlparse

import requests

_GOOGLE = "https://www.googleapis.com/webmasters/v3/sites/{property}/searchAnalytics/query"
_BING = "https://ssl.bing.com/webmaster/api.svc/json/GetRankAndTrafficStats"
_MAX_BYTES = 2 * 1024 * 1024


def validate_property(provider: str, property_id: str, domain: str) -> None:
    """Restrict the requested property to the verified workspace domain."""
    if provider == "google" and property_id.startswith("sc-domain:"):
        host = property_id[len("sc-domain:") :].lower()
    else:
        parsed = urlparse(property_id)
        if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("Enter the exact property URL from your provider account.")
        host = parsed.hostname.lower()
    if host != domain.lower():
        raise ValueError("The provider property must match the verified workspace domain.")


def fetch_search_measurement(
    provider: str, property_id: str, access_token: str, start_date: str, end_date: str
) -> dict:
    """Fetch limited, aggregate search data from a fixed provider endpoint.

    These metrics are not AI-only citation counts. Caller must verify workspace
    ownership and property association before invoking this function.
    """
    try:
        start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    except ValueError as exc:
        raise ValueError("Enter valid start and end dates.") from exc
    if start > end or (end - start).days > 366:
        raise ValueError("Choose a date range of at most 367 days.")
    if not access_token or len(access_token) > 8192 or any(c.isspace() for c in access_token):
        raise ValueError("Enter a valid provider access token.")
    headers = {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}
    try:
        if provider == "google":
            response = requests.post(
                _GOOGLE.format(property=quote(property_id, safe="")),
                headers=headers,
                json={
                    "startDate": start_date,
                    "endDate": end_date,
                    "dimensions": ["date"],
                    "type": "web",
                    "rowLimit": 367,
                },
                timeout=15,
                allow_redirects=False,
                stream=True,
            )
        elif provider == "bing":
            response = requests.get(
                _BING,
                headers=headers,
                params={"siteUrl": property_id},
                timeout=15,
                allow_redirects=False,
                stream=True,
            )
        else:
            raise ValueError("Unsupported provider.")
        with response:
            if response.status_code != 200:
                raise ValueError("The provider rejected the request. Check the token and property permissions.")
            raw = bytearray()
            for chunk in response.iter_content(65536):
                raw.extend(chunk)
                if len(raw) > _MAX_BYTES:
                    raise ValueError("The provider response was too large.")
        payload = json.loads(raw)
        rows = payload.get("rows", []) if provider == "google" else payload.get("d", [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("The provider returned an unexpected response.")
    except requests.RequestException as exc:
        raise ValueError("Could not reach the provider. Try again later.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError, AttributeError) as exc:
        raise ValueError("The provider returned an invalid response.") from exc
    return {
        "provider": provider,
        "property": property_id,
        "start_date": start_date,
        "end_date": end_date,
        "metric_scope": "search_traffic_not_ai_citations",
        "note": (
            "Google web search totals include multiple search surfaces; they are not AI-only metrics."
            if provider == "google"
            else "Bing returns its available traffic history across search surfaces; this is not AI citation data."
        ),
        "rows": rows,
    }
