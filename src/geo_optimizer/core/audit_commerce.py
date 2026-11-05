"""Informational commerce checks on product structured data present on a page."""

from __future__ import annotations

from geo_optimizer.core.citability._helpers import _iter_jsonld_items, _jsonld_types

_GOOGLE = "https://developers.google.com/search/docs/appearance/structured-data/merchant-listing"
_OPENAI = "https://developers.openai.com/commerce/guides/get-started"


def audit_commerce(soup) -> dict:
    """Inspect Product JSON-LD; does not access feeds or verify merchant eligibility."""
    products = [item for item in _iter_jsonld_items(soup) if "Product" in _jsonld_types(item)]
    if not products:
        return {
            "applicable": False,
            "checks": [],
            "recommendations": [],
            "note": "No Product JSON-LD found. Audit an individual product page if this site sells products.",
        }
    product = products[0]
    raw_offers = product.get("offers")
    offers = [raw_offers] if isinstance(raw_offers, dict) else raw_offers if isinstance(raw_offers, list) else []
    offers = [offer for offer in offers if isinstance(offer, dict)]

    def present(value: object) -> bool:
        return value is not None and value != "" and value != [] and value != {}

    checks = [
        ("name", present(product.get("name")), "Add the product name to Product structured data."),
        ("image", present(product.get("image")), "Add a representative product image to Product structured data."),
        ("description", present(product.get("description")), "Add an accurate product description."),
        (
            "price",
            any(present(o.get("price")) or present(o.get("lowPrice")) for o in offers),
            "Add the current offer price.",
        ),
        (
            "currency",
            any(present(o.get("priceCurrency")) for o in offers),
            "Add the offer currency, such as USD or CAD.",
        ),
        ("availability", any(present(o.get("availability")) for o in offers), "Add the offer availability."),
        ("brand", present(product.get("brand")), "Add the product brand when applicable."),
    ]
    return {
        "applicable": True,
        "product_count": len(products),
        "checks": [
            {"key": key, "present": found, "evidence_level": "provider_guidance", "source_url": _GOOGLE}
            for key, found, _ in checks
        ],
        "recommendations": [suggestion for _, found, suggestion in checks if not found],
        "feed_status": "not_checked",
        "feed_guidance_url": _OPENAI,
        "note": (
            "Checks the first Product JSON-LD item only. It does not verify current prices, image accessibility, "
            "feed submissions, provider eligibility, or product listings."
        ),
    }
