# Review — feature 16 (conversacion_cliente_asesor)

**Veredicto:** APPROVED

`./init.sh` en verde: 1185 passed (dato del leader; el intento 1 tenía 1183 passed y 2 failed, y los 2 tests se corrigieron en el intento 2). No volví a ejecutarlo.

## Trazabilidad requirements ↔ tests
R1-R62: [x], todos cubiertos. Comprobé que existen los tests citados en `progress/impl_conversacion_cliente_asesor.md` §Trazabilidad:
- `services/orchestrator/tests/test_advisor_commands.py`: R1-R26 y R60-R62.
- `services/orchestrator/tests/test_client_forward.py`: R27-R46.
- `services/orchestrator/tests/test_security.py:152,175,230`: T56-T58.
- `services/handover/tests/test_client_message.py`: R47-R54, R57 y R59.
- `services/handover/tests/test_security.py`:
  - ROUTES e INVALID_BODIES, l. 22 y 35-38: R55 y R56.
  - Test de la l. 110: T68.

Nota menor: T42 y T43 están juntos en `test_forward_failure_sends_fixed_text_without_rag`, parametrizado con `upstream_error` y `handover_unavailable` (`test_client_forward.py:121-138`). Cubren R32 y R33 con las mismas aserciones que pide la spec.

## Tasks
- T1-T68 y T70-T74: [x].
- T0 y T69: siguen en `[ ]`. El motivo está documentado en el informe impl: el writer no ejecuta shell. Las dos quedan satisfechas con el `./init.sh` verde. Respecto al alcance de los tests (ver abajo), las únicas líneas quitadas en tests ya existentes vienen de la #14: `test_case_reply.py:207` y `test_cases.py:45`. El leader puede marcar T0 y T69 como `[x]`.

## Alcance y hallazgos
- **Comandos.** `parse_advisor_command` (`orchestrator/domain.py:139-154`) es pura y su gramática es estricta (D1). En todas las llamadas a handover, `advisor_id` es `str(telegram_user_id)` (l. 309 y 340). `authorize(close)` va antes de `close` (l. 342-343).
- **Caso cerrado.** Con `case_closed` se envía el texto propio y no se registra `advisor_forbidden` (l. 319-324 y 351-354).
- **Reenvío.** Va después del historial y antes de las palabras clave y del RAG (l. 486-491). Ningún log contiene texto.
- **Cliente HTTP.** Falla cerrado; comprueba `case_id` y el código de error (`adapters/handover.py:137-221`).
- **Handover.** La ruta nueva está en `main.py:156-160`. `forward_client_message` no modifica el caso; envía solo `chat_id` y `text` y recorta a 4096 con `build_client_forward`. Un `advisor_id` no entero devuelve `502` sin llamar a `/send`.
- **`.env.example`.** Tiene las 8 variables (l. 46-53). El orquestador no lee `ADVISOR_CHAT_IDS`.
- **Tests existentes.** En `services/*/tests/test_security.py` solo hay líneas añadidas (design §8). En el `test_security.py` del orquestador se añaden T56-T58 sin tocar los tests previos.
- **Contratos y otras áreas.** La #16 no cambia `contracts/`, `telegram_gateway/`, `eval/`, `docker-compose.yml` ni `.github/`. El diff de esas áreas en el working tree corresponde a las #10-#15, #17 y #18, todas ya `done` y sin commit.
- **Fallos del intento 1.** Las dos correcciones son correctas y no relajan nada. La respuesta va al `chat_id` del remitente (`200`), como piden R13 y R14. El test de payload ahora construye `httpx.Response` con `request=`, sin tocar el adaptador.

## Checkpoints
- C1: [x]
- C2: [x] (solo la #16 está `in_progress`)
- C3: [x] (sin dependencias nuevas; la ruta ya está en CONTRATOS.md, #15; SQL parametrizado)
- C4: [x] (fakes y MockTransport; pruebas de seguridad T56-T58 y T68)
- C5: [ ] Lo resuelve el leader al cerrar: entrada en `progress/history.md` y estado de la #16. No bloquea esta revisión.
- C6: [x]

## Cambios requeridos
Ninguno bloqueante.
