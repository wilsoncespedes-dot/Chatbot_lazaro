"""Fixtures del orquestador: solo adaptadores falsos (sin red ni Postgres)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from lazaro_contracts import CaseListItem, SearchResult

from orchestrator.accounts import hash_token
from orchestrator.adapters.db_query import FakeDbQuery
from orchestrator.adapters.gateway import FakeGatewayClient
from orchestrator.adapters.handover import FakeHandoverClient
from orchestrator.adapters.llm import FakeLLM
from orchestrator.adapters.rag import FakeRagClient
from orchestrator.adapters.repository import FakeRepository
from orchestrator.config import Settings
from orchestrator.domain import Adapters, ClientSession
from orchestrator.main import create_app
from orchestrator.privacy import ConversationTexts, consent_button_proof, notice_sha256

SERVICE_TOKEN = "svc-token"
FIXED_NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
RECEIVED_AT = "2026-01-02T03:04:00+00:00"

PRIVACY_NOTICE_TEXT = (
    "Aviso de privacidad. Tratamos tus datos para atender tu consulta. "
    "Acepto el tratamiento de mis datos."
)
PRIVACY_NOTICE_VERSION = "v1"
PRIVACY_ACCEPT_PHRASE = "Acepto el tratamiento de mis datos."
PRIVACY_ACCEPTED_REPLY = "Gracias. Ya puedes escribirnos."
PRIVACY_RETENTION_DAYS = "30"


@pytest.fixture(autouse=True)
def _clear_settings_env(monkeypatch):
    """Aísla cada test del entorno del shell: `Settings` solo ve valores explícitos.

    pydantic-settings lee variables del proceso; sin esto, variables como
    `TELEGRAM_BOT_USERNAME` o `PRIVACY_*` definidas fuera de los tests cambian
    sus resultados (#35).
    """
    for name in Settings.model_fields:
        monkeypatch.delenv(name.upper(), raising=False)


def llm_json(answer: str, chunk_id: str, quote: str) -> str:
    return json.dumps(
        {"answer": answer, "citations": [{"chunk_id": chunk_id, "quote": quote}]},
        ensure_ascii=False,
    )


def make_chunks(n: int = 2) -> list[SearchResult]:
    return [
        SearchResult(chunk_id=f"ch{i}", manual="Manual A", text=f"texto del fragmento {i}", score=0.9)
        for i in range(1, n + 1)
    ]


@dataclass
class Env:
    client: TestClient
    repo: FakeRepository
    rag: FakeRagClient
    llm: FakeLLM
    gateway: FakeGatewayClient
    handover: FakeHandoverClient
    db_query: FakeDbQuery
    settings: Settings
    adapters: Adapters

    def post(self, text: str = "¿Cómo instalo el módulo?", update_id: int = 1, user: int = 10,
             chat: int = 100, headers: dict | None = None, consent: bool = True,
             raise_server_exceptions: bool | None = None):
        if consent:
            self.repo.add_privacy_consent(
                user,
                self.settings.privacy_notice_version,
                notice_sha256(self.settings.privacy_notice_text),
                FIXED_NOW,
            )
        body = {
            "update_id": update_id,
            "telegram_user_id": user,
            "chat_id": chat,
            "text": text,
            "received_at": RECEIVED_AT,
        }
        client = self.client
        if raise_server_exceptions is not None:
            client = TestClient(
                self.client.app, raise_server_exceptions=raise_server_exceptions
            )
        return client.post(
            "/messages", json=body,
            headers={"X-Service-Token": SERVICE_TOKEN} if headers is None else headers,
        )

    def present(
        self,
        user: int = 10,
        chat: int = 100,
        channel: str = "telegram",
    ):
        """R39: presenta el aviso para que exista un desafío pendiente."""
        body = {
            "channel": channel,
            "external_user_id": str(user),
            "external_chat_id": str(chat),
            "external_message_id": f"present-{user}",
            "kind": "text",
            "text": "Hola",
            "received_at": RECEIVED_AT,
        }
        return self.client.post(
            "/messages",
            json=body,
            headers={"X-Service-Token": SERVICE_TOKEN},
        )

    def button_proof(
        self,
        button_id: str,
        user: int = 10,
        channel: str = "telegram",
        chat: int = 100,
    ) -> str:
        """R37, R39: prueba del desafío pendiente para esta identidad."""
        challenge = self.adapters.consent_challenges.get(channel, str(user))
        if challenge is None:
            self.present(user=user, chat=chat, channel=channel)
            challenge = self.adapters.consent_challenges.get(channel, str(user))
        assert challenge is not None
        texts = self.repo.get_conversation_texts()
        return consent_button_proof(
            self.settings.service_token,
            channel,
            str(user),
            str(chat),
            button_id,
            texts.notice_version,
            notice_sha256(texts.notice_text),
            challenge.nonce,
        )

    def post_button(
        self,
        button_id: str,
        user: int = 10,
        chat: int = 100,
        message_id: str = "button-1",
        channel: str = "telegram",
        proof: str | None = None,
    ):
        body = {
            "channel": channel,
            "external_user_id": str(user),
            "external_chat_id": str(chat),
            "external_message_id": message_id,
            "kind": "button",
            "button_id": button_id,
            "button_proof": (
                proof
                if proof is not None
                else self.button_proof(
                    button_id, user=user, channel=channel, chat=chat
                )
            ),
            "received_at": RECEIVED_AT,
        }
        return self.client.post(
            "/messages",
            json=body,
            headers={"X-Service-Token": SERVICE_TOKEN},
        )

    def events(self) -> list[tuple[str, str]]:
        return [(e.type, e.reason) for e in self.repo.events]


def make_env(**settings_overrides) -> Env:
    # `seed_texts=False` simula un panel sin configurar; por defecto los tests
    # parten de los textos ya guardados por un administrador.
    seed_texts = settings_overrides.pop("seed_texts", True)
    values = {
        "service_token": SERVICE_TOKEN,
        "rag_top_k": 7,
        "privacy_notice_text": PRIVACY_NOTICE_TEXT,
        "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        "privacy_accept_phrase": PRIVACY_ACCEPT_PHRASE,
        "privacy_accepted_reply": PRIVACY_ACCEPTED_REPLY,
        "privacy_retention_days": PRIVACY_RETENTION_DAYS,
        # R44: las suites históricas prueban el flujo previo sin login; los
        # tests de #38 activan el login explícitamente.
        "identity_login_required": False,
    }
    values.update(settings_overrides)
    settings = Settings(**values)
    repo = FakeRepository()
    rag = FakeRagClient(results=make_chunks())
    llm = FakeLLM(reply=llm_json("Respuesta final", "ch1", "texto del fragmento 1"))
    gateway = FakeGatewayClient()
    handover = FakeHandoverClient()
    db_query = FakeDbQuery()
    counter = iter(range(1, 10_000))
    adapters = Adapters(
        repository=repo, rag=rag, llm=llm, gateway=gateway, handover=handover,
        db_query=db_query,
        clock=lambda: FIXED_NOW, new_id=lambda: f"case-{next(counter)}",
    )
    if seed_texts:
        repo.save_conversation_texts(
            ConversationTexts(
                notice_text=settings.privacy_notice_text,
                notice_version=settings.privacy_notice_version,
                accepted_reply=settings.privacy_accepted_reply,
                greeting=settings.conversation_greeting,
                rejected_reply=settings.conversation_rejected_reply,
                login_reminder=settings.conversation_login_reminder,
                suspended_reply=settings.conversation_suspended_reply,
                unsupported_reply=settings.conversation_unsupported_reply,
                active_welcome=settings.conversation_active_welcome,
                confirm_button_reply=settings.conversation_confirm_button_reply,
                login_link_label="Abrir el enlace de acceso",
                session_closed_reply="Tu sesión se cerró. Vuelve a iniciar sesión.",
            ),
            "test-seed",
            FIXED_NOW,
        )
    client = TestClient(create_app(settings, adapters))
    return Env(client, repo, rag, llm, gateway, handover, db_query, settings, adapters)


NOW = FIXED_NOW
CSRF = "csrf-token"


def make_profile(env, username: str, role: str = "asesor", telegram_user_id=700):
    profile = env.repo.create_profile(username, role, "hash", NOW)
    if telegram_user_id is not None:
        env.repo.profiles[profile.id].telegram_user_id = telegram_user_id
    return env.repo.get_profile(profile.id) or profile


def login(env, role: str = "asesor", username: str | None = None, telegram_user_id=700):
    username = username or ("admin1" if role == "admin" else "asesor1")
    profile = make_profile(env, username, role, telegram_user_id)
    cookie = "admin_session" if role == "admin" else "advisor_session"
    token = f"{role}-session"
    env.repo.create_session(
        hash_token(token), profile.id, CSRF, NOW + timedelta(hours=1)
    )
    env.client.cookies.set(cookie, token)
    return profile


def login_admin(env, username: str = "admin1"):
    return login(env, "admin", username, telegram_user_id=None)


def link_case(
    env,
    case_id: str = "case-1",
    channel: str = "telegram",
    user: str = "10",
    chat: str = "100",
    profile_id: str | None = None,
    created_at: datetime | None = None,
):
    contact = env.repo.get_or_create_channel_contact(channel, user, chat, NOW)
    env.repo.link_case(
        case_id, contact.id, created_at or NOW, profile_id=profile_id
    )
    return contact


def add_message(env, contact, role: str, text: str, at: datetime):
    env.repo.add_message(contact.id, role, text, at)


def case_item(
    case_id: str,
    status: str = "open",
    actions: list[str] | None = None,
    created_at: datetime | None = None,
) -> CaseListItem:
    if actions is None:
        actions = (
            ["reply", "close"]
            if status == "assigned"
            else ["reply", "assign", "close"]
        )
    return CaseListItem(
        case_id=case_id,
        status=status,  # type: ignore[arg-type]
        created_at=created_at or NOW,
        actions=actions,  # type: ignore[arg-type]
    )


def set_presence(env, profile_id: str, status: str, at: datetime | None = None):
    env.repo.set_advisor_presence(profile_id, status, at or NOW)


def add_client_session(
    env,
    session_id: str,
    profile_id: str,
    contact_id: str,
    started_at: datetime,
    last_activity_at: datetime,
    ended_at: datetime | None = None,
):
    env.repo.client_sessions[session_id] = ClientSession(
        id=session_id,
        profile_id=profile_id,
        contact_id=contact_id,
        started_at=started_at,
        last_activity_at=last_activity_at,
        ended_at=ended_at,
        end_reason=None,
    )


@pytest.fixture()
def panel():
    """Helpers compartidos del panel multicanal (#41) expuestos como fixture."""
    return SimpleNamespace(
        NOW=NOW,
        CSRF=CSRF,
        make_profile=make_profile,
        login=login,
        login_admin=login_admin,
        link_case=link_case,
        add_message=add_message,
        case_item=case_item,
        set_presence=set_presence,
        add_client_session=add_client_session,
    )


@pytest.fixture()
def env() -> Env:
    return make_env()


@pytest.fixture()
def env_factory():
    return make_env
