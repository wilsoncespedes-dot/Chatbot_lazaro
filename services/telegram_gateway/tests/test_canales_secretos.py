"""R33, R35, R37: cifrado, fallo cerrado y representación sin secretos."""
from __future__ import annotations

from datetime import datetime, timezone

from cryptography.fernet import Fernet

import pytest
from lazaro_contracts import (
    ChannelActiveRequest,
    ChannelCreateRequest,
    ChannelUpdateRequest,
)

from telegram_gateway.adapters.channels import TelegramChannel, WhatsAppCloudChannel
from telegram_gateway.adapters.channel_repository import FakeChannelRepository
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.adapters.whatsapp import FakeWhatsAppAdapter
from telegram_gateway.channel_service import ChannelService
from telegram_gateway.config import Settings
from telegram_gateway.domain import (
    Adapters,
    ChannelAlreadyExists,
    ChannelInactive,
    ChannelManagedByEnvironment,
    ChannelNotConfigured,
    ChannelNotFound,
    ChannelRecord,
    ChannelSecrets,
    ChannelSecretsUnavailable,
    ChannelStoreUnavailable,
    UnknownChannel,
)
from telegram_gateway.registry import (
    CHANNEL_REGISTRY,
    ChannelContext,
    ChannelRegistry,
    UnknownAdapterType,
)
from telegram_gateway.secret_cipher import SecretCipher


def test_secret_cipher_encrypts_and_round_trips_channel_secrets():
    """R33: el token cifra secreto y credenciales y se descifra con la misma clave."""
    key = Fernet.generate_key().decode("ascii")
    cipher = SecretCipher(key)
    value = ChannelSecrets(
        secret="secreto-del-canal",
        credentials={"api_token": "credencial-privada"},
    )
    token = cipher.encrypt(value)
    assert cipher.status == "ok"
    assert cipher.available is True
    assert "secreto-del-canal" not in token
    assert "credencial-privada" not in token
    assert cipher.decrypt(token).secret == value.secret
    assert dict(cipher.decrypt(token).credentials) == dict(value.credentials)


@pytest.mark.parametrize("key", ["", "clave-invalida", "é" * 44])
def test_secret_cipher_reports_missing_or_invalid_key(key):
    """R35: una clave vacía o inválida deja el cifrador no disponible."""
    cipher = SecretCipher(key)
    assert cipher.status == ("missing" if not key else "invalid")
    assert cipher.available is False
    with pytest.raises(ChannelSecretsUnavailable):
        cipher.encrypt(ChannelSecrets(secret="valor"))


def test_secret_cipher_rejects_wrong_key_and_malformed_tokens():
    """R35: no se revelan detalles al fallar el descifrado."""
    first = SecretCipher(Fernet.generate_key().decode("ascii"))
    second = SecretCipher(Fernet.generate_key().decode("ascii"))
    token = first.encrypt(ChannelSecrets(secret="valor"))
    with pytest.raises(ChannelSecretsUnavailable):
        second.decrypt(token)
    with pytest.raises(ChannelSecretsUnavailable):
        first.decrypt("token-malformado")


def test_secret_objects_repr_never_exposes_secret_values():
    """R37: ni SecretCipher ni ChannelSecrets muestran sus valores en repr."""
    key = Fernet.generate_key().decode("ascii")
    secret = "secreto-que-no-debe-aparecer"
    credential = "credencial-que-no-debe-aparecer"
    cipher = SecretCipher(key)
    secrets = ChannelSecrets(secret=secret, credentials={"api_token": credential})
    assert "status='ok'" in repr(cipher)
    assert key not in repr(cipher)
    assert secret not in repr(secrets)
    assert credential not in repr(secrets)


NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)


def _registry(*, available: bool = True):
    registry = CHANNEL_REGISTRY.copy()
    availability = [available]

    @registry.register("tipo_prueba")
    class SimulatedFactory:
        managed_by_environment = False

        @classmethod
        def is_available(cls, context):
            return availability[0]

        @classmethod
        def build(cls, record, context, secrets):
            return {"channel_id": record.id, "secrets": secrets}

    return registry, availability


def _service(*, key: str | None = None, whatsapp=None, new_secret=None):
    repository = FakeChannelRepository(clock=lambda: NOW)
    registry, availability = _registry()
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=FakeOrchestratorClient(),
        clock=lambda: NOW,
        whatsapp=whatsapp,
    )
    context = ChannelContext(settings=Settings(), adapters=adapters)
    cipher = SecretCipher(key if key is not None else Fernet.generate_key().decode("ascii"))
    service = ChannelService(
        repository,
        registry,
        cipher,
        context,
        new_secret=new_secret,
    )
    return service, repository, cipher, registry, availability


def _create_request(**changes) -> ChannelCreateRequest:
    values = {
        "id": "canal-demo",
        "name": "Canal demo",
        "adapter_type": "tipo_prueba",
        "icon": "chat",
        "color": "#1B6FA8",
        "credentials": {"api_token": "credencial-original"},
    }
    values.update(changes)
    return ChannelCreateRequest(**values)


def _record(channel_id="canal-demo", **changes) -> ChannelRecord:
    values = {
        "id": channel_id,
        "name": "Canal demo",
        "adapter_type": "tipo_prueba",
        "icon": "chat",
        "color": "#1B6FA8",
        "config": {},
        "active": True,
        "created_at": NOW,
        "has_secrets": False,
        "active_follows_environment": False,
    }
    values.update(changes)
    return ChannelRecord(**values)


def test_channel_service_seeds_whatsapp_according_to_adapter_availability():
    """R29, R30: las filas built-in reflejan la disponibilidad de Telegram/WhatsApp."""
    unavailable, unavailable_repo, *_ = _service(whatsapp=None)
    unavailable_rows = {row.id: row for row in unavailable.list_channels().channels}
    assert unavailable_rows["telegram"].active is True
    assert unavailable_rows["whatsapp"].active is False
    assert unavailable_rows["whatsapp"].managed_by_environment is True

    enabled, enabled_repo, *_ = _service(whatsapp=FakeWhatsAppAdapter())
    enabled_rows = {row.id: row for row in enabled.list_channels().channels}
    assert enabled_rows["whatsapp"].active is True
    assert enabled_repo.get("whatsapp").active_follows_environment is True
    assert unavailable_repo.get("whatsapp").active_follows_environment is True


def test_resolve_rejects_unknown_unregistered_inactive_and_unavailable_channels():
    """R23–R25: resolve falla cerrado con la precedencia acordada."""
    service, repository, _, registry, availability = _service()
    service.ensure_seeded()
    with pytest.raises(UnknownChannel):
        service.resolve("canal-ausente")

    unregistered = _record("canal-desconocido", adapter_type="no_registrado")
    repository.create(unregistered, None)
    with pytest.raises(ChannelNotConfigured):
        service.resolve(unregistered.id)

    inactive = _record("canal-inactivo", active=False)
    repository.create(inactive, None)
    availability[0] = False
    with pytest.raises(ChannelNotConfigured):
        service.resolve(inactive.id)
    availability[0] = True
    with pytest.raises(ChannelInactive):
        service.resolve(inactive.id)

    active = _record("canal-activo")
    repository.create(active, None)
    resolved = service.resolve(active.id)
    assert resolved == {"channel_id": active.id, "secrets": None}


def test_resolve_with_secrets_fails_when_key_is_unavailable():
    """R35: enviar por un canal con secretos cifrados exige clave válida."""
    service, repository, _, _, _ = _service(key="")
    encrypted = SecretCipher(Fernet.generate_key().decode("ascii")).encrypt(
        ChannelSecrets(secret="canal-secret")
    )
    repository.create(_record(has_secrets=True), encrypted)
    with pytest.raises(ChannelSecretsUnavailable):
        service.resolve("canal-demo")


def test_channel_service_create_generates_distinct_secrets_and_encrypts_credentials():
    """R33, R40: crear cifra credenciales y devuelve secreto aleatorio de 43 caracteres."""
    generated = iter(("A" * 43, "B" * 43))
    service, repository, cipher, *_ = _service(new_secret=lambda: next(generated))
    first = service.create(_create_request())
    second = service.create(_create_request(id="canal-demo-2"))
    assert len(first.secret) == len(second.secret) == 43
    assert first.secret != second.secret
    encrypted = repository.get_encrypted_secrets("canal-demo")
    assert encrypted is not None
    assert first.secret not in encrypted
    secrets = cipher.decrypt(encrypted)
    assert secrets.secret == first.secret
    assert dict(secrets.credentials) == {"api_token": "credencial-original"}
    assert first.channel.has_secrets is True


def test_channel_service_create_rejects_duplicate_unknown_and_managed_types():
    """R40–R42: create devuelve 409/422 y no modifica registros existentes."""
    service, repository, *_ = _service()
    created = service.create(_create_request())
    original_secret = repository.get_encrypted_secrets("canal-demo")
    with pytest.raises(ChannelAlreadyExists):
        service.create(_create_request())
    with pytest.raises(UnknownAdapterType):
        service.create(_create_request(id="otro", adapter_type="no_registrado"))
    with pytest.raises(UnknownAdapterType):
        service.create(_create_request(id="telegram-nuevo", adapter_type="telegram"))
    assert repository.get_encrypted_secrets("canal-demo") == original_secret
    assert created.secret not in original_secret


def test_channel_service_create_without_key_does_not_persist():
    """R35, R40: crear sin clave responde 503 antes de guardar el canal."""
    service, repository, *_ = _service(key="")
    with pytest.raises(ChannelSecretsUnavailable):
        service.create(_create_request())
    assert repository.get("canal-demo") is None


def test_channel_service_update_only_changes_sent_fields_without_key():
    """R43: actualizar name no necesita clave ni modifica config/credenciales."""
    service, repository, cipher, *_ = _service()
    service.create(_create_request(config={"region": "uno"}))
    token = repository.get_encrypted_secrets("canal-demo")
    no_key_service, _, _, _, _ = _service(key="")
    no_key_service._repository = repository
    updated = no_key_service.update(
        "canal-demo", ChannelUpdateRequest(name="Nombre nuevo")
    )
    assert updated.name == "Nombre nuevo"
    assert updated.config == {"region": "uno"}
    assert repository.get_encrypted_secrets("canal-demo") == token
    assert cipher.decrypt(token).credentials == {"api_token": "credencial-original"}


def test_channel_service_update_credentials_replaces_them_and_preserves_secret():
    """R33, R43: credenciales reemplazan el mapa cifrado y conservan el secreto HMAC."""
    service, repository, cipher, *_ = _service()
    created = service.create(_create_request())
    updated = service.update(
        "canal-demo",
        ChannelUpdateRequest(credentials={"api_token": "credencial-nueva"}),
    )
    encrypted = repository.get_encrypted_secrets("canal-demo")
    assert encrypted is not None
    secrets = cipher.decrypt(encrypted)
    assert secrets.secret == created.secret
    assert dict(secrets.credentials) == {"api_token": "credencial-nueva"}
    assert updated.has_secrets is True


def test_channel_service_active_flag_stops_environment_following():
    """R45: PATCH active modifica active y limpia active_follows_environment."""
    service, repository, *_ = _service()
    service.list_channels()
    updated = service.set_active("whatsapp", ChannelActiveRequest(active=True))
    assert updated.active is True
    assert repository.get("whatsapp").active_follows_environment is False


def test_channel_service_regenerate_and_reveal_secret_keep_audited_values(caplog):
    """R46–R48: regenerar invalida el anterior, revela el vigente y audita sin valores."""
    generated = iter(("A" * 43, "B" * 43))
    service, repository, cipher, *_ = _service(new_secret=lambda: next(generated))
    created = service.create(_create_request())
    with caplog.at_level("INFO"):
        regenerated = service.regenerate_secret("canal-demo")
        revealed = service.reveal_secret("canal-demo")
    assert regenerated.secret != created.secret
    assert revealed.secret == regenerated.secret
    encrypted = repository.get_encrypted_secrets("canal-demo")
    assert encrypted is not None
    assert cipher.decrypt(encrypted).credentials == {"api_token": "credencial-original"}
    logs = "\n".join(record.getMessage() for record in caplog.records)
    assert "channel_secret_regenerated channel_id=canal-demo" in logs
    assert "channel_secret_revealed channel_id=canal-demo" in logs
    assert created.secret not in logs and regenerated.secret not in logs


def test_channel_service_blocks_secret_operations_on_environment_channels():
    """R44: credenciales y operaciones de secreto rechazan canales gestionados."""
    service, *_ = _service(whatsapp=FakeWhatsAppAdapter())
    service.list_channels()
    with pytest.raises(ChannelManagedByEnvironment):
        service.update(
            "telegram", ChannelUpdateRequest(credentials={"api_token": "x"})
        )
    with pytest.raises(ChannelManagedByEnvironment):
        service.regenerate_secret("telegram")
    with pytest.raises(ChannelManagedByEnvironment):
        service.reveal_secret("telegram")


def test_channel_service_reports_missing_rows_and_store_failures():
    """R26, R49: rutas de servicio distinguen 404 de fallo 503 del almacén."""
    service, repository, *_ = _service()
    with pytest.raises(ChannelNotFound):
        service.set_active("canal-ausente", ChannelActiveRequest(active=False))
    repository.fail = True
    with pytest.raises(ChannelStoreUnavailable):
        service.list_channels()
