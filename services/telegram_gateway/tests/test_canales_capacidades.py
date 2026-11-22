"""R2–R4, R6–R8 (#65): capacidades por defecto en ChannelInfo y siembra de consent_mode."""
from __future__ import annotations

from datetime import datetime, timezone

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from lazaro_contracts import ChannelListResponse
from pydantic import SecretStr

from telegram_gateway.adapters.channel_repository import (
    ChannelChanges,
    FakeChannelRepository,
    PostgresChannelRepository,
)
from telegram_gateway.adapters.dedup import FakeDedupStore
from telegram_gateway.adapters.orchestrator import FakeOrchestratorClient
from telegram_gateway.adapters.telegram import FakeTelegramClient
from telegram_gateway.adapters.whatsapp import FakeWhatsAppAdapter
from telegram_gateway.config import Settings
from telegram_gateway.domain import BUILTIN_CHANNEL_SEEDS, Adapters, ChannelRecord, ChannelSeed
from telegram_gateway.main import create_app
from telegram_gateway.registry import CHANNEL_REGISTRY

TOKEN = "service-token-test"
NOW = datetime(2026, 11, 21, 15, 0, tzinfo=timezone.utc)


def _client(repository: FakeChannelRepository, registry=None) -> TestClient:
    adapters = Adapters(
        telegram=FakeTelegramClient(),
        dedup=FakeDedupStore(),
        orchestrator=FakeOrchestratorClient(),
        whatsapp=FakeWhatsAppAdapter(),
        channels=repository,
        channel_registry=registry or CHANNEL_REGISTRY.copy(),
    )
    settings = Settings(
        service_token=TOKEN,
        telegram_webhook_secret="telegram-webhook-secret",
        telegram_bot_token="123456:BOT",
        channel_secrets_key=SecretStr(Fernet.generate_key().decode("ascii")),
        whatsapp_enabled=True,
        whatsapp_access_token=SecretStr("access"),
        whatsapp_app_secret=SecretStr("meta-app-secret"),
        whatsapp_verify_token=SecretStr("verify"),
        whatsapp_phone_number_id="phone-1",
    )
    return TestClient(create_app(settings, adapters), raise_server_exceptions=False)


def _listing(client: TestClient) -> dict:
    response = client.get("/channels", headers={"X-Service-Token": TOKEN})
    assert response.status_code == 200, response.text
    parsed = ChannelListResponse.model_validate(response.json())
    return {info.id: info for info in parsed.channels}


def _record(**changes) -> ChannelRecord:
    values = {
        "id": "canal-raro",
        "name": "Canal raro",
        "adapter_type": "tipo_fantasma",
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


def test_builtin_channels_report_default_capabilities():
    """R2, R4: whatsapp informa ventana (plantilla, sin texto libre) y telegram no."""
    with _client(FakeChannelRepository()) as client:
        infos = _listing(client)
    whatsapp = infos["whatsapp"].capabilities
    telegram = infos["telegram"].capabilities
    assert whatsapp is not None and telegram is not None
    assert (whatsapp.free_text_allowed, whatsapp.requires_template) == (False, True)
    assert (telegram.free_text_allowed, telegram.requires_template) == (True, False)


def test_simulated_channel_reports_capabilities_from_its_config():
    """R2: un canal simulado informa las capacidades de su config, sin secretos."""
    repository = FakeChannelRepository()
    repository.create(
        _record(
            id="simulado",
            adapter_type="simulado",
            config={"capabilities": {"free_text_allowed": False, "requires_template": True}},
        ),
        None,
    )
    with _client(repository) as client:
        info = _listing(client)["simulado"]
    assert info.capabilities is not None
    assert info.capabilities.free_text_allowed is False
    assert info.capabilities.requires_template is True


def test_unregistered_adapter_type_reports_no_capabilities():
    """R3: un tipo de adaptador sin factory devuelve capabilities=None."""
    repository = FakeChannelRepository()
    repository.create(_record(), None)
    with _client(repository) as client:
        info = _listing(client)["canal-raro"]
    assert info.capabilities is None
    assert info.configured is False


def test_factory_without_default_capabilities_reports_none():
    """R3: un tipo registrado que no informa capacidades por defecto da None."""
    registry = CHANNEL_REGISTRY.copy()

    @registry.register("tipo_mudo")
    class MuteFactory:
        managed_by_environment = False

        @classmethod
        def is_available(cls, context):
            return True

        @classmethod
        def build(cls, record, context, secrets):
            raise AssertionError("no debe construirse para listar")

    repository = FakeChannelRepository()
    repository.create(_record(id="canal-mudo", adapter_type="tipo_mudo"), None)
    with _client(repository, registry) as client:
        info = _listing(client)["canal-mudo"]
    assert info.capabilities is None
    assert info.configured is True


def test_builtin_seeds_carry_consent_mode():
    """R6: las semillas definen consent_mode texto (telegram) y boton (whatsapp)."""
    seeds = {seed.id: seed for seed in BUILTIN_CHANNEL_SEEDS}
    assert seeds["telegram"].config == {"consent_mode": "texto"}
    assert seeds["whatsapp"].config == {"consent_mode": "boton"}


def test_fake_seed_creates_rows_with_consent_mode():
    """R6: la siembra crea las filas nuevas con su consent_mode."""
    repository = FakeChannelRepository(clock=lambda: NOW)
    repository.seed([(seed, True) for seed in BUILTIN_CHANNEL_SEEDS])
    rows = {record.id: record for record in repository.list_channels()}
    assert rows["telegram"].config == {"consent_mode": "texto"}
    assert rows["whatsapp"].config == {"consent_mode": "boton"}


def test_fake_seed_fills_missing_consent_mode_without_touching_other_keys():
    """R7: una fila existente sin consent_mode recibe el valor sembrado y conserva el resto."""
    repository = FakeChannelRepository(clock=lambda: NOW)
    seed = ChannelSeed("telegram", "Telegram", "telegram", "telegram", "#1B6FA8")
    repository.seed([(seed, True)])
    repository.update("telegram", ChannelChanges(config={"region": "co"}))
    repository.seed([(BUILTIN_CHANNEL_SEEDS[0], True)])
    record = next(r for r in repository.list_channels() if r.id == "telegram")
    assert record.config == {"region": "co", "consent_mode": "texto"}


def test_fake_seed_never_overwrites_stored_consent_mode():
    """R8: si la fila ya tiene consent_mode, la siembra no lo cambia."""
    repository = FakeChannelRepository(clock=lambda: NOW)
    repository.seed([(BUILTIN_CHANNEL_SEEDS[1], True)])
    repository.update("whatsapp", ChannelChanges(config={"consent_mode": "texto"}))
    repository.seed([(BUILTIN_CHANNEL_SEEDS[1], True)])
    repository.seed([(BUILTIN_CHANNEL_SEEDS[1], True)])
    record = next(r for r in repository.list_channels() if r.id == "whatsapp")
    assert record.config == {"consent_mode": "texto"}


class _Cursor:
    def __init__(self, log):
        self.log = log

    def execute(self, sql, params=()):
        self.log.append((sql, tuple(params or ())))

    def fetchall(self):
        return []

    def fetchone(self):
        return None


class _Connection:
    def __init__(self):
        self.log: list[tuple[str, tuple]] = []

    def cursor(self):
        return _Cursor(self.log)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_postgres_seed_inserts_config_and_fills_only_missing_keys():
    """R6–R8: INSERT con la config sembrada y UPDATE `semilla || config` condicionado."""
    conn = _Connection()
    repository = PostgresChannelRepository("postgresql://test", connect=lambda: conn)
    repository.seed([(BUILTIN_CHANNEL_SEEDS[1], True)])
    insert = next((sql, p) for sql, p in conn.log if sql.startswith("INSERT INTO canales"))
    assert '{"consent_mode":"boton"}' in insert[1]
    fill = next((sql, p) for sql, p in conn.log if "|| config" in sql)
    assert "CAST(%s AS JSONB) || config" in fill[0]
    assert "NOT (CAST(%s AS JSONB) <@ config)" in fill[0]
    assert fill[1] == ('{"consent_mode":"boton"}', "whatsapp", '{"consent_mode":"boton"}')
