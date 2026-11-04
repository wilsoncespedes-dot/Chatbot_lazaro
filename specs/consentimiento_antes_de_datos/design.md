# Design — consentimiento_antes_de_datos (feature #35)

## 1. Problema en el código actual

`services/orchestrator/orchestrator/domain.py::process_message` despacha `/start <token>`,
`/consultar` y `/responder`/`/cerrar` (incluido el mal formado) **antes** de `_privacy_gate`,
y en las tres ramas llama primero a `repo.get_or_create_contact(...)`. Después,
`_handle_start_token` consume el token (escribe `profiles.telegram_user_id`), `handle_db_query`
escribe `db_query_audit` y `_deny_command` escribe `events`. Todo eso ocurre para cualquier
remitente, tenga o no consentimiento.

## 2. Archivos a tocar

| Archivo | Cambio |
|---|---|
| `services/orchestrator/orchestrator/domain.py` | Constante `STAFF_ROLES`, helper `_is_linked_staff`, reorden de `process_message`. |
| `services/orchestrator/orchestrator/adapters/repository.py` | Nuevo método `get_link_token_role` en `Repository` (Protocol), `FakeRepository` y `PostgresRepository`. |
| `services/orchestrator/tests/test_consent_before_data.py` | Nuevo: pruebas de seguridad, excepción de personal, `/start`, no regresión. |
| `services/orchestrator/tests/test_privacy.py` | Ajustar `test_personal_routes_never_create_consent` y `test_personal_routes_work_without_privacy_configuration` (R19 de la #27 queda reemplazado). |
| `services/orchestrator/tests/test_accounts.py` | Añadir pruebas de `get_link_token_role` (falso y Postgres con cursor falso, mismo patrón que `test_postgres_consume_link_token_is_atomic_single_statement`). |
| `docs/proyecto.md` | §11 (fila «Datos personales»): nota de tratamiento técnico mínimo (dedup Redis con `DEDUP_TTL_SECONDS`, búfer con `MESSAGE_GROUPING_BUFFER_TTL_SECONDS`, `processed_updates` solo con `update_id`) y «consentimiento antes de cualquier dato salvo personal vinculado». |

No se tocan `contracts/`, `services/telegram_gateway/` (R23/R24 ya los cubren sus pruebas
actuales), `services/handover/`, `main.py` ni el esquema SQL.

## 3. Firmas nuevas

### Repositorio (`adapters/repository.py`)

```python
# Protocol Repository
def get_link_token_role(self, token_hash: str, now: datetime) -> str | None: ...
```

- **Fake**: busca `self.link_tokens.get(token_hash)`; si existe, `used_at is None` y
  `expires_at > now`, devuelve `self.profiles[token.profile_id].role` (o `None` si el perfil no
  existe). No muta nada; puede tomar `self._profiles_lock` para lectura coherente.
- **Postgres**: una sola sentencia, sin escrituras:
  ```sql
  SELECT p.role FROM link_tokens t JOIN profiles p ON p.id = t.profile_id
  WHERE t.token_hash = %s AND t.used_at IS NULL AND t.expires_at > %s
  ```
  con `self._run(..., (token_hash, now), fetch=True)`; devuelve `rows[0][0]` o `None`.

`get_profile_by_telegram_user_id` ya existe en las tres versiones y se reutiliza tal cual.

### Dominio (`domain.py`)

```python
STAFF_ROLES = frozenset({"asesor", "admin"})

def _is_linked_staff(request: MessageRequest, adapters: Adapters) -> bool:
    """R1, R2: solo lectura. uid <= 0 nunca es personal."""
    uid = request.telegram_user_id
    if uid <= 0:
        return False
    profile = adapters.repository.get_profile_by_telegram_user_id(uid)
    return profile is not None and profile.role in STAFF_ROLES
```

### Nuevo orden de `process_message`

```python
def process_message(request, settings, adapters) -> None:
    repo = adapters.repository
    start_token = parse_start_token(request.text)
    db_query = None
    command = None
    if start_token is None:
        db_query = parse_db_query_command(request.text, settings.db_query_max_question_length)
        if db_query is None:
            command = parse_advisor_command(request.text)

    if start_token is not None or db_query is not None or command is not None:
        exempt = _is_linked_staff(request, adapters)                       # R1, R2
        if not exempt and start_token is not None:
            role = repo.get_link_token_role(hash_token(start_token), adapters.clock())  # R3
            exempt = role in STAFF_ROLES                                    # R8
        if not exempt and not _privacy_gate(request, settings, adapters):  # R10, R15, R18
            return
        contact = repo.get_or_create_contact(request.telegram_user_id, request.chat_id, adapters.clock())
        if start_token is not None:
            _handle_start_token(request, contact, start_token, settings, adapters)
        elif db_query is not None:
            handle_db_query(request, db_query, settings, adapters)
        else:
            _handle_advisor_command(request, contact, command, settings, adapters)
        return

    if not _privacy_gate(request, settings, adapters):
        return
    ...  # ruta de texto libre sin cambios (R21)
```

Puntos clave:

- Precedencia de parseo idéntica a la actual (`/start` > `/consultar` > comando de asesor).
- Las lecturas (`get_profile_by_telegram_user_id`, `get_link_token_role`, y
  `has_privacy_consent` dentro de `_privacy_gate`) ocurren antes de cualquier escritura. La
  única escritura posible antes de pasar la compuerta es `add_privacy_consent` dentro de
  `_privacy_gate` (R19).
- Tras pasar la compuerta (exento o con consentimiento) los manejadores
  `_handle_start_token`, `handle_db_query` y `_handle_advisor_command` no cambian: la
  autorización existente se mantiene (R12–R14, R17).
- `hash_token` ya se importa en `domain.py` (lo usa `_handle_start_token`).
- `_is_linked_staff` solo se llama si el texto es comando o `/start`: el texto libre no paga
  una lectura extra.
- `privacy_acceptance_pending` y `main.py` no cambian; `mark_update_if_new` sigue guardando
  solo `update_id` (R20).

## 4. Excepciones

No se añaden. Un fallo de `get_profile_by_telegram_user_id` o `get_link_token_role` sube como
hoy (la tarea de fondo lo registra como `process_message_failed`; no hay escritura previa).

## 5. Pruebas (estrategia)

Archivo nuevo `tests/test_consent_before_data.py`, con `env`/`env_factory` de `conftest.py` y
`env.post(..., consent=False)`.

- Helper `_linked_rows(repo, uid) -> dict[str, list]` que devuelve las filas del glosario
  ligadas al remitente: contactos con ese `telegram_user_id`; mensajes, eventos, `case_links`,
  `rag_streaks`, `rag_outcomes`, `contact_created_at` de esos contactos; `db_query_audits` con
  ese `telegram_user_id`; perfiles con `telegram_user_id == uid`; tokens con `used_at` no nulo.
  Además se comprueba que `contacts`, `messages`, `events`, `db_query_audits` están vacíos en
  absoluto (repositorio nuevo), para no depender del mapeo contacto→uid.
- **Prueba de seguridad parametrizada** (R18) por ruta: texto libre, `/consultar …`,
  `/responder case-1 hola`, `/cerrar case-1`, `/responder` mal formado, `/consultar` mal
  formado, `/start <token de cliente>`. Asserts: `_linked_rows` vacío, `privacy_consents == []`,
  `gateway.sent == [(chat, PRIVACY_NOTICE_TEXT)]`, sin llamadas a handover/LLM/db_query/RAG
  (R10, R11, R15, R16), `repo.processed == {update_id}` (R20).
- Misma ruta seguida de la frase de aceptación (R19): única fila nueva = `privacy_consents`.
- Personal (`create_profile` + `repo.profiles[id].telegram_user_id = uid`, rol `asesor` y
  `admin`) sin consentimiento y también con configuración de privacidad vacía (R6, R7).
- Orden lectura→escritura (R1, R3): subclase de `FakeRepository` que registra los nombres de
  métodos llamados; se verifica que `get_profile_by_telegram_user_id` (y para `/start`,
  `get_link_token_role`) aparece antes del primer método de escritura
  (`get_or_create_contact`, `add_*`, `consume_link_token`, `link_case`, `record_rag_outcome`).
- `/start`: token de asesor/admin sin consentimiento vincula (R8); personal vinculado con
  token inválido recibe `link_failed_reply` sin aviso (R9); token de cliente → aviso, token
  intacto, después aceptación y mismo `/start` vincula (R15–R17).
- Versión cambiada (R22): consentimiento `v0` precargado; texto libre y `/consultar` de un
  no-personal no añaden mensajes, eventos ni auditorías.
- `get_link_token_role` (R4, R5) en `test_accounts.py`: válido, vencido, usado, inexistente;
  y versión Postgres con cursor falso que registra SQL: exactamente un `SELECT`, sin
  `UPDATE`/`INSERT`/`DELETE`.
- R23/R24: pruebas existentes del gateway
  (`services/telegram_gateway/tests/test_webhook.py::test_dedup_key_stored_with_ttl`,
  `services/telegram_gateway/tests/test_grouping.py::test_buffer_and_group_expire_after_ttl`,
  `services/telegram_gateway/tests/test_message_buffer.py::test_ttl_expires_buffer_and_inflight_group`).
  No se crean nuevas; se citan en la trazabilidad.

## 6. Alternativas descartadas

1. **Llamar a `_privacy_gate` para todos los mensajes, sin excepción de personal.** Rompería
   el uso de asesores sin consentimiento, que el acceptance exige mantener.
2. **Hacer `consume_link_token` condicional al rol (UPDATE con filtro `profiles.role`) en vez
   de un método de lectura.** Eliminaría la ventana de carrera de S6, pero mezcla la decisión
   de privacidad con la escritura y obliga a cambiar la firma y la sentencia atómica ya
   probada (#20/#26). El acceptance pide explícitamente «búsqueda del token de solo lectura».
3. **Responder `link_failed_reply` a tokens inválidos sin consentimiento sin crear contacto.**
   Funciona, pero introduce un camino de respuesta distinto antes de la compuerta y diferencia
   tokens válidos de inválidos para remitentes anónimos; se prefiere la regla uniforme (S1).

## 7. Riesgos y supuestos

- **S1–S5**: ver `requirements.md`.
- **S6 (riesgo residual aceptado)**: si un admin cambia el rol del dueño de un token de
  `asesor` a `cliente` entre `get_link_token_role` y `consume_link_token` (milisegundos), un
  remitente sin consentimiento podría quedar vinculado. Requiere acción simultánea de un
  administrador y el token secreto; se acepta y se documenta.
- Sin dependencias nuevas. Sin variables de entorno nuevas. Sin cambios en `contracts/`.
