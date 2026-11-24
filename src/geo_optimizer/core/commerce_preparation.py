"""Build reviewable product preparation data from captured audit evidence."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any
from urllib.parse import urlsplit

from geo_optimizer.models.results.commerce_preparation import CommercePreparation

_FIELDS = (
    "item_id",
    "product_url",
    "description",
    "image_url",
    "price",
    "currency",
    "availability",
)
_AVAILABILITY = {"InStock", "OutOfStock", "PreOrder", "BackOrder", "Discontinued"}
_PRICE = re.compile(r"^(?:0|[1-9]\d*)(?:\.\d{1,2})?$")


def _web_url(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme in ("https", "http") and bool(parsed.hostname) and not parsed.username and not parsed.password
        )
    except ValueError:
        return False


def catalog_from_audit(audit: dict) -> dict:
    """Extract observed cards; keep displayed prices as unverified text."""
    if not isinstance(audit, dict) or not isinstance(audit.get("pages"), list):
        raise ValueError("Expected a site-audit JSON with a pages list.")
    items = []
    for page in audit["pages"]:
        for signal in page.get("catalog_signals", []):
            name = signal.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            items.append(
                {
                    "name": name.strip(),
                    "source_url": page.get("url", ""),
                    "observed_price_text": signal.get("price_text", ""),
                    **dict.fromkeys(_FIELDS, ""),
                    "owner_reviewed": False,
                    "rights_confirmed": False,
                }
            )
    if not items:
        raise ValueError("No product-card signals found; audit a representative catalog page first.")
    return {
        "audit_url": audit.get("url", ""),
        "audit_date": audit.get("audit_date", "unknown"),
        "items": items,
    }


def prepare_catalog(catalog: dict) -> CommercePreparation:
    """Validate the review worksheet and build draft JSON-LD, not a provider feed."""
    if not isinstance(catalog, dict) or not isinstance(catalog.get("items"), list) or not catalog["items"]:
        raise ValueError("Expected a review catalog with at least one item.")
    if any(not isinstance(item, dict) for item in catalog["items"]):
        raise ValueError("Each catalog item must be an object.")
    ids = Counter(
        item.get("item_id", "")
        for item in catalog["items"]
        if isinstance(item.get("item_id"), str) and item.get("item_id", "")
    )
    results, graph = [], []
    for index, item in enumerate(catalog["items"], 1):
        issues = []
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            issues.append("name is missing")
        for field in _FIELDS:
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                issues.append(f"{field} is missing")
        for field in ("product_url", "image_url"):
            value = item.get(field, "")
            if isinstance(value, str) and value and not _web_url(value):
                issues.append(f"{field} must be an HTTP(S) URL")
        price = item.get("price", "")
        if isinstance(price, str) and price and not _PRICE.fullmatch(price):
            issues.append("price must be a non-negative decimal with at most two decimal places")
        currency = item.get("currency", "")
        if isinstance(currency, str) and currency and not re.fullmatch(r"[A-Z]{3}", currency):
            issues.append("currency must be a three-letter uppercase code")
        availability = item.get("availability", "")
        if isinstance(availability, str) and availability and availability not in _AVAILABILITY:
            issues.append("availability must be InStock, OutOfStock, PreOrder, BackOrder or Discontinued")
        identifier = item.get("item_id", "")
        if isinstance(identifier, str) and identifier and ids[identifier] > 1:
            issues.append("item_id is duplicated")
        for field in ("owner_reviewed", "rights_confirmed"):
            if item.get(field) is not True:
                issues.append(f"{field} must be confirmed by the owner")
        results.append(
            {
                "item": index,
                "name": name if isinstance(name, str) else "",
                "issues": issues,
            }
        )
        product: dict[str, Any] = {"@type": "Product"}
        for source, target in (
            ("name", "name"),
            ("description", "description"),
            ("image_url", "image"),
        ):
            value = item.get(source)
            if isinstance(value, str) and value and (source != "image_url" or _web_url(value)):
                product[target] = value
        offer = {"@type": "Offer"}
        if isinstance(price, str) and _PRICE.fullmatch(price):
            offer["price"] = price
        if isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency):
            offer["priceCurrency"] = currency
        if isinstance(availability, str) and availability in _AVAILABILITY:
            offer["availability"] = f"https://schema.org/{availability}"
        if _web_url(item.get("product_url", "")):
            offer["url"] = item["product_url"]
        if len(offer) > 1:
            product["offers"] = offer
        graph.append(product)
    return CommercePreparation(
        catalog=catalog,
        validation={
            "status": "draft_only",
            "internal_checks_complete": all(not r["issues"] for r in results),
            "note": "Internal completeness checks only; provider schema, eligibility and data accuracy are not verified.",
            "items": results,
        },
        structured_data={"@context": "https://schema.org", "@graph": graph},
    )
