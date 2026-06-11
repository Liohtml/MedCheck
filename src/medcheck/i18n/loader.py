"""Internationalization catalog loader for MedCheck report strings."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# Locate our current folder path dynamically
I18N_DIR = Path(__file__).parent


@lru_cache(maxsize=4)
def _load_catalog(lang: str) -> dict[str, str]:
    """Load a JSON catalog from disk with internal caching."""
    file_path = I18N_DIR / f"{lang}.json"
    if not file_path.is_file():
        return {}
    try:
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def get_strings(lang: str | None) -> dict[str, str]:
    """Retrieve the translation dictionary for the specified language.

    Falls back to English ('en') if the language catalog does not exist
    or if specific translation strings are missing.
    """
    target_lang = (lang or "en").lower().strip()

    # Load English fallback strings first
    en_strings = _load_catalog("en")

    if target_lang == "en":
        return en_strings

    # Load the requested target catalog
    target_strings = _load_catalog(target_lang)
    if not target_strings:
        return en_strings

    # Merge them: Use target translations, fill missing gaps with English
    merged = en_strings.copy()
    merged.update(target_strings)
    return merged
