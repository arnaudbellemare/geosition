"""Persist raw collection payloads before normalization."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from geo_optimizer.storage.paths import resolve_collection_home

if TYPE_CHECKING:
    from geo_optimizer.storage.artifacts import ArtifactStore

COLLECTION_HOME = resolve_collection_home()
PARSER_VERSION = "1.0.0"
_SAFE_SEGMENT_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_collection_run_id() -> str:
    """Generate a unique collection run identifier."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid4().hex[:8]}"


def _safe_segment(value: str, *, fallback: str) -> str:
    """Return a filesystem-safe single path segment."""
    cleaned = _SAFE_SEGMENT_RE.sub("-", str(value or "")).strip(".-_")
    return cleaned[:120] or fallback


class CollectionArtifactStore:
    """Filesystem store for raw API/scrape responses and rendered evidence."""

    def __init__(self, base_dir: Path | None = None, *, org_slug: str = "default"):
        self.org_slug = org_slug
        self.base_dir = base_dir or COLLECTION_HOME
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._remote: ArtifactStore | None = None
        try:
            from geo_optimizer.storage.artifacts import get_artifact_store

            self._remote = get_artifact_store()
            if self._remote.scheme != "s3":
                self._remote = None
        except Exception:
            self._remote = None

    def run_dir(self, run_id: str) -> Path:
        path = self.base_dir / "raw" / _safe_segment(run_id, fallback="run")
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_raw(
        self,
        run_id: str,
        *,
        provider: str,
        prompt_id: str,
        payload: object,
        suffix: str = "json",
    ) -> str:
        """Save raw payload; return relative path from collection home."""
        directory = self.run_dir(run_id)
        safe_provider = _safe_segment(provider, fallback="provider")
        safe_id = _safe_segment(prompt_id, fallback="prompt")
        safe_suffix = _safe_segment(suffix, fallback="txt")
        filename = f"{safe_provider}_{safe_id}.{safe_suffix}"
        path = directory / filename
        path.relative_to(directory)
        if suffix == "json":
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        else:
            path.write_text(str(payload), encoding="utf-8")
        rel = str(path.relative_to(self.base_dir))
        if self._remote is not None:
            uri = self._remote.save_raw_collection(
                run_id,
                org_slug=self.org_slug,
                provider=provider,
                prompt_id=prompt_id,
                payload=payload,
            )
            return uri
        return rel

    def save_rendered_html(self, run_id: str, provider: str, prompt_id: str, html: str) -> str:
        """Store rendered HTML evidence from browser lane."""
        directory = self.run_dir(run_id)
        safe_provider = _safe_segment(provider, fallback="provider")
        safe_id = _safe_segment(prompt_id, fallback="prompt")
        path = directory / f"{safe_provider}_{safe_id}.html"
        path.relative_to(directory)
        path.write_text(html, encoding="utf-8")
        return str(path.relative_to(self.base_dir))
