"""Prepare review-only service and enquiry data from site audit evidence."""

from __future__ import annotations

from geo_optimizer.core.commerce_preparation import _web_url
from geo_optimizer.models.results.commerce_services import ServicePreparation


def review_from_audit(audit: dict) -> dict:
    """Group identical observed names and controls while retaining evidence pages."""
    if not isinstance(audit, dict) or not isinstance(audit.get("pages"), list):
        raise ValueError("Expected a site-audit JSON with a pages list.")
    services, journeys = {}, {}
    for page in audit["pages"]:
        source = page.get("url", "")
        for name in page.get("services", []):
            if not isinstance(name, str) or not name.strip():
                continue
            name = name.strip()
            item = services.setdefault(
                name,
                {
                    "name": name,
                    "evidence_pages": [],
                    "description": "",
                    "service_url": "",
                    "area_served": "",
                    "provider_name": "",
                    "owner_reviewed": False,
                },
            )
            if source not in item["evidence_pages"]:
                item["evidence_pages"].append(source)
        for signal in page.get("journey_signals", []):
            if signal.get("kind") != "enquiry":
                continue
            label = signal.get("label", "")
            element = signal.get("element", "")
            destination = signal.get("url") or ""
            key = (label, element, destination)
            item = journeys.setdefault(
                key,
                {
                    "label": label,
                    "element": element,
                    "observed_url": destination,
                    "evidence_pages": [],
                    "tested": False,
                    "outcome_notes": "",
                },
            )
            if source not in item["evidence_pages"]:
                item["evidence_pages"].append(source)
    if not services and not journeys:
        raise ValueError("No service or enquiry signals found; audit representative service and contact pages first.")
    return {
        "audit_url": audit.get("url", ""),
        "audit_date": audit.get("audit_date", "unknown"),
        "coverage": audit.get("coverage", {}),
        "services": list(services.values()),
        "journeys": list(journeys.values()),
    }


def prepare_services(review: dict) -> ServicePreparation:
    """Build draft Service JSON-LD and internal review checks."""
    if (
        not isinstance(review, dict)
        or not isinstance(review.get("services"), list)
        or not isinstance(review.get("journeys"), list)
    ):
        raise ValueError("Expected a review file with services and journeys lists.")
    if not review["services"] and not review["journeys"]:
        raise ValueError("Review file contains no services or enquiry signals.")
    if any(not isinstance(item, dict) for item in review["services"] + review["journeys"]):
        raise ValueError("Each service and journey must be an object.")
    validation, graph = [], []
    for index, service in enumerate(review["services"], 1):
        issues = []
        for field in ("name", "description", "service_url", "area_served", "provider_name"):
            if not isinstance(service.get(field), str) or not service[field].strip():
                issues.append(f"{field} is missing")
        url = service.get("service_url", "")
        if isinstance(url, str) and url and not _web_url(url):
            issues.append("service_url must be an HTTP(S) URL")
        if service.get("owner_reviewed") is not True:
            issues.append("owner_reviewed must be confirmed by the owner")
        node = {"@type": "Service"}
        for source, target in (
            ("name", "name"),
            ("description", "description"),
            ("service_url", "url"),
            ("area_served", "areaServed"),
        ):
            value = service.get(source)
            if isinstance(value, str) and value and (source != "service_url" or _web_url(value)):
                node[target] = value
        provider = service.get("provider_name")
        if isinstance(provider, str) and provider:
            node["provider"] = {"@type": "Organization", "name": provider}
        graph.append(node)
        validation.append({"item": index, "name": service.get("name", ""), "issues": issues})
    journey_validation = []
    for index, journey in enumerate(review["journeys"], 1):
        issues = []
        if journey.get("tested") is not True:
            issues.append("journey has not been marked tested")
        if journey.get("tested") is True and not str(journey.get("outcome_notes", "")).strip():
            issues.append("record the authorized test outcome")
        journey_validation.append({"item": index, "label": journey.get("label", ""), "issues": issues})
    return ServicePreparation(
        review=review,
        validation={
            "status": "draft_only",
            "note": "Internal completeness checks only; service accuracy, provider eligibility and journey outcomes are not verified.",
            "services": validation,
            "journeys": journey_validation,
        },
        structured_data={"@context": "https://schema.org", "@graph": graph},
    )
