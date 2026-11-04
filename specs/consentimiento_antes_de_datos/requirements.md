# Requirements — consentimiento_antes_de_datos (feature #35)

> Fuente de verdad: `acceptance` de la #35 en `feature_list.json`. Contexto legal: Decreto 1377
> de 2013 (autorización a más tardar al recoger los datos) y `docs/especificacion.md`, fila
> «Tratamiento de datos» y sección del orden de la conversación («el consentimiento va antes…
> porque desde el primer mensaje ya se recogen datos personales»). Solo se corrige el orden de
> la compuerta en el orchestrator; botones Acepto/No acepto, registro de rechazo y máquina de
> estados (fase 2) quedan **fuera de alcance**. Sin contratos nuevos.
>
> Esta feature **reemplaza** el R19 de `specs/privacidad_y_retencion_datos/requirements.md`
> («rutas de personal igual que antes con o sin consentimiento»): ahora solo el personal
> vinculado queda exento (R6–R9 de este spec). Los demás R de la #27 siguen vigentes.

## Glosario

- **Consentimiento vigente**: fila de `privacy_consents` del `telegram_user_id` remitente con
  `notice_version` igual a `PRIVACY_NOTICE_VERSION` actual (`has_privacy_consent`).
- **Personal vinculado**: remitente con `telegram_user_id > 0` para el que
  `get_profile_by_telegram_user_id(telegram_user_id)` devuelve un perfil con rol `asesor` o
  `admin`.
- **Token de personal**: token de `/start <token>` para el que `get_link_token_role` (nuevo,
  solo lectura) devuelve `asesor` o `admin`.
- **Comandos de personal**: textos que hoy reconocen `parse_db_query_command` (`/consultar`,
  bien o mal formado) y `parse_advisor_command` (`/responder`, `/cerrar` y cualquier intento
  mal formado con esos prefijos).
- **Texto libre**: todo mensaje que no es `/start <token>` ni comando de personal.
- **Datos ligados al remitente**: filas que el orchestrator escribe en `contacts`, `messages`,
  `events`, `db_query_audit`, `case_links`, `auto_handover_streaks`, `auto_handover_outcomes`
  y la columna `profiles.telegram_user_id` (más `link_tokens.used_at` del token enviado). En el
  repositorio falso: `contacts`, `contact_created_at`, `messages`, `events`, `case_links`,
  `case_link_created_at`, `rag_streaks`, `rag_outcomes`, `rag_outcome_at`, `db_query_audits`,
  `profiles[*].telegram_user_id` y `link_tokens[*].used_at`.

## Supuestos explícitos

- **S1** — El acceptance solo habla de token de perfil `cliente`. Un token inexistente,
  vencido o ya usado se trata igual que uno de cliente (pasa por `_privacy_gate`): sin
  consentimiento no se puede crear contacto para responder «vínculo fallido» sin violar la
  regla general; con consentimiento vigente se responde `link_failed_reply` como hoy.
- **S2** — El personal vinculado que envía `/start <token>` queda exento como en sus comandos
  (procesado como hoy), porque ya es personal identificado.
- **S3** — Con la configuración de privacidad incompleta, los comandos y `/start` de quien no
  es personal se descartan como el texto libre (log `privacy_not_configured`, sin respuesta);
  producción exige la configuración completa (#27 R1).
- **S4** — «Como hoy» para el personal incluye que `get_or_create_contact` cree su fila en
  `contacts`: la regla de esta feature protege a quien no es personal.
- **S5** — La exención de `/consultar` alcanza a `admin` (lo pide el acceptance), pero la
  autorización de `handle_db_query` sigue exigiendo `asesor`: un `admin` recibe
  `db_query_forbidden_reply` y su fila de auditoría como hoy.

## Orchestrator — detección de personal (solo lectura)

### R1
CUANDO llega un comando de personal, el orchestrator DEBE consultar
`get_profile_by_telegram_user_id` del remitente antes de llamar a cualquier método de escritura
del repositorio.

### R2
SI el remitente tiene `telegram_user_id <= 0` ENTONCES el orchestrator NO DEBE tratarlo como
personal vinculado.

### R3
CUANDO llega `/start <token>` de un remitente que no es personal vinculado, el orchestrator
DEBE obtener el rol del dueño del token con `get_link_token_role(hash_token(token), clock())`
antes de llamar a cualquier método de escritura del repositorio.

### R4
El método `get_link_token_role` (repositorio falso y Postgres) DEBE devolver el rol del perfil
dueño del token solo si el token existe, `used_at` es nulo y `expires_at > now`; en otro caso
DEBE devolver `None`.

### R5
El método `get_link_token_role` NO DEBE modificar `link_tokens` ni `profiles` (en Postgres:
una sola sentencia `SELECT`, sin `UPDATE`, `INSERT` ni `DELETE`).

## Orchestrator — excepción de personal

### R6
MIENTRAS el remitente es personal vinculado, CUANDO envía un comando de personal, el
orchestrator DEBE procesarlo igual que antes de esta feature sin pasar por `_privacy_gate`, con
o sin consentimiento vigente y con o sin configuración de privacidad completa.

### R7
CUANDO ocurre R6, el orchestrator NO DEBE enviar `PRIVACY_NOTICE_TEXT` ni crear filas en
`privacy_consents`.

### R8
CUANDO llega `/start <token>` con un token de personal, el orchestrator DEBE vincular el perfil
y responder `link_success_reply` como antes de esta feature, con o sin consentimiento vigente
del remitente.

### R9
MIENTRAS el remitente es personal vinculado, CUANDO envía `/start <token>`, el orchestrator
DEBE procesarlo igual que antes de esta feature sin pasar por `_privacy_gate` (S2).

## Orchestrator — remitentes que no son personal

### R10
MIENTRAS el remitente no es personal vinculado y no tiene consentimiento vigente, CUANDO envía
un comando de personal, el orchestrator DEBE enviar `PRIVACY_NOTICE_TEXT` a su `chat_id`.

### R11
CUANDO ocurre R10, el orchestrator NO DEBE llamar a `handover`, al LLM ni a `db_query`.

### R12
MIENTRAS el remitente no es personal vinculado y tiene consentimiento vigente, CUANDO envía
`/consultar`, el orchestrator DEBE responder `db_query_forbidden_reply` y guardar la auditoría
`forbidden`, como antes de esta feature.

### R13
MIENTRAS el remitente no es personal vinculado y tiene consentimiento vigente, CUANDO envía
`/responder <id> <texto>` o `/cerrar <id>`, el orchestrator DEBE delegar la autorización en
`handover` como antes de esta feature y, si es denegada, responder
`advisor_command_forbidden_reply`.

### R14
MIENTRAS el remitente no es personal vinculado y tiene consentimiento vigente, CUANDO envía un
comando de asesor mal formado, el orchestrator DEBE responder `advisor_command_help` como antes
de esta feature.

## Orchestrator — `/start <token>` de quien no es personal

### R15
MIENTRAS el remitente no es personal vinculado y no tiene consentimiento vigente, CUANDO envía
`/start <token>` con un token que no es de personal (de cliente, o inexistente, vencido o
usado: S1), el orchestrator DEBE enviar `PRIVACY_NOTICE_TEXT` a su `chat_id`.

### R16
CUANDO ocurre R15, el orchestrator NO DEBE marcar el token como usado ni escribir
`telegram_user_id` en `profiles`.

### R17
CUANDO un remitente que recibió R15 con un token de cliente acepta la política y reenvía el
mismo `/start <token>` antes de que venza, el orchestrator DEBE vincular el perfil cliente a su
`telegram_user_id` y responder `link_success_reply`.

## Orchestrator — regla general (prueba de seguridad obligatoria)

### R18
MIENTRAS el remitente no tiene consentimiento vigente y no está exento (R6, R8, R9), CUANDO
envía texto libre, `/consultar`, `/responder`, `/cerrar`, un comando mal formado o
`/start <token>` con token de cliente, el orchestrator NO DEBE dejar ningún dato ligado al
remitente en el repositorio.

### R19
CUANDO, en el escenario de R18, el remitente envía después la frase de aceptación, el
orchestrator DEBE dejar como única fila nueva ligada a su `telegram_user_id` la de
`privacy_consents`.

### R20
CUANDO llega un mensaje de un remitente sin consentimiento vigente y no exento, el orchestrator
DEBE guardar únicamente su `update_id` en `processed_updates` (tratamiento técnico mínimo, sin
datos de la persona).

## Orchestrator — no regresión

### R21
MIENTRAS el remitente tiene consentimiento vigente, CUANDO envía texto libre, el orchestrator
DEBE seguir el flujo actual (contacto, mensaje, RAG, respuesta) sin cambios.

### R22
CUANDO `PRIVACY_NOTICE_VERSION` cambia y el remitente que no es personal solo tiene
consentimiento de una versión anterior, el orchestrator NO DEBE guardar datos nuevos ligados a
él (por texto libre ni por comandos de personal) hasta que acepte la versión vigente.

## Telegram gateway — almacenamiento transitorio (se mantiene)

### R23
El gateway DEBE guardar la marca de deduplicación por `update_id` en Redis con expiración
`DEDUP_TTL_SECONDS`.

### R24
El gateway DEBE expirar el búfer de agrupación de mensajes tras
`MESSAGE_GROUPING_BUFFER_TTL_SECONDS`.

## Restricciones (las verifica el reviewer, no son R)

- Sin cambios en `contracts/` ni contratos nuevos.
- `docs/proyecto.md` documenta R20, R23 y R24 como tratamiento técnico mínimo necesario para
  responder.
- `./init.sh` queda verde.

## Cobertura del acceptance

| Acceptance | Requirements |
|---|---|
| 1. Regla: sin consentimiento no se persiste nada salvo `privacy_consents` | R18, R19, R10, R11, R15, R16 |
| 2. Excepción de personal (lectura antes de escribir) | R1, R2, R6, R7 |
| 3. No personal pasa por `_privacy_gate`; tras aceptar no gana permisos | R10, R11, R12, R13, R14 |
| 4. `/start <token>` solo lectura; personal como hoy; cliente sin consentimiento no consume; tras aceptar funciona | R3, R4, R5, R8, R9, R15, R16, R17 |
| 5. Almacenamientos transitorios documentados | R20, R23, R24 (+ restricción de docs) |
| 6. Prueba de seguridad por ruta | R18, R19 |
| 7. No regresión (personal, cliente con consentimiento, cambio de versión) | R6, R8, R21, R22 |
| 8. Fuera de alcance, sin contratos, `init.sh` verde | Restricciones |
