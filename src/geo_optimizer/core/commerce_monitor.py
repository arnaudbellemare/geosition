"""Compare read-only commerce audit snapshots without claiming transaction success."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from geo_optimizer.core.commerce_site import run_site_audit
from geo_optimizer.models.results.commerce_monitor import CommerceMonitorResult
from geo_optimizer.utils.http import fetch_url


class MonitorScanError(ValueError):
    """A site scan could not be completed."""


def _pages(report):
    return {page["url"]: page for page in report.get("pages", []) if isinstance(page, dict) and page.get("url")}


def _journeys(page):
    return {
        (s.get("kind", ""), s.get("element", ""), s.get("label", ""), s.get("url") or "")
        for s in page.get("journey_signals", [])
    }


def _prices(page):
    result = {}
    for item in page.get("catalog_signals", []):
        name = item.get("name")
        if name and name not in result:
            result[name] = item.get("price_text", "")
        elif name:
            result[name] = None  # Names alone do not distinguish duplicate products.
    return result


def _products(page):
    result = {}
    for item in page.get("products", []):
        name = item.get("name")
        if name and name not in result:
            result[name] = item.get("fields", {})
        elif name:
            result[name] = None
    return result


def compare_reports(previous: dict, current: dict) -> dict:
    """Compare only pages successfully observed in both compatible render modes."""
    changes, unknowns = [], []
    old_pages, new_pages = _pages(previous), _pages(current)
    for url in sorted(old_pages.keys() - new_pages.keys()):
        unknowns.append(f"Previously observed page was not audited: {url}")
    for url in sorted(old_pages.keys() & new_pages.keys()):
        old, new = old_pages[url], new_pages[url]
        if old.get("render_status") != new.get("render_status") or new.get("render_status") in ("partial", "failed"):
            unknowns.append(f"Rendering was incomplete or changed on {url}; no page comparison made.")
            continue
        old_prices, new_prices = _prices(old), _prices(new)
        for name in sorted(old_prices.keys() - new_prices.keys()):
            changes.append({"type": "catalog_card_not_observed", "page": url, "item": name})
        for name in sorted(new_prices.keys() - old_prices.keys()):
            changes.append({"type": "catalog_card_observed", "page": url, "item": name})
        for name, old_price in old_prices.items():
            new_price = new_prices.get(name)
            if old_price is not None and new_price is not None and old_price != new_price:
                changes.append(
                    {
                        "type": "displayed_price_changed",
                        "page": url,
                        "item": name,
                        "before": old_price,
                        "after": new_price,
                    }
                )
        old_products, new_products = _products(old), _products(new)
        for name in old_products.keys() & new_products.keys():
            before, after = old_products[name], new_products[name]
            if not isinstance(before, dict) or not isinstance(after, dict):
                continue
            for field in sorted(before.keys() & after.keys()):
                if before[field] is True and after[field] is False:
                    changes.append(
                        {"type": "product_field_no_longer_observed", "page": url, "item": name, "field": field}
                    )
                elif before[field] is False and after[field] is True:
                    changes.append({"type": "product_field_observed", "page": url, "item": name, "field": field})
        for signal in sorted(_journeys(old) - _journeys(new)):
            changes.append(
                {
                    "type": "journey_signal_not_observed",
                    "page": url,
                    "signal": dict(zip(("kind", "element", "label", "url"), signal)),
                }
            )
        for signal in sorted(_journeys(new) - _journeys(old)):
            changes.append(
                {
                    "type": "journey_signal_observed",
                    "page": url,
                    "signal": dict(zip(("kind", "element", "label", "url"), signal)),
                }
            )
    old_probes = {p["url"]: p for p in previous.get("journey_probes", [])}
    new_probes = {p["url"]: p for p in current.get("journey_probes", [])}
    for url in sorted(old_probes.keys() & new_probes.keys()):
        before, after = old_probes[url]["status"], new_probes[url]["status"]
        if before == "reachable" and after == "not_verified":
            changes.append({"type": "contact_page_no_longer_verified", "url": url})
        elif before == "not_verified" and after == "reachable":
            changes.append({"type": "contact_page_reachable_again", "url": url})
    if (
        previous.get("coverage", {}).get("complete")
        and current.get("coverage", {}).get("complete")
        and old_pages.keys() == new_pages.keys()
        and not unknowns
    ):
        old_ids = {x.get("id") for x in previous.get("recommendations", []) if x.get("id")}
        new_ids = {x.get("id") for x in current.get("recommendations", []) if x.get("id")}
        for key in sorted(new_ids - old_ids):
            changes.append({"type": "finding_added", "finding": key})
        for key in sorted(old_ids - new_ids):
            changes.append({"type": "finding_no_longer_reported", "finding": key})
    else:
        unknowns.append(
            "Site coverage or page comparisons were incomplete; site-wide finding changes were not compared."
        )
    return {"changes": changes, "unknowns": unknowns}


def probe_journey_destinations(report: dict) -> list[dict]:
    """Fetch only clearly named same-origin contact pages, without sending an enquiry."""
    base = urlsplit(report["url"])
    candidates = set()
    for page in report.get("pages", []):
        for signal in page.get("journey_signals", []):
            if signal.get("kind") != "enquiry" or signal.get("element") != "link":
                continue
            url = signal.get("url") or ""
            parsed = urlsplit(url)
            path = parsed.path.lower().rstrip("/")
            if (
                (parsed.scheme, parsed.netloc.lower()) != (base.scheme, base.netloc.lower())
                or parsed.query
                or parsed.fragment
            ):
                continue
            if path.split("/")[-1] not in ("contact", "contactez-nous", "nous-joindre", "get-in-touch"):
                continue
            candidates.add(url)
    probes = []
    for url in sorted(candidates)[:10]:
        response, error = fetch_url(url, timeout=5)
        final = getattr(response, "url", url) if response is not None else url
        final_parts = urlsplit(final)
        same_origin = (final_parts.scheme, final_parts.netloc.lower()) == (base.scheme, base.netloc.lower())
        ok = not error and response is not None and response.status_code in (200, 203) and same_origin
        probes.append(
            {
                "url": url,
                "status": "reachable" if ok else "not_verified",
                "detail": "GET returned a page; delivery not tested"
                if ok
                else str(error or "Unexpected response or redirect"),
            }
        )
    return probes


def _compact(report):
    return {
        "url": report["url"],
        "pages": [
            {key: p.get(key) for key in ("url", "render_status", "catalog_signals", "products", "journey_signals")}
            for p in report.get("pages", [])
        ],
        "coverage": report.get("coverage", {}),
        "recommendations": [{"id": r.get("id")} for r in report.get("recommendations", [])],
    }


def run_commerce_monitor(
    url: str, db_path: Path, max_pages: int = 25, render: bool = False, baseline: dict | None = None
) -> CommerceMonitorResult:
    """Audit once, compare with the last successful snapshot, and persist evidence."""
    normalized = url if url.startswith(("http://", "https://")) else "https://" + url
    parsed = urlsplit(normalized)
    if parsed.query or parsed.fragment:
        raise ValueError("Monitor URLs cannot include a query or fragment.")
    normalized = normalized.rstrip("/") + ("/" if not parsed.path or parsed.path == "/" else "")
    key = json.dumps([normalized, max_pages, render], separators=(",", ":"))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_path)) as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS commerce_monitor_snapshots (id INTEGER PRIMARY KEY, monitor_key TEXT NOT NULL, checked_at TEXT NOT NULL, report_json TEXT NOT NULL)"
        )
        row = db.execute(
            "SELECT report_json FROM commerce_monitor_snapshots WHERE monitor_key=? ORDER BY id DESC LIMIT 1", (key,)
        ).fetchone()
        previous = json.loads(row[0]) if row else None
        if baseline is not None:
            if previous is not None:
                raise ValueError("A baseline already exists for this monitor; do not overwrite history.")
            coverage = baseline.get("coverage", {})
            if (
                baseline.get("url", "").rstrip("/") != normalized.rstrip("/")
                or coverage.get("max_pages") != max_pages
                or coverage.get("render_requested") != render
            ):
                raise ValueError("Baseline URL, page limit and rendering settings must match this monitor.")
            previous = _compact(baseline)
        try:
            current = _compact(asdict(run_site_audit(normalized, max_pages=max_pages, render=render)))
        except ValueError as exc:
            raise MonitorScanError(str(exc)) from exc
        probes = probe_journey_destinations(current)
        current["journey_probes"] = probes
        comparison = compare_reports(previous, current) if previous else {"changes": [], "unknowns": []}
        if not current["coverage"].get("complete", False):
            comparison["unknowns"].append("Current scan coverage is incomplete; some pages or findings may be missing.")
        for page in current["pages"]:
            if page.get("render_status") in ("failed", "partial"):
                comparison["unknowns"].append(f"Rendering incomplete on {page['url']}.")
        for probe in probes:
            if probe["status"] != "reachable":
                comparison["unknowns"].append(f"Contact page could not be verified: {probe['url']}")
        timestamp = datetime.now(timezone.utc).isoformat()
        if baseline is not None:
            db.execute(
                "INSERT INTO commerce_monitor_snapshots (monitor_key,checked_at,report_json) VALUES (?,?,?)",
                (key, str(baseline.get("audit_date", "imported")), json.dumps(previous)),
            )
        db.execute(
            "INSERT INTO commerce_monitor_snapshots (monitor_key,checked_at,report_json) VALUES (?,?,?)",
            (key, timestamp, json.dumps(current)),
        )
    return CommerceMonitorResult(
        normalized,
        timestamp,
        previous is None,
        current["coverage"],
        comparison["changes"],
        comparison["unknowns"],
        probes,
    )
