"""Artifact storage: local filesystem (MVP) or S3-compatible (Fil One)."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import cast

from geo_optimizer.storage.paths import resolve_collection_home, s3_object_key


class ArtifactStore(ABC):
    """Store raw answers, reports, and exports."""

    scheme: str = "file"

    @abstractmethod
    def save_json(self, key: str, payload: object, *, run_id: str = "") -> str:
        """Persist JSON; return storage URI (file:// or s3://)."""

    @abstractmethod
    def save_text(self, key: str, text: str, *, content_type: str = "text/plain") -> str:
        """Persist text blob; return storage URI."""

    @abstractmethod
    def read_text(self, uri: str) -> str:
        """Load text by URI returned from save_*."""

    def save_raw_collection(
        self,
        run_id: str,
        *,
        org_slug: str = "default",
        provider: str,
        prompt_id: str,
        payload: object,
    ) -> str:
        """Save collection raw payload with standard key layout."""
        filename = f"{provider}_{prompt_id or 'prompt'}.json"
        key = s3_object_key(org_slug=org_slug, run_id=run_id, filename=filename, category="raw")
        return self.save_json(key, payload, run_id=run_id)


class LocalArtifactStore(ArtifactStore):
    """MVP: files under data/collection/ or GEO_COLLECTION_HOME."""

    scheme = "file"

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or resolve_collection_home()

    def _resolve_under_base(self, key: str) -> Path:
        """Resolve a storage key and ensure it stays under the artifact root."""
        relative = Path(key)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Artifact key must be a relative path inside the artifact store")
        path = (self.base_dir / relative).resolve()
        base = self.base_dir.resolve()
        try:
            path.relative_to(base)
        except ValueError as exc:
            raise ValueError("Artifact key escapes the artifact store") from exc
        return path

    def _path_for_key(self, key: str, run_id: str = "") -> Path:
        if run_id:
            path = self._resolve_under_base(str(Path("raw") / run_id / Path(key).name))
        else:
            path = self._resolve_under_base(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, key: str, payload: object, *, run_id: str = "") -> str:
        path = self._path_for_key(key, run_id)
        path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        return f"file://{path.resolve()}"

    def save_text(self, key: str, text: str, *, content_type: str = "text/plain") -> str:
        path = self._path_for_key(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return f"file://{path.resolve()}"

    def read_text(self, uri: str) -> str:
        if uri.startswith("file://"):
            path = Path(uri[7:]).resolve()
            base = self.base_dir.resolve()
            try:
                path.relative_to(base)
            except ValueError as exc:
                raise ValueError("Artifact URI escapes the artifact store") from exc
            return path.read_text(encoding="utf-8")
        path = self._path_for_key(uri)
        return path.read_text(encoding="utf-8")


class S3ArtifactStore(ArtifactStore):
    """Production blobs: Fil One or any S3-compatible endpoint."""

    scheme = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        region: str = "auto",
        prefix: str = "",
    ):
        self.bucket = bucket
        self.endpoint_url = endpoint_url.rstrip("/")
        self.access_key = access_key
        self.secret_key = secret_key
        self.region = region
        self.prefix = prefix.strip("/")

    def _client(self):
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("Install boto3 for S3/Fil One storage: pip install geosition[storage]") from exc

        return boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region,
            config=Config(signature_version="s3v4"),
        )

    def _full_key(self, key: str) -> str:
        if self.prefix:
            return f"{self.prefix}/{key.lstrip('/')}"
        return key.lstrip("/")

    def save_json(self, key: str, payload: object, *, run_id: str = "") -> str:
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        return self._put(self._full_key(key), body, content_type="application/json")

    def save_text(self, key: str, text: str, *, content_type: str = "text/plain") -> str:
        return self._put(self._full_key(key), text.encode("utf-8"), content_type=content_type)

    def _put(self, key: str, body: bytes, *, content_type: str) -> str:
        client = self._client()
        client.put_object(Bucket=self.bucket, Key=key, Body=body, ContentType=content_type)
        return f"s3://{self.bucket}/{key}"

    def read_text(self, uri: str) -> str:
        if not uri.startswith("s3://"):
            raise ValueError(f"Not an s3 URI: {uri}")
        remainder = uri[5:]
        bucket, _, key = remainder.partition("/")
        client = self._client()
        response = client.get_object(Bucket=bucket, Key=key)
        return cast(str, response["Body"].read().decode("utf-8"))


def get_artifact_store() -> ArtifactStore:
    """Select artifact backend from GEO_ARTIFACT_BACKEND (local | s3)."""
    backend = os.environ.get("GEO_ARTIFACT_BACKEND", "local").strip().lower()
    if backend == "s3":
        bucket = os.environ.get("GEO_S3_BUCKET", os.environ.get("FIL_ONE_BUCKET", "")).strip()
        endpoint = os.environ.get("GEO_S3_ENDPOINT", os.environ.get("FIL_ONE_ENDPOINT", "")).strip()
        access = os.environ.get("GEO_S3_ACCESS_KEY", os.environ.get("FIL_ONE_ACCESS_KEY", "")).strip()
        secret = os.environ.get("GEO_S3_SECRET_KEY", os.environ.get("FIL_ONE_SECRET_KEY", "")).strip()
        region = os.environ.get("GEO_S3_REGION", "auto").strip()
        prefix = os.environ.get("GEO_S3_PREFIX", "geo-platform").strip()
        if not all([bucket, endpoint, access, secret]):
            raise RuntimeError(
                "S3 artifact backend requires GEO_S3_BUCKET, GEO_S3_ENDPOINT, "
                "GEO_S3_ACCESS_KEY, GEO_S3_SECRET_KEY (or FIL_ONE_* aliases)"
            )
        return S3ArtifactStore(
            bucket=bucket,
            endpoint_url=endpoint,
            access_key=access,
            secret_key=secret,
            region=region,
            prefix=prefix,
        )
    return LocalArtifactStore()


def get_optional_artifact_store() -> ArtifactStore | None:
    """Return S3 store only when configured; None keeps local-only."""
    if os.environ.get("GEO_ARTIFACT_BACKEND", "").strip().lower() != "s3":
        return None
    return get_artifact_store()
