"""Test per summary storica nella web app."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from geo_optimizer.models.results import AuditResult

pytest.importorskip("fastapi", reason="fastapi non installato (pip install geosition[web])")

from geo_optimizer.web.app import _load_history_summary, _save_and_load_history_summary

_NOW = datetime.now(timezone.utc)


def _ts(days_ago: int) -> str:
    """Return an ISO timestamp *days_ago* days before now."""
    return (_NOW - timedelta(days=days_ago)).isoformat()


def _make_result(score: int, timestamp: str) -> AuditResult:
    """Creates a AuditResult minimo per i test web history."""
    return AuditResult(
        url="https://example.com",
        timestamp=timestamp,
        score=score,
        band="good" if score >= 68 else "foundation",
        http_status=200,
        page_size=1000,
        score_breakdown={"robots": 18, "llms": 12, "schema": 8, "meta": 10, "content": 8},
        recommendations=["fix-a"],
    )


def test_save_and_load_history_summary(monkeypatch, tmp_path):
    """The web app saves a snapshot and returns a serialisable trend summary."""
    db_path = Path(tmp_path / "tracking.db")
    monkeypatch.setattr("geo_optimizer.models.config.TRACKING_DB_PATH", db_path)
    monkeypatch.setattr("geo_optimizer.core.history.TRACKING_DB_PATH", db_path)

    first = _save_and_load_history_summary(_make_result(62, _ts(14)))
    second = _save_and_load_history_summary(_make_result(77, _ts(7)))

    assert first is not None
    assert first["total_snapshots"] == 1
    assert second is not None
    assert second["total_snapshots"] == 2
    assert second["score_delta"] == 15
    assert second["latest_score"] == 77


def test_load_history_summary_returns_none_when_empty(monkeypatch, tmp_path):
    """Without saved snapshots the web app exposes no history."""
    db_path = Path(tmp_path / "tracking.db")
    monkeypatch.setattr("geo_optimizer.models.config.TRACKING_DB_PATH", db_path)
    monkeypatch.setattr("geo_optimizer.core.history.TRACKING_DB_PATH", db_path)

    assert _load_history_summary("https://example.com") is None
