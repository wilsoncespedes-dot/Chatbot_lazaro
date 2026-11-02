# #20 verificacion_cuentas — Tasks

- [x] T1 — Crear `orchestrator/accounts.py` (hash/verify PBKDF2, token, `hash_token`, `parse_start_token`) y añadir variables a `config.py` y `.env.example`. Cubre: R3, R4, R6.
- [x] T2 — Añadir tablas `profiles`/`link_tokens` y métodos `create_profile`, `get_profile`, `add_link_token`, `consume_link_token` (consulta atómica del design) en `Repository`, `FakeRepository` y `PostgresRepository`. Cubre: R1, R2, R6, R7, R8.
- [x] T3 — En `domain.py`: excepciones `UsernameTaken`/`ProfileNotFound`, `create_profile`, `issue_link_token` y `_handle_start_token` con desvío temprano en `process_message` (antes de comandos y `add_message`). Cubre: R1, R2, R4, R5, R6, R7, R9.
- [x] T4 — En `main.py`: rutas `POST /profiles` (201) y `POST /profiles/{id}/link-token` (201) con modelos locales sin campos de hash. Cubre: R1, R4, R5, R10.
- [x] T5 — `tests/test_accounts.py`: creación por cada rol y rol inválido (422), username duplicado/mayúsculas (409), hash y `verify_password`, ausencia de clave en respuesta/fila/logs (`caplog`), token emitido y su TTL con reloj fijo, 404, 401 en ambas rutas. Cubre: R1, R2, R3, R4, R5, R10.
- [x] T6 — Tests del vínculo en `tests/test_accounts.py`: vínculo correcto, token inexistente/expirado/reutilizado y cuenta ya vinculada con el mismo `link_failed_reply` y token sin consumir, carrera con dos consumos (solo uno gana; SQL de `PostgresRepository` con conexión falsa contiene `used_at IS NULL`), y que el token no aparece en `messages`/`events`/logs ni llega a RAG/LLM. Cubre: R6, R7, R8, R9.
