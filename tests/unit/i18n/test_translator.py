"""AI-1.17 — message catalog Translator (unit, no IO)."""

from __future__ import annotations

import pytest

from libs.i18n import Translator

_CATALOGS = {
    "en": {"greeting": "Hello, {name}", "only_en": "English only"},
    "az": {"greeting": "Salam, {name}"},  # no ``only_en`` -> falls back to en
}


@pytest.fixture
def translator() -> Translator:
    return Translator(_CATALOGS, default_locale="en")


@pytest.mark.unit
def test_translate_uses_requested_locale(translator: Translator) -> None:
    assert translator.translate("az", "greeting", name="Aysu") == "Salam, Aysu"


@pytest.mark.unit
def test_translate_falls_back_to_default_locale(translator: Translator) -> None:
    assert translator.translate("az", "only_en") == "English only"


@pytest.mark.unit
def test_translate_unknown_locale_uses_default(translator: Translator) -> None:
    assert translator.translate("fr", "greeting", name="Z") == "Hello, Z"


@pytest.mark.unit
def test_translate_unknown_key_returns_the_key(translator: Translator) -> None:
    assert translator.translate("en", "missing.key") == "missing.key"


@pytest.mark.unit
def test_translate_missing_param_keeps_template(translator: Translator) -> None:
    # A formatting gap (``name`` absent) must not raise — return the unformatted
    # template rather than blowing up the response.
    assert translator.translate("az", "greeting", unrelated="x") == "Salam, {name}"


@pytest.mark.unit
def test_catalog_merges_default_under_locale(translator: Translator) -> None:
    assert translator.catalog("az") == {"greeting": "Salam, {name}", "only_en": "English only"}


@pytest.mark.unit
def test_catalog_unknown_locale_is_default(translator: Translator) -> None:
    assert translator.catalog("fr") == _CATALOGS["en"]


@pytest.mark.unit
def test_locales_and_default(translator: Translator) -> None:
    assert translator.locales() == ("en", "az")
    assert translator.default_locale == "en"


@pytest.mark.unit
def test_default_locale_must_have_a_catalog() -> None:
    with pytest.raises(ValueError, match="default locale"):
        Translator(_CATALOGS, default_locale="de")
