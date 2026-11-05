"""Internal link graph and orphan-page analysis from sitemap URLs."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from geo_optimizer.core.llms_generator import fetch_sitemap
from geo_optimizer.utils.http import fetch_url

_MAX_WORKERS = 8


@dataclass
class LinkGraphResult:
    """Risultato analisi grafo di linking interno."""

    sitemap: str
    pages_discovered: int = 0
    pages_analyzed: int = 0
    internal_edges: int = 0
    orphan_pages: list[str] = field(default_factory=list)
    weakly_linked_pages: list[str] = field(default_factory=list)
    in_degree: dict[str, int] = field(default_factory=dict)
    out_degree: dict[str, int] = field(default_factory=dict)
    recommendations: list[str] = field(default_factory=list)
    error: str = ""


def analyze_link_graph(sitemap_url: str, max_pages: int = 30) -> LinkGraphResult:
    """Scarica una sitemap e costruisce il grafo di link interni."""
    entries = fetch_sitemap(sitemap_url)
    if not entries:
        return LinkGraphResult(sitemap=sitemap_url, error="No URLs found in sitemap")

    urls = _select_urls(entries, max_pages=max_pages)
    html_map: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        future_map = {pool.submit(_fetch_html, url): url for url in urls}
        for future in as_completed(future_map):
            url = future_map[future]
            html = future.result()
            if html:
                html_map[url] = html

    return analyze_link_graph_from_html_map(sitemap_url, urls, html_map)


def analyze_link_graph_from_html_map(
    sitemap_url: str,
    urls: list[str],
    html_map: dict[str, str],
) -> LinkGraphResult:
    """Analizza un grafo interno dato un mapping URL->HTML (testabile offline)."""
    normalized_urls = [_normalize_url(u) for u in urls]
    url_set = set(normalized_urls)
    in_degree = dict.fromkeys(normalized_urls, 0)
    out_degree = dict.fromkeys(normalized_urls, 0)
    edges: set[tuple[str, str]] = set()

    for original_url in urls:
        page_url = _normalize_url(original_url)
        html = html_map.get(original_url) or html_map.get(page_url)
        if not html:
            continue
        soup = BeautifulSoup(html, "html.parser")
        links = _extract_internal_links(soup, page_url)
        targets = {t for t in links if t in url_set and t != page_url}
        out_degree[page_url] = len(targets)
        for target in targets:
            edges.add((page_url, target))
            in_degree[target] += 1

    homepage = _infer_homepage(normalized_urls)
    orphan_pages = sorted([u for u, degree in in_degree.items() if degree == 0 and u != homepage])
    weak_pages = sorted([u for u, degree in out_degree.items() if degree <= 1])

    result = LinkGraphResult(
        sitemap=sitemap_url,
        pages_discovered=len(normalized_urls),
        pages_analyzed=len([u for u in normalized_urls if (u in html_map or _denormalize_match(u, html_map))]),
        internal_edges=len(edges),
        orphan_pages=orphan_pages,
        weakly_linked_pages=weak_pages[:20],
        in_degree=in_degree,
        out_degree=out_degree,
    )
    result.recommendations = _build_recommendations(result)
    return result


def _select_urls(entries, max_pages: int) -> list[str]:
    seen: set[str] = set()
    urls: list[str] = []
    for entry in entries:
        url = getattr(entry, "url", "")
        normalized = _normalize_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
        if len(urls) >= max_pages:
            break
    return urls


def _fetch_html(url: str) -> str:
    response, err = fetch_url(url)
    if err or response is None:
        return ""
    try:
        return response.content.decode(response.encoding or "utf-8", errors="replace")
    except (UnicodeDecodeError, LookupError):
        return response.text or ""


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    no_fragment = url.split("#", 1)[0]
    return no_fragment.rstrip("/") or no_fragment


def _extract_internal_links(soup, page_url: str) -> set[str]:
    parsed = urlparse(page_url)
    domain = parsed.netloc.lower()
    links: set[str] = set()
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        resolved = _normalize_url(urljoin(page_url, href))
        if not resolved:
            continue
        if urlparse(resolved).netloc.lower() == domain:
            links.add(resolved)
    return links


def _infer_homepage(urls: list[str]) -> str:
    for url in urls:
        parsed = urlparse(url)
        if parsed.path in ("", "/"):
            return url
    return urls[0] if urls else ""


def _build_recommendations(result: LinkGraphResult) -> list[str]:
    recs: list[str] = []
    if result.error:
        return [result.error]
    if result.orphan_pages:
        recs.append(f"Link to orphan pages from hub pages/navigation ({len(result.orphan_pages)} orphan pages).")
    if result.weakly_linked_pages:
        recs.append("Increase contextual internal links for pages with <=1 outgoing links.")
    if result.internal_edges < max(5, result.pages_discovered // 2):
        recs.append("Strengthen overall internal linking mesh; add cross-links between related pages.")
    if not recs:
        recs.append("Internal link graph looks healthy. Monitor monthly after content updates.")
    return recs


def _denormalize_match(normalized: str, html_map: dict[str, str]) -> bool:
    if normalized in html_map:
        return True
    alt = normalized + "/"
    return alt in html_map
