"""Resolve data directories for MVP (repo data/) vs production paths."""

from __future__ import annotations

import os
import re
from pathlib import Path

from geo_optimizer.models.config import GEO_OPTIMIZER_HOME

_S3_SEGMENT_RE = re.compile(r"[^a-zA-Z0-9._=-]+")


def resolve_data_dir() -> Path:
    """Primary data root: GEO_DATA_DIR, else ./data if present, else ~/.geo-optimizer."""
    explicit = os.environ.get("GEO_DATA_DIR", "").strip()
    if explicit:
        path = Path(explicit)
        path.mkdir(parents=True, exist_ok=True)
        return path

    if os.environ.get("VERCEL", "").strip().lower() in ("1", "true", "yes"):
        path = Path(os.environ.get("TMPDIR", "/tmp")) / "geosition"
        path.mkdir(parents=True, exist_ok=True)
        return path

    cwd_data = Path.cwd() / "data"
    if cwd_data.is_dir() or os.environ.get("GEO_USE_REPO_DATA", "").lower() in ("1", "true", "yes"):
        cwd_data.mkdir(parents=True, exist_ok=True)
        return cwd_data

    GEO_OPTIMIZER_HOME.mkdir(parents=True, exist_ok=True)
    return GEO_OPTIMIZER_HOME


def resolve_collection_home() -> Path:
    """Collection artifacts: under data dir when MVP, or override via GEO_COLLECTION_HOME."""
    override = os.environ.get("GEO_COLLECTION_HOME", "").strip()
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    path = resolve_data_dir() / "collection"
    path.mkdir(parents=True, exist_ok=True)
    return path


def resolve_platform_db_path() -> Path:
    """Platform SQLite path under data dir."""
    override = os.environ.get("GEO_PLATFORM_DB", "").strip()
    if override:
        return Path(override)
    return resolve_data_dir() / "platform.db"


def resolve_benchmark_db_path() -> Path:
    """Benchmark SQLite path under data dir."""
    override = os.environ.get("GEO_BENCHMARK_DB", "").strip()
    if override:
        return Path(override)
    return resolve_data_dir() / "benchmark.db"


def s3_object_key(
    *,
    org_slug: str,
    run_id: str,
    filename: str,
    category: str = "raw",
) -> str:
    """Canonical S3 key for Fil One / S3-compatible storage."""
    safe_org = _safe_s3_segment(org_slug, fallback="default").lower()
    safe_run = _safe_s3_segment(run_id, fallback="run")
    safe_category = _safe_s3_segment(category, fallback="raw").lower()
    safe_filename = _safe_s3_segment(Path(filename).name, fallback="artifact")
    return f"orgs/{safe_org}/{safe_category}/{safe_run}/{safe_filename}"


def _safe_s3_segment(value: str, *, fallback: str) -> str:
    """Return one safe S3 key segment with path separators removed."""
    cleaned = _S3_SEGMENT_RE.sub("-", value.strip()).strip(".-_/")
    return cleaned[:120] or fallback
