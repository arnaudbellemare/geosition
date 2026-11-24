"""Site-level commerce audit result."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CommerceSiteReport:
    url: str
    pages: list[dict] = field(default_factory=list)
    failures: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    coverage: dict = field(default_factory=dict)
    recommendations: list[dict] = field(default_factory=list)
    browser_access: dict = field(default_factory=dict)
