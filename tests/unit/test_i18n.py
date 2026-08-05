import json

from medcheck.i18n import get_strings
from medcheck.i18n.loader import I18N_DIR


def test_i18n_loader_resolves_languages():
    # Test explicitly supported language using your actual catalog values
    de_strings = get_strings("de")
    assert de_strings["report_title"] == "MedCheck Radiologiebericht"

    # Test fallback mechanism for unknown language
    fallback_strings = get_strings("xyz")
    assert fallback_strings["report_title"] == "MedCheck Radiology Report"

    # Test fallback mechanism for None configuration
    none_strings = get_strings(None)
    assert none_strings["report_title"] == "MedCheck Radiology Report"


def test_catalogs_have_identical_keys():
    # Every locale must carry the full key set (report + ui_*) so no language
    # silently falls back to English for individual strings.
    keys = {}
    for lang in ("en", "de", "fr", "es"):
        with open(I18N_DIR / f"{lang}.json", encoding="utf-8") as f:
            keys[lang] = set(json.load(f))
    assert keys["de"] == keys["en"]
    assert keys["fr"] == keys["en"]
    assert keys["es"] == keys["en"]


def test_i18n_rejects_path_traversal_lang():
    # A traversal-style language value must not be interpolated into a path; it
    # falls back to English instead of attempting to read outside the i18n dir.
    strings = get_strings("../../../../etc/passwd")
    assert strings["report_title"] == "MedCheck Radiology Report"
