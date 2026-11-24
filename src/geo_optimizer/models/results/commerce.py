"""Results for a single-page AI commerce readiness audit."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CommerceReadinessReport:
    url: str
    products: list[dict] = field(default_factory=list)
    services: list[str] = field(default_factory=list)
    journey_signals: list[dict] = field(default_factory=list)
    manual_checks: dict[str, str] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
