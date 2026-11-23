"""R1-R9: historial casual reutilizado con puertas de privacidad e identidad."""
from __future__ import annotations

from datetime import timedelta

from orchestrator import domain


GENERAL_REPLY = '{"mode":"general","answer":"Respuesta general"}'


def _prompt_history(env) -> str:
    _, user = env.llm.calls[-1]
    if "<historial>" not in user:
        return ""
    return user.split("<historial>", 1)[1].split("</historial>", 1)[0]


def _consented_contact(env):
    return env.repo.get_or_create_channel_contact("telegram", "10", "100", env.clock())


def test_optional_login_includes_recent_messages_for_same_contact(env_factory):
    """R1, R4: la sesión no es requisito si el login es opcional y hay consentimiento."""
    env = env_factory(memory_enabled=True, identity_login_required=False)
    contact = _consented_contact(env)
    env.repo.add_message(contact.id, "user", "¿Qué pregunté primero?", env.clock())
    env.repo.add_message(contact.id, "bot", "Preguntaste por los planetas.", env.clock())
    env.rag.results = []
    env.llm.reply = GENERAL_REPLY

    env.post(text="¿Qué pregunté primero?")

    history = _prompt_history(env)
    assert "¿Qué pregunté primero?" in history
    assert "Preguntaste por los planetas." in history


def test_current_message_is_removed_but_previous_same_text_is_kept(env_factory):
    """R2: solo se excluye la fila actual por rol, texto y timestamp exactos."""
    env = env_factory(memory_enabled=True, identity_login_required=False)
    contact = _consented_contact(env)
    repeated = "¿Qué pregunté primero?"
    env.repo.add_message(contact.id, "user", repeated, env.clock() - timedelta(minutes=1))
    env.rag.results = []
    env.llm.reply = GENERAL_REPLY

    env.post(text=repeated)

    history = _prompt_history(env)
    assert history.count(repeated) == 1


def test_casual_history_is_limited_to_memory_context_messages(env_factory):
    """R3: se entregan como máximo los mensajes previos configurados."""
    env = env_factory(
        memory_enabled=True,
        identity_login_required=False,
        memory_context_messages=2,
    )
    contact = _consented_contact(env)
    for index in range(5):
        env.repo.add_message(contact.id, "user", f"Anterior {index}", env.clock())
    env.rag.results = []
    env.llm.reply = GENERAL_REPLY

    env.post(text="Pregunta actual")

    history = _prompt_history(env)
    assert "Anterior 3" in history and "Anterior 4" in history
    assert "Anterior 2" not in history
    assert history.count('<mensaje rol=') == 2


def test_casual_history_is_isolated_by_contact_and_channel(env_factory):
    """R4: solo los mensajes del contacto actual llegan al prompt."""
    env = env_factory(memory_enabled=True, identity_login_required=False)
    contact = _consented_contact(env)
    other_telegram = env.repo.get_or_create_channel_contact(
        "telegram", "11", "101", env.clock()
    )
    other_whatsapp = env.repo.get_or_create_channel_contact(
        "whatsapp", "10", "57300", env.clock()
    )
    env.repo.add_message(contact.id, "user", "Historial permitido", env.clock())
    env.repo.add_message(other_telegram.id, "user", "Secreto de otro contacto", env.clock())
    env.repo.add_message(other_whatsapp.id, "user", "Secreto de otro canal", env.clock())
    env.rag.results = []
    env.llm.reply = GENERAL_REPLY

    env.post(text="Consulta actual")

    history = _prompt_history(env)
    assert "Historial permitido" in history
    assert "Secreto de otro contacto" not in history
    assert "Secreto de otro canal" not in history


def test_unconsented_contact_history_never_reaches_llm(env_factory):
    """R6: el gate de consentimiento precede a la búsqueda de historial y al LLM."""
    env = env_factory(memory_enabled=True, identity_login_required=False)
    contact = _consented_contact(env)
    env.repo.add_message(contact.id, "user", "Texto anterior privado", env.clock())
    env.rag.results = []
    env.llm.reply = GENERAL_REPLY

    env.post(text="Consulta sin aceptar", consent=False)

    assert env.llm.calls == []
    assert env.gateway.sent == [] or all(
        "Texto anterior privado" not in text for _, text in env.gateway.sent
    )


def test_memory_disabled_omits_casual_history_and_permanent_memory(env_factory):
    """R5: la bandera global apaga ambos tipos de contexto."""
    env = env_factory(memory_enabled=False, identity_login_required=False)
    contact = _consented_contact(env)
    env.repo.add_message(contact.id, "user", "Texto previo", env.clock())
    env.rag.results = []
    env.llm.reply = GENERAL_REPLY

    env.post(text="Pregunta general")

    _, user = env.llm.calls[-1]
    assert "<historial>" not in user and "<memoria>" not in user
    assert "Texto previo" not in user


def test_active_authenticated_session_keeps_existing_context(env_factory):
    """R7: una sesión activa continúa usando memoria e historial existentes."""
    env = env_factory(memory_enabled=True, identity_login_required=False)
    contact = _consented_contact(env)
    started_at = env.clock() - timedelta(minutes=5)
    session = domain.ClientSession(
        id="session-authenticated",
        profile_id="p-authenticated",
        contact_id=contact.id,
        started_at=started_at,
        last_activity_at=started_at,
    )
    env.repo.client_sessions[session.id] = session
    env.repo.set_client_memory(
        session.profile_id, ("Memoria autenticada",), session.id, started_at
    )
    env.repo.add_message(contact.id, "user", "Historial autenticado", started_at)
    env.rag.results = []
    env.llm.reply = GENERAL_REPLY

    env.post(text="Pregunta actual")

    _, user = env.llm.calls[-1]
    assert "Memoria autenticada" in user
    assert "Historial autenticado" in user


def test_required_login_does_not_fall_back_to_contact_history(env_factory):
    """R9: login obligatorio mantiene la ruta de identidad sin llamar al LLM."""
    env = env_factory(memory_enabled=True, identity_login_required=True)
    contact = _consented_contact(env)
    env.repo.add_message(contact.id, "user", "Dato que no debe salir", env.clock())
    env.rag.results = []
    env.llm.reply = GENERAL_REPLY

    env.post(text="Pregunta casual")

    assert env.llm.calls == []
    assert all("Dato que no debe salir" not in text for _, text in env.gateway.sent)


def test_context_reuses_repository_and_adds_no_storage_schema():
    """R8: la feature solo consume el repositorio y esquema actuales."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    source = (root / "services/orchestrator/orchestrator/adapters/repository.py").read_text(
        encoding="utf-8"
    )
    assert "def last_messages(self, contact_id: str, limit: int)" in source
    assert "CREATE TABLE IF NOT EXISTS messages" in source
    assert "CREATE TABLE IF NOT EXISTS conversational_" not in source
    assert domain._conversational_context.__module__ == "orchestrator.domain"
