"""Dataclasses for GEOSITION results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass
class MethodEvidence:
    """Structured evidence attached to a citability method score."""

    summary: str = ""
    examples: list[str] = field(default_factory=list)
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
class MethodScore:
    """A content heuristic; its score is not a measured citation effect."""

    name: str  # "cite_sources"
    label: str  # "Cite Sources"
    detected: bool = False
    score: int = 0
    max_score: int = 10
    impact: str = ""  # "+27%"
    details: MethodEvidence | Mapping[str, object] = field(default_factory=MethodEvidence)
    evidence_level: str = "product_heuristic"


@dataclass
class CitabilityResult:
    """Citability analysis result with the 9 Princeton KDD 2024 methods."""

    methods: list[MethodScore] = field(default_factory=list)
    total_score: int = 0  # 0-100 (normalized sum)
    grade: str = "low"  # low/medium/high/excellent
    top_improvements: list[str] = field(default_factory=list)


# ─── AI Discovery (geo-checklist.dev) ────────────────────────────────────────


@dataclass
class AiDiscoveryResult:
    """Result of checking AI discovery endpoints (.well-known/ai.txt, /ai/*.json)."""

    has_well_known_ai: bool = False
    has_summary: bool = False
    has_faq: bool = False
    has_service: bool = False
    summary_valid: bool = False  # ha i campi richiesti (name + description)
    faq_count: int = 0  # number of FAQs found
    endpoints_found: int = 0  # total count of endpoints found (0-4)


# ─── CDN AI Crawler Check (#225) ─────────────────────────────────────────────


@dataclass
class CdnAiCrawlerResult:
    """Result of checking if CDN blocks AI crawler user-agents.

    Simulates requests as AI bots (GPTBot, ClaudeBot, PerplexityBot) and
    compares status codes + content-length to a normal browser request.
    """

    checked: bool = False
    browser_status: int = 0
    browser_content_length: int = 0
    bot_results: list[dict] = field(default_factory=list)
    # bot_results: [{"bot": "GPTBot", "status": 200, "content_length": 12345,
    #                "blocked": False, "challenge_detected": False}]
    any_blocked: bool = False
    cdn_detected: str = ""  # "cloudflare", "akamai", "aws", "" if none
    cdn_headers: dict[str, str] = field(default_factory=dict)
    error: str = ""  # fix #304: error message (unsafe URL, timeout, etc.)


# ─── JS Rendering Check (#226) ──────────────────────────────────────────────


@dataclass
class JsRenderingResult:
    """Result of checking if page content is accessible without JavaScript.

    Analyzes raw HTML (no JS execution) for content indicators:
    word count, heading count, SPA framework detection.
    """

    checked: bool = False
    raw_word_count: int = 0
    raw_heading_count: int = 0
    has_empty_root: bool = False  # <div id="root"></div> or id="app"
    has_noscript_content: bool = False
    framework_detected: str = ""  # "react", "vue", "angular", "next", ""
    js_dependent: bool = False  # True if content likely needs JS
    details: str = ""


# ─── WebMCP Readiness Check (#233) ────────────────────────────────────────────


@dataclass
class WebMcpResult:
    """Checks whether the site is ready for AI agents via WebMCP and related signals."""

    checked: bool = False

    # WebMCP detection
    has_register_tool: bool = False  # navigator.modelContext.registerTool()
    has_tool_attributes: bool = False  # HTML attributes toolname/tooldescription
    tool_count: int = 0  # number of declared tools

    # Agent-readiness signals
    has_potential_action: bool = False  # schema potentialAction (SearchAction, etc.)
    potential_actions: list[str] = field(default_factory=list)  # action types found
    has_labeled_forms: bool = False  # forms with accessible label + description
    labeled_forms_count: int = 0
    has_openapi: bool = False  # link to OpenAPI/Swagger spec

    # Summary
    agent_ready: bool = False  # True if at least 1 WebMCP signal or 2+ agent-readiness signals
    readiness_level: str = "none"  # "none", "basic", "ready", "advanced"


# ─── Prompt Injection Detection (#276) ────────────────────────────────────────

__all__ = [
    "MethodEvidence",
    "MethodScore",
    "CitabilityResult",
    "AiDiscoveryResult",
    "CdnAiCrawlerResult",
    "JsRenderingResult",
    "WebMcpResult",
]
