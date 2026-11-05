from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

pytest.importorskip("aiosqlite")
pytest.importorskip("pydantic_settings")

_SCRAPER_ROOT = Path(__file__).resolve().parents[1] / "apps" / "ai-scraper-api"
if str(_SCRAPER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRAPER_ROOT))

from src.auth import require_admin  # noqa: E402
from src.config import settings  # noqa: E402


def test_scraper_admin_auth_fails_closed_for_placeholder_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "change-me-in-production")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(require_admin("Bearer change-me-in-production"))

    assert exc.value.status_code == 503


def test_scraper_admin_auth_accepts_configured_key(monkeypatch):
    monkeypatch.setattr(settings, "admin_key", "configured-secret")

    asyncio.run(require_admin("Bearer configured-secret"))
