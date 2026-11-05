"""Provider-specific answer collector adapters."""

from __future__ import annotations

from geo_optimizer.core.collection.adapters.brightdata_browser import BrightDataBrowserAdapter
from geo_optimizer.core.collection.adapters.gemini_grounding import GeminiGroundingAdapter
from geo_optimizer.core.collection.adapters.manual import ManualFileAdapter
from geo_optimizer.core.collection.adapters.perplexity import PerplexityApiAdapter

ADAPTER_REGISTRY: dict[str, type] = {
    "perplexity": PerplexityApiAdapter,
    "gemini_grounding": GeminiGroundingAdapter,
    "gemini": GeminiGroundingAdapter,
    "brightdata": BrightDataBrowserAdapter,
    "google_ai": BrightDataBrowserAdapter,
    "chatgpt": BrightDataBrowserAdapter,
    "manual": ManualFileAdapter,
}


def get_adapter(provider_id: str, **kwargs):
    """Instantiate adapter by id."""
    key = provider_id.strip().lower()
    if key not in ADAPTER_REGISTRY:
        raise ValueError(f"Unknown collector adapter: {provider_id}. Choose from: {', '.join(ADAPTER_REGISTRY)}")
    if key in {"chatgpt", "google_ai"}:
        kwargs.setdefault("platform", key)
    return ADAPTER_REGISTRY[key](**kwargs)


__all__ = [
    "ADAPTER_REGISTRY",
    "get_adapter",
    "PerplexityApiAdapter",
    "GeminiGroundingAdapter",
    "BrightDataBrowserAdapter",
    "ManualFileAdapter",
]
