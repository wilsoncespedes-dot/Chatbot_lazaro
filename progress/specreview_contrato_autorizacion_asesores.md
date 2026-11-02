# Spec review — contrato_autorizacion_asesores (feature #13)

**Veredicto:** SPEC_CHANGES_REQUESTED

Revisado el 2026-10-31 contra `specs/contrato_autorizacion_asesores/{requirements,design,tasks}.md`,
el acceptance de la #13, los criterios «Decidido por el humano (2026-10-31)» de la #14 y la #16,
`progress/propuesta_etapa2.md` §4 y §6, `contracts/CONTRATOS.md` y `contracts/tests/*` actuales,
y el modelo de la #9 (`specs/contrato_asignar_caso/`, `progress/specreview_contrato_asignar_caso.md`).
La feature sigue `blocked` por decisión del humano; este informe no cambia su estado.
Línea base: `.venv/Scripts/python.exe -m pytest contracts` en verde; `contracts/` sin cambios en el árbol.

Resumen: el spec es fiel al acceptance y a las decisiones del humano, y la trazabilidad R→test
está completa. Se rechaza porque deja **fuera del contrato** comportamientos que se pueden observar
por HTTP en las rutas que toca (precedencia de errores, `reply` sobre un caso `closed`, `close` sobre
`closed` con otro asesor). Si se dejan para la #14, la #14 tendría que definir contrato fuera de
una feature de contrato (principio 2 de `docs/architecture.md`). Hacen falta decisiones del humano
(ver la última sección) y unas pocas R nuevas.

## Cobertura del acceptance
- [x] A1 (ruta `POST /cases/{id}/authorize`: expone handover, llama orchestrator, `CaseAuthorizeRequest {advisor_id, action: reply|close}`, `200 CaseAuthorizeResponse {allowed: true, case_id}`, errores 401/422/403/404/409/500) → R1-R10, R27, R28, R33.
- [x] A2 (`403 forbidden` en `## Reglas comunes` y en reply, close y assign) → R14-R17.
- [x] A3 (S12 con las reglas de la #14 y la limitación de identidad por HTTP) → R19-R26. La limitación queda en S12 (R25, T28) como pidió el humano.
- [x] A4 (modelos exportados, ejemplos, rechazo sin `advisor_id`, `action` fuera de la lista, `allowed` != `true`) → R29 (T11, T32), R31 (T35), R34 (T37), R37, R38-R40.
- [x] A5 (aditivo; filas nuevas como único cambio en secciones publicadas) → R18, R41, R42. Design §1 confirma 0 líneas eliminadas en `CONTRATOS.md`.

## Fidelidad a las decisiones del humano (#14 y propuesta §6)
- [x] Solo son asesores los de `ADVISOR_CHAT_IDS` → R19.
- [x] `open`/`timed_out`: responde cualquier asesor registrado y la 1.ª respuesta asigna; `assigned`: solo el asignado → R20.
- [x] Cerrar sin asignar: cualquier registrado; `assigned`: solo el asignado → R21.
- [x] Sin reasignación ni supervisor → R22.
- [x] Fallo cerrado con `502 upstream_error` sin enviar → R23.
- [x] close y assign aplican las mismas reglas y responden 403 sin modificar el caso → R24.
- [x] Limitación de identidad por HTTP con `SERVICE_TOKEN` → R25. (El texto de design §4.4 añade que la identidad por persona llega con el webhook validado o con el panel; no lo exige ninguna R ni lo comprueba ningún test. Es fiel a la #14, no bloquea.)
- [x] Nada inventado: R26 se deriva de «close y assign aplican las mismas reglas» (#14) y está marcado para confirmar (design §7 duda 4).

## EARS estricto
- [x] Un solo `DEBE`/`NO DEBE` por R, sin verbos blandos.
- [x] R1, R27, R28, R33, R37-R39, R41: ubicuo; R29-R32, R34-R36: no deseado; R18, R42: evento.
- [x] R2-R17 y R19-R26 usan «En la sección/tabla …, `CONTRATOS.md` DEBE …» o «La fila `S12` … DEBE …», la forma ya aceptada en la #1 y la #9.
- Nota menor (no bloquea): R40 usa «DEBEN» (plural), igual que R25 de la #9.

## Verificable (cada R con test nombrado)
- [x] R1, R2, R4, R5, R7, R8, R9 → parametrizados ampliados (T8); R3 → T13; R6 → T14; R10 → T15; R11 → T16; R12 → T17; R13 → T18.
- [x] R14 → T9 + T19; R15-R17 → T20; R18 → T21 + T39.
- [x] R19-R26 → T22-T29. He comprobado que cada fragmento que buscan está en el texto de design §4.4 (p. ej. «otro asesor recibe `403`», «sin enviar nada al cliente», «suplante»).
- [x] R27 → T30; R28 → T31, T34; R29/R30 → T11 + T32/T33; R31 → T35; R32, R35, R36 → T11; R33 → T36; R34 → T37; R37 → T12 + T38; R38-R40 → T10; R41/R42 → batería previa + diff (T39, T40), como R26/R27 de la #9.
- [x] Los fragmentos de las filas nuevas (`| 403 | forbidden |`) encajan con la regex de `_error_rows` (`contracts/tests/test_contratos_doc.py:92`, un espacio a cada lado) y la fila común con la de la línea 200 (`\s+`).

## Diseño
- [x] Solo `contracts/`; sin dependencias ni variables nuevas; firmas explícitas (design §3).
- [x] 5 alternativas descartadas con motivo (design §6).
- [x] Sección «Supuestos a confirmar» con S12 y lista de dudas (design §7).
- [ ] **Faltan en el contrato comportamientos observables por HTTP** (ver cambios 1-3).

## Tasks
- [x] T1-T40 en `[ ]`, en orden (modelos → ejemplos → documento → tests ampliados → tests nuevos → verificación), cada una con sus `R<n>`; entre todas cubren R1-R42.
- [ ] T21 congela las tablas de reply/close/assign con igualdad exacta (ver cambio 4).

## Carácter aditivo y tests existentes (punto 5 del encargo)
- [x] Ningún test de `services/`, `eval/` ni `scripts/` lee `CONTRATOS.md` (grep de `CONTRATOS.md` y `Llama:` en `*.py`: solo `contracts/tests/test_contratos_doc.py`).
- [x] Las filas nuevas no rompen nada: `test_errors_table_has_route_specific_rows` (l.168) y `test_common_rules_document_error_shape_and_codes` (l.201) comprueban `<=`, así que filas de más no fallan; las entradas existentes de `OWN_ERRORS` no se editan.
- [x] `test_assumptions_mention_s1_to_s10` y `test_assumptions_include_assign_idempotency` siguen verdes: S11 no se edita.
- [x] Única edición de texto existente: la 2.ª línea de la docstring de `contracts/lazaro_contracts/cases.py` (`y /cases/{id}/assign."""`). Ningún test la lee.
- Nota: R26 cambia de hecho lo que S11 promete a un asesor distinto del asignado (antes `200`, ahora `403`), aunque no se edite S11. Es una consecuencia directa de la decisión del humano (#14: «close y assign aplican las mismas reglas»), no un debilitamiento de tests. Debe confirmarlo el humano (punto d).

## Secuencia con la #15
- [x] La #13 no toca la línea `- **Llama:**` de ninguna ruta ni reserva S13 (design §1, T6).
- [x] La #15 solo añade entradas tras las de la #13 en `ROUTES`, `SUCCESS_CODES`, `OWN_ERRORS`, `EXAMPLES`, `MODEL_NAMES`, `BASE_EXAMPLES` e `IDENTIFIER_FIELDS`; no toca el `expected` de la l.189 ni las tablas de errores de reply/close/assign, así que T21 de la #13 sigue verde después de la #15.
- La #15 vuelve a editar la docstring de módulo de `cases.py` que reescribe la #13. Es documentación, no rompe nada; está anotado en la revisión de la #15.

## Nada peligroso
- [x] No borra datos, no usa la red, no toca archivos fuera del repo.

## Evaluación de las dudas de design §7 (punto 3 del encargo)

| Duda | Recomendación del leader | Evaluación | ¿Debe ir en la #13? |
|---|---|---|---|
| (a) Precedencia | 403 asesor no registrado → 404 → 409 → 403 por caso de otro | Coherente: no revela si un caso existe a quien no es asesor y deja el `409` para asesores válidos. | **Sí.** Es lo que ve quien llama a `authorize`, `close` y `assign`. Si solo lo fija la #14, el contrato queda incompleto. |
| (b) close sobre `closed` | La ruta close mantiene S8 (`200`); `authorize` con `action=close` sobre `closed` da `409` | Coherente con S8 y con el acceptance (409 en `authorize`). Con la precedencia (a), en close el escalón 409 pasa a ser «`200` S8», así que **otro asesor registrado que cierra un caso `closed` que tenía asignado otro recibe `200`**, no `403`. Es inofensivo (no cambia nada), pero hay que decirlo. | **Sí**, una frase en S12 (y que la #14 lo pruebe). |
| (c) Fallo cerrado | Reutiliza la fila `502 upstream_error` de reply, explicado en S12 | Coherente con «filas nuevas solo 403» del acceptance. Hoy esa fila (`CONTRATOS.md` l.234) y la común (l.47) dicen «la llamada a `POST /send` del gateway falla», que deja de ser la única causa. R23 no cita `POST /cases/{id}/reply` ni dice que se reutiliza esa fila. | **Sí**: ampliar R23/T26 para que S12 diga que es el `502 upstream_error` de `POST /cases/{id}/reply`. |
| (d) assign de un caso `assigned` | Otro asesor 403, el mismo 200 (S11) | Coherente; ya está en R26/T29. | Ya está; falta solo que el humano lo confirme. |

Hueco que no figura en §7 y que hay que añadir:

- (e) **`POST /cases/{id}/reply` sobre un caso `closed`.** Con la #14 el orquestador llama a
  `authorize(action=reply)` y recibe `409 case_closed` (R13), pero la tabla de errores de reply
  (`CONTRATOS.md` l.229-235) no tiene `409` y la #13 no dice qué responde reply en ese caso. Hoy
  `reply_to_case` (`services/orchestrator/orchestrator/domain.py:285-305`) envía igualmente y solo
  registra `assign_failed`, así que el comportamiento cambia sí o sí. Lo mismo vale para
  `/responder` de la #16. Hace falta decidirlo y documentarlo en el contrato.

## Cambios requeridos
1. **design §7 / requirements:** cuando el humano decida (a), añadir una R (fila S12) con la
   precedencia de errores de `authorize`, `close` y `assign`, y su test en `test_contratos_doc.py`
   (p. ej. `test_assumptions_s12_error_precedence`). Quitar la duda 1 de §7.
2. **(b)** Añadir una R (fila S12) que diga que `POST /cases/{id}/close` sobre un caso `closed`
   sigue S8 (`200`) para cualquier asesor registrado, mientras que `authorize` con `action` =
   `close` sobre `closed` responde `409`. Añadir su test. Quitar la duda 2 de §7.
3. **(c) y (e)** Ampliar R23 (y T26) para que S12 diga que el fallo cerrado es el
   `502 upstream_error` de `POST /cases/{id}/reply`. Añadir a §7 la duda (e) y, cuando el humano
   decida, una R con lo que responde reply (y por tanto `/responder`) cuando `authorize` da `409`:
   - `409 case_closed`: fila nueva en la tabla de reply y `/cases/{id}/reply` en la «Dónde» de la
     fila común 409. Esto último edita una fila publicada, contra el precedente de R13 de la #9,
     así que necesita el permiso expreso del humano.
   - `403 forbidden`: sin filas nuevas, pero el 403 deja de significar solo «no autorizado».
4. **T21** (`test_existing_case_routes_keep_their_error_rows`): cambiar la igualdad exacta por
   «filas previas ∪ {403} ⊆ filas». R18 solo prohíbe quitar o modificar filas. Con igualdad
   exacta, cualquier fila que añada después la #14 o la #16 (p. ej. la de la opción
   `409` de (e)) obligaría a editar un test de la #13, y eso deja de ser aditivo.
5. Al cerrar las dudas, actualizar `tasks.md` (tests nuevos con su `R<n>`) y la lista «Dudas que
   este spec NO resuelve» de design §7.

## Decisiones para el humano
1. **(a) Precedencia de errores:** ¿apruebas 403 (asesor no registrado) → 404 → 409 → 403 (caso
   asignado a otro) para `authorize`, `close` y `assign`, y que vaya en S12?
2. **(b) close sobre `closed`:** ¿confirmas que close mantiene S8 (`200`) incluso para un asesor
   registrado distinto del que lo tenía asignado, y que `authorize(close)` sobre `closed` da `409`?
3. **(c) Fallo cerrado:** ¿basta con reutilizar la fila `502 upstream_error` de reply y explicarlo
   en S12, o quieres editar su texto «Cuándo»? (Editarlo cambia una línea publicada.)
4. **(d) assign de un caso `assigned` por otro asesor → `403`:** confirma que aceptas este cambio
   de lo que ve quien llama frente a S11 (antes `200`).
5. **(e) reply sobre un caso `closed`:** ¿`409 case_closed` (fila nueva en reply y, si lo
   permites, editar la «Dónde» de la fila común 409) o `403 forbidden` (sin filas nuevas)?
   Hoy el orquestador envía igualmente; con la #14 tiene que elegir una de las dos.

## Segunda vuelta (2026-10-31)

**Veredicto:** SPEC_CHANGES_REQUESTED

### Cambios requeridos de la primera vuelta
- [x] **Cambio 1 (precedencia).** R43 + T41; duda quitada de §7 y pasada a C1 (REVISAR).
- [x] **Cambio 2 (close sobre `closed`).** R44 + T42; C2 (REVISAR).
- [x] **Cambio 3 (fallo cerrado y reply sobre `closed`).** R45 + T43 (fila `502 upstream_error` ya publicada de reply, sin editar su «Cuándo»); duda (e) resuelta con la recomendación del leader en R46 + T44 (`403 forbidden`, sin filas nuevas); la alternativa `409 case_closed` está en §6.
- [x] **Cambio 4 (T21).** Inclusión (`previas | {403} <= filas`), explicado en design §5 l.216-218.
- [x] **Cambio 5.** `tasks.md` (T7 cubre R43-R46; T41-T44; T40 mapea R1-R46) y §7 («Dudas que este spec NO resuelve») actualizados.

### Decisiones del humano no tomadas en silencio
- [x] C1, C2, C3 y C5 marcadas **REVISAR (recomendación del leader, pendiente del humano)** (design §7, l.258-271), las cuatro que pidió el leader. R26/(d) sigue como duda abierta (l.275-278).

### Problema nuevo (bloquea)
- [ ] **R43 contradice a R44 y a la #14.** R43 (`requirements.md` l.255-260), el texto de S12 (design §4.4) y T41 (`tasks.md` l.59) fijan para `POST /cases/{id}/close` el escalón «`409` por caso `closed`». Pero R44 dice que `close` sobre `closed` responde `200` (S8), la tabla de errores de close no tiene `409`, y la #14 (`specs/autorizacion_asesores/design.md` §3.2, tabla l.120-126, paso 3: close → `200` sin cambios; §8 D1: «`closed` `409` (reply/assign)») lo deja claro. Tal como está, S12 publicaría que close responde `409` en un caso y `200` en el mismo caso dos frases después. Lo dice ya C2 en §7 («en close el escalón `409` es el `200` de S8»), pero no llega ni a la R, ni al texto del contrato, ni al test.

### Nada inventado, sin otros conflictos
- [x] R43-R46 recogen exactamente las recomendaciones del leader y coinciden con D1-D3 y D5 de la #14.
- [x] Con la #15: la #13 sigue sin tocar líneas `- **Llama:**` ni reservar S13; T21 por inclusión deja a la #15 (y a la #16) añadir filas sin editar tests de la #13.
- Nota (no bloquea, para el humano): la #14 (§8 D6) hace que en `POST /cases/{id}/reply` el orquestador autorice antes de buscar el vínculo caso-contacto (un no asesor recibe `403` aunque el caso no exista). Es precedencia observable en reply y S12 no la recoge (R43 solo habla de authorize, close y assign). Conviene añadirla a S12 en el mismo arreglo.

### EARS, trazabilidad y tasks
- [x] R43-R46 con un solo `DEBE`, forma «La fila `S12` … DEBE …» ya aceptada; cada una con su test (T41-T44). T1-T44 en `[ ]`, en orden.

### Cambios requeridos
1. **Reescribir R43, la frase de precedencia de S12 (design §4.4) y T41** para que el escalón «caso `closed`» sea `409` en `authorize` y `assign` y el `200` de S8 en `close` (R44). Por ejemplo: «`403` (asesor no registrado) → `404` (caso inexistente) → `409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios por S8) → `403` (caso asignado a otro asesor)», y que T41 busque ese fragmento.
2. (Recomendado, mismo arreglo) Añadir a S12 la precedencia de `POST /cases/{id}/reply` de la #14 D6 (autorizar antes de comprobar el caso), marcada REVISAR, con su R y su test; o dejar escrito en §7 que queda fuera y por qué.

### Decisiones para el humano (siguen abiertas)
1. C1 — precedencia `403` no registrado → `404` → `409`/`200` S8 → `403` asignado a otro.
2. C2 — `close` sobre `closed` mantiene S8 (`200`) para cualquier asesor registrado; `authorize(close)` sobre `closed` → `409`.
3. C3 — fallo cerrado con la fila `502 upstream_error` ya publicada de reply, sin editar su texto.
4. C5 — reply sobre `closed` → `403 forbidden` (alternativa: `409 case_closed` editando la fila común).
5. (d) — `assign` de un caso `assigned` por otro asesor → `403` (estrecha S11).

## Tercera vuelta (2026-10-31)

**Veredicto:** SPEC_APPROVED (solo quedan decisiones del humano)

Revisado contra `specs/contrato_autorizacion_asesores/{requirements,design,tasks}.md` (versión
posterior a la segunda vuelta), `specs/autorizacion_asesores/design.md` §3.2 y §8 (solo lectura),
`specs/contrato_conversacion_caso/` y `progress/specreview_conversacion_cliente_asesor.md` (cambio 3).
Línea base: `contracts/` sin cambios en el árbol; `.venv/Scripts/python.exe -m pytest contracts` en verde.

### Cambios requeridos de la segunda vuelta
- [x] **Cambio 1 (R43 contra R44).** R43 (`requirements.md` l.255-260) dice ahora «caso `closed`
  (`409` en `authorize` y `assign`; `200` sin cambios por S8 en `close`, R44)». La frase de S12
  (design §4.4, l.176) dice «`409` (caso `closed`; en `POST /cases/{id}/close`, `200` sin cambios
  por S8)», y T41 (`tasks.md` l.59) busca exactamente ese fragmento (comprobado carácter a carácter
  contra §4.4). Sin contradicción:
  - con R44 (l.262-265) y T42: close sobre `closed` → `200` para cualquier asesor registrado;
    `authorize(close)` sobre `closed` → `409`;
  - con la tabla de errores de close (`CONTRATOS.md`, sin `409`): la #13 no añade `409` a close;
  - con la #14: §3.2 (tabla l.137-143, paso 3: authorize `409`, assign `409`, close `200` S8) y §8
    D1/D2 (l.347-348) dicen lo mismo. Como el paso 3 va antes que el 4, otro asesor que cierra un
    caso `closed` recibe `200`, que es lo que dice R44 («cualquier asesor registrado»).
  - C1 y C2 de design §7 (l.268, l.270) repiten la misma regla.
- [x] **Cambio 2 (precedencia de reply).** R47 (l.276-280) + T45 (l.63) + C6 (design §7 l.269),
  marcada **REVISAR (recomendación del leader, pendiente del humano)**. Texto en S12 (§4.4):
  «En `POST /cases/{id}/reply` el orquestador autoriza antes de comprobar si el caso existe: un
  `advisor_id` no registrado recibe `403` …». Coincide con D6 de la #14 (l.361: autoriza antes de
  buscar el vínculo caso-contacto; un caso desconocido para un asesor registrado sigue en `404`,
  R35 de la #7). Los dos fragmentos de T45 están en §4.4.

### Checklist
- [x] **EARS:** R43-R47 con un solo `DEBE`, forma «La fila `S12` … DEBE …» ya aceptada. R1-R42 sin cambios.
- [x] **Trazabilidad:** R1-R42 como en la primera vuelta; R43→T41, R44→T42, R45→T43, R46→T44,
  R47→T45. Todos los fragmentos de T41-T45 aparecen en el texto de §4.4. T7 cubre R19-R26 y R43-R47.
- [x] **T40** documenta R1-R47 (R43-R47 → T41-T45).
- [x] **Tasks:** T1-T45 en `[ ]`; T41-T45 con ids nuevos sin renumerar T30-T40 (explicado en l.57).
- [x] **Nada inventado:** C1, C2, C3, C5 y C6 siguen marcadas REVISAR (design §7 l.258-272) y
  R26/(d) sigue como duda abierta (l.276-279). La feature sigue `blocked` hasta que las confirme el humano (l.280-281).
- [x] **Aditivo sobre `CONTRATOS.md`:** solo filas nuevas (`403` ×4, `S12`) y la sección nueva;
  0 líneas eliminadas (design §1 l.19-22, T39). No se tocan líneas `- **Llama:**` existentes (T6)
  ni el «Cuándo» de las filas `502` (R45, C3). S12 no tiene `|` dentro del texto, así que
  `_assumption_row` la puede leer.
- [x] **Coherencia con la #15:** la #15 solo depende de que exista `S12` (su T32 busca que la fila no esté
  vacía) y no busca `authorize` ni `forbidden` (su design l.21-22). Ningún cambio de esta vuelta la afecta.
- [x] **Decisiones del humano de `propuesta_etapa2.md` §6:** respetadas (sin cambios desde la primera vuelta).
- [x] **Nada peligroso.**

### Notas menores (no bloquean)
1. `requirements.md` l.251 y `design.md` l.262 dicen «D1-D5» de la #14, pero R47/C6 corresponde a D6.
   Conviene poner «D1-D6» al tocar el archivo.

### Línea `Llama` de `authorize` y `/cerrar` de la #16 (cambio 3 de `specreview_conversacion_cliente_asesor.md`)
- La #13 no la menciona. **Debe mencionarla en design §7, «Dudas que este spec NO resuelve», como duda
  abierta** (recomendado, no bloquea, porque es una decisión del humano y no de la #13): si el humano
  elige la opción (a) de D4 de la #16, la línea de design §4.1 l.119 (`- **Llama:** orchestrator (antes
  de reenviar … con `POST /cases/{id}/reply`)`) tendría que nombrar también el comando `/cerrar`. Conviene
  decidirlo **antes** de implementar la #13: después sería editar una línea `Llama` ya publicada.
  En cualquiera de las opciones R3 y T13 siguen valiendo (solo exigen `orchestrator` en esa línea);
  solo cambiaría el paréntesis de §4.1.

### Cambios requeridos
Ninguno que bloquee. Recomendados: nota menor 1 y la mención de la duda `/cerrar` en design §7.

### Decisiones del humano (siguen abiertas)
1. C1: precedencia `403` (no registrado) → `404` → `409` (`200` S8 en close) → `403` (asignado a otro)
   en authorize, close y assign.
2. C2: `close` sobre `closed` mantiene S8 (`200`) para cualquier asesor registrado; `authorize(close)`
   sobre `closed` → `409`.
3. C3: fallo cerrado con la fila `502 upstream_error` ya publicada de reply, sin editar su texto.
4. C5: reply sobre `closed` → `403 forbidden` (alternativa: `409 case_closed` editando la fila común).
5. C6: en reply el orquestador autoriza antes de comprobar el caso (un no registrado recibe `403` aunque
   el caso no exista).
6. (d) / R26: `assign` de un caso `assigned` por otro asesor → `403` (estrecha S11).
7. D4 de la #16 (opción a/b/c): si se elige (a), ampliar en la #13, antes de implementarla, la línea
   `- **Llama:**` de `authorize` para incluir el comando `/cerrar`.
