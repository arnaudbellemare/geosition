"""
GEOSITION — Generative Engine Optimization Toolkit

Make websites visible and citable by AI search engines
(ChatGPT, Perplexity, Claude, Gemini).

Based on the Princeton KDD 2024 research paper (arxiv.org/abs/2311.09735).

Programmatic usage::

    from geo_optimizer import audit, AuditResult
    result = audit("https://example.com")
    print(result.score, result.band)
"""

from __future__ import annotations

import warnings

# Suppress persistent urllib3 LibreSSL runtime warning in CLI contexts.
warnings.filterwarnings(
    "ignore",
    message=r"urllib3 v2 only supports OpenSSL 1\.1\.1\+.*",
    category=Warning,
)

__version__ = "4.9.0"

# ─── Public API ──────────────────────────────────────────────────────────────

from geo_optimizer.core.audit import run_full_audit as audit  # noqa: E402
from geo_optimizer.core.audit import run_full_audit_async as audit_async  # noqa: E402
from geo_optimizer.core.registry import AuditCheck, CheckRegistry, CheckResult  # noqa: E402
from geo_optimizer.models.results import (  # noqa: E402
    AuditResult,
    CitabilityResult,
    ContentResult,
    FixItem,
    FixPlan,
    LlmsTxtResult,
    MetaResult,
    MethodScore,
    NextAction,
    RobotsResult,
    SchemaAnalysis,
    SchemaResult,
    SitemapUrl,
    VerticalAuditResult,
    VerticalSignal,
)

__all__ = [
    # Version
    "__version__",
    # Main functions
    "audit",
    "audit_async",
    # Plugin system
    "CheckRegistry",
    "AuditCheck",
    "CheckResult",
    # Result dataclasses
    "AuditResult",
    "RobotsResult",
    "LlmsTxtResult",
    "SchemaResult",
    "MetaResult",
    "ContentResult",
    "CitabilityResult",
    "MethodScore",
    "NextAction",
    "FixPlan",
    "FixItem",
    "SchemaAnalysis",
    "SitemapUrl",
    "VerticalAuditResult",
    "VerticalSignal",
]
