"""Service and enquiry preparation result."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ServicePreparation:
    review: dict
    validation: dict
    structured_data: dict
