"""
Local HTTP cache on filesystem.

Saves HTTP responses in ``~/.geo-cache/`` to avoid repeated fetches
during development. Disabled by default, enabled with ``--cache``.

Usage:
    geo audit --url https://example.com --cache
    geo audit --url https://example.com --clear-cache
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path

# Cache directory in the user's home for local CLI use.
CACHE_DIR = Path.home() / ".geo-cache"

# Default TTL: 1 hour
DEFAULT_TTL = 3600

# Disk cache size limit: 500 MB (fix #192)
MAX_CACHE_SIZE_BYTES = 500 * 1024 * 1024


class FileCache:
    """HTTP cache on filesystem with TTL."""

    def __init__(self, cache_dir: Path | None = None, ttl: int = DEFAULT_TTL):
        env_cache_dir = os.environ.get("GEO_CACHE_DIR", "").strip()
        self.cache_dir = cache_dir or (Path(env_cache_dir) if env_cache_dir else CACHE_DIR)
        self.ttl = ttl
        self._fallback_dir = Path(tempfile.gettempdir()) / "geosition-cache"

    def _key(self, url: str) -> str:
        """Generate cache key from URL (SHA-256 hash)."""
        return hashlib.sha256(url.encode()).hexdigest()

    def _path(self, url: str) -> Path:
        """Cache file path for a URL."""
        return self.cache_dir / f"{self._key(url)}.json"

    def get(self, url: str) -> tuple[int, str, dict] | None:
        """Retrieve response from cache if valid.

        Returns:
            Tuple (status_code, text, headers) or None if not cached/expired.
        """
        path = self._path(url)
        try:
            if not path.exists():
                return None
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

        # Check TTL
        cached_at = data.get("cached_at", 0)
        if time.time() - cached_at > self.ttl:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None

        return (
            data.get("status_code", 200),
            data.get("text", ""),
            data.get("headers", {}),
        )

    def put(self, url: str, status_code: int, text: str, headers: dict) -> None:
        """Save response to cache. Evicts oldest if over disk limit (fix #192)."""
        if not self._ensure_cache_dir():
            return

        # Evict oldest entries if cache exceeds disk limit
        self._evict_if_needed()

        data = {
            "url": url,
            "status_code": status_code,
            "text": text,
            "headers": dict(headers),
            "cached_at": time.time(),
        }

        path = self._path(url)
        try:
            path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        except OSError:
            return

    def _ensure_cache_dir(self) -> bool:
        """Ensure the cache directory is writable, falling back to system temp."""
        for path in (self.cache_dir, self._fallback_dir):
            try:
                path.mkdir(parents=True, exist_ok=True)
                probe = path / ".write-test"
                probe.write_text("", encoding="utf-8")
                probe.unlink(missing_ok=True)
                self.cache_dir = path
                return True
            except OSError:
                continue
        return False

    def _evict_if_needed(self) -> None:
        """Remove oldest cache entries if total size exceeds MAX_CACHE_SIZE_BYTES."""
        try:
            if not self.cache_dir.exists():
                return
            files = sorted(self.cache_dir.glob("*.json"), key=lambda f: f.stat().st_mtime)
            total_size = sum(f.stat().st_size for f in files)
        except OSError:
            return

        while total_size > MAX_CACHE_SIZE_BYTES and files:
            oldest = files.pop(0)
            try:
                # Fix TOCTOU #212: reads the size before unlink;
                # if the file disappears between stat() and unlink(), the exception
                # is handled without subtracting an incorrect size from total_size
                file_size = oldest.stat().st_size
                oldest.unlink(missing_ok=True)
                total_size -= file_size
            except (FileNotFoundError, OSError):
                pass  # File already removed by another process, skip

    def clear(self) -> int:
        """Clear the entire cache. Returns the number of files removed."""
        try:
            if not self.cache_dir.exists():
                return 0
            count = sum(1 for _ in self.cache_dir.glob("*.json"))
            shutil.rmtree(self.cache_dir)
        except OSError:
            return 0
        return count

    def stats(self) -> dict:
        """Cache statistics: file count, total size."""
        try:
            if not self.cache_dir.exists():
                return {"files": 0, "size_bytes": 0}
            files = list(self.cache_dir.glob("*.json"))
            total_size = sum(f.stat().st_size for f in files)
        except OSError:
            return {"files": 0, "size_bytes": 0}
        return {"files": len(files), "size_bytes": total_size}
