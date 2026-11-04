# Design — estados_y_consentimiento (feature #37)

## Alcance

Implementar la máquina de siete estados, la prueba de consentimiento mediante
botón, evidencia versionada, cierre/reinicio, bloqueo de RAG/LLM fuera de
`activa`, manejo de mensajes no textuales y lectura/edición de los textos fijos
desde el panel administrativo existente. Reutilizar la identidad por canal de
#36 y no debilitar la compuerta de #35. #38 emite eventos de login y vigencia;
esta feature define y prueba las transiciones al recibirlos, sin implementar
credenciales, sesiones ni login.

## Archivos a crear o modificar

- `services/orchestrator/orchestrator/domain.py`: enum de estado, reductor puro
  de `(estado, evento) -> estado`, flujo de botón de consentimiento y
  enrutamiento que impide llamar al LLM fuera de `activa`.
- `services/orchestrator/orchestrator/main.py`: procesar `NormalizedMessage`
  de tipo `button`, llamar al reductor, persistir cambios de estado solo tras
  consentimiento vigente y propagar error de escritura de evidencia sin enviar
  confirmación.
- `services/orchestrator/orchestrator/adapters/repository.py`: añadir
  `conversation_states` asociado al contacto consentido; ampliar la evidencia
  de consentimiento para resultado, ID de mensaje y botón; preservar registros
  históricos y hacer que solo decisiones `accepted` con prueba vigente
  satisfagan `has_channel_privacy_consent`. Añadir almacenamiento/read de
  textos administrables con los métodos de configuración existentes.
- `services/orchestrator/orchestrator/admin.py`: formulario y rutas protegidas
  por sesión admin y CSRF para editar política (texto + versión), saludo,
  confirmación, cierre, contenido no textual, recordatorio de login, texto de
  servicio suspendido, bienvenida/temas. Validar tamaños y valores requeridos.
- `services/orchestrator/tests/test_conversation_states.py` (nuevo): reducer,
  estado, consentimiento y rutas de transición con repositorios/adaptadores
  falsos; trazabilidad a cada R.
- `services/orchestrator/tests/test_conversation_texts.py` (nuevo): permisos,
  CSRF, persistencia y lectura en vivo de textos del panel; no requiere DB real.
- `services/telegram_gateway/telegram_gateway/adapters/telegram.py` y
  `services/telegram_gateway/telegram_gateway/domain.py`: enviar botones
  interactivos con callback autenticado que incorpora la huella de política;
  normalizar `callback_query` a `privacy.accept` / `privacy.reject`.
- `services/telegram_gateway/tests/test_webhook.py` y
  `services/telegram_gateway/tests/test_multicanal.py`: verificar markup de
  botones y callback de extremo a extremo hasta la decisión persistida en el
  orquestador, incluida la prueba de versión/hash (R37/R38).
- `services/orchestrator/tests/test_privacy.py` y
  `services/orchestrator/tests/test_multichannel_identity.py`: pruebas de
  regresión para #35/#36, nuevos botones y evidencia.
- `services/orchestrator/orchestrator/adapters/repository.py` schema/migración:
  añadir campos anulables para evidencia nueva; migración aditiva e idempotente
  que no borra ni reescribe consentimientos aceptados existentes.
- `contracts/lazaro_contracts/channels.py` y `contracts/CONTRATOS.md`: añadir de
  forma aditiva `NormalizedMessage.button_proof` y
  `OptionsBlock.option_ids`/`option_proofs` (S15) para transportar la prueba del
  aviso y pintar botones interactivos.

## Modelos y firmas

- `ConversationState(StrEnum)`: `new`, `awaiting_consent`, `closed`,
  `awaiting_login`, `active`, `with_advisor`, `no_access`.
- `ConversationEvent(StrEnum)`: `first_message`, `accept_button`,
  `reject_button`, `policy_question`, `unconfirmed_acceptance`,
  `restart_message`, `escalation_requested`, `suppression_requested`,
  `login_valid`, `login_expired`,
  `credential_expired`, `credential_renewed`, `escalated`, `advisor_resolved`,
  `advisor_returned`, `session_closed`, `session_idle_timeout`,
  `unsupported_message`.
- `transition_state(state, event) -> ConversationState`: función pura; los
  eventos no permitidos para el estado actual mantienen estado y se cubren por
  test.
- `get_conversation_state(contact_id) -> ConversationState` y
  `set_conversation_state(contact_id, state, at) -> None`.
- `get_conversation_texts() -> ConversationTexts` y
  `save_conversation_texts(texts, admin_profile_id, at) -> None`.
- `add_privacy_decision(channel, external_user_id, notice_version,
  notice_sha256, result, external_message_id, button_id, at) -> None`.
- Los IDs de botón normalizados son `privacy.accept` y `privacy.reject`.
  Los adaptadores mapean el callback/botón del canal a esos IDs; los botones
  desconocidos no conceden consentimiento. Telegram incluye en el callback una
  prueba autenticada de la versión/hash presentada y de la identidad/canal que
  recibió el aviso. El orquestador la compara con la política e identidad
  actuales antes de registrar evidencia (R37/R38); no contiene datos personales
  y se mantiene dentro del límite del canal.
- Implementación concreta de la prueba: `option_proofs` (S15 de
  `CONTRATOS.md`) lleva
  `HMAC-SHA256(service_token, "<channel>:<external_user_id>:<external_chat_id>:<button_id>:<notice_version>:<notice_sha256>:<nonce>")`
  truncado a 32 hex. El nonce aleatorio genera una prueba distinta por
  presentación; el orquestador conserva temporalmente los dos proofs y la
  versión/hash/chat solo en memoria, los consume atómicamente al primer clic válido
  y rechaza si ya existe consentimiento vigente (R39). El gateway pinta
  `OptionsBlock.option_ids` como teclado
  inline con `callback_data = "<button_id>:<proof>"`, normaliza el
  `callback_query` a `NormalizedMessage(kind="button", button_id, button_proof)`
  y el orquestador recalcula la prueba con la identidad y política vigentes
  antes de guardar evidencia o cambiar estado.

## Persistencia y privacidad

- No se guarda `awaiting_consent`, el mensaje entrante ni el contacto antes de
  aceptación. La aceptación/rechazo usa la tabla de evidencia `privacy_consents`
  bajo `(channel, external_user_id)`; la excepción `processed_updates` Telegram
  legacy de #35 se conserva exactamente. El estado `closed` se reconstruye del
  último rechazo y el siguiente mensaje inicia en `new`.
- Tras aceptación válida se crea/reutiliza el contacto de #36 y se persiste
  `awaiting_login` por `contact_id`. El `client_id` permanece ausente; #38 hará
  login y vínculo verificado.
- El esquema conserva columnas/filas históricas. Las decisiones nuevas guardan
  `result` (`accepted`/`rejected`), `evidence_type`, `external_message_id`,
  `button_id` y `occurred_at`; `accepted_at` histórico queda preservado y es
  nullable para rechazos. Una marca de migración mantiene `accepted_at` nullable
  sin borrar ni modificar su valor histórico. Los registros previos basados en texto se migran con
  `result=accepted` y `evidence_type=legacy`, pero no cuentan como prueba de
  botón para habilitar `awaiting_login`; el siguiente mensaje vuelve a pedir
  confirmación por botón aunque el texto/version no haya cambiado.
  `has_channel_privacy_consent` solo cuenta aceptación de la versión vigente
  con `evidence_type=button`.
- `conversation_states` contiene filas solo para contactos ya consentidos.
  Una versión legal nueva invalida el estado conversacional previo en runtime y
  fuerza aviso + botones sin persistir contenido hasta la aceptación.
- El texto de política, versión, saludo y respuestas fijas se leen del
  almacenamiento operativo editable por admin. Si faltan los campos legales
  obligatorios, se falla cerrado según #35. No hay fallback legal inventado ni
  generación del LLM para estas respuestas.
- El rechazo conserva únicamente la evidencia mínima descrita por el documento
  (versión, hash, canal/ID externo, resultado y mensaje/botón); el punto de
  retención de esa evidencia sigue sujeto a validación legal abierta. En la
  misma transacción se elimina el contenido personal del hilo rechazado y sus
  filas de contacto asociadas; no se elimina la evidencia del rechazo.

## Integración con otras fases

- Se consumen `NormalizedMessage.kind == "button"` y `button_id` de #36; no se
  añaden contratos HTTP entre servicios. El adaptador Telegram completa el
  transporte interactivo del evento ya definido por #36.
- Los eventos `login_valid`, `login_expired`, `credential_expired`,
  `credential_renewed`, `session_closed` y `session_idle_timeout` tienen pruebas
  con eventos falsos y un punto de llamada estable para #38. Ningún endpoint ni
  token de login se implementa aquí.
- El estado `with_advisor` reutiliza handover y el panel de asesores existentes;
  no crea un panel nuevo. La implementación de herramientas por estado pertenece
  a #39, pero #37 debe impedir que los estados inactivos lleguen al flujo RAG/LLM.
- La edición queda dentro del panel admin actual (#21). #42 podrá extender esta
  superficie con clientes, credenciales, plantillas, horario y métricas.

## Alternativa descartada

Se descarta modelar el consentimiento como aceptación de texto libre o persistir
un estado de espera previo al consentimiento: el documento exige el botón como
prueba, y #35/#36 prohíben persistir el contenido/contacto antes de aceptar.
El flujo temporal se deriva de la entrada actual y de la evidencia mínima de
`privacy_consents`.

## Dependencias

- #35 establece la compuerta y almacén de evidencia sin escrituras de persona
  antes de aceptación.
- #36 provee identidad por canal, botones normalizados y bloques de respuesta.
- #38 proveerá eventos de login y vigencia; no se adelanta su código.
- Panel existente #21 y almacenamiento `app_settings`; no se añaden librerías ni
  dependencias externas.

## Supuestos a confirmar

- Si la política/textos obligatorios no están configurados, la decisión segura
  es no habilitar el flujo y no inventar un aviso.
- Las respuestas de rechazo se conservan solo como evidencia mínima conforme a
  `docs/especificacion.md`; su plazo exacto requiere validación legal y no se
  decide aquí.
