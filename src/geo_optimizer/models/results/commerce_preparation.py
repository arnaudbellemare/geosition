"""Data returned by the commerce preparation workflow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CommercePreparation:
    catalog: dict
    validation: dict
    structured_data: dict
