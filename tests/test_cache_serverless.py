from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from geo_optimizer.utils.cache import FileCache


def test_file_cache_put_falls_back_when_primary_cache_dir_is_read_only(tmp_path):
    primary = tmp_path / "readonly-home-cache"
    fallback = tmp_path / "tmp-cache"
    cache = FileCache(primary)
    cache._fallback_dir = fallback

    original_mkdir = Path.mkdir

    def mkdir_side_effect(path, *args, **kwargs):
        if path == primary:
            raise OSError("Read-only file system")
        return original_mkdir(path, *args, **kwargs)

    with patch.object(Path, "mkdir", autospec=True, side_effect=mkdir_side_effect):
        cache.put("https://example.com", 200, "<html>ok</html>", {"content-type": "text/html"})

    assert cache.cache_dir == fallback
    assert cache.get("https://example.com") == (200, "<html>ok</html>", {"content-type": "text/html"})
