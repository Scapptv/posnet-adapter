"""i18n bootstrap endpoint (AI-1.17).

``GET /v1/i18n/messages`` returns the negotiated locale and its full message
catalog so a frontend can render localized text. It is unauthenticated on purpose
— the login screen needs strings before a token exists — and tenant-agnostic.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from libs.i18n import Translator

from ...i18n import get_locale, get_translator

router = APIRouter(prefix="/i18n", tags=["i18n"])


class MessagesResponse(BaseModel):
    locale: str
    messages: dict[str, str]


@router.get("/messages", response_model=MessagesResponse)
async def messages(
    locale: str = Depends(get_locale),
    translator: Translator = Depends(get_translator),
) -> MessagesResponse:
    return MessagesResponse(locale=locale, messages=translator.catalog(locale))
