"""Gemini generation with optional, observable Google Search grounding."""

from __future__ import annotations

import os
import re
from copy import deepcopy

import requests

from geo_optimizer.core.collection.normalize import _domain_from_url
from geo_optimizer.core.collection.protocol import CollectionRequest
from geo_optimizer.core.collection.store import PARSER_VERSION, _now_iso
from geo_optimizer.models.results.collection import CitationSupport, CollectedAnswer, CollectedCitation

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}"
_MODEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")


def _grounding_citations(parts: list[dict], metadata: dict) -> tuple[list[CollectedCitation], list[CollectedCitation]]:
    """Separate retrieved chunks from supported citations; offsets are UTF-8 bytes."""
    chunks = metadata.get("groundingChunks") or []
    retrieved = []
    for index, chunk in enumerate(chunks):
        web = chunk.get("web") or {}
        uri = str(web.get("uri", ""))
        retrieved.append(
            CollectedCitation(
                url=uri,
                domain=_domain_from_url(uri),
                title=str(web.get("title", "")),
                position=index + 1,
                evidence_type="retrieved",
            )
        )
    supported: dict[int, CollectedCitation] = {}
    for support in metadata.get("groundingSupports") or []:
        segment = support.get("segment") or {}
        part_index = segment.get("partIndex", 0)
        if not isinstance(part_index, int) or not 0 <= part_index < len(parts) or parts[part_index].get("thought"):
            continue
        text = str(parts[part_index].get("text", ""))
        start, end = segment.get("startIndex", 0), segment.get("endIndex", 0)
        if not isinstance(start, int) or not isinstance(end, int) or not 0 <= start < end <= len(text.encode("utf-8")):
            continue
        try:
            before = text.encode("utf-8")[:start].decode("utf-8")
            quote = text.encode("utf-8")[start:end].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if segment.get("text") and segment["text"] != quote:
            continue
        offset = sum(len(str(p.get("text", ""))) for p in parts[:part_index] if not p.get("thought"))
        span = CitationSupport(start=offset + len(before), end=offset + len(before) + len(quote), text=quote)
        for index in support.get("groundingChunkIndices") or []:
            if not isinstance(index, int) or not 0 <= index < len(retrieved) or not retrieved[index].url:
                continue
            citation = supported.setdefault(index, deepcopy(retrieved[index]))
            citation.evidence_type = "citation"
            citation.supports.append(span)
    return [c for c in retrieved if c.url], list(supported.values())


class GeminiGroundingAdapter:
    """Collect fresh API answers; legacy requests keep search enabled by default."""

    provider_id = "gemini_grounding"
    collection_mode = "api"
    surface = "gemini_generate_content"

    def __init__(self, *, model: str = "gemini-2.5-flash", api_key: str | None = None, timeout: int = 120):
        if not _MODEL_RE.fullmatch(model):
            raise ValueError("Use a Gemini model identifier, without URL or path components")
        self.model = model
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is required for Gemini collection")
        return {"x-goog-api-key": self.api_key}

    def check_capabilities(self) -> dict:
        """Check generation availability without making a paid generation request.

        Model metadata does not certify search support. A rejected search request is
        retained as a failed attempt; there is no fallback to another model.
        """
        response = requests.get(
            _GEMINI_URL.format(model=self.model), headers=self._headers(), timeout=self.timeout, allow_redirects=False
        )
        response.raise_for_status()
        raw = response.json()
        if not isinstance(raw, dict):
            raise ValueError("The model metadata response was not a JSON object")
        if "generateContent" not in raw.get("supportedGenerationMethods", []):
            raise ValueError("The selected model does not advertise generateContent support")
        return raw

    def collect(self, request: CollectionRequest) -> CollectedAnswer:
        """Use the same parsing and controls as raw-persisting collection."""
        return self.collect_with_raw(request)[0]

    def collect_with_raw(self, request: CollectionRequest) -> tuple[CollectedAnswer, dict]:
        """Send only the neutral prompt and generation controls, never scoring data."""
        if request.retrieval_policy not in {"default", "disabled", "enabled"}:
            raise ValueError("Unsupported retrieval policy")
        body: dict = {"contents": [{"parts": [{"text": request.prompt.query_text}]}]}
        if request.retrieval_policy != "disabled":
            body["tools"] = [{"googleSearch": {}}]
        if request.generation_settings:
            body["generationConfig"] = dict(request.generation_settings)
        response = requests.post(
            _GEMINI_URL.format(model=self.model) + ":generateContent",
            headers=self._headers(),
            json=body,
            timeout=self.timeout,
            allow_redirects=False,
        )
        response.raise_for_status()
        raw = response.json()
        return self._from_raw(raw, request), raw

    def _from_raw(self, raw: dict, request: CollectionRequest) -> CollectedAnswer:
        candidate = (raw.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        answer_text = "".join(str(p.get("text", "")) for p in parts if not p.get("thought"))
        metadata = candidate.get("groundingMetadata") or {}
        retrieved, citations = _grounding_citations(parts, metadata)
        queries = [str(q) for q in metadata.get("webSearchQueries", []) if q]
        provenance = deepcopy(request.provenance)
        provenance.requested_model = self.model
        provenance.returned_model = str(raw.get("modelVersion", ""))
        provenance.search_enabled = request.retrieval_policy != "disabled"
        provenance.available_tools = ["googleSearch"] if provenance.search_enabled else []
        provenance.context_isolated = True
        provenance.request_sent = True
        provenance.requested_language = request.language
        provenance.requested_country = request.country
        provenance.search_queries = queries
        provenance.retrieved_sources = retrieved
        if queries or retrieved:
            provenance.search_used = True
            provenance.search_evidence = "provider_grounding"
        elif request.retrieval_policy == "disabled":
            provenance.search_used = False
            provenance.search_evidence = "tools_disabled"
        else:
            # Absence of grounding metadata cannot prove that no search happened.
            provenance.search_used = None
            provenance.search_evidence = "no_search_evidence"
        provenance.usage = {key: value for key, value in (raw.get("usageMetadata") or {}).items() if type(value) is int}
        blocked = (raw.get("promptFeedback") or {}).get("blockReason")
        finish = str(candidate.get("finishReason", ""))
        if blocked or finish in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}:
            status, error = "refused", "provider_refusal"
        elif not answer_text.strip():
            status, error = "empty", "empty_response"
        elif finish and finish != "STOP":
            status, error = "error", "incomplete_response"
        elif request.retrieval_policy == "disabled" and provenance.search_used:
            status, error = "error", "unexpected_retrieval"
        else:
            status, error = "success", ""
        return CollectedAnswer(
            prompt_id=request.prompt.prompt_id,
            query_text=request.prompt.query_text,
            query_class=request.prompt.query_class,
            provider="gemini",
            surface=self.surface,
            model=self.model,
            language=request.language,
            answer_text=answer_text if status == "success" else "",
            citations=citations,
            mentioned_domains=sorted({_domain_from_url(c.url) for c in citations}),
            collection_mode=self.collection_mode,
            parser_version=PARSER_VERSION,
            parse_confidence=0.92 if citations else 0.7,
            collected_at=_now_iso(),
            keyword_topic=request.prompt.keyword_topic,
            persona=request.prompt.persona,
            status=status,
            error_code=error,
            provenance=provenance,
        )
