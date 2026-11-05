"""Citability: content freshness and temporal decay detection functions."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timezone

from geo_optimizer.core.citability._helpers import (
    _extract_dates_from_soup,
    _get_clean_text,
)
from geo_optimizer.models.config import (
    FRESHNESS_AGING_DAYS,
    FRESHNESS_FRESH_DAYS,
    FRESHNESS_VERY_FRESH_DAYS,
)
from geo_optimizer.models.results import MethodScore

# ─── Freshness helper functions ───────────────────────────────────────────────


def _compute_freshness_level(days_old: float) -> str:
    """Map content age in days to a freshness level string (#401).

    Levels (AutoGEO ICLR 2026):
    - very_fresh: < 3 months (FRESHNESS_VERY_FRESH_DAYS)
    - fresh:      3-6 months (FRESHNESS_FRESH_DAYS)
    - aging:      6-12 months (FRESHNESS_AGING_DAYS)
    - stale:      > 12 months
    """
    if days_old < FRESHNESS_VERY_FRESH_DAYS:
        return "very_fresh"
    if days_old < FRESHNESS_FRESH_DAYS:
        return "fresh"
    if days_old < FRESHNESS_AGING_DAYS:
        return "aging"
    return "stale"


def _freshness_citability_score(freshness_level: str) -> int:
    """Return citability score points for a given freshness level (#401).

    This is the CITABILITY score, separate from the GEO signals_freshness score.
    """
    return {
        "very_fresh": 4,
        "fresh": 3,
        "aging": 2,
        "stale": 0,
    }.get(freshness_level, 0)


# Pattern for dates in text: "Last updated: DATE", "Updated: DATE", etc.
_UPDATED_DATE_RE = re.compile(
    r"\b(?:last\s+updated|updated|aggiornato)\s*:?\s*"
    r"(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{4}"  # DD/MM/YYYY or similar
    r"|\d{4}[/\-\.]\d{1,2}[/\-\.]\d{1,2}"  # YYYY-MM-DD
    r"|\w+\s+\d{1,2},?\s+\d{4})",  # Month DD, YYYY
    re.IGNORECASE,
)


def _parse_date_flexible(date_str: str) -> datetime | None:
    """Try to parse a date string in common formats. Returns None on failure."""
    if not date_str:
        return None
    # Take only the first 10 chars for ISO format
    clean = str(date_str).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(clean[:10], fmt).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
    # Try "Month DD, YYYY" format
    try:
        # Remove comma and try
        clean_no_comma = clean.replace(",", "")
        return datetime.strptime(clean_no_comma[:20].strip(), "%B %d %Y").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        pass
    return None


# ─── 15. Content Freshness Warning (+10%) ────────────────────────────────────


def detect_content_freshness(soup, clean_text: str | None = None) -> MethodScore:
    """Detect content freshness via JSON-LD dates and year references in text.

    Returns a graduated freshness_level (#401):
    - very_fresh: < 3 months (4 citability points)
    - fresh: 3-6 months (3 citability points)
    - aging: 6-12 months (2 citability points)
    - stale: > 12 months or no date (0 citability points)
    """
    now = datetime.now(tz=timezone.utc)
    current_year = now.year

    # Fix #5: use shared helper to extract dates
    _dates = _extract_dates_from_soup(soup)
    date_modified = _dates["dateModified"]
    date_published = _dates["datePublished"]

    # Analyze the dates found
    days_old = None
    freshness_level = "unknown"
    has_date_signal = False

    for date_str in [date_modified, date_published]:
        if not date_str:
            continue
        has_date_signal = True
        try:
            clean_date = str(date_str)[:10]  # YYYY-MM-DD
            parsed = datetime.strptime(clean_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            days_old = (now - parsed).days
            freshness_level = _compute_freshness_level(days_old)
            break
        except (ValueError, TypeError):
            continue

    # Backward compat: is_fresh is True for very_fresh and fresh
    is_fresh = freshness_level in ("very_fresh", "fresh")
    months_old = days_old / 30 if days_old is not None else None

    # No valid date parsed despite a date signal → treat as stale
    if has_date_signal and days_old is None:
        freshness_level = "stale"

    # No date signal at all → unknown (treated as stale for scoring)
    if not has_date_signal:
        freshness_level = "stale"

    # Look for year references in the text
    body_text = clean_text or _get_clean_text(soup)
    year_refs = re.findall(r"\b(20[12]\d)\b", body_text)
    year_counts = Counter(year_refs)

    # Fix #426: consistent threshold — use current_year-1 (same as detect_no_stale_data)
    has_old_year_refs = any(int(y) < current_year - 1 for y in year_counts)
    has_current_year_refs = any(int(y) >= current_year for y in year_counts)

    # Score calculation
    score = _freshness_citability_score(freshness_level)
    warnings: list[str] = []

    if freshness_level == "stale" and has_date_signal and months_old is not None:
        warnings.append(f"Contenuto aggiornato {int(months_old)} mesi fa")
    elif not has_date_signal:
        warnings.append("No date signal found (dateModified/datePublished)")
        score += 1  # Base point to avoid penalizing too harshly

    if has_current_year_refs:
        score += 2
    elif has_old_year_refs and not is_fresh:
        warnings.append("References to past years without recent update date")

    return MethodScore(
        name="content_freshness",
        label="Content Freshness",
        detected=is_fresh or has_current_year_refs,
        score=min(score, 6),
        max_score=6,
        impact="+10%",
        details={
            "date_modified": date_modified,
            "date_published": date_published,
            "is_fresh": is_fresh,
            "freshness_level": freshness_level,
            "months_old": round(months_old, 1) if months_old is not None else None,
            "year_references": dict(year_counts),
            "warnings": warnings,
        },
    )


# ─── 23. Content Decay Detection (-10%) — Quality Signal Batch 2 ─────────────


def detect_content_decay(soup, clean_text: str | None = None) -> MethodScore:
    """Detect content decay signals: old year references, stale update dates."""
    body_text = clean_text or _get_clean_text(soup)
    now = datetime.now(tz=timezone.utc)
    current_year = now.year
    penalties = 0

    # 1. Past years in text without a recent dateModified
    year_refs = re.findall(r"\b(20[12]\d)\b", body_text)
    old_years = [int(y) for y in year_refs if int(y) < current_year - 1]
    current_years = [int(y) for y in year_refs if int(y) >= current_year]

    # Fix #9: use shared helper to extract dates
    _dates = _extract_dates_from_soup(soup)
    date_modified = _dates["dateModified"]

    # Check whether dateModified is recent
    is_recently_modified = False
    if date_modified:
        try:
            clean_date = str(date_modified)[:10]
            parsed = datetime.strptime(clean_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            months_old = (now - parsed).days / 30
            is_recently_modified = months_old <= 12
        except (ValueError, TypeError):
            pass

    # Penalize old years without a recent update
    if old_years and not is_recently_modified and not current_years:
        penalties += min(len(set(old_years)), 3)

    # 2. "last updated" / "aggiornato" pattern with old date
    update_patterns = re.findall(
        r"(?:last\s+updated|updated\s+on|aggiornato\s+(?:il|a|al))\s*:?\s*"
        r"(?:(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})|(\w+)\s+(\d{1,2}),?\s+(\d{4}))",
        body_text,
        re.IGNORECASE,
    )
    for match in update_patterns:
        # Extract the year from the match
        year_str = match[2] or match[5]
        if year_str and int(year_str) < current_year - 1:
            penalties += 1

    # 3. Count external links (cannot test if broken, but report the count)
    external_links = 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http") and not href.startswith("#"):
            external_links += 1

    # Inverted score: 5 if no decay, 0 if severe
    score = max(5 - penalties, 0)

    return MethodScore(
        name="no_content_decay",
        label="No Content Decay",
        detected=penalties >= 2,
        score=score,
        max_score=5,
        impact="-10%",
        details={
            "old_year_references": list(set(old_years)),
            "is_recently_modified": is_recently_modified,
            "stale_update_patterns": len(update_patterns),
            "external_links_count": external_links,
            "total_penalties": penalties,
        },
    )


# ─── Stale Data Detection (-10%) — Batch A v3.16.0 ──────────────────────────


def detect_stale_data(soup, clean_text: str | None = None) -> MethodScore:
    """Detect stale data signals. Score INVERSO: 4 se pulito, 0 se molto stale."""
    body_text = clean_text or _get_clean_text(soup)
    now = datetime.now(tz=timezone.utc)
    current_year = now.year
    penalties = 0

    # 1. Old copyright year in the footer
    footer = soup.find("footer")
    old_copyright = False
    if footer:
        footer_text = footer.get_text(strip=True)
        # Fix #418: handle copyright ranges (e.g. © 2020-2026) — use end year
        copyright_years = re.findall(
            r"©\s*(20\d{2})(?:\s*[-–]\s*(20\d{2}))?|copyright\s*(20\d{2})(?:\s*[-–]\s*(20\d{2}))?",
            footer_text,
            re.I,
        )
        for match in copyright_years:
            # Use the last year in the range (end year), or the single year
            year = int(match[1] or match[3] or match[0] or match[2])
            if year < current_year - 1:
                old_copyright = True
                penalties += 2
                break

    # 2. Pattern "as of YYYY" or "in YYYY" with a stale year in the text
    # Fix #455: expanded to cover 2000-2009 (was 20[12]\d = 2010-2029 only)
    stale_refs = re.findall(
        r"\b(?:as\s+of|in|nel|del|aggiornato\s+al?)\s+(20[0-2]\d)\b",
        body_text,
        re.IGNORECASE,
    )
    stale_year_refs = [int(y) for y in stale_refs if int(y) < current_year - 1]
    if len(stale_year_refs) >= 3:
        penalties += 2
    elif len(stale_year_refs) >= 1:
        penalties += 1

    # Inverted score: 4 if clean, 0 if very stale
    score = max(4 - penalties, 0)

    return MethodScore(
        name="no_stale_data",
        label="No Stale Data",
        detected=penalties >= 1,  # fix #327: detected=True when the problem is present
        score=min(score, 4),
        max_score=4,
        impact="-10%",
        details={
            "old_copyright_in_footer": old_copyright,
            "stale_year_references": stale_year_refs,
            "penalties": penalties,
        },
    )


# ─── Temporal Signal Coherence (+8%) — Batch B v3.16.0 ───────────────────────


def detect_temporal_coherence(soup, clean_text: str | None = None) -> MethodScore:
    """Detect temporal signal coherence across schema dates and visible content dates.

    Compares dateModified/datePublished from JSON-LD schema with visible
    'Last updated' / 'Updated' patterns in text. Coherent dates (< 30 days
    apart) get full score; incoherent dates (> 90 days) get a warning.
    """
    import json

    body_text = clean_text or _get_clean_text(soup)
    dates_found: dict[str, datetime] = {}

    # 1. Schema JSON-LD: dateModified, datePublished
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                for key in ("dateModified", "datePublished"):
                    if key in item:
                        parsed = _parse_date_flexible(str(item[key]))
                        if parsed:
                            dates_found[f"schema_{key}"] = parsed
        except (json.JSONDecodeError, TypeError):
            continue

    # 2. Meta tag article:modified_time / article:published_time
    for meta_prop, label in [
        ("article:modified_time", "meta_modified"),
        ("article:published_time", "meta_published"),
    ]:
        meta = soup.find("meta", attrs={"property": meta_prop})
        if meta and meta.get("content"):
            parsed = _parse_date_flexible(meta["content"])
            if parsed:
                dates_found[label] = parsed

    # 3. Visible pattern in text: "Last updated: DATE", "Updated: DATE"
    matches = _UPDATED_DATE_RE.findall(body_text)
    for i, match in enumerate(matches[:3]):  # Max 3 match
        parsed = _parse_date_flexible(match)
        if parsed:
            dates_found[f"visible_updated_{i}"] = parsed

    # 4. Calculate coherence
    date_values = list(dates_found.values())
    is_coherent = False
    is_incoherent = False
    max_diff_days = 0

    if len(date_values) >= 2:
        # Calculate the maximum difference between all pairs
        for i in range(len(date_values)):
            for j in range(i + 1, len(date_values)):
                diff = abs((date_values[i] - date_values[j]).days)
                max_diff_days = max(max_diff_days, diff)

        if max_diff_days <= 30:
            is_coherent = True
        elif max_diff_days > 90:
            is_incoherent = True

    # Score
    score = 0
    if len(date_values) >= 2 and is_coherent:
        score = 4  # Full score: dates present and coherent
    elif len(date_values) >= 2 and not is_incoherent:
        score = 2  # Dates present, moderate difference (30-90 days)
    elif len(date_values) == 1:
        score = 1  # Only one date found
    # If incoherent (> 90 days) or no dates: score = 0

    return MethodScore(
        name="temporal_coherence",
        label="Temporal Signal Coherence",
        detected=len(date_values) >= 2 and is_coherent,
        score=min(score, 4),
        max_score=4,
        impact="+8%",
        details={
            "dates_found": {k: v.isoformat() for k, v in dates_found.items()},
            "date_count": len(date_values),
            "max_diff_days": max_diff_days,
            "is_coherent": is_coherent,
            "is_incoherent": is_incoherent,
        },
    )
