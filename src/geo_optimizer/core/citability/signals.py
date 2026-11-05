"""Citability: text quality signal detection functions.

Covers: fluency, technical terms, authoritative tone, easy-to-understand,
unique words, keyword stuffing, definition patterns, nuance signals,
citability density, negative signals, comparison content, boilerplate ratio,
token efficiency.
"""

from __future__ import annotations

import re
from collections import Counter

from geo_optimizer.core.citability._helpers import (
    _AUTHORITY_RE,
    _CONNECTIVES,
    _HEDGE_RE,
    _STOP_WORDS,
    _TECH_RE,
    _get_clean_text,
)
from geo_optimizer.models.config import (
    FRONT_LOADING_DENSITY_THRESHOLD,
    KEYWORD_STUFFING_THRESHOLD,
    TTR_THRESHOLD,
    TTR_WINDOW_SIZE,
)
from geo_optimizer.models.results import MethodScore

# ─── Local constants for this module ─────────────────────────────────────────

# Pattern for citable facts: numbers, dates, specific claims
_CITABLE_FACT_NUMERIC_RE = re.compile(
    r"\b\d+(?:\.\d+)?%"
    r"|\$\d+(?:[.,]\d+)*"
    r"|€\d+(?:[.,]\d+)*"
    r"|\b\d{4}\b"
    r"|\b\d+(?:\.\d+)?\s*(?:million|billion|thousand|miliardi|milioni)\b"
    r"|\b\d+(?:\.\d+)?\s*(?:x|times|volte)\b",
    re.IGNORECASE,
)

# Proper nouns: 2-4 capitalized words (#449: excluded common English words)
_CITABLE_PROPER_NAME_RE = re.compile(
    r"(?<!\.\s)(?<!^)\b"
    r"(?!(?:The|This|That|These|Those|What|When|Where|Which|Who|How|"
    r"And|But|For|Nor|Yet|Some|Most|Both|Each|Such|"
    r"Not|Can|May|Will|Was|Were|Are|Has|Had|Did|Does)\s)"
    r"[A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,}){1,3}\b"
)

# Pattern for explicit definitions
_DEFINITION_RE = re.compile(
    r"\b(?:is|are|refers?\s+to|means?|defines?|represents?|consists?\s+of"
    r"|è|sono|si\s+riferisce\s+a|significa|definisce|rappresenta|consiste\s+in)\b",
    re.IGNORECASE,
)

_NUANCE_RE = re.compile(
    r"\b(?:however|on the other hand|nevertheless|nonetheless|that said"
    r"|conversely|in contrast|although|despite|while .+ also"
    r"|limitations? include|drawbacks?|disadvantages?"
    r"|it(?:'s| is) (?:worth noting|important to note)"
    r"|not without|trade-?offs?|caveat|downside"
    r"|tuttavia|d'altra parte|nonostante|ciononostante"
    r"|limiti|svantaggi|aspetti negativi)\b",
    re.IGNORECASE,
)

_NUANCE_HEADING_RE = re.compile(
    r"\b(?:limitations?|cons|disadvantages?|drawbacks?|challenges?"
    r"|trade-?offs?|caveats?|risks?"
    r"|limiti|svantaggi|sfide|rischi)\b",
    re.IGNORECASE,
)

# Pattern CTA aggressivi
_CTA_RE = re.compile(
    r"\b(?:buy now|sign up|subscribe|get started|try free|order now|click here"
    r"|compra ora|iscriviti|registrati|prova gratis|acquista|scarica ora"
    r"|limited time|act now|don't miss|offerta limitata|non perdere)\b",
    re.IGNORECASE,
)

_VS_RE = re.compile(r"\bvs\.?\b|\bversus\b|\bconfronto\b|\bcomparison\b", re.IGNORECASE)
_PRO_CON_RE = re.compile(
    r"\b(?:pros?\s*(?:and|&|e)\s*cons?|vantaggi\s*e\s*svantaggi"
    r"|advantages?\s*(?:and|&)\s*disadvantages?|pro\s*e\s*contro)\b",
    re.IGNORECASE,
)


# ─── 4. Fluency Optimization (+29%) ──────────────────────────────────────────


def detect_fluency(soup, clean_text: str | None = None) -> MethodScore:
    """Estimate text fluency through structural heuristics."""
    paragraphs = soup.find_all("p")
    if not paragraphs:
        return MethodScore(name="fluency_optimization", label="Fluency Optimization", max_score=6, impact="+29%")

    # Average paragraph length
    para_lengths = [len(p.get_text().split()) for p in paragraphs if p.get_text().strip()]
    avg_para_len = sum(para_lengths) / max(len(para_lengths), 1)

    # Logical connectives (fix #29: use clean_text)
    body_text = clean_text or _get_clean_text(soup)
    connective_count = len(_CONNECTIVES.findall(body_text))

    # Text-to-list ratio
    list_items = soup.find_all("li")
    text_to_list_ratio = len(paragraphs) / max(len(list_items), 1)

    score = 0
    if avg_para_len >= 30:
        score += 2
    elif avg_para_len >= 15:
        score += 1
    score += min(connective_count // 2, 2)
    if text_to_list_ratio >= 1.5:
        score += 1
    if len(paragraphs) >= 5:
        score += 1

    return MethodScore(
        name="fluency_optimization",
        label="Fluency Optimization",
        detected=score >= 3,
        score=min(score, 6),
        max_score=6,
        impact="+29%",
        details={
            "avg_paragraph_words": round(avg_para_len, 1),
            "connective_count": connective_count,
            "paragraphs": len(paragraphs),
            "list_items": len(list_items),
        },
    )


# ─── 5. Technical Terms (+18%) ───────────────────────────────────────────────


def detect_technical_terms(soup, clean_text: str | None = None) -> MethodScore:
    """Detect density of technical terminology in content."""
    body_text = clean_text or _get_clean_text(soup)
    tech_matches = _TECH_RE.findall(body_text)

    code_blocks = len(soup.find_all(["code", "pre", "kbd", "samp"]))
    abbr_tags = len(soup.find_all("abbr"))
    dfn_tags = len(soup.find_all("dfn"))

    word_count = max(len(body_text.split()), 1)
    density = len(tech_matches) / word_count * 1000

    score = min(int(density) + code_blocks * 2 + abbr_tags + dfn_tags, 5)

    return MethodScore(
        name="technical_terms",
        label="Technical Terms",
        detected=density >= 5 or code_blocks >= 1,
        score=score,
        max_score=5,
        impact="+18%",
        details={
            "tech_matches": len(tech_matches),
            "density_per_1000": round(density, 2),
            "code_blocks": code_blocks,
            "abbr_tags": abbr_tags,
        },
    )


# ─── 6. Authoritative Tone (+16%) ────────────────────────────────────────────


def detect_authoritative_tone(soup, clean_text: str | None = None) -> MethodScore:
    """Detect authoritative tone signals and author credentials."""
    body_text = clean_text or _get_clean_text(soup)

    authority_signals = len(_AUTHORITY_RE.findall(body_text))
    hedge_signals = len(_HEDGE_RE.findall(body_text))

    # Author bio
    author_bio = soup.find_all(
        ["div", "section", "aside"],
        class_=re.compile(r"author|bio|about-author|byline|contributor", re.I),
    )
    author_schema = soup.find_all("span", attrs={"itemprop": "author"})

    # Credentials
    credentials = re.findall(r"\b(?:Dr\.?|Prof\.?|PhD|M\.?D\.?|MBA|MSc|BSc|CEO|CTO)\b", body_text)

    # Author meta tag
    author_meta = soup.find("meta", attrs={"name": re.compile(r"author", re.I)})

    score = 0
    score += min(authority_signals, 4)
    score -= min(hedge_signals // 3, 2)
    score += min(len(author_bio) + len(author_schema), 3)
    score += min(len(credentials), 2)
    score += 1 if author_meta else 0

    return MethodScore(
        name="authoritative_tone",
        label="Authoritative Tone",
        detected=max(score, 0) >= 3,
        score=max(min(score, 5), 0),
        max_score=5,
        impact="+16%",
        details={
            "authority_markers": authority_signals,
            "hedge_markers": hedge_signals,
            "has_author_bio": bool(author_bio or author_schema),
            "credentials": list(set(credentials))[:5],
            "has_author_meta": bool(author_meta),
        },
    )


# ─── 7. Easy-to-Understand (+14%) ────────────────────────────────────────────


def detect_easy_to_understand(soup) -> MethodScore:
    """Estimate readability with structural metrics."""
    main = soup.find("main") or soup.find("article") or soup
    paragraphs = main.find_all("p") if main else []

    all_sentences = []
    for p in paragraphs:
        text = p.get_text(separator=" ")
        for s in re.split(r"[.!?]+", text):
            words = s.split()
            if len(words) >= 3:
                all_sentences.append(words)

    if not all_sentences:
        return MethodScore(name="easy_to_understand", label="Easy-to-Understand", max_score=5, impact="+14%")

    avg_sentence_len = sum(len(s) for s in all_sentences) / len(all_sentences)

    # Heading hierarchy
    h2_count = len(soup.find_all("h2"))
    h3_count = len(soup.find_all("h3"))

    # FAQ sections
    faq_headings = [
        h for h in soup.find_all(["h2", "h3"]) if re.search(r"faq|domand|question|how to|come", h.get_text(), re.I)
    ]

    score = 0
    if avg_sentence_len <= 15:
        score += 3
    elif avg_sentence_len <= 20:
        score += 2
    if h2_count >= 3:
        score += 2
    elif h2_count >= 1:
        score += 1
    if h3_count >= 1:
        score += 1
    score += min(len(faq_headings), 2)

    return MethodScore(
        name="easy_to_understand",
        label="Easy-to-Understand",
        detected=score >= 3,
        score=min(score, 5),
        max_score=5,
        impact="+14%",
        details={
            "avg_sentence_length": round(avg_sentence_len, 1),
            "h2_count": h2_count,
            "h3_count": h3_count,
            "faq_sections": len(faq_headings),
        },
    )


# ─── 8. Unique Words (+7%) ───────────────────────────────────────────────────


def detect_unique_words(soup, clean_text: str | None = None) -> MethodScore:
    """Calculate Type-Token Ratio to estimate vocabulary richness."""
    body_text = (clean_text or _get_clean_text(soup)).lower()
    words = [w for w in re.findall(r"\b[a-zA-Zà-ú]{4,}\b", body_text) if w not in _STOP_WORDS]

    if len(words) < 50:
        return MethodScore(name="unique_words", label="Unique Words", max_score=3, impact="+7%")

    # TTR with sliding window of 200 words
    window = TTR_WINDOW_SIZE
    ttr_scores = []
    for i in range(0, max(len(words) - window, 1), 50):
        w = words[i : i + window]
        if w:
            ttr_scores.append(len(set(w)) / len(w))

    avg_ttr = sum(ttr_scores) / max(len(ttr_scores), 1)

    score = min(int(avg_ttr * 8), 3)

    return MethodScore(
        name="unique_words",
        label="Unique Words",
        detected=avg_ttr >= TTR_THRESHOLD,
        score=score,
        max_score=3,
        impact="+7%",
        details={
            "ttr": round(avg_ttr, 3),
            "total_words": len(words),
            "unique_count": len(set(words)),
        },
    )


# ─── 9. Keyword Stuffing (-9%) ───────────────────────────────────────────────


def detect_keyword_stuffing(soup, clean_text: str | None = None) -> MethodScore:
    """Detect keyword stuffing that penalizes AI visibility."""
    body_text = (clean_text or _get_clean_text(soup)).lower()
    words = re.findall(r"\b[a-zA-Zà-ú]{3,}\b", body_text)

    if len(words) < 50:
        # Text too short for meaningful analysis
        return MethodScore(
            name="keyword_stuffing", label="No Keyword Stuffing", score=6, max_score=6, impact="-9%", detected=False
        )

    word_freq = Counter(words)
    total = len(words)
    threshold = KEYWORD_STUFFING_THRESHOLD

    # Words with abnormal frequency (above threshold)
    suspicious = {w: c for w, c in word_freq.most_common(20) if c / total > threshold and w not in _STOP_WORDS}

    stuffing_count = len(suspicious)

    # Over-optimization warning (C-SEO Bench 2025):
    # 1. Repetitive phrases (same phrase appearing 3+ times)
    sentences = re.split(r"[.!?]+", body_text)
    sentence_counts = Counter(s.strip() for s in sentences if len(s.strip()) > 20)
    repeated_phrases = {s: c for s, c in sentence_counts.items() if c >= 3}

    # 2. Keyword front-loading in the first 200 words
    first_200 = words[:200]
    front_loading_warning = False
    if len(first_200) >= 50:
        front_freq = Counter(first_200)
        front_total = len(first_200)
        front_suspicious = {
            w: c
            for w, c in front_freq.most_common(10)
            if c / front_total > FRONT_LOADING_DENSITY_THRESHOLD and w not in _STOP_WORDS
        }
        if len(front_suspicious) >= 2:
            front_loading_warning = True

    # Additional penalty for over-optimization
    over_opt_penalty = 0
    if repeated_phrases:
        over_opt_penalty += min(len(repeated_phrases), 2)
    if front_loading_warning:
        over_opt_penalty += 1

    # Full score if no stuffing detected
    if stuffing_count == 0:
        score = 6
    elif stuffing_count <= 1:
        score = 4
    elif stuffing_count <= 3:
        score = 2
    else:
        score = 0

    # Apply over-optimization penalty
    score = max(score - over_opt_penalty, 0)

    return MethodScore(
        name="keyword_stuffing",
        label="No Keyword Stuffing",
        detected=stuffing_count >= 2 or bool(repeated_phrases),
        score=min(score, 6),
        max_score=6,
        impact="-9%",
        details={
            "suspicious_keywords": {k: round(v / total * 100, 1) for k, v in suspicious.items()},
            "stuffing_severity": "high" if stuffing_count >= 4 else "medium" if stuffing_count >= 2 else "none",
            "repeated_phrases": len(repeated_phrases),
            "front_loading_detected": front_loading_warning,
        },
    )


# ─── 16. Citability Density (+15%) ───────────────────────────────────────────


def detect_citability_density(soup, clean_text: str | None = None) -> MethodScore:
    """Detect density of citable facts per paragraph."""
    paragraphs = soup.find_all("p")
    if not paragraphs:
        return MethodScore(name="citability_density", label="Citability Density", max_score=7, impact="+15%")

    total_paras = 0
    dense_paras = 0
    total_facts = 0

    for p in paragraphs:
        text = p.get_text(strip=True)
        if len(text.split()) < 10:
            continue
        total_paras += 1
        numeric_facts = _CITABLE_FACT_NUMERIC_RE.findall(text)
        proper_names = _CITABLE_PROPER_NAME_RE.findall(text)
        fact_count = len(numeric_facts) + len(proper_names)
        total_facts += fact_count
        if fact_count >= 2:
            dense_paras += 1

    if total_paras == 0:
        return MethodScore(name="citability_density", label="Citability Density", max_score=7, impact="+15%")

    density_ratio = dense_paras / total_paras

    # Score based on percentage of dense paragraphs
    if density_ratio >= 0.5:
        score = 7
    elif density_ratio >= 0.3:
        score = 5
    elif density_ratio >= 0.15:
        score = 3
    elif dense_paras >= 1:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="citability_density",
        label="Citability Density",
        detected=dense_paras >= 2,
        score=min(score, 7),
        max_score=7,
        impact="+15%",
        details={
            "total_paragraphs": total_paras,
            "dense_paragraphs": dense_paras,
            "density_ratio": round(density_ratio, 2),
            "total_citable_facts": total_facts,
        },
    )


# ─── 17. Definition Pattern Detection (+10%) ─────────────────────────────────


def detect_definition_patterns(soup) -> MethodScore:
    """Detect definition patterns after H1/H2 headings (matches 'what is X?' queries)."""
    headings = soup.find_all(["h1", "h2"])
    if not headings:
        return MethodScore(name="definition_patterns", label="Definition Patterns", max_score=5, impact="+10%")

    definitions_found = 0

    for heading in headings:
        # Find the first paragraph after the heading
        # Fix #421: always try fallback when sibling is not <p> (e.g. wrapper div)
        next_elem = heading.find_next_sibling()
        if not next_elem or next_elem.name != "p":
            next_elem = heading.find_next("p")
        if not next_elem or next_elem.name != "p":
            continue

        # Check the first 150 characters of the paragraph
        first_text = next_elem.get_text(strip=True)[:150]
        if _DEFINITION_RE.search(first_text):
            definitions_found += 1

    total_headings = len(headings)
    ratio = definitions_found / total_headings if total_headings > 0 else 0

    # Score based on how many headings have a definition
    if ratio >= 0.6:
        score = 5
    elif ratio >= 0.4:
        score = 4
    elif ratio >= 0.2:
        score = 3
    elif definitions_found >= 1:
        score = 2
    else:
        score = 0

    return MethodScore(
        name="definition_patterns",
        label="Definition Patterns",
        detected=definitions_found >= 1,
        score=min(score, 5),
        max_score=5,
        impact="+10%",
        details={
            "definitions_found": definitions_found,
            "total_headings": total_headings,
            "ratio": round(ratio, 2),
        },
    )


# ─── 20. Negative Signals Detection (-15%) — Quality Signal Batch 2 ──────────


def detect_negative_signals(soup, clean_text: str | None = None) -> MethodScore:
    """Detect negative quality signals: excessive self-promotion, thin content, repetitions."""
    body_text = clean_text or _get_clean_text(soup)
    words = body_text.split()
    word_count = len(words)
    penalties = 0

    # 1. Excessive self-promotion: CTA every 200 words (fix #331: unified with audit.py)
    cta_matches = _CTA_RE.findall(body_text)
    cta_count = len(cta_matches)
    if word_count > 0 and cta_count > 0 and cta_count / word_count > 0.005:
        penalties += 2  # CTAs too frequent (1 CTA per 200 words)

    # 2. Thin content: < 300 words with complex H2 headings
    h2_tags = soup.find_all("h2")
    if h2_tags and word_count < 300:
        penalties += 2  # Content too thin for a structured topic

    # 3. Content with no author
    author_meta = soup.find("meta", attrs={"name": re.compile(r"author", re.I)})
    author_bio = soup.find_all(
        ["div", "section", "aside"],
        class_=re.compile(r"author|bio|byline", re.I),
    )
    author_schema = soup.find_all("span", attrs={"itemprop": "author"})
    if not author_meta and not author_bio and not author_schema:
        penalties += 1

    # 4. Repetitive sentences (same sentence 3+ times)
    sentences = [s.strip().lower() for s in re.split(r"[.!?]+", body_text) if len(s.strip()) > 20]
    sentence_counts = Counter(sentences)
    repeated = sum(1 for c in sentence_counts.values() if c >= 3)
    if repeated > 0:
        penalties += min(repeated, 2)

    # Inverted score: 5 if no signals, 0 if many
    score = max(5 - penalties, 0)

    return MethodScore(
        name="no_negative_signals",
        label="No Negative Signals",
        detected=penalties >= 2,
        score=score,
        max_score=5,
        impact="-15%",
        details={
            "cta_count": cta_count,
            "is_thin_content": bool(h2_tags and word_count < 300),
            "has_author": bool(author_meta or author_bio or author_schema),
            "repeated_phrases": repeated,
            "total_penalties": penalties,
        },
    )


# ─── 21. Comparison Content (+10%) — Quality Signal Batch 2 ──────────────────


def detect_comparison_content(soup, clean_text: str | None = None) -> MethodScore:
    """Detect comparison content: tables, pro/con sections, X vs Y headings."""
    score = 0

    # 1. "X vs Y" pattern in headings
    vs_headings = 0
    for h in soup.find_all(["h1", "h2", "h3", "h4"]):
        h_text = h.get_text(strip=True)
        if _VS_RE.search(h_text):
            vs_headings += 1

    # 2. Sezioni pro/contro
    pro_con_sections = 0
    for h in soup.find_all(["h2", "h3", "h4"]):
        h_text = h.get_text(strip=True)
        if _PRO_CON_RE.search(h_text):
            pro_con_sections += 1
    # Search in text as well (fix #30: use clean_text)
    body_text = clean_text or _get_clean_text(soup)
    pro_con_in_text = len(_PRO_CON_RE.findall(body_text))

    # 3. Comparison tables (>3 rows and >2 columns = bonus)
    comparison_tables = 0
    large_tables = 0
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) >= 2:
            comparison_tables += 1
            # Check if it's "large" (>3 rows and >2 columns)
            cols = rows[0].find_all(["th", "td"]) if rows else []
            if len(rows) > 3 and len(cols) > 2:
                large_tables += 1

    # Calculate score
    score += min(vs_headings, 2)
    score += min(pro_con_sections + (1 if pro_con_in_text > 0 else 0), 2)
    score += min(comparison_tables + large_tables, 2)

    detected = vs_headings >= 1 or pro_con_sections >= 1 or comparison_tables >= 1

    return MethodScore(
        name="comparison_content",
        label="Comparison Content",
        detected=detected,
        score=min(score, 4),
        max_score=4,
        impact="+10%",
        details={
            "vs_headings": vs_headings,
            "pro_con_sections": pro_con_sections,
            "comparison_tables": comparison_tables,
            "large_tables": large_tables,
        },
    )


# ─── 24. Content-to-Boilerplate Ratio (+8%) — Quality Signal Batch 2 ─────────


def detect_boilerplate_ratio(soup, soup_clean=None) -> MethodScore:
    """Detect content-to-boilerplate ratio: main/article text vs total page text."""
    import copy

    # Fix #4: use pre-computed soup_clean if available
    if soup_clean is not None:
        total_soup = soup_clean
    else:
        total_soup = copy.deepcopy(soup)
        for tag in total_soup(["script", "style"]):
            tag.decompose()
    total_text = total_soup.get_text(separator=" ", strip=True)
    total_len = len(total_text)

    if total_len < 50:
        return MethodScore(
            name="boilerplate_ratio",
            label="Content-to-Boilerplate Ratio",
            detected=False,
            score=2,
            max_score=4,
            impact="+8%",
            details={"ratio": 0, "method": "insufficient_text"},
        )

    # Look for the main content in <main> or <article>
    content_tag = soup.find("main") or soup.find("article")
    method = "main_tag"

    if content_tag:
        # Fix #419: remove script/style from content_tag before extracting text
        clean_content = copy.deepcopy(content_tag)
        for tag in clean_content(["script", "style"]):
            tag.decompose()
        content_text = clean_content.get_text(separator=" ", strip=True)
    else:
        # Heuristic: remove nav, header, footer, sidebar
        method = "heuristic"
        clean_soup = copy.deepcopy(soup)
        for tag in clean_soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        # Remove sidebar by class/id
        for tag in clean_soup.find_all(
            ["div", "aside", "section"],
            class_=re.compile(r"sidebar|widget|menu|navigation|nav-", re.I),
        ):
            tag.decompose()
        for tag in clean_soup.find_all(
            ["div", "aside", "section"],
            id=re.compile(r"sidebar|widget|menu|navigation", re.I),
        ):
            tag.decompose()
        content_text = clean_soup.get_text(separator=" ", strip=True)

    content_len = len(content_text)
    ratio = content_len / total_len if total_len > 0 else 0

    # Score based on the ratio
    if ratio >= 0.6:
        score = 4
    elif ratio >= 0.45:
        score = 3
    elif ratio >= 0.30:
        score = 2
    elif ratio >= 0.15:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="boilerplate_ratio",
        label="Content-to-Boilerplate Ratio",
        detected=ratio >= 0.45,
        score=min(score, 4),
        max_score=4,
        impact="+8%",
        details={
            "content_length": content_len,
            "total_length": total_len,
            "ratio": round(ratio, 2),
            "method": method,
        },
    )


# ─── 25. Nuance/Honesty Signals (+5%) — Quality Signal Batch 2 ──────────────


def detect_nuance_signals(soup, clean_text: str | None = None) -> MethodScore:
    """Detect nuance and intellectual honesty signals in content."""
    body_text = clean_text or _get_clean_text(soup)

    # Honesty patterns in text
    nuance_matches = _NUANCE_RE.findall(body_text)

    # Headings with sections dedicated to limitations/drawbacks
    nuance_headings = 0
    for h in soup.find_all(["h2", "h3", "h4"]):
        h_text = h.get_text(strip=True)
        if _NUANCE_HEADING_RE.search(h_text):
            nuance_headings += 1

    total_signals = len(nuance_matches) + nuance_headings * 2

    # Score based on the number of signals
    if total_signals >= 5:
        score = 3
    elif total_signals >= 3:
        score = 2
    elif total_signals >= 1:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="nuance_signals",
        label="Nuance/Honesty Signals",
        detected=total_signals >= 2,
        score=min(score, 3),
        max_score=3,
        impact="+5%",
        details={
            "nuance_patterns": len(nuance_matches),
            "nuance_headings": nuance_headings,
            "total_signals": total_signals,
        },
    )


# ─── Token Efficiency (#365) ─────────────────────────────────────────────────


def detect_token_efficiency(soup, clean_text: str | None = None) -> MethodScore:
    """Analyze content-to-noise ratio for LLM context window efficiency (#365).

    Measures how much of the page is useful content vs boilerplate/noise
    from an LLM token perspective. High token efficiency = more useful
    information per token consumed from the context window.
    """
    import copy

    # Total page text (without scripts/styles)
    total_soup = copy.deepcopy(soup)
    for tag in total_soup(["script", "style"]):
        tag.decompose()
    total_text = total_soup.get_text(separator=" ", strip=True)
    total_words = len(total_text.split())

    if total_words < 20:
        return MethodScore(
            name="token_efficiency",
            label="Token Efficiency",
            detected=False,
            score=1,
            max_score=3,
            impact="+8%",
            details={"total_words": total_words, "ratio": 0, "method": "insufficient_text"},
        )

    # Content words: text inside <main>, <article>, or content <p> tags
    content_tag = soup.find("main") or soup.find("article")
    if content_tag:
        clean_content = copy.deepcopy(content_tag)
        for tag in clean_content(["script", "style", "nav"]):
            tag.decompose()
        content_text = clean_content.get_text(separator=" ", strip=True)
    else:
        # Fallback: sum all <p> text
        content_text = " ".join(p.get_text(strip=True) for p in soup.find_all("p"))

    content_words = len(content_text.split())

    # Noise: navigation, footer, sidebar, repeated elements
    noise_words = total_words - content_words
    ratio = content_words / total_words if total_words > 0 else 0

    # Score: higher ratio = better token efficiency
    if ratio >= 0.75:
        score = 3
    elif ratio >= 0.60:
        score = 2
    elif ratio >= 0.45:
        score = 1
    else:
        score = 0

    return MethodScore(
        name="token_efficiency",
        label="Token Efficiency",
        detected=ratio >= 0.60,
        score=min(score, 3),
        max_score=3,
        impact="+8%",
        details={
            "total_words": total_words,
            "content_words": content_words,
            "noise_words": noise_words,
            "ratio": round(ratio, 2),
        },
    )
