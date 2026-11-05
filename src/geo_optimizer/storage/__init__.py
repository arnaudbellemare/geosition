"""Storage backends: local MVP, Supabase (production), Fil One / S3 (blobs)."""

from __future__ import annotations

from geo_optimizer.storage.artifacts import ArtifactStore, get_artifact_store
from geo_optimizer.storage.paths import resolve_collection_home, resolve_data_dir
from geo_optimizer.storage.platform import get_platform_store

__all__ = [
    "ArtifactStore",
    "get_artifact_store",
    "get_platform_store",
    "resolve_collection_home",
    "resolve_data_dir",
]
