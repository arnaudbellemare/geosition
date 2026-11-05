"""
GEO Audit — Performance / Core Web Vitals sub-audit (v4.12).

Checks the HTML for static load-speed signals that affect how fast AI crawlers
and browsers can parse the page:

- Images missing width + height  → layout shift (CLS)
- Images missing loading="lazy"  → unnecessary bytes on page load
- <script> without async/defer  → render-blocking JS
- <link rel="stylesheet"> in <head> → render-blocking CSS
- @font-face without font-display:swap → invisible text during load (FOIT)

No JavaScript execution, no network requests — pure HTML static analysis.
Informational check — does not affect GEO score.
"""

from __future__ import annotations

import re

from geo_optimizer.models.results import PerfIssue, PerfResult

# Matches @font-face blocks that do NOT contain font-display:swap
_FONT_FACE_RE = re.compile(r"@font-face\s*\{([^}]*)\}", re.IGNORECASE | re.DOTALL)
_FONT_DISPLAY_SWAP_RE = re.compile(r"font-display\s*:\s*swap", re.IGNORECASE)

# Data URIs and SVG inline are exempt from lazy-loading
_DATA_URI_RE = re.compile(r"^data:", re.IGNORECASE)

# Small decorative images: if no src we can't judge; skip
_SKIP_LAZY_ATTRS = {"loading", "decoding"}


def audit_perf(soup, raw_html: str = "", base_url: str = "") -> PerfResult:
    """Analyze HTML for Core Web Vitals / performance anti-patterns.

    Args:
        soup: BeautifulSoup of the full HTML document.
        raw_html: Raw HTML string (used for @font-face detection in <style> blocks).
        base_url: Page URL (used in issue element snippets).

    Returns:
        PerfResult with counts and individual issues list.
    """
    if soup is None:
        return PerfResult(checked=True)

    issues: list[PerfIssue] = []

    # ── 1. Images missing width + height ──────────────────────────────────────
    imgs_missing_dims = 0
    imgs_missing_lazy = 0

    for img in soup.find_all("img"):
        src = img.get("src", "")
        # Skip inline data URIs (they don't trigger network requests)
        if _DATA_URI_RE.match(src):
            continue

        width = img.get("width")
        height = img.get("height")
        if not width or not height:
            imgs_missing_dims += 1
            snippet = _img_snippet(img)
            issues.append(
                PerfIssue(
                    check="img_missing_dimensions",
                    severity="warning",
                    element=snippet,
                    fix="Add explicit width and height attributes to avoid CLS: "
                    '<img src="..." width="800" height="600" ...>',
                )
            )

        # Lazy-loading: skip if already has loading attr or is above-the-fold (first 3 imgs heuristic)
        loading = img.get("loading", "").lower()
        if loading not in ("lazy", "eager") and not _DATA_URI_RE.match(src):
            imgs_missing_lazy += 1
            issues.append(
                PerfIssue(
                    check="img_missing_lazy",
                    severity="warning",
                    element=_img_snippet(img),
                    fix='Add loading="lazy" to defer off-screen images: <img src="..." loading="lazy" ...>',
                )
            )

    # ── 2. Render-blocking <script> tags ─────────────────────────────────────
    render_blocking_scripts = 0
    head = soup.find("head")

    for script in soup.find_all("script"):
        src = script.get("src")
        if not src:
            continue  # Inline scripts don't block the parser the same way
        has_async = script.has_attr("async")
        has_defer = script.has_attr("defer")
        if not has_async and not has_defer:
            render_blocking_scripts += 1
            issues.append(
                PerfIssue(
                    check="render_blocking_script",
                    severity="error",
                    element=f'<script src="{src[:80]}">',
                    fix=f'Add async or defer: <script src="{src[:60]}" defer>',
                )
            )

    # ── 3. Render-blocking stylesheets ───────────────────────────────────────
    render_blocking_styles = 0
    if head:
        for link in head.find_all("link", rel=lambda r: r and "stylesheet" in (r if isinstance(r, list) else [r])):
            # media="print" stylesheets don't block rendering
            media = link.get("media", "all")
            if media == "print":
                continue
            # preload / prefetch are fine
            rel_list = link.get("rel", [])
            if isinstance(rel_list, str):
                rel_list = [rel_list]
            if "preload" in rel_list or "prefetch" in rel_list:
                continue
            render_blocking_styles += 1
            href = link.get("href", "")
            issues.append(
                PerfIssue(
                    check="render_blocking_stylesheet",
                    severity="warning",
                    element=f'<link rel="stylesheet" href="{href[:80]}">',
                    fix="Load non-critical CSS asynchronously: "
                    '<link rel="preload" as="style" onload="this.rel=\'stylesheet\'">',
                )
            )

    # ── 4. @font-face missing font-display: swap ─────────────────────────────
    missing_font_display = False
    style_texts: list[str] = []
    for style_tag in soup.find_all("style"):
        style_texts.append(style_tag.get_text())
    # Also scan raw HTML for <style> outside BeautifulSoup parse (edge case)
    if raw_html:
        style_texts.append(raw_html)

    combined_style = " ".join(style_texts)
    font_faces = _FONT_FACE_RE.findall(combined_style)
    for ff_body in font_faces:
        if not _FONT_DISPLAY_SWAP_RE.search(ff_body):
            missing_font_display = True
            break

    if missing_font_display:
        issues.append(
            PerfIssue(
                check="missing_font_display_swap",
                severity="warning",
                element="@font-face { ... }",
                fix="Add font-display: swap inside each @font-face block to prevent invisible text (FOIT).",
            )
        )

    # ── Score ─────────────────────────────────────────────────────────────────
    score = _compute_perf_score(
        imgs_missing_dims=imgs_missing_dims,
        imgs_missing_lazy=imgs_missing_lazy,
        render_blocking_scripts=render_blocking_scripts,
        render_blocking_styles=render_blocking_styles,
        missing_font_display=missing_font_display,
    )

    return PerfResult(
        checked=True,
        images_missing_dimensions=imgs_missing_dims,
        images_missing_lazy=imgs_missing_lazy,
        render_blocking_scripts=render_blocking_scripts,
        render_blocking_styles=render_blocking_styles,
        missing_font_display_swap=missing_font_display,
        issues=issues,
        perf_score=score,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _img_snippet(img) -> str:
    src = img.get("src", "")[:60]
    alt = img.get("alt", "")[:30]
    return f'<img src="{src}" alt="{alt}">'


def _compute_perf_score(
    imgs_missing_dims: int,
    imgs_missing_lazy: int,
    render_blocking_scripts: int,
    render_blocking_styles: int,
    missing_font_display: bool,
) -> int:
    """Score 0-100 based on absence of performance anti-patterns."""
    score = 100

    # Render-blocking resources are the most impactful (each -15, cap -30)
    script_penalty = min(render_blocking_scripts * 15, 30)
    style_penalty = min(render_blocking_styles * 10, 20)
    score -= script_penalty + style_penalty

    # Images (softer penalty — many sites have legitimate above-fold images)
    dim_penalty = min(imgs_missing_dims * 3, 15)
    lazy_penalty = min(imgs_missing_lazy * 2, 10)
    score -= dim_penalty + lazy_penalty

    # Font display swap
    if missing_font_display:
        score -= 5

    return max(0, score)
