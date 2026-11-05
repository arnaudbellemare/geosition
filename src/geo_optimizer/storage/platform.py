"""Platform store factory: SQLite (MVP) or Supabase Postgres (production)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Union

from geo_optimizer.storage.paths import resolve_platform_db_path

if TYPE_CHECKING:
    from geo_optimizer.saas.store import PlatformStore
    from geo_optimizer.saas.supabase_store import SupabasePlatformStore

PlatformStoreLike = Union["PlatformStore", "SupabasePlatformStore"]
_LOGGER = logging.getLogger(__name__)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _supabase_configured() -> bool:
    base = os.environ.get("SUPABASE_URL", os.environ.get("NEXT_PUBLIC_SUPABASE_URL", "")).strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    return bool(base and key)


def get_platform_store(db_path: Path | None = None):
    """Return active platform persistence backend."""
    configured_backend = os.environ.get("GEO_PLATFORM_BACKEND", "").strip().lower()
    backend = configured_backend or "sqlite"
    if not configured_backend and _truthy_env("VERCEL"):
        if _supabase_configured():
            backend = "supabase"
        else:
            _LOGGER.warning(
                "Vercel platform storage is using SQLite under /tmp because Supabase is not configured. "
                "Signup/login will work, but data can be lost on serverless cold starts. Set SUPABASE_URL "
                "or NEXT_PUBLIC_SUPABASE_URL plus SUPABASE_SERVICE_ROLE_KEY for durable production auth.",
            )
    if backend == "supabase":
        from geo_optimizer.saas.supabase_store import SupabasePlatformStore

        return SupabasePlatformStore()
    from geo_optimizer.saas.store import PlatformStore

    path = db_path or resolve_platform_db_path()
    return PlatformStore(path)
