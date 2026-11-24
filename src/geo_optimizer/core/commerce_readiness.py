"""Inspect observable commerce signals without asserting partner eligibility."""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from geo_optimizer.core.citability._helpers import _iter_jsonld_items, _jsonld_types
from geo_optimizer.models.results.commerce import CommerceReadinessReport
from geo_optimizer.utils.http import fetch_url


def _present(value: object) -> bool:
    return value is not None and value != "" and value != [] and value != {}


def _product(item: dict) -> dict:
    raw = item.get("offers")
    offers = [raw] if isinstance(raw, dict) else raw if isinstance(raw, list) else []
    offers = [offer for offer in offers if isinstance(offer, dict)]
    fields = {key: _present(item.get(key)) for key in ("name", "description", "image", "sku")}
    for key, aliases in (
        ("price", ("price", "lowPrice")),
        ("currency", ("priceCurrency",)),
        ("availability", ("availability",)),
    ):
        fields[key] = any(_present(offer.get(alias)) for offer in offers for alias in aliases)
    return {
        "name": str(item.get("name") or "Unnamed product"),
        "fields": fields,
        "evidence": "Product JSON-LD on the audited page; presence only",
    }


def _nested_items(soup):
    """Walk JSON-LD objects including nested ItemList entries, without duplicates."""
    pending = list(reversed(_iter_jsonld_items(soup)))
    seen = set()
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            if id(item) in seen:
                continue
            seen.add(id(item))
            yield item
            pending.extend(reversed(list(item.values())))
        elif isinstance(item, list):
            pending.extend(reversed(item))


def run_commerce_readiness(url: str) -> CommerceReadinessReport:
    """Fetch one public page using the existing secure HTTP stack and inspect it."""
    url = url if url.startswith(("http://", "https://")) else "https://" + url
    response, error = fetch_url(url)
    if error or response is None:
        raise ValueError(f"Unable to fetch page: {error or 'connection failed'}")
    if response.status_code not in (200, 203):
        raise ValueError(f"Unable to fetch page: HTTP {response.status_code}")
    return analyze_commerce_html(url, response.text)


def analyze_commerce_html(url: str, html: str) -> CommerceReadinessReport:
    """Inspect supplied HTML; caller is responsible for obtaining it safely."""
    soup = BeautifulSoup(html, "html.parser")
    items = list(_nested_items(soup))
    products = [_product(item) for item in items if "Product" in _jsonld_types(item)]
    services = []
    service_ids = set()
    for item in items:
        if "Service" not in _jsonld_types(item):
            continue
        identifier = item.get("@id")
        if isinstance(identifier, str):
            if identifier in service_ids:
                continue
            service_ids.add(identifier)
        services.append(str(item.get("name") or "Unnamed service"))
    signals = []
    patterns = (
        ("cart", r"\b(cart|basket|panier)\b"),
        ("booking", r"\b(book|booking|appointment|rendez-vous|réserver)\b"),
        ("enquiry", r"\b(contact(?:er|ez)?|enquir(?:y|e)|inquiry|quote|devis|proposition)\b"),
    )
    for element in soup.select("a[href], button"):
        label = element.get_text(" ", strip=True) or element.get("aria-label", "")
        for kind, pattern in patterns:
            if re.search(pattern, label, re.IGNORECASE):
                signals.append(
                    {
                        "kind": kind,
                        "label": label[:120],
                        "element": "link" if element.name == "a" else "button",
                        "url": urljoin(url, element["href"]) if element.name == "a" else None,
                    }
                )
                break
    return CommerceReadinessReport(
        url=url,
        products=products,
        services=services,
        journey_signals=signals[:30],
        manual_checks={
            "feed_submission": "unknown",
            "merchant_eligibility": "unknown",
            "verified_browser_access": "unknown",
            "checkout_or_booking_completion": "unknown",
            "prices_and_availability_current": "unknown",
        },
        limitations=[
            "One page of server-returned HTML only; no JavaScript rendering or site crawl.",
            "Field presence and link or button labels do not establish visibility, correctness or a working transaction.",
            "Service names are structured-data records and may describe the same service more than once.",
            "No feed, partner approval, browser access, ranking or sales are verified.",
        ],
    )
