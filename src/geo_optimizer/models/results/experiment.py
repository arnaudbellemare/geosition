"""Typed memory/search measurement results, independent of readiness scores."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BrandObservation:
    """Conservative, inspectable brand classification for one answer."""

    brand: str = ""
    mentioned: bool = False
    recommended: bool = False
    owned_domain_cited: bool = False
    search_backed: bool = False
    mention_spans: list[dict] = field(default_factory=list)
    recommendation_spans: list[dict] = field(default_factory=list)
    classification_method: str = "explicit_recommendation_v1"


@dataclass
class ConditionMetrics:
    """Outcome percentages, averaging prompt rates equally."""

    condition: str = ""
    attempts: int = 0
    valid_answers: int = 0
    prompt_count: int = 0
    mentioned_answers: int = 0
    recommended_answers: int = 0
    owned_domain_cited_answers: int = 0
    search_used_answers: int = 0
    search_backed_answers: int = 0
    statuses: dict[str, int] = field(default_factory=dict)
    mention_rate: float | None = None
    recommendation_rate: float | None = None
    owned_domain_citation_rate: float | None = None
    search_use_rate: float | None = None
    search_observed_answers: int = 0
    search_unknown_answers: int = 0
    search_backed_rate: float | None = None
    search_used_mention_rate: float | None = None


@dataclass
class PairedDifference:
    """Complete-pair search-minus-unassisted difference in percentage points."""

    metric: str = ""
    pair_count: int = 0
    prompt_count: int = 0
    delta_pp: float | None = None
    interval_low_pp: float | None = None
    interval_high_pp: float | None = None


@dataclass
class ExperimentSlice:
    """A single provider/surface/model-version cohort."""

    provider: str = ""
    surface: str = ""
    requested_model: str = ""
    returned_model: str = ""
    collection_mode: str = ""
    configuration_hash: str = ""
    brand: str = ""
    conditions: list[ConditionMetrics] = field(default_factory=list)
    paired_differences: list[PairedDifference] = field(default_factory=list)
    unmatched_valid_answers: int = 0


@dataclass
class MemorySearchReport:
    """Separate memory/search tracks with evidence and cohort coverage."""

    experiment_id: str = ""
    collection_run_id: str = ""
    artifact_base: str = ""
    prompt_set_hash: str = ""
    configuration_hash: str = ""
    generated_at: str = ""
    total_attempts: int = 0
    generation_requests_made: int = 0
    unclassified_attempts: int = 0
    expected_attempts: int = 0
    missing_attempts: int = 0
    status_counts: dict[str, int] = field(default_factory=dict)
    error_counts: dict[str, int] = field(default_factory=dict)
    observed_tokens: int = 0
    usage_unknown_attempts: int = 0
    observed_search_queries: int = 0
    slices: list[ExperimentSlice] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
