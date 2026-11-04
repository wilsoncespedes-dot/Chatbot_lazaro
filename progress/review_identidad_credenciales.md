# Review — feature #38 identidad_credenciales

**Veredicto:** CHANGES_REQUESTED

Verificado sin hallazgos: token `<nonce>.<hmac>` con `compare_digest`, sin consultar el repo si la firma falla, de un solo uso, con caducidad e invalidación de los anteriores (Fake y Postgres). Scrypt con prefijo, compatibilidad PBKDF2 y hash ficticio. Bloqueo por usuario/IP antes de verificar. Índices parciales y CTE atómica en Postgres. Filtro `uvicorn.access`. `IDENTITY_LOGIN_REQUIRED` + validación de producción. `.env.example`/`render.yaml`. T0–T22 `[x]`, R1–R50 trazados a tests. Los 3 tests corregidos no debilitan la cobertura: 202 es el contrato de `/messages`; el test de R9 sigue fijando `login_link_label=""`; el de R27 ahora también comprueba que el ganador queda consumido. `./init.sh` verde según el leader (no repetido).

## Cambios requeridos
1. **R28 incumplido.** En `services/orchestrator/orchestrator/domain.py:1726-1731` `touch_client_session` solo se llama si `state != WITH_ADVISOR`, y es el único punto donde se llama. Mientras el cliente habla con un asesor, `last_activity_at` no avanza. Cuando el asesor resuelve (→ `active`), el siguiente mensaje cae en `_idle_expired` (l.1727) y se cierra la sesión de inmediato si la atención duró ≥ 60 min. R28 es incondicional: hay que actualizar la actividad siempre que haya sesión y solo saltarse la expiración en `with_advisor`. Falta el test que lo cubre: un mensaje en `with_advisor` actualiza `last_activity_at` (hoy `test_with_advisor_session_does_not_expire` no lo comprueba).
2. **R30 / design §Decisiones 4 en el login.** En `domain.py:810-813` `login_client` cierra por `idle` la sesión activa del perfil sin mirar si su contacto está en `with_advisor`. Un segundo login de la misma credencial desde otro chat expulsa al contacto que está siendo atendido por un asesor; el punto 1 lo agrava. La sesión de un contacto en `with_advisor` debe tratarse como no expirada (→ `SessionConflict` 409). Hace falta un test en `test_identity_login.py`.
3. **Errores de BD reportados como conflicto.** En `services/orchestrator/orchestrator/adapters/repository.py:2416-2419` `PostgresRepository.start_client_session` captura `Exception` y devuelve `"conflict"`. Así, una caída de conexión o un error SQL se responde como 409 «sesión activa» y deja un audit `login_conflict` falso. El design solo convierte `UniqueViolation` en conflicto. Hay que capturar `psycopg.errors.UniqueViolation`, hacer rollback y relanzar el resto.

## Checkpoints
- C1–C2, C4–C6: [x] (C6 «cada R cubierto» queda [ ] hasta añadir el test del punto 1)
- C3: [x] (sin dependencias nuevas, sin cambios en contracts, sin secretos)

## Re-revisión (ciclo 1)
**Veredicto:** APROBADO
- Punto 1 (R28): `domain.py:1733-1742` llama a `touch_client_session` siempre que hay sesión; `with_advisor` solo exime de `_idle_expired`. `test_with_advisor_session_does_not_expire` afirma `last_activity_at == later` (l.144).
- Punto 2 (R30): `domain.py:810-818` responde `SessionConflict` + audit `login_conflict` si el contacto de la sesión está en `with_advisor`, antes de evaluar `idle`. Test `test_with_advisor_session_is_not_treated_as_idle_on_login` en verde.
- Punto 3: `repository.py:2429-2436` hace rollback y solo devuelve `"conflict"` si `_is_unique_violation` (l.1407); el resto se relanza. Correcto para pg8000: los errores de servidor se lanzan como `DatabaseError` con `args[0]` = dict de campos del backend, donde `"C"` es el SQLSTATE; el rollback es obligatorio porque la transacción queda abortada. Test `test_postgres_start_session_only_maps_unique_violation_to_conflict` cubre 23505 → conflict y otro error → propagado.
- Tests de identidad (messages/login/repository): todos en verde; `./init.sh` verde según el leader (2405 passed).
- C6: [x] (R28 y R30 ya tienen test).
