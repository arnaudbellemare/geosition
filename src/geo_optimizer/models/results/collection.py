"""Canonical schema for hybrid AI answer collection (API / browser / manual)."""

from __future__ import annotations

from dataclasses import dataclass, field

COLLECTION_SCHEMA_VERSION = "1.1"


@dataclass
class CitationSupport:
    """Provider-supported span in answer text, using Python character offsets."""

    start: int = 0
    end: int = 0
    text: str = ""


@dataclass
class CollectedCitation:
    """Structured citation from provider metadata or extraction."""

    url: str = ""
    domain: str = ""
    title: str = ""
    position: int = 0
    snippet: str = ""
    evidence_type: str = "unknown"  # unknown | retrieved | citation
    supports: list[CitationSupport] = field(default_factory=list)


@dataclass
class AnswerProvenance:
    """Requested experiment controls and separately observed retrieval behavior."""

    experiment_id: str = ""
    condition: str = "unknown"  # unknown | unassisted | search_enabled
    repetition: int = 0
    attempt_id: str = ""
    prompt_hash: str = ""
    configuration_hash: str = ""
    requested_model: str = ""
    returned_model: str = ""
    context_isolated: bool = False
    request_sent: bool | None = None
    requested_language: str = ""
    requested_country: str = ""
    effective_language: str = ""
    effective_country: str = ""
    search_enabled: bool | None = None
    search_used: bool | None = None
    search_evidence: str = "unknown"
    available_tools: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    retrieved_sources: list[CollectedCitation] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)


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
    status: str = "success"  # success | error | refused | empty
    error_code: str = ""
    provenance: AnswerProvenance = field(default_factory=AnswerProvenance)


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
    experiment: ExperimentManifest | None = None
    artifact_base: str = ""


@dataclass
class ExperimentBrand:
    """Scoring-only brand identity, never included in provider requests."""

    name: str = ""
    domain: str = ""
    aliases: list[str] = field(default_factory=list)


@dataclass
class ExperimentManifest:
    """Frozen controls for one paired memory/search measurement wave."""

    schema_version: str = "1.0"
    experiment_id: str = ""
    target: ExperimentBrand = field(default_factory=ExperimentBrand)
    competitors: list[ExperimentBrand] = field(default_factory=list)
    provider: str = "gemini"
    surface: str = "gemini_generate_content"
    model: str = ""
    repetitions: int = 3
    generation_settings: dict[str, float | int] = field(default_factory=dict)
    prompt_set_hash: str = ""
    configuration_hash: str = ""
    system_instruction_hash: str = ""
    created_at: str = ""
    max_requests: int = 120
    max_total_tokens: int | None = None


__all__ = [
    "COLLECTION_SCHEMA_VERSION",
    "CitationSupport",
    "AnswerProvenance",
    "ExperimentBrand",
    "ExperimentManifest",
    "CollectedCitation",
    "CollectedAnswer",
    "PromptSpec",
    "CollectedAnswerBatch",
]
