"""Feature flag registry: the catalog of known flags + override resolution (AI-1.17).

The registry is the single source of *which* flags exist and their built-in
defaults; per-tenant overrides are stored elsewhere (the core ``feature_flags``
table) and merged in via :meth:`FlagRegistry.resolve`. Pure data + logic, so it is
trivially unit-tested and reusable across services.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FlagSpec:
    key: str
    default: bool
    description: str


class UnknownFlagError(LookupError):
    """Raised when a flag key is not declared in the registry."""

    def __init__(self, key: str) -> None:
        super().__init__(f"unknown feature flag: {key}")
        self.key = key


class FlagRegistry:
    def __init__(self, specs: Sequence[FlagSpec]) -> None:
        registry: dict[str, FlagSpec] = {}
        for spec in specs:
            if spec.key in registry:
                raise ValueError(f"duplicate feature flag: {spec.key}")
            registry[spec.key] = spec
        self._specs = registry

    def __contains__(self, key: object) -> bool:
        return key in self._specs

    def keys(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def specs(self) -> tuple[FlagSpec, ...]:
        return tuple(self._specs.values())

    def require(self, key: str) -> None:
        """Raise :class:`UnknownFlagError` unless ``key`` is a declared flag."""
        if key not in self._specs:
            raise UnknownFlagError(key)

    def defaults(self) -> dict[str, bool]:
        return {key: spec.default for key, spec in self._specs.items()}

    def resolve(self, overrides: Mapping[str, bool]) -> dict[str, bool]:
        """Effective flags = built-in defaults overlaid with ``overrides``.

        Overrides for keys not in the registry are ignored (a removed flag whose
        stored row outlives it must not resurface).
        """
        effective = self.defaults()
        for key, enabled in overrides.items():
            if key in self._specs:
                effective[key] = enabled
        return effective
