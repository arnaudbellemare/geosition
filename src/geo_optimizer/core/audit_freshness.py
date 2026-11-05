"""
GEO Audit — Freshness signals (v4.14).

Goes beyond signals.has_freshness (which only checks schema/meta tags) to verify:
  1. A human-readable date appears in the visible HTML body, near the top of the page
  2. The HTTP Last-Modified response header is present
  3. The schema dateModified and the visible date agree (within 7 days)
  4. A <time> element with a datetime attribute is present

A schema date that contradicts the visible text is a trust signal conflict — AI
systems that cross-reference structured data with visible content may downweight
pages where these signals disagree.

All functions return dataclasses, NEVER print.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import cast

from geo_optimizer.models.results import FreshnessResult

# Patterns for human-readable dates in visible text
# Matches forms like: "January 15, 2025", "15 Jan 2025", "2025-01-15", "Jan 15, 2025"
_DATE_PATTERNS = [
    # ISO 8601: 2025-01-15
    re.compile(r"\b(20\d{2})[-/](0[1-9]|1[0-2])[-/](0[1-9]|[12]\d|3[01])\b"),
    # "January 15, 2025" or "Jan 15, 2025"
    re.compile(
        r"\b(January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+(\d{1,2}),?\s+(20\d{2})\b",
        re.IGNORECASE,
    ),
    # "15 January 2025" or "15 Jan 2025"
    re.compile(
        r"\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|"
        r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+(20\d{2})\b",
        re.IGNORECASE,
    ),
]

_MONTH_MAP = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

# Words in the first 500 that count as "near top"
_NEAR_TOP_WORD_THRESHOLD = 500


def _try_parse_date(text: str) -> datetime | None:
    """Attempt to parse a date string in ISO or common verbose formats."""
    text = text.strip()
    # ISO 8601
    for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text[:10], fmt)
        except ValueError:
            pass
    return None


def _extract_visible_date(soup_clean) -> tuple[str, bool]:
    """Find the first date-like string in the visible text.

    Returns (date_text, near_top) where near_top is True if the date appears
    within the first ~500 words of the page body.
    """
    if soup_clean is None:
        return "", False

    body = soup_clean.find("body") or soup_clean
    text = body.get_text(separator=" ", strip=True)
    words = text.split()
    # Limit search to visible portion for "near top" check
    first_500 = " ".join(words[:_NEAR_TOP_WORD_THRESHOLD])

    for pattern in _DATE_PATTERNS:
        # Search in first 500 words first
        m = pattern.search(first_500)
        if m:
            return m.group(0), True
        # Fall back to full text
        m = pattern.search(text)
        if m:
            return m.group(0), False

    return "", False


def _extract_schema_date(schema_result) -> str:
    """Pull dateModified (or datePublished) from schema results."""
    if schema_result is None:
        return ""
    for s in schema_result.raw_schemas:
        schemas_to_check = list(s.get("@graph", [s]))
        for schema in schemas_to_check:
            date = schema.get("dateModified", "") or schema.get("datePublished", "")
            if date and isinstance(date, str):
                return cast(str, date[:10])  # Keep YYYY-MM-DD portion only
    return ""


def _dates_agree(date_a: str, date_b: str, tolerance_days: int = 7) -> bool | None:
    """Return True if dates agree within tolerance, False if conflict, None if unparseable."""
    d_a = _try_parse_date(date_a)
    d_b = _try_parse_date(date_b)
    if d_a is None or d_b is None:
        return None
    return abs((d_a - d_b).days) <= tolerance_days


def audit_freshness(soup, soup_clean, response_headers: dict, schema_result=None) -> FreshnessResult:
    """Audit freshness signals: visible date, Last-Modified, schema agreement.

    Args:
        soup: BeautifulSoup of the full page.
        soup_clean: BeautifulSoup with script/style removed (or None).
        response_headers: HTTP response headers dict.
        schema_result: Already-computed SchemaResult (optional).

    Returns:
        FreshnessResult with all freshness signals populated.
    """
    result = FreshnessResult()

    if soup is None:
        return result

    result.checked = True

    # ── 1. Visible date in HTML body ─────────────────────────────────────────
    effective_clean = soup_clean or soup
    visible_text, near_top = _extract_visible_date(effective_clean)
    if visible_text:
        result.visible_date_text = visible_text
        result.visible_date_near_top = near_top

    # ── 2. <time datetime="..."> element ─────────────────────────────────────
    time_el = soup.find("time", attrs={"datetime": True})
    if time_el:
        result.has_time_element = True
        result.time_datetime = time_el.get("datetime", "").strip()

    # ── 3. HTTP Last-Modified header ─────────────────────────────────────────
    normalised = {k.lower(): v for k, v in (response_headers or {}).items()}
    last_mod = normalised.get("last-modified", "").strip()
    if last_mod:
        result.has_last_modified = True
        result.last_modified_header = last_mod

    # ── 4. Schema date ───────────────────────────────────────────────────────
    schema_date = _extract_schema_date(schema_result)
    if schema_date:
        result.schema_date = schema_date

    # ── 5. Date agreement check ──────────────────────────────────────────────
    if schema_date and visible_text:
        agreement = _dates_agree(schema_date, visible_text[:10])
        if agreement is True:
            result.date_agreement = True
        elif agreement is False:
            result.date_conflict = True
            result.conflict_detail = (
                f"Schema dateModified ({schema_date}) disagrees with visible date "
                f"('{visible_text}'). AI systems cross-referencing structured data "
                "with visible content may downweight this page."
            )

    return result
