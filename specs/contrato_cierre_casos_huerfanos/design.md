# Design — contrato_cierre_casos_huerfanos (feature #17)

> Cómo se construye lo pedido en `requirements.md`. Fuentes: acceptance de la #17,
> decisión del humano del 2026-10-31 (opción C + procedimiento A de
> `progress/specreview_conversacion_cliente_asesor.md` §6 y «Decisiones para el humano»
> punto 2; cambio 5 / D11 de `progress/specreview_autorizacion_asesores.md`). Forma y
> estilo: los de la #13 (`specs/contrato_autorizacion_asesores/`, excepciones cerradas
> E1/E2 de su §1.1). Apoyado en `docs/architecture.md` §3 (principios 1 y 2: cambiar un
> contrato es una feature propia) y `docs/conventions.md`.

## 1. Alcance

- Solo se tocan `contracts/CONTRATOS.md` (una línea) y
  `contracts/tests/test_contratos_doc.py` (solo añadir tests). No se toca `services/`,
  `eval/`, `scripts/`, `docker-compose.yml`, `.github/` ni `requirements*.txt`.
- Sin modelos, ejemplos, alias ni rutas nuevos: la regla es comportamiento de rutas ya
  publicadas (`authorize`, `close`, `reply`, `assign`) y vive en S12, como el resto de
  reglas de autorización de la #13.
- Sin dependencias nuevas. Sin variables de entorno nuevas (`ADVISOR_CHAT_IDS` ya existe).
- La #14 implementa la regla y el recuento al arrancar; **no edita el contrato**. Si la
  #14 necesitara otro texto en el contrato, sería otra feature de contrato.

### 1.1 Excepción al principio aditivo (lista cerrada)

Decidido por el humano (2026-10-31): S12 se actualiza. Es la **única** línea publicada de
`contracts/` que cambia. No se añaden filas ni líneas nuevas en `CONTRATOS.md`.

| # | Línea publicada | R | Verificación | Motivo |
|---|-----------------|---|--------------|--------|
| H1 | Fila `S12` de `## Supuestos a confirmar` (línea 436 de la versión actual) | R1-R11 (contenido), R12 (diff exacto) | tests T3-T13; comprobación de diff T14 | opción C + procedimiento A |

**H1 — antes** (`CONTRATOS.md`, línea 436 de la versión actual, literal):

```markdown
| S12 | Autorización de asesores (`POST /cases/{id}/authorize`). Solo son asesores los chat_id de `ADVISOR_CHAT_IDS` (hasta que existan el panel y la verificación de cuentas); un `advisor_id` que no está en `ADVISOR_CHAT_IDS` recibe `403` con `error` = `forbidden`. Responder (`reply`): un caso `open` o `timed_out` lo responde cualquier asesor registrado y la primera respuesta lo asigna; un caso `assigned` solo lo responde el asesor asignado. Cerrar (`close`): un caso `open` o `timed_out` lo cierra cualquier asesor registrado; un caso `assigned` solo lo cierra el asesor asignado. Sin reasignación y sin rol supervisor. Las mismas reglas se aplican en `POST /cases/{id}/reply` (el orquestador responde `403` sin enviar nada al cliente), `POST /cases/{id}/close` y `POST /cases/{id}/assign` (handover responde `403` sin modificar el caso); asignar un caso ya `assigned` (S11) solo responde `200` al asesor asignado y otro asesor recibe `403`. Esto cambia el `200` sin cambios que S11 daba en la #9 a cualquier asesor: el asesor asignado sigue recibiendo `200` sin cambios. Precedencia de errores en `POST /cases/{id}/authorize`, `POST /cases/{id}/close` y `POST /cases/{id}/assign`: `403` (asesor no registrado) → `404` (caso inexistente) → `409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8) → `403` (caso asignado a otro asesor). En `POST /cases/{id}/reply` el orquestador autoriza antes de comprobar si el caso existe: un `advisor_id` no registrado recibe `403` con `error` = `forbidden` aunque el caso no exista. `POST /cases/{id}/close` sobre un caso `closed` sigue S8: `200` sin cambios para cualquier asesor registrado, aunque no sea el asignado; `authorize` con `action` = `close` sobre un caso `closed` responde `409`. `POST /cases/{id}/reply` sobre un caso `closed` responde `409` con `error` = `case_closed`, sin enviar nada al cliente (el orquestador propaga el `409` de `authorize`). Si handover no está disponible para autorizar, el orquestador falla cerrado: no envía la respuesta y responde `502` con `upstream_error` (la fila `502 upstream_error` ya publicada de `POST /cases/{id}/reply`). La autorización por HTTP con `SERVICE_TOKEN` no impide que un proceso que ya tenga ese token suplante un `advisor_id` registrado; la identidad por persona llega con la #16 (remitente del webhook validado) o con el panel y la verificación de cuentas. | — |
```

**H1 — después** (literal; una sola línea, fin de línea LF como el resto del archivo):

```markdown
| S12 | Autorización de asesores (`POST /cases/{id}/authorize`). Solo son asesores los chat_id de `ADVISOR_CHAT_IDS` (hasta que existan el panel y la verificación de cuentas); un `advisor_id` que no está en `ADVISOR_CHAT_IDS` recibe `403` con `error` = `forbidden`. Responder (`reply`): un caso `open` o `timed_out` lo responde cualquier asesor registrado y la primera respuesta lo asigna; un caso `assigned` solo lo responde el asesor asignado. Cerrar (`close`): un caso `open` o `timed_out` lo cierra cualquier asesor registrado; un caso `assigned` solo lo cierra el asesor asignado, salvo un caso huérfano. Caso huérfano: un caso `assigned` cuyo `advisor_id` es nulo o ya no está en `ADVISOR_CHAT_IDS`. Un caso huérfano lo cierra cualquier asesor registrado: `POST /cases/{id}/close` lo pasa a `closed` y `authorize` con `action` = `close` responde `200` con `allowed` = `true`; cerrarlo no es reasignarlo. Un caso huérfano no lo responde ni lo asigna ningún otro asesor: `POST /cases/{id}/reply` y `authorize` con `action` = `reply` responden `403` con `error` = `forbidden`, y `POST /cases/{id}/assign` responde `403` con `error` = `forbidden` sin modificar el caso, como con cualquier caso asignado a otro asesor. Sin reasignación y sin rol supervisor. Las mismas reglas se aplican en `POST /cases/{id}/reply` (el orquestador responde `403` sin enviar nada al cliente), `POST /cases/{id}/close` y `POST /cases/{id}/assign` (handover responde `403` sin modificar el caso); asignar un caso ya `assigned` (S11) solo responde `200` al asesor asignado y otro asesor recibe `403`. Esto cambia el `200` sin cambios que S11 daba en la #9 a cualquier asesor: el asesor asignado sigue recibiendo `200` sin cambios. Precedencia de errores en `POST /cases/{id}/authorize`, `POST /cases/{id}/close` y `POST /cases/{id}/assign`: `403` (asesor no registrado) → `404` (caso inexistente) → `409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8) → `403` (caso asignado a otro asesor), escalón que no se aplica a `POST /cases/{id}/close` ni a `authorize` con `action` = `close` sobre un caso huérfano (para ellos, superados los tres primeros escalones, el cierre está permitido). En `POST /cases/{id}/reply` el orquestador autoriza antes de comprobar si el caso existe: un `advisor_id` no registrado recibe `403` con `error` = `forbidden` aunque el caso no exista. `POST /cases/{id}/close` sobre un caso `closed` sigue S8: `200` sin cambios para cualquier asesor registrado, aunque no sea el asignado; `authorize` con `action` = `close` sobre un caso `closed` responde `409`. `POST /cases/{id}/reply` sobre un caso `closed` responde `409` con `error` = `case_closed`, sin enviar nada al cliente (el orquestador propaga el `409` de `authorize`). Si handover no está disponible para autorizar, el orquestador falla cerrado: no envía la respuesta y responde `502` con `upstream_error` (la fila `502 upstream_error` ya publicada de `POST /cases/{id}/reply`). La autorización por HTTP con `SERVICE_TOKEN` no impide que un proceso que ya tenga ese token suplante un `advisor_id` registrado; la identidad por persona llega con la #16 (remitente del webhook validado) o con el panel y la verificación de cuentas. Retirada de un asesor: antes de quitar su chat_id de `ADVISOR_CHAT_IDS`, el asesor cierra sus casos; al arrancar, handover registra cuántos casos huérfanos hay, sin sus ids. | — |
```

#### Qué cambia dentro de la línea (tres inserciones, nada se borra)

Todo el texto de la línea «antes» se conserva, carácter a carácter y en el mismo orden;
solo se insertan tres tramos:

1. Tras «un caso `assigned` solo lo cierra el asesor asignado» (antes del punto) se inserta
   «, salvo un caso huérfano» y, tras ese punto, las tres frases «Caso huérfano: …»,
   «Un caso huérfano lo cierra …; cerrarlo no es reasignarlo.» y «Un caso huérfano no lo
   responde ni lo asigna … asignado a otro asesor.» (R1-R7).
2. Tras «→ `403` (caso asignado a otro asesor)» (antes del punto) se inserta «, escalón que
   no se aplica a … sobre un caso huérfano (para ellos, superados los tres primeros
   escalones, el cierre está permitido)» (R8, R9).
3. Tras «… y la verificación de cuentas.» (antes de « | — |») se inserta « Retirada de un
   asesor: …, sin sus ids.» (R10, R11).

La línea «después» no contiene `|` dentro del texto (mismo número de `|` que la «antes»),
así que `_assumption_row("S12")` la sigue leyendo entera.

#### Decisión: `advisor_id` nulo

**Decidido por el humano (2026-10-31):** un caso `assigned` con `advisor_id` nulo es un caso
huérfano. Un asesor registrado puede cerrarlo (`POST /cases/{id}/close` y `authorize` con
`action` = `close` → `200 allowed=true`), pero no responderlo ni asignarlo (`403 forbidden`).
Por eso la definición de la línea «después» dice «cuyo `advisor_id` es nulo o ya no está en
`ADVISOR_CHAT_IDS`» (R1, test T3): «ya no está» solo sugería un asesor que antes estuvo en la
lista. Las demás frases de S12 hablan de «caso huérfano», así que R2-R9 se aplican también
al caso con `advisor_id` nulo sin más texto.

La #14 (`specs/autorizacion_asesores/`) lo trata como huérfano y su vocabulario «Caso
huérfano» (`requirements.md`) ya lo recoge como decidido por el humano (2026-10-31), con la
regla publicada por esta feature; el razonamiento técnico sigue en §3.1 de su `design.md`.
Su T8 depende de ello: deja sin cambios `test_close_marks_closed_and_records_advisor` porque
un `assigned` sin `advisor_id` cuenta como huérfano. Con esta feature queda publicado en S12.
Este spec no edita la #14.

Este cambio sigue siendo una inserción: la frase «Caso huérfano: …» entera es nueva (tramo
1 de arriba), así que el diff «antes» → «después» sigue sin borrados ni sustituciones. No
toca ningún fragmento que busquen los tests existentes de S12 (§5).

#### Coherencia con C1/C2 de la #13 (la frase de precedencia)

- **C1** (precedencia `403` no registrado → `404` → `409`/S8 → `403` otro asesor): los tres
  primeros escalones no cambian para nadie, tampoco para un huérfano. Un asesor retirado que
  intenta cerrar su propio caso huérfano sigue recibiendo `403` en el primer escalón (no
  está registrado). Solo el cuarto escalón se salta, y solo para `close` y
  `authorize(close)` sobre un huérfano. Para `assign` y `authorize(reply)` sobre un
  huérfano el cuarto escalón sigue aplicándose (`403`), igual que `reply` en el
  orquestador (que propaga el `403` de `authorize`).
- **C2** (`close` sobre `closed` → `200` S8; `authorize(close)` sobre `closed` → `409`): un
  caso huérfano está `assigned`, nunca `closed`; una vez cerrado deja de ser huérfano y se
  le aplica C2 tal cual.
- «Sin reasignación y sin rol supervisor» sigue siendo cierto: cerrar no asigna y
  cualquier asesor registrado (no un rol) puede cerrar el huérfano.
- «Las mismas reglas se aplican en … `POST /cases/{id}/close` …» arrastra la excepción a la
  ruta `close` de handover sin editar esa frase.

### Fuera de alcance

- **Implementar** la regla en handover (`authorize`, `close`), el recuento de huérfanos al
  arrancar y sus tests: es la #14 (ver §6).
- **Editar otras líneas publicadas**: la prosa de `### POST /cases/{id}/close` («Cerrar un
  caso ya cerrado responde igual …»), su fila `403 | forbidden` («el asesor no está
  autorizado a cerrar el caso; el caso no cambia (S12)»), la fila común `403`, la prosa de
  `### POST /cases/{id}/authorize` («según las reglas de S12») y la fila `S11`. Todas siguen
  siendo ciertas tras H1 porque remiten a S12 o no hablan de quién cierra un `assigned`.
- **Un supuesto nuevo** (p. ej. S14): descartado en §4.
- **`client-message` y S13** (#15): ver §7, duda 1.
- **`specs/contrato_autorizacion_asesores/`** (#13, done): no se edita. Su §4.4 (texto de
  S12) y sus R21/R43 quedan como histórico; el texto vigente de S12 es el de H1.

## 2. Archivos

| Acción | Ruta | Cambio |
|--------|------|--------|
| modificar | `contracts/CONTRATOS.md` | sustituir la línea «antes» de H1 por la «después» (§1.1). Nada más |
| modificar | `contracts/tests/test_contratos_doc.py` | añadir al final un bloque `# ── contrato_cierre_casos_huerfanos (feature #17) ──…` con los 11 tests de `tasks.md` (T3-T13). Ninguna línea existente se toca |

## 3. Firmas nuevas

Solo funciones de test, en `contracts/tests/test_contratos_doc.py`, que reutilizan el
helper existente `_assumption_row("S12")` (sin helpers nuevos). Cada docstring empieza por
`contrato_cierre_casos_huerfanos R<n>:`.

```python
def test_assumptions_s12_defines_orphan_case() -> None: ...                       # R1
def test_assumptions_s12_orphan_close_by_any_registered_advisor() -> None: ...    # R2
def test_assumptions_s12_orphan_authorize_close_allowed() -> None: ...            # R3
def test_assumptions_s12_orphan_close_is_not_reassignment() -> None: ...          # R4
def test_assumptions_s12_assigned_close_rule_has_orphan_exception() -> None: ...  # R5
def test_assumptions_s12_orphan_reply_forbidden() -> None: ...                    # R6
def test_assumptions_s12_orphan_assign_forbidden() -> None: ...                   # R7
def test_assumptions_s12_precedence_other_advisor_step_skips_orphan_close() -> None: ...  # R8
def test_assumptions_s12_precedence_orphan_close_allowed_after_first_steps() -> None: ...  # R9
def test_assumptions_s12_documents_advisor_retirement_procedure() -> None: ...    # R10
def test_assumptions_s12_documents_orphan_count_at_startup() -> None: ...         # R11
```

No hay excepciones nuevas ni reutilizadas: el contrato solo declara códigos ya publicados
(`200`, `403 forbidden`).

## 4. Alternativas descartadas

- **Un supuesto nuevo (`S14`) en vez de editar S12.** Descartada: S12 seguiría diciendo
  «un caso `assigned` solo lo cierra el asesor asignado» y la precedencia terminaría en
  «`403` (caso asignado a otro asesor)» sin salvedad, así que el documento se
  contradiría a sí mismo (mismo motivo por el que la #13 editó S11 en vez de dejar que S12
  lo estrechara). Además el acceptance pide expresamente actualizar S12, y S13 está
  reservado para la #15.
- **Una ruta nueva (p. ej. `POST /cases/{id}/close-orphan`) o un `action` nuevo en
  `authorize`.** Descartada: el humano decidió que el cierre se hace con
  `POST /cases/{id}/close` y `authorize(close)`, rutas ya publicadas. Una ruta o un literal
  nuevos ampliarían el contrato sin necesidad.
- **Reasignar el huérfano (opción D)**, **no reenviar al retirado (B)**, **herramienta de
  administración (E)** y **vencimiento de `assigned` (F)**: no elegidas por el humano
  (eligió C + A). No se documentan en el contrato.
- **Editar la fila `403 | forbidden` de `### POST /cases/{id}/close`** para nombrar el
  huérfano. Descartada: sigue siendo cierta (si el asesor no está autorizado, `403`) y el
  humano solo autorizó cambiar S12.
- **Un test que exija la línea «después» completa por igualdad.** Descartada: una futura
  feature de contrato que edite S12 tendría que editar (debilitar) este test. La igualdad
  literal se comprueba una vez, con el diff de T14; los tests buscan fragmentos, como en
  la #13.
- **Verificar R12-R14 con `git diff` contra `HEAD`.** Descartada: los cambios de la #13
  aún no están confirmados en git (`git status`: `contracts/` modificado), así que el diff
  contra `HEAD` mezclaría las dos features. Se compara contra una copia de `contracts/`
  tomada justo antes de editar (T1, T14, T15).

## 5. Tests de contrato existentes que leen S12 (o las líneas cercanas)

Revisados en `contracts/tests/test_contratos_doc.py` (versión actual, solo lectura) con
la línea «después» de H1: **todos los fragmentos que buscan siguen presentes, literales**
(comprobado sobre el texto de §1.1, incluida la definición con «es nulo o ya no está», que
solo cambia texto nuevo de esta feature: ningún test existente busca «huérfano» ni un
fragmento que cruce esa frase; `` `ADVISOR_CHAT_IDS` `` de R19 sigue apareciendo). **Ningún test cambia de código, ninguna aserción se
elimina y ninguna expectativa cambia.** Se listan para que el implementer no los toque y el
reviewer lo compruebe.

| Test existente (`contracts/tests/test_contratos_doc.py::…`) | R (#13) | Qué lee | ¿Cambia su expectativa? |
|---|---|---|---|
| `test_assumptions_s12_defines_who_is_advisor` | R19 | S12 | No |
| `test_assumptions_s12_reply_rules` | R20 | S12 | No (la regla de responder no cambia) |
| `test_assumptions_s12_close_rules` | R21 | S12: «lo cierra cualquier asesor registrado», «solo lo cierra el asesor asignado» | No. Ambos fragmentos siguen literales; «solo lo cierra el asesor asignado» va ahora seguido de «, salvo un caso huérfano», que el test no mira. La salvedad la cubre el test nuevo T7 (R5) |
| `test_assumptions_s12_no_reassignment_nor_supervisor` | R22 | S12: «Sin reasignación», «supervisor» | No |
| `test_assumptions_s12_fails_closed` | R23 | S12 | No |
| `test_assumptions_s12_applies_to_existing_routes` | R24 | S12 | No |
| `test_assumptions_s12_identity_limitation` | R25 | S12 | No |
| `test_assumptions_s12_limits_s11_to_assigned_advisor` | R26 | S12 | No |
| `test_assumptions_s12_error_precedence` | R43 | S12: cadena de precedencia completa hasta «→ `403` (caso asignado a otro asesor)» | No. La cadena sigue literal y contigua; H1 añade después «, escalón que no se aplica …», que el test no mira. La salvedad la cubren T10 (R8) y T11 (R9) |
| `test_assumptions_s12_close_on_closed_keeps_s8` | R44 | S12 | No |
| `test_assumptions_s12_fail_closed_reuses_reply_502` | R45 | S12 y tabla de reply | No |
| `test_assumptions_s12_reply_on_closed_is_case_closed` | R46 | S12 | No |
| `test_assumptions_s12_reply_authorizes_before_case_lookup` | R47 | S12 | No |
| `test_assumptions_s12_documents_s11_change` | R51 | S12 | No |
| `test_assumptions_s11_other_advisor_gets_forbidden` / `test_assumptions_include_assign_idempotency` | R50 / #9 R14 | S11 (no se edita) | No |
| `test_assumptions_mention_s1_to_s10` | R15 | S1-S10 | No |
| `test_authorize_section_documents_allowed_true_or_forbidden`, `test_authorize_section_documents_closed_case` | R12, R13 | prosa de `authorize` (no se edita) | No |
| `test_existing_case_routes_document_forbidden[…close]`, `test_existing_case_routes_keep_their_error_rows[…close]`, `test_common_rules_forbidden_row_cites_case_routes` | R15-R18, R14 | tablas de errores (no se editan) | No |

Si al implementar cualquiera de estos tests fallara, es que la línea «después» no se copió
literal: se corrige la línea, nunca el test (R14).

Tests de servicios que dependan de que nadie pueda cerrar el caso `assigned` de un asesor
retirado no son de contrato y aún no existen (la #14 está `blocked`); ver §6.

## 6. Qué partes de `specs/autorizacion_asesores/` (#14) deben reflejar esta regla

Este spec **no** las edita; las mantiene el spec_author de la #14 (con revisión). Se citan
por id de requirement (R), de decisión (D), de tarea (T) y por sección, nunca por número de
línea, porque ese spec se edita en paralelo. Según su versión actual, la #14 **ya
incorpora** la regla; esta lista sirve para que el reviewer compruebe que sigue alineada:

- **Cabecera y vocabulario de `requirements.md`**: la decisión 4 (opción C + procedimiento
  A) figura como decidida por el humano y remite a esta feature. El término «Caso huérfano»
  incluye el `advisor_id` nulo como decisión del humano (2026-10-31), publicada por esta
  feature (§1.1, «Decisión: `advisor_id` nulo»). Ya está alineado; solo hay que comprobar que
  sigue así.
- **R7** (`authorize` sobre caso `assigned` a otro asesor registrado → `403`) y **R15**
  (`close` ídem → `403`): reescritas para excluir al huérfano, que se rige por R46-R48.
- **R46** (`authorize(close)` de un asesor registrado sobre un huérfano → `200
  allowed=true`): corresponde a R3 y R9 de aquí.
- **R47** (`close` de un asesor registrado sobre un huérfano → `closed`, `closed_by` = quien
  cierra): corresponde a R2 de aquí y responde la duda 3 de §7.
- **R48** (`authorize(reply)` y `assign` sobre un huérfano → `403`) y **R12** (`assign` de
  otro asesor → `403`): corresponden a R6 y R7 de aquí. **R4/R11/R14** (asesor no
  registrado → `403`, también el retirado): sin cambio de comportamiento.
- **R49-R52** (recuento de huérfanos al arrancar, sin ids, en el `lifespan`): corresponden a
  R11 de aquí. Evento, nivel y comportamiento ante fallo siguen **[REVISAR]** en sus
  **D12** y **D13** (§7, duda 4).
- **`design.md` §3.1** (nota del `advisor_id` nulo) y **§3.2** (tabla de pasos: paso 4a para
  otro asesor registrado, **paso 4b** para el huérfano; viñeta del asesor retirado que
  recibe `403` en el paso 1): coherentes con H1 y con la coherencia C1 de §1.1.
- **`design.md` §8.2, D11** (casos `assigned` de un asesor retirado): decidida, con remisión
  a esta feature y a S12.
- **`tasks.md`**: **T5** (`close_case` pasos 1-5, cubre R47), **T54** (`is_orphan_case`,
  `can_act_on_case`), **T8** (sin cambios porque el `assigned` sin `advisor_id` es huérfano;
  ahora apoyado en la decisión del humano), **T14** (retirado → `403`, sin cambios), **T17**
  y **T23** (otro asesor registrado → `403`, sin cambios) y **T53** (D11 ya no pendiente;
  D12 y D13 sí).
- Registro de denegaciones: `close`/`authorize(close)` sobre un huérfano por un asesor
  registrado es un permiso, no una denegación (no se registra); `reply`/`assign`/
  `authorize(reply)` de otro asesor se siguen registrando como hoy.

También afecta, sin editarse aquí, a `specs/conversacion_cliente_asesor/` (#16): la viñeta
«Asesor retirado de `ADVISOR_CHAT_IDS` con un caso `assigned`» de su `design.md` §7 y la
fila «Duda abierta» correspondiente de su §11 («sin cambios»): con esta regla, `/cerrar` de
cualquier asesor registrado sobre un huérfano pasa `authorize(close)` y cierra el caso.

## 7. Supuestos a confirmar

| Id | Supuesto | Valor por defecto |
|----|----------|-------------------|
| S12 | Se amplía con el caso huérfano (incluido el `advisor_id` nulo), su cierre por cualquier asesor registrado, la prohibición de responderlo o asignarlo, la salvedad en la precedencia y el procedimiento de retirada (texto en §1.1). Decidido por el humano (2026-10-31) | — |

Ninguna duda de `docs/proyecto.md` §12 se resuelve aquí; no hay variables de entorno
nuevas en `.env.example`.

### Dudas que este spec NO resuelve (no se inventan)

1. **Reenvío de mensajes del cliente a un asesor retirado (Ley 1581).** El humano eligió C +
   A, no B. Mientras el huérfano no se cierre, `client-message` (#15, S13) seguirá
   tratándolo como `assigned` y la #16 reenviará los mensajes del cliente al Telegram del
   asesor retirado (`progress/specreview_conversacion_cliente_asesor.md` §6, punto 1). Este
   spec no lo cambia ni lo menciona en S12. Si el humano quiere cortarlo, sería un cambio
   de S13/#15.
2. **Cuándo deja de estar un asesor en `ADVISOR_CHAT_IDS`.** S12 define el huérfano por la
   lista, sin decir «en qué momento». Lo que se deriva del sistema actual (no se escribe en
   S12): handover carga la lista al arrancar (#10), así que un cambio en la lista se ve tras
   reiniciar handover; si se vuelve a añadir el id, el caso deja de ser huérfano y vuelven
   las reglas normales. Si el humano quiere otra semántica, es otra decisión.
3. **`closed_by` al cerrar un huérfano.** Se deriva del contrato publicado
   (`CaseCloseRequest.advisor_id` = «asesor que cierra el caso»): queda como cerrador quien
   cierra, no el asesor retirado. S12 no lo repite; lo confirma la #14.
4. **Detalles del recuento al arrancar** (nombre del evento, nivel, si se registra también
   cuando hay 0, si se repite periódicamente). S12 solo fija «al arrancar», «cuántos» y
   «sin sus ids». Lo decide la #14 con su revisión.
5. **Aviso al cliente o al asesor que cierra un huérfano.** No decidido (es la A12 de la
   #16). S12 no dice nada.
6. **Caso `assigned` de un asesor activo que nunca lo cierra** (opción F). Fuera de esta
   decisión.

El caso `assigned` con `advisor_id` nulo **no** es una duda abierta: lo decidió el humano el
2026-10-31 (§1.1, «Decisión: `advisor_id` nulo»; R1).

## 8. Dependencias

Ninguna nueva. Los tests usan `pytest` y el helper existente del archivo.
