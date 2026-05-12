"""Minimal i18n: load JSON message catalogs and translate by dotted key.

Supports French (fr) and English (en). Locale is detected from the system
once at startup; the user can override via /api/lang (Task 28 in plan-1).
"""

from __future__ import annotations

import json
import locale
from pathlib import Path

SUPPORTED_LANGS: tuple[str, ...] = ("fr", "en")
DEFAULT_LANG: str = "en"
LOCALES_DIR: Path = Path(__file__).resolve().parent / "locales"


def normalize_lang(value: str | None) -> str:
    """Map a locale string ('fr_CA', 'en-US', 'FR') to a supported code.

    Returns DEFAULT_LANG for None / empty / unsupported values.
    """
    if not value:
        return DEFAULT_LANG
    code = value.lower().replace("-", "_").split("_", 1)[0]
    if code in SUPPORTED_LANGS:
        return code
    return DEFAULT_LANG


def detect_system_lang() -> str:
    """Detect the language from the OS locale, falling back to DEFAULT_LANG."""
    try:
        loc = locale.getlocale()
        return normalize_lang(loc[0] if loc else None)
    except Exception:
        return DEFAULT_LANG


def load_catalog(lang: str) -> dict[str, str]:
    """Load the JSON catalog for the given language code.

    Falls back to DEFAULT_LANG if the requested language is unsupported
    or its catalog file is missing.
    """
    code = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    path = LOCALES_DIR / f"{code}.json"
    if not path.exists() and code != DEFAULT_LANG:
        path = LOCALES_DIR / f"{DEFAULT_LANG}.json"
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    return {k: str(v) for k, v in data.items()}


def translate(key: str, catalog: dict[str, str]) -> str:
    """Return catalog[key] or the key itself if missing (visible fallback)."""
    return catalog.get(key, key)
