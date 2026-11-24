"""Validate a supported subset of OpenAI's discovery feed before local export."""

from __future__ import annotations

import re
from collections import Counter
from decimal import Decimal

from geo_optimizer.core.commerce_preparation import _web_url
from geo_optimizer.models.results.commerce_feed import FeedValidation

_FIELDS = (
    "item_id",
    "title",
    "description",
    "url",
    "brand",
    "seller_name",
    "image_url",
    "price",
    "availability",
    "target_countries",
    "store_country",
)
_AVAILABILITY = {"in_stock", "out_of_stock", "pre_order", "backorder", "unknown"}
_COUNTRIES = {"US", "CA", "MX"}
_MONEY = re.compile(r"^(\d+(?:\.\d{1,2})?) (USD|CAD|MXN)$")
_PLACEHOLDERS = {"null", "n/a", "unknown"}


def validate_feed(candidate: dict) -> FeedValidation:
    """Check the 11 basic discovery fields; do not assert provider acceptance."""
    if not isinstance(candidate, dict) or not isinstance(candidate.get("items"), list) or not candidate["items"]:
        raise ValueError("Input must contain a non-empty items list.")
    if any(not isinstance(x, dict) or not isinstance(x.get("record"), dict) for x in candidate["items"]):
        raise ValueError("Each item must contain a record object.")
    records = [item["record"] for item in candidate["items"]]
    ids = Counter(r.get("item_id") for r in records if isinstance(r.get("item_id"), str) and r.get("item_id"))
    rows = []
    for index, item in enumerate(candidate["items"], 1):
        r = item["record"]
        errors, gates = [], []
        for field in _FIELDS:
            value = r.get(field)
            if field == "target_countries":
                if (
                    not isinstance(value, list)
                    or not value
                    or any(not isinstance(x, str) or x not in _COUNTRIES for x in value)
                ):
                    errors.append("target_countries must be a non-empty list of US, CA or MX")
            elif (
                not isinstance(value, str)
                or not value.strip()
                or (field != "availability" and value.strip().lower() in _PLACEHOLDERS)
            ):
                errors.append(f"{field} is missing or a placeholder")
        identifier = r.get("item_id")
        if isinstance(identifier, str) and identifier and ids[identifier] > 1:
            errors.append("item_id is duplicated")
        for field in ("url", "image_url"):
            if isinstance(r.get(field), str) and not _web_url(r[field]):
                errors.append(f"{field} must be an absolute HTTP(S) URL")
        if isinstance(r.get("availability"), str) and r["availability"] not in _AVAILABILITY:
            errors.append("availability is not a supported value")
        if isinstance(r.get("store_country"), str) and r["store_country"] not in _COUNTRIES:
            errors.append("store_country must be US, CA or MX")
        match = _MONEY.fullmatch(r.get("price", "")) if isinstance(r.get("price"), str) else None
        if not match or Decimal(match.group(1)) <= 0:
            errors.append("price must be a positive decimal amount followed by USD, CAD or MXN")
        for field in ("owner_reviewed", "rights_confirmed"):
            if item.get(field) is not True:
                gates.append(f"{field} not confirmed")
        if candidate.get("market_confirmed") is not True:
            gates.append("merchant market and currency access not confirmed")
        rows.append({"row": index, "item_id": identifier, "errors": errors, "review_gates": gates})
    passed = all(not row["errors"] for row in rows)
    return FeedValidation(
        basic_checks_passed=passed,
        ready_for_enabled_export=passed and all(not r["review_gates"] for r in rows),
        rows=rows,
        limitations=[
            "Offline basic field and format checks only; not an official validator or provider acceptance.",
            "Does not verify URLs, merchant eligibility, current stock, item identity, ownership, pricing, rights or account permissions.",
            "Standard OpenAI uploads currently default to US; confirm Canadian market and CAD support for the specific integration.",
        ],
    )


def feed_rows(candidate: dict, enable_search: bool) -> list[dict]:
    """Render validated discovery rows with explicit eligibility."""
    validation = validate_feed(candidate)
    if not validation.basic_checks_passed:
        raise ValueError("Feed has basic field errors; see validation.json.")
    if enable_search and not validation.ready_for_enabled_export:
        raise ValueError("Owner review, rights and market confirmation are required for enabled export.")
    return [
        {**{field: item["record"][field] for field in _FIELDS}, "is_eligible_search": enable_search}
        for item in candidate["items"]
    ]
