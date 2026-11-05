"""
GEO Audit — Marketing readiness sub-audit (v4.13).

Analyses a page through three marketing lenses drawn from the marketingskills framework
(github.com/alirezarezvani/claude-skills/tree/main/marketing-skill):

1. **Copywriting quality** (page-cro + copywriting skills)
   - H1 / headline effectiveness: outcome-focused vs. feature-focused vs. generic
   - Value proposition clarity: is there a "you get X" framing above the fold?
   - CTA copy: weak ("Submit", "Learn More") vs. strong ("Start Free Trial", "Book Now")
   - Benefit vs. feature language ratio

2. **Content strategy signals** (content-strategy + ai-seo skills)
   - Blog / content hub presence
   - FAQ section or schema
   - Comparison / alternatives pages (high AI citation value)
   - Pricing page + /pricing.md for AI agents
   - Email/lead capture
   - Social proof with numbers

3. **AI presence** (ai-seo + schema-markup + programmatic-seo skills)
   - robots.txt: AI crawlers blocked? (GPTBot, PerplexityBot, ClaudeBot, Google-Extended)
   - Definition block in first 300 words (Pillar 1: extractability)
   - Attributed vs. unattributed statistics (cited stats > naked numbers)
   - JS-heavy content detection (AI crawlers can't execute JS)
   - Location pages presence (programmatic-seo Locations playbook)
   - Organization sameAs + author schema (entity authority for AI citations)

Combines with existing audit_conversion, audit_perf, and the GEO citability score
to produce MarketingResult with prioritised actions.

Informational check — does not affect GEO score.
"""

from __future__ import annotations

import re
from typing import cast
from urllib.parse import urljoin, urlparse

from geo_optimizer.core.audit_marketing.planning import _compute_copy_score, _compute_strategy_score
from geo_optimizer.core.citability.platform import _GENERIC_ALT_RE
from geo_optimizer.models.results import (
    AIPresenceResult,
    ContentStrategyResult,
    CopywritingResult,
    ImageAuditResult,
)

# ─── Copywriting patterns ─────────────────────────────────────────────────────

# Weak CTAs from the page-cro skill (submit, learn more, click here, etc.)
_WEAK_CTA_RE = re.compile(
    r"^(?:submit|learn more|click here|read more|more info(?:rmation)?|"
    r"view more|see more|continue|next|ok|okay|yes|no|cancel|go|enter|"
    r"en savoir plus|lire la suite|voir plus|cliquez ici|suivant)$",
    re.IGNORECASE,
)

# Strong CTAs from the copywriting skill (action + outcome oriented)
_STRONG_CTA_RE = re.compile(
    r"\b(?:start|get started|try|book|reserve|schedule|request|sign up|join|"
    r"download|claim|grab|unlock|access|discover|explore|see how|watch demo|"
    r"get (?:a |my |your |free )?(?:quote|demo|trial|report|audit)|"
    r"free trial|start free|try free|"
    r"commencer|réserver|obtenir|télécharger|essayer|démarrer|"
    r"soumission gratuite|démo gratuite)\b",
    re.IGNORECASE,
)

# Generic / empty headlines (vague, no info-value)
_GENERIC_H1_RE = re.compile(
    r"^(?:welcome|home|page|untitled|hello|bienvenue|accueil|"
    r"welcome to .{1,30}|bienvenue .{1,30})$",
    re.IGNORECASE,
)

# Outcome-focused language patterns (customer benefit)
_OUTCOME_RE = re.compile(
    r"\b(?:save|reduce|increase|improve|grow|boost|cut|eliminate|avoid|"
    r"faster|easier|better|more|less|without|no more|get (?:rid of|more)|"
    r"économiser|réduire|augmenter|améliorer|grandir|accélérer|plus facile|"
    r"gagner du temps|sans|élimine)\b",
    re.IGNORECASE,
)

# Feature-focused language (company talking about itself)
_FEATURE_RE = re.compile(
    r"\b(?:we offer|we provide|we are|we have|our (?:product|service|platform|"
    r"solution|software|tool|team|company)|we help|we specialize|founded in|"
    r"nous offrons|nous proposons|notre (?:produit|service|plateforme|solution|équipe)|"
    r"nous sommes|nous avons)\b",
    re.IGNORECASE,
)

# Benefit language (you-focused)
_BENEFIT_RE = re.compile(
    r"\b(?:you(?:'ll| will| can| get| save| reduce| have)| your |"
    r"help you |for you |"
    r"vous(?:\s+allez|\s+pouvez|\s+obtenez|\s+économisez)| votre | pour vous )\b",
    re.IGNORECASE,
)

# Value proposition patterns (what + for whom + outcome)
_VALUE_PROP_RE = re.compile(
    r"(?:"
    r"(?:help|helps|helping)\s+\w+\s+(?:to\s+)?\w+"  # "helps [X] do Y"
    r"|(?:the|a|an)\s+\w+\s+(?:for|that|to)\s+\w+"  # "the tool for X"
    r"|(?:save|cut|reduce|grow|increase|improve)\s+your"  # "save your X"
    r"|without\s+(?:the|any)\b"  # "without the hassle"
    r")",
    re.IGNORECASE,
)

# ─── Content strategy patterns ────────────────────────────────────────────────

# Blog / content hub URL patterns
_BLOG_PATH_RE = re.compile(
    r"^/(?:blog|articles?|news|insights?|resources?|posts?|content|"
    r"blogue|nouvelles|ressources)",
    re.IGNORECASE,
)

# Comparison / alternatives URL patterns (high AI citability — ai-seo skill)
_COMPARISON_PATH_RE = re.compile(
    r"^/(?:vs|versus|compare|alternatives?|comparaison|par-rapport)",
    re.IGNORECASE,
)

# Pricing URL patterns
_PRICING_PATH_RE = re.compile(
    r"^/(?:pricing|price|plans?|tarif|tarification|forfait)",
    re.IGNORECASE,
)

# FAQ section / heading patterns
_FAQ_RE = re.compile(
    r"\b(?:faq|frequently asked|questions\s+(?:fréquentes|fréquemment)|"
    r"common\s+questions|q\s*&\s*a|questions\s+réponses)\b",
    re.IGNORECASE,
)

# Case study / proof patterns
_PROOF_RE = re.compile(
    r"\b(?:case\s+study|case\s+studies|success\s+stor|client\s+(?:result|success)|"
    r"étude\s+de\s+cas|résultats\s+client|témoignage|success)\b",
    re.IGNORECASE,
)

# Numbers-as-proof patterns ("10,000 customers", "3× faster", "saved $1M")
_NUMBER_PROOF_RE = re.compile(
    r"(?:\d[\d,\.]*\s*(?:customers?|clients?|users?|teams?|companies|businesses|"
    r"entreprises|utilisateurs|équipes)"
    r"|\d+[\d,\.]*\s*(?:×|x|%)\s*(?:faster|more|better|less|reduction|improvement)"
    r"|\$[\d,\.]+(?:M|K|B)?\s*(?:saved|reduced|earned|generated)"
    r"|(?:over|more than|plus de)\s+\d[\d,\.]*)",
    re.IGNORECASE,
)

# Lead magnet / email capture patterns
_LEAD_MAGNET_RE = re.compile(
    r"\b(?:free\s+(?:guide|ebook|template|checklist|report|tool|trial|demo|consultation|audit)|"
    r"download\s+(?:the|our|your)|subscribe|newsletter|"
    r"guide gratuit|ebook gratuit|modèle gratuit|liste de vérification|"
    r"abonnez[-\s]vous|infolettre)\b",
    re.IGNORECASE,
)

# Above-fold tag limit (first N top-level tags in body)
_ABOVE_FOLD_TAGS = 25

# ─── AI presence patterns (ai-seo + schema-markup + programmatic-seo skills) ─

# Known AI crawlers — blocking any of these is an immediate visibility killer
# Source: ai-seo skill robots.txt section
_AI_BOTS: dict[str, str] = {
    "GPTBot": "ChatGPT / OpenAI",
    "PerplexityBot": "Perplexity",
    "ClaudeBot": "Anthropic / Claude",
    "anthropic-ai": "Anthropic (alternate)",
    "Google-Extended": "Google AI Overviews",
    "Applebot-Extended": "Apple Intelligence",
    "cohere-ai": "Cohere",
}

# Definition block: sentence where a term is defined ("X is …", "X est …")
# Must be in first ~300 words to count as an extractable definition.
# Supports EN + FR opening letters for Québec / bilingual sites.
_DEFINITION_BLOCK_RE = re.compile(
    r"[A-ZÀÂÄÇÉÈÊËÎÏÔŒÙÛÜŸ][^.!?]{4,60}\s+"
    r"(?:is|are|refers?\s+to|means?|denotes?|"
    r"est|sont|réfère\s+à|réfèrent\s+à|désigne|désignent|signifie|signifient|"
    r"constitue|constituent|représente|représentent)\s+"
    r"[^.!?]{10,150}[.!?]",
    re.MULTILINE,
)

# Attributed statistics: a percentage near a named source
# Matches: "According to X", "Selon X", "(Source, 2024)", "X 2024 report"
_ATTRIBUTED_STAT_RE = re.compile(
    r"(?:"
    r"according\s+to\s+\w[\w\s,\.]{2,40}"  # "According to McKinsey"
    r"|selon\s+[\wÀ-ÿ\s,'\.]{2,45}"  # "Selon la SCHL"
    r"|d['\u2019]après\s+[\wÀ-ÿ\s,'\.]{2,45}"  # "D'après Statistique Canada"
    r"|\w[\w\s]{2,30}\s+(?:found|reports?|shows?|states?)\s+that"  # "Gartner found that"
    r"|\(\s*[\wÀ-ÿ\s]{2,35},?\s*\d{4}\s*\)"  # "(Princeton, 2024)", "(CMHC, 2023)"
    r"|[\wÀ-ÿ\s]{2,30},?\s*\d{4}\s+(?:survey|study|report|research|sondage|étude|rapport)"
    r")",
    re.IGNORECASE,
)

# Bare percentage — a number with % not preceded by an attribution
_RAW_STAT_RE = re.compile(r"\b\d+(?:\.\d+)?%")

# ─── H2 keyword quality patterns ─────────────────────────────────────────────

# AI-generated / generic H2 labels that add no keyword value
_GENERIC_H2_RE = re.compile(
    r"^(?:introduction|overview|summary|conclusion|more info|details|section|"
    r"content|information|description|about|pilotage|chunking|contexte|"
    r"méthode de pilotage|chunking lisible|accès direct|preuves de confiance|"
    r"pages utiles|cadre d'exécution|engagement de service|"
    r"définition du service|définition|cadre|"
    r"visit(?:eurs)? et agents|agents ia)\s*$",
    re.IGNORECASE,
)

# Service / location keywords that indicate a keyword-targeted H2
_SERVICE_H2_RE = re.compile(
    r"\b(?:gestion|syndicat|copropriété|copropriete|locatif|locative|location|"
    r"airbnb|immobilier|immobilière|condo|propriét|montréal|montreal|laval|"
    r"longueuil|brossard|québec|québec|rive-sud|"
    r"management|property|rental|condo|real estate|"
    r"service|tarif|prix|soumission|consultation|"
    r"pourquoi|nos clients|témoignage|avantage)\b",
    re.IGNORECASE,
)

# ─── Image SEO patterns ───────────────────────────────────────────────────────

# Keywords that should appear in image filenames / alt text for property mgmt
_IMAGE_KEYWORD_RE = re.compile(
    r"(?:gestion|syndicat|copropriete|copropriété|locatif|location|airbnb|"
    r"immobilier|immobilière|condo|montreal|laval|propriet|management|"
    r"property|rental|building|immeuble|bâtiment)",
    re.IGNORECASE,
)

_PROPERTY_VERTICALS = {"real-estate-proptech", "property-management", "real-estate", "proptech"}


def _is_property_marketing_context(vertical: str = "auto", page_keyword: str = "", text: str = "") -> bool:
    if vertical in _PROPERTY_VERTICALS:
        return True
    return bool(_IMAGE_KEYWORD_RE.search(f"{page_keyword} {text}".lower()))


# ─── Industry membership / backlink trust patterns ────────────────────────────

# Industry trust / membership signals — generic cross-vertical patterns
# plus vertical-specific ones. The vertical-specific patterns are filtered
# at runtime so the module never hard-codes a single industry.
_MEMBERSHIP_GENERIC: list[tuple[str, str]] = [
    ("BBB", r"\bBBB\b|Better Business Bureau"),
    ("Chambre de commerce", r"Chambre\s+de\s+commerce"),
    ("ISO certified", r"\bISO\s+\d{4,5}\b"),
    ("Certified member", r"\bmembre\s+certifié\b|\bcertified\s+member\b"),
    ("Accredited", r"\baccrédité\b|\baccredited\b"),
]

_MEMBERSHIP_BY_VERTICAL: dict[str, list[tuple[str, str]]] = {
    "real-estate-proptech": [
        ("RGCQ", r"\bRGCQ\b"),
        ("CORPIQ", r"\bCORPIQ\b"),
        ("APCHQ", r"\bAPCHQ\b"),
        ("OACIQ", r"\bOACIQ\b"),
        ("ACI/CREA", r"\bACI\b|\bCREA\b"),
    ],
    "saas": [
        ("SOC 2", r"\bSOC\s*2\b"),
        ("ISO 27001", r"\bISO\s*27001\b"),
        ("GDPR", r"\bGDPR\b"),
        ("G2", r"\bG2\s+(?:Crowd|Leader|Verified)\b"),
        ("Capterra", r"\bCapterra\b"),
    ],
    "health": [
        ("Collège des médecins", r"Collège\s+des\s+médecins"),
        ("RAMQ", r"\bRAMQ\b"),
        ("CMQ", r"\bCMQ\b"),
        ("OPQ", r"\bOPQ\b"),
    ],
    "legal": [
        ("Barreau", r"\bBarreau\b"),
        ("Chambre des notaires", r"Chambre\s+des\s+notaires"),
    ],
    "e-commerce": [
        ("Shopify Partner", r"Shopify\s+(?:Partner|Expert|Plus)"),
        ("PCI DSS", r"\bPCI\s+DSS\b"),
        ("Visa/MC Verified", r"\bVerified\s+by\s+Visa\b|\bMastercard\s+SecureCode\b"),
    ],
    "restaurant": [
        ("MAPAQ", r"\bMAPAQ\b"),
        ("Health permit", r"permis\s+(?:de\s+)?santé|health\s+permit"),
    ],
    "generic": [],
}

# ─── LocalBusiness schema fields ─────────────────────────────────────────────

# Checked in audit_content_strategy via JSON-LD parsing

# Location page URL patterns — service + city or just /city/
# Covers major Canadian cities relevant to the proptech vertical
_LOCATION_PATH_RE = re.compile(
    r"^/(?:"
    r"[a-z][a-z-]+-(?:montreal|quebec|laval|longueuil|brossard|ottawa|toronto|"
    r"calgary|vancouver|edmonton|winnipeg|hamilton|longueuil|gatineau|sherbrooke|"
    r"levis|kelowna|abbotsford|mississauga|brampton|surrey|richmond|burnaby|"
    r"markham|vaughan|richmond-hill|oakville|burlington)"
    r"|(?:montreal|quebec|laval|longueuil|brossard|ottawa|toronto|calgary|"
    r"vancouver|edmonton|winnipeg|hamilton|gatineau|sherbrooke|levis|kelowna|"
    r"abbotsford|mississauga|brampton|surrey|richmond|burnaby|markham|vaughan|"
    r"richmond-hill|oakville|burlington)(?:/[a-z-]+)?)",
    re.IGNORECASE,
)


def audit_copywriting(soup, meta=None, vertical: str = "auto", page_keyword: str = "") -> CopywritingResult:
    """Analyse copywriting quality from HTML."""
    body = soup.find("body")
    if not body:
        return CopywritingResult(checked=True)

    issues: list[str] = []
    suggestions: list[str] = []
    if not page_keyword:
        page_keyword = _extract_page_keyword(soup)
    property_context = _is_property_marketing_context(vertical, page_keyword, body.get_text(" ", strip=True)[:2000])

    # ── H1 analysis ───────────────────────────────────────────────────────────
    h1_tag = soup.find("h1")
    h1_text = h1_tag.get_text(strip=True) if h1_tag else ""

    h1_is_generic = bool(_GENERIC_H1_RE.match(h1_text)) if h1_text else True
    h1_is_outcome = bool(_OUTCOME_RE.search(h1_text)) if h1_text else False
    h1_is_feature = bool(_FEATURE_RE.search(h1_text)) if h1_text else False

    if h1_is_generic or not h1_text:
        issues.append(f'H1 is generic or missing: "{h1_text or "(none)"}"')
        example = (
            "Manage your rental portfolio in minutes, not hours"
            if property_context
            else "Launch weekly AI visibility reports without manual spreadsheets"
        )
        suggestions.append(
            "Replace generic H1 with an outcome-focused headline: "
            '"[Verb] [desired outcome] without [pain point]" '
            f'— e.g. "{example}"'
        )
    elif h1_is_feature and not h1_is_outcome:
        issues.append(f'H1 is feature-focused (talks about you, not the customer): "{h1_text[:60]}"')
        before = "We provide property management services" if property_context else "We provide AI audit software"
        after = (
            "Rent faster, worry less — full-service property management for Montreal landlords"
            if property_context
            else "See which AI answers cite your brand before competitors do"
        )
        suggestions.append(f'Rewrite H1 to lead with the customer outcome. Instead of "{before}" → "{after}"')

    # ── Value proposition above fold ──────────────────────────────────────────
    # Check first ~25 body tags for value prop language
    above_fold_text = _get_above_fold_text(body)
    has_value_prop = bool(_VALUE_PROP_RE.search(above_fold_text))
    value_prop_snippet = ""
    if has_value_prop:
        m = _VALUE_PROP_RE.search(above_fold_text)
        if m:
            # Extract sentence context around match
            start = max(0, m.start() - 40)
            end = min(len(above_fold_text), m.end() + 40)
            value_prop_snippet = "…" + above_fold_text[start:end].strip() + "…"

    if not has_value_prop:
        issues.append("No clear value proposition found above the fold")
        suggestions.append(
            "Add a sub-headline below your H1 that explains the value in one sentence: "
            '"[Product] helps [audience] [achieve outcome] without [pain point]." '
            "Keep it under 20 words — clarity beats cleverness."
        )

    # ── CTA copy analysis ─────────────────────────────────────────────────────
    weak_ctas: list[str] = []
    strong_ctas: list[str] = []

    for el in body.find_all(["a", "button"]):
        text = el.get_text(strip=True)
        if not text or len(text) > 60:
            continue
        if _WEAK_CTA_RE.match(text):
            weak_ctas.append(text)
        elif _STRONG_CTA_RE.search(text):
            strong_ctas.append(text)

    if weak_ctas and not strong_ctas:
        issues.append(f"All CTAs use weak copy ({', '.join(weak_ctas[:3])}). These don't communicate value.")
        suggestions.append(
            "Replace weak CTAs with action + outcome copy. "
            'Examples: "Get a Free Quote", "Book Your Consultation", '
            '"Start Managing for Free". The button should answer "what do I get?"'
        )
    elif weak_ctas:
        issues.append(f"Some CTAs still use weak copy: {', '.join(set(weak_ctas[:3]))}")
        suggestions.append(
            f"Upgrade weak CTAs. You already have strong ones ({', '.join(strong_ctas[:2])}) "
            "— apply the same pattern everywhere."
        )

    # ── Benefit vs. feature language ─────────────────────────────────────────
    full_text = body.get_text(separator=" ")
    benefit_count = len(_BENEFIT_RE.findall(full_text))
    feature_count = len(_FEATURE_RE.findall(full_text))
    total = benefit_count + feature_count
    benefit_ratio = round(benefit_count / total, 2) if total > 0 else 0.0

    if benefit_ratio < 0.3 and total > 5:
        issues.append(
            f"Copy is {round((1 - benefit_ratio) * 100)}% feature-focused "
            f"({feature_count} 'we/our' vs {benefit_count} 'you/your' phrases). "
            "Customers care about their outcome, not your features."
        )
        suggestions.append(
            'Audit every "we offer X" sentence and rewrite as "you get X." '
            'Rule of thumb: the word "you" should appear more than "we" on any page.'
        )

    # ── H2 keyword quality ────────────────────────────────────────────────────
    h2_tags = soup.find_all("h2")
    h2_count = len(h2_tags)
    h2_texts = [h.get_text(strip=True) for h in h2_tags[:8]]
    if property_context:
        h2_service_count = sum(1 for t in h2_texts if _SERVICE_H2_RE.search(t))
    else:
        h2_service_count = sum(1 for t in h2_texts if len(t.split()) >= 2 and not _GENERIC_H2_RE.match(t))
    h2_generic_count = sum(1 for t in h2_texts if _GENERIC_H2_RE.match(t))

    if h2_count == 0:
        h2_keyword_quality = "missing"
        issues.append("No H2 headings found — add 5-8 H2s targeting your key services and cities.")
        examples = (
            '"Gestion de syndicat de copropriété à Montréal", '
            '"Gestion locative résidentielle", "Gestion Airbnb Montréal"'
            if property_context
            else '"AI visibility benchmarking", "Competitor citation tracking", "Weekly GEO reports"'
        )
        suggestions.append(
            "Structure your page with H2s for each service or use case: "
            f"{examples}. Each H2 = one keyword cluster Google can rank you for."
        )
    elif h2_generic_count > h2_count // 2:
        h2_keyword_quality = "ai-focused"
        issues.append(
            f"{h2_generic_count}/{h2_count} H2s use generic/AI-optimised labels with no Google keyword value "
            f'(e.g. "{h2_texts[0][:50]}"). Rewrite them around services and cities.'
        )
        examples = (
            '"Gestion de syndicat de copropriété Montréal", "Nos services de gestion locative", '
            '"Demandez une soumission gratuite"'
            if property_context
            else '"AI visibility benchmarks", "How weekly audits work", "Compare competitor citations"'
        )
        suggestions.append(
            "Replace AI-framework H2s with service, use-case, or location headings Google can rank. "
            f"Examples: {examples}. Keep AI-optimised content in llms.txt or concise supporting copy."
        )
    elif h2_service_count >= h2_count // 2:
        h2_keyword_quality = "good"
    else:
        h2_keyword_quality = "generic"
        issues.append(
            f"Only {h2_service_count}/{h2_count} H2s contain service/location keywords. "
            "Add keyword-targeted H2s for each service and city you serve."
        )
        if property_context:
            suggestions.append(
                "Add at least one H2 per core service: syndicat de copropriété, "
                "gestion locative, Airbnb, commercial. Include the city name in at least 2 H2s."
            )
        else:
            suggestions.append(
                "Add at least one H2 per core service, use case, or audience. Include the primary keyword in "
                "2-3 H2s without repeating the exact same phrase."
            )

    # ── Score ─────────────────────────────────────────────────────────────────
    score = _compute_copy_score(
        h1_is_generic=h1_is_generic,
        h1_is_outcome=h1_is_outcome,
        has_value_prop=has_value_prop,
        weak_ctas=weak_ctas,
        strong_ctas=strong_ctas,
        benefit_ratio=benefit_ratio,
    )

    return CopywritingResult(
        checked=True,
        h1_text=h1_text[:120],
        h1_is_outcome_focused=h1_is_outcome,
        h1_is_feature_focused=h1_is_feature,
        h1_is_generic=h1_is_generic,
        has_value_prop_in_hero=has_value_prop,
        value_prop_snippet=value_prop_snippet[:200],
        weak_ctas=list(set(weak_ctas))[:5],
        strong_ctas=list(set(strong_ctas))[:5],
        benefit_phrases=benefit_count,
        feature_phrases=feature_count,
        benefit_ratio=benefit_ratio,
        h2_count=h2_count,
        h2_keyword_quality=h2_keyword_quality,
        h2_service_count=h2_service_count,
        h2_samples=h2_texts[:5],
        issues=issues,
        suggestions=suggestions,
        copy_score=score,
    )


def _extract_page_keyword(soup) -> str:
    """Return the primary keyword tokens from the page title or H1."""
    if soup is None:
        return ""
    title_tag = soup.find("title")
    if title_tag:
        text = title_tag.get_text(strip=True)
        text = re.split(r"\s*[\|—–\-]\s*", text)[0].strip()
        if len(text) > 5:
            return text.lower()
    h1 = soup.find("h1")
    if h1:
        text = h1.get_text(strip=True)
        if len(text) > 5:
            return cast(str, text.lower()[:80])
    return ""


def audit_images(soup, base_url: str = "", page_keyword: str = "", vertical: str = "auto") -> ImageAuditResult:
    """Audit all <img> tags for SEO best practices.

    Checks:
    - Total image count (0 images = major ranking signal gap)
    - Alt text presence and keyword quality
    - Filename keyword relevance
    - WebP format usage
    - width + height attributes (prevents layout shift)
    - loading="lazy" attribute
    - Generic/meaningless alt text ("photo", "image", numbers)
    - Alt text length (< 10 chars non-empty, > 125 chars too long)
    - Page-specific keyword match in alt text
    """
    if soup is None:
        return ImageAuditResult(checked=True)

    if not page_keyword:
        page_keyword = _extract_page_keyword(soup)
    property_context = _is_property_marketing_context(vertical, page_keyword)

    # Build a small set of meaningful tokens from the page keyword for matching
    _stop = {
        "de",
        "du",
        "la",
        "le",
        "les",
        "des",
        "et",
        "en",
        "a",
        "au",
        "aux",
        "par",
        "sur",
        "un",
        "une",
        "the",
        "of",
        "for",
        "in",
        "and",
    }
    page_kw_tokens: list[str] = [t for t in re.split(r"[\s\-–|,]+", page_keyword) if len(t) >= 4 and t not in _stop]

    from urllib.parse import urljoin, urlparse

    imgs = soup.find_all("img")
    total = len(imgs)
    missing_alt = 0
    empty_alt = 0
    keyword_alt = 0
    keyword_filename = 0
    webp_count = 0
    missing_dims = 0
    missing_lazy = 0
    generic_alt = 0
    page_kw_alt = 0  # alt contains a page-specific keyword token
    short_alt = 0  # non-empty alt < 10 chars
    long_alt = 0  # alt > 125 chars

    for img in imgs:
        alt = img.get("alt")
        src = img.get("src", "") or img.get("data-src", "") or ""

        # Alt text
        if alt is None:
            missing_alt += 1
        elif alt.strip() == "":
            empty_alt += 1
        else:
            alt_clean = alt.strip()
            # Generic / meaningless
            if _GENERIC_ALT_RE.match(alt_clean):
                generic_alt += 1
            # Length checks
            if len(alt_clean) < 10:
                short_alt += 1
            elif len(alt_clean) > 125:
                long_alt += 1
            if property_context and _IMAGE_KEYWORD_RE.search(alt_clean):
                keyword_alt += 1
            # Page-specific keyword match
            if page_kw_tokens and any(t in alt_clean.lower() for t in page_kw_tokens):
                page_kw_alt += 1

        # Filename keyword (from src path)
        try:
            path = urlparse(urljoin(base_url, src)).path.lower()
            filename = path.split("/")[-1]
            if property_context and _IMAGE_KEYWORD_RE.search(filename):
                keyword_filename += 1
            if filename.endswith(".webp"):
                webp_count += 1
        except (ValueError, AttributeError):
            pass

        # Dimensions
        if not (img.get("width") and img.get("height")):
            missing_dims += 1

        # Lazy loading
        loading = img.get("loading", "")
        if loading.lower() != "lazy":
            missing_lazy += 1

    issues: list[str] = []
    suggestions: list[str] = []

    if total == 0:
        issues.append(
            "No images found on the page. Google ranks pages with real photos higher — "
            "competitors often use images of the product, team, customers, or service in action."
        )
        if property_context:
            suggestions.append(
                "Add 5+ real photos with keyword-rich filenames: "
                "gestion-syndicat-copropriete-montreal.webp, "
                "gestionnaire-immobilier-montreal.webp, "
                "immeuble-gestion-locative-montreal.webp. "
                "Compress to WebP at under 150 KB each. Alt text = filename keyword."
            )
        else:
            suggestions.append(
                "Add 3-5 real product, team, customer, or workflow images with descriptive filenames. "
                "Compress to WebP at under 150 KB each and write alt text that describes the image and page topic."
            )
    else:
        if missing_alt > 0:
            issues.append(
                f"{missing_alt}/{total} image(s) missing alt text — Google can't read images, only their alt text."
            )
            suggestions.append(
                'Add descriptive alt text to every image. Format: "[what the image shows] — [brand or topic]".'
            )
        if property_context and keyword_filename == 0 and total > 0:
            issues.append(
                "No images have keyword-rich filenames (e.g. img1234.jpg vs "
                "gestion-syndicat-copropriete-montreal.webp). "
                "Google Images ranks by filename — generic names miss this."
            )
            suggestions.append(
                "Rename every image file to include the page keyword before uploading. "
                "Format: [service]-[city].webp. "
                "Example: gestion-locative-montreal-appartement.webp"
            )
        if webp_count == 0 and total > 0:
            issues.append(
                f"No WebP images found — all {total} image(s) use older formats. "
                "WebP is 25-35% smaller than JPG/PNG at the same quality."
            )
            suggestions.append(
                "Convert all images to WebP using Squoosh.app (free, browser-based) "
                "or: cwebp -q 80 input.jpg -o output.webp. "
                "Target: hero < 150 KB, section photos < 80 KB, thumbnails < 20 KB."
            )
        if missing_dims > total // 2:
            issues.append(
                f"{missing_dims}/{total} images missing width/height attributes — "
                "causes Cumulative Layout Shift (CLS), hurting Core Web Vitals score."
            )
            suggestions.append(
                "Add explicit width and height to every <img>: "
                '<img src="..." width="800" height="533" loading="lazy" alt="...">. '
                "The browser reserves space before the image loads, preventing layout shift."
            )
        if generic_alt > 0:
            issues.append(
                f"{generic_alt}/{total} image(s) have generic alt text ('photo', 'image', number) — "
                "these provide no keyword signal to Google."
            )
            suggestions.append(
                "Replace generic alts with descriptive keyword-rich text. "
                'Format: "[what the image shows] — [brand or topic]". '
                'Bad: alt="photo". Good: alt="AI visibility benchmark dashboard — Acme".'
            )
        if page_kw_tokens and page_kw_alt == 0 and total > 0:
            kw_display = page_keyword[:60] if page_keyword else "page keyword"
            issues.append(
                f'No images have alt text matching the page keyword ("{kw_display}") — '
                "alt text should reflect what is actually shown in the photo AND the page topic."
            )
            if page_kw_tokens:
                token_example = page_kw_tokens[0]
                suggestions.append(
                    f'Add "{token_example}" (and related terms) to at least 2-3 image alts. '
                    "Google uses alt text to understand what the page is about — "
                    "images that match the page topic reinforce your keyword relevance."
                )

    # Score: start at 100, deduct per issue
    score = 100
    if total == 0:
        score = 0
    else:
        if missing_alt > 0:
            score -= min(30, missing_alt * 10)
        if property_context and keyword_filename == 0:
            score -= 20
        if webp_count == 0:
            score -= 15
        if missing_dims > total // 2:
            score -= 15
        if property_context and keyword_alt == 0 and total > 0:
            score -= 10
        if generic_alt > 0:
            score -= min(10, generic_alt * 3)
        if page_kw_tokens and page_kw_alt == 0:
            score -= 10
    score = max(0, score)

    return ImageAuditResult(
        checked=True,
        total_images=total,
        images_missing_alt=missing_alt,
        images_empty_alt=empty_alt,
        images_keyword_alt=keyword_alt,
        images_keyword_filename=keyword_filename,
        images_webp=webp_count,
        images_missing_dimensions=missing_dims,
        images_missing_lazy=missing_lazy,
        issues=issues,
        suggestions=suggestions,
        image_score=score,
    )


def audit_content_strategy(soup, base_url: str = "", schema=None, vertical: str = "generic") -> ContentStrategyResult:
    """Analyse content strategy signals from HTML."""
    body = soup.find("body")
    if not body:
        return ContentStrategyResult(checked=True)

    issues: list[str] = []
    suggestions: list[str] = []

    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc.lower()

    # Collect all internal links with their paths
    internal_paths: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        if href.startswith("/"):
            internal_paths.append(href)
        elif href.startswith(("http://", "https://")):
            p = urlparse(href)
            if p.netloc.lower() == base_domain:
                internal_paths.append(p.path)

    # ── Blog presence ─────────────────────────────────────────────────────────
    blog_paths = [p for p in internal_paths if _BLOG_PATH_RE.match(p)]
    has_blog = bool(blog_paths)
    blog_url = urljoin(base_url, blog_paths[0]) if blog_paths else ""
    # Count distinct /blog/* paths as article estimate
    blog_articles = (
        len({p for p in internal_paths if p.startswith(blog_paths[0]) and p != blog_paths[0]}) if blog_paths else 0
    )

    if not has_blog:
        issues.append("No blog / content hub found")
        suggestions.append(
            "Launch a blog to build topical authority and AI citation potential. "
            "Start with 5 high-intent articles: your key service + location + FAQ format. "
            "Each article gets cited independently by AI — a blog multiplies your GEO surface area."
        )

    # ── FAQ ───────────────────────────────────────────────────────────────────
    has_faq_schema = _check_faq_schema(soup, schema)
    # Also detect FAQ heading in visible content
    page_text = body.get_text(separator=" ")
    property_context = _is_property_marketing_context(vertical, text=page_text[:2000])
    has_faq_heading = bool(_FAQ_RE.search(page_text))
    has_faq_section = has_faq_schema or has_faq_heading

    if not has_faq_section:
        issues.append("No FAQ section detected")
        suggestions.append(
            "Add a FAQ section to your homepage/service pages. "
            "Format: Q: [exact question visitors ask] / A: [direct 2-3 sentence answer]. "
            "FAQPage schema makes these directly extractable by Google AI Overviews and Perplexity."
        )

    # ── Comparison / alternatives pages ──────────────────────────────────────
    comparison_paths = [p for p in internal_paths if _COMPARISON_PATH_RE.match(p)]
    has_comparison_pages = bool(comparison_paths)
    comparison_urls = [urljoin(base_url, p) for p in comparison_paths[:5]]

    if not has_comparison_pages:
        issues.append("No comparison or alternatives pages found (/vs/, /compare/, etc.)")
        suggestions.append(
            "Create at least one '[Your brand] vs [Competitor]' page. "
            "These pages are cited in ~33% of AI answers for competitive queries "
            "and generate high-intent organic traffic. "
            "Key: be fair and structured — AI systems flag obviously biased comparisons."
        )

    # ── Pricing transparency ──────────────────────────────────────────────────
    pricing_paths = [p for p in internal_paths if _PRICING_PATH_RE.match(p)]
    has_pricing_page = bool(pricing_paths)
    # We can't check for /pricing.md without a network request; flag as suggestion
    has_pricing_md = False  # Would need HTTP check; left for manual verify

    if not has_pricing_page:
        issues.append("No pricing page linked from homepage")
        suggestions.append(
            "Add a /pricing or /plans page. "
            "Opaque pricing hurts conversion and AI agent readability — AI assistants "
            "comparing products for users will skip you if pricing requires a form fill. "
            "Consider adding /pricing.md (plain text) for AI agents that parse your site."
        )
    else:
        suggestions.append(
            "Add /pricing.md (plain text file) alongside your pricing page. "
            "AI agents evaluating tools on behalf of users can read markdown files directly — "
            "no JavaScript rendering required. See ai-seo skill for format guidance."
        )

    # ── Email / lead capture ──────────────────────────────────────────────────
    # Check for email input fields or newsletter language
    has_email_input = bool(soup.find("input", attrs={"type": "email"}))
    has_lead_magnet_text = bool(_LEAD_MAGNET_RE.search(page_text))
    has_email_capture = has_email_input or has_lead_magnet_text

    if not has_email_capture:
        issues.append("No email capture or lead magnet found")
        suggestions.append(
            "Add an email capture with a specific offer: "
            '"Free [guide/checklist/audit] for [your audience]." '
            "This builds a retargeting list from AI-referred visitors who aren't ready to buy yet. "
            "Even a simple newsletter with a clear benefit works."
        )

    # ── Social proof with numbers ─────────────────────────────────────────────
    has_numbers_proof = bool(_NUMBER_PROOF_RE.search(page_text))
    has_case_studies = bool(_PROOF_RE.search(page_text))

    if not has_numbers_proof:
        issues.append("No quantified social proof found (customer counts, improvement stats)")
        numbers_example = (
            '"[X]+ properties managed • [Y]% client satisfaction • [Z]+ years in Montreal."'
            if property_context
            else '"[X]+ customers • [Y]% faster reporting • [Z]+ weekly audits completed."'
        )
        suggestions.append(
            "Add a numbers bar to your hero or above-fold area: "
            f"{numbers_example} "
            "Specific numbers increase AI citation probability by +37% (Princeton GEO study) "
            "and significantly improve page conversion."
        )

    # ── Internal link count ───────────────────────────────────────────────────
    internal_link_count = len(internal_paths)
    if internal_link_count < 5:
        issues.append(
            f"Only {internal_link_count} internal link(s) found — Google sees a single isolated page. "
            "A healthy site links to 10+ service/location pages from the homepage."
        )
        if property_context:
            example_paths = "/syndicat-copropriete-montreal/, /gestion-locative-montreal/, /tarifs/, /blog/"
        else:
            example_paths = "/features/, /use-cases/, /pricing/, /customers/, /blog/"
        suggestions.append(
            "Build a clear page architecture and link to the key pages from the homepage: "
            f"{example_paths}. Internal links distribute PageRank and help Google discover all your pages."
        )
    elif internal_link_count < 10:
        issues.append(
            f"Only {internal_link_count} internal links — thin site structure. "
            "Aim for 15+ links to service, location, and support pages."
        )

    # ── LocalBusiness schema completeness ─────────────────────────────────────
    has_local_business_schema = False
    local_business_has_address = False
    local_business_has_phone = False
    local_business_has_hours = False
    local_business_has_geo = False

    import json as _json

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            blocks = data if isinstance(data, list) else [data]
            for block in blocks:
                btype = str(block.get("@type", ""))
                if any(t in btype for t in ("LocalBusiness", "RealEstateAgent", "ProfessionalService", "Organization")):
                    has_local_business_schema = True
                    if block.get("address") or block.get("streetAddress"):
                        local_business_has_address = True
                    if block.get("telephone") or block.get("phone"):
                        local_business_has_phone = True
                    if block.get("openingHours") or block.get("openingHoursSpecification"):
                        local_business_has_hours = True
                    if block.get("geo") or block.get("latitude"):
                        local_business_has_geo = True
        except (ValueError, AttributeError, KeyError):
            pass

    if not has_local_business_schema:
        issues.append(
            "No LocalBusiness/ProfessionalService JSON-LD schema found. "
            "This is required for Google Maps, Local Pack, and Google Business Profile sync."
        )
        suggestions.append(
            "Add LocalBusiness schema with full address, phone, hours and geo coordinates. "
            'Example: {"@type":"LocalBusiness","name":"Acme Service Co",'
            '"address":{"@type":"PostalAddress","streetAddress":"...","addressLocality":"City"},'
            '"telephone":"+1-514-xxx-xxxx","openingHours":"Mo-Fr 09:00-17:00",'
            '"geo":{"@type":"GeoCoordinates","latitude":45.50,"longitude":-73.57}}'
        )
    else:
        missing_lb = []
        if not local_business_has_address:
            missing_lb.append("address")
        if not local_business_has_phone:
            missing_lb.append("telephone")
        if not local_business_has_hours:
            missing_lb.append("openingHours")
        if not local_business_has_geo:
            missing_lb.append("geo coordinates")
        if missing_lb:
            issues.append(
                f"LocalBusiness schema incomplete — missing: {', '.join(missing_lb)}. "
                "Incomplete schema reduces Local Pack eligibility."
            )
            suggestions.append(
                f"Add the missing fields to your LocalBusiness JSON-LD: {', '.join(missing_lb)}. "
                "Complete schema = higher chance of appearing in Google Maps and Local Pack."
            )

    # ── Industry memberships / backlink trust signals ─────────────────────────
    page_text_full = soup.get_text(separator=" ")
    found_memberships: list[str] = []
    # Combine generic cross-vertical patterns with vertical-specific ones
    membership_patterns = _MEMBERSHIP_GENERIC + _MEMBERSHIP_BY_VERTICAL.get(vertical, [])
    for name, pattern in membership_patterns:
        if re.search(pattern, page_text_full, re.IGNORECASE):
            found_memberships.append(name)
    has_industry_memberships = bool(found_memberships)

    if not has_industry_memberships:
        # Build a hint list from the vertical-specific memberships for the suggestion
        vert_names = [n for n, _ in _MEMBERSHIP_BY_VERTICAL.get(vertical, [])]
        generic_names = [n for n, _ in _MEMBERSHIP_GENERIC[:3]]
        hint_names = vert_names[:3] if vert_names else generic_names
        hint_str = ", ".join(hint_names) if hint_names else "BBB, Chambre de commerce"
        issues.append(
            f"No industry association memberships or trust badges detected ({hint_str}, …). "
            "These are trust signals and free backlink sources."
        )
        suggestions.append(
            f"Display relevant industry memberships ({hint_str}) — these associations have "
            "member directories with free backlinks and are a key trust signal for visitors "
            "evaluating your business. Add their logos to your footer or About page."
        )

    # ── Score ─────────────────────────────────────────────────────────────────
    score = _compute_strategy_score(
        has_blog=has_blog,
        has_faq_section=has_faq_section,
        has_comparison_pages=has_comparison_pages,
        has_pricing_page=has_pricing_page,
        has_email_capture=has_email_capture,
        has_numbers_proof=has_numbers_proof,
        has_case_studies=has_case_studies,
    )

    return ContentStrategyResult(
        checked=True,
        has_blog=has_blog,
        blog_url=blog_url,
        estimated_article_count=blog_articles,
        has_faq_section=has_faq_section,
        has_faq_schema=has_faq_schema,
        has_comparison_pages=has_comparison_pages,
        comparison_urls=comparison_urls,
        has_pricing_page=has_pricing_page,
        has_pricing_md=has_pricing_md,
        has_email_capture=has_email_capture,
        has_lead_magnet=has_lead_magnet_text,
        has_case_studies=has_case_studies,
        has_numbers_proof=has_numbers_proof,
        internal_link_count=internal_link_count,
        has_local_business_schema=has_local_business_schema,
        local_business_has_address=local_business_has_address,
        local_business_has_phone=local_business_has_phone,
        local_business_has_hours=local_business_has_hours,
        local_business_has_geo=local_business_has_geo,
        has_industry_memberships=has_industry_memberships,
        industry_membership_names=found_memberships,
        issues=issues,
        suggestions=suggestions,
        content_score=score,
    )


def audit_ai_presence(soup, base_url: str = "", schema=None) -> AIPresenceResult:
    """Check AI search presence signals from the ai-seo, schema-markup, and programmatic-seo skills.

    Checks:
    - robots.txt: AI crawlers blocked? (immediate citation killer)
    - Definition block in first 300 words (extractability)
    - Attributed vs. unattributed statistics (authority signal)
    - JS-heavy content (technical discoverability)
    - Location pages (programmatic-seo Locations playbook)
    - Organization sameAs / author schema (entity authority)
    """
    issues: list[str] = []
    suggestions: list[str] = []

    # ── robots.txt AI bot check ────────────────────────────────────────────────
    robots_fetched, blocked_bots = _check_robots_txt(base_url)
    if robots_fetched and blocked_bots:
        issues.append(
            f"AI crawlers blocked in robots.txt: {', '.join(blocked_bots)}. "
            "These bots cannot index or cite your content."
        )
        suggestions.append(
            "Add explicit Allow rules for AI crawlers in robots.txt:\n"
            "  User-agent: GPTBot\n  Allow: /\n\n"
            "  User-agent: PerplexityBot\n  Allow: /\n\n"
            "  User-agent: ClaudeBot\n  Allow: /\n\n"
            "  User-agent: Google-Extended\n  Allow: /\n"
            "This is a 5-minute fix that unlocks citation on all major AI platforms."
        )

    # ── Definition block (ai-seo Pillar 1: Structure / Extractability) ─────────
    body = soup.find("body") if soup else None
    has_definition_block = False
    definition_snippet = ""

    if body:
        # Check first ~300 words
        first_text = " ".join(body.get_text(separator=" ").split()[:300])
        m = _DEFINITION_BLOCK_RE.search(first_text)
        if m:
            has_definition_block = True
            definition_snippet = m.group(0)[:120]

    if not has_definition_block:
        issues.append("No definition block found in first 300 words")
        suggestions.append(
            "Add a self-contained definition sentence in the first 300 words: "
            '"[Your service] is [concise definition in 1-2 sentences]." '
            "AI systems pull this verbatim for 'what is X' queries — it's the most-cited content pattern."
        )

    # ── Attributed vs. unattributed statistics ─────────────────────────────────
    has_attributed_stats = False
    unattributed_count = 0

    if body:
        page_text = body.get_text(separator=" ")
        attributed_matches = _ATTRIBUTED_STAT_RE.findall(page_text)
        has_attributed_stats = bool(attributed_matches)

        raw_stat_matches = _RAW_STAT_RE.findall(page_text)
        # Unattributed = raw stats not near an attribution pattern
        # Simple heuristic: count raw stats beyond the attributed ones
        unattributed_count = max(0, len(raw_stat_matches) - len(attributed_matches))

    if unattributed_count > 0 and not has_attributed_stats:
        issues.append(
            f"{unattributed_count} statistic(s) found without source attribution. "
            "AI systems deprioritise uncited numbers — they can't verify the source."
        )
        suggestions.append(
            'Add source attribution to every statistic: "According to [Source] ([Year]), X%…" '
            "or append ([Source], [Year]) after the number. "
            "Attributed stats are +37% more likely to be cited by AI search engines (Princeton GEO study)."
        )
    elif unattributed_count > 2:
        suggestions.append(
            f"You have {unattributed_count} unattributed stats alongside cited ones. "
            "Add '(Source, Year)' to remaining numbers to maximise citation probability."
        )

    # ── JS-heavy content detection (ai-seo Pillar 3: Discoverable) ─────────────
    js_heavy = False
    if body:
        script_count = len(soup.find_all("script"))
        body_text_len = len(body.get_text(strip=True))
        # Heuristic: many scripts + thin visible text → likely JS-rendered SPA
        js_heavy = script_count > 15 and body_text_len < 800

    if js_heavy:
        issues.append(
            f"Page appears JS-heavy ({len(soup.find_all('script'))} scripts, <800 chars visible text). "
            "AI crawlers cannot execute JavaScript — important content may be invisible to them."
        )
        suggestions.append(
            "Ensure core content (headline, value prop, FAQ, services) is server-rendered HTML, "
            "not injected by JavaScript. Use Next.js/Nuxt SSR or static generation. "
            "Run 'curl -A GPTBot https://yoursite.com | grep -c \"<p\"' to see what AI bots actually get."
        )

    # ── Location pages (programmatic-seo Locations playbook) ──────────────────
    has_location_pages = False
    location_page_count = 0

    if body and base_url:
        from urllib.parse import urlparse as _urlparse

        base_domain = _urlparse(base_url).netloc.lower()
        location_paths: list[str] = []

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("/"):
                path = href.split("?")[0].rstrip("/")
            elif href.startswith(("http://", "https://")):
                p = _urlparse(href)
                if p.netloc.lower() == base_domain:
                    path = p.path.split("?")[0].rstrip("/")
                else:
                    continue
            else:
                continue

            if path and _LOCATION_PATH_RE.match(path):
                location_paths.append(path)

        unique_location_paths = list(dict.fromkeys(location_paths))
        has_location_pages = bool(unique_location_paths)
        location_page_count = len(unique_location_paths)

    if not has_location_pages:
        suggestions.append(
            "Consider creating location-specific pages: /[service]-montreal/, /[service]-laval/, etc. "
            "The programmatic-seo Locations playbook shows these pages capture high-intent local queries "
            "and each one is an independent AI citation target for '[service] in [city]' searches."
        )

    # ── Organization sameAs + author schema (schema-markup skill) ─────────────
    has_org_sameas = False
    has_author_schema = False

    if soup:
        import json as _json

        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = _json.loads(script.string or "")
                # Handle @graph arrays
                items = data if isinstance(data, list) else [data]
                if isinstance(data, dict) and "@graph" in data:
                    items = data["@graph"]

                for item in items:
                    schema_type = str(item.get("@type", ""))
                    if any(t in schema_type for t in ("Organization", "LocalBusiness")) and item.get("sameAs"):
                        has_org_sameas = True
                    if "Person" in schema_type and item.get("sameAs"):
                        has_author_schema = True
            except (ValueError, AttributeError, KeyError):
                pass

    if not has_org_sameas:
        suggestions.append(
            "Add sameAs links to your Organization schema — list your LinkedIn, Google Business Profile, "
            "and any Wikipedia/Wikidata entry. This connects your entity across the web and improves "
            "AI system entity recognition, making you more citable in brand-related queries."
        )

    # ── Score ─────────────────────────────────────────────────────────────────
    score = _compute_presence_score(
        robots_fetched=robots_fetched,
        blocked_bots=blocked_bots,
        has_definition_block=has_definition_block,
        has_attributed_stats=has_attributed_stats,
        unattributed_count=unattributed_count,
        js_heavy=js_heavy,
        has_location_pages=has_location_pages,
        has_org_sameas=has_org_sameas,
        has_author_schema=has_author_schema,
    )

    return AIPresenceResult(
        checked=True,
        robots_txt_fetched=robots_fetched,
        blocked_ai_bots=blocked_bots,
        has_definition_block=has_definition_block,
        definition_snippet=definition_snippet,
        has_attributed_stats=has_attributed_stats,
        unattributed_stat_count=unattributed_count,
        js_heavy=js_heavy,
        has_location_pages=has_location_pages,
        location_page_count=location_page_count,
        has_org_sameas=has_org_sameas,
        has_author_schema=has_author_schema,
        issues=issues,
        suggestions=suggestions,
        presence_score=score,
    )


def _check_robots_txt(base_url: str) -> tuple[bool, list[str]]:
    """Fetch robots.txt and return (fetched, list_of_blocked_ai_bot_names).

    Parses User-agent / Disallow rules and checks whether any known AI crawlers
    are explicitly blocked (Disallow: /) or blocked via a wildcard (*) rule.
    """
    if not base_url:
        return False, []

    try:
        from geo_optimizer.utils.http import fetch_url

        robots_url = urljoin(base_url, "/robots.txt")
        r, _ = fetch_url(robots_url, timeout=5)
        if not r or r.status_code != 200:
            return False, []
    except (ImportError, AttributeError, OSError):
        return False, []

    # Parse robots.txt into {agent_lower: [("disallow"|"allow", path)]}
    rules: dict[str, list[tuple[str, str]]] = {}
    current_agents: list[str] = []
    group_has_rules = False

    for raw_line in r.text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            current_agents = []  # blank line ends a group
            group_has_rules = False
            continue

        lower = line.lower()
        if lower.startswith("user-agent:"):
            agent = line[len("user-agent:") :].strip().lower()
            if group_has_rules:
                current_agents = [agent]
                group_has_rules = False
            else:
                current_agents.append(agent)
            rules.setdefault(agent, [])
        elif lower.startswith("disallow:") and current_agents:
            path = line[len("disallow:") :].strip()
            for ag in current_agents:
                rules.setdefault(ag, []).append(("disallow", path))
            group_has_rules = True
        elif lower.startswith("allow:") and current_agents:
            path = line[len("allow:") :].strip()
            for ag in current_agents:
                rules.setdefault(ag, []).append(("allow", path))
            group_has_rules = True

    # Does the wildcard block everything?
    wildcard_blocks_root = any(rt == "disallow" and path in ("/", "/*") for rt, path in rules.get("*", []))

    blocked: list[str] = []
    for bot_name in _AI_BOTS:
        bot_lower = bot_name.lower()
        bot_rules = rules.get(bot_lower, [])

        explicitly_blocked = any(rt == "disallow" and path in ("/", "/*") for rt, path in bot_rules)
        explicitly_allowed = any(rt == "allow" and path in ("/", "/*", "") for rt, path in bot_rules)

        # Blocked if: explicit block, or wildcard blocks all and no explicit allow
        if explicitly_blocked or (wildcard_blocks_root and not explicitly_allowed and not bot_rules):
            blocked.append(bot_name)

    return True, blocked


def _compute_presence_score(
    robots_fetched: bool,
    blocked_bots: list,
    has_definition_block: bool,
    has_attributed_stats: bool,
    unattributed_count: int,
    js_heavy: bool,
    has_location_pages: bool,
    has_org_sameas: bool,
    has_author_schema: bool,
) -> int:
    score = 0

    # robots.txt (max 25) — blocked bots is an immediate killer
    if robots_fetched:
        score += 0 if blocked_bots else 25
    else:
        score += 15  # can't check → neutral, partial credit

    # Definition block (max 25) — most extractable content pattern
    if has_definition_block:
        score += 25

    # Statistics attribution (max 20)
    if has_attributed_stats and unattributed_count == 0:
        score += 20
    elif has_attributed_stats:
        score += 10
    elif unattributed_count == 0:
        score += 10  # no stats at all → not a negative

    # JS-heavy content (max 15)
    if not js_heavy:
        score += 15

    # Location pages (max 10) — programmatic SEO signal
    if has_location_pages:
        score += 10

    # Entity schema (max 5)
    if has_org_sameas:
        score += 5

    return min(100, score)


def _get_above_fold_text(body) -> str:
    """Extract text from the first ~N top-level elements (above the fold heuristic)."""
    tags = [t for t in body.descendants if hasattr(t, "name") and t.name]
    sample = tags[:_ABOVE_FOLD_TAGS]
    return " ".join(t.get_text(strip=True) for t in sample if hasattr(t, "get_text"))


def _check_faq_schema(soup, schema) -> bool:
    """Check for FAQPage schema in JSON-LD or SchemaResult."""
    if schema is not None:
        types = getattr(schema, "schema_types", [])
        if isinstance(types, list) and any("FAQ" in str(t) for t in types):
            return True

    import json as _json

    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = _json.loads(script.string or "")
            if "FAQPage" in str(data):
                return True
        except (ValueError, AttributeError):
            pass
    return False
