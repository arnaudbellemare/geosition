from __future__ import annotations

from unittest.mock import patch

from geo_optimizer.core.audit_media import _fetch_size
from geo_optimizer.core.audit_serp import _analyze_competitor


def test_serp_competitor_analysis_uses_hardened_fetch_for_untrusted_url():
    with patch("geo_optimizer.utils.http.fetch_url", return_value=(None, "Unsafe URL")) as fetch:
        competitor = _analyze_competitor(
            rank=1,
            url="http://169.254.169.254/latest/meta-data",
            title="",
            description="",
        )

    fetch.assert_called_once_with("http://169.254.169.254/latest/meta-data", timeout=10)
    assert competitor.word_count == 0


def test_media_size_check_blocks_unsafe_url_before_head_request():
    with patch(
        "geo_optimizer.utils.validators.resolve_and_validate_url",
        return_value=(False, "URL points to a non-public address.", []),
    ) as validate, patch("requests.head") as head:
        size = _fetch_size("http://169.254.169.254/video.mp4")

    validate.assert_called_once_with("http://169.254.169.254/video.mp4")
    head.assert_not_called()
    assert size == -1
