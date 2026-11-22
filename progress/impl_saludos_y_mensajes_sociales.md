# Implementación — #59 `saludos_y_mensajes_sociales`

Estado: **done**. Revisión de código: **APROBADO** (pasada enfocada, sin puntos bloqueantes).

## Qué cambia

«hola» (y otras frases sociales exactas) ya no cae en `buscar_base_conocimiento`.
La guardia va en `domain.py::_resolve_and_run`, después de los guardrails y de
las keywords de supresión/asesor/frustración, y antes del router y de
`default_tool`. Envía `settings.social_reply` y retorna: sin `rag.search`, sin
`llm.complete`, sin `no_results`, sin `record_rag_outcome` y sin traspaso.

El detector `harness.py::is_social_message` es puro: normaliza con
`normalize_text` + `re.sub(r"[^a-z0-9]+", " ", ...)` y compara por **igualdad**.
Por eso «hola, ¿cómo instalo el módulo?» sigue yendo al RAG con el texto
completo. La detección solo se aplica en estado `ACTIVE`.

Configuración nueva: `SOCIAL_MESSAGES` y `SOCIAL_REPLY` (también en
`.env.example`), con los mismos valores por defecto del spec. No se añadió
ninguna herramienta a `TOOL_MATRIX`/`TOOL_NAMES` (siguen siendo 6).

## Trazabilidad R1–R11

| Requirement | Test | Resultado |
|---|---|---|
| R1 — respuesta social en `ACTIVE` | `test_social_messages.py::test_social_reply_is_sent` | OK |
| R2 — sin `rag.search` | `::test_social_reply_does_not_call_rag_or_llm` | OK |
| R3 — sin `llm.complete` | `::test_social_reply_does_not_call_rag_or_llm` | OK |
| R4 — sin evento `no_results` | `::test_social_reply_does_not_record_failure_or_handover` | OK |
| R5 — sin `record_rag_outcome` | `::test_social_reply_does_not_record_failure_or_handover` | OK |
| R6 — sin caso ni aviso a asesor | `::test_social_reply_does_not_record_failure_or_handover` | OK |
| R7 — el resto del flujo sigue igual | `::test_non_social_message_keeps_existing_flow` | OK |
| R8 — saludo + pregunta va al RAG con texto completo | `::test_is_social_message_is_pure_and_exact`, `::test_greeting_with_question_goes_to_rag_with_full_text` | OK |
| R9 — keyword de asesor gana | `::test_handover_keyword_wins_over_social` | OK (reforzado: el texto es social exacto y aun así escala) |
| R10 — configuración por entorno | `::test_social_settings_are_read_from_env` | OK |
| R11 — detector puro y sin mutación | `::test_is_social_message_is_pure_and_exact` | OK |
| No regresión de la matriz | `test_harness_matrix.py::test_r1_r3_matrix_decision`, `::test_r1_r2_matrix_is_complete_immutable_and_has_six_tools` | OK |

## Verificación

- `python -m pytest services/orchestrator/tests/test_social_messages.py -q` → 8 passed.
- `python -m pytest -q` → 3631 passed, 2 skipped.
- `bash init.sh` (Git Bash; `bash` de WSL no está disponible en este equipo) → **verde**, 3631 passed, 2 skipped, modo `supervisado`.

## Entorno

Faltaban dos dependencias ya declaradas en `requirements.txt` y el suite no podía
arrancar: se instalaron `cryptography>=43,<48` y `pg8000>=1.31,<2`. No son cambios
de código ni dependencias nuevas del proyecto.

## Ajuste documentado a un test existente

`services/orchestrator/tests/test_multicanal_flow.py` usaba «Hola» como payload
arbitrario para comprobar identidad de canal y respuesta RAG. Como #59 convierte
«Hola» en mensaje social, ese payload ya no ejercita lo que el test quería
probar. Se sustituyó por `CANONICAL_TEXT = "¿Cómo instalo el módulo?"` y se
actualizaron las dos aserciones de `rag.calls`. La intención del test (canal,
contactos y «Respuesta final») se conserva íntegra; la cobertura del saludo
vive ahora en `test_social_messages.py`. El reviewer lo revisó y lo aprobó.

Los otros archivos sensibles (`test_harness_matrix.py`, `test_decisions.py`,
`test_conversation_states.py`, `test_harness_flow.py`, `test_identity_messages.py`
y `test_auto_handover.py`) no se modificaron.

## Observaciones no bloqueantes del reviewer

- `SOCIAL_REPLY` por defecto empieza con «¡Hola!» también para «gracias», «ok» o
  «buenas noches»; es configurable y no es un defecto.
- No hay test explícito de «hola» en estados distintos de `ACTIVE`; el código lo
  impide con la condición `state == ConversationState.ACTIVE`.
