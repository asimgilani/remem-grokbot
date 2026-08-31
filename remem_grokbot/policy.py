from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from typing import Iterable

FORBIDDEN_WRITE_NAMESPACE = "default"
FALLBACK_WRITE_NAMESPACE = "grokbot"
OMITTED_READ_NAMESPACES: tuple[str, ...] = ("default", "grokbot")


class CanonicalUuidError(ValueError):
    """Raised when a document or entity id is not a canonical UUID."""


def canonical_uuid(value: str, field: str) -> str:
    try:
        parsed = uuid.UUID(str(value).strip())
    except (ValueError, AttributeError, TypeError) as exc:
        raise CanonicalUuidError(f"{field} must be a canonical UUID") from exc
    return str(parsed)


@dataclass(frozen=True)
class NamespacePolicy:
    """Grok Bot namespace rules.

    Writes never land in ``default``. ``REMEM_DEFAULT_NAMESPACE`` is honored
    only when it is set and is not ``default``. Otherwise writes use ``grokbot``.
    Omitted reads become ``["default", "grokbot"]``. Callers who pass
    ``namespaces`` keep that list. ``["*"]`` is never injected.
    """

    write_namespace: str

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> NamespacePolicy:
        source = env if env is not None else os.environ
        raw = str(source.get("REMEM_DEFAULT_NAMESPACE", "")).strip()
        if raw and raw != FORBIDDEN_WRITE_NAMESPACE:
            return cls(write_namespace=raw)
        return cls(write_namespace=FALLBACK_WRITE_NAMESPACE)

    def resolve_write(self, requested: str | None = None) -> str:
        return self.write_namespace

    def resolve_read(self, requested: Iterable[str] | None) -> list[str]:
        if requested is None:
            return list(OMITTED_READ_NAMESPACES)
        values = [str(item) for item in requested if str(item)]
        if not values:
            return list(OMITTED_READ_NAMESPACES)
        return values
