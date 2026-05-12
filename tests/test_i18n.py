"""Tests for app.i18n module."""

from unittest.mock import patch

import pytest

from app.i18n import (
    SUPPORTED_LANGS,
    detect_system_lang,
    load_catalog,
    normalize_lang,
    translate,
)

REQUIRED_KEYS = {
    "app.title",
    "nav.home",
    "nav.conditions",
    "nav.tips",
    "home.title",
    "home.subtitle",
    "home.cta",
    "form.species",
    "form.region",
    "form.water_type",
    "form.submit",
    "conditions.title",
    "conditions.weather",
    "conditions.solunar",
    "conditions.tips",
    "errors.weather_unavailable",
    "errors.gps_refused",
    "errors.db_recovered",
    "footer.disclaimer",
    "footer.about",
}


def test_supported_langs_are_fr_and_en() -> None:
    assert set(SUPPORTED_LANGS) == {"fr", "en"}


@pytest.mark.parametrize(
    "loc_value, expected",
    [
        ("fr_CA", "fr"),
        ("fr_FR", "fr"),
        ("FR", "fr"),
        ("en_US", "en"),
        ("en_GB", "en"),
        ("EN", "en"),
        ("de_DE", "en"),  # unsupported falls back to en
        ("", "en"),
        (None, "en"),
    ],
)
def test_normalize_lang(loc_value: str | None, expected: str) -> None:
    assert normalize_lang(loc_value) == expected


def test_detect_system_lang_uses_locale_getlocale() -> None:
    with patch("app.i18n.locale.getlocale", return_value=("fr_CA", "UTF-8")):
        assert detect_system_lang() == "fr"


def test_detect_system_lang_falls_back_to_en_on_error() -> None:
    with patch("app.i18n.locale.getlocale", side_effect=Exception("boom")):
        assert detect_system_lang() == "en"


def test_detect_system_lang_handles_none_locale() -> None:
    with patch("app.i18n.locale.getlocale", return_value=(None, None)):
        assert detect_system_lang() == "en"


def test_load_catalog_fr() -> None:
    cat = load_catalog("fr")
    assert "app.title" in cat
    assert isinstance(cat["app.title"], str)


def test_load_catalog_en() -> None:
    cat = load_catalog("en")
    assert "app.title" in cat
    assert isinstance(cat["app.title"], str)


def test_load_catalog_unknown_falls_back_to_en() -> None:
    cat = load_catalog("xx")
    en = load_catalog("en")
    assert cat == en


def test_translate_returns_value_for_known_key() -> None:
    cat = load_catalog("en")
    val = translate("app.title", cat)
    assert val and val != "app.title"


def test_translate_returns_key_when_missing() -> None:
    val = translate("nonexistent.key", {"foo": "bar"})
    assert val == "nonexistent.key"


def test_fr_catalog_has_all_required_keys() -> None:
    cat = load_catalog("fr")
    missing = REQUIRED_KEYS - set(cat)
    assert not missing, f"FR missing keys: {missing}"


def test_fr_catalog_values_are_french() -> None:
    cat = load_catalog("fr")
    text = " ".join(cat.values()).lower()
    assert any(c in text for c in "éèêàâîôûç") or "pêche" in text or "espèce" in text


def test_en_catalog_has_all_required_keys() -> None:
    cat = load_catalog("en")
    missing = REQUIRED_KEYS - set(cat)
    assert not missing, f"EN missing keys: {missing}"


def test_en_and_fr_catalogs_have_same_keys() -> None:
    fr = load_catalog("fr")
    en = load_catalog("en")
    only_fr = set(fr) - set(en)
    only_en = set(en) - set(fr)
    assert not only_fr, f"FR has keys missing in EN: {only_fr}"
    assert not only_en, f"EN has keys missing in FR: {only_en}"


def test_en_values_are_english() -> None:
    cat = load_catalog("en")
    text = " ".join(cat.values()).lower()
    assert any(w in text for w in ("the ", "and ", "for ", "your "))
