# Design — contrato_conversacion_caso (feature #15)

> Cómo se construye lo pedido en `requirements.md`. Fuentes de negocio: acceptance de
> la #15 y de la #16 (`feature_list.json`, criterios «Decidido por el humano
> (2026-10-31)») y `progress/propuesta_etapa2.md` §6. Modelo de estructura y estilo:
> la #9 (`specs/contrato_asignar_caso/`, `progress/impl_contrato_asignar_caso.md`).
> Apoyado en `docs/architecture.md` §3 (principios 1 y 2) y `docs/conventions.md`.

## 1. Alcance

- Solo se tocan archivos bajo `contracts/`. No se toca `services/`, `eval/`,
  `scripts/`, `docker-compose.yml`, `.github/` ni `requirements*.txt`.
- **Estado de partida: tras la #13.** La #13 (`contrato_autorizacion_asesores`) se
  implementa antes y deja en `CONTRATOS.md` la sección `### POST /cases/{id}/authorize`,
  la fila `403 | forbidden` en `## Reglas comunes` y en las tablas de errores de
  `reply`, `close` y `assign`, y la fila `S12`. Este spec:
  - numera su supuesto como **S13**;
  - coloca su sección al final de `## Rutas`, tras la última que exista (la de
    `authorize`, si la #13 la puso al final);
  - cita `S12` en la fila S13 como las reglas de autorización de los comandos de
    asesor (R38, test T32). Es el único enlace con el texto de la #13: ningún test de
    esta feature busca `authorize` ni `forbidden`.
  - **Sin la #13 implementada no se empieza** (T0 de `tasks.md`): S13 no tendría S12
    al que remitir y su numeración quedaría con hueco. Comprobado el 2026-11-01: la
    #13 y la #17 ya están en `CONTRATOS.md` (fila `S12`, que ya incluye los casos
    huérfanos; fila común `403 | forbidden`; sección `### POST /cases/{id}/authorize`
    al final de `## Rutas`). S13 remite a S12 sin repetir sus reglas, así que hereda
    su versión vigente.
- **Aditivo** (R34, R35): dos modelos, tres ejemplos, una sección de ruta, una fila de
  supuesto y tests. Los tests existentes solo se amplían (entradas nuevas en sus
  dicts/listas multilínea) o se añaden tests nuevos; ninguna aserción se borra ni se
  relaja.
- **Única edición de texto ya publicado con efecto en el contrato** (acceptance #15):
  la línea `- **Llama:**` de `### POST /cases/{id}/close` (R14). Pasa de
  `asesor (herramienta interna con token; panel en el futuro)` a
  `asesor (herramienta interna con token; panel en el futuro), orchestrator (comando `/cerrar` de un asesor desde Telegram, #16)`.
  Se cita solo `/cerrar` porque `/responder` no llama a `close` (lo atiende el propio
  orquestador vía la lógica de `POST /cases/{id}/reply`).
- Otra edición sin efecto en el comportamiento, igual que en la #9: la docstring de
  módulo de `cases.py` añade `/cases/{id}/client-message` a la lista de rutas (R34 la
  permite expresamente). Es la misma docstring que reescribe la #13; la #15 solo
  añade la ruta y no quita nada de lo que dejó la #13.
- **Qué decisiones de la #16 entran en S13.** Criterio: entra en S13 lo que fija cómo
  se usan las rutas del contrato (qué ruta se llama, cuándo, qué hace el llamador con
  cada respuesta y con qué identidad). Por eso entran: el reenvío solo con `assigned`;
  `open`/`not_assigned`/`404` → flujo actual; tras un `502`, texto fijo y sin volver a
  llamar al RAG; los comandos por `POST /messages`; el mensaje de un asesor que no es
  comando → flujo actual (R36: es lo que permite que `POST /messages` sirva a clientes
  y a asesores sin cambiar su contrato); la autorización con S12 (R38) y la identidad
  del remitente (R18, R37, R39). Quedan fuera los textos al usuario sin efecto en
  ninguna ruta (confirmación al asesor tras `/responder` o `/cerrar`, aviso al cliente
  al cerrar, ayuda de uso, el formato `Caso <id> | Cliente: <texto>`): son variables y
  comportamiento de la #16 y no cambian qué ruta se llama ni con qué datos.
- **`## Reglas comunes` no se toca.** Comprobado sobre el estado actual:
  - `502 | upstream_error` ya existe (Dónde: `/cases/{id}/reply`);
  - `404 | not_found` ya existe (Dónde: `/cases/{id}/reply`, `/cases/{id}/close`);
  - `401`, `422 validation_error` y `500` dicen «todas».
  Todos los códigos de la ruta nueva ya están declarados (R13). Siguiendo el
  precedente de la #9 (R13 retirado por el humano: no se editan celdas «Dónde» de
  filas existentes) y la regla de la #15 («la línea `Llama` es el único cambio de
  texto en una sección existente»), NO se editan esas celdas ni se duplican filas.
  Consecuencia aceptada: la columna «Dónde» de las filas 404 y 502 no lista la ruta
  nueva (como ya pasa con la 404 y `assign`); la tabla de la propia ruta es la
  referencia.
- Sin dependencias nuevas. Sin variables de entorno nuevas: los textos fijos
  (fallo de reenvío, ayuda, confirmaciones) son variables de la #16, no del contrato.

### Fuera de alcance

- Implementar la ruta en handover, el formato `Caso <id> | Cliente: <texto>`, el
  recorte a 4096, los eventos `forwarded_to_advisor` / `forward_failed` /
  `advisor_forbidden`, el parseo de `/responder` y `/cerrar`, los textos fijos y las
  confirmaciones: todo es la #16.
- Las reglas de autorización de asesores y `POST /cases/{id}/authorize`: #13 / #14.
- Cualquier cambio en `POST /messages`, `MessageRequest` o `MessageResponse` (R33):
  los comandos de asesor llegan por esa ruta sin cambiarla.
- Cualquier cambio en `reply`, `assign`, `check-timeouts`, `handover` o sus modelos.

## 2. Archivos

| Acción | Ruta | Cambio |
|--------|------|--------|
| modificar | `contracts/lazaro_contracts/cases.py` | añadir `CaseClientMessageRequest` y `CaseClientMessageResponse` al final del módulo (tras `CheckTimeoutsResponse`, o tras el último modelo que deje la #13); ampliar la docstring de módulo |
| modificar | `contracts/lazaro_contracts/__init__.py` | importar los dos modelos desde `.cases` y añadirlos a `__all__` (tras `"CaseAssignResponse"` o tras los modelos de la #13) |
| crear | `contracts/examples/case_client_message_request.json` | `{"text": "Ya reinicié el equipo y sigue sin dejarme entrar.", "at": "2026-10-30T19:20:00Z"}` |
| crear | `contracts/examples/case_client_message_response.json` | `{"status": "forwarded", "case_id": "6f1c2a3e-0000-4000-8000-000000000001"}` |
| crear | `contracts/examples/case_client_message_response_not_assigned.json` | `{"status": "not_assigned", "case_id": "6f1c2a3e-0000-4000-8000-000000000001"}` |
| modificar | `contracts/CONTRATOS.md` | sección `### POST /cases/{id}/client-message` al final de `## Rutas`; línea `- **Llama:**` de `### POST /cases/{id}/close`; fila `S13` al final de `## Supuestos a confirmar` |
| modificar | `contracts/tests/test_contratos_doc.py` | ampliar `ROUTES`, `OWN_ERRORS`, `SUCCESS_CODES`; tests nuevos (ver `tasks.md`) |
| modificar | `contracts/tests/test_examples.py` | ampliar imports, `EXAMPLES` y `MODEL_NAMES` |
| modificar | `contracts/tests/test_models.py` | ampliar imports, `BASE_EXAMPLES` e `IDENTIFIER_FIELDS`; tests nuevos |
| modificar | `contracts/tests/test_packaging.py` | ampliar `MODEL_NAMES` |

Los ejemplos reutilizan el `case_id` ficticio de `case_close_response.json` y de
`case_assign_response.json`. Ningún JSON existente cambia.

## 3. Firmas nuevas

Estilo de los modelos vecinos (docstring de una línea, ≤ 100 caracteres por línea).
`cases.py` ya importa `AwareDatetime`, `Literal`, `Identifier` y `MessageText`.

```python
# contracts/lazaro_contracts/cases.py  (al final del módulo)

class CaseClientMessageRequest(ContractModel):
    """Mensaje de un cliente que el orquestador pide reenviar al asesor del caso (S13)."""

    text: MessageText
    at: AwareDatetime


class CaseClientMessageResponse(ContractModel):
    """Respuesta 200 de POST /cases/{id}/client-message (S13)."""

    status: Literal["forwarded", "not_assigned"]
    case_id: Identifier
```

`ContractModel` ya aplica `extra="forbid"` (R27); `MessageText` ya limita a 1–4096
(R23); `AwareDatetime` ya rechaza fechas sin zona (R22); `Identifier` ya limita a
1–64 (R26). No hace falta código de validación adicional.

No se añaden excepciones: el contrato solo declara códigos. `not_found` y
`upstream_error` ya existen; sus excepciones en handover las define la #16.

## 4. Texto nuevo en `CONTRATOS.md`

### 4.1 Sección de la ruta (al final de `## Rutas`)

Misma forma que `### POST /cases/{id}/assign` (los tests parametrizados parsean esa
estructura):

```markdown
### POST /cases/{id}/client-message

- **Expone:** handover
- **Llama:** orchestrator (al recibir por `POST /messages` un mensaje de un cliente con caso; S13)
- **Modelos:** `CaseClientMessageRequest` → `CaseClientMessageResponse`

`{id}` es el `case_id` (identificador, 1–64 caracteres). Si el caso está `assigned`,
handover envía el texto al asesor asignado y responde `200` con `status` =
`forwarded`; si el caso existe y no está `assigned`, responde `200` con `status` =
`not_assigned` sin enviar nada (S13).

#### Request

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `text` | texto (1–4096) | sí | mensaje del cliente que se reenvía al asesor |
| `at` | fecha ISO 8601 con zona | sí | momento del mensaje del cliente |

#### Respuesta

`200 OK`

| Campo | Tipo | Obligatorio | Descripción |
|-------|------|-------------|-------------|
| `status` | `forwarded` \| `not_assigned` | sí | `forwarded` si se envió al asesor asignado; `not_assigned` si el caso no está `assigned` |
| `case_id` | identificador | sí | caso del mensaje |

#### Errores

| HTTP | error | Cuándo |
|------|-------|--------|
| 401 | unauthorized | falta `X-Service-Token` o no es válido |
| 422 | validation_error | el cuerpo no valida contra `CaseClientMessageRequest` |
| 404 | not_found | el caso no existe |
| 502 | upstream_error | falló el envío al asesor (la llamada a `POST /send` del gateway falla) |
| 500 | internal_error | error inesperado |
```

Notas de redacción:

- «si el caso existe y no está `assigned`» cubre `open`, `timed_out` y `closed`. Se
  deduce del acceptance de la #15: la lista de `status` es `forwarded | not_assigned`
  y la de errores no incluye `409`, así que un caso `closed` no es error. El texto no
  enumera los estados para no fijar en el contrato el modelo interno de handover
  (mismo criterio que la #9 con `timed_out`).
- `at` se describe como «momento del mensaje del cliente». Qué valor concreto envía
  el orquestador (p. ej. el `received_at` de `POST /messages`) lo decide la #16.

### 4.2 Línea `- **Llama:**` de `### POST /cases/{id}/close` (R14)

```markdown
- **Llama:** asesor (herramienta interna con token; panel en el futuro), orchestrator (comando `/cerrar` de un asesor desde Telegram, #16)
```

### 4.3 Fila `S13` (al final de `## Supuestos a confirmar`, R15–R18, R36–R39)

```markdown
| S13 | Solo se reenvían al asesor, con `POST /cases/{id}/client-message`, los mensajes de un cliente cuyo caso está `assigned`; con un caso `open`, con `not_assigned` o con `404` sigue el flujo actual (RAG, rechazo o traspaso). Si el reenvío falla (`502`), el cliente recibe un texto fijo y no se vuelve al RAG. Los comandos de asesor `/responder <case_id> <texto>` y `/cerrar <case_id>` llegan por `POST /messages`, cuyo contrato no cambia; un mensaje de un asesor que no es `/responder` ni `/cerrar` sigue el flujo actual, como el de cualquier cliente. Los comandos se autorizan con las reglas de S12; en ellos el `advisor_id` es el `telegram_user_id` del update validado con `TELEGRAM_WEBHOOK_SECRET`, nunca un id escrito en el texto del mensaje, y la pertenencia a `ADVISOR_CHAT_IDS` se comprueba con ese `telegram_user_id`, no con el `chat_id`; por eso un id de grupo (negativo) de `ADVISOR_CHAT_IDS` no puede usar los comandos | — |
```

La redacción puede variar mientras los tests de `tasks.md` encuentren los fragmentos
que buscan (listados en T18–T21 y T31–T34).

Encaje con S6. S6 dice que el `advisor_id` es el chat_id del asesor (de
`ADVISOR_CHAT_IDS`). En un chat privado de Telegram el `chat_id` y el
`telegram_user_id` del remitente coinciden, así que S6 sigue valiendo para la
versión mínima y S13 no lo modifica (R34). La diferencia solo aparece con un id de
grupo (negativo, que la #10 acepta en `ADVISOR_CHAT_IDS`): un `telegram_user_id`
siempre es positivo, así que ese id nunca casa con un remitente y no puede usar los
comandos. Es lo seguro: comparar con el `chat_id` dejaría usar los comandos a
cualquier miembro del grupo. Ver §7 (supuesto conservador adoptado en modo nocturno).

## 5. Cómo se amplían los tests existentes

Regla: solo añadir líneas. Ninguna línea de aserción existente se borra ni se relaja.
No se editan listas de una sola línea (`TEXT_MODELS`, el `parametrize` de
`test_datetime_without_timezone_is_rejected`): sus casos se cubren con tests nuevos,
para que el diff de `contracts/tests/` no tenga líneas eliminadas.

- `test_contratos_doc.py`:
  - `ROUTES["POST /cases/{id}/client-message"] = "handover"` → los parametrizados
    `test_doc_has_a_section_per_route` (R1), `test_route_names_exposing_service` (R2),
    `test_route_names_caller` (R3, no vacío), `test_route_names_models_in_package`
    (R4), `test_request_table_lists_every_request_field` (R5),
    `test_response_section_has_success_code_and_fields` (R6) y
    `test_errors_table_has_common_rows` (R7).
  - `SUCCESS_CODES[...] = "200"` (R6).
  - `OWN_ERRORS[...] = [("404", "not_found"), ("502", "upstream_error")]` (R8).
  - El conjunto `expected` de `test_common_rules_document_error_shape_and_codes` NO
    cambia: ya contiene `404 not_found` y `502 upstream_error`.
- `test_examples.py`: tres entradas en `EXAMPLES` y dos nombres en `MODEL_NAMES` →
  `test_every_example_validates_against_its_model`, `test_every_example_file_is_mapped`
  y `test_every_model_has_an_example` (R29–R32).
- `test_models.py`: en `BASE_EXAMPLES`,
  `CaseClientMessageRequest: ("case_client_message_request.json", None)` y
  `CaseClientMessageResponse: ("case_client_message_response.json", None)` →
  `test_missing_required_field_is_rejected` (R20, R21, R24) y
  `test_unexpected_field_is_rejected` (R27). En `IDENTIFIER_FIELDS`,
  `(CaseClientMessageResponse, "case_id")` → `test_invalid_identifier_is_rejected`
  (R26). `test_every_model_has_a_required_field_case_except_check_timeouts_request`
  sigue verde (ambos modelos tienen campos obligatorios).
- `test_packaging.py`: dos nombres en `MODEL_NAMES` →
  `test_model_is_exported_and_is_base_model` (R28).

## 6. Alternativas descartadas

- **Reutilizar `POST /cases/{id}/reply` en sentido inverso o un `POST /send` directo
  del orquestador al chat del asesor.** El orquestador no conoce qué asesor tiene
  asignado el caso ni la lista de asesores: ambos viven en handover
  (`docs/architecture.md` §3.1; acceptance #16: «el orquestador no lee la lista de
  asesores»). Además `reply` tiene la dirección contraria y la expone el orquestador.
- **Añadir `case_status` o `assigned_to` a una respuesta existente (p. ej.
  `HandoverResponse`) para que el orquestador decida si reenvía.** Modifica un modelo
  publicado (rompe R34) y obliga a una segunda llamada para enviar; la ruta nueva
  decide y envía en una sola llamada, y `not_assigned` deja al orquestador seguir el
  flujo actual sin otra consulta.
- **Responder `409` (`case_not_assigned` o `case_closed`) cuando el caso no está
  `assigned`.** El acceptance fija `200` con `status` = `not_assigned`: que el caso
  no esté asignado es el camino normal de casi todos los mensajes (S13), no un error;
  y un código nuevo exigiría tocar `## Reglas comunes`.
- **Editar la celda «Dónde» de las filas `404` y `502 upstream_error` de
  `## Reglas comunes`, o añadir filas duplicadas para la ruta nueva.** Lo primero
  contradice el acceptance («la línea `Llama` es el único cambio de texto en una
  sección existente») y el precedente de la #9 (R13 retirado por el humano). Lo
  segundo deja dos filas con el mismo código en la tabla, ambiguo para quien la lee.
- **Un campo `chat_id` o `contact_id` en `CaseClientMessageRequest`.** No lo pide el
  acceptance; handover ya tiene el caso (y su asesor asignado) por `{id}`.

## 7. Supuestos a confirmar

| Id | Supuesto | Valor por defecto |
|----|----------|-------------------|
| S13 | Funcionamiento decidido por el humano el 2026-10-31 para la #16 (§4.3): reenvío solo con `assigned`; `open`/`not_assigned`/`404` → flujo actual; fallo `502` → texto fijo sin RAG; comandos por `POST /messages` sin cambios; mensaje de asesor que no es comando → flujo actual (R36); comandos autorizados con S12 (R38, enlace pedido en la revisión del spec; la #16 ya exige un remitente «autorizado (#14)»); `advisor_id` = `telegram_user_id` del update validado | — |
| — | **Supuesto conservador adoptado en modo nocturno (2026-11-01; el humano no lo ha decidido).** Identidad de los comandos (R37, R39): `ADVISOR_CHAT_IDS` se compara con el `telegram_user_id` del remitente, no con el `chat_id`; un id de grupo (negativo, permitido por la #10) no puede usar `/responder` ni `/cerrar`. Motivo: es la opción más restrictiva (con el `chat_id`, cualquier miembro de un grupo podría usar los comandos), coincide con la decisión del humano «el `advisor_id` es el id del remitente del webhook» (#16) y no cambia la #10 (los grupos siguen recibiendo avisos). No bloquea la implementación. **Alternativa** (si el humano la elige después): exigir ids positivos para los asesores que usen comandos (lo validaría la #10/#16 al cargar `ADVISOR_CHAT_IDS`; S13 diría entonces que los ids de asesor son positivos en vez de R39); se sustituirían R39 y T34 y R37 se mantendría | comparar con `telegram_user_id`; los grupos no usan comandos |
| — | Un caso que existe y no está `assigned` (incluido `closed`) responde `200` `not_assigned`. Derivado del acceptance de la #15 (no hay `409` en su lista de errores). No es una decisión nueva; en modo nocturno se mantiene sin confirmación porque es lo único compatible con el acceptance (el cliente de un caso cerrado vuelve al flujo actual) | — |
| — | `at` = momento del mensaje del cliente; el valor concreto que envía el orquestador lo fija la #16 | — |

Ninguna duda de `docs/proyecto.md` §12 se resuelve aquí; no hay variables de entorno
nuevas en `.env.example` (los textos fijos configurables son de la #16).

## 8. Dependencias

Ninguna nueva. Se usa `pydantic>=2.12,<3`, ya fijado en `contracts/requirements.txt`.
