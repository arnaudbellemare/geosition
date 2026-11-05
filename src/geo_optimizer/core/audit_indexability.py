"""
GEO Audit — Indexability conflict detection (v4.14).

Checks three layers that control whether AI crawlers can index and use page content:
  1. robots.txt (already in RobotsResult — cross-referenced here)
  2. <meta name="robots"> page-level directive
  3. X-Robots-Tag HTTP response header

The most dangerous case is nosnippet (meta or header), which Google explicitly
documents as blocking content from AI Overviews and AI Mode. A site can pass the
robots.txt check perfectly while silently blocking all AI citation via this tag.

A robots-vs-meta conflict occurs when robots.txt allows a bot but the page carries
noindex or nosnippet — the bot fetches the page but can't use it.

All functions return dataclasses, NEVER print.
"""

from __future__ import annotations

import re

from geo_optimizer.models.results import IndexabilityResult

# Matches max-snippet=N (N may be 0 or positive integer)
_MAX_SNIPPET_RE = re.compile(r"max-snippet\s*=\s*(-?\d+)", re.IGNORECASE)


def _parse_robots_directive(directive: str) -> dict:
    """Parse a robots directive string into flags.

    Args:
        directive: Content of meta robots or X-Robots-Tag, e.g. "noindex, max-snippet=0"

    Returns:
        Dict with keys: noindex, nosnippet, max_snippet (int, -1 = unrestricted)
    """
    lower = directive.lower()
    noindex = "noindex" in lower
    nosnippet = "nosnippet" in lower

    max_snippet = -1  # -1 = unrestricted (not set)
    m = _MAX_SNIPPET_RE.search(directive)
    if m:
        max_snippet = int(m.group(1))

    # max-snippet=0 is equivalent to nosnippet
    if max_snippet == 0:
        nosnippet = True

    return {"noindex": noindex, "nosnippet": nosnippet, "max_snippet": max_snippet}


def audit_indexability(
    soup,
    response_headers: dict,
    robots_allowed: bool = True,
) -> IndexabilityResult:
    """Detect indexability conflicts across meta robots, X-Robots-Tag, and robots.txt.

    Args:
        soup: BeautifulSoup of the page.
        response_headers: HTTP response headers dict (case-insensitive lookup attempted).
        robots_allowed: Whether the page's bot is allowed in robots.txt (from RobotsResult).

    Returns:
        IndexabilityResult with conflict flags and directive details.
    """
    result = IndexabilityResult()

    if soup is None:
        return result

    result.checked = True

    # ── Layer 2: <meta name="robots"> ────────────────────────────────────────
    meta_robots = soup.find("meta", attrs={"name": re.compile(r"^robots$", re.IGNORECASE)})
    if meta_robots:
        content = meta_robots.get("content", "").strip()
        if content:
            result.meta_robots_content = content
            parsed = _parse_robots_directive(content)
            result.meta_noindex = parsed["noindex"]
            result.meta_nosnippet = parsed["nosnippet"]
            result.meta_max_snippet = parsed["max_snippet"]

    # ── Layer 3: X-Robots-Tag response header ────────────────────────────────
    # Header names are case-insensitive; normalise to lowercase for lookup
    normalised_headers = {k.lower(): v for k, v in (response_headers or {}).items()}
    x_robots = normalised_headers.get("x-robots-tag", "")
    if x_robots:
        result.x_robots_content = x_robots
        parsed = _parse_robots_directive(x_robots)
        result.x_robots_noindex = parsed["noindex"]
        result.x_robots_nosnippet = parsed["nosnippet"]
        result.x_robots_max_snippet = parsed["max_snippet"]

    # ── Aggregate flags ───────────────────────────────────────────────────────
    result.has_nosnippet = result.meta_nosnippet or result.x_robots_nosnippet
    result.has_noindex = result.meta_noindex or result.x_robots_noindex

    # ── Conflict: robots.txt allows + page-level suppresses ──────────────────
    if robots_allowed and (result.has_noindex or result.has_nosnippet):
        result.robots_meta_conflict = True
        parts = []
        if result.meta_noindex or result.meta_nosnippet:
            parts.append(f"meta robots: '{result.meta_robots_content}'")
        if result.x_robots_noindex or result.x_robots_nosnippet:
            parts.append(f"X-Robots-Tag: '{result.x_robots_content}'")
        directive_summary = "; ".join(parts)
        if result.has_nosnippet and result.has_noindex:
            result.conflict_detail = (
                f"robots.txt allows crawling but page blocks indexing AND snippets ({directive_summary}). "
                "Remove noindex and nosnippet to restore AI citation eligibility."
            )
        elif result.has_nosnippet:
            result.conflict_detail = (
                f"robots.txt allows crawling but page suppresses snippets ({directive_summary}). "
                "nosnippet blocks Google AI Overviews and AI Mode — remove it to restore AI citation."
            )
        else:
            result.conflict_detail = (
                f"robots.txt allows crawling but page blocks indexing ({directive_summary}). "
                "AI crawlers fetch the page but cannot index or cite it."
            )

    return result
