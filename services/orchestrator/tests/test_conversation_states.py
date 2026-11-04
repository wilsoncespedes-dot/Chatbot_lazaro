"""Máquina de siete estados, consentimiento por botón y textos fijos (#37)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from lazaro_contracts import NormalizedMessage

from orchestrator.domain import (
    ConversationEvent,
    ConversationState,
    apply_conversation_event,
    conversation_texts,
    consent_configured,
    process_channel_message,
    transition_state,
)
from orchestrator.privacy import (
    PRIVACY_ACCEPT_BUTTON,
    PRIVACY_REJECT_BUTTON,
    consent_button_proof,
    notice_sha256,
)

NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)


def _message(
    text: str | None = None,
    *,
    channel: str = "telegram",
    user: str = "10",
    chat: str = "100",
    message_id: str = "m1",
    kind: str = "text",
    button_id: str | None = None,
    button_proof: str | None = None,
) -> NormalizedMessage:
    return NormalizedMessage(
        channel=channel,  # type: ignore[arg-type]
        external_user_id=user,
        external_chat_id=chat,
        external_message_id=message_id,
        kind=kind,  # type: ignore[arg-type]
        text=text,
        button_id=button_id,
        button_proof=button_proof,
        received_at=NOW,
    )


def _proof(
    env,
    button_id: str,
    channel: str = "telegram",
    user: str = "10",
    chat: str = "100",
) -> str:
    """R39: prueba del desafío vigente; presenta el aviso si aún no existe."""
    challenge = env.adapters.consent_challenges.get(channel, user)
    if challenge is None:
        process_channel_message(
            _message("Hola", channel=channel, user=user, chat=chat),
            env.settings,
            env.adapters,
        )
        challenge = env.adapters.consent_challenges.get(channel, user)
    assert challenge is not None
    texts = env.repo.get_conversation_texts()
    return consent_button_proof(
        env.settings.service_token,
        channel,
        user,
        chat,
        button_id,
        texts.notice_version,
        notice_sha256(texts.notice_text),
        challenge.nonce,
    )


def _grant(
    env,
    channel: str = "telegram",
    user: str = "10",
    chat: str = "100",
):
    env.repo.add_channel_privacy_consent(
        channel,
        user,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        NOW,
    )
    return env.repo.get_or_create_channel_contact(channel, user, chat, NOW)


def _state(env, contact_id: str) -> ConversationState | None:
    return env.repo.get_conversation_state(contact_id)


# --- R1: estados y transiciones ----------------------------------------------------------


def test_all_seven_states_exist():
    """R1: el vocabulario tiene los siete estados del documento."""
    assert {state.value for state in ConversationState} == {
        "new",
        "awaiting_consent",
        "closed",
        "awaiting_login",
        "active",
        "with_advisor",
        "no_access",
    }


def test_transition_table_covers_the_documented_paths():
    """R1, R8, R10-R18, R26-R28: reductor puro de cada transición publicada."""
    cases = [
        (ConversationState.NEW, ConversationEvent.FIRST_MESSAGE,
         ConversationState.AWAITING_CONSENT),
        (ConversationState.AWAITING_CONSENT, ConversationEvent.ACCEPT_BUTTON,
         ConversationState.AWAITING_LOGIN),
        (ConversationState.AWAITING_CONSENT, ConversationEvent.REJECT_BUTTON,
         ConversationState.CLOSED),
        (ConversationState.CLOSED, ConversationEvent.RESTART_MESSAGE,
         ConversationState.NEW),
        (ConversationState.AWAITING_LOGIN, ConversationEvent.LOGIN_VALID,
         ConversationState.ACTIVE),
        (ConversationState.AWAITING_LOGIN, ConversationEvent.LOGIN_EXPIRED,
         ConversationState.NO_ACCESS),
        (ConversationState.ACTIVE, ConversationEvent.SESSION_CLOSED,
         ConversationState.AWAITING_LOGIN),
        (ConversationState.ACTIVE, ConversationEvent.SESSION_IDLE_TIMEOUT,
         ConversationState.AWAITING_LOGIN),
        (ConversationState.ACTIVE, ConversationEvent.CREDENTIAL_EXPIRED,
         ConversationState.NO_ACCESS),
        (ConversationState.ACTIVE, ConversationEvent.ESCALATED,
         ConversationState.WITH_ADVISOR),
        (ConversationState.WITH_ADVISOR, ConversationEvent.ADVISOR_RESOLVED,
         ConversationState.ACTIVE),
        (ConversationState.WITH_ADVISOR, ConversationEvent.ADVISOR_RETURNED,
         ConversationState.ACTIVE),
        (ConversationState.NO_ACCESS, ConversationEvent.CREDENTIAL_RENEWED,
         ConversationState.ACTIVE),
        (ConversationState.NO_ACCESS, ConversationEvent.ESCALATION_REQUESTED,
         ConversationState.WITH_ADVISOR),
        (ConversationState.NO_ACCESS, ConversationEvent.SUPPRESSION_REQUESTED,
         ConversationState.WITH_ADVISOR),
        # #38 R43: cierre de sesión desde sin acceso vuelve a esperar login.
        (ConversationState.NO_ACCESS, ConversationEvent.SESSION_CLOSED,
         ConversationState.AWAITING_LOGIN),
        (ConversationState.NO_ACCESS, ConversationEvent.SESSION_IDLE_TIMEOUT,
         ConversationState.AWAITING_LOGIN),
    ]
    for state, event, expected in cases:
        assert transition_state(state, event) == expected


def test_unsupported_and_unknown_events_keep_the_state():
    """R15: contenido no soportado no cambia el estado; un evento ajeno tampoco."""
    for state in ConversationState:
        assert (
            transition_state(state, ConversationEvent.UNSUPPORTED_MESSAGE) == state
        )
    assert (
        transition_state(ConversationState.ACTIVE, ConversationEvent.FIRST_MESSAGE)
        == ConversationState.ACTIVE
    )


# --- R2, R3, R35: antes del consentimiento ------------------------------------------------


def test_first_message_shows_greeting_notice_and_buttons_without_persisting(env):
    """R2, R35: saludo, aviso y botones; ni contacto, ni mensaje, ni estado, ni LLM."""
    process_channel_message(_message("Hola"), env.settings, env.adapters)

    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.repo.events == []
    assert env.repo.conversation_states == {}
    assert env.repo.processed_messages == set()
    assert env.rag.calls == [] and env.llm.calls == []
    [channel, destination, prompt] = env.gateway.channel_sent[0]
    assert (channel, destination) == ("telegram", "100")
    assert env.settings.conversation_greeting in prompt
    assert env.settings.privacy_notice_text in prompt
    assert "Acepto" in prompt and "No acepto" in prompt


def test_policy_question_answers_with_the_policy_and_buttons(env):
    """R3: una pregunta sobre la política recibe el aviso vigente sin LLM."""
    process_channel_message(_message("¿Qué hacen con mis datos?"), env.settings, env.adapters)

    assert env.repo.contacts == {} and env.repo.messages == []
    assert env.llm.calls == []
    assert env.settings.privacy_notice_text in env.gateway.channel_sent[0][2]


def test_text_affirmation_asks_for_the_button_and_keeps_awaiting(env):
    """R6, R34: el «sí» textual no concede; se pide confirmar con el botón."""
    process_channel_message(
        _message(env.settings.privacy_accept_phrase, message_id="m1"),
        env.settings,
        env.adapters,
    )
    process_channel_message(
        _message("sí, acepto", message_id="m2"), env.settings, env.adapters
    )

    assert env.repo.privacy_consents == []
    assert env.repo.contacts == {}
    assert env.repo.conversation_states == {}
    assert env.llm.calls == []
    assert (100, env.settings.conversation_confirm_button_reply) in env.gateway.sent
    assert "Acepto" in env.gateway.channel_sent[-1][2]


def test_policy_question_while_awaiting_consent_answers_policy(env):
    """R3: una pregunta posterior al primer mensaje recibe el aviso y los botones."""
    process_channel_message(_message("Hola", message_id="m1"), env.settings, env.adapters)
    process_channel_message(
        _message("¿Qué hacen con mis datos?", message_id="m2"),
        env.settings,
        env.adapters,
    )

    assert env.repo.contacts == {} and env.repo.messages == []
    assert env.llm.calls == []
    assert env.settings.privacy_notice_text in env.gateway.channel_sent[-1][2]
    assert "Acepto" in env.gateway.channel_sent[-1][2]


# --- R4, R5, R20, R24, R26, R29, R36: botones -------------------------------------------


def test_accept_button_records_version_hash_message_and_button(env):
    """R4, R20, R24, R26: evidencia completa y paso a esperando inicio de sesión."""
    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_ACCEPT_BUTTON,
            button_proof=_proof(env, PRIVACY_ACCEPT_BUTTON),
            message_id="btn-1",
        ),
        env.settings,
        env.adapters,
    )

    [consent] = env.repo.privacy_consents
    assert consent.channel == "telegram"
    assert consent.external_user_id == "10"
    assert consent.notice_version == env.settings.privacy_notice_version
    assert consent.notice_sha256 == notice_sha256(env.settings.privacy_notice_text)
    assert consent.result == "accepted"
    assert consent.evidence_type == "button"
    assert consent.external_message_id == "btn-1"
    assert consent.button_id == PRIVACY_ACCEPT_BUTTON
    assert consent.accepted_at == NOW
    contact = env.repo.contacts[10]
    assert _state(env, contact.id) == ConversationState.AWAITING_LOGIN
    assert env.gateway.sent[-1] == (100, env.settings.privacy_accepted_reply)


def test_reject_button_records_only_minimal_evidence_and_deletes_content(env):
    """R5, R29, R36: rechazo con evidencia mínima y sin contenido personal."""
    contact = env.repo.get_or_create_channel_contact(
        "telegram", "10", "100", NOW
    )
    env.repo.add_message(contact.id, "user", "dato personal", NOW)
    env.repo.add_event(contact.id, "rag_answer", "chunks_found", NOW)

    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_REJECT_BUTTON,
            button_proof=_proof(env, PRIVACY_REJECT_BUTTON),
            message_id="btn-r",
        ),
        env.settings,
        env.adapters,
    )

    [consent] = env.repo.privacy_consents
    assert consent.result == "rejected"
    assert consent.external_message_id == "btn-r"
    assert consent.button_id == PRIVACY_REJECT_BUTTON
    assert consent.accepted_at is None
    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.repo.events == []
    assert env.repo.conversation_states == {}
    assert env.gateway.sent[-1] == (100, env.settings.conversation_rejected_reply)


def test_rejected_conversation_restarts_from_new_on_next_message(env):
    """R8, R36: tras rechazar, el siguiente mensaje empieza de cero."""
    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_REJECT_BUTTON,
            button_proof=_proof(env, PRIVACY_REJECT_BUTTON),
            message_id="btn-r",
        ),
        env.settings,
        env.adapters,
    )
    process_channel_message(
        _message("Hola otra vez", message_id="m2"), env.settings, env.adapters
    )

    assert env.settings.conversation_greeting in env.gateway.channel_sent[-1][2]
    assert env.repo.contacts == {}
    assert env.repo.messages == []


def test_unknown_button_does_not_grant_consent(env):
    """R4, R5: un botón desconocido no registra consentimiento ni crea contacto."""
    process_channel_message(
        _message(kind="button", button_id="otro.boton", message_id="btn-x"),
        env.settings,
        env.adapters,
    )

    assert env.repo.privacy_consents == []
    assert env.repo.contacts == {}
    assert env.repo.conversation_states == {}
    assert "Acepto" in env.gateway.channel_sent[-1][2]


def test_legacy_text_acceptance_does_not_grant_the_flow(env):
    """R34: una aceptación histórica de texto no cuenta como prueba de botón."""
    env.repo.add_privacy_decision(
        "telegram",
        "10",
        env.settings.privacy_notice_version,
        "sha",
        "accepted",
        "legacy-1",
        "",
        NOW,
        evidence_type="legacy",
    )

    assert not env.repo.has_channel_privacy_consent(
        "telegram", "10", env.settings.privacy_notice_version
    )
    process_channel_message(_message("Hola"), env.settings, env.adapters)
    assert env.repo.contacts == {}
    assert env.llm.calls == []


# --- R7: cambio de versión ----------------------------------------------------------------


def test_new_policy_version_blocks_new_messages_and_requests_consent(env):
    """R7: versión nueva → aviso de nuevo y nada nuevo persistido."""
    env.repo.add_channel_privacy_consent(
        "telegram", "10", "v0", "sha-v0", NOW
    )

    process_channel_message(_message("Hola", message_id="m2"), env.settings, env.adapters)

    assert env.repo.contacts == {}
    assert env.repo.messages == []
    assert env.settings.privacy_notice_text in env.gateway.channel_sent[-1][2]


def test_consent_prompt_carries_signed_canonical_buttons(env):
    """R38, R39: el aviso viaja con IDs canónicos y prueba del nonce vigente."""
    process_channel_message(_message("Hola"), env.settings, env.adapters)

    [_channel, _destination, blocks] = env.gateway.blocks_sent[-1]
    options = blocks[-1]
    challenge = env.adapters.consent_challenges.get("telegram", "10")
    assert challenge is not None
    sha = notice_sha256(env.settings.privacy_notice_text)
    assert options.type == "options"
    assert options.option_ids == [PRIVACY_ACCEPT_BUTTON, PRIVACY_REJECT_BUTTON]
    assert options.option_proofs == [
        consent_button_proof(
            env.settings.service_token,
            "telegram",
            "10",
            "100",
            PRIVACY_ACCEPT_BUTTON,
            env.settings.privacy_notice_version,
            notice_sha256(env.settings.privacy_notice_text),
            challenge.nonce,
        ),
        consent_button_proof(
            env.settings.service_token,
            "telegram",
            "10",
            "100",
            PRIVACY_REJECT_BUTTON,
            env.settings.privacy_notice_version,
            notice_sha256(env.settings.privacy_notice_text),
            challenge.nonce,
        ),
    ]
    assert challenge.notice_sha256 == sha


def test_old_or_tampered_button_does_not_accept_the_new_policy(env):
    """R37: el clic de un aviso anterior o manipulado no registra consentimiento."""
    old = env.repo.get_conversation_texts()
    process_channel_message(_message("Hola"), env.settings, env.adapters)
    challenge = env.adapters.consent_challenges.get("telegram", "10")
    assert challenge is not None
    old_proof = consent_button_proof(
        env.settings.service_token,
        "telegram",
        "10",
        "100",
        PRIVACY_ACCEPT_BUTTON,
        old.notice_version,
        notice_sha256(old.notice_text),
        challenge.nonce,
    )
    env.repo.save_conversation_texts(
        replace(old, notice_text="Aviso publicado después", notice_version="v2"),
        "admin-1",
        NOW,
    )

    other_user_proof = consent_button_proof(
        env.settings.service_token,
        "telegram",
        "99",
        "100",
        PRIVACY_ACCEPT_BUTTON,
        "v2",
        notice_sha256("Aviso publicado después"),
        challenge.nonce,
    )
    for proof in (old_proof, other_user_proof, "manipulada"):
        process_channel_message(
            _message(
                kind="button",
                button_id=PRIVACY_ACCEPT_BUTTON,
                button_proof=proof,
                message_id=f"btn-{proof}",
            ),
            env.settings,
            env.adapters,
        )

    assert env.repo.privacy_consents == []
    assert env.repo.contacts == {}
    assert env.repo.conversation_states == {}
    assert "Aviso publicado después" in env.gateway.channel_sent[-1][2]


# --- R9-R14, R28: estados consentidos -----------------------------------------------------


def test_awaiting_login_only_sends_the_reminder(env):
    """R9: en esperando inicio de sesión no se llama a RAG ni al LLM."""
    contact = _grant(env)
    env.repo.set_conversation_state(contact.id, ConversationState.AWAITING_LOGIN, NOW)

    process_channel_message(_message("hola"), env.settings, env.adapters)

    assert env.gateway.sent[-1] == (100, env.settings.conversation_login_reminder)
    assert env.rag.calls == [] and env.llm.calls == []


def test_active_conversation_keeps_the_existing_attention_flow(env):
    """R10: en activa se conserva el flujo RAG/LLM existente."""
    contact = _grant(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)

    process_channel_message(_message("¿Cómo instalo el módulo?"), env.settings, env.adapters)

    assert env.rag.calls == [("¿Cómo instalo el módulo?", env.settings.rag_top_k)]
    assert env.llm.calls
    assert env.gateway.sent[-1] == (100, "Respuesta final")


def test_escalation_sets_with_advisor_and_forwarding_skips_the_llm(env):
    """R11, R12, R13: escalar cambia a con_asesor, reenvía y la devolución vuelve a activa."""
    contact = _grant(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)

    process_channel_message(_message("quiero hablar con un asesor"), env.settings, env.adapters)
    assert _state(env, contact.id) == ConversationState.WITH_ADVISOR
    assert env.handover.requests

    env.repo.link_case("case-1", contact.id, NOW)
    env.handover.client_message_status = "forwarded"
    process_channel_message(_message("sigo esperando", message_id="m2"), env.settings, env.adapters)
    assert env.handover.client_messages[-1][:2] == ("case-1", "sigo esperando")
    assert env.llm.calls == []

    assert (
        apply_conversation_event(contact.id, ConversationEvent.ADVISOR_RESOLVED, env.adapters)
        == ConversationState.ACTIVE
    )


def test_no_access_replies_suspended_and_escalates_without_rag(env):
    """R14, R28: sin acceso responde fijo; pedir asesor pasa a con_asesor sin RAG/LLM."""
    contact = _grant(env)
    env.repo.set_conversation_state(contact.id, ConversationState.NO_ACCESS, NOW)

    process_channel_message(_message("hola"), env.settings, env.adapters)
    assert env.gateway.sent[-1] == (100, env.settings.conversation_suspended_reply)
    assert env.rag.calls == [] and env.llm.calls == []

    process_channel_message(
        _message("quiero hablar con un asesor", message_id="m2"), env.settings, env.adapters
    )
    assert _state(env, contact.id) == ConversationState.WITH_ADVISOR
    assert env.rag.calls == [] and env.llm.calls == []


def test_no_access_suppression_request_moves_to_advisor_without_rag(env):
    """R28: la solicitud de supresión en sin_acceso pasa a con_asesor sin RAG/LLM."""
    contact = _grant(env)
    env.repo.set_conversation_state(contact.id, ConversationState.NO_ACCESS, NOW)

    process_channel_message(
        _message("quiero que borren mis datos"), env.settings, env.adapters
    )

    assert _state(env, contact.id) == ConversationState.WITH_ADVISOR
    assert env.rag.calls == [] and env.llm.calls == []


def test_with_advisor_stops_bot_replies_until_resolution(env):
    """R11, R12: con_asesor no genera respuesta del bot ni llama al LLM."""
    contact = _grant(env)
    env.repo.set_conversation_state(contact.id, ConversationState.WITH_ADVISOR, NOW)
    before = list(env.gateway.sent)

    process_channel_message(_message("sigo esperando"), env.settings, env.adapters)

    assert env.gateway.sent == before
    assert env.rag.calls == [] and env.llm.calls == []


def test_unsupported_content_gets_fixed_reply_without_state_change(env):
    """R15: audio/imagen/documento/sticker no mutan estado ni persisten contenido."""
    contact = _grant(env)
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)

    process_channel_message(
        _message(kind="unsupported", message_id="u1"), env.settings, env.adapters
    )

    assert env.gateway.sent[-1] == (100, env.settings.conversation_unsupported_reply)
    assert env.repo.messages == []
    assert _state(env, contact.id) == ConversationState.ACTIVE


# --- R16-R18, R27: eventos de credenciales y sesión --------------------------------------


def test_credential_and_session_events_update_the_state(env):
    """R16, R17, R18, R27: eventos falsos de #38 mueven la conversación."""
    contact = _grant(env)

    env.repo.set_conversation_state(contact.id, ConversationState.AWAITING_LOGIN, NOW)
    assert (
        apply_conversation_event(contact.id, ConversationEvent.LOGIN_VALID, env.adapters)
        == ConversationState.ACTIVE
    )
    assert (
        apply_conversation_event(contact.id, ConversationEvent.CREDENTIAL_EXPIRED, env.adapters)
        == ConversationState.NO_ACCESS
    )
    assert (
        apply_conversation_event(contact.id, ConversationEvent.CREDENTIAL_RENEWED, env.adapters)
        == ConversationState.ACTIVE
    )
    assert (
        apply_conversation_event(contact.id, ConversationEvent.SESSION_CLOSED, env.adapters)
        == ConversationState.AWAITING_LOGIN
    )
    assert (
        apply_conversation_event(contact.id, ConversationEvent.LOGIN_EXPIRED, env.adapters)
        == ConversationState.NO_ACCESS
    )
    env.repo.set_conversation_state(contact.id, ConversationState.ACTIVE, NOW)
    assert (
        apply_conversation_event(
            contact.id, ConversationEvent.SESSION_IDLE_TIMEOUT, env.adapters
        )
        == ConversationState.AWAITING_LOGIN
    )


# --- R21-R23, R25, R30, R31, R33: garantías y configuración -------------------------------


def test_no_fixed_or_legal_text_is_generated_by_the_llm(env):
    """R30: los textos fijos no se completan con el modelo."""
    process_channel_message(_message("hola"), env.settings, env.adapters)
    contact = _grant(env)
    env.repo.set_conversation_state(contact.id, ConversationState.NO_ACCESS, NOW)
    process_channel_message(_message("hola", message_id="m2"), env.settings, env.adapters)

    assert env.llm.calls == []


def test_missing_legal_text_fails_closed_without_persisting(env_factory):
    """R25, R33: sin aviso/versión no se habilita el flujo ni se inventa un texto."""
    env = env_factory(
        privacy_notice_text="",
        privacy_notice_version="",
        privacy_accept_phrase="",
        privacy_accepted_reply="",
        privacy_retention_days="",
    )
    assert not consent_configured(env.settings, env.adapters)

    process_channel_message(_message("hola"), env.settings, env.adapters)

    assert env.gateway.channel_sent == []
    assert env.repo.contacts == {} and env.repo.messages == []
    assert env.llm.calls == []


def test_settings_texts_are_not_a_fallback_for_the_panel(env_factory):
    """R25, R32, R33: los textos legales del entorno no sustituyen al panel."""
    env = env_factory(seed_texts=False)
    assert env.settings.privacy_notice_text
    assert not consent_configured(env.settings, env.adapters)

    process_channel_message(_message("hola"), env.settings, env.adapters)

    assert env.gateway.channel_sent == []
    assert env.repo.contacts == {} and env.repo.messages == []
    assert env.llm.calls == []


def test_identity_is_isolated_per_channel(env):
    """R23, R31: la misma identidad numérica no se asocia entre canales."""
    _grant(env, "telegram", "10", "100")
    process_channel_message(_message("hola", channel="whatsapp", user="10", chat="chat-10"),
                            env.settings, env.adapters)

    assert 10 in env.repo.contacts
    assert ("whatsapp", "10") not in env.repo.contacts
    assert "client_id" not in env.repo.contacts[10].model_fields


def test_panel_texts_are_read_at_runtime_without_restart(env):
    """R19, R21, R32: el texto guardado por el panel se usa en el siguiente mensaje."""
    from orchestrator.privacy import ConversationTexts

    env.repo.save_conversation_texts(
        ConversationTexts(
            notice_text="Aviso nuevo del panel",
            notice_version="v-panel",
            greeting="Saludo del panel",
            accepted_reply="Aceptado desde panel",
            rejected_reply="Cierre desde panel",
            login_reminder="Login desde panel",
            suspended_reply="Suspendido desde panel",
            unsupported_reply="Solo texto desde panel",
            active_welcome="Bienvenida desde panel",
            confirm_button_reply="Pulsa el botón del panel",
        ),
        "admin-1",
        NOW,
    )

    process_channel_message(_message("hola"), env.settings, env.adapters)

    prompt = env.gateway.channel_sent[-1][2]
    assert "Saludo del panel" in prompt
    assert "Aviso nuevo del panel" in prompt
    assert conversation_texts(env.settings, env.adapters).notice_version == "v-panel"


# --- R39: desafío efímero de un solo uso ---------------------------------------------------


def test_challenge_is_random_per_presentation_and_invalidates_previous_buttons(env):
    """R37, R39: cada presentación emite un nonce nuevo; el botón anterior no vale."""
    process_channel_message(_message("Hola", message_id="m1"), env.settings, env.adapters)
    first = env.adapters.consent_challenges.get("telegram", "10")
    process_channel_message(_message("Hola", message_id="m2"), env.settings, env.adapters)
    second = env.adapters.consent_challenges.get("telegram", "10")

    assert first is not None and second is not None
    assert first.nonce != second.nonce

    texts = env.repo.get_conversation_texts()
    old_proof = consent_button_proof(
        env.settings.service_token,
        "telegram",
        "10",
        "100",
        PRIVACY_ACCEPT_BUTTON,
        texts.notice_version,
        notice_sha256(texts.notice_text),
        first.nonce,
    )
    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_ACCEPT_BUTTON,
            button_proof=old_proof,
            message_id="btn-old",
        ),
        env.settings,
        env.adapters,
    )

    assert env.repo.privacy_consents == []
    assert env.repo.contacts == {}
    assert env.repo.conversation_states == {}
    assert "Acepto" in env.gateway.channel_sent[-1][2]


def test_button_from_another_chat_does_not_consume_the_challenge(env):
    """R38, R40: el mismo usuario desde otro chat no registra ni consume el desafío."""
    process_channel_message(
        _message("Hola", chat="100", message_id="m1"), env.settings, env.adapters
    )
    proof = consent_button_proof(
        env.settings.service_token,
        "telegram",
        "10",
        "100",
        PRIVACY_ACCEPT_BUTTON,
        env.settings.privacy_notice_version,
        notice_sha256(env.settings.privacy_notice_text),
        env.adapters.consent_challenges.get("telegram", "10").nonce,
    )

    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_ACCEPT_BUTTON,
            button_proof=proof,
            chat="200",
            message_id="btn-other-chat",
        ),
        env.settings,
        env.adapters,
    )

    assert env.repo.privacy_consents == []
    assert env.repo.contacts == {}
    assert env.repo.conversation_states == {}
    assert env.adapters.consent_challenges.get("telegram", "10") is not None

    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_ACCEPT_BUTTON,
            button_proof=proof,
            chat="100",
            message_id="btn-right-chat",
        ),
        env.settings,
        env.adapters,
    )

    [consent] = env.repo.privacy_consents
    assert consent.result == "accepted"
    assert env.adapters.consent_challenges.get("telegram", "10") is None


def test_button_without_a_pending_presentation_is_rejected(env):
    """R39: un callback ausente o de una presentación que no existe no concede."""
    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_ACCEPT_BUTTON,
            button_proof="f" * 32,
            message_id="btn-absent",
        ),
        env.settings,
        env.adapters,
    )

    assert env.repo.privacy_consents == []
    assert env.repo.contacts == {}
    assert env.repo.conversation_states == {}
    assert "Acepto" in env.gateway.channel_sent[-1][2]


def test_repeated_reject_after_accept_is_ignored(env):
    """R29, R39: un rechazo viejo no borra una conversación activa."""
    accept_proof = _proof(env, PRIVACY_ACCEPT_BUTTON)
    reject_proof = _proof(env, PRIVACY_REJECT_BUTTON)
    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_ACCEPT_BUTTON,
            button_proof=accept_proof,
            message_id="btn-accept",
        ),
        env.settings,
        env.adapters,
    )
    contact = env.repo.contacts[10]
    apply_conversation_event(contact.id, ConversationEvent.LOGIN_VALID, env.adapters)
    env.repo.add_message(contact.id, "user", "contenido activo", NOW)
    messages_before = list(env.repo.messages)
    state_before = _state(env, contact.id)

    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_REJECT_BUTTON,
            button_proof=reject_proof,
            message_id="btn-reject",
        ),
        env.settings,
        env.adapters,
    )

    assert [consent.result for consent in env.repo.privacy_consents] == ["accepted"]
    assert env.repo.contacts[10].id == contact.id
    assert env.repo.messages == messages_before
    assert _state(env, contact.id) == state_before == ConversationState.ACTIVE


def test_repeated_accept_after_reject_is_ignored(env):
    """R36, R39: tras rechazar, un aceptar repetido no crea contacto ni consentimiento."""
    reject_proof = _proof(env, PRIVACY_REJECT_BUTTON)
    accept_proof = _proof(env, PRIVACY_ACCEPT_BUTTON)
    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_REJECT_BUTTON,
            button_proof=reject_proof,
            message_id="btn-reject",
        ),
        env.settings,
        env.adapters,
    )

    process_channel_message(
        _message(
            kind="button",
            button_id=PRIVACY_ACCEPT_BUTTON,
            button_proof=accept_proof,
            message_id="btn-accept",
        ),
        env.settings,
        env.adapters,
    )

    [consent] = env.repo.privacy_consents
    assert consent.result == "rejected"
    assert env.repo.contacts == {}
    assert env.repo.conversation_states == {}
    assert env.repo.messages == []


def test_challenge_store_consumes_only_once():
    """R39: dos clics simultáneos del mismo botón producen una sola decisión."""
    import threading

    from orchestrator.privacy import ConsentChallengeStore

    store = ConsentChallengeStore()
    challenge = store.register("telegram", "10", "100", "v1", "sha")
    proof = consent_button_proof(
        "secret",
        "telegram",
        "10",
        "100",
        PRIVACY_ACCEPT_BUTTON,
        "v1",
        "sha",
        challenge.nonce,
    )
    barrier = threading.Barrier(2)
    results: list[bool] = []

    def click() -> None:
        barrier.wait()
        results.append(
            store.consume(
                "telegram",
                "10",
                "100",
                button_id=PRIVACY_ACCEPT_BUTTON,
                proof=proof,
                secret="secret",
                notice_version="v1",
                notice_sha="sha",
            )
        )

    threads = [threading.Thread(target=click) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(results) == [False, True]
