"""Domain ownership verification (DNS TXT and HTTPS well-known)."""

from __future__ import annotations

import logging
import secrets

import requests

from geo_optimizer.utils.http import fetch_url
from geo_optimizer.utils.validators import validate_public_url

logger = logging.getLogger(__name__)

VERIFY_PREFIX = "geo-verify="


def generate_verify_token() -> str:
    """Generate token for DNS or HTTPS verification."""
    return secrets.token_urlsafe(16)


def dns_verify_hostname(domain: str) -> str:
    """Host name for DNS TXT record."""
    return f"_geo-verify.{domain.strip().lower()}"


def https_verify_url(domain: str) -> str:
    """URL for HTTPS file verification."""
    host = domain.strip().lower()
    return f"https://{host}/.well-known/geo-verify.txt"


def verify_dns_txt(domain: str, token: str) -> tuple[bool, str]:
    """Check Google DNS-over-HTTPS for TXT record containing geo-verify=token."""
    host = dns_verify_hostname(domain)
    expected = f"{VERIFY_PREFIX}{token}"
    url = f"https://dns.google/resolve?name={host}&type=TXT"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.debug("DNS verify failed for %s: %s", host, exc)
        return False, f"DNS lookup failed: {exc}"

    for answer in payload.get("Answer") or []:
        raw = str(answer.get("data", "")).strip('"').strip()
        if expected in raw or token in raw:
            return True, "DNS TXT record verified"
    return False, f"TXT record not found at {host}. Expected: {expected}"


def verify_https_file(domain: str, token: str) -> tuple[bool, str]:
    """Fetch /.well-known/geo-verify.txt and check token."""
    target = https_verify_url(domain)
    ok, err = validate_public_url(target)
    if not ok:
        return False, err or "Invalid verification URL"

    expected_line = f"{VERIFY_PREFIX}{token}"
    try:
        response, fetch_error = fetch_url(target, timeout=15)
        if response is None:
            return False, fetch_error or "Could not fetch verification file"
        body = (response.text or "")[:2000]
    except Exception as exc:
        logger.debug("HTTPS verify failed for %s: %s", target, exc)
        return False, f"Could not fetch verification file: {exc}"

    if expected_line in body or token in body:
        return True, "HTTPS well-known file verified"
    return False, f"File at {target} must contain: {expected_line}"


def verify_domain(domain: str, token: str, *, method: str = "dns") -> tuple[bool, str]:
    """Verify domain using dns or https method."""
    if method not in {"dns", "https"}:
        raise ValueError("Verification method must be 'dns' or 'https'")
    if method == "https":
        return verify_https_file(domain, token)
    return verify_dns_txt(domain, token)
