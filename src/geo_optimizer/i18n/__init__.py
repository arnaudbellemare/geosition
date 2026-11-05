"""
Internationalization (i18n) for GEOSITION.

Uses Python standard library gettext. Output language auto-detected from the
audited site's HTML lang attribute and URL path.  Can be overridden with
``--lang`` or the ``GEO_LANG`` environment variable.

Language configuration priority:
    1. ``--lang`` CLI flag (explicit override)
    2. ``GEO_LANG`` environment variable
    3. Auto-detected from ``<html lang="...">`` attribute of the audited page
    4. Auto-detected from URL path (``/fr/``, ``/en/``)
    5. Default: ``en``
"""

from __future__ import annotations

import gettext
import os
import re
from pathlib import Path

# Directory containing .mo translation files
LOCALES_DIR = Path(__file__).parent / "locales"

# Default language (fallback when nothing else can be determined)
DEFAULT_LANG = "en"

# Supported output languages
SUPPORTED_LANGS = {"en", "fr", "it"}

# Global translation instance
_current_translation = None

# Tracks the currently active language code
_current_lang: str = DEFAULT_LANG

# True once the user explicitly passed --lang or GEO_LANG
_lang_explicitly_set = False


def _map_lang_code(raw: str) -> str:
    """Map an arbitrary HTML/HTTP lang tag to a supported code."""
    raw = raw.lower().strip()
    if raw.startswith("fr"):
        return "fr"
    if raw.startswith("it"):
        return "it"
    if raw.startswith("en"):
        return "en"
    return DEFAULT_LANG


def get_lang() -> str:
    """Determine the current language from GEO_LANG env var or default."""
    lang = os.environ.get("GEO_LANG", DEFAULT_LANG).lower()
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    return lang


def setup_i18n(lang: str | None = None) -> gettext.GNUTranslations:
    """Initialize the i18n system for the specified language.

    Args:
        lang: Language code (en, fr, it). If None, uses get_lang().

    Returns:
        GNUTranslations object (or NullTranslations if .mo file is missing).
    """
    global _current_translation, _current_lang

    if lang is None:
        lang = get_lang()

    try:
        translation = gettext.translation(
            "geo_optimizer",
            localedir=str(LOCALES_DIR),
            languages=[lang],
        )
    except FileNotFoundError:
        # No .mo file yet — pass strings through unchanged
        translation = gettext.NullTranslations()

    _current_translation = translation
    _current_lang = lang
    return translation


def _(message: str) -> str:
    """Translate a message into the current language."""
    global _current_translation

    if _current_translation is None:
        setup_i18n()

    return _current_translation.gettext(message)


def set_lang(lang: str) -> None:
    """Explicitly set the output language (called from --lang flag or GEO_LANG)."""
    global _lang_explicitly_set
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    setup_i18n(lang)
    _lang_explicitly_set = True


def auto_detect_lang(html_lang: str = "", url: str = "") -> str:
    """Auto-detect and apply the output language from the audited page.

    No-op if the user already passed ``--lang`` or set ``GEO_LANG``.
    Detection priority:
        1. ``<html lang="...">`` attribute value (*html_lang* param)
        2. URL path prefix (``/fr/``, ``/en/``, ``/it/``)
        3. Keep current default (``en``)

    Returns the detected language code.
    """
    global _lang_explicitly_set

    if _lang_explicitly_set:
        return get_lang()

    lang: str | None = None

    # 1. HTML lang attribute is the most reliable signal
    if html_lang:
        lang = _map_lang_code(html_lang)

    # 2. URL path prefix (/fr/, /en/, /it/, or fr.example.com subdomain)
    if not lang and url:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        path = parsed.path.lower()
        host = parsed.hostname or ""
        # Path-based: /fr/, /fr-ca/, /en/, /it/
        m = re.match(r"^/(fr|en|it)[/-]", path) or re.match(r"^/(fr|en|it)$", path)
        if m:
            lang = m.group(1)
        # Subdomain-based: fr.example.com, en.example.com
        elif re.match(r"^(fr|en|it)\.", host):
            lang = host.split(".")[0]

    if lang and lang in SUPPORTED_LANGS:
        setup_i18n(lang)
        return lang

    return get_lang()
