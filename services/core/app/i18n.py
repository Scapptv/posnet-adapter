"""Core service i18n: supported locales, catalogs and request helpers (AI-1.17).

Beachhead locales: Azerbaijani (default), with English, Turkish and Russian — the
languages the AZ -> TR market path needs. The catalogs hold shell/auth/error
strings the frontends fetch via ``GET /v1/i18n/messages`` (see the i18n router);
the :class:`Translator` mechanism lives in ``libs.i18n``.
"""

from __future__ import annotations

from fastapi import Request

from libs.i18n import Translator, negotiate_locale

DEFAULT_LOCALE = "az"

# One dict per locale; the default (az) is the source of truth, others may be
# partial (missing keys fall back to az via the Translator).
CATALOGS: dict[str, dict[str, str]] = {
    "az": {
        "app.name": "Posnet",
        "app.tagline": "POS-mərkəzli omnichannel inteqrasiya hub-ı",
        "auth.login": "Daxil ol",
        "auth.logout": "Çıxış",
        "error.unauthorized": "Kimlik təsdiqlənmədi",
        "error.forbidden": "İcazə yoxdur",
        "error.not_found": "Tapılmadı",
        "error.rate_limited": "Həddən çox sorğu",
        "error.internal": "Daxili xəta baş verdi",
        "common.save": "Yadda saxla",
        "common.cancel": "Ləğv et",
    },
    "en": {
        "app.name": "Posnet",
        "app.tagline": "POS-anchored omnichannel integration hub",
        "auth.login": "Log in",
        "auth.logout": "Log out",
        "error.unauthorized": "Unauthorized",
        "error.forbidden": "Forbidden",
        "error.not_found": "Not found",
        "error.rate_limited": "Too many requests",
        "error.internal": "An internal error occurred",
        "common.save": "Save",
        "common.cancel": "Cancel",
    },
    "tr": {
        "app.name": "Posnet",
        "app.tagline": "POS merkezli omnichannel entegrasyon hub'ı",
        "auth.login": "Giriş yap",
        "auth.logout": "Çıkış yap",
        "error.unauthorized": "Kimlik doğrulanmadı",
        "error.forbidden": "Erişim engellendi",
        "error.not_found": "Bulunamadı",
        "error.rate_limited": "Çok fazla istek",
        "error.internal": "Bir sunucu hatası oluştu",
        "common.save": "Kaydet",
        "common.cancel": "İptal",
    },
    "ru": {
        "app.name": "Posnet",
        "app.tagline": "Интеграционный хаб с центром в POS",
        "auth.login": "Войти",
        "auth.logout": "Выйти",
        "error.unauthorized": "Не авторизован",
        "error.forbidden": "Доступ запрещён",
        "error.not_found": "Не найдено",
        "error.rate_limited": "Слишком много запросов",
        "error.internal": "Произошла внутренняя ошибка",
        "common.save": "Сохранить",
        "common.cancel": "Отмена",
    },
}

SUPPORTED_LOCALES: tuple[str, ...] = tuple(CATALOGS)


def build_translator() -> Translator:
    return Translator(CATALOGS, default_locale=DEFAULT_LOCALE)


def get_translator(request: Request) -> Translator:
    """The process-wide translator (built once in the app factory)."""
    return request.app.state.translator  # type: ignore[no-any-return]


def get_locale(request: Request) -> str:
    """Resolve the request locale: explicit ``?locale=`` override (if supported),
    else ``Accept-Language`` negotiation, else the default."""
    override = request.query_params.get("locale")
    if override and override.lower() in SUPPORTED_LOCALES:
        return override.lower()
    return negotiate_locale(
        request.headers.get("Accept-Language"), SUPPORTED_LOCALES, DEFAULT_LOCALE
    )
