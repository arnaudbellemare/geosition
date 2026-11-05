from __future__ import annotations

import re
from urllib.parse import urlparse

from geo_optimizer.models.results import ContentResult


def audit_content_quality(soup, url: str, soup_clean=None) -> ContentResult:
    """Check content quality for GEO. Returns ContentResult.

    Args:
        soup: BeautifulSoup dell'HTML originale.
        url: URL della pagina.
        soup_clean: (optional) BeautifulSoup pre-cleaned (no script/style).
                    Se fornito, evita il re-parse dell'HTML (fix #285).
    """
    import copy

    result = ContentResult()

    # Fix H-8: guard against None soup (defensive — called from plugins/tests)
    if soup is None:
        return result

    # H1 — presence + uniqueness
    h1_tags = soup.find_all("h1")
    result.h1_count = len(h1_tags)
    if h1_tags:
        result.has_h1 = True
        result.h1_text = h1_tags[0].text.strip()

    # Headings
    headings = soup.find_all(["h1", "h2", "h3", "h4"])
    result.heading_count = len(headings)

    # Fix #285: use pre-computed soup_clean if available, otherwise create a copy
    # Use copy.deepcopy() instead of BS(str(soup)) to avoid costly re-parsing
    if soup_clean is None:
        soup_clean = copy.deepcopy(soup)
        for tag in soup_clean(["script", "style"]):
            tag.decompose()

    # Fix #107: separator=" " prevents word concatenation from adjacent tags
    # Example: <span>Hello</span><span>World</span> → "Hello World" instead of "HelloWorld"
    body_text = soup_clean.get_text(separator=" ", strip=True)
    numbers = re.findall(r"\b\d+[%\u20ac$\u00a3]|\b\d+\.\d+|\b\d{3,}\b", body_text)
    result.numbers_count = len(numbers)
    if len(numbers) >= 3:
        result.has_numbers = True

    # Word count
    words = body_text.split()
    result.word_count = len(words)

    # External links (citations)
    parsed = urlparse(url)
    base_domain = parsed.netloc
    all_links = soup.find_all("a", href=True)
    # Fix F-08: guard against empty base_domain (malformed URL)
    if base_domain:
        external_links = [
            link for link in all_links if link["href"].startswith("http") and base_domain not in link["href"]
        ]
    else:
        external_links = [link for link in all_links if link["href"].startswith("http")]
    result.external_links_count = len(external_links)
    if external_links:
        result.has_links = True

    # External nofollow: count <a rel="nofollow"> on outgoing links
    # AI citation engines follow external links to verify sources; nofollow blocks that.
    nofollow_count = 0
    for link in external_links:
        rel_val = link.get("rel") or []
        # rel attribute is parsed by BS4 as a list of tokens
        if isinstance(rel_val, list):
            rel_tokens = [r.lower() for r in rel_val]
        else:
            rel_tokens = [r.strip().lower() for r in str(rel_val).split()]
        if "nofollow" in rel_tokens:
            nofollow_count += 1
    result.external_nofollow_count = nofollow_count
    if external_links and nofollow_count == len(external_links):
        result.all_external_nofollow = True

    # Text-to-HTML ratio: visible text bytes vs raw HTML bytes
    # Low ratio (< 10%) signals template/boilerplate-heavy pages that AI may
    # treat as thin content even when word count appears adequate.
    raw_html = str(soup)
    raw_html_len = len(raw_html.encode("utf-8", errors="replace"))
    text_len = len(body_text.encode("utf-8", errors="replace"))
    if raw_html_len > 0:
        result.text_html_ratio = round(text_len / raw_html_len, 3)

    # Heading hierarchy: both H2 and H3 present
    h2_tags = soup_clean.find_all("h2")
    h3_tags = soup_clean.find_all("h3")
    if h2_tags and h3_tags:
        result.has_heading_hierarchy = True

    # Lists or tables
    lists = soup_clean.find_all(["ul", "ol", "table"])
    if lists:
        result.has_lists_or_tables = True

    # Front-loading: first 30% of text has substantial content with concrete data
    # Fix #306: threshold was computed incorrectly (always >= 50 for pages >= 50 words)
    if words:
        soglia_30 = max(len(words) * 30 // 100, 1)
        first_30pct = words[:soglia_30]
        # First 30% must have at least 50 words AND contain numbers/statistics
        if len(first_30pct) >= 50:
            numeri_nel_30pct = sum(1 for w in first_30pct if re.search(r"\d", w))
            if numeri_nel_30pct >= 1:
                result.has_front_loading = True

    # Stable anchors: fraction of h2/h3 tags carrying an id= attribute
    # Section-level citations require linkable anchors (e.g. /page#pricing)
    h2_h3 = soup_clean.find_all(["h2", "h3"])
    if h2_h3:
        with_id = sum(1 for h in h2_h3 if h.get("id", "").strip())
        result.headings_with_id = with_id
        result.heading_id_ratio = round(with_id / len(h2_h3), 2)

    # Definition-first: opening paragraph answers the topic in 1–3 sentences
    # Heuristic: first <p> in main content has ≥ 20 words and ends with a period
    # (avoids nav snippets and UI boilerplate)
    _check_definition_first(soup_clean, result)

    return result


def _check_definition_first(soup_clean, result) -> None:
    """Detect whether the page opens with a definitional paragraph near the top.

    Sets result.has_definition_first to True when the first substantive <p>
    has ≥ 20 words and forms a complete sentence (ends with . ! or ?).
    """
    # Skip header/nav/aside — look in <main>, <article>, or <body>
    for container_tag in ("main", "article", "body"):
        container = soup_clean.find(container_tag)
        if container:
            break
    else:
        return

    for p in container.find_all("p"):
        text = p.get_text(separator=" ", strip=True)
        word_count = len(text.split())
        if word_count < 20:
            continue
        # Must end like a complete sentence
        if text[-1] in ".!?":
            result.has_definition_first = True
        return  # Only check the first substantive paragraph
