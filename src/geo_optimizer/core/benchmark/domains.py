"""Domain normalization helpers for benchmark comparisons."""

from __future__ import annotations

from urllib.parse import urlparse


def normalize_benchmark_domain(value: str) -> str:
    """Normalize domains so apex and leading-www hosts compare together."""
    raw = (value or "").strip().lower()
    if raw.startswith(("http://", "https://")):
        raw = urlparse(raw).hostname or raw
    raw = raw.split("/")[0].split(":")[0]
    return raw[4:] if raw.startswith("www.") else raw
