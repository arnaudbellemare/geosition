"""Result of offline commerce feed validation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FeedValidation:
    basic_checks_passed: bool
    ready_for_enabled_export: bool
    rows: list[dict]
    limitations: list[str]
