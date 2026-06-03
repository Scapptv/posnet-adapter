"""Message catalog with a locale -> default-locale -> key fallback chain (AI-1.17).

The mechanism is content-agnostic: a service supplies its catalogs (one ``dict``
of ``key -> template`` per locale) and the default locale; the translator only
resolves lookups. Templates use :pymeth:`str.format` placeholders.
"""

from __future__ import annotations

from collections.abc import Mapping


class Translator:
    def __init__(self, catalogs: Mapping[str, Mapping[str, str]], *, default_locale: str) -> None:
        if default_locale not in catalogs:
            raise ValueError(f"default locale {default_locale!r} has no catalog")
        self._catalogs: dict[str, dict[str, str]] = {
            locale: dict(messages) for locale, messages in catalogs.items()
        }
        self._default_locale = default_locale

    @property
    def default_locale(self) -> str:
        return self._default_locale

    def locales(self) -> tuple[str, ...]:
        return tuple(self._catalogs)

    def translate(self, locale: str, key: str, /, **params: object) -> str:
        """Resolve ``key`` for ``locale``, falling back to the default locale then
        the key itself; a missing format parameter leaves the template unformatted."""
        template = self._lookup(locale, key)
        if not params:
            return template
        try:
            return template.format(**params)
        except (KeyError, IndexError):
            return template

    def catalog(self, locale: str) -> dict[str, str]:
        """The full set of messages for ``locale``: default-locale entries overlaid
        with the locale's own (so every key resolves, even partially-translated ones)."""
        merged = dict(self._catalogs[self._default_locale])
        merged.update(self._catalogs.get(locale, {}))
        return merged

    def _lookup(self, locale: str, key: str) -> str:
        catalog = self._catalogs.get(locale)
        if catalog is not None and key in catalog:
            return catalog[key]
        default = self._catalogs[self._default_locale]
        if key in default:
            return default[key]
        return key
