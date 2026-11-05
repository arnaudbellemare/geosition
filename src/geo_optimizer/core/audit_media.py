"""
Media optimization audit — v1.0

Checks video and audio elements for mobile load performance:
- Format compatibility (mp4/webm for video, mp3/ogg for audio)
- File size via HEAD request (flag > 5 MB video, > 2 MB audio)
- Lazy loading (loading="lazy" or Intersection Observer pattern)
- Poster images on <video> (prevents layout shift on mobile)
- Autoplay without muted (blocked by iOS/Android browsers)
- Missing width/height dimensions (causes CLS / layout shift)

Score: starts at 100, deductions per issue type.
"""

from __future__ import annotations

from urllib.parse import urljoin, urlparse

from geo_optimizer.models.results import MediaAsset, MediaResult

_VIDEO_EXTS = {".mp4", ".webm", ".ogv", ".mov", ".avi", ".mkv"}
_AUDIO_EXTS = {".mp3", ".ogg", ".wav", ".aac", ".m4a", ".flac", ".opus"}

# Threshold sizes for "large" warnings
_VIDEO_MAX_BYTES = 5 * 1024 * 1024  # 5 MB  (general)
_VIDEO_MOBILE_MAX_BYTES = 3 * 1024 * 1024  # 3 MB  (mobile-targeted source)
_AUDIO_MAX_BYTES = 2 * 1024 * 1024  # 2 MB


def _ext(url: str) -> str:
    path = urlparse(url).path.lower()
    return "." + path.rsplit(".", 1)[-1] if "." in path else ""


def _media_type_from_ext(ext: str) -> tuple[str, str]:
    """Return (media_type, format) from file extension."""
    if ext in _VIDEO_EXTS:
        return "video", ext.lstrip(".")
    if ext in _AUDIO_EXTS:
        return "audio", ext.lstrip(".")
    return "unknown", "unknown"


def _fetch_size(url: str) -> int:
    """Return Content-Length in bytes from HEAD request, -1 on failure."""
    try:
        import requests

        from geo_optimizer.utils.http import create_session_with_retry
        from geo_optimizer.utils.validators import resolve_and_validate_url

        ok, _reason, pinned_ips = resolve_and_validate_url(url)
        if not ok:
            return -1
        session = create_session_with_retry(total_retries=1, pinned_ips=pinned_ips)
        try:
            r = session.head(
                url,
                timeout=6,
                allow_redirects=False,
                headers={"User-Agent": "geo-optimizer/4.13"},
            )
        finally:
            session.close()
        cl = r.headers.get("Content-Length", "")
        return int(cl) if cl.isdigit() else -1
    except requests.exceptions.RequestException:
        return -1


def audit_media(soup, base_url: str) -> MediaResult:
    """Audit <video> and <audio> elements on the page for mobile optimization."""
    if soup is None:
        return MediaResult(checked=False)

    result = MediaResult(checked=True)
    assets: list[MediaAsset] = []

    # ── Collect <video> elements ───────────────────────────────────────────────
    for tag in soup.find_all("video"):
        asset = MediaAsset(media_type="video")

        # Inspect all <source> children for responsive variants and WebM fallback
        sources = tag.find_all("source")
        asset.has_responsive_sources = any(s.get("media") for s in sources)
        asset.has_webm_source = any(
            (s.get("type", "").lower() == "video/webm" or _ext(s.get("src", "")).lower() == ".webm") for s in sources
        )

        # Determine URL: src attr or first <source> child
        src = tag.get("src", "")
        if not src:
            source = sources[0] if sources else None
            src = source.get("src", "") if source else ""

        if src:
            asset.url = urljoin(base_url, src) if not src.startswith("http") else src
            ext = _ext(asset.url)
            _, asset.format = _media_type_from_ext(ext)
        else:
            asset.url = ""
            asset.format = "unknown"

        # Attributes
        asset.has_poster = bool(tag.get("poster", ""))
        asset.autoplay_unmuted = tag.has_attr("autoplay") and not tag.has_attr("muted")
        asset.has_dimensions = bool(tag.get("width")) and bool(tag.get("height"))

        # loading="lazy" on video is non-standard but some browsers honour it;
        # also check for data-src (lazy libraries) or Intersection Observer pattern
        asset.has_lazy_load = tag.get("loading") == "lazy" or bool(tag.get("data-src")) or bool(tag.get("data-lazy"))

        # Size check (only for absolute / resolvable URLs, skip data: URIs)
        if asset.url and not asset.url.startswith("data:"):
            asset.size_bytes = _fetch_size(asset.url)

        assets.append(asset)
        result.video_count += 1

        if asset.size_bytes > _VIDEO_MAX_BYTES:
            result.large_videos += 1
        if not asset.has_lazy_load:
            result.missing_lazy += 1
        if not asset.has_poster:
            result.missing_poster += 1
        if asset.autoplay_unmuted:
            result.autoplay_unmuted += 1
        if asset.format not in ("mp4", "webm", "ogv", "unknown"):
            result.non_mp4_videos += 1
        if not asset.has_responsive_sources:
            result.missing_responsive_sources += 1
        if not asset.has_webm_source and asset.format in ("mp4", "unknown"):
            result.no_webm_fallback += 1

    # ── Collect <audio> elements ───────────────────────────────────────────────
    for tag in soup.find_all("audio"):
        asset = MediaAsset(media_type="audio")

        src = tag.get("src", "")
        if not src:
            source = tag.find("source")
            src = source.get("src", "") if source else ""

        if src:
            asset.url = urljoin(base_url, src) if not src.startswith("http") else src
            ext = _ext(asset.url)
            _, asset.format = _media_type_from_ext(ext)
        else:
            asset.url = ""
            asset.format = "unknown"

        asset.has_lazy_load = tag.get("loading") == "lazy" or bool(tag.get("data-src"))
        asset.has_dimensions = True  # audio has no dimensions

        if asset.url and not asset.url.startswith("data:"):
            asset.size_bytes = _fetch_size(asset.url)

        assets.append(asset)
        result.audio_count += 1

        if asset.size_bytes > _AUDIO_MAX_BYTES:
            result.large_audios += 1

    # ── Scan <source> tags outside <video>/<audio> (picture elements etc.) ────
    # Also scan for video URLs in <a href> or background CSS as a heuristic
    for tag in soup.find_all("a", href=True):
        href = tag["href"]
        ext = _ext(href)
        if ext in _VIDEO_EXTS or ext in _AUDIO_EXTS:
            mt, fmt = _media_type_from_ext(ext)
            asset = MediaAsset(
                url=urljoin(base_url, href) if not href.startswith("http") else href,
                media_type=mt,
                format=fmt,
                has_lazy_load=False,
                has_poster=False,
            )
            assets.append(asset)
            if mt == "video":
                result.video_count += 1
            else:
                result.audio_count += 1

    result.assets = assets

    # ── Issues ────────────────────────────────────────────────────────────────
    if result.video_count == 0 and result.audio_count == 0:
        # No media found — that's fine, but note it
        result.issues = []
        result.suggestions = [
            "No video or audio detected. Adding a product demo video can increase conversion by 20-80%."
        ]
        result.media_score = 100
        return result

    if result.large_videos:
        result.issues.append(
            f"{result.large_videos} video(s) exceed 5 MB — compress to H.264 MP4 "
            f"at 720p/30fps for mobile. Target: < 3 MB per clip."
        )
    if result.missing_poster:
        result.issues.append(
            f"{result.missing_poster} video(s) missing poster= attribute — "
            "mobile devices show a blank frame until the video loads."
        )
    if result.autoplay_unmuted:
        result.issues.append(
            f"{result.autoplay_unmuted} video(s) use autoplay without muted — "
            "iOS and Android browsers block unmuted autoplay. Add the muted attribute."
        )
    if result.missing_lazy:
        result.issues.append(
            f"{result.missing_lazy} video(s) not lazy-loaded — "
            "load the above-fold video eagerly, use loading='lazy' or data-src for others."
        )
    if result.large_audios:
        result.issues.append(
            f"{result.large_audios} audio file(s) exceed 2 MB — "
            "convert to MP3 128 kbps or Opus 96 kbps for web delivery."
        )
    if result.non_mp4_videos:
        result.issues.append(
            f"{result.non_mp4_videos} video(s) are not MP4/WebM — "
            "use H.264 MP4 as primary, WebM as fallback: "
            "<source src='video.webm' type='video/webm'><source src='video.mp4' type='video/mp4'>."
        )
    if result.no_webm_fallback:
        result.issues.append(
            f"{result.no_webm_fallback} video(s) have no WebM fallback source — "
            "WebM (VP9) is 25-40% smaller than H.264 MP4 and plays natively on Android Chrome. "
            "Add: <source src='video.webm' type='video/webm'> before the MP4 source."
        )
    if result.missing_responsive_sources:
        result.issues.append(
            f"{result.missing_responsive_sources} video(s) serve the same file to mobile and desktop — "
            "mobile visitors on 4G download the full desktop-sized video. "
            "Use <source media='(max-width: 767px)' src='video-mobile.mp4'> to serve a smaller clip "
            "(target < 3 MB) on phones, and the full version on desktop."
        )

    result.suggestions = [
        "Recommended pipeline: HandBrake → H.264 MP4, CRF 23, 720p, AAC 128 kbps. Target < 3 MB.",
        "For audio: use FFmpeg → MP3 128 kbps (broad compat) + Opus 96 kbps (smaller file).",
        "Add <video poster='thumb.jpg' muted playsinline preload='none'> for every video.",
        "Test on 4G: use Chrome DevTools → Throttle → Fast 3G before launch.",
    ]

    # ── Score ─────────────────────────────────────────────────────────────────
    score = 100
    if result.large_videos:
        score -= min(30, result.large_videos * 15)
    if result.missing_poster:
        score -= min(20, result.missing_poster * 10)
    if result.autoplay_unmuted:
        score -= min(20, result.autoplay_unmuted * 10)
    if result.missing_lazy:
        score -= min(15, result.missing_lazy * 5)
    if result.large_audios:
        score -= min(10, result.large_audios * 5)
    if result.non_mp4_videos:
        score -= min(15, result.non_mp4_videos * 5)
    if result.no_webm_fallback:
        score -= min(10, result.no_webm_fallback * 5)
    if result.missing_responsive_sources:
        score -= min(10, result.missing_responsive_sources * 5)
    result.media_score = max(0, score)

    return result
