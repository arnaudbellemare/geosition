"""Dataclasses for GEOSITION results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DecaySignal:
    """A single content decay signal (#383)."""

    decay_type: str = ""  # temporal | statistical | version | event | price
    text: str = ""
    estimated_stale_days: int = 0
    suggestion: str = ""


@dataclass
class ContentDecayResult:
    """Content decay prediction for a page (#383)."""

    checked: bool = False
    signals: list[DecaySignal] = field(default_factory=list)
    earliest_decay_days: int | None = None
    decay_risk: str = "low"  # low | medium | high
    evergreen_score: int = 100


# ─── Server Log Analysis (v4.7) ─────────────────────────────────────────────


@dataclass
class BotStats:
    """Statistics for a single AI bot from server logs (#227)."""

    bot_name: str = ""
    visits: int = 0
    unique_pages: int = 0
    first_seen: str = ""
    last_seen: str = ""


@dataclass
class CrawledPage:
    """A page crawled by AI bots (#227)."""

    path: str = ""
    total_visits: int = 0
    bots: list[str] = field(default_factory=list)


@dataclass
class LogAnalysisResult:
    """Server log analysis for AI crawler activity (#227)."""

    checked: bool = False
    log_file: str = ""
    total_lines: int = 0
    ai_requests: int = 0
    date_range_start: str = ""
    date_range_end: str = ""
    bots: list[BotStats] = field(default_factory=list)
    top_pages: list[CrawledPage] = field(default_factory=list)


# ─── Multi-Platform Citation Profile (v4.7) ─────────────────────────────────


@dataclass
class PlatformScore:
    """Readiness score for a specific AI platform (#228)."""

    platform: str = ""
    score: int = 0
    strengths: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


@dataclass
class PlatformCitationResult:
    """Multi-platform citation readiness profile (#228)."""

    checked: bool = False
    platforms: list[PlatformScore] = field(default_factory=list)


# ─── Brand Sentiment Analysis (v4.7) ────────────────────────────────────────


@dataclass
class BrandSentimentResult:
    """Brand sentiment analysis from LLM responses (#378)."""

    checked: bool = False
    skipped_reason: str | None = None
    brand: str = ""
    overall_score: int = 0  # -100 (negative) to +100 (positive)
    sentiment: str = "unknown"  # positive | neutral | negative | unknown
    positive_phrases: list[str] = field(default_factory=list)
    negative_phrases: list[str] = field(default_factory=list)
    recommendation_strength: str = ""  # strongly_recommended | mentioned | neutral | warned_against
    llm_provider: str = ""
    llm_model: str = ""
    raw_response: str = ""


# ─── Citation Attribution Chain (v4.7) ───────────────────────────────────────


@dataclass
class AttributionSegment:
    """A segment of LLM response matched to source content (#375)."""

    llm_text: str = ""
    source_text: str = ""
    similarity: float = 0.0
    faithfulness: str = ""  # faithful | paraphrased | altered | hallucinated


@dataclass
class CitationAttributionResult:
    """Citation attribution chain analysis (#375)."""

    checked: bool = False
    skipped_reason: str | None = None
    query: str = ""
    segments: list[AttributionSegment] = field(default_factory=list)
    faithfulness_score: float = 0.0  # 0-1
    details_lost: list[str] = field(default_factory=list)
    details_added: list[str] = field(default_factory=list)
    llm_provider: str = ""
    llm_model: str = ""


# ─── Multi-Turn Persistence (v4.7) ──────────────────────────────────────────


@dataclass
class TurnResult:
    """Result of a single conversation turn (#376)."""

    turn: int = 0
    query: str = ""
    brand_mentioned: bool = False
    mention_count: int = 0
    response_snippet: str = ""


@dataclass
class MultiTurnResult:
    """Multi-turn conversation persistence analysis (#376)."""

    checked: bool = False
    skipped_reason: str | None = None
    brand: str = ""
    turns: list[TurnResult] = field(default_factory=list)
    persistence_score: int = 0  # 0-100
    last_mentioned_turn: int = 0
    total_turns: int = 0
    llm_provider: str = ""
    llm_model: str = ""


# ─── Cross-Platform Citation Map (v4.7) ─────────────────────────────────────


@dataclass
class CitationMapEntry:
    """A single entry in the cross-platform citation map (#356)."""

    query: str = ""
    platform: str = ""
    brand_mentioned: bool = False
    sentiment: str = ""  # positive | neutral | negative
    faithfulness: float = 0.0
    snippet: str = ""


@dataclass
class CitationMapResult:
    """Cross-platform citation map aggregation (#356)."""

    checked: bool = False
    skipped_reason: str | None = None
    brand: str = ""
    entries: list[CitationMapEntry] = field(default_factory=list)
    platforms_tested: int = 0
    platforms_citing: int = 0
    overall_visibility: float = 0.0  # 0-1


# ─── Prompt Library (v4.7) ───────────────────────────────────────────────────


@dataclass
class PromptResult:
    """Result of executing a single prompt (#379)."""

    intent: str = ""
    prompt: str = ""
    brand_mentioned: bool = False
    mention_count: int = 0
    sentiment: str = ""
    response_snippet: str = ""


@dataclass
class PromptLibraryResult:
    """Batch prompt execution results (#379)."""

    checked: bool = False
    skipped_reason: str | None = None
    brand: str = ""
    results: list[PromptResult] = field(default_factory=list)
    mention_rate: float = 0.0  # 0-1
    avg_sentiment_score: float = 0.0
    llm_provider: str = ""
    llm_model: str = ""


# ─── Context Window Optimization (v4.9) ─────────────────────────────────────


@dataclass
class ContextWindowResult:
    """Context window utilization analysis (#370). Informational — does not affect GEO score."""

    checked: bool = False
    total_words: int = 0
    total_tokens_estimate: int = 0
    front_loaded_ratio: float = 0.0  # % of key info in first 30% of content
    key_info_tokens: int = 0  # tokens containing key information
    filler_ratio: float = 0.0  # % of tokens that are boilerplate/filler
    optimal_for: list[str] = field(default_factory=list)  # ["rag_chunk", "perplexity", "chatgpt", ...]
    truncation_risk: str = "none"  # none | low | medium | high
    context_efficiency_score: int = 0  # 0-100


# ─── Instruction Following Readiness (v4.9) ─────────────────────────────────


@dataclass
class InstructionReadinessResult:
    """AI agent instruction following readiness (#371). Informational — does not affect GEO score."""

    checked: bool = False
    # Action clarity: CTAs with descriptive text
    labeled_buttons: int = 0
    unlabeled_buttons: int = 0
    action_clarity_score: int = 0  # 0-100
    # Form machine-readability
    total_inputs: int = 0
    labeled_inputs: int = 0
    typed_inputs: int = 0  # inputs with explicit type attribute
    form_readability_score: int = 0  # 0-100
    # Workflow linearity: navigation complexity
    nav_links: int = 0
    stateful_urls: bool = False  # URLs with query params or hash fragments
    # Error recovery: machine-readable error patterns
    has_aria_live: bool = False
    has_error_roles: bool = False  # role="alert" or aria-invalid
    # Summary
    readiness_score: int = 0  # 0-100
    readiness_level: str = "none"  # none | basic | ready | advanced


__all__ = [
    "DecaySignal",
    "ContentDecayResult",
    "BotStats",
    "CrawledPage",
    "LogAnalysisResult",
    "PlatformScore",
    "PlatformCitationResult",
    "BrandSentimentResult",
    "AttributionSegment",
    "CitationAttributionResult",
    "TurnResult",
    "MultiTurnResult",
    "CitationMapEntry",
    "CitationMapResult",
    "PromptResult",
    "PromptLibraryResult",
    "ContextWindowResult",
    "InstructionReadinessResult",
]
