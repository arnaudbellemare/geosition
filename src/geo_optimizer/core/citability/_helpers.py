"""Shared constants and helper functions for the citability package."""

from __future__ import annotations

import json
import re
from collections import Counter  # noqa: F401 — re-exported for submodule use

# ─── Constants ────────────────────────────────────────────────────────────────

# Authoritative domains for Cite Sources
_AUTHORITATIVE_TLDS = {".edu", ".gov", ".org"}
_AUTHORITATIVE_DOMAINS = {
    "wikipedia.org",
    "pubmed.ncbi.nlm.nih.gov",
    "scholar.google.com",
    "nature.com",
    "sciencedirect.com",
    "jstor.org",
    "arxiv.org",
    "ncbi.nlm.nih.gov",
    "who.int",
    "cdc.gov",
    "europa.eu",
    "springer.com",
    "ieee.org",
}

# Attribution quote pattern: "text" — Author
# Fix #429: removed DOTALL to prevent cross-paragraph false positives
_QUOTE_ATTRIBUTION_RE = re.compile(
    r'["“][^"”]{10,300}["”]\s*(?:[-—–]|—|–)\s*\w+',
)

# Statistics patterns
_STAT_PATTERNS = [
    r"\b\d+(?:\.\d+)?%",
    r"\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b",
    r"\$\d+(?:[.,]\d+)*(?:\s*(?:M|B|K|million|billion|thousand))?\b",
    r"\b\d+\s*(?:million|billion|trillion|thousand)\b",
    r"\b\d+(?:\.\d+)?\s*(?:x|X)\b",
]
_STAT_RE = re.compile("|".join(_STAT_PATTERNS), re.IGNORECASE)

# Logical connectives (EN + IT)
_CONNECTIVES = re.compile(
    r"\b(?:therefore|consequently|furthermore|moreover|however|nevertheless"
    r"|in addition|as a result|for example|for instance|in conclusion"
    r"|specifically|in particular|in contrast"
    r"|quindi|pertanto|di conseguenza|inoltre|innanzitutto|infatti"
    r"|tuttavia|nonostante|in particolare|ad esempio|come risultato)\b",
    re.IGNORECASE,
)

# Authoritative tone markers
_AUTHORITY_RE = re.compile(
    r"\b(?:according to|research (?:shows?|indicates?|demonstrates?)"
    r"|studies? (?:show|indicate|demonstrate|confirm)"
    r"|evidence (?:shows?|suggests?|indicates?)"
    r"|experts? (?:agree|recommend|suggest)"
    r"|data (?:shows?|indicates?|reveals?)"
    r"|proven|demonstrated|established)\b",
    re.IGNORECASE,
)

# Excessive hedging
_HEDGE_RE = re.compile(
    r"\b(?:might be|could possibly|maybe|perhaps|somewhat|kind of|sort of|seems like)\b",
    re.IGNORECASE,
)

# Common English uppercase words excluded from tech acronym matching (#425)
_UPPER_STOPWORDS = r"AM|AN|AS|AT|BE|BY|DO|GO|HE|IF|IN|IS|IT|ME|MY|NO|OF|ON|OR|SO|TO|UP|US|WE"

# Technical terminology patterns (#425: excluded common words from acronym pattern)
_TECH_PATTERNS = [
    r"\b(?!(?:" + _UPPER_STOPWORDS + r")\b)[A-Z]{2,6}\b",
    r"\bv\d+\.\d+(?:\.\d+)?\b",
    r"\bRFC\s*\d+\b",
    r"\bISO\s*\d+\b",
    r"\b(?:IEEE|IETF|W3C|ECMA)\b",
    r"`[^`]+`",
]
_TECH_RE = re.compile("|".join(_TECH_PATTERNS))

# Stop words for TTR (basic English)
_STOP_WORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "in",
    "on",
    "at",
    "to",
    "for",
    "of",
    "with",
    "by",
    "from",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "will",
    "would",
    "could",
    "should",
    "may",
    "might",
    "shall",
    "this",
    "that",
    "these",
    "those",
    "it",
    "its",
    "not",
    "no",
    "can",
    "so",
    "if",
    "then",
    "than",
    "also",
}


# ─── Helper functions ─────────────────────────────────────────────────────────


def _get_clean_text(soup, soup_clean=None) -> str:
    """Estrae testo pulito rimuovendo script, style, nav, footer.

    Args:
        soup: BeautifulSoup originale.
        soup_clean: (optional) soup pre-cleaned from script/style (fix #285).
                    Se fornito, evita il re-parse costoso dell'HTML.
    """
    import copy

    if soup_clean is not None:
        # Use a copy of the pre-computed soup_clean, strip only nav/footer/header
        working = copy.deepcopy(soup_clean)
        for tag in working(["nav", "footer", "header"]):
            tag.decompose()
        return str(working.get_text(separator=" ", strip=True))

    # Fallback: build a clean copy from scratch with deepcopy (fix #285: avoid BS(str(soup)))
    working = copy.deepcopy(soup)
    for tag in working(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return str(working.get_text(separator=" ", strip=True))


def _extract_dates_from_soup(soup) -> dict[str, str | None]:
    """Estrae dateModified e datePublished da JSON-LD e meta tag.

    Fix #5/#9: logica condivisa tra detect_content_freshness e detect_content_decay.

    Returns:
        Dict with keys "dateModified" and "datePublished" (None if not found).
    """
    dates: dict[str, str | None] = {"dateModified": None, "datePublished": None}

    # JSON-LD schema
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict):
                    # Fix #326: unpack @graph (Yoast/RankMath)
                    if "@graph" in item and isinstance(item["@graph"], list):
                        items.extend(item["@graph"])
                        continue
                    if "dateModified" in item and not dates["dateModified"]:
                        dates["dateModified"] = item["dateModified"]
                    if "datePublished" in item and not dates["datePublished"]:
                        dates["datePublished"] = item["datePublished"]
        except (json.JSONDecodeError, TypeError):
            continue

    # Meta tag fallback
    if not dates["dateModified"]:
        meta_mod = soup.find("meta", attrs={"property": "article:modified_time"})
        if meta_mod and meta_mod.get("content"):
            dates["dateModified"] = meta_mod["content"]
    if not dates["datePublished"]:
        meta_pub = soup.find("meta", attrs={"property": "article:published_time"})
        if meta_pub and meta_pub.get("content"):
            dates["datePublished"] = meta_pub["content"]

    return dates


def _iter_jsonld_items(soup) -> list[dict]:
    """Return JSON-LD dict items, including nested @graph entries."""
    items: list[dict] = []
    pending: list[object] = []

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        pending.extend(data if isinstance(data, list) else [data])

    while pending:
        item = pending.pop(0)
        if not isinstance(item, dict):
            continue
        items.append(item)
        graph = item.get("@graph")
        if isinstance(graph, list):
            pending.extend(graph)

    return items


def _jsonld_types(item: dict) -> list[str]:
    """Normalize JSON-LD @type values to a list of strings."""
    schema_type = item.get("@type", "")
    if isinstance(schema_type, list):
        return [str(value) for value in schema_type]
    return [str(schema_type)] if schema_type else []
