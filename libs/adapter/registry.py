"""Process-wide channel-adapter registry (AI-2.5.1).

An adapter package self-registers on import (typically by calling
``register_adapter("birmarket", BirmarketAdapter)`` at module load), and the
sync engine looks it up by ``code`` — the same string that lives in
``channels.code`` (ADR-0018) and matches an inbound webhook path
``/v1/channels/{code}/webhook``.

The registry is intentionally a plain module-global ``dict`` (no DI container):
adapter registration is a process-startup, write-once-per-code fact, and the
test suite uses :func:`clear_registry` to keep tests isolated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .capabilities import AdapterCapabilities
    from .protocol import ChannelAdapter

_REGISTRY: dict[str, type[ChannelAdapter]] = {}


class AdapterAlreadyRegisteredError(KeyError):
    """Tried to register a second adapter under an existing ``code``.

    Catches the "two packages collide on the same channel" mistake at process
    startup, when the fix is to rename one of them.
    """


class AdapterNotFoundError(KeyError):
    """No adapter registered for the requested ``code``.

    Surfaced by the sync engine when it sees a channel row whose ``code`` has
    no installed adapter — almost always a missing import in app startup.
    """


def register_adapter(code: str, adapter_cls: type[ChannelAdapter]) -> None:
    """Add ``adapter_cls`` to the registry under ``code``.

    ``code`` must match ``adapter_cls.capabilities.code`` so the lookup key
    matches what the sync engine sees on the class. Raises
    :class:`AdapterAlreadyRegisteredError` if a different class is already
    registered under that code; re-registering the same class is a no-op so
    re-import (typical in tests) doesn't blow up.
    """
    declared = adapter_cls.capabilities.code
    if declared != code:
        raise ValueError(
            f"register_adapter: code {code!r} must match capabilities.code {declared!r}"
        )
    existing = _REGISTRY.get(code)
    if existing is None:
        _REGISTRY[code] = adapter_cls
        return
    if existing is adapter_cls:
        return
    raise AdapterAlreadyRegisteredError(
        f"channel code {code!r} already registered to {existing.__name__}"
    )


def get_adapter(code: str) -> type[ChannelAdapter]:
    """Return the adapter class for ``code``. Raises
    :class:`AdapterNotFoundError` if nothing is registered."""
    try:
        return _REGISTRY[code]
    except KeyError as exc:
        raise AdapterNotFoundError(f"no adapter registered for code {code!r}") from exc


def list_adapters() -> list[AdapterCapabilities]:
    """Return every registered adapter's capabilities, ordered by ``code``."""
    return [cls.capabilities for _, cls in sorted(_REGISTRY.items())]


def clear_registry() -> None:
    """Test-only — empty the registry between cases.

    Production code never calls this. The plain ``dict`` keeps registration
    cheap (no locking), so tests own the cleanup via a fixture.
    """
    _REGISTRY.clear()
