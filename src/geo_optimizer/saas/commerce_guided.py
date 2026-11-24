"""Workspace-scoped AI commerce setup and audit operations."""

from __future__ import annotations

import json
from dataclasses import asdict

from geo_optimizer.core.commerce_provider_evidence import attach_vercel_evidence, validate_vercel_evidence
from geo_optimizer.core.commerce_site import run_site_audit
from geo_optimizer.core.monitor import normalize_monitor_domain
from geo_optimizer.saas.commerce_providers import PROVIDER_STEP_IDS, PROVIDERS

STEPS = frozenset({"journey", "catalog", "service", "site", "accounts", "connection", "test", "monitor"})
STEPS = STEPS | PROVIDER_STEP_IDS
STATES = frozenset({"todo", "working", "done", "blocked"})


def _scope(service, token, domain):
    _, org = service.require_session(token)
    normalized = service._normalize_domain(domain)
    service._require_verified(org.org_id, normalized)
    return org.org_id, normalized


def get_setup(service, token, domain):
    org_id, domain = _scope(service, token, domain)
    statuses = {}
    for step in STEPS:
        runs = service.store.list_runs(org_id, kind="commerce_setup_" + step, domain=domain, limit=1)
        if runs:
            statuses[step] = runs[0].result_summary
    audit_runs = service.store.list_runs(org_id, kind="commerce_guided_audit", domain=domain, limit=1)
    audit = json.loads(audit_runs[0].result_summary) if audit_runs else None
    if audit:
        audit = _attach_saved_evidence(service, org_id, domain, audit)
    return {"domain": domain, "statuses": statuses, "audit": audit, "providers": PROVIDERS}


def save_step(service, token, domain, step, status):
    org_id, domain = _scope(service, token, domain)
    if step not in STEPS or status not in STATES:
        raise ValueError("Invalid setup step or progress state.")
    service.store.create_run(
        org_id, kind="commerce_setup_" + step, domain=domain, status="completed", result_summary=status
    )
    return {"step": step, "status": status, "verified": False}


def _attach_saved_evidence(service, org_id, domain, audit):
    runs = service.store.list_runs(org_id, kind="commerce_browser_provider_evidence", domain=domain, limit=1)
    if runs:
        attach_vercel_evidence(audit, json.loads(runs[0].result_summary))
    return audit


def save_browser_evidence(service, token, domain, evidence):
    org_id, domain = _scope(service, token, domain)
    validate_vercel_evidence(evidence, normalize_monitor_domain(domain))
    service.store.create_run(
        org_id,
        kind="commerce_browser_provider_evidence",
        domain=domain,
        status="completed",
        result_summary=json.dumps(evidence),
    )
    return {"saved": True, "classification": "operator_reported_correlated", "independently_verified": False}


def run_audit(service, token, domain):
    org_id, domain = _scope(service, token, domain)
    report = run_site_audit(normalize_monitor_domain(domain), max_pages=10, render=False)
    data = asdict(report)
    summary = {
        "url": data["url"],
        "coverage": data["coverage"],
        "recommendations": data["recommendations"],
        "failures": data["failures"],
        "warnings": data["warnings"],
        "skipped": data["skipped"],
        "browser_access": data["browser_access"],
        "limitations": "Bounded same-origin crawl; JavaScript rendering was not requested. No payment, account, or provider access is verified.",
    }
    summary = _attach_saved_evidence(service, org_id, domain, summary)
    if not data["coverage"].get("pages_audited"):
        raise ValueError("No pages could be audited. Check the website and try again.")
    service.store.create_run(
        org_id, kind="commerce_guided_audit", domain=domain, status="completed", result_summary=json.dumps(summary)
    )
    return summary
