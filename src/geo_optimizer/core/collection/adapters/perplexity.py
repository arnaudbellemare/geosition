"""Perplexity API lane — structured Sonar chat with citations."""

from __future__ import annotations

import os
from typing import cast

import requests

from geo_optimizer.core.collection.normalize import _citations_from_urls, _domain_from_url
from geo_optimizer.core.collection.protocol import CollectionRequest
from geo_optimizer.core.collection.store import PARSER_VERSION, _now_iso
from geo_optimizer.models.results.collection import CollectedAnswer

_PERPLEXITY_URL = "https://api.perplexity.ai/chat/completions"
_DEFAULT_MODEL = "sonar"


class PerplexityApiAdapter:
    """Collect answers via Perplexity Chat Completions API."""

    provider_id = "perplexity"
    collection_mode = "api"
    surface = "perplexity_sonar"

    def __init__(self, *, model: str = _DEFAULT_MODEL, api_key: str | None = None, timeout: int = 120):
        self.model = model
        self.api_key = api_key or os.environ.get("PERPLEXITY_API_KEY", "")
        self.timeout = timeout

    def _fetch_raw(self, request: CollectionRequest) -> dict:
        if not self.api_key:
            raise RuntimeError("PERPLEXITY_API_KEY is required for Perplexity API collection")
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": request.prompt.query_text}],
        }
        response = requests.post(
            _PERPLEXITY_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=body,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return cast(dict, response.json())

    def _from_raw(self, raw: dict, request: CollectionRequest) -> CollectedAnswer:
        choice = (raw.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        answer_text = str(message.get("content", ""))
        urls: list[str] = []
        citations_meta = message.get("citations") or raw.get("citations") or []
        if isinstance(citations_meta, list):
            for item in citations_meta:
                if isinstance(item, str):
                    urls.append(item)
                elif isinstance(item, dict) and item.get("url"):
                    urls.append(str(item["url"]))
        citations = _citations_from_urls(urls)
        domains = sorted({_domain_from_url(u) for u in urls if _domain_from_url(u)})
        return CollectedAnswer(
            prompt_id=request.prompt.prompt_id,
            query_text=request.prompt.query_text,
            query_class=request.prompt.query_class,
            provider=self.provider_id,
            surface=self.surface,
            model=self.model,
            language=request.language,
            device=request.device,
            answer_text=answer_text,
            citations=citations,
            mentioned_domains=domains,
            collection_mode=self.collection_mode,
            parser_version=PARSER_VERSION,
            parse_confidence=0.9 if citations else 0.75,
            collected_at=_now_iso(),
            keyword_topic=request.prompt.keyword_topic,
            persona=request.prompt.persona,
        )

    def collect(self, request: CollectionRequest) -> CollectedAnswer:
        return self._from_raw(self._fetch_raw(request), request)

    def collect_with_raw(self, request: CollectionRequest) -> tuple[CollectedAnswer, dict]:
        raw = self._fetch_raw(request)
        return self._from_raw(raw, request), raw
