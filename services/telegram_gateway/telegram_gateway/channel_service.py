"""Casos de uso para sembrar, resolver y administrar canales."""
from __future__ import annotations

import logging
import secrets
import threading
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

from lazaro_contracts import (
    ChannelActiveRequest,
    ChannelCapabilities,
    ChannelCreateRequest,
    ChannelCreateResponse,
    ChannelInfo,
    ChannelListResponse,
    ChannelSecretResponse,
    ChannelUpdateRequest,
    credential_hint,
)

from .adapters.channel_repository import ChannelChanges, ChannelRepository
from .domain import (
    BUILTIN_CHANNEL_SEEDS,
    ChannelAlreadyExists,
    ChannelInactive,
    ChannelManagedByEnvironment,
    ChannelNotConfigured,
    ChannelNotFound,
    ChannelRecord,
    ChannelSecrets,
    ChannelSecretsUnavailable,
    ChannelSeed,
    ChannelStoreUnavailable,
    DomainError,
    UnknownChannel,
)
from .registry import ChannelContext, ChannelRegistry, UnknownAdapterType
from .secret_cipher import SecretCipher

if TYPE_CHECKING:
    from .ports.canal import Canal

logger = logging.getLogger(__name__)


class ChannelService:
    def __init__(
        self,
        repository: ChannelRepository,
        registry: ChannelRegistry,
        cipher: SecretCipher,
        context: ChannelContext,
        seeds: Sequence[ChannelSeed] = BUILTIN_CHANNEL_SEEDS,
        new_secret: Callable[[], str] | None = None,
    ) -> None:
        self._repository = repository
        self._registry = registry
        self._cipher = cipher
        self._context = context
        self._seeds = tuple(seeds)
        self._new_secret = new_secret or (lambda: secrets.token_urlsafe(32))
        self._seed_lock = threading.Lock()
        self._seeded = False

    def _repository_call(self, method: Callable, *args):
        try:
            return method(*args)
        except DomainError:
            raise
        except Exception as exc:
            logger.error("channel_store_error code=%s", type(exc).__name__)
            raise ChannelStoreUnavailable(
                "El almacén de canales no está disponible."
            ) from None

    def ensure_seeded(self) -> None:
        if self._seeded:
            return
        with self._seed_lock:
            if self._seeded:
                return
            rows = []
            for seed in self._seeds:
                factory = self._registry.get(seed.adapter_type)
                rows.append((seed, factory.is_available(self._context)))
            self._repository_call(self._repository.seed, rows)
            self._seeded = True

    def _record(self, channel_id: str) -> ChannelRecord:
        record = self._repository_call(self._repository.get, channel_id)
        if record is None:
            raise ChannelNotFound("El canal no existe.")
        return record

    def _factory(self, record: ChannelRecord):
        try:
            return self._registry.get(record.adapter_type)
        except UnknownAdapterType:
            return None

    def _validate_config(self, factory, config) -> None:
        hook = getattr(factory, "validate_config", None)
        if factory is None or config is None or not callable(hook):
            return
        hook(dict(config), self._context)

    def _info(self, record: ChannelRecord) -> ChannelInfo:
        factory = self._factory(record)
        configured = factory is not None and factory.is_available(self._context)
        managed = factory.managed_by_environment if factory is not None else False
        return ChannelInfo(
            id=record.id,
            name=record.name,
            adapter_type=record.adapter_type,
            icon=record.icon,
            color=record.color,
            config=dict(record.config),
            active=record.active,
            configured=configured,
            has_secrets=record.has_secrets,
            managed_by_environment=managed,
            created_at=record.created_at,
            capabilities=_default_capabilities(factory, record),
            credential_hints=dict(record.credential_hints),
        )

    def _secrets_for(self, record: ChannelRecord) -> ChannelSecrets | None:
        encrypted = self._repository_call(
            self._repository.get_encrypted_secrets, record.id
        )
        if encrypted is None:
            if record.has_secrets:
                raise ChannelSecretsUnavailable(
                    "Los secretos del canal no están disponibles."
                )
            return None
        return self._cipher.decrypt(encrypted)

    def list_channels(self) -> ChannelListResponse:
        self.ensure_seeded()
        records = self._repository_call(self._repository.list_channels)
        return ChannelListResponse(
            channels=[self._info(record) for record in records],
            adapter_types=list(self._registry.creatable_types()),
        )

    def resolve(self, channel_id: str):
        self.ensure_seeded()
        try:
            record = self._record(channel_id)
        except ChannelNotFound:
            raise UnknownChannel("El canal no está registrado.") from None
        try:
            factory = self._registry.get(record.adapter_type)
        except UnknownAdapterType:
            raise ChannelNotConfigured(
                "El adaptador de canal no está disponible."
            ) from None
        if not factory.is_available(self._context):
            raise ChannelNotConfigured("El adaptador de canal no está disponible.")
        if not record.active:
            raise ChannelInactive("El canal está inactivo.")
        channel_secrets = self._secrets_for(record)
        return factory.build(record, self._context, channel_secrets)

    def _seed_record(self, channel_id: str) -> ChannelRecord | None:
        """Registro sintético de un canal integrado cuando la tabla no responde."""
        for seed in self._seeds:
            if seed.id == channel_id:
                return ChannelRecord(
                    id=seed.id,
                    name=seed.name,
                    adapter_type=seed.adapter_type,
                    icon=seed.icon,
                    color=seed.color,
                    config=dict(seed.config),
                    active=True,
                    created_at=self._context.adapters.clock(),
                    has_secrets=False,
                    active_follows_environment=True,
                )
        return None

    def resolve_for_webhook(
        self, channel_id: str, *, own_route: bool = False
    ) -> tuple["Canal", str | None]:
        """R7-R9: resuelve un canal activo con secreto o lanza 404 uniforme.

        Fase 2: un adaptador con `webhook_propio` (Telegram, WhatsApp) verifica
        su propio webhook y solo entra por su URL histórica (`own_route`); se
        devuelve sin secreto genérico (`None`). Si la tabla de canales no
        responde, esas URLs siguen funcionando con la semilla integrada (R15).
        """
        not_found = "El canal no existe."
        try:
            self.ensure_seeded()
            record = self._repository_call(self._repository.get, channel_id)
        except ChannelStoreUnavailable:
            record = self._seed_record(channel_id) if own_route else None
            if record is None:
                raise
        if record is None:
            raise ChannelNotFound(not_found)
        factory = self._factory(record)
        if factory is None or not factory.is_available(self._context):
            raise ChannelNotFound(not_found)
        if not record.active:
            raise ChannelNotFound(not_found)
        own_webhook = getattr(factory, "webhook_propio", False) is True
        if own_webhook != own_route:
            raise ChannelNotFound(not_found)
        if own_webhook:
            try:
                canal = factory.build(record, self._context, None)
            except ChannelNotConfigured:
                raise ChannelNotFound(not_found) from None
            return canal, None
        channel_secrets = self._secrets_for(record)
        if channel_secrets is None or channel_secrets.secret is None:
            raise ChannelNotFound(not_found)
        try:
            canal = factory.build(record, self._context, channel_secrets)
        except ChannelNotConfigured:
            raise ChannelNotFound(not_found) from None
        return canal, channel_secrets.secret

    def _mailbox_record(self, channel_id: str) -> tuple[ChannelRecord, type]:
        """R19, R20: 404 uniforme si no hay fila o el tipo no tiene buzón."""
        self.ensure_seeded()
        not_found = "El canal no existe."
        record = self._repository_call(self._repository.get, channel_id)
        if record is None:
            raise ChannelNotFound(not_found)
        factory = self._factory(record)
        if factory is None or not factory.is_available(self._context):
            raise ChannelNotFound(not_found)
        if not getattr(factory, "has_mailbox", False):
            raise ChannelNotFound(not_found)
        return record, factory

    def mailbox_channel(self, channel_id: str) -> "Canal":
        """R19: construye el canal para leer su buzón (puede estar inactivo)."""
        record, factory = self._mailbox_record(channel_id)
        try:
            return factory.build(record, self._context, None)
        except ChannelNotConfigured:
            raise ChannelNotFound("El canal no existe.") from None

    def active_mailbox_channel(self, channel_id: str) -> "Canal":
        """R20: exige además que el canal esté activo para recibir mensajes."""
        record, factory = self._mailbox_record(channel_id)
        if not record.active:
            raise ChannelInactive("El canal está inactivo.")
        try:
            return factory.build(record, self._context, None)
        except ChannelNotConfigured:
            raise ChannelNotFound("El canal no existe.") from None

    def create(self, request: ChannelCreateRequest) -> ChannelCreateResponse:
        self.ensure_seeded()
        try:
            factory = self._registry.get(request.adapter_type)
        except UnknownAdapterType:
            raise
        if factory.managed_by_environment:
            raise UnknownAdapterType("El tipo de adaptador no admite creación.")
        if self._repository_call(self._repository.get, request.id) is not None:
            raise ChannelAlreadyExists("El id del canal ya existe.")
        self._validate_config(factory, request.config)

        secret = self._new_secret()
        encrypted = self._cipher.encrypt(
            ChannelSecrets(secret=secret, credentials=request.credentials)
        )
        record = ChannelRecord(
            id=request.id,
            name=request.name,
            adapter_type=request.adapter_type,
            icon=request.icon,
            color=request.color,
            config=dict(request.config),
            active=request.active,
            created_at=self._context.adapters.clock(),
            has_secrets=True,
            active_follows_environment=False,
            credential_hints=_hints(request.credentials),
        )
        created = self._repository_call(self._repository.create, record, encrypted)
        if not created:
            raise ChannelAlreadyExists("El id del canal ya existe.")
        return ChannelCreateResponse(channel=self._info(record), secret=secret)

    def update(
        self, channel_id: str, request: ChannelUpdateRequest
    ) -> ChannelInfo:
        self.ensure_seeded()
        record = self._record(channel_id)
        fields = request.model_fields_set
        factory = self._factory(record)
        if "credentials" in fields and factory is not None and factory.managed_by_environment:
            raise ChannelManagedByEnvironment(
                "El canal lo gestiona la configuración del entorno."
            )
        if "config" in fields:
            self._validate_config(factory, request.config)

        encrypted_secrets = None
        if "credentials" in fields:
            current_secrets = self._secrets_for(record) or ChannelSecrets()
            encrypted_secrets = self._cipher.encrypt(
                ChannelSecrets(
                    secret=current_secrets.secret,
                    credentials=request.credentials or {},
                )
            )
        changes = ChannelChanges(
            name=request.name if "name" in fields else None,
            icon=request.icon if "icon" in fields else None,
            color=request.color if "color" in fields else None,
            config=(dict(request.config) if "config" in fields else None),
            encrypted_secrets=encrypted_secrets,
            credential_hints=(
                _hints(request.credentials or {}) if "credentials" in fields else None
            ),
        )
        updated = self._repository_call(
            self._repository.update, channel_id, changes
        )
        if updated is None:
            raise ChannelNotFound("El canal no existe.")
        return self._info(updated)

    def set_active(
        self, channel_id: str, request: ChannelActiveRequest
    ) -> ChannelInfo:
        self.ensure_seeded()
        updated = self._repository_call(
            self._repository.set_active, channel_id, request.active
        )
        if updated is None:
            raise ChannelNotFound("El canal no existe.")
        return self._info(updated)

    def regenerate_secret(self, channel_id: str) -> ChannelSecretResponse:
        self.ensure_seeded()
        record = self._record(channel_id)
        factory = self._factory(record)
        if factory is not None and factory.managed_by_environment:
            raise ChannelManagedByEnvironment(
                "El canal lo gestiona la configuración del entorno."
            )
        current = self._secrets_for(record) or ChannelSecrets()
        secret = self._new_secret()
        encrypted = self._cipher.encrypt(
            ChannelSecrets(secret=secret, credentials=current.credentials)
        )
        if not self._repository_call(
            self._repository.set_encrypted_secrets, channel_id, encrypted
        ):
            raise ChannelNotFound("El canal no existe.")
        logger.info("channel_secret_regenerated channel_id=%s", channel_id)
        return ChannelSecretResponse(channel_id=channel_id, secret=secret)

    def reveal_secret(self, channel_id: str) -> ChannelSecretResponse:
        self.ensure_seeded()
        record = self._record(channel_id)
        factory = self._factory(record)
        if factory is not None and factory.managed_by_environment:
            raise ChannelManagedByEnvironment(
                "El canal lo gestiona la configuración del entorno."
            )
        current = self._secrets_for(record)
        if current is None or current.secret is None:
            raise ChannelNotFound("El canal o su secreto no existen.")
        logger.info("channel_secret_revealed channel_id=%s", channel_id)
        return ChannelSecretResponse(channel_id=channel_id, secret=current.secret)


def _hints(credentials) -> dict[str, str]:
    """#66 R3/R4: solo la pista de cada credencial, nunca su valor."""
    return {name: credential_hint(value) for name, value in dict(credentials).items()}


def _default_capabilities(factory, record: ChannelRecord) -> ChannelCapabilities | None:
    """Capacidades sin destino del tipo (R2); None si no hay factory o no las informa (R3)."""
    if factory is None:
        return None
    default = getattr(factory, "default_capabilities", None)
    if not callable(default):
        return None
    try:
        capabilities = default(dict(record.config))
    except Exception:  # noqa: BLE001 - un adaptador defectuoso no rompe el listado
        logger.warning("channel_capabilities_failed adapter_type=%s", record.adapter_type)
        return None
    return capabilities if isinstance(capabilities, ChannelCapabilities) else None
