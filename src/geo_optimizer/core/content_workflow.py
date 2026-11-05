"""Workflow contenutistico operativo: keyword density, E-E-A-T, entity signals."""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import cast

from bs4 import BeautifulSoup

from geo_optimizer.core.citability import (
    detect_anchor_text_quality,
    detect_eeat,
    detect_entity_resolution,
    detect_keyword_stuffing,
    detect_kg_density,
)
from geo_optimizer.models.results import ContentWorkflowResult, KeywordDensityItem
from geo_optimizer.utils.http import fetch_url

_WORD_RE = re.compile(r"\b[a-zA-ZÀ-ÖØ-öø-ÿ]{3,}\b")
_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "your",
    "vous",
    "pour",
    "avec",
    "dans",
    "les",
    "des",
    "une",
    "sur",
    "gestion",
    "montreal",
}


def analyze_content_workflow_url(
    url: str,
    target_keywords: list[str] | None = None,
    top_terms: int = 15,
) -> ContentWorkflowResult:
    """Esegue l'audit contenutistico partendo da una URL pubblica."""
    response, err = fetch_url(url)
    if err or response is None:
        return ContentWorkflowResult(source=url, error=err or "unable to fetch URL")

    try:
        html = response.content.decode(response.encoding or "utf-8", errors="replace")
    except (UnicodeDecodeError, LookupError):
        html = response.text

    return analyze_content_workflow_html(
        html=html,
        source=url,
        base_url=url,
        target_keywords=target_keywords,
        top_terms=top_terms,
    )


def analyze_content_workflow_file(
    file_path: str,
    target_keywords: list[str] | None = None,
    top_terms: int = 15,
    base_url: str = "https://example.com",
) -> ContentWorkflowResult:
    """Esegue l'audit contenutistico su un file HTML locale."""
    path = Path(file_path)
    try:
        html = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        html = path.read_text(encoding="latin-1")
    except OSError as exc:
        return ContentWorkflowResult(source=str(path), error=f"unable to read file: {exc}")

    return analyze_content_workflow_html(
        html=html,
        source=str(path),
        base_url=base_url,
        target_keywords=target_keywords,
        top_terms=top_terms,
    )


def analyze_content_workflow_html(
    html: str,
    source: str,
    base_url: str,
    target_keywords: list[str] | None = None,
    top_terms: int = 15,
) -> ContentWorkflowResult:
    """Analizza un documento HTML gia' disponibile."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    words = [w.lower() for w in _WORD_RE.findall(text)]
    word_count = len(words)

    result = ContentWorkflowResult(source=source, analyzed_words=word_count)
    if word_count == 0:
        result.error = "page appears empty or non-textual"
        return result

    result.top_terms = _extract_top_terms(words, top_terms)
    result.target_keywords = _extract_target_keywords(text, words, target_keywords or [])

    result.keyword_stuffing = detect_keyword_stuffing(soup, clean_text=text)
    result.eeat_signals = detect_eeat(soup)
    result.anchor_text_quality = detect_anchor_text_quality(soup, base_url=base_url)
    result.entity_resolution = detect_entity_resolution(soup)
    result.kg_density = detect_kg_density(soup, clean_text=text)
    result.recommendations = _build_recommendations(result)
    return result


def _extract_top_terms(words: list[str], top_terms: int) -> list[KeywordDensityItem]:
    counter = Counter(w for w in words if w not in _STOPWORDS)
    total = len(words)
    rows: list[KeywordDensityItem] = []
    for term, count in counter.most_common(max(top_terms, 1)):
        rows.append(
            KeywordDensityItem(
                keyword=term,
                count=count,
                density_pct=round((count / total) * 100, 2),
            )
        )
    return rows


def _extract_target_keywords(text: str, words: list[str], targets: list[str]) -> list[KeywordDensityItem]:
    normalized = []
    total_words = max(len(words), 1)
    lowered_text = text.lower()
    for raw in targets:
        kw = raw.strip().lower()
        if not kw:
            continue
        pattern = r"\b" + re.escape(kw) + r"\b"
        count = len(re.findall(pattern, lowered_text))
        normalized.append(
            KeywordDensityItem(
                keyword=kw,
                count=count,
                density_pct=round((count / total_words) * 100, 2),
            )
        )
    return normalized


def _build_recommendations(result: ContentWorkflowResult) -> list[str]:
    recs: list[str] = []
    stuffing_details = result.keyword_stuffing.details or {}
    suspicious = cast(dict[str, float], stuffing_details.get("suspicious_keywords") or {})
    if suspicious:
        top = ", ".join(f"{k} ({v}%)" for k, v in list(suspicious.items())[:3])
        recs.append(f"Reduce repeated terms and diversify lexical variants: {top}.")

    for item in result.target_keywords:
        if item.density_pct > 3.5:
            recs.append(f"Lower keyword density for '{item.keyword}' (currently {item.density_pct}%).")
        elif 0 < item.density_pct < 0.8:
            recs.append(f"Increase semantic coverage for '{item.keyword}' (currently {item.density_pct}%).")
        elif item.count == 0:
            recs.append(f"Target keyword missing: '{item.keyword}'. Add it in title/H2/opening paragraph.")

    if result.eeat_signals.score < 3:
        recs.append("Strengthen E-E-A-T: add visible About, Contact, Terms, and Privacy links.")
    if result.anchor_text_quality.score < 2:
        recs.append("Improve internal anchor text specificity; avoid generic labels like 'read more'.")
    if result.entity_resolution.score < 2:
        recs.append("Improve entity clarity with explicit first-use definitions and typed schema name/description.")
    if result.kg_density.score < 2:
        recs.append("Add relationship statements ('X is Y', 'founded by', 'located in') for KG extraction.")

    if not recs:
        recs.append("Content signals are solid. Keep monitoring drift monthly.")
    return recs
