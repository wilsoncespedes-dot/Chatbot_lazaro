# Requirements — #46 `consentimiento_texto_telegram`

> Decisión del dueño: en Telegram el aviso de consentimiento se envía **sin
> botones inline**; la persona acepta escribiendo la frase exacta de aceptación
> (default `ACEPTO`) y rechaza escribiendo la frase exacta de rechazo (default
> `NO ACEPTO`). WhatsApp conserva sus botones y su comportamiento de #37.
> Depende de #35 (sin datos antes del consentimiento) y reutiliza la evidencia
> versionada de #37.

Definiciones usadas abajo:

- **Frase de aceptación efectiva**: `PRIVACY_ACCEPT_PHRASE` sin espacios
  extremos; si queda vacía, `ACEPTO`.
- **Frase de rechazo efectiva**: `PRIVACY_REJECT_PHRASE` sin espacios extremos;
  si queda vacía, `NO ACEPTO`.
- **Coincidencia exacta**: `normalize_privacy_text(texto) ==
  normalize_privacy_text(frase)` (trim, espacios internos colapsados a uno,
  `casefold`). Igualdad, nunca contención.
- **Aviso vigente mostrado**: existe en `ConsentChallengeStore` un desafío para
  `(canal, external_user_id)` cuyo `notice_version` y `notice_sha256` son los
  del aviso vigente del panel y cuyo `external_chat_id` es el chat del mensaje.
- **Remitente sin consentimiento**: `has_channel_privacy_consent(canal,
  external_user_id, versión vigente)` es falso.

## Orquestador — configuración

## R1
El sistema (orchestrator, `Settings`) DEBE exponer como frase de aceptación
efectiva el valor de `PRIVACY_ACCEPT_PHRASE` sin espacios extremos y, si queda
vacío, el literal `ACEPTO`.

## R2
El sistema (orchestrator, `Settings`) DEBE exponer como frase de rechazo
efectiva el valor de `PRIVACY_REJECT_PHRASE` sin espacios extremos y, si queda
vacío, el literal `NO ACEPTO`.

## R3
SI la frase de aceptación efectiva y la de rechazo efectiva son iguales tras
`normalize_privacy_text` ENTONCES `Settings` DEBE fallar al cargar con un
`ValueError` que nombre `PRIVACY_REJECT_PHRASE`.

## R4
SI `PRIVACY_TEXT_CONSENT_INSTRUCTION` no contiene los marcadores `{accept}` y
`{reject}` ENTONCES `Settings` DEBE fallar al cargar con un `ValueError` que
nombre `PRIVACY_TEXT_CONSENT_INSTRUCTION`.

## R5
El sistema (orchestrator) DEBE reconocer una frase de aceptación o de rechazo
solo por coincidencia exacta tras `normalize_privacy_text`: `"  acepto "`
coincide con `ACEPTO`; `"NO ACEPTO"`, `"acepto por favor"` y `"sí acepto"` NO
coinciden con `ACEPTO`.

## Orquestador — aviso en Telegram

## R6
CUANDO el orquestador muestra el aviso de consentimiento a un remitente del
canal `telegram`, el sistema DEBE enviar solo bloques de texto, sin
`OptionsBlock`, de modo que el gateway no adjunte `reply_markup`.

## R7
CUANDO el orquestador muestra el aviso de consentimiento a un remitente del
canal `telegram`, el texto enviado DEBE ser el aviso vigente del panel
(`notice_text`, precedido del `greeting` en la primera presentación) seguido
de `PRIVACY_TEXT_CONSENT_INSTRUCTION` con `{accept}` y `{reject}` sustituidos
por las frases efectivas.

## R8
El sistema (orchestrator) NO DEBE incluir los IDs internos de botón
(`privacy.accept`, `privacy.reject`) ni pruebas HMAC en el texto del aviso de
consentimiento de ningún canal.

## R9
CUANDO el orquestador muestra el aviso de consentimiento a un remitente del
canal `telegram`, el sistema DEBE registrar en `ConsentChallengeStore` un
desafío ligado a canal, `external_user_id`, chat receptor, versión y hash del
aviso vigente, aunque el gateway no ofrezca `send_channel_blocks`.

## Orquestador — aceptación por texto en Telegram

## R10
CUANDO un remitente de `telegram` sin consentimiento envía un texto que
coincide con la frase de aceptación efectiva MIENTRAS el aviso vigente le fue
mostrado, el sistema DEBE añadir en `privacy_consents` una fila con
`result="accepted"`, `evidence_type="text"`, `external_message_id` del mensaje
(el `update_id` en la ruta histórica `MessageRequest`), `notice_version` y
`notice_sha256` vigentes, `button_id=""` y como timestamp el `received_at` del
mensaje.

## R11
CUANDO se registra una aceptación o un rechazo por texto, el sistema DEBE
consumir el desafío de forma atómica, de modo que dos frases (repetidas o
concurrentes) sobre la misma presentación registren como máximo una decisión.

## R12
CUANDO se registra una aceptación por texto, el sistema DEBE continuar con el
mismo flujo posterior a la aceptación que el botón de #37: crear el contacto
del canal, fijar el estado `AWAITING_LOGIN` y enviar `accepted_reply` con el
enlace de inicio de sesión.

## R13
El repositorio (memoria y Postgres) DEBE considerar consentimiento vigente una
aceptación de la versión vigente con `evidence_type` `button` o `text`, y NO
DEBE considerar vigente una con `evidence_type="legacy"`.

## R14
SI un remitente de `telegram` sin consentimiento envía la frase de aceptación
o la de rechazo sin que el aviso vigente le haya sido mostrado (nunca mostrado,
versión o hash cambiados, chat distinto o desafío ya consumido) ENTONCES el
sistema NO DEBE registrar ninguna decisión en `privacy_consents`.

## R15
SI un remitente de `telegram` sin consentimiento envía la frase de aceptación
o la de rechazo sin que el aviso vigente le haya sido mostrado ENTONCES el
sistema DEBE mostrarle el aviso vigente según R6-R9.

## R16
CUANDO `POST /messages` recibe por `telegram` un texto que coincide con la
frase de aceptación o de rechazo efectiva de un remitente sin consentimiento,
el orquestador DEBE procesarlo dentro de la petición HTTP, de modo que un
fallo al guardar la evidencia responda `500` (paridad con R18 de #35).

## R17
CUANDO se registra una aceptación por texto, el sistema DEBE marcar
`(canal, external_message_id)` como procesado, de modo que la reentrega del
mismo mensaje responda `duplicate` sin registrar otra decisión ni enviar otra
respuesta.

## Orquestador — rechazo por texto en Telegram

## R18
CUANDO un remitente de `telegram` sin consentimiento envía un texto que
coincide con la frase de rechazo efectiva MIENTRAS el aviso vigente le fue
mostrado, el sistema DEBE registrar la decisión mínima `result="rejected"`
con `evidence_type="text"`, versión, hash, `external_message_id` y timestamp,
ejecutar `delete_contact_content` y responder `rejected_reply`.

## R19
CUANDO se registra un rechazo por texto, el sistema NO DEBE crear ni conservar
filas en `contacts`, `messages`, `events`, `db_query_audit`, `case_links`,
`auto_handover_*` ni `profiles.telegram_user_id` para ese remitente; la única
escritura es la de `privacy_consents`.

## R20
CUANDO un remitente de `telegram` que rechazó envía un texto nuevo, el sistema
DEBE reiniciar desde `Nuevo` y mostrar saludo y aviso vigente sin registrar
decisión, aunque el texto sea la frase de aceptación.

## Orquestador — texto no coincidente en Telegram

## R21
MIENTRAS el aviso vigente fue mostrado a un remitente de `telegram` sin
consentimiento, CUANDO llega un texto que no coincide con ninguna frase, el
sistema DEBE reenviar el aviso con la instrucción de frases (R6-R8) sin
registrar decisión.

## R22
MIENTRAS un remitente de `telegram` no tiene consentimiento, el sistema NO
DEBE persistir `contacts`, `messages` ni `events` ni invocar LLM/RAG por un
texto no coincidente.

## R23
SI un remitente de `telegram` sin consentimiento envía un texto afirmativo
que no coincide exactamente con la frase de aceptación (p. ej. `sí`,
`sí acepto`) ENTONCES el sistema NO DEBE responder con `confirm_button_reply`
(que remite a botones) y DEBE tratarlo como R21.

## Garantías de #35

## R24
MIENTRAS un remitente de `telegram` no tiene consentimiento, cada ruta de #35
(texto libre, `/consultar`, `/responder`, `/cerrar`, comando mal formado,
`/start` con token de cliente) NO DEBE dejar filas ligadas a ese
`telegram_user_id`, salvo la de `privacy_consents` si después acepta por
frase de texto.

## Botones antiguos de Telegram

## R25
SI llega un `button` de consentimiento por el canal `telegram` de un remitente
sin consentimiento vigente ENTONCES el sistema NO DEBE registrar ninguna
decisión, aunque la prueba coincida con un desafío pendiente.

## R26
SI llega un `button` de consentimiento por el canal `telegram` de un remitente
sin consentimiento vigente ENTONCES el orquestador DEBE responder `202` y
reenviar el aviso de texto sin botones (R6-R8).

## R27
SI llega un `button` de consentimiento por el canal `telegram` de un remitente
con consentimiento vigente ENTONCES el sistema DEBE ignorarlo sin escribir ni
responder (comportamiento de #37).

## WhatsApp sin cambios

## R28
CUANDO el orquestador muestra el aviso a un remitente de `whatsapp`, el
sistema DEBE enviar el `OptionsBlock` con etiquetas `Acepto`/`No acepto`,
`option_ids` `privacy.accept`/`privacy.reject` y pruebas del desafío, igual
que en #37.

## R29
CUANDO un remitente de `whatsapp` pulsa un botón de consentimiento válido, el
sistema DEBE registrar la decisión con `evidence_type="button"` como en #37.

## R30
SI un remitente de `whatsapp` sin consentimiento escribe la frase de
aceptación ENTONCES el sistema NO DEBE registrar consentimiento y DEBE
responder `confirm_button_reply` y el aviso con botones, como en #37.

## Gateway

## R31
CUANDO `telegram_gateway` recibe un texto que coincide con
`MESSAGE_GROUPING_REJECT_PHRASE` no vacía, el sistema DEBE entregarlo de
inmediato sin agruparlo, igual que la frase de aceptación.

## R32
CUANDO `telegram_gateway` envía a Telegram bloques que solo contienen
`TextBlock`, el sistema DEBE llamar a `send_message` con `reply_markup=None`.

## Cobertura del acceptance

| Criterio de #46 | Requirements |
|---|---|
| Aviso Telegram sin botones, instrucción con frases configurables, sin redacción legal nueva | R1, R2, R3, R4, R6, R7, R8, R32 |
| Aceptación solo tras aviso vigente; frase antes del aviso no acepta y muestra aviso; normalización documentada | R5, R9, R10, R11, R14, R15 |
| Evidencia `text` con id externo, versión, hash, timestamp | R10, R13, R16, R17 |
| Rechazo cierra sin datos personales; no coincidente recuerda aviso sin persistir | R18, R19, R20, R21, R22, R23 |
| Garantía #35 | R19, R22, R24 |
| WhatsApp intacto; callbacks Telegram antiguos seguros | R25, R26, R27, R28, R29, R30 |
| Pruebas e `./init.sh` verde | Todas (ver `tasks.md`) |
| Frase de rechazo no se agrupa en el gateway | R31 |
