"""Bridge geo-aeo-tracker JSON exports into canonical CollectedAnswer records."""

from __future__ import annotations

from geo_optimizer.core.collection.normalize import _citations_from_urls, _domain_from_url
from geo_optimizer.core.collection.store import PARSER_VERSION, _now_iso
from geo_optimizer.models.results.collection import CollectedAnswer, CollectedCitation


def from_brightdata_scrape(raw: dict, *, prompt_id: str = "", query_class: str = "") -> CollectedAnswer:
    """Normalize geo-aeo-tracker /api/scrape response (NormalizedScrapeResult)."""
    provider = str(raw.get("provider", "unknown"))
    prompt = str(raw.get("prompt", ""))
    answer = str(raw.get("answer", ""))
    sources = [str(url) for url in raw.get("sources", []) if url]
    citations = _citations_from_urls(sources)
    domains = [_domain_from_url(url) for url in sources if _domain_from_url(url)]

    return CollectedAnswer(
        prompt_id=prompt_id,
        query_text=prompt,
        query_class=query_class,
        provider=provider,
        surface=_surface_for_provider(provider),
        model=provider,
        answer_text=answer,
        citations=citations,
        mentioned_domains=sorted(set(domains)),
        collection_mode="browser",
        parser_version=PARSER_VERSION,
        parse_confidence=0.85 if citations else 0.6,
        collected_at=str(raw.get("createdAt", _now_iso())),
    )


def from_platform_result(raw: dict, *, prompt_id: str = "", query_class: str = "") -> CollectedAnswer:
    """Normalize SRO PlatformResult from bulk analysis."""
    platform = str(raw.get("platform", raw.get("provider", "unknown")))
    citations: list[CollectedCitation] = []
    for index, item in enumerate(raw.get("citations", []), start=1):
        url = str(item.get("url", ""))
        if not url:
            continue
        citations.append(
            CollectedCitation(
                url=url,
                domain=str(item.get("domain", _domain_from_url(url))),
                title=str(item.get("title", "")),
                position=index,
                snippet=str(item.get("citedSentence", item.get("description", ""))),
            )
        )

    return CollectedAnswer(
        prompt_id=prompt_id,
        query_text=str(raw.get("query", raw.get("keyword", ""))),
        query_class=query_class,
        provider=platform,
        surface=_surface_for_provider(platform),
        model=platform,
        answer_text=str(raw.get("answer", "")),
        citations=citations,
        mentioned_domains=sorted({c.domain for c in citations if c.domain}),
        collection_mode="browser",
        parser_version=PARSER_VERSION,
        parse_confidence=0.9 if citations else 0.55,
        collected_at=_now_iso(),
    )


def from_grounding_result(raw: dict, *, prompt_id: str = "", query_class: str = "") -> CollectedAnswer:
    """Normalize Gemini GroundingResult from geo-aeo-tracker."""
    chunks = raw.get("chunks", [])
    urls = [str(c.get("uri", "")) for c in chunks if c.get("uri")]
    titles = {str(c.get("uri", "")): str(c.get("title", "")) for c in chunks if c.get("uri")}
    citations = _citations_from_urls(urls, titles=titles)

    return CollectedAnswer(
        prompt_id=prompt_id,
        query_text=str(raw.get("query", "")),
        query_class=query_class,
        provider="gemini",
        surface="gemini_grounding",
        model="gemini-2.5-flash",
        answer_text=str(raw.get("answer", "")),
        citations=citations,
        mentioned_domains=sorted({_domain_from_url(u) for u in urls if _domain_from_url(u)}),
        collection_mode="api",
        parser_version=PARSER_VERSION,
        parse_confidence=0.92,
        collected_at=_now_iso(),
    )


def from_bulk_analysis_item(raw: dict) -> list[CollectedAnswer]:
    """Expand one BulkAnalysisResult item into multiple canonical answers."""
    keyword = str(raw.get("input", {}).get("keyword", ""))
    query_class = ""
    answers: list[CollectedAnswer] = []

    grounding = raw.get("grounding")
    if grounding:
        answers.append(
            from_grounding_result(
                grounding,
                prompt_id=f"{keyword}:gemini_grounding",
                query_class=query_class,
            )
        )

    for platform in raw.get("platforms", []):
        if platform.get("status") != "done":
            continue
        platform["query"] = platform.get("query", keyword)
        answers.append(
            from_platform_result(
                platform,
                prompt_id=f"{keyword}:{platform.get('platform', 'platform')}",
                query_class=query_class,
            )
        )
    return answers


def _surface_for_provider(provider: str) -> str:
    mapping = {
        "google_ai": "google_ai_mode",
        "ai_mode": "google_ai_mode",
        "chatgpt": "chatgpt",
        "perplexity": "perplexity",
        "gemini": "gemini",
        "copilot": "copilot",
        "grok": "grok",
    }
    return mapping.get(provider, provider)
