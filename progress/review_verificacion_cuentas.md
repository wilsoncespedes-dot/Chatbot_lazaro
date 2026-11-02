# Review — feature #20 verificacion_cuentas

**Veredicto:** APPROVED

`./init.sh` volví a ejecutarlo: 1268 passed, exit 0.

## Trazabilidad requirements ↔ tests (`services/orchestrator/tests/test_accounts.py`)
- R1: [x] `test_create_profile_returns_201_without_password` (3 roles), `test_invalid_role_returns_422`, `test_invalid_username_returns_422`, `test_short_password_returns_422`, `test_password_min_length_is_configurable`
- R2: [x] `test_duplicate_username_is_case_insensitive_and_returns_409`
- R3: [x] `test_hash_password_format_salt_and_verify`, `test_profile_password_never_appears_in_logs`, fila revisada en `test_create_profile_returns_201_without_password`
- R4: [x] `test_issue_link_token_stores_only_hash_and_uses_fixed_ttl`, `test_issue_link_token_link_is_null_without_bot_username`
- R5: [x] `test_issue_link_token_for_unknown_profile_returns_404`
- R6: [x] `test_start_token_links_sender_and_consumes_token`, `test_parse_start_token`
- R7: [x] tests para token desconocido, expirado, reutilizado y cuenta ya vinculada en otro perfil (en todos: el mismo `link_failed_reply` y el token sin consumir)
- R8: [x] `test_two_concurrent_consumptions_only_one_wins`, `test_postgres_consume_link_token_is_atomic_single_statement`
- R9: [x] el texto `/start` no llega a `messages`, `events`, `caplog`, RAG, LLM ni handover (tests de R6 y del token desconocido)
- R10: [x] `test_profile_routes_require_service_token` (sin token y con token incorrecto)

## Tasks completas
- T1–T6: [x]

## Puntos de la revisión
- **Passwords:** se usa PBKDF2-SHA256 con 600k iteraciones por defecto (mínimo 100k), una sal de 16 bytes por perfil y `hmac.compare_digest`. Ni `Profile` ni `ProfileResponse` exponen el hash. La contraseña no se registra en logs.
- **Tokens:** se generan con `token_urlsafe(32)` y solo se guarda su SHA-256. El token en claro va únicamente en la respuesta HTTP autenticada. Los cuatro tipos de fallo devuelven el mismo texto, así que no se puede saber si el perfil existe. El log solo incluye `result` y `contact_id`.
- **Atomicidad:** el CTE `UPDATE link_tokens … used_at IS NULL AND expires_at > now` seguido de `UPDATE profiles` es una sola sentencia. Si `telegram_user_id` choca con `UNIQUE`, se hace rollback y el token queda sin consumir. El candado de Python y la condición `used_at IS NULL` impiden que dos peticiones a la vez lo consuman. `create_profile` usa `ON CONFLICT (username) DO NOTHING`, que también es atómico.
- **Deduplicación de Telegram:** `mark_update_if_new` va antes de lanzar el procesamiento en segundo plano, así que un update repetido de `/start` no se procesa ni se responde dos veces. El desvío por `/start <token>` ocurre antes de `add_message` y de los comandos de asesor. El gateway no registra el texto en logs.

## Checkpoints
- C1: [x]  C2: [x]  C3: [x] (sin dependencias nuevas; variables en `.env.example`; SQL parametrizado)  C4: [x]  C5: [x]  C6: [x]

## Notas no bloqueantes (para una feature posterior)
1. `adapters/repository.py:384` — `except Exception` también captura caídas de la base de datos: en ese caso se responde `link_failed_reply` sin dejar ningún log. Conviene capturar solo la violación de `UNIQUE` y registrar `code=` en los demás casos.
2. `domain.py:549` — a diferencia de los comandos de asesor (`domain.py:452`), aquí no se rechaza `telegram_user_id <= 0`, de modo que un canal o `sender_chat` podría vincularse a un perfil. Hoy el riesgo es bajo porque el rol todavía no da permisos, pero hay que cerrarlo antes de usar el rol para autorizar.
3. `accounts.py:46` — `/start@BotName <token>`, la forma que se usa en grupos, no se reconoce y sigue el flujo normal. Eso guarda el texto (con el token) en `messages` y lo envía al RAG. Es poco probable, porque el enlace `t.me/...?start=` abre un chat privado.
4. Se quitó del DDL el `CHECK (role IN …)` que pedía el design, y el rol solo se valida en Pydantic. La desviación está justificada en `impl_verificacion_cuentas.md`.
5. No hay test unitario del SQL de `PostgresRepository.create_profile` (`ON CONFLICT`). Tampoco hay uno específico de `/start` repetido con el mismo `update_id`, aunque la deduplicación genérica ya tiene tests.
