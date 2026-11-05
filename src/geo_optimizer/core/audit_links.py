"""
GEO Audit — Broken link + 404 detection sub-audit (v4.12).

Crawls all internal links found on the homepage, issues one HEAD request per
unique path (deduped), and classifies each as:

- 200 OK
- 3xx redirect (chain)
- 404 / 410 broken
- 5xx server error
- 0 = timeout / connection failure

Generates a ready-to-paste Vercel redirects JSON block for any 3xx chains
pointing to a different final URL.

Informational check — does not affect GEO score.

Performance note: uses a thread pool (max 8 concurrent) so a page with 40
internal links takes ~2s rather than 40×500ms sequentially.
"""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

from geo_optimizer.models.results import LinkIssue, LinksResult

# Maximum number of unique internal paths to check (avoids very large sites
# spending 60+ seconds checking every URL)
_MAX_LINKS_TO_CHECK = 40

# Maximum external links to check when --check-external is enabled
_MAX_EXTERNAL_LINKS = 50

# Per-request timeout in seconds
_LINK_TIMEOUT = 6

# Thread-pool concurrency
_WORKERS = 8


def audit_links(soup, base_url: str, check_external: bool = False) -> LinksResult:
    """Crawl internal links from soup and check each for HTTP errors.

    Args:
        soup: BeautifulSoup of the homepage.
        base_url: Canonical site URL (e.g. "https://www.example.com").
        check_external: Also HEAD-check external links (slower; off by default).

    Returns:
        LinksResult with broken/redirect lists and a vercel.json redirects block.
    """
    if soup is None or not base_url:
        return LinksResult(checked=True)

    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower()

    # ── Collect unique internal and external URLs ─────────────────────────────
    seen_internal: set[str] = set()
    seen_external: set[str] = set()
    internal_urls: list[tuple[str, str]] = []  # (resolved_url, anchor_text)
    external_urls: list[tuple[str, str]] = []  # (resolved_url, anchor_text)

    for a in soup.find_all("a", href=True):
        href = a["href"].strip()

        # Skip anchors, mailto, tel, js
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue

        resolved = urljoin(base_url, href)
        parsed = urlparse(resolved)
        clean = resolved.split("#")[0].rstrip("/") or resolved
        anchor_text = a.get_text(strip=True)[:80]

        if parsed.netloc.lower() == base_domain:
            if clean not in seen_internal:
                seen_internal.add(clean)
                internal_urls.append((clean, anchor_text))
        elif check_external and parsed.scheme in ("http", "https") and clean not in seen_external:
            seen_external.add(clean)
            external_urls.append((clean, anchor_text))

    total = len(internal_urls)
    sample = internal_urls[:_MAX_LINKS_TO_CHECK]

    # ── Check internal URLs in parallel ──────────────────────────────────────
    broken: list[LinkIssue] = []
    redirects: list[LinkIssue] = []

    results = _check_urls_parallel([(url, anchor) for url, anchor in sample], base_url)

    for url, anchor, status in results:
        if status in (404, 410) or status >= 500 or status == 0:
            broken.append(
                LinkIssue(
                    url=url,
                    status=status,
                    anchor_text=anchor,
                    source_page=base_url,
                )
            )
        elif 300 <= status < 400:
            redirects.append(
                LinkIssue(
                    url=url,
                    status=status,
                    anchor_text=anchor,
                    source_page=base_url,
                )
            )

    # ── Check external URLs in parallel (opt-in) ──────────────────────────────
    external_broken: list[LinkIssue] = []

    if check_external and external_urls:
        ext_sample = external_urls[:_MAX_EXTERNAL_LINKS]
        ext_results = _check_urls_parallel([(url, anchor) for url, anchor in ext_sample], base_url)
        for url, anchor, status in ext_results:
            # 403 counts as broken for external links — it means the URL is
            # inaccessible (often a dead redirect or firewall block on stale links)
            if status in (403, 404, 410) or status >= 500 or status == 0:
                external_broken.append(
                    LinkIssue(
                        url=url,
                        status=status,
                        anchor_text=anchor,
                        source_page=base_url,
                    )
                )

    # ── Generate vercel.json redirects block for 3xx internal URLs ────────────
    vercel_block = _build_vercel_redirects(redirects, base_url)

    # ── Canonical-redirect conflict ───────────────────────────────────────────
    canonical_conflict, canonical_url, canonical_redirects_to = _check_canonical_conflict(soup, base_url)

    # ── Breadcrumb detection ──────────────────────────────────────────────────
    has_breadcrumbs, breadcrumb_type = _detect_breadcrumbs(soup)

    return LinksResult(
        checked=True,
        total_internal_links=total,
        broken_links=broken,
        redirect_chains=redirects,
        broken_count=len(broken),
        vercel_redirects_block=vercel_block,
        external_broken_links=external_broken,
        external_broken_count=len(external_broken),
        canonical_redirect_conflict=canonical_conflict,
        canonical_url=canonical_url,
        canonical_redirects_to=canonical_redirects_to,
        has_breadcrumbs=has_breadcrumbs,
        breadcrumb_type=breadcrumb_type,
    )


# ─── Canonical-redirect conflict ─────────────────────────────────────────────


def _check_canonical_conflict(soup, base_url: str) -> tuple[bool, str, str]:
    """Check whether the page's canonical URL itself redirects.

    A canonical pointing to a URL that then 301s is a self-defeating trust signal:
    the declared authoritative URL is not where the content lives.

    Returns:
        (conflict: bool, canonical_url: str, redirects_to: str)
    """
    from geo_optimizer.utils.http import fetch_url

    canonical_tag = soup.find("link", attrs={"rel": "canonical"}) if soup else None
    if not canonical_tag:
        return False, "", ""

    canonical_url = canonical_tag.get("href", "").strip()
    if not canonical_url or not canonical_url.startswith("http"):
        return False, canonical_url, ""

    # Only check if canonical differs from base_url (same-URL canonical is always fine)
    if canonical_url.rstrip("/") == base_url.rstrip("/"):
        return False, canonical_url, ""

    try:
        r, err = fetch_url(canonical_url, timeout=_LINK_TIMEOUT)
        if err or r is None:
            return False, canonical_url, ""
        if 300 <= r.status_code < 400:
            # Redirect detected — get final URL from Location header if available
            location = r.headers.get("Location", "") if hasattr(r, "headers") else ""
            return True, canonical_url, location
    except (AttributeError, TypeError):
        pass

    return False, canonical_url, ""


# ─── Breadcrumb detection ─────────────────────────────────────────────────────


def _detect_breadcrumbs(soup) -> tuple[bool, str]:
    """Detect breadcrumb navigation in the page.

    Checks three signals:
    1. BreadcrumbList in JSON-LD schema
    2. <nav aria-label="breadcrumb"> or role="navigation" breadcrumb pattern
    3. <ol> or <ul> with breadcrumb-related class/id names

    Returns:
        (found: bool, breadcrumb_type: str) where type is "schema", "nav", "aria" or ""
    """
    import json

    if soup is None:
        return False, ""

    # 1. BreadcrumbList in JSON-LD schema
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        schemas = data.get("@graph", [data]) if isinstance(data, dict) else []
        for s in schemas:
            if isinstance(s, dict) and s.get("@type") == "BreadcrumbList":
                return True, "schema"

    # 2. <nav> with aria-label containing "breadcrumb" (ARIA pattern)
    for nav in soup.find_all("nav"):
        label = (nav.get("aria-label", "") or "").lower()
        if "breadcrumb" in label:
            return True, "aria"

    # 3. ol/ul/div/nav with breadcrumb-related class or id
    _BREADCRUMB_PATTERN = re.compile(r"breadcrumb", re.IGNORECASE)
    for tag in soup.find_all(["ol", "ul", "nav", "div"]):
        cls = " ".join(tag.get("class", []))
        id_ = tag.get("id", "")
        if _BREADCRUMB_PATTERN.search(cls) or _BREADCRUMB_PATTERN.search(id_):
            return True, "nav"

    return False, ""


# ─── Parallel HTTP checks ─────────────────────────────────────────────────────


def _check_urls_parallel(url_anchors: list[tuple[str, str]], base_url: str) -> list[tuple[str, str, int]]:
    """Check a list of (url, anchor) pairs concurrently.

    Returns list of (url, anchor, status_code).
    """
    from geo_optimizer.utils.http import fetch_url

    results: list[tuple[str, str, int]] = []

    def _check(url: str, anchor: str) -> tuple[str, str, int]:
        try:
            r, err = fetch_url(url, timeout=_LINK_TIMEOUT)
            if err or r is None:
                return url, anchor, 0
            return url, anchor, r.status_code
        except (AttributeError, TypeError):
            return url, anchor, 0

    with ThreadPoolExecutor(max_workers=_WORKERS) as pool:
        futures = {pool.submit(_check, url, anchor): (url, anchor) for url, anchor in url_anchors}
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError):
                url, anchor = futures[future]
                results.append((url, anchor, 0))

    return results


# ─── Vercel redirect builder ──────────────────────────────────────────────────


def _build_vercel_redirects(redirects: list[LinkIssue], base_url: str) -> str:
    """Build a vercel.json-compatible redirects JSON block.

    Only includes internal 301/302 links where we can identify a destination
    by stripping common redirect patterns (trailing slash, www normalisation).
    """
    if not redirects:
        return ""

    entries = []

    for issue in redirects:
        parsed = urlparse(issue.url)
        source_path = parsed.path or "/"

        # Heuristic: if the only difference is a trailing slash, suggest the canonical
        canonical_path = source_path.rstrip("/") or "/"
        if canonical_path != source_path:
            entries.append(
                {
                    "source": source_path,
                    "destination": canonical_path,
                    "permanent": True,
                }
            )

    if not entries:
        # Generic placeholder for manual review
        for issue in redirects[:5]:
            parsed = urlparse(issue.url)
            entries.append(
                {
                    "source": parsed.path or "/",
                    "destination": "/<correct-path>",
                    "permanent": True,
                    "_comment": f"HTTP {issue.status} — update destination",
                }
            )

    block = {"redirects": entries}
    return json.dumps(block, indent=2)
