"""Read-only commerce monitoring result."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CommerceMonitorResult:
    url: str
    checked_at: str
    baseline: bool
    coverage: dict
    changes: list[dict] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    journey_probes: list[dict] = field(default_factory=list)
