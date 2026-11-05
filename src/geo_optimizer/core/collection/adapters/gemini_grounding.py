"""Gemini API lane with Google Search grounding metadata."""

from __future__ import annotations

import os

import requests

from geo_optimizer.core.collection.normalize import _citations_from_urls, _domain_from_url
from geo_optimizer.core.collection.protocol import CollectionRequest
from geo_optimizer.core.collection.store import PARSER_VERSION, _now_iso
from geo_optimizer.models.results.collection import CollectedAnswer

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


class GeminiGroundingAdapter:
    """Collect grounded answers via Gemini generateContent + googleSearch tool."""

    provider_id = "gemini_grounding"
    collection_mode = "api"
    surface = "gemini_grounding"

    def __init__(self, *, model: str = "gemini-2.5-flash", api_key: str | None = None, timeout: int = 120):
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.timeout = timeout

    def collect(self, request: CollectionRequest) -> CollectedAnswer:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini grounding collection")

        url = _GEMINI_URL.format(model=self.model)
        body = {
            "contents": [{"parts": [{"text": request.prompt.query_text}]}],
            "tools": [{"googleSearch": {}}],
        }
        response = requests.post(url, headers={"x-goog-api-key": self.api_key}, json=body, timeout=self.timeout)
        response.raise_for_status()
        raw = response.json()

        candidate = (raw.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        answer_text = "".join(str(part.get("text", "")) for part in parts)

        metadata = candidate.get("groundingMetadata") or {}
        chunks = metadata.get("groundingChunks") or []
        urls: list[str] = []
        titles: dict[str, str] = {}
        for chunk in chunks:
            web = chunk.get("web") or {}
            uri = str(web.get("uri", ""))
            if uri:
                urls.append(uri)
                titles[uri] = str(web.get("title", ""))

        citations = _citations_from_urls(urls, titles=titles)
        domains = sorted({_domain_from_url(u) for u in urls if _domain_from_url(u)})

        return CollectedAnswer(
            prompt_id=request.prompt.prompt_id,
            query_text=request.prompt.query_text,
            query_class=request.prompt.query_class,
            provider="gemini",
            surface=self.surface,
            model=self.model,
            language=request.language,
            answer_text=answer_text,
            citations=citations,
            mentioned_domains=domains,
            collection_mode=self.collection_mode,
            parser_version=PARSER_VERSION,
            parse_confidence=0.92 if citations else 0.7,
            collected_at=_now_iso(),
            keyword_topic=request.prompt.keyword_topic,
            persona=request.prompt.persona,
        )

    def collect_with_raw(self, request: CollectionRequest) -> tuple[CollectedAnswer, dict]:
        """Collect and return raw API payload for artifact storage."""
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini grounding collection")

        url = _GEMINI_URL.format(model=self.model)
        body = {
            "contents": [{"parts": [{"text": request.prompt.query_text}]}],
            "tools": [{"googleSearch": {}}],
        }
        response = requests.post(url, headers={"x-goog-api-key": self.api_key}, json=body, timeout=self.timeout)
        response.raise_for_status()
        raw = response.json()
        answer = self._from_raw(raw, request)
        return answer, raw

    def _from_raw(self, raw: dict, request: CollectionRequest) -> CollectedAnswer:
        candidate = (raw.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        answer_text = "".join(str(part.get("text", "")) for part in parts)
        metadata = candidate.get("groundingMetadata") or {}
        chunks = metadata.get("groundingChunks") or []
        urls = [str((c.get("web") or {}).get("uri", "")) for c in chunks]
        urls = [u for u in urls if u]
        citations = _citations_from_urls(urls)
        return CollectedAnswer(
            prompt_id=request.prompt.prompt_id,
            query_text=request.prompt.query_text,
            query_class=request.prompt.query_class,
            provider="gemini",
            surface=self.surface,
            model=self.model,
            language=request.language,
            answer_text=answer_text,
            citations=citations,
            mentioned_domains=sorted({_domain_from_url(u) for u in urls if _domain_from_url(u)}),
            collection_mode=self.collection_mode,
            parser_version=PARSER_VERSION,
            parse_confidence=0.92 if citations else 0.7,
            collected_at=_now_iso(),
            keyword_topic=request.prompt.keyword_topic,
            persona=request.prompt.persona,
        )
