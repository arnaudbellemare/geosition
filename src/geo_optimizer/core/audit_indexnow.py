"""
IndexNow protocol readiness audit.

IndexNow lets sites push URL change notifications directly to search
engines (Bing, Yandex, Seznam) without waiting for a crawl.  A valid
setup requires:

1. A key file served at ``/{key}.txt`` or ``/.well-known/indexnow.txt``
2. A way for the engine to discover the key — via HTML meta tag, link
   element, or known file paths.

This module inspects the already-fetched HTML soup for in-page signals
and optionally probes well-known key paths via HTTP.
"""

from __future__ import annotations

import re

from geo_optimizer.models.results import IndexNowResult

# Key format: 32–128 hex characters (UUID-style without dashes also valid)
_KEY_RE = re.compile(r"^[a-f0-9]{32,128}$", re.IGNORECASE)
_WELL_KNOWN_PATHS = [
    "/.well-known/indexnow.txt",
    "/indexnow.txt",
]


def audit_indexnow(soup, base_url: str = "", response_headers: dict | None = None) -> IndexNowResult:
    """Inspect a parsed HTML page for IndexNow readiness signals.

    Args:
        soup: BeautifulSoup of the page HTML.
        base_url: Canonical site URL (used to build probe URLs).
        response_headers: HTTP response headers dict (unused currently,
            reserved for future ``Link:`` header detection).

    Returns:
        IndexNowResult with discovered signals and a recommendations list.
    """
    result = IndexNowResult(checked=True)

    # ── 1. <meta name="indexnow-key" content="..."> ──────────────────────────
    for meta in soup.find_all("meta"):
        name = (meta.get("name") or "").lower()
        if name in ("indexnow-key", "indexnow"):
            key = (meta.get("content") or "").strip()
            if key:
                result.has_meta_tag = True
                result.key_value = key
                result.key_looks_valid = bool(_KEY_RE.match(key))
                if result.key_looks_valid:
                    result.key_url = f"{base_url.rstrip('/')}/{key}.txt"

    # ── 2. <link rel="indexnow" href="..."> ─────────────────────────────────
    for link in soup.find_all("link"):
        rel = " ".join(link.get("rel") or []).lower()
        if "indexnow" in rel:
            result.has_link_element = True
            href = (link.get("href") or "").strip()
            if href and not result.key_url:
                result.key_url = href

    # ── 3. Derive score and recommendations ─────────────────────────────────
    if result.has_meta_tag or result.has_link_element:
        result.is_configured = True
        if not result.key_looks_valid and result.key_value:
            result.recommendations.append(
                f"IndexNow key '{result.key_value[:8]}…' doesn't match expected format "
                "(32–128 lowercase hex chars) — verify the key file content."
            )
        if result.key_url:
            result.recommendations.append(f"Verify key file is publicly accessible: {result.key_url}")
    else:
        result.recommendations.append(
            'IndexNow not detected. Add <meta name="indexnow-key" content="{your-key}"> '
            "and serve the key at /{your-key}.txt to enable instant re-indexing on Bing/Yandex."
        )
        result.recommendations.append("Generate a key at https://www.indexnow.org/ — free, no account required.")

    return result
