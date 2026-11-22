"""Registro de factories para adaptadores de canales."""
from __future__ import annotations

import re
from dataclasses import dataclass
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Protocol, TypeVar

from lazaro_contracts import (
    CHANNEL_ID_PATTERN,
    MAX_CHANNEL_ID_LENGTH,
    MIN_CHANNEL_ID_LENGTH,
    ChannelCapabilities,
)

from .domain import (
    ChannelRecord,
    ChannelSecrets,
    DomainError,
)

if TYPE_CHECKING:
    from .config import Settings
    from .domain import Adapters
    from .ports.canal import Canal


@dataclass(frozen=True)
class ChannelContext:
    settings: Settings
    adapters: Adapters


class ChannelFactory(Protocol):
    managed_by_environment: ClassVar[bool]

    @classmethod
    def is_available(cls, context: ChannelContext) -> bool: ...

    @classmethod
    def default_capabilities(
        cls, config: Mapping[str, Any] | None = None
    ) -> ChannelCapabilities:
        """Capacidades sin destino del tipo, sin construir el cliente ni leer secretos."""
        ...

    @classmethod
    def build(
        cls,
        record: ChannelRecord,
        context: ChannelContext,
        secrets: ChannelSecrets | None,
    ) -> Canal: ...


class DuplicateAdapterType(ValueError):
    """El tipo de adaptador ya está registrado."""


class UnknownAdapterType(DomainError):
    """No existe una factory registrada para el tipo solicitado."""

    code = "validation_error"
    status_code = 422


FactoryT = TypeVar("FactoryT", bound=type[ChannelFactory])


class ChannelRegistry:
    def __init__(self, factories: dict[str, type[ChannelFactory]] | None = None) -> None:
        self._factories = dict(factories or {})

    def register(
        self, adapter_type: str
    ) -> Callable[[FactoryT], FactoryT]:
        if (
            not isinstance(adapter_type, str)
            or not MIN_CHANNEL_ID_LENGTH <= len(adapter_type) <= MAX_CHANNEL_ID_LENGTH
            or re.fullmatch(CHANNEL_ID_PATTERN, adapter_type) is None
        ):
            raise ValueError("tipo_adaptador debe ser un slug de canal válido")

        def decorator(factory: FactoryT) -> FactoryT:
            if adapter_type in self._factories:
                raise DuplicateAdapterType(
                    f"tipo_adaptador ya registrado: {adapter_type}"
                )
            if not isinstance(getattr(factory, "managed_by_environment", None), bool):
                raise TypeError("la factory debe declarar managed_by_environment")
            self._factories[adapter_type] = factory
            return factory

        return decorator

    def get(self, adapter_type: str) -> type[ChannelFactory]:
        try:
            return self._factories[adapter_type]
        except KeyError as exc:
            raise UnknownAdapterType("tipo_adaptador no registrado") from exc

    def adapter_types(self) -> tuple[str, ...]:
        return tuple(self._factories)

    def creatable_types(self) -> tuple[str, ...]:
        return tuple(
            adapter_type
            for adapter_type, factory in self._factories.items()
            if not factory.managed_by_environment
        )

    def copy(self) -> "ChannelRegistry":
        return ChannelRegistry(self._factories)


CHANNEL_REGISTRY = ChannelRegistry()
