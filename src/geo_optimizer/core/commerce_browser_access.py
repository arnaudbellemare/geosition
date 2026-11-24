"""Cloud-browser access guidance grounded in observed site responses.

An ordinary GEOSITION fetch is never evidence of an authenticated ChatGPT visit.
"""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit

GUIDE = "https://developers.openai.com/commerce/agent-access"

PROVIDER_GUIDANCE = {
    "cloudflare": "If a signed ChatGPT cloud-browser visit is confirmed blocked, ask the site administrator to review Security > Settings > AI Crawler and Agent access policies, Personal Agents, and allow the verified OpenAI agent if appropriate. Alternatively, review the verified ChatGPT Operator detection ID 129220581 in WAF. Confirm current labels in OpenAI's guide.",
    "akamai": "If a signed visit is confirmed blocked, ask the administrator to add the verified ChatGPT Agent bot to a custom bot category and allow it in the applicable Bot & Agent Control policy.",
    "human": "If a signed visit is confirmed blocked, ask the administrator to review the verified ChatGPT Agent entry in HUMAN Sightline known bots or AgenticTrust permissions.",
    "vercel": "If a signed visit is confirmed blocked, ask the administrator to review Vercel security settings for the verified ChatGPT Agent (chatgpt-operator). No change is needed if visits already work.",
    "other": "If a signed visit is confirmed blocked, ask the CDN or firewall administrator to verify Web Bot Auth HTTP message signatures using OpenAI's published keys and RFC 9421 before considering a narrowly scoped exception.",
}


def observe_fetch(url, response, error):
    """Summarize a normal fetch; response headers are hints, not verified identities."""
    headers = getattr(response, "headers", {}) if response is not None else {}
    headers = {str(k).lower(): str(v) for k, v in headers.items()} if isinstance(headers, Mapping) else {}
    server = headers.get("server", "").lower()
    hints = []
    if "cf-ray" in headers or "cloudflare" in server:
        hints.append("cloudflare")
    if "x-vercel-id" in headers or "vercel" in server:
        hints.append("vercel")
    if "akamai" in server or "x-akamai-transformed" in headers:
        hints.append("akamai")
    status = getattr(response, "status_code", None) if response is not None else None
    challenged = headers.get("cf-mitigated", "").lower() == "challenge"
    final_url = getattr(response, "url", None) if response is not None else None
    if not isinstance(final_url, str):
        final_url = url
    original, final = urlsplit(url), urlsplit(final_url)
    off_origin = (original.scheme.lower(), original.netloc.lower()) != (final.scheme.lower(), final.netloc.lower())
    state = (
        "challenge_observed"
        if challenged
        else "different_origin"
        if off_origin
        else "reachable"
        if status in (200, 203) and not error
        else "unavailable"
    )
    return {
        "url": url,
        "fetch_status": state,
        "http_status": status,
        "provider_hints": hints,
        "detail": "Ordinary GEOSITION fetch; not a signed ChatGPT cloud-browser visit.",
    }


def build_browser_access(observations):
    """Build a reviewable manual test and fix plan without asserting access."""
    hints = sorted({hint for item in observations for hint in item.get("provider_hints", [])})
    return {
        "verified_access": "unknown",
        "observations": observations,
        "provider_hints": hints,
        "provider_hint_note": "Response headers are unverified hints; confirm the actual CDN or firewall with the site administrator.",
        "test_steps": [
            "Choose representative public product or service pages and the contact, booking or checkout path; record the URLs and time.",
            "Use a real ChatGPT cloud-browser visit and record whether each page and agreed non-transactional step works, is challenged, or is blocked.",
            "Ask the site administrator to correlate the visit with CDN or firewall logs and confirm the provider's verified agent or valid request signature.",
            "If a verified visit is blocked, apply a provider-specific exception only where appropriate; retain authentication and page-level access controls.",
            "Repeat the same verified visit after any change and record the outcome and time. Do not place an order, pay, or submit an enquiry without authorization.",
        ],
        "guided_fixes": PROVIDER_GUIDANCE,
        "guidance_url": GUIDE,
        "limitations": "Ordinary fetches, user-agent imitation, robots.txt and response headers cannot establish verified ChatGPT browser access. A page response alone cannot establish a complete transaction or enquiry.",
    }
