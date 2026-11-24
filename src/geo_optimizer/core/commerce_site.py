"""Bounded, read-only site audit built on the protected HTTP fetcher."""

from __future__ import annotations

import json
import os
import subprocess
import time
from collections import deque
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urldefrag, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

from bs4 import BeautifulSoup

from geo_optimizer.core.commerce_browser_access import build_browser_access, observe_fetch
from geo_optimizer.core.commerce_readiness import analyze_commerce_html
from geo_optimizer.core.commerce_recommendations import build_site_recommendations
from geo_optimizer.models.results.commerce_site import CommerceSiteReport
from geo_optimizer.utils.http import fetch_url


def _origin(url):
    p = urlsplit(url)
    return p.scheme.lower(), p.netloc.lower()


def _page_url(url, origin):
    url = urldefrag(url)[0]
    p = urlsplit(url)
    if _origin(url) != origin or p.username or p.password or p.scheme not in ("http", "https"):
        return None
    if p.query or p.path.lower().endswith((".jpg", ".png", ".webp", ".pdf", ".xml", ".css", ".js", ".svg")):
        return None
    if any(
        part in p.path.lower().split("/") for part in ("logout", "log-out", "signout", "checkout", "cart", "delete")
    ):
        return None
    return urlunsplit((p.scheme, p.netloc, p.path or "/", "", ""))


def render_page(url, html):
    """Render with only same-origin scripts fetched via GEOSITION; browser network is blocked."""
    soup = BeautifulSoup(html, "html.parser")
    scripts = {}
    warnings = []
    script_elements = soup.select("script[src]")
    if len(script_elements) > 20:
        warnings.append("Only the first 20 external scripts were considered.")
    for script in script_elements[:20]:
        source = urljoin(url, script["src"])
        if _origin(source) != _origin(url):
            warnings.append("Cross-origin scripts were not loaded.")
            continue
        response, error = fetch_url(source, timeout=5, max_size=1024 * 1024)
        if error or response is None or response.status_code != 200 or _origin(response.url) != _origin(url):
            warnings.append("A same-origin script could not be loaded safely.")
            continue
        scripts[source] = response.text
    payload = json.dumps({"url": url, "html": html, "scripts": scripts})
    try:
        process = subprocess.run(
            ["node", str(Path(__file__).with_name("commerce_render.cjs"))],
            input=payload,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
            env=os.environ.copy(),
        )
        if process.returncode:
            return None, ["Browser rendering unavailable or failed: " + process.stderr[-500:]]
        return json.loads(process.stdout)["html"], list(dict.fromkeys(warnings))
    except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as exc:
        return None, [f"Browser rendering unavailable or failed: {exc}"]


def run_site_audit(url, max_pages=25, render=False):
    """Audit same-origin pages linked from the starting page or root sitemap."""
    url = url if url.startswith(("https://", "http://")) else "https://" + url
    p = urlsplit(url)
    origin = _origin(url)
    root = f"{p.scheme}://{p.netloc}/"
    start = _page_url(url, origin)
    if start is None:
        raise ValueError("Start URL must be an HTTP(S) page on the site.")
    robots_response, robots_error = fetch_url(urljoin(root, "robots.txt"), timeout=5)
    robot = RobotFileParser()
    robots_ok = robots_response is not None and not robots_error and robots_response.status_code in (200, 404)
    robot.parse(robots_response.text.splitlines() if robots_ok and robots_response.status_code == 200 else [])
    sitemap_response, sitemap_error = fetch_url(urljoin(root, "sitemap.xml"), timeout=5)
    queue = deque([start])
    discovered = {start}
    warnings = []
    if not robots_ok:
        warnings.append("robots.txt unavailable; only the requested page was audited.")
    sitemap_queue = deque()
    if sitemap_response is not None and not sitemap_error and sitemap_response.status_code == 200:
        sitemap_queue.append(sitemap_response.text)
    seen_sitemaps = set()
    while sitemap_queue and len(seen_sitemaps) < 8:
        content = sitemap_queue.popleft()
        seen_sitemaps.add(content[:200] + str(len(content)))
        try:
            if "<!DOCTYPE" in content.upper():
                raise ElementTree.ParseError("DOCTYPE is not supported")
            tree = ElementTree.fromstring(content)
            is_index = tree.tag.split("}")[-1] == "sitemapindex"
            for node in tree.iter():
                if node.tag.split("}")[-1] != "loc" or not node.text:
                    continue
                target = node.text.strip()
                if is_index:
                    if (
                        _origin(target) != origin
                        or target in seen_sitemaps
                        or len(seen_sitemaps) + len(sitemap_queue) >= 8
                    ):
                        warnings.append("Some sitemap indexes were not followed due to scope or limit.")
                        continue
                    child, error = fetch_url(target, timeout=5)
                    if child is not None and not error and child.status_code == 200:
                        sitemap_queue.append(child.text)
                    else:
                        warnings.append("A sitemap index entry could not be fetched.")
                else:
                    candidate = _page_url(target, origin)
                    if candidate and candidate not in discovered:
                        queue.append(candidate)
                        discovered.add(candidate)
        except ElementTree.ParseError:
            warnings.append("Sitemap could not be parsed.")
    pages, failures, skipped = [], [], []
    browser_observations = []
    deadline = time.monotonic() + 180
    while queue and len(pages) + len(failures) < max_pages and time.monotonic() < deadline:
        current = queue.popleft()
        if current != start and (not robots_ok or not robot.can_fetch("*", current)):
            skipped.append({"url": current, "reason": "robots.txt disallows or is unavailable"})
            continue
        response, error = fetch_url(current, timeout=5)
        browser_observations.append(observe_fetch(current, response, error))
        if error or response is None or response.status_code not in (200, 203):
            failures.append({"url": current, "error": error or f"HTTP {response.status_code}"})
            continue
        final = getattr(response, "url", current)
        if not isinstance(final, str) or _origin(final) != origin:
            failures.append(
                {
                    "url": current,
                    "error": "Redirected outside the starting origin; content not audited.",
                }
            )
            continue
        html = response.text
        render_warnings = []
        render_status = "not_requested"
        if render:
            rendered, render_warnings = render_page(final, html)
            render_status = ("partial" if render_warnings else "rendered") if rendered is not None else "failed"
            if rendered is not None:
                html = rendered
        page = asdict(analyze_commerce_html(final, html))
        page["limitations"] = [x for x in page["limitations"] if not x.startswith("One page")]
        if render:
            page["limitations"].append(
                "Browser network requests are blocked; API, third-party and interactive content may be missing."
            )
        page["render_status"] = render_status
        page["render_warnings"] = render_warnings
        soup = BeautifulSoup(html, "html.parser")
        page["catalog_signals"] = []
        for card in soup.select(".card, [itemtype*='schema.org/Product']"):
            heading, price = (
                card.select_one("h1,h2,h3,h4"),
                card.select_one(".price, [itemprop=price]"),
            )
            if heading and price:
                page["catalog_signals"].append(
                    {
                        "name": heading.get_text(" ", strip=True),
                        "price_text": price.get_text(" ", strip=True),
                        "evidence": "HTML card heuristic; not verified product data",
                    }
                )
        pages.append(page)
        if robots_ok:
            for link in soup.select("a[href]"):
                candidate = _page_url(urljoin(final, link["href"]), origin)
                if candidate and candidate not in discovered:
                    discovered.add(candidate)
                    queue.append(candidate)
    if not pages:
        reason = failures[0]["error"] if failures else "No pages could be audited."
        raise ValueError(reason)
    if queue and time.monotonic() >= deadline:
        warnings.append("Time limit reached; some discovered pages remain unaudited.")
    report = CommerceSiteReport(
        url=url,
        browser_access=build_browser_access(browser_observations),
        pages=pages,
        failures=failures,
        skipped=skipped,
        warnings=warnings,
        coverage={
            "pages_audited": len(pages),
            "max_pages": max_pages,
            "pending": len(queue),
            "complete": not queue
            and not failures
            and not skipped
            and not warnings
            and all(p["render_status"] not in ("partial", "failed") for p in pages),
            "scope": "Discovered same-origin pages only; query URLs and transactional paths excluded.",
            "render_requested": render,
        },
    )

    report.recommendations = build_site_recommendations(asdict(report))
    return report
