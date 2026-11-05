"""
GEO Audit — Conversion readiness sub-audit (v4.12).

Scores how ready the page is to convert AI-referred visitors into leads:

- CTA above the fold: primary action button/link in the first ~20% of body
- Contact form: <form> with at least one email or tel input
- Phone number: tel: link or phone-pattern text
- Testimonials/reviews: review sections, star ratings, named quotes
- AggregateRating schema: structured proof
- Trust badges: SSL, guarantee, award language

Output: scored checklist + prioritised fix copy suggestions.
No network requests — pure HTML/schema analysis.
Informational check — does not affect GEO score.
"""

from __future__ import annotations

import re

from geo_optimizer.models.results import ConversionResult, ConversionSignal

# ─── Detection patterns ────────────────────────────────────────────────────────

# CTA keywords (case-insensitive) — used in link/button text
_CTA_RE = re.compile(
    r"\b(?:get started|book\s+(?:a|now|free)?|reserve|schedule|contact us|call us|"
    r"request|sign up|try free|free trial|get\s+(?:a\s+)?(?:free\s+)?quote|"
    r"quote|demandez|commencer|réserver|consulter|obtenir|inscription|essai gratuit|"
    r"soumission|devis)\b",
    re.IGNORECASE,
)

# Phone number patterns — North American and international
_PHONE_RE = re.compile(
    r"(?:\+?\d[\d\s\-\(\)\.]{7,}\d|tel:[+\d\-\(\)\s]+)",
    re.IGNORECASE,
)

# Testimonial section indicators
_TESTIMONIAL_RE = re.compile(
    r"\b(?:testimonial|review|avis|témoignage|client\s+say|what\s+(?:our\s+)?client|"
    r"what\s+people\s+say|rated|rating|stars?|étoile|note\s+\d|satisfaction)\b",
    re.IGNORECASE,
)

# Trust badge language
_TRUST_BADGE_RE = re.compile(
    r"\b(?:ssl\s+secure|money.back\s+guarantee|100\s*%\s+(?:satisfaction|guaranteed?)|"
    r"certified|accredited|award|accrédité|certifié|garantie|garanti|no\s+contract|"
    r"sans\s+engagement|licensed|insured|assuré)\b",
    re.IGNORECASE,
)

# "Above the fold" heuristic: first N tags in <body>
_ABOVE_FOLD_TAG_LIMIT = 30


def audit_conversion(
    soup,
    base_url: str = "",
    schema=None,
    meta=None,
    content=None,
) -> ConversionResult:
    """Analyse HTML for conversion readiness signals.

    Args:
        soup: BeautifulSoup of the full HTML document.
        base_url: Page URL (informational only).
        schema: SchemaResult (used to check AggregateRating).
        meta: MetaResult (unused currently, reserved).
        content: ContentResult (unused currently, reserved).

    Returns:
        ConversionResult with scored checklist and priority fixes.
    """
    if soup is None:
        return ConversionResult(checked=True)

    body = soup.find("body")
    if not body:
        return ConversionResult(checked=True)

    signals: list[ConversionSignal] = []

    # ── 1. CTA above the fold ─────────────────────────────────────────────────
    cta_above_fold, cta_count, cta_evidence = _check_cta(body)
    signals.append(
        ConversionSignal(
            key="cta_above_fold",
            label="Primary CTA visible above the fold",
            detected=cta_above_fold,
            evidence=cta_evidence,
            fix='Add a prominent action button in the hero section: "Book a free consultation →"',
        )
    )

    # ── 2. Contact form ───────────────────────────────────────────────────────
    has_contact_form, form_evidence = _check_contact_form(body)
    signals.append(
        ConversionSignal(
            key="has_contact_form",
            label="Contact / lead capture form present",
            detected=has_contact_form,
            evidence=form_evidence,
            fix="Embed a short contact form (name, email, message) on the homepage or a linked /contact page.",
        )
    )

    # ── 3. Phone number ───────────────────────────────────────────────────────
    has_phone, phone_evidence = _check_phone(body)
    signals.append(
        ConversionSignal(
            key="has_phone",
            label="Phone number / tel: link present",
            detected=has_phone,
            evidence=phone_evidence,
            fix='Add a clickable phone number: <a href="tel:+15141234567">(514) 123-4567</a>',
        )
    )

    # ── 4. Testimonials / reviews ─────────────────────────────────────────────
    has_testimonials, testimonial_evidence = _check_testimonials(body)
    signals.append(
        ConversionSignal(
            key="has_testimonials",
            label="Testimonials or social proof section",
            detected=has_testimonials,
            evidence=testimonial_evidence,
            fix='Add a "What our clients say" section with 3+ named reviews and star ratings.',
        )
    )

    # ── 5. AggregateRating schema ─────────────────────────────────────────────
    has_aggregate_rating = _check_aggregate_rating(soup, schema)
    signals.append(
        ConversionSignal(
            key="has_aggregate_rating",
            label="AggregateRating structured data",
            detected=has_aggregate_rating,
            evidence="AggregateRating JSON-LD block detected" if has_aggregate_rating else "",
            fix=(
                'Add AggregateRating schema: {"@type":"AggregateRating","ratingValue":"4.9",'
                '"reviewCount":"47"} inside your Organization or LocalBusiness JSON-LD.'
            ),
        )
    )

    # ── 6. Trust badges ───────────────────────────────────────────────────────
    has_trust_badges, badge_evidence = _check_trust_badges(body)
    signals.append(
        ConversionSignal(
            key="has_trust_badges",
            label="Trust badges / guarantees / certifications",
            detected=has_trust_badges,
            evidence=badge_evidence,
            fix='Add a short trust line near CTAs: "Licensed · Insured · 5-star rated" or a money-back guarantee.',
        )
    )

    # ── 7. Form friction (form-cro) ───────────────────────────────────────────
    max_form_fields, has_strong_submit, has_privacy_near_form = _check_form_friction(body)
    if has_contact_form:
        signals.append(
            ConversionSignal(
                key="form_submit_copy",
                label="Form submit button uses action-oriented copy",
                detected=has_strong_submit,
                evidence="",
                fix=(
                    'Replace generic "Submit" / "Send" with specific copy: '
                    '"Get My Free Quote", "Book a Consultation", "Request Demo".'
                ),
            )
        )
        signals.append(
            ConversionSignal(
                key="form_privacy_text",
                label="Privacy / no-spam text near form",
                detected=has_privacy_near_form,
                evidence="",
                fix='Add a short trust line beneath the submit button: "No spam. We\'ll never share your info."',
            )
        )

    # ── 8. Social auth options ────────────────────────────────────────────────
    has_social_auth, social_auth_evidence = _check_social_auth(body)

    # ── 9. Mobile viewport ────────────────────────────────────────────────────
    has_mobile_viewport = _check_mobile_viewport(soup)
    if not has_mobile_viewport:
        signals.append(
            ConversionSignal(
                key="mobile_viewport",
                label="Mobile viewport meta tag present",
                detected=False,
                evidence="",
                fix='Add <meta name="viewport" content="width=device-width, initial-scale=1"> to <head>.',
            )
        )

    # ── Score ──────────────────────────────────────────────────────────────────
    score = _compute_conversion_score(signals)

    # ── Priority fixes (top 3 undetected) ────────────────────────────────────
    priority_fixes = [
        s.fix for s in sorted(signals, key=lambda s: _signal_weight(s.key), reverse=True) if not s.detected
    ][:3]

    return ConversionResult(
        checked=True,
        cta_above_fold=cta_above_fold,
        has_contact_form=has_contact_form,
        has_phone_number=has_phone,
        has_testimonials=has_testimonials,
        has_aggregate_rating=has_aggregate_rating,
        has_trust_badges=has_trust_badges,
        cta_count=cta_count,
        signals=signals,
        conversion_score=score,
        priority_fixes=priority_fixes,
        # form-cro extensions
        max_form_fields=max_form_fields,
        has_strong_submit_copy=has_strong_submit,
        has_privacy_near_form=has_privacy_near_form,
        has_social_auth=has_social_auth,
        has_mobile_viewport=has_mobile_viewport,
    )


# ─── Signal detectors ─────────────────────────────────────────────────────────


def _check_cta(body) -> tuple[bool, int, str]:
    """Return (cta_above_fold, total_cta_count, evidence_text)."""
    all_tags = list(body.descendants)
    above_fold_tags = [t for t in all_tags if hasattr(t, "name")][:_ABOVE_FOLD_TAG_LIMIT]

    cta_count = 0
    cta_above = False
    first_evidence = ""

    # Check all buttons and <a> tags across the full body
    for el in body.find_all(["a", "button"]):
        text = el.get_text(strip=True)
        if _CTA_RE.search(text):
            cta_count += 1
            if not first_evidence:
                first_evidence = text[:60]

    # Check whether any CTA appears in above-fold region
    for el in above_fold_tags:
        if not hasattr(el, "get_text"):
            continue
        text = el.get_text(strip=True)
        if el.name in ("a", "button") and _CTA_RE.search(text):
            cta_above = True
            break

    return cta_above, cta_count, first_evidence


def _check_contact_form(body) -> tuple[bool, str]:
    """Detect a contact/lead form with email or tel input."""
    for form in body.find_all("form"):
        for inp in form.find_all("input"):
            type_ = inp.get("type", "text").lower()
            name_ = inp.get("name", "").lower()
            placeholder_ = inp.get("placeholder", "").lower()
            if type_ in ("email", "tel") or "email" in name_ or "email" in placeholder_:
                action = form.get("action", "")[:60]
                return True, f'<form action="{action}">'
        # Also check textarea (generic contact form)
        if form.find("textarea"):
            return True, "<form with textarea>"
    return False, ""


def _check_phone(body) -> tuple[bool, str]:
    """Detect a phone number via tel: link or phone-like text."""
    # First check tel: links (most reliable)
    for a in body.find_all("a", href=True):
        if a["href"].lower().startswith("tel:"):
            return True, a["href"][:30]

    # Fallback: scan visible text for phone pattern
    text = body.get_text(separator=" ")
    m = _PHONE_RE.search(text)
    if m:
        return True, m.group(0)[:30]

    return False, ""


def _check_testimonials(body) -> tuple[bool, str]:
    """Detect a reviews or testimonials section."""
    # Check class attributes for common patterns
    for el in body.find_all(True, attrs={"class": _testimonial_class_matcher}):
        return True, f"<{el.name} class contains review/testimonial>"

    # Check id attributes separately (BS4 AND-s multiple attrs, so do them one by one)
    for el in body.find_all(True, attrs={"id": _testimonial_class_matcher}):
        return True, f"<{el.name} id contains review/testimonial>"

    # Check visible text for testimonial language
    text = body.get_text(separator=" ")
    m = _TESTIMONIAL_RE.search(text)
    if m:
        return True, m.group(0)[:40]

    return False, ""


def _testimonial_class_matcher(value) -> bool:
    if not value:
        return False
    if isinstance(value, list):
        value = " ".join(value)
    return bool(
        re.search(
            r"\b(?:testimonial|review|avis|rating|stars?|temoignage)\b",
            value,
            re.IGNORECASE,
        )
    )


def _check_aggregate_rating(soup, schema) -> bool:
    """Check for AggregateRating in JSON-LD schema or inline markup."""
    # Check SchemaResult if provided
    if schema is not None:
        types = getattr(schema, "schema_types", [])
        if isinstance(types, list) and any("AggregateRating" in t for t in types):
            return True
        # Check raw schema JSON-LD text
        raw = getattr(schema, "raw_schemas", [])
        for blob in raw if isinstance(raw, list) else []:
            if "AggregateRating" in str(blob):
                return True

    # Also check raw JSON-LD in soup
    if soup:
        import json as _json

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = _json.loads(script.string or "")
                if "AggregateRating" in str(data):
                    return True
            except (ValueError, AttributeError):
                pass

    return False


def _check_trust_badges(body) -> tuple[bool, str]:
    """Detect trust/guarantee/certification language."""
    text = body.get_text(separator=" ")
    m = _TRUST_BADGE_RE.search(text)
    if m:
        return True, m.group(0)[:50]
    return False, ""


# ─── Form-CRO detectors (v4.13) ──────────────────────────────────────────────

# Weak submit button copy
_WEAK_SUBMIT_RE = re.compile(
    r"^(?:submit|send|go|ok|confirmer?|envoyer?|valider?|soumettre)$",
    re.IGNORECASE,
)

# Strong / action-oriented submit copy
_STRONG_SUBMIT_RE = re.compile(
    r"\b(?:get|book|start|request|download|schedule|reserve|claim|try|join|"
    r"sign up|quote|demo|calculate|subscribe|register|apply|contact|send\s+message|"
    r"obtenir|réserver|commencer|demander|calculer|s'inscrire|télécharger)\b",
    re.IGNORECASE,
)

# Privacy / no-spam text near form
_FORM_PRIVACY_RE = re.compile(
    r"\b(?:no\s+spam|privacy|we\s+(?:won't|will\s+not|never)\s+(?:share|sell)|"
    r"unsubscribe\s+anytime|pas\s+de\s+spam|confidentialit[eé]|"
    r"we\s+respect\s+your|your\s+info(?:rmation)?\s+is\s+safe)\b",
    re.IGNORECASE,
)

# Social auth / OAuth buttons
_SOCIAL_AUTH_RE = re.compile(
    r"(?:sign\s+(?:in|up)\s+with\s+(?:google|apple|microsoft|facebook)|"
    r"continue\s+with\s+(?:google|apple|microsoft)|"
    r"oauth\.google\.|accounts\.google\.com|appleid\.apple\.com|"
    r"login\.microsoftonline|class=[\"'][^\"']*(?:google-btn|apple-id-btn|"
    r"btn-google|btn-apple|btn-microsoft|social-login)[^\"']*[\"'])",
    re.IGNORECASE,
)


def _check_form_friction(body) -> tuple[int, bool, bool]:
    """Analyse form fields for friction signals.

    Returns:
        (max_field_count, has_strong_submit_copy, has_privacy_near_form)
    """
    max_fields = 0
    has_strong_submit = False
    has_privacy = False

    for form in body.find_all("form"):
        # Count input fields (exclude hidden, submit, button types)
        inputs = [
            i
            for i in form.find_all("input")
            if i.get("type", "text").lower() not in ("hidden", "submit", "button", "image", "reset")
        ]
        textareas = form.find_all("textarea")
        selects = form.find_all("select")
        field_count = len(inputs) + len(textareas) + len(selects)
        max_fields = max(max_fields, field_count)

        # Check submit button copy quality
        for btn in form.find_all(["button", "input"]):
            btn_type = btn.get("type", "submit").lower()
            if btn_type in ("submit", "button"):
                text = (btn.get_text(strip=True) or btn.get("value", "")).strip()
                if text:
                    if _STRONG_SUBMIT_RE.search(text) and not _WEAK_SUBMIT_RE.match(text):
                        has_strong_submit = True
                    elif not _WEAK_SUBMIT_RE.match(text) and len(text) > 3:
                        # Not clearly weak and has real text — benefit of the doubt
                        has_strong_submit = True

        # Check for privacy text in / near form (check form text + siblings)
        form_text = form.get_text(separator=" ")
        if _FORM_PRIVACY_RE.search(form_text):
            has_privacy = True
        else:
            # Check sibling elements just after the form
            for sibling in form.next_siblings:
                sib_text = getattr(sibling, "get_text", lambda: "")()
                if sib_text and _FORM_PRIVACY_RE.search(sib_text):
                    has_privacy = True
                    break

    return max_fields, has_strong_submit, has_privacy


def _check_social_auth(body) -> tuple[bool, str]:
    """Detect social OAuth login/signup buttons."""
    html = str(body)
    m = _SOCIAL_AUTH_RE.search(html)
    if m:
        return True, m.group(0)[:60]
    return False, ""


def _check_mobile_viewport(soup) -> bool:
    """Detect <meta name="viewport"> in <head>."""
    head = soup.find("head")
    if not head:
        return False
    for meta in head.find_all("meta"):
        if meta.get("name", "").lower() == "viewport":
            return True
    return False


# ─── Scoring ─────────────────────────────────────────────────────────────────

_SIGNAL_WEIGHTS = {
    "cta_above_fold": 30,
    "has_contact_form": 20,
    "has_phone": 15,
    "has_testimonials": 15,
    "has_aggregate_rating": 10,
    "has_trust_badges": 10,
}


def _signal_weight(key: str) -> int:
    return _SIGNAL_WEIGHTS.get(key, 5)


def _compute_conversion_score(signals: list[ConversionSignal]) -> int:
    """Weighted score 0-100 based on detected signals."""
    total = sum(_SIGNAL_WEIGHTS.get(s.key, 5) for s in signals)
    earned = sum(_SIGNAL_WEIGHTS.get(s.key, 5) for s in signals if s.detected)
    if total == 0:
        return 0
    return round((earned / total) * 100)
