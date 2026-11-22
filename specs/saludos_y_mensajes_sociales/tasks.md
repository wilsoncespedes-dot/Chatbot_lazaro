# Tasks — #59 `saludos_y_mensajes_sociales`

Reglas: no se edita ni se borra ningún test existente. Los tests nuevos van en
`services/orchestrator/tests/test_social_messages.py` y llevan en su docstring
el `R<n>` que cubren. No se añaden herramientas a `TOOL_MATRIX`/`TOOL_NAMES`.

## Configuración

- [x] T1 — En `services/orchestrator/orchestrator/config.py`: añadir `DEFAULT_SOCIAL_MESSAGES` y `DEFAULT_SOCIAL_REPLY` junto a `DEFAULT_HANDOVER_KEYWORDS`; añadir los campos `social_messages` y `social_reply` junto a `handover_keywords`; añadir la property `social_message_list` junto a `handover_keyword_list`, con el mismo patrón de separación por coma y `strip`. En `.env.example`, bajo el bloque del harness, añadir `SOCIAL_MESSAGES` y `SOCIAL_REPLY` con los valores de `design.md`. No tocar `REQUIRED_IN_PRODUCTION`. Cubre: R10.

- [x] T2 — En `services/orchestrator/tests/test_social_messages.py`: añadir `test_social_settings_are_read_from_env`. Con `monkeypatch.setenv`, comprobar que `Settings().social_message_list == ["hola", "gracias"]` (con espacios y una frase vacía en el raw) y que `social_reply` toma el valor configurado. El fixture de `conftest.py` ya limpia las variables del entorno. Cubre: R10.

## Detector puro

- [x] T3 — En `services/orchestrator/orchestrator/harness.py`: añadir `_social_key(text: str) -> str` e `is_social_message(text: str, phrases: list[str] | tuple[str, ...]) -> bool` según `design.md`, junto a `matches_any`. Reutilizar `normalize_text` y `re` (ya importados). Comparar por **igualdad** de forma normalizada, nunca por subcadena. Sin IO. En el mismo archivo de tests añadir `test_is_social_message_is_pure_and_exact`, parametrizado con sociales (`"hola"`, `"¡Hola!"`, `"¿Cómo estás?"`, `"gracias"`) y no sociales (`"hola como creo un usuario"`, `"hola asesor"`, `"¿cuánto cuesta?"`, `""`); comprobar además que no se muta la lista de frases. Cubre: R11, R8.

## Guardia en el orquestador

- [x] T4 — En `services/orchestrator/orchestrator/domain.py`: añadir `is_social_message` al import de `.harness` e insertar la rama de `design.md` en `_resolve_and_run`, después de frustración y antes del router y de `default_tool`, con `state == ConversationState.ACTIVE`. En `test_social_messages.py` añadir: `test_social_reply_is_sent` (R1), `test_social_reply_does_not_call_rag_or_llm` (`env.rag.calls == []` y `env.llm.calls == []`, R2 y R3) y `test_social_reply_does_not_record_failure_or_handover` (sin evento `no_results`, `env.repo.rag_outcomes == set()`, `env.handover.requests == []`, R4, R5 y R6). Usar `env.post(text="hola")`. Cubre: R1, R2, R3, R4, R5, R6.

- [x] T5 — En `test_social_messages.py`: añadir `test_non_social_message_keeps_existing_flow` (con la pregunta por defecto de `env.post`, `env.rag.calls == [("¿Cómo instalo el módulo?", 7)]` y una llamada al LLM) y `test_greeting_with_question_goes_to_rag_with_full_text` (`env.post(text="hola, ¿cómo instalo el módulo?")` → `env.rag.calls[0][0]` es el texto completo y la respuesta no es `social_reply`). Cubre: R7, R8.

- [x] T6 — En `test_social_messages.py`: añadir `test_handover_keyword_wins_over_social` con `env.post(text="hola, quiero un asesor")`: exactamente una petición en `env.handover.requests` y sin respuesta social. Cubre: R9.

## Cierre

- [x] T7 — Comprobar que `test_harness_matrix.py`, `test_decisions.py`, `test_conversation_states.py`, `test_harness_flow.py`, `test_identity_messages.py` y `test_auto_handover.py` no aparecen modificados, y ejecutar `python -m pytest services/orchestrator/tests` en verde. Único test existente ajustado: `test_multicanal_flow.py` usaba «Hola» como payload arbitrario; al pasar «Hola» a mensaje social se sustituye por `CANONICAL_TEXT` (una pregunta real) y se documenta en `progress/impl_saludos_y_mensajes_sociales.md`. Se revisó con el reviewer y aprobó que la intención del test se conserva. Comprobación de cierre (no regresión); no cubre ningún `R<n>`.

- [x] T8 — Ejecutar `./init.sh` y dejarlo en verde; escribir `progress/impl_saludos_y_mensajes_sociales.md` con el mapa de trazabilidad R1–R11 (tabla «Test que verifica cada requirement» de `requirements.md`) y el resultado de T7. Comprobación de cierre; no cubre ningún `R<n>`.
