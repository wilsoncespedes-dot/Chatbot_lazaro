# Spec review — autorizacion_asesores (feature #14)

**Veredicto:** SPEC_CHANGES_REQUESTED

Revisado el 2026-10-31 contra `specs/autorizacion_asesores/{requirements,design,tasks}.md`, el
acceptance de la #14 (A1-A11) en `feature_list.json`, `progress/propuesta_etapa2.md` §4 y §6, la
versión ACTUAL de `specs/contrato_autorizacion_asesores/` (#13, R1-R47, C1-C6), los specs de la
#10, #11, #12 y #16, y el código actual de `services/handover` y `services/orchestrator`.
La feature sigue `blocked`; este informe no cambia su estado ni toca `feature_list.json` ni specs.
Línea base: `.venv/Scripts/python.exe -m pytest services/handover services/orchestrator` → 212 passed.

Resumen: el spec es fiel a las decisiones del humano, coincide con la versión actual de la #13 y
la trazabilidad R→test está completa. Se rechaza por dos defectos que impiden cumplir R36 con el
orden fijado (10 → 11 → 12 → 13 → 14) y porque acepta sin marcar REVISAR dos consecuencias de
negocio (la carrera autorizar → asignar, que permite reasignar en silencio, y los casos de un
asesor retirado). Son cambios de texto y de tests; el diseño de fondo es correcto.

## Cobertura del acceptance
- [x] A1 (`authorize`; no registrado → `403`) → R1-R10.
- [x] A2 (`close`/`assign` con las mismas reglas, `403` sin modificar) → R11-R18.
- [x] A3 (`reply` autoriza ANTES de enviar; `403` sin enviar ni guardar) → R23-R27, R32, R33.
- [x] A4 (denegaciones registradas en ambos servicios) → R19-R22 (handover), R29-R30 (orchestrator).
- [x] A5 (solo `ADVISOR_CHAT_IDS`) → R1, R4, R11, R14.
- [x] A6 (sin asignar: cualquiera y la 1.ª respuesta asigna; `assigned`: solo el asignado; sin reasignar ni supervisor) → R2, R3, R7, R12, R13, R24. Ver cambio 3: bajo concurrencia la regla «sin reasignar» no se garantiza.
- [x] A7 (cerrar sin asignar: cualquiera; `assigned`: solo el asignado) → R15-R18.
- [x] A8 (handover caído → fallo cerrado `502`, sin enviar) → R28, R34; T43, T51.
- [x] A9 (limitación de identidad por HTTP documentada en S12 y en el design) → `design.md:308-317`; S12 de la #13 (R25).
- [ ] A10 (tests de la #7 ajustados sin debilitar) → R36 y `design.md:283-306` son correctos para los tests de la #7, pero la lista de tests existentes que cambian está incompleta respecto al estado que deja la #12 (cambio 1).
- [x] A11 (tests y prueba de seguridad obligatoria) → T32 (handover, ids falsificados: `"0111"`, `" 111"`, `"111,222"`…) y T51 (orchestrator con `HttpHandoverClient` real: `403`, `allowed=false`, `ConnectError` → nada enviado).

## EARS y verificabilidad
- [x] Cada R usa uno de los 5 patrones con un solo `DEBE`/`NO DEBE` e indica el servicio (encabezados «Servicio handover» / «Servicio orchestrator» y «(handover)»/«(orchestrator)» en el texto).
- [x] Sin verbos blandos. R16, R17, R21, R24 y R35 encadenan acciones bajo un único `DEBE`; mismo estilo aceptado en la #7, verificables con un test cada una.
- [x] Cada R tiene test nombrado: R1 T11/T32 · R2 T12 · R3 T13 · R4 T14 · R5 T15 · R6 T16 · R7 T17 · R8 T18 · R9-R10 T10 (parametrizados existentes ampliados) · R11 T19 · R12 T20 · R13 T21/T7 · R14 T22 · R15 T23 · R16 T24/T8 · R17 T25 · R18 T26 · R19 T27 · R20 T28/T26 · R21 T30/T31/T9 · R22 T29 · R23 T37/T38 · R24 T39 · R25 T40 · R26 T41 · R27 T42 · R28 T43 · R29 T44 · R30 T45 · R31 T46 · R32 T48 · R33 T49 · R34 T50 · R35 T47/T36 · R36 T52.

## Diseño (capas, fakes, SQL, reloj, separación)
- [x] Capas: reglas en `domain.py` (`is_registered_advisor`, `can_act_on_case` puras), rutas finas en `main.py`, IO en `adapters/` (`design.md:62-150`).
- [x] Fakes: `FakeCaseRepository.denials`, `FakeHandoverClient(authorize_error, fail_authorize)` con valores por defecto que no cambian los tests de la #7 (`design.md:252-267`).
- [x] SQL parametrizado: `INSERT INTO handover_denials ... VALUES (%s, %s, %s, %s)` y `CREATE TABLE IF NOT EXISTS` (`design.md:160-173`); T30 con `case_id` malicioso.
- [x] Reloj inyectado en `Denial.at` y en `advisor_forbidden` (`design.md:105-109`, `220-223`).
- [x] Separación de servicios: el orquestador no lee `ADVISOR_CHAT_IDS` ni la base de handover; pregunta por `authorize` (`design.md:345-347`). `AdvisorForbidden` duplicada por servicio, sin imports cruzados (`design.md:280-281`).
- [x] Sin dependencias nuevas ni variables nuevas (`design.md:360-363`).
- [x] Alternativas descartadas: 5 (`design.md:343-358`).
- [x] Nada peligroso: no borra datos, no usa red en tests, no toca nada fuera del repo.

## 1. Fidelidad a las decisiones del humano (§6 y criterios «Decidido»)
- [x] Fallo cerrado: R28/R34; cualquier respuesta no contemplada, `allowed` ≠ `true` u otro `case_id` → `502` sin enviar (`design.md:241-248`).
- [x] Sin reasignación ni supervisor: R12 (otro asesor → `403`), R13 (mismo asesor → `200` sin cambios). Salvedad de concurrencia en el cambio 3.
- [x] Cerrar `assigned` solo el asignado (R15, R16); sin asignar cualquiera (R17).
- [x] Limitación de identidad por HTTP documentada (`design.md:308-317`), con remisión a la #16 (remitente del webhook validado, nunca un id escrito en el texto).
- [x] Reenvío solo con `assigned`, texto fijo + `forward_failed` sin RAG y `advisor_id` = remitente en Telegram: no son de esta feature (están en la #16); la #14 no los contradice.

## 2. Decisiones marcadas REVISAR
- [x] D1-D4 (recomendaciones del leader) y D5-D9 (spec_author) marcadas **REVISAR** en `design.md:319-339`.
- [ ] En `requirements.md` llevan la marca R4, R6, R11-R14, R18, R23, R26, R28, pero no R19, R20 (D7), R22 (D8), R30 (D9) ni R35 (cambio 4).
- [ ] Hay dos decisiones de negocio sin marcar: la carrera autorizar → asignar (`design.md:36-38`, `350-353`, R35) y los casos asignados de un asesor retirado (`design.md:135-136`). Ver cambios 3 y 5.

## 3. Consumo exacto del contrato #13 (versión actual)
- [x] Modelos `CaseAuthorizeRequest`/`CaseAuthorizeResponse`/`CaseAuthorizeAction` tal como `specs/contrato_autorizacion_asesores/design.md:72-92` (`allowed: Literal[True]`).
- [x] Precedencia `403` no registrado → `404` → `closed` → `403` otro asesor (#13 R43) = tabla `design.md:120-126`.
- [x] `close` sobre `closed` → `200` sin cambios para cualquier asesor registrado (S8) y `authorize(close)` sobre `closed` → `409` (#13 R44) = R18 y R6.
- [x] `reply` sobre `closed` → `403 forbidden` (#13 R46, C5) = R26/D5.
- [x] `reply` autoriza antes de comprobar si el caso existe (#13 R47, C6) = R23/D6.
- [x] Fallo cerrado con la fila `502 upstream_error` publicada de reply (#13 R45, C3) = D3.
- [x] Asignar un `assigned`: solo `200` al asignado, otro `403` (#13 R26) = R12/R13.
- [x] No toca `contracts/` (`design.md:11-13`).
- Si la corrección en paralelo de la #13 cambia C2 (close sobre closed) o C6 (precedencia de reply), hay que reescribir R18/T26 o R23/T37-T38 sin renumerar. Hoy coinciden.

## 4. Coherencia con la #16
- [x] La #16 reutiliza `reply_to_case`, `HandoverClient.authorize`, `AuthorizationDenied`, `AdvisorForbidden` sin cambiar firmas; su única edición sobre código de la #14 es aditiva (`authorized_advisors` en el fake).
- [ ] `/cerrar` de la #16 no tiene los mismos efectos ni errores que `POST /cases/{id}/close` sobre un caso `closed` (la #14 da `200` por S8; `/cerrar` da «no tienes permiso» y un `advisor_forbidden`). El detalle y la decisión están en `progress/specreview_conversacion_cliente_asesor.md` (cambio 3); en la #14 solo afecta a la línea `Llama` de `authorize` (#13).

## 5. Coordinación con #10, #11 y #12 (orden 10 → 11 → 12 → 13 → 14)
- [x] Tabla nueva `handover_denials` y método nuevo `add_denial`: no chocan con `handover_requests`/`add_request`/`complete_request` (#11) ni con `claim_timeout`/`release_timeout_claim`/`mark_timed_out`/`update_last_messages` (#12). No toca `update_case`.
- [x] `_SCHEMA`: la sentencia nueva va al final, tras el `ALTER TABLE ... timeout_claimed_at` de la #12; `test_postgres_repository_uses_parameters_only` (modificado por la #12) no se ve afectado.
- [ ] **Firma de `assign_case`/`close_case`** (`design.md:95-102`): ganan `settings`. La #12 crea `services/handover/tests/test_timeout_races.py` con T15/T16 (`specs/vencimiento_automatico/tasks.md:32-33`), que llaman a `assign_case(case_id, "222", ...)` y a `close_case(...)` desde un `on_send`. Con la #12 ya implementada, esos tests dejan de funcionar con la #14 y no están en `design.md` §6 (`design.md:283-306`) → R36 no se puede cumplir tal como está escrito (cambio 1).
- [ ] **Conteo de `CREATE TABLE`** (`design.md:291`, `tasks.md:24` T9): dice «`== 2` → `== 3` (o +1 sobre lo que haya dejado la #11)». Con el orden fijado la #11 lo deja en 3 (`specs/registro_solicitudes_traspaso/tasks.md:40`, T22) y la #12 no lo cambia (`specs/vencimiento_automatico/design.md:366-367`): la #14 debe pasar de `3` a `4` (cambio 2).
- [ ] `design.md:31-35` («Si la #12 llega antes o después») debe describir el código tal como lo deja la #12: `make_env(advisors, repo, gateway)` y `FakeCaseRepository.timeout_claims`. Las tasks T14/T19/T22 usan `make_env(advisors=[222, 333])`, que sigue siendo compatible (cambio 2).
- [ ] **Carreras assign/close (#12 D1, riesgos (a)-(d))**: la #12 recomienda resolverlas **en la #14** (opción (b), `specs/vencimiento_automatico/design.md:386-392`). La #14 dice «no se resuelve aquí» (`design.md:36-38`) sin remitir a la D1 de la #12 ni marcarlo REVISAR. Además la #14 **agrava** la carrera: la ventana ya no es «leer → escribir» dentro de handover, sino `authorize` → `POST /send` al gateway (hasta `HTTP_TIMEOUT_SECONDS=10`) → `assign` (`design.md:205-215`). Dos asesores que contestan al mismo aviso en esos segundos llegan los dos al cliente, y si ambos `assign` leen antes de escribir, el último gana: el primero recibió `200` y queda **reasignado en silencio**, contra «sin reasignación». R35 solo cubre el caso en que el segundo `assign` ve ya `assigned` (cambio 3).
- [ ] **Conexión pg8000 compartida entre hilos (#12 D2, riesgo (f))**: la #14 la agrava un poco. Cada `POST /cases/{id}/reply` pasa a hacer dos llamadas a handover (`authorize` + `assign`), y las denegaciones añaden `INSERT`s. Todo corre en rutas síncronas sobre la misma conexión. No es bloqueante para esta feature, pero el design debe citarlo y remitir a la D2 de la #12 (cambio 3).

## Cambios requeridos
1. **R36 / `design.md` §6 / tasks:** añadir a la tabla de tests existentes que cambian `services/handover/tests/test_timeout_races.py` (T15 y T16 de la #12). El único cambio es pasar `settings` a `assign_case`/`close_case`, con las aserciones idénticas. Comprobar que el asesor `"222"` de esos tests está en `ADVISORS`: lo está, así que la semántica no cambia. Añadir una task (p. ej. T7b) y reflejarlo en T52.
2. **Orden fijado:** en `design.md:291` y `tasks.md:24` (T9), cambiar el conteo a `3` → `4`. Reescribir `design.md:23-38` partiendo del estado que dejan la #11 y la #12 (sin «antes o después»).
3. **Carrera autorizar → enviar → asignar y conexión compartida:** convertir `design.md:36-38` y la alternativa de `design.md:350-353` en una decisión **REVISAR** (D10). Debe describir la ventana real (incluye el envío al gateway), la reasignación silenciosa por «último que escribe gana» y la doble respuesta al cliente, y remitir a la D1 y la D2 de la #12. El humano elige entre las opciones de «Decisiones para el humano» (punto 1). Si elige la asignación condicional, añadir R y tests: un `assign` de otro asesor que pierde la carrera recibe `403` sin escribir.
4. Marcar **[REVISAR]** R19, R20 (D7), R22 (D8), R30 (D9) y R35 (D10) en `requirements.md`, como ya están R4, R6, R11-R14, R18, R23, R26 y R28.
5. **Asesor retirado:** `design.md:135-136` decide en silencio que un asesor retirado de `ADVISOR_CHAT_IDS` pierde también sus casos `assigned` y que nadie más puede responderlos ni cerrarlos (paso 1 para él, paso 4 para los demás). Marcarlo REVISAR (D11), con remisión a la decisión del humano sobre los casos huérfanos (punto 3 de abajo y `progress/specreview_conversacion_cliente_asesor.md`). Si el humano elige la opción C, la regla cambia aquí y en S12 de la #13, que aún se está corrigiendo.

## Decisiones para el humano
1. **Carrera autorizar → asignar (nueva, sin marcar en el spec).** Hoy: dos asesores pueden responder al cliente casi a la vez y el último `assign` puede quitar el caso al primero sin avisar. Opciones:
   - (a) Aceptarlo y documentarlo (lo que hace el spec ahora).
   - (b) **Recomendada:** asignación condicional en la #14 (`UPDATE ... WHERE status IN ('open','timed_out')`, o `assigned` al mismo asesor, con `RETURNING`) y cierre condicional (`WHERE status <> 'closed'`), como la opción (b) de la D1 de la #12. Evita la reasignación silenciosa y el cierre que borra el asesor (riesgo (c)). El segundo cliente sigue recibiendo la respuesta ya enviada, que queda registrada como `assign_failed`.
   - (c) Asignar antes de enviar. Cambia el orden de la #7 (R33): si el envío falla, el caso queda asignado sin respuesta.
2. **Conexión pg8000 compartida (D2 de la #12).** La #14 suma tráfico y la #16 lo multiplica. Conviene decidir el candado en `_run` (o una conexión por petición) antes de implementar la #16, y aplicar lo mismo en `PostgresRepository` del orquestador, que tiene el mismo patrón con `BackgroundTasks` en el pool de hilos.
3. **Casos `assigned` de un asesor retirado.** Ver opciones A-F en `progress/specreview_conversacion_cliente_asesor.md`. Afecta a esta feature si se elige permitir a cualquier asesor registrado cerrar un caso huérfano (opción C).
4. **Qué D1-D9 son de verdad de negocio:**
   - De negocio: **D2** (un asesor registrado recibe `200` al «cerrar» un caso que ya cerró otro; no cambia datos). **D4** (deriva directamente de «sin reasignación»: confirmar). **D5** (el asesor que responde a un caso cerrado recibe «forbidden» y no «caso cerrado»; afecta a lo que ve). **D7** (alcance de la auditoría: solo los `403` cuentan como denegación; los intentos sobre casos inexistentes o cerrados no quedan en handover). Además las dos sin marcar: la carrera (punto 1) y el asesor retirado (punto 3).
   - Técnicas o de seguridad, solo para confirmar: **D1** y **D6** (no revelar si un caso existe), **D3** (reutilizar la fila `502` publicada), **D8** (si falla guardar la denegación, `500`), **D9** (solo log si el caso no está vinculado). Nota sobre D8: es la política contraria a S2 de la #11, donde la auditoría no bloquea. Aquí no cambia el resultado (en ningún caso se envía nada), pero conviene confirmar que la diferencia es intencionada.

## Segunda vuelta (2026-10-31)

**Veredicto:** SPEC_CHANGES_REQUESTED

Revisado contra `specs/autorizacion_asesores/{requirements,design,tasks}.md` (R1-R53, T1-T75 + T7b),
`progress/spec_autorizacion_asesores.md`, las decisiones del humano 1-4 (2026-10-31),
`contracts/CONTRATOS.md` actual (S11, S12, tablas de `authorize`/`reply`/`close`/`assign`),
`specs/contrato_autorizacion_asesores/design.md` §4 y §9, `specs/contrato_cierre_casos_huerfanos/design.md`
(H1 «después», §6, §7), `specs/vencimiento_automatico/design.md` (riesgos (a)-(h), D1, D2) y `tasks.md`
T14-T17, y el código actual de `services/handover` y `services/orchestrator` (`_run`/`_connection`,
`HttpHandoverClient.assign`, `conftest.py`, `test_cases.py`, `test_startup.py`).
Estado en `feature_list.json`: #14 `blocked`, `depends_on` [10, 13, 17]; #17 `spec_ready`. No se ha
editado ningún spec ni `feature_list.json`.

Resumen: el contenido está bien. Las cuatro decisiones del humano están aplicadas sin invenciones,
los cambios 1-5 están resueltos, el spec está alineado con C5 y con todo §9 de la #13 y con el texto
H1 «después» de la #17, y la trazabilidad R→test es completa. Se rechaza por un solo defecto
bloqueante, el orden de las tasks (cambio 1): las tasks nuevas T54-T75 van detrás de la verificación
T52-T53 y de las tasks que dependen de ellas. Hay además dos correcciones menores (cambios 2 y 3).
Ninguna exige tocar requirements de fondo ni el design.

### Cambios 1-5 del informe previo
- [x] 1. `test_timeout_races.py` está en §6 (`design.md:480`), en T7b (`tasks.md:26`) y en T52 (`tasks.md:85`). La coherencia de T14-T17 de la #12 con las escrituras condicionales se explica en `design.md:245-254`. Se comprueba que `ADVISORS = [111, 222, 333]` (`services/handover/tests/conftest.py:19`).
- [x] 2. El conteo pasa de 3 a 4 (`design.md:49-50`, `479`; `tasks.md:27`; T71 «4 `CREATE TABLE`»). El punto de partida ya no dice «antes o después» (`design.md:26-44`), con el orden 10 → 11 → 12 → 13 → 17 → 14.
- [x] 3. La carrera y la conexión se resuelven con las decisiones 2 y 3 (D10 en `design.md:540-554`; candado en `design.md:323-355`). Las D1 y D2 de la #12 se citan en `design.md:42-44` y `608-614`.
- [x] 4. R19/R20 (D7), R22 (D8) y R30 (D9) llevan **[REVISAR]**. R35 ya no lo lleva porque lo resuelve la decisión 2.
- [x] 5. El asesor retirado queda decidido (D11, `design.md:561-573`). La vieja viñeta «queda huérfano sin salida» ha desaparecido.

### Decisiones del humano (2026-10-31)
- [x] **1 (C5).** R26 responde `409 case_closed` sin enviar, sin guardar y sin llamar a `assign` (`requirements.md:194-198`). R29 y R30 aplican solo a R25. R53 dice que un `409` no genera `advisor_forbidden` (ni evento ni log). El flujo está en `design.md:388-406` y `CaseClosed` del orquestador en `design.md:370-372`. T41 y T75 son los tests; T44 ya no se parametriza con `case_closed`. Coincide con la fila `409` de reply en `CONTRATOS.md:236` y con S12.
- [x] **2 (carrera).**
  - `assign_if_unassigned` usa `WHERE status IN (%s,%s) RETURNING case_id` y `close_if_not_closed` usa `WHERE status <> %s RETURNING case_id`, con los estados como parámetros (`design.md:222-223`).
  - Si otro asesor gana la asignación, el perdedor recibe `403` sin cambiar el caso (R38, T62). La respuesta ya enviada queda como `assign_failed` (R35, T47; `HttpHandoverClient.assign` convierte cualquier `4xx` en `ServiceUnavailable`, `services/orchestrator/orchestrator/adapters/handover.py:64-68`, y T36 lo amplía con `403`).
  - Derivadas sin inventar: R39 (`409` si se cerró en medio, igual que #7 R13 y C1), R40 (el mismo asesor recibe `200` sin escribir, que es el «o `assigned` al mismo asesor» de la decisión y S11) y R42 (S8).
  - El registro de denegación de R38 escribe en `handover_denials`, no en el caso. Es coherente con «sin escribir», que se refiere al caso, y con D7.
- [x] **3 (candado).** R44 y R45; `threading.Lock` en todo `_run`, incluido `_connection()` (`design.md:326-345`). Coincide con el código actual (`repository.py:134-154`: `_connection` solo se llama desde `_run` y no hay reentrada). Tests T70 y T71. El orquestador queda solo documentado (`design.md:352-355`, `558-559`; entrada `later` de `feature_list.json`) y no hay ninguna R ni task sobre él.
- [x] **4 (huérfanos, C + A).**
  - R46 (`authorize(close)` → `200`) y R47 (`close` → `closed`, con `closed_by` igual a quien cierra y conservando `advisor_id`/`assigned_at`; es la duda 3 de la #17, que se deriva de `CaseCloseRequest`).
  - R48 (`reply`/`assign` → `403`). R7 y R15 se han reescrito para excluir al huérfano.
  - El arranque registra el recuento sin ids (R49-R52). La #14 no edita `contracts/` (`design.md:12-13`).
  - La tabla §3.2 (paso 4b) reproduce la precedencia de H1 «después»: los escalones 1-3 se aplican a todos y el 4.º se salta solo para `close`/`authorize(close)` sobre un huérfano.

### Consumo del contrato
- [x] `CONTRATOS.md` actual: `authorize` (401/422/403/404/409/500, `allowed` = `true`), la fila común `403`, las filas `403` de reply, close y assign, la `409` de reply y S11/S12 (#13). R22 → `500 internal_error` está en la tabla de `authorize`.
- [x] S12 «después» de la #17 (H1): la definición de huérfano, el cierre por cualquier asesor registrado, la prohibición de reply/assign, la salvedad en la precedencia y el procedimiento de retirada con el recuento «sin sus ids» se corresponden con R46-R50. La #17 delega en la #14 el nombre, el nivel y el caso 0 del log (duda 4), y R49/R50 lo fijan. Como #17 está `spec_ready`, la parada con `blocked` si S12 no lo recoge está en `design.md:18-21` y `tasks.md:3-6`.
- [x] Alineación con §9 de la #13: D5 (`design.md:533-538`), la nota de alineación (§8.1), el flujo §4.2, R26, R29/R30/T44 y T41 (renombrado). T33/T35/T46 citan R26 de forma coherente. D1-D4 y D6 no tienen desalineación.

### Coherencia con otras features
- [x] #10 (`done`): `make_env(advisors)` existe. `test_startup.py` solo gana tests. Los niveles de R49/R50 son coherentes con S6 de la #10.
- [x] #11: tabla y método distintos. El conteo de `CREATE TABLE` parte de 3. La diferencia de D8 frente a S2 de la #11 está declarada.
- [x] #12: T15/T16 de `test_timeout_races.py` solo ganan `env.settings` y dan el mismo resultado. `HookRepository` hereda los métodos nuevos. D1 y D2 se resuelven aquí y los riesgos (d) y (e) siguen abiertos. Lo que debe reflejar la #12 está en `design.md:608-614`. Nota: T62 usa `make_env(repo=...)`, que llega con la #12. Es coherente con el orden fijado, pero si la #14 se implementara antes que la #12, T62 y T7b no tendrían base.
- [x] #16 (solo señalar): `design.md:615-623` señala `CaseClosed` en lugar de `AdvisorForbidden`, la ausencia de `advisor_forbidden` con un `409`, `/cerrar` sobre huérfanos, el candado del orquestador y el cambio 3 pendiente.

### EARS, verificabilidad y trazabilidad
- [x] R37-R53 usan uno de los 5 patrones, con un solo `DEBE`/`NO DEBE`, el servicio indicado y sin verbos blandos. R38 y R47 encadenan acciones bajo un único `DEBE`, el mismo estilo aceptado en la primera vuelta.
- [x] Las R forman partición sin contradicciones: R7/R46/R48 en `authorize` sobre `assigned` a otro; R15/R47 en `close`; R12/R48 en `assign` (los dos dan `403`); R13/R40 (los dos dan `200` sin escribir).
- [x] Cada R tiene al menos un test nombrado (tabla `tasks.md:121-140`): R37 T62/T67/T68 · R38 T62/T47 · R39 T63 · R40 T64 · R41 T24/T60/T65/T67/T68 · R42 T66 · R43 T67/T68 · R44 T70 · R45 T71 · R46 T59 · R47 T60/T8 · R48 T61 · R49 T72 · R50 T72 · R51 T73 · R52 T74 · R53 T75. La cobertura de R1-R36 es la de la primera vuelta.
- [x] Ids estables: R1-R36 sin renumerar (R7, R15, R26, R29 y R30 se han reescrito en su sitio); R37-R53 y T54-T75 van al final; T8 se conserva como «sin cambios».
- [ ] **Tasks en orden** (cambio 1).
- [x] REVISAR solo en lo pendiente: D7, D8, D9, D12 y D13 (`design.md:575-585`). §8.4 recoge además el cierre que gana a la asignación con el SQL decidido, los riesgos (d)/(e) de la #12 y la feature del candado del orquestador. Las decisiones de la #13 y las 1-4 figuran como «Decidido por el humano».
- [x] Nada peligroso: no borra datos, no usa red en los tests y no toca nada fuera del repo.

### Cambios requeridos
1. **Orden de ejecución de las tasks (bloqueante).** `tasks.md:83-86` («Verificación», T52-T53) está antes de `tasks.md:88-117` (T54-T75). Además, T3 (`tasks.md:17`) usa `can_act_on_case`/`is_orphan_case` de T54, y T4/T5 (`tasks.md:18-19`) usan `assign_if_unassigned`/`close_if_not_closed` de T55. Un implementer que siga el documento ejecutaría T52 (todo verde y diff final) antes de escribir T54-T75. Hay que corregirlo sin renumerar:
   - mover el bloque «## Verificación» (T52, T53) al final del archivo, antes de la tabla de trazabilidad;
   - añadir en la cabecera (`tasks.md:7-11`) una línea con el orden de ejecución, p. ej. «T1, T2, T54, T55, T56, T3, T4, T5, T57, T6, T58, T7-T10, T7b, T11-T32, T59-T74, T33-T51, T75, T52, T53»;
   - o reordenar las líneas de las tasks en ese orden, sin cambiar los ids.
2. **Etiqueta de T69 (menor).** `tasks.md:108` y la fila R43 de `tasks.md:129` atribuyen T69 (`count_assigned_by_advisor`) a R43, pero R43 (`requirements.md:303-307`) solo trata las escrituras condicionales de R37 y R41. Hay que dejar T69 en «Cubre: R49» y quitarlo de la fila R43. Otra opción es extender R43 para incluir el recuento (cambia el texto de R43, que es nueva en esta vuelta).
3. **Vocabulario del caso huérfano (menor).** `requirements.md:33-34` presenta «(también si es nulo)» como «Decidido por el humano …, regla publicada por la #17». El texto H1 de la #17 no habla del `advisor_id` nulo; es una derivación del spec_author (`design.md:162-164`). Hay que redactarlo así: «Decidido por el humano (2026-10-31), regla publicada por la #17; el `advisor_id` nulo se incluye por derivación (`design.md` §3.1)». De esto depende que T8 no cambie.

### Decisiones del humano abiertas (no bloquean la aprobación del spec)
1. **D7.** Solo los `403` cuentan como denegación en handover. Incluye el `403` por carrera perdida (R38).
2. **D8.** Si falla guardar la denegación, `500`. Es la política contraria a S2 de la #11.
3. **D9.** Con un caso no vinculado, solo queda la línea de log en el orquestador.
4. **D12.** El recuento se hace en el `lifespan` y no en `create_app`.
5. **D13.** Si el recuento falla, aviso y el servicio arranca igual.
6. **Cierre contra asignación con el SQL decidido** (`design.md:590-597`, T65). En esa ventana, A puede cerrar un caso ya `assigned` a B. Opciones: aceptarlo, o pedir la condición más estrecha (una R y un test nuevos).
7. **Riesgos (d) y (e) de la #12.** Decidir si van en la #12 o en una feature propia.
8. **Candado del `PostgresRepository` del orquestador antes de la #16.** Decidir en qué feature va.

### Para el leader (fuera del spec, no bloquea)
- La `description` de la #14 en `feature_list.json` todavía dice «PENDIENTE antes de implementar: alinear el spec con C5». Ya está alineado.
- El acceptance de la #14 dice «un caso `assigned` solo lo cierra el asesor asignado» y no recoge las decisiones 1-4. Conviene añadir los criterios «Decidido por el humano (2026-10-31)» de C5, la carrera, el candado y los huérfanos (salvedad del cierre), para que el acceptance no contradiga R46/R47.

## Tercera vuelta (2026-10-31)

**Veredicto:** SPEC_APPROVED

- [x] Cambios de la segunda vuelta: (1) el orden de ejecución está en la cabecera (`tasks.md:9-12`) y la verificación T52-T53 va al final (`tasks.md:125-128`). T54-T58 se ejecutan antes de T3-T6 y T76-T79 están incluidas. (2) T69 → R49; la fila R43 ya no la cita. (3) El vocabulario del huérfano cita el texto real de S12, que ya incluye el `advisor_id` nulo (`CONTRATOS.md:436`).
- [x] Decisiones del humano aplicadas sin invenciones:
  - C5: R26, R29, R30 y R53, con T41 y T75.
  - Asignación y cierre condicionales con `RETURNING`: R37-R43, R54 y R55. El cierre exige en el mismo `UPDATE` el estado o el asesor permitido (`design.md:251`), y si pierde contra una asignación ajena responde `403` y registra la denegación (T65, T76-T79).
  - Solo los `403` son denegación (R19, R20); `500` si falla guardarla (R22); solo log si no hay contacto vinculado (R30).
  - `lifespan` con `WARNING` y arranque igual: R49-R52.
  - `threading.Lock` en `_run`: R44, R45.
  - Huérfanos, incluido el `advisor_id` nulo, cerrables y sin reply/assign: R46-R48, R54.
  - La #18 solo se referencia, sin R.
- [x] El spec consume exactamente S12 actual (#13 + #17): precedencia, salvedad del huérfano en el 4.º escalón, `close` sobre `closed` con `200` por S8, `409` en reply, `502` con fallo cerrado y recuento sin ids. Además, no edita `contracts/`.
- [x] EARS con un solo `DEBE`. Todas las R de R1-R55 tienen test y la tabla de trazabilidad está completa. Las 16 líneas del acceptance están cubiertas.
- Observaciones no bloqueantes: la `description` de la #14 en `feature_list.json` tiene un espacio doble («la #10.  decisiones»). Los riesgos (d) y (e) de la #12 siguen abiertos fuera de esta feature (§8.4).
