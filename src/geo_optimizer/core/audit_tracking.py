"""
GEO Audit — Analytics & tracking presence audit (v4.13).

Detects whether the page has analytics, conversion tracking, and measurement
tools installed — a baseline requirement for any data-driven marketing effort.

Detectors (all pure HTML/script-tag analysis — no network requests):

- GA4 (Google Analytics 4)            — gtag config 'G-' or analytics.js with GA4 measurement ID
- GTM (Google Tag Manager)             — googletagmanager.com scripts
- Meta / Facebook Pixel                — connect.facebook.net or fbq()
- LinkedIn Insight Tag                 — snap.licdn.com or LinkedIn partner ID
- Twitter / X Pixel                    — static.ads-twitter.com or twq()
- Google Ads conversion tag            — googleadservices.com / google_conversion
- Plausible Analytics                  — plausible.io
- Fathom Analytics                     — cdn.usefathom.com
- Matomo / Piwik                       — matomo.js / piwik.js
- Segment                              — cdn.segment.com
- Mixpanel                             — cdn.mxpnl.com or mixpanel.com/lib
- Amplitude                            — cdn.amplitude.com
- Heap                                 — cdn.heapanalytics.com
- HubSpot tracking                     — js.hs-scripts.com / hs-analytics
- Hotjar                               — static.hotjar.com
- Microsoft Clarity                    — clarity.ms

Score: 0 (nothing) → 30 (basic analytics) → 70 (analytics + conversion pixel) → 100 (analytics + conversion + heatmap/session recording)
"""

from __future__ import annotations

import re

from geo_optimizer.models.results import TrackingResult, TrackingSignal

# ─── Detection patterns ────────────────────────────────────────────────────────

# GA4: gtag('config', 'G-XXXXXXXX') OR data-stream-id="G-..."
_GA4_RE = re.compile(
    r"(?:gtag\s*\(\s*['\"]config['\"].*?['\"]G-[A-Z0-9]+['\"]"
    r"|googletagmanager\.com/gtag/js\?id=G-"
    r"|['\"]G-[A-Z0-9]{6,}['\"]"
    r"|google-analytics\.com/g/collect)",
    re.IGNORECASE,
)

# GTM: googletagmanager.com script or noscript iframe
_GTM_RE = re.compile(
    r"(?:googletagmanager\.com/gtm\.js|GTM-[A-Z0-9]+)",
    re.IGNORECASE,
)

# Universal Analytics (UA-) — legacy but still counts as analytics
_UA_RE = re.compile(r"UA-\d{6,}-\d", re.IGNORECASE)

# Meta / Facebook Pixel
_META_PIXEL_RE = re.compile(
    r"(?:connect\.facebook\.net|fbq\s*\(|facebook\.com/tr[/?]"
    r"|_fbq\s*=|facebook-jssdk)",
    re.IGNORECASE,
)

# LinkedIn Insight Tag
_LINKEDIN_RE = re.compile(
    r"(?:snap\.licdn\.com|linkedin\.com/insight-tag"
    r"|window\._linkedin_partner_id)",
    re.IGNORECASE,
)

# Twitter / X Pixel
_TWITTER_RE = re.compile(
    r"(?:static\.ads-twitter\.com|twq\s*\(|t\.co/i/adsct)",
    re.IGNORECASE,
)

# Google Ads conversion
_GADS_RE = re.compile(
    r"(?:googleadservices\.com|google_conversion|gtag.*?AW-\d+)",
    re.IGNORECASE,
)

# Privacy-friendly / lightweight analytics
_PLAUSIBLE_RE = re.compile(r"plausible\.io", re.IGNORECASE)
_FATHOM_RE = re.compile(r"cdn\.usefathom\.com", re.IGNORECASE)
_MATOMO_RE = re.compile(r"(?:matomo\.js|piwik\.js|/piwik/|/matomo/)", re.IGNORECASE)

# Product analytics
_SEGMENT_RE = re.compile(r"cdn\.segment\.(?:com|io)", re.IGNORECASE)
_MIXPANEL_RE = re.compile(r"(?:cdn\.mxpnl\.com|mixpanel\.com/lib)", re.IGNORECASE)
_AMPLITUDE_RE = re.compile(r"cdn\.amplitude\.com", re.IGNORECASE)
_HEAP_RE = re.compile(r"cdn\.heapanalytics\.com", re.IGNORECASE)

# CRM / Marketing automation
_HUBSPOT_RE = re.compile(r"(?:js\.hs-scripts\.com|hs-analytics)", re.IGNORECASE)

# Heatmap / session recording
_HOTJAR_RE = re.compile(r"static\.hotjar\.com", re.IGNORECASE)
_CLARITY_RE = re.compile(r"clarity\.ms", re.IGNORECASE)


def audit_tracking(soup, raw_html: str = "", base_url: str = "") -> TrackingResult:
    """Detect analytics and conversion tracking tools from HTML.

    Args:
        soup: BeautifulSoup of the full HTML document.
        raw_html: Raw HTML string (used for fast regex scanning).
        base_url: Page URL (informational only).

    Returns:
        TrackingResult with detected tools, score, and priority fixes.
    """
    if soup is None:
        return TrackingResult(checked=True)

    # Build a combined text blob from script src attrs + inline script content
    script_blob = _build_script_blob(soup, raw_html)

    signals: list[TrackingSignal] = []

    # ── 1. GA4 ────────────────────────────────────────────────────────────────
    has_ga4, ga4_evidence = _detect(script_blob, _GA4_RE, "GA4 measurement ID")
    signals.append(
        TrackingSignal(
            key="has_ga4",
            label="Google Analytics 4 (GA4)",
            detected=has_ga4,
            evidence=ga4_evidence,
            fix=(
                "Install GA4: add the gtag.js snippet with your G-XXXXXXXX measurement ID "
                "or deploy via Google Tag Manager."
            ),
        )
    )

    # ── 2. GTM ────────────────────────────────────────────────────────────────
    has_gtm, gtm_evidence = _detect(script_blob, _GTM_RE, "GTM-XXXXXXX")
    signals.append(
        TrackingSignal(
            key="has_gtm",
            label="Google Tag Manager (GTM)",
            detected=has_gtm,
            evidence=gtm_evidence,
            fix=(
                "Install GTM to manage all your tracking tags in one place "
                "without code deployments: https://tagmanager.google.com"
            ),
        )
    )

    # ── 3. Meta Pixel ─────────────────────────────────────────────────────────
    has_meta_pixel, meta_evidence = _detect(script_blob, _META_PIXEL_RE, "fbq / connect.facebook.net")
    signals.append(
        TrackingSignal(
            key="has_meta_pixel",
            label="Meta (Facebook) Pixel",
            detected=has_meta_pixel,
            evidence=meta_evidence,
            fix=(
                "Install the Meta Pixel to measure and retarget visitors from Meta ads: "
                "https://www.facebook.com/events/manager/pixel"
            ),
        )
    )

    # ── 4. LinkedIn Insight ───────────────────────────────────────────────────
    has_linkedin, li_evidence = _detect(script_blob, _LINKEDIN_RE, "snap.licdn.com")
    signals.append(
        TrackingSignal(
            key="has_linkedin",
            label="LinkedIn Insight Tag",
            detected=has_linkedin,
            evidence=li_evidence,
            fix=("Add the LinkedIn Insight Tag for B2B retargeting and conversion tracking from LinkedIn campaigns."),
        )
    )

    # ── 5. Other analytics ────────────────────────────────────────────────────
    has_plausible, _ = _detect(script_blob, _PLAUSIBLE_RE)
    has_fathom, _ = _detect(script_blob, _FATHOM_RE)
    has_matomo, _ = _detect(script_blob, _MATOMO_RE)
    has_segment, _ = _detect(script_blob, _SEGMENT_RE)
    has_mixpanel, _ = _detect(script_blob, _MIXPANEL_RE)
    has_amplitude, _ = _detect(script_blob, _AMPLITUDE_RE)
    has_heap, _ = _detect(script_blob, _HEAP_RE)

    # UA legacy
    has_ua, _ = _detect(script_blob, _UA_RE)

    has_other_analytics = any(
        [
            has_plausible,
            has_fathom,
            has_matomo,
            has_segment,
            has_mixpanel,
            has_amplitude,
            has_heap,
            has_ua,
        ]
    )

    other_names = []
    if has_plausible:
        other_names.append("Plausible")
    if has_fathom:
        other_names.append("Fathom")
    if has_matomo:
        other_names.append("Matomo")
    if has_segment:
        other_names.append("Segment")
    if has_mixpanel:
        other_names.append("Mixpanel")
    if has_amplitude:
        other_names.append("Amplitude")
    if has_heap:
        other_names.append("Heap")
    if has_ua:
        other_names.append("Universal Analytics (legacy)")

    if has_other_analytics or has_ga4:
        signals.append(
            TrackingSignal(
                key="has_other_analytics",
                label="Privacy-friendly / product analytics",
                detected=has_other_analytics,
                evidence=", ".join(other_names) if other_names else "",
                fix="Consider adding Plausible or Fathom as a privacy-first analytics alternative.",
            )
        )

    # ── 6. Conversion tracking ────────────────────────────────────────────────
    has_gads, gads_evidence = _detect(script_blob, _GADS_RE, "googleadservices")
    has_twitter_px, _ = _detect(script_blob, _TWITTER_RE)
    has_conversion_tracking = any([has_meta_pixel, has_linkedin, has_gads, has_twitter_px])
    signals.append(
        TrackingSignal(
            key="has_conversion_tracking",
            label="Conversion pixel / ad attribution",
            detected=has_conversion_tracking,
            evidence=gads_evidence if has_gads else "",
            fix=(
                "Install a conversion pixel (Meta, Google Ads, or LinkedIn) to measure "
                "ROI from paid campaigns and enable retargeting audiences."
            ),
        )
    )

    # ── 7. Heatmap / session recording ───────────────────────────────────────
    has_hotjar, hotjar_evidence = _detect(script_blob, _HOTJAR_RE)
    has_clarity, clarity_evidence = _detect(script_blob, _CLARITY_RE)
    has_heatmap = has_hotjar or has_clarity
    heatmap_evidence = hotjar_evidence or clarity_evidence
    signals.append(
        TrackingSignal(
            key="has_heatmap",
            label="Heatmap / session recording",
            detected=has_heatmap,
            evidence=heatmap_evidence,
            fix=(
                "Install Microsoft Clarity (free) or Hotjar to record sessions and "
                "identify where visitors get stuck or drop off."
            ),
        )
    )

    # ── 8. HubSpot ────────────────────────────────────────────────────────────
    has_hubspot, hs_evidence = _detect(script_blob, _HUBSPOT_RE)
    if has_hubspot:
        signals.append(
            TrackingSignal(
                key="has_hubspot",
                label="HubSpot tracking",
                detected=True,
                evidence=hs_evidence,
                fix="",
            )
        )

    # ── Aggregate flags ───────────────────────────────────────────────────────
    has_analytics = has_ga4 or has_gtm or has_other_analytics or has_hubspot
    score = _compute_tracking_score(has_analytics, has_conversion_tracking, has_heatmap)

    priority_fixes = [s.fix for s in signals if not s.detected and s.fix][:3]

    return TrackingResult(
        checked=True,
        has_analytics=has_analytics,
        has_conversion_tracking=has_conversion_tracking,
        has_ga4=has_ga4,
        has_gtm=has_gtm,
        has_meta_pixel=has_meta_pixel,
        has_other_analytics=has_other_analytics,
        has_heatmap=has_heatmap,
        signals=signals,
        tracking_score=score,
        priority_fixes=priority_fixes,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _build_script_blob(soup, raw_html: str) -> str:
    """Build a single text blob from all script src/content for fast scanning."""
    parts: list[str] = []

    # Include raw_html directly (fastest, catches inline scripts + src attrs)
    if raw_html:
        parts.append(raw_html)
    else:
        # Fallback: extract from soup
        for tag in soup.find_all(["script", "iframe", "link"]):
            src = tag.get("src", "") or tag.get("href", "")
            if src:
                parts.append(src)
            if tag.name == "script" and tag.string:
                parts.append(tag.string[:2000])  # limit inline script scanning

    return "\n".join(parts)


def _detect(blob: str, pattern: re.Pattern, label: str = "") -> tuple[bool, str]:
    """Run a regex against the blob and return (detected, evidence_snippet)."""
    m = pattern.search(blob)
    if not m:
        return False, ""
    snippet = m.group(0)[:60].strip()
    return True, snippet


# ─── Scoring ─────────────────────────────────────────────────────────────────


def _compute_tracking_score(
    has_analytics: bool,
    has_conversion: bool,
    has_heatmap: bool,
) -> int:
    """Score 0-100 based on tier of measurement maturity."""
    if not has_analytics:
        return 0  # no measurement at all
    score = 40  # basic analytics installed
    if has_conversion:
        score += 40  # ad attribution / pixel
    if has_heatmap:
        score += 20  # session insight layer
    return min(score, 100)
