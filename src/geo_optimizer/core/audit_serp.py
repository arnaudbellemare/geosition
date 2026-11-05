"""
SERP competitor gap analysis — v1.0

Workflow:
  1. Extract main keyword from the audited page (title → H1 → meta description)
  2. Search Google (no API key — uses the public HTML endpoint with a browser UA)
     Falls back to Bing, then DuckDuckGo if Google returns no results.
  3. Fetch and analyze top-10 organic results (content length, H2s, schema, FAQ, video)
  4. Compare against the audited page and produce an actionable gap report
  5. Generate service × city location page suggestions based on the keyword + vertical
"""

from __future__ import annotations

import re
import time
import urllib.parse
from typing import TypedDict, cast

from geo_optimizer.models.results import SerpCompetitor, SerpResult


class _SerpSearchResult(TypedDict):
    rank: int
    url: str
    title: str
    description: str


# Google HTML search — Canadian locale, 10 results
_GOOGLE_URL = "https://www.google.ca/search?q={query}&num=10&hl=fr&gl=ca"
_BING_URL = "https://www.bing.com/search?q={query}&count=10&mkt=fr-CA"
_DDG_URL = "https://html.duckduckgo.com/html/?q={query}&kl=ca-en"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-CA,fr;q=0.9,en-CA;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    # Intentionally omit "br" — requests has no built-in Brotli decoder and
    # sites that return Content-Encoding: br produce garbled text without it.
    "Accept-Encoding": "gzip, deflate",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

# Canadian cities for location page suggestions (comprehensive)
_CA_CITIES = [
    "Montreal",
    "Laval",
    "Longueuil",
    "Brossard",
    "Boucherville",
    "Repentigny",
    "Terrebonne",
    "Saint-Jean-sur-Richelieu",
    "Blainville",
    "Mirabel",
    "Mascouche",
    "Châteauguay",
    "Saint-Jérôme",
    "Varennes",
    "Quebec City",
    "Levis",
    "Saguenay",
    "Sherbrooke",
    "Trois-Rivières",
    "Ottawa",
    "Gatineau",
    "Toronto",
    "Calgary",
    "Edmonton",
    "Vancouver",
]


# Slug-ify a city name for URL paths
def _slugify(text: str) -> str:
    s = text.lower().replace("é", "e").replace("è", "e").replace("ê", "e")
    s = s.replace("à", "a").replace("â", "a").replace("î", "i").replace("ô", "o")
    s = s.replace("û", "u").replace("ç", "c").replace("ë", "e")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _extract_keyword(soup, result) -> str:
    """Pull the most descriptive keyword from the page."""
    # 1. Title tag (clean)
    if soup:
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)
            # Remove brand suffix ("… | Brand Name", "… – Brand")
            title = re.split(r"\s*[\|\–\-—]\s*", title)[0].strip()
            if len(title) > 5:
                return title

    # 2. H1
    if soup:
        h1 = soup.find("h1")
        if h1:
            h1_text = h1.get_text(strip=True)
            if len(h1_text) > 5:
                return cast(str, h1_text[:80])

    # 3. Meta description first 60 chars
    if soup:
        meta = soup.find("meta", attrs={"name": "description"})
        if meta and meta.get("content"):
            return cast(str, meta["content"][:60].strip())

    # 4. URL-derived fallback
    if hasattr(result, "url"):
        from urllib.parse import urlparse

        hostname = urlparse(result.url).hostname or ""
        return hostname.replace("www.", "").replace("-", " ")

    return ""


def _parse_google(html: str) -> list[_SerpSearchResult]:
    """Parse Google HTML search results page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: list[_SerpSearchResult] = []
    rank = 0

    # Google organic results: <div class="g"> containing <a> with h3
    for div in soup.find_all("div", class_="g"):
        # Skip featured snippets and ads
        if div.find_parent(class_=re.compile(r"ULSxyf|RNNXgb|commercial")):
            continue

        a_tag = div.find("a", href=True)
        h3 = div.find("h3")
        if not a_tag or not h3:
            continue

        href = a_tag["href"]
        # Skip internal Google URLs
        if not href.startswith("http") or "google." in href:
            continue

        snippet_tag = div.find("div", {"data-sncf": True}) or div.find(class_=re.compile(r"VwiC3b|lEBKkf|st"))
        snippet = snippet_tag.get_text(strip=True)[:200] if snippet_tag else ""

        rank += 1
        results.append(
            {
                "rank": rank,
                "url": href,
                "title": h3.get_text(strip=True),
                "description": snippet,
            }
        )
        if rank >= 10:
            break

    return results


def _parse_bing(html: str) -> list[_SerpSearchResult]:
    """Parse Bing HTML search results page."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: list[_SerpSearchResult] = []
    rank = 0

    for li in soup.select("#b_results > li.b_algo"):
        a_tag = li.find("a", href=True)
        h2 = li.find("h2")
        snippet = li.select_one(".b_caption p")
        if not a_tag or not h2:
            continue
        href = a_tag["href"]
        if not href.startswith("http"):
            continue
        rank += 1
        results.append(
            {
                "rank": rank,
                "url": href,
                "title": h2.get_text(strip=True),
                "description": snippet.get_text(strip=True) if snippet else "",
            }
        )
        if rank >= 10:
            break

    return results


def _parse_ddg(html: str) -> list[_SerpSearchResult]:
    """Parse DuckDuckGo HTML search results page (last-resort fallback)."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    results: list[_SerpSearchResult] = []
    rank = 0

    for div in soup.select(".result"):
        classes = div.get("class") or []
        if any("ad" in c for c in classes):
            continue
        title_a = div.select_one(".result__a")
        url_span = div.select_one(".result__url")
        snippet = div.select_one(".result__snippet")
        if not title_a:
            continue

        raw_url = " ".join(url_span.get_text().split()) if url_span else ""  # collapse whitespace
        raw_url = raw_url.strip()
        if raw_url and not raw_url.startswith("http"):
            raw_url = "https://" + raw_url

        if not raw_url:
            href = title_a.get("href", "")
            uddg = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("uddg", [""])[0]
            raw_url = urllib.parse.unquote(uddg) if uddg else ""

        if not raw_url:
            continue

        rank += 1
        results.append(
            {
                "rank": rank,
                "url": raw_url,
                "title": title_a.get_text(strip=True),
                "description": snippet.get_text(strip=True) if snippet else "",
            }
        )
        if rank >= 10:
            break

    return results


def _search_google(keyword: str) -> list[_SerpSearchResult]:
    """
    Fetch first-page results for the keyword.
    Engine priority: DuckDuckGo → Bing (with redirect resolution) → Google.

    DDG is used first because it returns clean HTML with no JS challenge.
    Google is last because it serves a JS-redirect page to non-browser clients.
    Returns list of dicts: {rank, url, title, description}
    """
    import requests

    query = urllib.parse.quote_plus(keyword)

    # Resolve Bing's /ck/a redirect URLs
    def _resolve_bing_url(href: str) -> str:
        if "bing.com/ck/a" not in href:
            return href
        from geo_optimizer.utils.http import fetch_url

        try:
            r, err = fetch_url(href, timeout=5, max_size=256 * 1024)
            if err or r is None:
                return ""
            final = r.url
            if "bing.com" not in final:
                return final
        except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError):
            pass
        return ""

    engines = [
        (_DDG_URL.format(query=query), _parse_ddg, "DuckDuckGo"),
        (_BING_URL.format(query=query), _parse_bing, "Bing"),
        (_GOOGLE_URL.format(query=query), _parse_google, "Google"),
    ]

    for url, parser, name in engines:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=14, allow_redirects=True)
            if r.status_code != 200:
                continue
            results = parser(r.text)
            if name == "Bing":
                # Resolve Bing redirect URLs
                resolved = []
                for item in results:
                    real_url = _resolve_bing_url(item["url"])
                    if real_url:
                        item["url"] = real_url
                        resolved.append(item)
                results = resolved
            if results:
                return results
        except (requests.exceptions.RequestException, ValueError, AttributeError):
            continue

    return []


def _analyze_competitor(rank: int, url: str, title: str, description: str) -> SerpCompetitor:
    """Fetch a competitor URL and extract SEO signals."""
    from bs4 import BeautifulSoup

    comp = SerpCompetitor(rank=rank, url=url, title=title, description=description)

    try:
        from geo_optimizer.utils.http import fetch_url

        r, err = fetch_url(url, timeout=10)
        if err or r is None or r.status_code != 200:
            return comp

        soup = BeautifulSoup(r.text, "html.parser")

        # H1
        h1 = soup.find("h1")
        comp.h1 = h1.get_text(strip=True)[:120] if h1 else ""

        # H2s — count and text for keyword gap analysis
        h2_tags = soup.find_all("h2")
        comp.h2_count = len(h2_tags)
        comp.h2_texts = [h2.get_text(strip=True) for h2 in h2_tags if h2.get_text(strip=True)]

        # Word count (body text)
        body = soup.find("body")
        if body:
            text = body.get_text(separator=" ", strip=True)
            comp.word_count = len(text.split())
            comp.content_snippet = text[:200]

        # Schema
        schema_tags = soup.find_all("script", type="application/ld+json")
        if schema_tags:
            comp.has_schema = True
            types = []
            import json

            for tag in schema_tags:
                try:
                    data = json.loads(tag.string or "")
                    if isinstance(data, dict):
                        t = data.get("@type", "")
                        if t:
                            types.append(t if isinstance(t, str) else str(t))
                    elif isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict):
                                t = item.get("@type", "")
                                if t:
                                    types.append(t if isinstance(t, str) else str(t))
                except (ValueError, AttributeError, KeyError):
                    pass
            comp.schema_types = list(dict.fromkeys(types))

        # FAQ detection
        comp.has_faq = bool(
            soup.find(class_=re.compile(r"faq|accordion|question", re.I))
            or soup.find(id=re.compile(r"faq|accordion|question", re.I))
            or "FAQPage" in str(comp.schema_types)
        )

        # Video
        comp.has_video = bool(soup.find("video") or soup.find("iframe", src=re.compile(r"youtube|vimeo|loom", re.I)))

        # Images
        comp.has_images = bool(soup.find("img"))

        # Internal links (same domain)
        from urllib.parse import urlparse

        domain = urlparse(url).netloc
        links = soup.find_all("a", href=True)
        comp.internal_links = sum(1 for a in links if urlparse(a["href"]).netloc in ("", domain))

        # Location-page signal: check for city/location patterns in internal links
        _loc_pattern = re.compile(r"/(?:location|locations|cities|villes|secteur)/", re.I)
        comp.has_location_pages = any(_loc_pattern.search(a["href"]) for a in links)

    except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError):
        pass

    return comp


def _build_location_suggestions(keyword: str, vertical: str) -> list[str]:
    """
    Generate service × city page slug suggestions.
    e.g. keyword="syndicat de copropriété Montreal" → ["/syndicat-de-copropriete-montreal/", ...]
    """
    # Extract the service part by stripping known city names from keyword
    service_part = keyword
    for city in _CA_CITIES:
        service_part = re.sub(rf"\b{re.escape(city)}\b", "", service_part, flags=re.IGNORECASE)
    service_part = re.sub(r"\s+", " ", service_part).strip(" ,.-")

    # If service_part is too short, derive from vertical
    if len(service_part) < 5:
        _vertical_services = {
            "real-estate-proptech": ["gestion-immobiliere", "syndicat-de-copropriete", "gestion-locative"],
            "saas": ["logiciel", "solution", "plateforme"],
            "e-commerce": ["boutique", "livraison", "commande"],
            "legal": ["avocat", "cabinet-juridique", "consultation-juridique"],
            "health": ["clinique", "medecin", "sante"],
            "restaurant": ["restaurant", "traiteur", "livraison-repas"],
        }
        services = _vertical_services.get(vertical, ["service"])
    else:
        services = [_slugify(service_part)]

    suggestions = []
    for service in services[:2]:
        for city in _CA_CITIES[:12]:
            slug = f"/{service}-{_slugify(city)}/"
            suggestions.append(slug)

    return suggestions[:24]  # cap at 24 suggestions


def audit_serp(
    soup,
    base_url: str,
    result=None,
    vertical: str = "auto",
    rival_urls: list[str] | None = None,
    keyword: str | None = None,
) -> SerpResult:
    """
    Run SERP competitor analysis for the audited page.

    If *rival_urls* is provided those URLs are analysed directly (the user
    looked up their real Google competitors) instead of running a SERP search.
    Otherwise the tool searches DuckDuckGo → Bing → Google and analyses the
    top-10 organic results.

    Args:
        keyword: Override the auto-detected keyword. When provided, skips
                 title/H1 extraction and uses this string directly for the
                 Google search and all gap analysis.

    Returns gap analysis and location page suggestions.
    """
    serp = SerpResult(checked=True)

    # 1. Resolve keyword: explicit override > auto-extracted from title/H1
    if keyword and keyword.strip():
        serp.keyword = keyword.strip()
    else:
        serp.keyword = _extract_keyword(soup, result)
        if not serp.keyword:
            serp.checked = False
            serp.issues = ["Could not extract a meaningful keyword from the page."]
            return serp

    # ── Path A: user-supplied competitor URLs (real Google ranking) ───────────
    raw_results: list[_SerpSearchResult]
    if rival_urls:
        serp.search_engine = "Google (manual)"
        raw_results = [
            {
                "rank": i + 1,
                "url": u if u.startswith("http") else "https://" + u,
                "title": "",
                "description": "",
            }
            for i, u in enumerate(rival_urls[:10])
        ]

    # ── Path B: automated SERP search ─────────────────────────────────────────
    else:
        serp.search_engine = "google (first page)"

        try:
            raw_results = _search_google(serp.keyword)
        except (ValueError, TypeError, KeyError, AttributeError, OSError, RuntimeError) as e:
            serp.issues = [f"SERP fetch failed: {e}"]
            return serp

        if not raw_results:
            serp.issues = ["No SERP results returned — try running with --keyword to override."]
            return serp

    # 3. Analyze competitors (rate-limited: 1 req/sec)
    competitors = []
    for item in raw_results[:10]:
        comp = _analyze_competitor(
            rank=item["rank"],
            url=item["url"],
            title=item["title"],
            description=item["description"],
        )
        competitors.append(comp)
        time.sleep(0.8)  # be polite

    serp.competitors = competitors

    # 4. Gap analysis
    word_counts = [c.word_count for c in competitors if c.word_count > 0]
    if word_counts:
        serp.avg_competitor_word_count = int(sum(word_counts) / len(word_counts))

    # Your word count from the soup
    if soup:
        body = soup.find("body")
        if body:
            serp.your_word_count = len(body.get_text(separator=" ", strip=True).split())

    serp.word_count_gap = max(0, serp.avg_competitor_word_count - serp.your_word_count)
    serp.avg_competitor_h2s = sum(c.h2_count for c in competitors) / len(competitors) if competitors else 0.0
    serp.competitors_with_schema = sum(1 for c in competitors if c.has_schema)
    serp.competitors_with_faq = sum(1 for c in competitors if c.has_faq)
    serp.competitors_with_video = sum(1 for c in competitors if c.has_video)
    serp.competitors_with_location_pages = sum(1 for c in competitors if c.has_location_pages)

    serp_features: list[str] = []
    if serp.competitors_with_faq:
        serp_features.append("faq")
    if serp.competitors_with_video:
        serp_features.append("video")
    if any(c.has_images for c in competitors):
        serp_features.append("images")
    if serp.competitors_with_schema:
        serp_features.append("structured_data")
    if serp.competitors_with_location_pages:
        serp_features.append("local_pack_pressure")
    from geo_optimizer.core.seo_intelligence import score_serp_crowdedness

    crowdedness = score_serp_crowdedness(
        keyword=serp.keyword,
        organic_results=len(competitors),
        competitor_domains=[urllib.parse.urlparse(c.url).hostname or c.url for c in competitors],
        serp_features=serp_features,
    )
    serp.crowdedness_score = crowdedness.score
    serp.crowdedness_label = crowdedness.label
    serp.serp_features = crowdedness.serp_features

    # 4b. Keyword gap analysis — topics in competitor H2s not on our page
    your_text = ""
    if soup:
        body = soup.find("body")
        if body:
            your_text = body.get_text(separator=" ", strip=True).lower()

    # Collect all competitor H2 texts (non-empty, deduplicated)
    all_h2_texts: list[str] = []
    seen: set[str] = set()
    for comp in competitors:
        for h2 in comp.h2_texts:
            h2_lower = h2.lower().strip()
            if h2_lower and h2_lower not in seen:
                seen.add(h2_lower)
                all_h2_texts.append(h2)

    # A competitor H2 is a "gap" when its key tokens don't appear in our page text
    _stop_words = {
        "de",
        "du",
        "la",
        "le",
        "les",
        "des",
        "et",
        "en",
        "a",
        "au",
        "aux",
        "par",
        "sur",
        "un",
        "une",
        "the",
        "of",
        "for",
        "in",
        "and",
        "or",
        "our",
        "your",
        "nos",
        "votre",
        "vos",
        "comment",
        "how",
        "what",
        "pourquoi",
        "why",
        "qui",
        "who",
    }

    gaps: list[str] = []
    for h2 in all_h2_texts:
        tokens = [t.lower() for t in re.split(r"[\s\-–|,?!.]+", h2) if len(t) >= 4 and t.lower() not in _stop_words]
        if tokens and not any(t in your_text for t in tokens):
            gaps.append(h2)
        if len(gaps) >= 10:
            break

    serp.keyword_gaps = gaps

    # Build "to rank page 1 you need:" action list
    p1_reqs: list[str] = []
    if serp.word_count_gap > 200:
        p1_reqs.append(
            f"Write at least {serp.avg_competitor_word_count} words of structured content "
            f"(your page has ~{serp.your_word_count} — gap: {serp.word_count_gap} words)."
        )
    if gaps:
        gap_examples = "; ".join(f'"{g}"' for g in gaps[:4])
        p1_reqs.append(f"Add H2 sections covering topics your competitors rank for but you don't: {gap_examples}.")
    if serp.competitors_with_schema >= 6:
        p1_reqs.append(
            f"Implement structured data (schema.org) — {serp.competitors_with_schema}/10 "
            "first-page competitors use it (LocalBusiness + Service at minimum)."
        )
    if serp.competitors_with_faq >= 4:
        p1_reqs.append(
            f"Add a FAQ section ({serp.competitors_with_faq}/10 competitors have one) "
            "— targets 'People also ask' and AI answer boxes."
        )
    if serp.competitors_with_video >= 3:
        p1_reqs.append(
            f"Embed at least one video ({serp.competitors_with_video}/10 competitors do) "
            "— increases dwell time and can appear in Google video carousels."
        )
    if serp.competitors_with_location_pages >= 3:
        p1_reqs.append(
            f"{serp.competitors_with_location_pages}/10 competitors have dedicated location pages "
            "— create service × city pages to capture local keyword variations."
        )

    serp.page1_requirements = p1_reqs

    # 5. Issues
    if serp.word_count_gap > 300:
        serp.issues.append(
            f"Your page has ~{serp.your_word_count} words vs avg {serp.avg_competitor_word_count} "
            f"for top competitors — gap of {serp.word_count_gap} words."
        )
    if serp.competitors_with_schema >= 6:
        serp.issues.append(
            f"{serp.competitors_with_schema}/10 top competitors use structured data schema — "
            "schema is a baseline expectation for first-page ranking."
        )
    if serp.competitors_with_faq >= 4:
        serp.issues.append(
            f"{serp.competitors_with_faq}/10 competitors have an FAQ section — "
            "FAQ content captures 'People also ask' SERP real estate."
        )
    if serp.competitors_with_video >= 3:
        serp.issues.append(
            f"{serp.competitors_with_video}/10 competitors embed video — "
            "video increases dwell time and can appear in video carousels."
        )

    # 6. Suggestions
    serp.suggestions = [
        f'Target keyword: "{serp.keyword}" — create dedicated, standalone content for this term.',
        f"Aim for {serp.avg_competitor_word_count}+ words of structured content to match top competitors.",
        f"Add {round(serp.avg_competitor_h2s)} H2 sections minimum (competitor avg is {serp.avg_competitor_h2s:.1f}).",
    ]
    if serp.competitors_with_faq >= 4:
        serp.suggestions.append("Add a FAQ section with 5-8 questions — targets 'People also ask' and AI citations.")

    # 7. Location page suggestions
    serp.location_page_suggestions = _build_location_suggestions(serp.keyword, vertical)

    return serp
