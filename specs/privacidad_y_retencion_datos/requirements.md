# Requirements — privacidad_y_retencion_datos (feature #27)

> Fuente: acceptance de la #27 en `feature_list.json`; `docs/proyecto.md` §11 (riesgo
> «Datos personales (Ley 1581, sin verificar con abogado)») y §12 («Datos personales: aviso y
> autorización según la Ley 1581»). Este spec **no** fija texto de aviso, finalidades, frase de
> aceptación, plazo de retención ni límite de vida de casos activos: son valores que aprueba el
> dueño (design §6). Sin ellos el sistema falla cerrado.

## Glosario

- **Configuración de privacidad completa** (orchestrator): `PRIVACY_NOTICE_TEXT`,
  `PRIVACY_NOTICE_VERSION`, `PRIVACY_ACCEPT_PHRASE`, `PRIVACY_ACCEPTED_REPLY` y
  `PRIVACY_RETENTION_DAYS` no vacíos y válidos.
- **Configuración de retención de handover**: `PRIVACY_RETENTION_DAYS` y
  `PRIVACY_ACTIVE_CASE_MAX_DAYS` no vacíos y válidos.
- **Ruta de cliente**: todo mensaje de `POST /messages` que no es `/start <token>`, `/consultar`,
  `/responder` ni `/cerrar` (es decir, el que hoy llega a `repo.add_message(..., "user", ...)`).
- **Rutas de personal**: `/start <token>`, `/consultar`, `/responder`, `/cerrar`.
- **Normalizar**: `" ".join(texto.split()).casefold()`.
- **Consentimiento vigente**: registro en `privacy_consents` del `telegram_user_id` remitente con
  `notice_version` igual a `PRIVACY_NOTICE_VERSION` actual.
- **Corte**: `clock() - PRIVACY_RETENTION_DAYS días` (cada servicio con su reloj).
- **Caso activo**: fila de `handover_cases` con `status` `open`, `assigned` o `timed_out`.
- **Corte de casos activos** (handover): `clock() - PRIVACY_ACTIVE_CASE_MAX_DAYS días`.

## Orchestrator — configuración

### R1
SI `APP_ENV=production` y falta alguna variable de la configuración de privacidad completa
ENTONCES el sistema DEBE lanzar `ProductionConfigError` al construir `Settings`.

### R2
SI `PRIVACY_RETENTION_DAYS` no está vacío y no es un entero ≥ 1 ENTONCES el orchestrator DEBE
fallar al construir `Settings` con `ValueError`, en cualquier `APP_ENV`.

### R3
SI `PRIVACY_NOTICE_TEXT` y `PRIVACY_ACCEPT_PHRASE` no están vacíos y el texto normalizado del
aviso no contiene la frase normalizada ENTONCES el orchestrator DEBE fallar al construir
`Settings` con `ValueError`.

## Orchestrator — consentimiento (ruta de cliente)

### R4
MIENTRAS la configuración de privacidad no está completa, CUANDO llega un mensaje por la ruta
de cliente, el orchestrator NO DEBE crear contacto, guardar mensaje ni evento, llamar a RAG, LLM
ni handover, ni enviar nada por el gateway.

### R5
MIENTRAS la configuración de privacidad no está completa, CUANDO llega un mensaje por la ruta
de cliente, el orchestrator DEBE responder `202`.

### R6
MIENTRAS la configuración de privacidad no está completa, CUANDO descarta un mensaje por R4, el
orchestrator DEBE escribir el log `privacy_not_configured` sin el texto, `telegram_user_id` ni
`chat_id`.

### R7
CUANDO llega por la ruta de cliente un mensaje de un remitente sin consentimiento vigente y su
texto normalizado no es igual a la frase normalizada, el orchestrator DEBE enviar
`PRIVACY_NOTICE_TEXT` al `chat_id` del mensaje.

### R8
CUANDO ocurre R7, el orchestrator NO DEBE crear contacto, guardar mensaje ni evento, ni llamar a
RAG, LLM ni handover.

### R9
CUANDO llega por la ruta de cliente un mensaje de un remitente sin consentimiento vigente cuyo
texto normalizado es igual a la frase normalizada, el orchestrator DEBE guardar en
`privacy_consents` un registro con `telegram_user_id`, `notice_version` actual,
`notice_sha256` (SHA-256 hex del `PRIVACY_NOTICE_TEXT` en UTF-8) y `accepted_at = clock()`.

### R10
CUANDO se guarda el consentimiento de R9, el orchestrator DEBE enviar `PRIVACY_ACCEPTED_REPLY`
al `chat_id`.

### R11
CUANDO ocurre R9, el orchestrator NO DEBE guardar el texto de aceptación como mensaje ni
enviarlo a RAG, LLM ni handover.

### R12
SI el texto de la ruta de cliente contiene la frase pero su forma normalizada no es igual a ella
(p. ej. con texto extra) ENTONCES el orchestrator NO DEBE guardar consentimiento.

### R13
SI el texto de la ruta de cliente de un remitente sin consentimiento vigente contiene la frase
pero su forma normalizada no es igual a ella ENTONCES el orchestrator DEBE enviar
`PRIVACY_NOTICE_TEXT` al `chat_id` (como en R7).

### R14
El orchestrator NO DEBE crear registros en `privacy_consents` por ninguna vía distinta de R9
(ni por `/start`, comandos, silencio ni valor preseleccionado).

### R15
CUANDO `PRIVACY_NOTICE_VERSION` cambia y el remitente solo tiene consentimiento de versiones
anteriores, el orchestrator DEBE tratarlo como sin consentimiento vigente (R7/R9) y conservar
los registros anteriores.

### R16
MIENTRAS el remitente tiene consentimiento vigente, el orchestrator DEBE procesar la ruta de
cliente igual que antes de esta feature (contacto, mensaje, reenvío al asesor, traspaso, RAG).

### R17
SI falla guardar el consentimiento de R9 ENTONCES el orchestrator NO DEBE enviar
`PRIVACY_ACCEPTED_REPLY`.

### R18
SI falla guardar el consentimiento de R9 ENTONCES el orchestrator DEBE responder `500` mediante
el manejador de errores existente.

### R19
El orchestrator DEBE procesar las rutas de personal igual que antes de esta feature, con o sin
configuración de privacidad completa y con o sin consentimiento del remitente.

> Reemplazado por #35 (consentimiento_antes_de_datos) R6–R10: solo el personal vinculado queda
> exento; quien no es personal pasa por la puerta de consentimiento también en `/start` y en los
> comandos de personal.

## Orchestrator — retención (`POST /privacy/purge`)

### R20
SI `POST /privacy/purge` del orchestrator llega sin `X-Service-Token` válido ENTONCES el sistema
DEBE responder `401` con `error="unauthorized"` sin borrar nada.

### R21
SI `PRIVACY_RETENTION_DAYS` está vacío ENTONCES `POST /privacy/purge` del orchestrator DEBE
responder `503` con `error="privacy_not_configured"` sin borrar nada.

### R22
CUANDO el orchestrator procesa `POST /privacy/purge`, el sistema DEBE borrar las filas de
`messages` con `at` < corte y conservar las de `at` ≥ corte.

### R23
CUANDO el orchestrator procesa `POST /privacy/purge`, el sistema DEBE borrar las filas de
`events` con `at` < corte y conservar las de `at` ≥ corte.

### R24
CUANDO el orchestrator procesa `POST /privacy/purge`, el sistema DEBE borrar cada contacto
inactivo (`created_at` < corte, sin `messages` con `at` ≥ corte y sin `case_links` con
`created_at` ≥ corte) junto con sus `case_links`.

### R25
CUANDO el orchestrator procesa `POST /privacy/purge`, el sistema NO DEBE borrar ni modificar
contactos activos ni sus `case_links`.

### R26
CUANDO el orchestrator procesa `POST /privacy/purge`, el sistema NO DEBE borrar ni modificar
filas de `profiles`, `link_tokens`, `admin_sessions`, `admin_login_attempts`,
`processed_updates`, `query_categories`, `app_settings`, `db_query_audit` ni
`privacy_consents`.

### R27
CUANDO termina `POST /privacy/purge` del orchestrator, el sistema DEBE responder `200` con
`PrivacyPurgeResponse` (`cutoff`, recuentos por tabla y `closed_active_cases = 0`) y guardar una
fila en `privacy_purge_runs` con `ran_at`, `cutoff` y los recuentos.

### R28
CUANDO se ejecuta dos veces `POST /privacy/purge` del orchestrator con el mismo reloj, la
segunda ejecución DEBE informar recuentos `0`.

## Handover — configuración y retención

### R29
SI `APP_ENV=production` y `PRIVACY_RETENTION_DAYS` o `PRIVACY_ACTIVE_CASE_MAX_DAYS` está vacío
ENTONCES handover DEBE lanzar `ProductionConfigError` al construir `Settings`.

### R30
SI `PRIVACY_RETENTION_DAYS` o `PRIVACY_ACTIVE_CASE_MAX_DAYS` no está vacío y no es un entero ≥ 1
ENTONCES handover DEBE fallar al construir `Settings` con `ValueError`, en cualquier `APP_ENV`.

### R31
SI `PRIVACY_RETENTION_DAYS` y `PRIVACY_ACTIVE_CASE_MAX_DAYS` no están vacíos y
`PRIVACY_ACTIVE_CASE_MAX_DAYS` ≥ `PRIVACY_RETENTION_DAYS` ENTONCES handover DEBE fallar al
construir `Settings` con `ValueError`.

### R32
SI la configuración de retención de handover no está completa ENTONCES `POST /privacy/purge` de
handover DEBE responder `503` con `error="privacy_not_configured"` sin borrar nada.

### R33
SI `POST /privacy/purge` de handover llega sin `X-Service-Token` válido ENTONCES el sistema DEBE
responder `401` con `{"error": "unauthorized"}`.

### R34
CUANDO handover procesa `POST /privacy/purge`, el sistema DEBE borrar las filas de
`handover_cases` con `status='closed'` y `closed_at` < corte.

### R35
CUANDO handover procesa `POST /privacy/purge`, el sistema DEBE cerrar y borrar en la misma
transacción cada caso activo con `created_at` < corte de casos activos.

### R36
CUANDO handover borra un caso por R35, el sistema DEBE borrar en la misma transacción las filas
de `handover_requests` cuyo `case_id` o `requested_case_id` sea el de ese caso.

### R37
CUANDO handover procesa `POST /privacy/purge`, el sistema NO DEBE borrar ni modificar casos
activos con `created_at` ≥ corte de casos activos.

### R38
CUANDO handover procesa `POST /privacy/purge`, el sistema DEBE borrar las filas de
`handover_requests` con `received_at` < corte.

### R39
CUANDO handover procesa `POST /privacy/purge`, el sistema NO DEBE borrar filas de
`handover_notifications` ni `handover_denials`.

### R40
CUANDO termina `POST /privacy/purge` de handover, el sistema DEBE responder `200` con
`PrivacyPurgeResponse` (`cutoff`, recuentos por tabla y `closed_active_cases` = número de casos
activos cerrados y borrados por R35) y guardar una fila en `privacy_purge_runs` de handover con
esos valores.

## Ejecución programada (`scripts/purgar_datos.py`, compose)

### R41
CUANDO se ejecuta una iteración de `scripts/purgar_datos.py`, el script DEBE llamar primero a
`POST {HANDOVER_URL}/privacy/purge` con cuerpo `{}` y `X-Service-Token: SERVICE_TOKEN`.

### R42
CUANDO la llamada de R41 responde `200`, el script DEBE llamar después, en la misma iteración, a
`POST {ORCHESTRATOR_URL}/privacy/purge` con cuerpo `{}` y `X-Service-Token: SERVICE_TOKEN`.

### R43
SI la llamada de R41 responde distinto de `200` o falla la conexión ENTONCES el script NO DEBE
llamar al orchestrator en esa iteración.

### R44
CUANDO las llamadas de R41 y R42 responden `200`, el script DEBE terminar con código 0.

### R45
SI la llamada de R41 o la de R42 responde distinto de `200` o falla la conexión ENTONCES el
script DEBE terminar con código distinto de 0.

### R46
CUANDO se ejecuta con `--intervalo`, el script DEBE repetir la iteración (R41–R43) cada
`PRIVACY_PURGE_INTERVAL_SECONDS` sin terminar si una iteración falla.

### R47
`docker-compose.yml` DEBE incluir el servicio `retention_worker` que ejecute
`purgar_datos.py --intervalo` con la imagen de `services/handover/Dockerfile`.

### R48
`services/handover/Dockerfile` DEBE copiar `scripts/purgar_datos.py` a la imagen.

### R49
El servicio `retention_worker` NO DEBE publicar puertos.

### R50
`.env.example` DEBE declarar las variables `PRIVACY_*` de esta feature, con
`PRIVACY_NOTICE_TEXT`, `PRIVACY_NOTICE_VERSION`, `PRIVACY_ACCEPT_PHRASE`,
`PRIVACY_ACCEPTED_REPLY`, `PRIVACY_RETENTION_DAYS` y `PRIVACY_ACTIVE_CASE_MAX_DAYS` vacíos.

## Contratos

### R51
`contracts/CONTRATOS.md` DEBE documentar `POST /privacy/purge` del orchestrator y de handover
(quién llama y en qué orden, request, respuesta con `closed_active_cases`, errores `401` y
`503 privacy_not_configured`).

### R52
`lazaro_contracts` DEBE exportar `PrivacyPurgeRequest` y `PrivacyPurgeResponse`.

## Cobertura del acceptance

| Criterio del acceptance | Requirements |
|---|---|
| Los clientes reciben y aceptan un aviso antes de que se procesen o guarden sus mensajes | R1–R19 |
| Los datos personales se retienen solo durante el plazo aprobado y existe un proceso verificable de eliminación | R20–R52 (casos activos acotados: R29–R31, R35–R37, R40; orden handover → orchestrator: R41–R43) |
| Tests de consentimiento, retención y eliminación sin afectar registros operativos necesarios | R9–R19, R22–R28, R34–R40 (en especial R19, R25, R26, R37, R39, R43) |
