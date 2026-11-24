"""Adapter interface for answer collection lanes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from geo_optimizer.models.results.collection import AnswerProvenance, CollectedAnswer, PromptSpec


@dataclass
class CollectionRequest:
    """Per-prompt collection job."""

    prompt: PromptSpec
    target_domain: str = ""
    country: str = ""
    language: str = "en"
    device: str = "desktop"
    require_sources: bool = True
    retrieval_policy: str = "default"  # default | disabled | enabled
    provenance: AnswerProvenance = field(default_factory=AnswerProvenance)
    generation_settings: dict[str, float | int] = field(default_factory=dict)


class AnswerCollectorAdapter(Protocol):
    """Collect one answer from a provider lane (API, browser, or manual)."""

    provider_id: str
    collection_mode: str  # api | browser | manual
    surface: str

    def collect(self, request: CollectionRequest) -> CollectedAnswer:
        """Return normalized answer; may write raw payload via pipeline store."""
        ...
