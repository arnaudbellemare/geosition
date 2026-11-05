from __future__ import annotations

import secrets

from fastapi import Header, HTTPException, status

from . import meter
from .config import settings

_PLACEHOLDER_ADMIN_KEYS = {"", "change-me-in-production"}


async def require_api_key(authorization: str = Header(...)) -> str:
    """FastAPI dependency. Returns the validated API key string."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    key = authorization.removeprefix("Bearer ").strip()
    row = await meter.get_key(key)
    if row is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return key


async def require_admin(authorization: str = Header(...)) -> None:
    """FastAPI dependency for admin-only routes."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    if settings.admin_key.strip() in _PLACEHOLDER_ADMIN_KEYS:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Admin key is not configured")
    key = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(key, settings.admin_key):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
