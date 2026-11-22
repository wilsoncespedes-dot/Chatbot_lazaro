# Requirements — #70 aviso_intencion_compra

Servicio: **orchestrator** (todo). `contracts/` y `handover` no cambian: crear el caso
reutiliza el traspaso actual con motivo `user_request`. Depende de #68 (bandeja
unificada) y reutiliza #53 (eventos en vivo) y #52/#69 (autoasignación del traspaso).

## Ajustes configurables (panel de administración)

## R1
El sistema DEBE ofrecer en los ajustes operativos del panel la clave `purchase_intent.phrases` (lista separada por comas) cuyo valor inicial, tomado de `PURCHASE_INTENT_PHRASES`, es «me interesa,quiero reservar,quiero comprar».

## R2
SI el formulario de ajustes recibe `purchase_intent.phrases` con una lista que no queda vacía tras normalizar, con más de 30 frases, con una frase de menos de 3 o más de 80 caracteres normalizados, o con caracteres de control ENTONCES el sistema DEBE rechazar el formulario con `SettingsFormInvalid` sin guardar ningún ajuste.

## R3
SI el valor guardado de `purchase_intent.phrases` es inválido al resolver los ajustes ENTONCES el sistema DEBE usar el valor de entorno `PURCHASE_INTENT_PHRASES`.

## R4
El sistema DEBE ofrecer en los ajustes operativos las claves `purchase_intent.enabled` (bool, por defecto `true`), `purchase_intent.interval_minutes` (entero 1..1440, por defecto 60) y `purchase_intent.create_case` (bool, por defecto `false`), cada una con su valor de entorno por defecto y su efecto inmediato sin redeploy.

## Detección

## R5
CUANDO la detección está habilitada y el texto normalizado de un mensaje procesado en estado `active` o `no_access` contiene alguna frase configurada (también normalizada), el sistema DEBE registrar una detección de intención de compra con origen `phrase`.

## R6
CUANDO el router de IA devuelve `{"tool": "buscar_base_conocimiento", "args": {"motivo": "purchase_intent"}}`, el sistema DEBE registrar una detección de intención de compra con origen `router` y ejecutar la herramienta con `args` vacíos.

## R7
SI el router devuelve el motivo `purchase_intent` junto a una herramienta distinta de `buscar_base_conocimiento` (incluida `escalar_a_asesor`) ENTONCES `parse_router_answer` DEBE rechazar la respuesta con `RouterInvalid("invalid_args")`.

## R8
El sistema DEBE describir el motivo `purchase_intent` en el prompt del router únicamente para la herramienta `buscar_base_conocimiento`, y los motivos aceptados por `escalar_a_asesor` DEBEN seguir siendo `user_request` y `frustration`.

## R9
CUANDO la detección está deshabilitada (`purchase_intent.enabled` = `false`), el sistema NO DEBE registrar detecciones ni por frase ni por router.

## R10
CUANDO el mensaje del cliente coincide con una frase de traspaso humano (`HANDOVER_KEYWORDS`), el sistema DEBE escalar exactamente como antes y NO DEBE registrar una detección de intención de compra.

## Efectos de la detección

## R11
CUANDO se registra una detección, el sistema DEBE guardar un evento `purchase_intent` en `events` cuyo motivo es `phrase` o `router`, sin incluir texto del cliente ni la frase coincidente.

## R12
CUANDO se registra una detección, el sistema DEBE seguir respondiendo al mensaje actual por el flujo normal (respuesta del RAG o de la herramienta elegida) sin sustituirla ni retrasarla.

## R13
MIENTRAS una conversación tiene una detección posterior a su último `case_closed`, dentro de `PURCHASE_INTENT_MARK_HOURS` (por defecto 72) y con estado distinto de `cerrada`, la bandeja DEBE mostrarla con el indicador de texto «Interés de compra» (`ConversationRow.purchase_intent = true`).

## R14
MIENTRAS la bandeja contiene conversaciones con la marca de interés de compra, el sistema DEBE ordenarlas después de las `pendiente` y antes del resto de conversaciones del mismo grupo, conservando el orden por última actividad dentro de cada grupo.

## R15
CUANDO se registra una detección, el sistema DEBE publicar un evento en vivo `purchase_intent` cuya clave de conversación es el `case_id` del último caso del contacto o, si no existe, su `contact_id`, y cuyo payload se limita a `type`, `id` y `case_id`.

## R16
CUANDO el panel en vivo recibe un evento `purchase_intent`, el sistema DEBE refrescar la lista de la bandeja sin recargar la página.

## R17
DONDE `purchase_intent.create_case` es `true`, el sistema DEBE abrir un caso tras responder al mensaje actual usando el flujo de traspaso existente (`_handover` con motivo `user_request`, sin acuse), siempre que la conversación siga en `active` o `no_access` y no tenga caso abierto.

## R18
MIENTRAS `purchase_intent.create_case` es `false` (valor por defecto), el sistema NO DEBE crear ningún caso ni cambiar el estado de la conversación por una detección.

## Anti-repetición y robustez

## R19
SI ya existe un evento `purchase_intent` de la misma conversación dentro de `purchase_intent.interval_minutes` ENTONCES el sistema NO DEBE registrar un evento nuevo, ni publicar un evento en vivo, ni crear un caso.

## R20
CUANDO transcurre `purchase_intent.interval_minutes` desde la última detección y el cliente vuelve a mostrar interés, el sistema DEBE registrar una nueva detección.

## R21
SI el registro del evento, la marca o la publicación en vivo falla ENTONCES el sistema DEBE registrar el error sin texto del cliente y continuar respondiendo al cliente.

## Texto del cliente como dato

## R22
El sistema DEBE tratar el texto del cliente solo como dato en la detección: comparación normalizada contra las frases, sin interpolarlo en SQL ni en HTML y, hacia el LLM, solo dentro de `<mensaje>` con las etiquetas de cierre neutralizadas.

## R23
CUANDO el texto del cliente contiene una orden de prompt injection y una frase de intención de compra, el sistema DEBE registrar la detección por frase y NO DEBE consultar el router.

## R24
El sistema DEBE escapar HTML en todos los textos que la bandeja muestre para el indicador, y el indicador NO DEBE depender solo del color.

## Configuración

## R25
El sistema DEBE documentar y validar en `config.py`, `.env.example` y `render.yaml` las variables `PURCHASE_INTENT_ENABLED`, `PURCHASE_INTENT_PHRASES`, `PURCHASE_INTENT_INTERVAL_MINUTES`, `PURCHASE_INTENT_CREATE_CASE` y `PURCHASE_INTENT_MARK_HOURS`.
