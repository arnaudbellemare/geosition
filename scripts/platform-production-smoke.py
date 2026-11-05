#!/usr/bin/env python3
"""Production smoke test for the GEOSITION platform flow.

The script intentionally does not bypass DNS/HTTPS ownership verification.
For a fully automated post-deploy smoke, run it against a controlled smoke
domain and provision the printed verification token before polling verify.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from typing import Any

import requests


def _json_response(response: requests.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError:
        payload = {"detail": response.text[:500]}
    return payload if isinstance(payload, dict) else {"payload": payload}


def _request(session: requests.Session, method: str, url: str, **kwargs) -> dict[str, Any]:
    response = session.request(method, url, timeout=kwargs.pop("timeout", 30), **kwargs)
    payload = _json_response(response)
    if response.status_code >= 400:
        detail = payload.get("detail") or payload
        raise RuntimeError(f"{method} {url} failed: {response.status_code} {detail}")
    return payload


def _headers(token: str = "") -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if token else {}


def _print_step(name: str, payload: object = "") -> None:
    suffix = f": {payload}" if payload else ""
    print(f"[geosition-smoke] {name}{suffix}")


def _wait_for_verification(
    session: requests.Session,
    *,
    base_url: str,
    token: str,
    domain_id: int,
    method: str,
    seconds: int,
) -> dict[str, Any]:
    deadline = time.time() + seconds
    last: dict[str, Any] = {}
    while time.time() <= deadline:
        last = _request(
            session,
            "POST",
            f"{base_url}/api/v1/domains/{domain_id}/verify",
            headers=_headers(token),
            json={"method": method},
        )
        if last.get("verified"):
            return last
        _print_step("verification pending", last.get("message") or "not verified yet")
        time.sleep(10)
    return last


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a live GEOSITION platform production smoke.")
    parser.add_argument("--base-url", default=os.environ.get("GEOSITION_PLATFORM_URL", "https://geositionai.com"))
    parser.add_argument("--email", default=os.environ.get("GEOSITION_SMOKE_EMAIL", ""))
    parser.add_argument("--password", default=os.environ.get("GEOSITION_SMOKE_PASSWORD", ""))
    parser.add_argument("--domain", default=os.environ.get("GEOSITION_SMOKE_DOMAIN", ""))
    parser.add_argument("--org-name", default=os.environ.get("GEOSITION_SMOKE_ORG", "GEOSITION Smoke"))
    parser.add_argument("--worker-token", default=os.environ.get("GEOSITION_WORKER_TOKEN", ""))
    parser.add_argument("--verify-method", choices=["none", "dns", "https"], default="none")
    parser.add_argument("--verify-timeout", type=int, default=180)
    parser.add_argument("--require-verified", action="store_true")
    parser.add_argument("--skip-audit", action="store_true")
    parser.add_argument("--require-reset-delivery", action="store_true")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    email = args.email or f"geosition-smoke+{uuid.uuid4().hex[:10]}@example.com"
    password = args.password or f"SmokePass-{uuid.uuid4().hex[:12]}"
    if not args.domain:
        raise SystemExit("Set --domain or GEOSITION_SMOKE_DOMAIN to the website domain used for smoke verification.")

    session = requests.Session()
    _print_step("base", base_url)

    health = session.get(f"{base_url}/health", timeout=20)
    if health.status_code >= 400:
        raise RuntimeError(f"GET /health failed: {health.status_code} {health.text[:300]}")
    _print_step("public health ok")

    if args.worker_token:
        platform_health = _request(
            session,
            "GET",
            f"{base_url}/api/v1/platform/health",
            headers={"X-GEOSITION-Worker-Token": args.worker_token},
        )
        _print_step("platform health", json.dumps(platform_health, sort_keys=True))
        if not platform_health.get("ok"):
            _print_step("platform health warnings", platform_health.get("next_actions", []))

    landing = session.get(f"{base_url}/platform", timeout=20)
    if landing.status_code >= 400 or "Your website" not in landing.text:
        raise RuntimeError(f"GET /platform failed or landing marker missing: {landing.status_code}")
    _print_step("landing ok")

    register = _request(
        session,
        "POST",
        f"{base_url}/api/v1/auth/register",
        json={"email": email, "password": password, "org_name": args.org_name, "domain": args.domain},
    )
    token = str((register.get("session") or {}).get("token") or "")
    if not token:
        raise RuntimeError("Registration did not return a session token")
    _print_step("signup ok", email)

    session.post(f"{base_url}/api/v1/auth/logout", headers=_headers(token), timeout=20)
    login = _request(session, "POST", f"{base_url}/api/v1/auth/login", json={"email": email, "password": password})
    token = str((login.get("session") or {}).get("token") or "")
    if not token:
        raise RuntimeError("Login did not return a session token")
    _print_step("login ok")

    verification = register.get("domain_verification") or _request(
        session,
        "POST",
        f"{base_url}/api/v1/domains",
        headers=_headers(token),
        json={"domain": args.domain},
    )
    domain_payload = verification.get("domain") or {}
    domain_id = int(domain_payload.get("domain_id") or 0)
    if not domain_id:
        raise RuntimeError(f"Domain add did not return a domain_id: {verification}")
    _print_step("domain added", domain_payload.get("domain") or args.domain)
    _print_step("dns host", verification.get("dns_host"))
    _print_step("dns value", verification.get("dns_value"))
    _print_step("https url", verification.get("https_url"))
    _print_step("https body", verification.get("https_body"))

    dashboard = session.get(f"{base_url}/platform/dashboard", headers=_headers(token), timeout=20)
    if dashboard.status_code >= 400 or "Copy Skill Files" not in dashboard.text:
        raise RuntimeError(f"Dashboard did not render expected workflow markers: {dashboard.status_code}")
    _print_step("dashboard locked/rendered ok")

    verified = False
    if args.verify_method != "none":
        result = _wait_for_verification(
            session,
            base_url=base_url,
            token=token,
            domain_id=domain_id,
            method=args.verify_method,
            seconds=args.verify_timeout,
        )
        verified = bool(result.get("verified"))
        _print_step("verification result", result.get("message") or result)

    if args.require_verified and not verified:
        raise RuntimeError("Domain verification did not succeed. Provision the DNS TXT or HTTPS file token and rerun.")

    if verified and not args.skip_audit:
        audit = _request(
            session,
            "POST",
            f"{base_url}/api/v1/audit",
            headers=_headers(token),
            json={"domain": domain_payload.get("domain") or args.domain},
            timeout=90,
        )
        _print_step("audit ok", f"{audit.get('score', '--')}/100 {audit.get('band', '')}")

    reset = _request(session, "POST", f"{base_url}/api/v1/auth/forgot-password", json={"email": email})
    _print_step("forgot password ok", reset.get("delivery", "unknown"))
    if args.require_reset_delivery and reset.get("delivery") == "email_unconfigured":
        raise RuntimeError("Password reset delivery is not production-ready")

    _print_step("complete")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[geosition-smoke] FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
