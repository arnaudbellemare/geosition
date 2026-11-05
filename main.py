"""Deployment entrypoint for FastAPI auto-detection."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_SRC = _ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from geo_optimizer.web.app import app  # noqa: E402

__all__ = ["app"]
