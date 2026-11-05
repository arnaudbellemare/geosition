"""Tests for AI answer collection provider adapters."""

from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from geo_optimizer.core.collection.adapters.brightdata_browser import BrightDataBrowserAdapter
from geo_optimizer.core.collection.protocol import CollectionRequest
from geo_optimizer.models.results.collection import PromptSpec


def _request() -> CollectionRequest:
    return CollectionRequest(
        prompt=PromptSpec(prompt_id="p1", query_text="best tools", query_class="recommendation"),
        target_domain="example.com",
    )


def test_brightdata_adapter_rejects_private_tracker_url():
    adapter = BrightDataBrowserAdapter(tracker_base_url="http://169.254.169.254/latest")

    with patch("requests.post") as post, pytest.raises(ValueError, match="Unsafe tracker URL"):
        adapter.collect(_request())

    post.assert_not_called()


def test_brightdata_adapter_allows_localhost_tracker_url():
    adapter = BrightDataBrowserAdapter(tracker_base_url="http://127.0.0.1:3000")
    response = Mock()
    response.json.return_value = {
        "provider": "google_ai",
        "prompt": "best tools",
        "answer": "Use https://example.com",
        "sources": ["https://example.com"],
    }
    response.raise_for_status.return_value = None

    with patch("requests.post", return_value=response) as post:
        answer = adapter.collect(_request())

    assert answer.provider == "google_ai"
    assert answer.citations[0].url == "https://example.com"
    post.assert_called_once()


def test_gemini_key_is_sent_in_header_and_language_is_preserved():
    from geo_optimizer.core.collection.adapters.gemini_grounding import GeminiGroundingAdapter

    response = Mock()
    response.json.return_value = {"candidates": [{"content": {"parts": [{"text": "Réponse"}]}}]}
    adapter = GeminiGroundingAdapter(api_key="test-key")
    request = CollectionRequest(prompt=PromptSpec(query_text="Question"), language="fr", country="CA")
    with patch("requests.post", return_value=response) as post:
        answer, _ = adapter.collect_with_raw(request)
    assert "test-key" not in post.call_args.args[0]
    assert post.call_args.kwargs["headers"]["x-goog-api-key"] == "test-key"
    assert answer.language == "fr"
    assert not answer.country
