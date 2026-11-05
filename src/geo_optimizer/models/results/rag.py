"""Dataclasses for GEOSITION results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RagChunkResult:
    """RAG chunking readiness analysis (#353)."""

    checked: bool = False
    total_sections: int = 0
    sections_in_range: int = 0
    avg_section_words: float = 0.0
    has_definition_opening: bool = False
    heading_as_boundary_ratio: float = 0.0
    anchor_sentences: int = 0
    chunk_readiness_score: int = 0


# ─── Embedding Proximity (v4.7) ─────────────────────────────────────────────


@dataclass
class QueryScore:
    """Per-query similarity score from embedding proximity analysis."""

    query: str = ""
    max_similarity: float = 0.0


@dataclass
class EmbeddingProximityResult:
    """Embedding-based RAG retrieval simulation (#354)."""

    checked: bool = False
    skipped_reason: str | None = None
    model_name: str = ""
    query_scores: list[QueryScore] = field(default_factory=list)
    avg_similarity: float = 0.0
    top_similarity: float = 0.0
    retrievable_chunks: int = 0
    total_chunks: int = 0


# ─── Semantic Coherence (v4.7) ───────────────────────────────────────────────


@dataclass
class PageTermExtract:
    """Terminology extracted from a single page for cross-page analysis (#253)."""

    url: str = ""
    title: str = ""
    h1: str = ""
    definitions: list[str] = field(default_factory=list)
    key_terms: list[str] = field(default_factory=list)
    language: str = ""
    hreflang_langs: list[str] = field(default_factory=list)


@dataclass
class CoherenceIssue:
    """A single cross-page coherence problem (#253)."""

    issue_type: str = ""  # conflicting_definition | duplicate_title | mixed_language
    severity: str = "low"  # high | medium | low
    description: str = ""
    pages: list[str] = field(default_factory=list)
    terms: list[str] = field(default_factory=list)


@dataclass
class SemanticCoherenceResult:
    """Aggregated cross-page semantic coherence analysis (#253)."""

    checked: bool = False
    pages_analyzed: int = 0
    issues: list[CoherenceIssue] = field(default_factory=list)
    coherence_score: int = 100
    language_consistency: float = 1.0


__all__ = [
    "RagChunkResult",
    "QueryScore",
    "EmbeddingProximityResult",
    "PageTermExtract",
    "CoherenceIssue",
    "SemanticCoherenceResult",
]
