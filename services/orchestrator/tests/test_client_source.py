"""Puerto FuenteDeClientes y tarjeta «a futuro» de Lázaro (#76)."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from orchestrator.client_id import PublicIdTaken, normalize_public_id
from orchestrator.client_source import FuenteClientesLocal, FuenteDeClientes
from orchestrator.domain import (
    UsernameTaken,
    client_source_of,
    create_client,
    list_clients_admin,
    renew_credential,
    revoke_credential,
    search_client_by_public_id,
)

PASSWORD = "clave-segura-123"
CSRF = "csrf-token"
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
PUBLIC_ID = "ABCD-2345"
FUTURE_CARD_TEXT = (
    "A futuro, esta sección podría conectarse a la API de Lazaro para traer los "
    "clientes automáticamente y mantenerlos sincronizados (evitando clientes "
    "creados o eliminados solo en un sistema). El bot podría identificar al "
    "cliente por el ID que entrega en el chat y buscarlo en los datos de Lazaro."
)


def _root() -> Path:
    return Path(__file__).resolve().parents[3]


def _create(repo, username: str = "cliente1", public_id: str = PUBLIC_ID):
    return repo.create_client_credential(
        username,
        "hash",
        NOW,
        NOW + timedelta(days=30),
        NOW,
        public_id=public_id,
    )


class SpyFuente:
    """Delega en la fuente local y registra cada llamada al puerto."""

    def __init__(self, repository) -> None:
        self._local = FuenteClientesLocal(repository)
        self.calls: list[tuple] = []

    def buscar_por_id(self, public_id: str):
        self.calls.append(("buscar_por_id", public_id))
        return self._local.buscar_por_id(public_id)

    def listar(self):
        self.calls.append(("listar",))
        return self._local.listar()

    def crear(
        self,
        username,
        password_hash,
        valid_from,
        valid_until,
        now,
        public_id,
    ):
        self.calls.append(("crear", username, public_id))
        return self._local.crear(
            username, password_hash, valid_from, valid_until, now, public_id
        )

    def actualizar(self, profile_id, now, *, valid_until=None, revocar=False):
        self.calls.append(("actualizar", profile_id, valid_until, revocar))
        return self._local.actualizar(
            profile_id, now, valid_until=valid_until, revocar=revocar
        )

    def obtener_credencial(self, profile_id):
        self.calls.append(("obtener_credencial", profile_id))
        return self._local.obtener_credencial(profile_id)


# --- Fuente local -----------------------------------------------------------------


def test_local_find_by_id_and_missing(env):
    """R3, R4: devuelve credencial y contactos vinculados; None si no existe."""
    profile = _create(env.repo)
    contact = env.repo.get_or_create_channel_contact(
        "telegram", "10", "100", NOW
    )
    env.repo.register_client_login(
        profile.id, "telegram", "10", env.settings.privacy_notice_version, NOW
    )
    source = FuenteClientesLocal(env.repo)

    found = source.buscar_por_id(PUBLIC_ID)

    assert found is not None
    assert found.profile.public_id == PUBLIC_ID
    assert found.credential.profile_id == profile.id
    assert found.credential.valid_until == NOW + timedelta(days=30)
    assert [item.id for item in found.contacts] == [contact.id]
    assert source.buscar_por_id("ZZZZ-ZZZZ") is None


def test_local_list_matches_repository(env):
    """R5: lista todos los clientes con credencial en el orden del repositorio."""
    _create(env.repo, username="zeta", public_id="ZZZZ-2345")
    _create(env.repo, username="alfa", public_id="ALFA-2345")
    source = FuenteClientesLocal(env.repo)

    assert source.listar() == env.repo.list_client_credentials()
    assert [row.profile.username for row in source.listar()] == ["alfa", "zeta"]


def test_local_create_returns_profile_with_public_id(env):
    """R6: crea perfil `cliente` y credencial, y devuelve el ID indicado."""
    source = FuenteClientesLocal(env.repo)

    profile = source.crear(
        "Cliente1",
        "hash",
        NOW,
        NOW + timedelta(days=15),
        NOW,
        PUBLIC_ID,
    )

    assert profile.username == "cliente1"
    assert profile.role == "cliente"
    assert profile.public_id == PUBLIC_ID
    credential = env.repo.get_client_credential(profile.id)
    assert credential is not None
    assert credential.valid_until == NOW + timedelta(days=15)


def test_local_create_duplicate_public_id_raises(env):
    """R7: un ID público ya usado propaga PublicIdTaken."""
    _create(env.repo)
    source = FuenteClientesLocal(env.repo)

    with pytest.raises(PublicIdTaken):
        source.crear(
            "otro", "hash", NOW, NOW + timedelta(days=15), NOW, PUBLIC_ID
        )


def test_local_create_duplicate_username_raises(env):
    """R8: un usuario existente propaga UsernameTaken."""
    _create(env.repo)
    source = FuenteClientesLocal(env.repo)

    with pytest.raises(UsernameTaken):
        source.crear(
            "cliente1", "hash", NOW, NOW + timedelta(days=15), NOW, "ZZZZ-2345"
        )


def test_local_update_renews_revokes_and_rejects(env):
    """R9, R10, R11: renueva, revoca y rechaza sin modificar datos."""
    profile = _create(env.repo)
    source = FuenteClientesLocal(env.repo)
    new_until = NOW + timedelta(days=60)

    assert source.actualizar(profile.id, NOW, valid_until=new_until) is True
    assert env.repo.get_client_credential(profile.id).valid_until == new_until

    assert source.actualizar(profile.id, NOW, revocar=True) is True
    assert env.repo.get_client_credential(profile.id).revoked_at == NOW

    assert source.actualizar(profile.id, NOW, valid_until=new_until) is False
    credential = env.repo.get_client_credential(profile.id)
    assert credential.valid_until == new_until
    assert credential.revoked_at == NOW

    assert source.actualizar("no-existe", NOW, valid_until=new_until) is False
    assert source.actualizar("no-existe", NOW, revocar=True) is False

    with pytest.raises(ValueError):
        source.actualizar(profile.id, NOW, valid_until=new_until, revocar=True)


# --- Integración con el dominio ---------------------------------------------------


def test_default_source_is_local_and_injectable(env_factory):
    """R1, R12: el puerto expone sus operaciones y resuelve la fuente local."""
    assert {
        "buscar_por_id",
        "listar",
        "crear",
        "actualizar",
        "obtener_credencial",
    } <= set(dir(FuenteDeClientes))
    env = env_factory()

    default = client_source_of(env.adapters)
    assert isinstance(default, FuenteClientesLocal)
    assert default.buscar_por_id("ZZZZ-ZZZZ") is None

    spy = SpyFuente(env.repo)
    env.adapters.client_source = spy
    assert client_source_of(env.adapters) is spy


def test_admin_create_client_goes_through_port(env_factory, panel):
    """R13: POST /admin/clientes crea por el puerto y redirige a la lista."""
    env = env_factory(admin_cookie_secure=False, password_scrypt_n=16384)
    panel.login_admin(env)
    spy = SpyFuente(env.repo)
    env.adapters.client_source = spy

    response = env.client.post(
        "/admin/clientes",
        data={"csrf_token": CSRF, "username": "cliente1", "password": PASSWORD},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/clientes"
    assert [call[0] for call in spy.calls] == ["crear"]
    stored = next(p for p in env.repo.profiles.values() if p.username == "cliente1")
    assert stored.role == "cliente"


def test_post_clients_api_goes_through_port(env_factory):
    """R17: POST /clients crea por el puerto y mantiene la respuesta 201."""
    env = env_factory(password_scrypt_n=16384)
    spy = SpyFuente(env.repo)
    env.adapters.client_source = spy

    response = env.client.post(
        "/clients",
        json={"username": "cliente1", "password": PASSWORD},
        headers={"X-Service-Token": env.settings.service_token},
    )

    assert response.status_code == 201
    assert [call[0] for call in spy.calls] == ["crear"]
    assert response.json()["username"] == "cliente1"


def test_list_renew_revoke_and_search_use_port(env_factory):
    """R14, R15, R16: listar, renovar, revocar y buscar pasan por el puerto."""
    env = env_factory(password_scrypt_n=16384)
    created = create_client(
        "cliente1", PASSWORD, None, None, env.settings, env.adapters
    )
    spy = SpyFuente(env.repo)
    env.adapters.client_source = spy

    rows = list_clients_admin(env.settings, env.adapters)
    assert [row.username for row in rows] == ["cliente1"]

    renew_credential(created.profile_id, env.settings, env.adapters)
    revoke_credential(created.profile_id, env.settings, env.adapters)

    public_id = normalize_public_id(created.public_id or "")
    view = search_client_by_public_id(public_id, env.settings, env.adapters)
    assert view is not None
    assert view.public_id == created.public_id

    kinds = [call[0] for call in spy.calls]
    assert kinds == [
        "listar",
        "obtener_credencial",
        "actualizar",
        "obtener_credencial",
        "actualizar",
        "buscar_por_id",
    ]
    renew_call = spy.calls[2]
    revoke_call = spy.calls[4]
    assert renew_call[2] is not None and renew_call[3] is False
    assert revoke_call[2] is None and revoke_call[3] is True


# --- Tarjeta y ausencia de conexión simulada --------------------------------------


def _admin_env(env_factory, panel):
    env = env_factory(admin_cookie_secure=False)
    panel.login_admin(env)
    return env


def test_clients_page_shows_future_card_exact_text(env_factory, panel):
    """R18, R19, R20: tarjeta visible, también en error, sin controles."""
    env = _admin_env(env_factory, panel)

    page = env.client.get("/admin/clientes")
    assert page.status_code == 200
    match = re.search(
        r'<section class="card" id="futuro-lazaro">(.*?)</section>',
        page.text,
        re.S,
    )
    assert match is not None
    card = match.group(1)
    assert FUTURE_CARD_TEXT in card
    assert not re.search(r"<(form|button|a|input)\b", card, re.IGNORECASE)

    invalid = env.client.post(
        "/admin/clientes",
        data={"csrf_token": CSRF, "username": "ab", "password": PASSWORD},
        follow_redirects=False,
    )
    assert invalid.status_code == 422
    error_match = re.search(
        r'<section class="card" id="futuro-lazaro">(.*?)</section>',
        invalid.text,
        re.S,
    )
    assert error_match is not None
    assert FUTURE_CARD_TEXT in error_match.group(1)


def test_no_lazaro_source_in_code_or_config():
    """R21: no hay clase, módulo ni variable que simule la API de Lázaro."""
    root = _root()
    self_path = Path(__file__).resolve()
    forbidden = re.compile(
        "Lazaro" + "ClientSource" + "|" + "lazaro" + r"_client(?!es)"
    )
    offenders = []
    for folder in ("services", "contracts", "scripts"):
        for path in (root / folder).rglob("*.py"):
            if path.resolve() == self_path:
                continue
            if forbidden.search(path.read_text(encoding="utf-8")):
                offenders.append(path.relative_to(root).as_posix())
    assert offenders == []

    env_example = (root / ".env.example").read_text(encoding="utf-8")
    assert not re.search(
        r"(?m)^\s*[A-Z0-9_]*LAZARO[A-Z0-9_]*\s*=", env_example
    )


def test_clients_page_lazaro_only_in_future_card(env_factory, panel):
    """R22: ninguna mención a Lázaro fuera de la tarjeta informativa."""
    env = _admin_env(env_factory, panel)

    html = env.client.get("/admin/clientes").text
    without_card = re.sub(
        r'<section class="card" id="futuro-lazaro">.*?</section>',
        "",
        html,
        flags=re.S,
    )
    assert not re.search(r"l[áa]zaro", without_card, re.IGNORECASE)


def test_docs_describe_lazaro_adapter_as_future_only():
    """R23, R24, R25: el adaptador solo se describe como posibilidad."""
    text = (_root() / "docs" / "architecture.md").read_text(encoding="utf-8")
    section = text.split(
        "### Fuente de clientes y adaptador", 1
    )[1].split("### Hoja de estilos", 1)[0]
    lowered = " ".join(section.lower().split())

    assert "Lazaro" + "ClientSource" in section
    assert "posibilidad a futuro, no implementada" in lowered
    assert "buscar_por_id" in section or "buscar por id" in lowered
    assert "listar" in lowered
    assert "sincroniz" in lowered
    assert "duplicad" in lowered
    assert "borrad" in lowered
    assert "no es un compromiso" in lowered
