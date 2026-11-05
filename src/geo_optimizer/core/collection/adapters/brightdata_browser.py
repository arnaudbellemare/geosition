"""Browser lane via geo-aeo-tracker scrape API or direct Bright Data proxy."""

from __future__ import annotations

import json
import os
from urllib.parse import urlparse

import requests

from geo_optimizer.core.collection.protocol import CollectionRequest
from geo_optimizer.core.collection.store import PARSER_VERSION
from geo_optimizer.core.collection.tracker_bridge import from_brightdata_scrape
from geo_optimizer.models.results.collection import CollectedAnswer

_TRACKER_PROVIDER_MAP = {
    "google_ai": "google_ai",
    "google_ai_mode": "google_ai",
    "ai_mode": "google_ai",
    "chatgpt": "chatgpt",
    "perplexity": "perplexity",
    "gemini": "gemini",
    "copilot": "copilot",
    "grok": "grok",
}

_LOCAL_TRACKER_HOSTS = {"localhost", "127.0.0.1", "::1"}


def _validate_tracker_url(base_url: str) -> None:
    """Allow local tracker instances or public tracker URLs, but block private SSRF targets."""
    parsed = urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Tracker URL must be an http(s) URL")
    if parsed.hostname.lower() in _LOCAL_TRACKER_HOSTS:
        return

    from geo_optimizer.utils.validators import validate_public_url

    ok, reason = validate_public_url(f"{base_url.rstrip('/')}/api/scrape")
    if not ok:
        raise ValueError(f"Unsafe tracker URL: {reason}")


class BrightDataBrowserAdapter:
    """Collect via geo-aeo-tracker POST /api/scrape (Bright Data datasets)."""

    provider_id = "brightdata"
    collection_mode = "browser"
    surface = "brightdata_scraper"

    def __init__(
        self,
        *,
        platform: str = "google_ai",
        tracker_base_url: str | None = None,
        timeout: int = 300,
    ):
        self.platform = _TRACKER_PROVIDER_MAP.get(platform, platform)
        self.tracker_base_url = (tracker_base_url or os.environ.get("GEO_AEO_TRACKER_URL", "")).rstrip("/")
        self.timeout = timeout
        self.surface = f"brightdata_{self.platform}"

    def collect(self, request: CollectionRequest) -> CollectedAnswer:
        if not self.tracker_base_url:
            raise RuntimeError(
                "GEO_AEO_TRACKER_URL is required for browser lane "
                "(e.g. http://localhost:3000 when geo-aeo-tracker is running)"
            )

        payload = {
            "provider": self.platform,
            "prompt": request.prompt.query_text,
            "requireSources": True,
            "country": request.country or request.prompt.country or None,
        }
        _validate_tracker_url(self.tracker_base_url)
        url = f"{self.tracker_base_url}/api/scrape"
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            data=json.dumps({k: v for k, v in payload.items() if v is not None}),
            timeout=self.timeout,
        )
        response.raise_for_status()
        raw = response.json()
        if raw.get("error"):
            raise RuntimeError(str(raw["error"]))

        answer = from_brightdata_scrape(
            raw,
            prompt_id=request.prompt.prompt_id,
            query_class=request.prompt.query_class,
        )
        answer.keyword_topic = request.prompt.keyword_topic
        answer.persona = request.prompt.persona
        answer.country = request.country or request.prompt.country
        answer.parser_version = PARSER_VERSION
        return answer

    def collect_with_raw(self, request: CollectionRequest) -> tuple[CollectedAnswer, dict]:
        """Collect and return raw scrape payload."""
        if not self.tracker_base_url:
            raise RuntimeError("GEO_AEO_TRACKER_URL is required for browser lane")

        payload = {
            "provider": self.platform,
            "prompt": request.prompt.query_text,
            "requireSources": True,
            "country": request.country or request.prompt.country or None,
        }
        _validate_tracker_url(self.tracker_base_url)
        url = f"{self.tracker_base_url}/api/scrape"
        response = requests.post(
            url,
            headers={"Content-Type": "application/json"},
            json={k: v for k, v in payload.items() if v is not None},
            timeout=self.timeout,
        )
        response.raise_for_status()
        raw = response.json()
        if raw.get("error"):
            raise RuntimeError(str(raw["error"]))
        answer = from_brightdata_scrape(
            raw,
            prompt_id=request.prompt.prompt_id,
            query_class=request.prompt.query_class,
        )
        return answer, raw
