"""Canonical schema for hybrid AI answer collection (API / browser / manual)."""

from __future__ import annotations

from dataclasses import dataclass, field

COLLECTION_SCHEMA_VERSION = "1.0"


@dataclass
class CollectedCitation:
    """Structured citation from provider metadata or extraction."""

    url: str = ""
    domain: str = ""
    title: str = ""
    position: int = 0
    snippet: str = ""


@dataclass
class CollectedAnswer:
    """Normalized answer record — internal contract for benchmark ingestion."""

    prompt_id: str = ""
    query_text: str = ""
    query_class: str = ""
    provider: str = ""
    surface: str = ""
    model: str = ""
    country: str = ""
    language: str = "en"
    device: str = "desktop"
    logged_in_state: str = "unknown"
    answer_text: str = ""
    citations: list[CollectedCitation] = field(default_factory=list)
    mentioned_domains: list[str] = field(default_factory=list)
    mentioned_brands: list[str] = field(default_factory=list)
    raw_response_path: str = ""
    rendered_html_path: str = ""
    screenshot_path: str = ""
    collection_mode: str = "api"  # api | browser | manual
    parser_version: str = ""
    parse_confidence: float = 1.0
    collected_at: str = ""
    keyword_topic: str = ""
    persona: str = ""
    status: str = "success"  # success | error
    error_code: str = ""


@dataclass
class PromptSpec:
    """Fixed prompt in a collection run."""

    prompt_id: str = ""
    query_text: str = ""
    query_class: str = ""
    keyword_topic: str = ""
    persona: str = ""
    country: str = ""
    language: str = "en"


@dataclass
class CollectedAnswerBatch:
    """Versioned bundle written to disk before benchmark run."""

    schema_version: str = COLLECTION_SCHEMA_VERSION
    target_domain: str = ""
    collection_run_id: str = ""
    prompts: list[PromptSpec] = field(default_factory=list)
    answers: list[CollectedAnswer] = field(default_factory=list)


__all__ = [
    "COLLECTION_SCHEMA_VERSION",
    "CollectedCitation",
    "CollectedAnswer",
    "PromptSpec",
    "CollectedAnswerBatch",
]
