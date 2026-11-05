"""Dataclasses for GEOSITION results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrustLayerDetails:
    """Typed metadata associated with a trust layer score."""

    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    metrics: dict[str, float] = field(default_factory=dict)
    extra: dict[str, object] = field(default_factory=dict)

    def get(self, key: str, default: object = None) -> object:
        """Backward-compatible dict-style access used by legacy consumers."""
        return self.extra.get(key, default)

    def __getitem__(self, key: str) -> object:
        return self.extra[key]

    def __setitem__(self, key: str, value: object) -> None:
        self.extra[key] = value


@dataclass
class PromptInjectionResult:
    """Detection of prompt injection patterns in web content (v4.4)."""

    checked: bool = False

    # Cat 1: text hidden via inline CSS
    hidden_text_found: bool = False
    hidden_text_count: int = 0
    hidden_text_samples: list[str] = field(default_factory=list)

    # Cat 2: invisible Unicode characters
    invisible_unicode_found: bool = False
    invisible_unicode_count: int = 0

    # Cat 3: direct LLM instructions
    llm_instruction_found: bool = False
    llm_instruction_count: int = 0
    llm_instruction_samples: list[str] = field(default_factory=list)

    # Cat 4: prompt in HTML comments
    html_comment_injection_found: bool = False
    html_comment_injection_count: int = 0
    html_comment_samples: list[str] = field(default_factory=list)

    # Cat 5: monochrome text (color ≈ background)
    monochrome_text_found: bool = False
    monochrome_text_count: int = 0

    # Cat 6: micro-font injection (font-size < 2px)
    microfont_found: bool = False
    microfont_count: int = 0

    # Cat 7: data attribute injection (data-ai-*, data-prompt-*)
    data_attr_injection_found: bool = False
    data_attr_injection_count: int = 0
    data_attr_samples: list[str] = field(default_factory=list)

    # Cat 8: aria-hidden with instructional content
    aria_hidden_injection_found: bool = False
    aria_hidden_injection_count: int = 0
    aria_hidden_samples: list[str] = field(default_factory=list)

    # Summary
    patterns_found: int = 0  # active categories (0-8)
    severity: str = "clean"  # "clean" | "suspicious" | "critical"
    risk_level: str = "none"  # "none" | "low" | "medium" | "high"


# ─── Negative Signals Detection ───────────────────────────────────────────────


@dataclass
class NegativeSignalsResult:
    """Negative signals that reduce the probability of AI citation."""

    checked: bool = False

    # 1. Excessive CTA density (self-promotional)
    cta_density_high: bool = False
    cta_count: int = 0

    # 2. Popup/interstitial in the DOM
    has_popup_signals: bool = False
    popup_indicators: list[str] = field(default_factory=list)

    # 3. Thin content
    is_thin_content: bool = False  # < 300 words with complex H1

    # 4. Broken/empty internal links
    broken_links_count: int = 0
    has_broken_links: bool = False

    # 5. Keyword stuffing
    has_keyword_stuffing: bool = False
    stuffed_word: str = ""
    stuffed_density: float = 0.0

    # 6. Missing author signal
    has_author_signal: bool = False  # Person schema, rel=author, class=author

    # 7. Boilerplate ratio
    boilerplate_ratio: float = 0.0  # 0.0-1.0 (nav+footer+sidebar / total)
    boilerplate_high: bool = False  # ratio > 0.6

    # 8. Mixed signals (promise vs content)
    has_mixed_signals: bool = False
    mixed_signal_detail: str = ""

    # Summary
    signals_found: int = 0  # count of negative signals found
    severity: str = "clean"  # "clean", "low", "medium", "high"


# ─── Trust Stack Score (#273) ─────────────────────────────────────────────────


@dataclass
class TrustLayerScore:
    """Score for a single Trust Stack layer."""

    name: str  # "technical", "identity", "social", "academic", "consistency"
    label: str  # "Technical Trust"
    score: int = 0
    max_score: int = 5
    signals_found: list[str] = field(default_factory=list)
    signals_missing: list[str] = field(default_factory=list)
    details: TrustLayerDetails = field(default_factory=TrustLayerDetails)


def _make_layer(name: str, label: str) -> TrustLayerScore:
    """Factory to create a TrustLayerScore with clean defaults."""
    return TrustLayerScore(name=name, label=label)


@dataclass
class TrustStackResult:
    """5-layer trust signal aggregation (v4.5, #273). Informational — does not affect GEO score."""

    checked: bool = False
    technical: TrustLayerScore = field(default_factory=lambda: _make_layer("technical", "Technical Trust"))
    identity: TrustLayerScore = field(default_factory=lambda: _make_layer("identity", "Identity Trust"))
    social: TrustLayerScore = field(default_factory=lambda: _make_layer("social", "Social Trust"))
    academic: TrustLayerScore = field(default_factory=lambda: _make_layer("academic", "Academic Trust"))
    consistency: TrustLayerScore = field(default_factory=lambda: _make_layer("consistency", "Consistency Trust"))
    composite_score: int = 0  # 0-25
    grade: str = "F"  # A/B/C/D/F
    trust_level: str = "low"  # "low" | "medium" | "high" | "excellent"


# ─── RAG Chunk Readiness (v4.7) ──────────────────────────────────────────────

__all__ = [
    "TrustLayerDetails",
    "PromptInjectionResult",
    "NegativeSignalsResult",
    "TrustLayerScore",
    "TrustStackResult",
]
