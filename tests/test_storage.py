"""Tests for storage tier configuration."""

from __future__ import annotations

import json

import pytest

from geo_optimizer.core.benchmark.store import BenchmarkStore
from geo_optimizer.saas.store import PlatformStore
from geo_optimizer.storage.artifacts import LocalArtifactStore, get_artifact_store
from geo_optimizer.storage.paths import (
    resolve_benchmark_db_path,
    resolve_data_dir,
    resolve_platform_db_path,
    s3_object_key,
)
from geo_optimizer.storage.platform import get_platform_store


def test_resolve_data_dir_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    data = tmp_path / "data"
    data.mkdir()
    monkeypatch.setenv("GEO_DATA_DIR", str(data))
    assert resolve_data_dir() == data
    assert resolve_platform_db_path() == data / "platform.db"


def test_resolve_data_dir_vercel_uses_tmp(tmp_path, monkeypatch):
    monkeypatch.delenv("GEO_DATA_DIR", raising=False)
    monkeypatch.delenv("GEO_USE_REPO_DATA", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    assert resolve_data_dir() == tmp_path / "geosition"
    assert resolve_platform_db_path() == tmp_path / "geosition" / "platform.db"
    assert resolve_benchmark_db_path() == tmp_path / "geosition" / "benchmark.db"


def test_sqlite_stores_default_to_vercel_tmp(tmp_path, monkeypatch):
    monkeypatch.delenv("GEO_PLATFORM_DB", raising=False)
    monkeypatch.delenv("GEO_BENCHMARK_DB", raising=False)
    monkeypatch.delenv("GEO_DATA_DIR", raising=False)
    monkeypatch.delenv("GEO_USE_REPO_DATA", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    platform_store = PlatformStore()
    benchmark_store = BenchmarkStore()

    assert platform_store.db_path == tmp_path / "geosition" / "platform.db"
    assert benchmark_store.db_path == tmp_path / "geosition" / "benchmark.db"


def test_local_artifact_store_uri(tmp_path):
    store = LocalArtifactStore(tmp_path / "collection")
    uri = store.save_json("orgs/test/raw/run1/file.json", {"ok": True}, run_id="run1")
    assert uri.startswith("file://")
    loaded = json.loads(store.read_text(uri))
    assert loaded["ok"] is True


def test_local_artifact_store_rejects_path_traversal(tmp_path):
    store = LocalArtifactStore(tmp_path / "collection")
    outside = tmp_path / "outside.txt"

    with pytest.raises(ValueError, match="relative path"):
        store.save_text("../outside.txt", "nope")

    with pytest.raises(ValueError, match="relative path"):
        store.read_text("../outside.txt")

    with pytest.raises(ValueError, match="escapes"):
        store.read_text(f"file://{outside}")

    assert not outside.exists()


def test_get_artifact_store_defaults_local():
    store = get_artifact_store()
    assert store.scheme == "file"


def test_get_artifact_store_s3_requires_config(monkeypatch):
    monkeypatch.setenv("GEO_ARTIFACT_BACKEND", "s3")
    monkeypatch.delenv("GEO_S3_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="GEO_S3"):
        get_artifact_store()


def test_s3_object_key_sanitizes_segments():
    key = s3_object_key(
        org_slug="../Acme/Team",
        category="../raw",
        run_id="../run/one",
        filename="../secret.json",
    )

    assert key == "orgs/acme-team/raw/run-one/secret.json"
    assert ".." not in key


def test_platform_store_sqlite_default(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GEO_PLATFORM_BACKEND", "sqlite")
    store = get_platform_store()
    from geo_optimizer.saas.store import PlatformStore

    assert isinstance(store, PlatformStore)
    assert store.db_path == tmp_path / "platform.db"


def test_platform_store_vercel_uses_supabase_when_configured(monkeypatch):
    monkeypatch.delenv("GEO_PLATFORM_BACKEND", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")

    from geo_optimizer.saas import supabase_store

    class FakeSupabasePlatformStore:
        pass

    monkeypatch.setattr(supabase_store, "SupabasePlatformStore", FakeSupabasePlatformStore)

    assert isinstance(get_platform_store(), FakeSupabasePlatformStore)


def test_platform_store_vercel_without_supabase_falls_back_to_sqlite(tmp_path, monkeypatch):
    monkeypatch.delenv("GEO_PLATFORM_BACKEND", raising=False)
    monkeypatch.delenv("GEO_DATA_DIR", raising=False)
    monkeypatch.delenv("GEO_PLATFORM_DB", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("TMPDIR", str(tmp_path))

    store = get_platform_store()

    assert isinstance(store, PlatformStore)
    assert store.db_path == tmp_path / "geosition" / "platform.db"


def test_platform_store_explicit_supabase_requires_config(monkeypatch):
    monkeypatch.setenv("GEO_PLATFORM_BACKEND", "supabase")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("NEXT_PUBLIC_SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)

    with pytest.raises(RuntimeError, match="SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"):
        get_platform_store()


def test_platform_store_explicit_sqlite_wins_on_vercel(tmp_path, monkeypatch):
    monkeypatch.setenv("GEO_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("GEO_PLATFORM_BACKEND", "sqlite")
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")

    store = get_platform_store()

    assert isinstance(store, PlatformStore)
    assert store.db_path == tmp_path / "platform.db"
