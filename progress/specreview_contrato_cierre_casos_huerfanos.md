# Spec review — feature #17 `contrato_cierre_casos_huerfanos`

**Veredicto:** SPEC_CHANGES_REQUESTED

Modo supervisado: esta revisión sirve de apoyo al humano, que sigue siendo quien aprueba el spec.
El spec es sólido y fiel a la decisión. Se rechaza por **un hueco concreto**: falta declarar una
duda abierta de la que depende la #14 (cambio 1). El cambio 2 es menor.

## Verificaciones hechas (con evidencia)

- **Línea «antes» de H1**: `design.md` l.35, extraída y comparada byte a byte (`cmp`) con la fila
  `| S12 |` actual de `contracts/CONTRATOS.md` (l.436): **idéntica**. El archivo usa LF (0 CR),
  igual que dice `design.md` l.38.
- **«antes» → «después»**: `difflib` carácter a carácter: solo hay **3 inserciones y ningún
  borrado ni sustitución**, como afirma `design.md` l.44-57. Número de `|` igual en las dos (4),
  así que `_assumption_row("S12")` (`test_contratos_doc.py` l.236-239) sigue leyendo la fila entera.
- **Tests existentes con el texto «después»**: copié `contracts/` al scratchpad, sustituí la fila
  S12 por la «después» y ejecuté `contracts/tests/test_contratos_doc.py`: **113 passed**. La batería
  completa de `contracts/tests` sobre la copia: 373 passed y 1 failed
  (`test_packaging.py::test_dev_requirements_include_contracts`), que es un artefacto de la copia
  (busca `requirements-dev.txt` en la raíz del repo; en el repo real pasa) y no tiene que ver con S12.
  Revisé a mano los fragmentos de R21 (`test_assumptions_s12_close_rules`, l.464-472) y R43
  (`test_assumptions_s12_error_precedence`, l.516-530): siguen literales y contiguos. La tabla de
  `design.md` §5 (l.158-177) es correcta: ningún test existente cambia.
- **Fragmentos de los tests nuevos** (T3-T13, `tasks.md` l.24-34): los 15 fragmentos «…» están
  literalmente en la fila «después».
- **Otras líneas publicadas**: busqué «otro asesor», «solo lo cierra», «asesor asignado» y las
  reglas de cierre en `CONTRATOS.md`, `lazaro_contracts/*.py` y `examples/`. Solo aparecen en S11
  (no se edita y no habla de cerrar), en la prosa de `authorize` (l.386-389, remite a S12) y en la
  fila `403 forbidden` de close (l.305, remite a S12). Ninguna contradice H1. Estoy de acuerdo con
  la lista de «Fuera de alcance» (`design.md` l.83-87).

## Checklist

- [x] **Fidelidad a la decisión del humano (2026-10-31).** Huérfano = `assigned` con `advisor_id`
  fuera de `ADVISOR_CHAT_IDS` (R1). Cualquier asesor registrado lo cierra por `close` (R2) y por
  `authorize(close)` → `200 allowed=true` (R3). No es reasignar (R4). `reply`/`authorize(reply)`/
  `assign` de otro asesor → `403 forbidden` (R6, R7). Procedimiento A (R10, R11). La #14 no edita el
  contrato (`design.md` l.20-21).
- [x] **Sin invenciones.** El aviso al cliente, el `closed_by`, los detalles del log, el momento de la
  retirada, el reenvío a un retirado (Ley 1581) y la opción F están como dudas abiertas
  (`design.md` l.241-263) y no se escriben en S12.
- [ ] **Dudas abiertas completas.** Falta una (cambio 1).
- [x] **Excepción cerrada al principio aditivo.** Lista cerrada H1 (`design.md` l.23-31), una sola
  línea y antes/después literales. R12 (diff exacto), R13 (solo dos archivos), R14 (el test solo se
  amplía).
- [x] **Sin contradicción con C1/C2/C5/C6 de la #13 ni con su precedencia.** C1: los tres primeros
  escalones no cambian y el 4.º solo se salta para `close`/`authorize(close)` sobre un huérfano
  (R8, R9; `design.md` l.64-70). C2: un huérfano nunca está `closed` (l.71-73). C5: `reply` sobre
  `closed` no se toca, porque el huérfano es `assigned`. C6: `reply` sigue autorizando antes de buscar
  el caso, y el huérfano pasa por `authorize(reply)` → `403`.
- [x] **EARS.** 15 R y 15 `DEBE`/`NO DEBE`, uno por R, sin verbos blandos. R1-R11 usan el sujeto
  «La fila `S12` de `CONTRATOS.md`», el mismo estilo que la #13 aprobada (`specs/contrato_autorizacion_asesores/requirements.md` l.135-154).
- [x] **Verificable y trazabilidad.** R1-R11 → T3-T13 (un test con nombre por R, `design.md`
  l.106-118 y `tasks.md` l.45-61). R12-R14 → comprobaciones de diff contra una copia previa (T1,
  T14, T15), con la razón de no usar `git diff HEAD` explicada (`design.md` l.145-148; es correcta:
  `contracts/` tiene cambios de la #13 sin commit). R15 → T16.
- [x] **Tasks.** T1-T17 están todas en `[ ]` y en orden (copia → edición → tests → verificación →
  informe). Entre todas cubren R1-R15.
- [x] **Diseño.** Solo `contracts/`, sin dependencias ni variables de entorno nuevas. Tiene 6
  alternativas descartadas (§4). No contiene nada peligroso.
- [x] **Cobertura del acceptance.** Tabla `requirements.md` l.122-130: los 5 criterios cubiertos.

## Coherencia con `specs/autorizacion_asesores/` (#14) — discrepancias (no arregladas)

1. **`advisor_id` nulo.** La #14 define huérfano como `advisor_id` «no es asesor registrado
   (también si es nulo)» (`specs/autorizacion_asesores/requirements.md` l.33-35, `design.md`
   l.162-164). Lo declara como una derivación suya, no como decisión del humano. Y se apoya en ello:
   `specs/autorizacion_asesores/tasks.md` T8 deja sin cambios
   `test_close_marks_closed_and_records_advisor` **solo porque** un `assigned` sin `advisor_id` cuenta
   como huérfano. El S12 de la #17 dice «cuyo `advisor_id` **ya no** está en `ADVISOR_CHAT_IDS`». Leído
   al pie de la letra incluye `None`, pero «ya no» sugiere un asesor que antes estuvo en la lista.
   La #17 no lo menciona en ninguna parte → cambio 1.
2. **Referencias de línea caducadas.** `design.md` §6 (l.190, l.207, l.210, l.212) cita líneas de la
   #14 («l.13-19», «l.134-143», «l.152-156», «l.393-401»). Ya no coinciden: D11 está ahora en la
   l.561 y la tabla de pasos en las l.172-180. Además, §6 describe como pendiente lo que la #14 ya
   incorpora (D11 decidida, R46-R52 nuevas, paso 4b) → cambio 2.
3. Coinciden con la #17: `closed_by` = quien cierra (#14 R47 frente a la duda 3 de la #17). Log del
   recuento sin ids (#14 R49-R51 frente a R11 y la duda 4). El retirado recibe `403` en el paso 1
   (#14 l.181-182 frente a la #17 `design.md` l.65-67). `assign`/`authorize(reply)` sobre un
   huérfano → `403` (#14 R48 frente a R6/R7). El hecho de que la #14 conserve el `advisor_id`/
   `assigned_at` del retirado al cerrar (R47) es un detalle de implementación que S12 no contradice.

## Cambios requeridos

1. **`specs/contrato_cierre_casos_huerfanos/design.md` §7, tras l.263** (lista «Dudas que este spec NO
   resuelve»): añadir la duda 7, **«Caso `assigned` con `advisor_id` nulo»**. Debe decir que el
   humano no lo decidió. También, que la fila S12 no lo menciona y que, leída al pie de la letra
   (`None` no está en `ADVISOR_CHAT_IDS`), lo trata como huérfano. Por último, que la #14 lo
   incluye por derivación (su T8 depende de ello). No hace falta tocar la línea «después» de H1 ni
   ningún R.
2. **`specs/contrato_cierre_casos_huerfanos/design.md` §6 (l.187-225)**, menor: quitar los números
   de línea de la #14 (o citar por id: R7, R15, R46-R52, D11, §3.2 paso 4b). Así no quedan
   referencias caducadas mientras el otro spec_author edita ese spec.

## Decisiones del humano abiertas (no las resuelve este spec)

- Si un caso `assigned` con `advisor_id` nulo cuenta como huérfano (cambio 1).
- Reenvío de mensajes del cliente al Telegram de un asesor retirado mientras el huérfano no se
  cierra (Ley 1581; sería un cambio de S13/#15). `design.md` l.243-248.
- `closed_by` al cerrar un huérfano (derivado: quien cierra; lo confirma la #14). l.254-256.
- Detalles del recuento al arrancar (evento, nivel, si se registra con 0, si se repite). La #14
  propone R49-R51 con REVISAR D12/D13. l.257-259.
- Aviso al cliente o al asesor al cerrar un huérfano (A12 de la #16). l.260-261.
- Caso `assigned` de un asesor activo que nunca lo cierra (opción F). l.262-263.

## Segunda vuelta (2026-10-31)

**Veredicto:** SPEC_CHANGES_REQUESTED

Modo supervisado: esta revisión sirve de apoyo al humano, que sigue siendo quien aprueba el spec.
Los cambios 1 y 2 de la primera vuelta están bien resueltos en lo que importa: el texto de H1, R1,
T3, los tests y las referencias por id. Se rechaza por **un solo punto, menor y solo de redacción**
(cambio 3). `design.md` dice dos veces que el vocabulario «Caso huérfano» de la #14 trata el nulo
«por derivación». Ese vocabulario ya dice que lo decidió el humano. Es justo el tipo de
descripción caducada que el cambio 2 quería quitar. No afecta al contrato ni a los tests.

### Verificaciones hechas (con evidencia)

- **«Antes» = S12 actual**: extraje `design.md` l.35 y la fila `| S12 |` de `contracts/CONTRATOS.md`
  (l.436) y las comparé con `cmp`: **idénticas**. `CONTRATOS.md` tiene 0 CR (LF).
- **«Antes» → «después»**: con `difflib`, carácter a carácter, salen 3 operaciones `insert`, 0
  `delete` y 0 `replace`. Número de `|`: 4 y 4.
- **Tests existentes con el texto «después»**: copié `contracts/` (más `conftest.py` y `pytest.ini`)
  al scratchpad, sustituí la fila S12 por la «después» de `design.md` l.41 y ejecuté
  `contracts/tests/test_contratos_doc.py`: **113 passed**. Ningún test existente busca «huérfano».
- **Fragmentos de los tests nuevos**: los 14 fragmentos distintos de T3-T13 (`tasks.md` l.24-34)
  están literalmente en la línea «después». Eso incluye el de T3, «… cuyo `advisor_id` es nulo o ya
  no está en `ADVISOR_CHAT_IDS`».
- **Ids y secciones citados en `design.md` §6**: existen todos en `specs/autorizacion_asesores/`.
  - `requirements.md`: R4, R7, R11, R12, R14, R15 y R46-R52.
  - `design.md`: §3.1 (nota del nulo), §3.2 (pasos 4a y 4b, viñeta del retirado), §8.2 D11,
    y D12 y D13 en §8.3.
  - `tasks.md`: T5, T8, T14, T17, T23, T53 y T54.
  - Lo que se dice de cada uno es correcto. R7 y R15 están reescritos con la remisión a R46-R48.
    R47 usa `closed_by` = quien cierra. R49-R51 recogen el recuento sin ids, con [REVISAR: D12/D13].
  - En `specs/conversacion_cliente_asesor/design.md` existen la viñeta «Asesor retirado de
    `ADVISOR_CHAT_IDS` con un caso `assigned`» de §7 (l.426) y la fila «Duda abierta» de §11
    (l.517).
  - No queda ningún número de línea de otros specs. Solo queda «línea 436» de `CONTRATOS.md` en
    H1, que es correcta.

### Checklist

- [x] **Cambio 1: `advisor_id` nulo decidido y explícito.**
  - La línea «después» (H1) dice «Caso huérfano: un caso `assigned` cuyo `advisor_id` es nulo o
    ya no está en `ADVISOR_CHAT_IDS`».
  - R1 (`requirements.md` l.37-40) y la cabecera (l.14-16) lo recogen, con cierre permitido y
    `reply`/`assign` → `403`.
  - T3 (`tasks.md` l.24) usa el fragmento con «es nulo o ya no está».
  - `design.md` §1.1, «Decisión: `advisor_id` nulo» (l.62-81), y §7 (l.283-284) lo declaran
    decidido, no duda abierta.
  - R2-R9 se aplican al nulo porque hablan de «caso huérfano».
- [x] **«Antes» carácter a carácter con el S12 actual.** Ver arriba.
- [x] **«Después» coherente con C1/C2/C5/C6 de la #13.**
  - C1: los tres primeros escalones no cambian. El 4.º solo se salta para
    `close`/`authorize(close)` sobre un huérfano.
  - C2: un huérfano nunca está `closed`.
  - C5: la frase de `reply` sobre `closed` → `409 case_closed` sigue intacta.
  - C6: «el orquestador autoriza antes de comprobar si el caso existe» sigue intacta. El huérfano
    con `reply` recibe `403` vía `authorize(reply)`.
  - Con `advisor_id` nulo no aparece ninguna contradicción: un asesor registrado nunca es «el
    asignado» de un nulo, así que sin la salvedad el resultado sería `403`. La salvedad lo
    convierte en cierre permitido, como decidió el humano.
- [x] **Cambio 2: sin números de línea de otros specs.** Los ids y las secciones existen (ver
  arriba).
- [x] **Tests existentes de S12 siguen pasando** con la «después» (113 passed).
- [x] **EARS.** 15 R con un solo `DEBE`/`NO DEBE` cada uno, sin verbos blandos. R1 conserva el
  patrón ubicuo. La nota «*(Actualizado …)*» es aclaratoria y no añade obligación.
- [x] **Trazabilidad completa.**
  - R1-R11 → T3-T13.
  - R12 → T14. R13 y R14 → T15. R15 → T16.
  - La tabla de cobertura del acceptance cubre los 5 criterios.
- [x] **Ids estables.** R1-R15 y T1-T17 no se renumeran. Las tasks siguen todas en `[ ]` y en orden.
- [x] **Nada inventado.** El nulo lo decidió el humano. El resto del texto de H1 no ha cambiado
  desde la primera vuelta.
- [x] **Dudas abiertas.** Las dudas 1-6 de `design.md` §7 (l.261-281) siguen listadas y sin
  resolver en silencio.
- [ ] **Coherencia con el vocabulario de la #14.** En el fondo coinciden: las dos tratan el nulo
  como huérfano y como decisión del humano. Pero `design.md` describe mal el estado actual de la
  #14 (cambio 3).

### Cambios requeridos

3. **`specs/contrato_cierre_casos_huerfanos/design.md`**: en dos sitios se describe el vocabulario
   de la #14 como si aún dijera «por derivación».
   - **Sitio 1: §1.1, «Decisión: `advisor_id` nulo», segundo párrafo (l.72-77).** Dice que la #14
     lo trataba «**por derivación propia**, no por decisión del humano (su vocabulario «Caso
     huérfano» en `requirements.md` …)» y que su spec_author «puede cambiar la nota «por
     derivación» por una remisión a S12».
   - **Sitio 2: §6, primera viñeta (l.215-218).** Dice que el término «incluye el `advisor_id` nulo
     «por derivación del spec»».
   - **Qué dice hoy la #14.** El vocabulario de `specs/autorizacion_asesores/requirements.md`
     (bloque «Vocabulario», entrada **Caso huérfano**) ya dice «Decidido por el humano
     (2026-10-31), regla publicada por la #17, incluido el caso con `advisor_id` nulo (también
     decidido por el humano el 2026-10-31)». La nota «se deriva de la regla decidida, no es una
     decisión nueva» solo sigue en `specs/autorizacion_asesores/design.md` §3.1, en el párrafo
     del `advisor_id` nulo.
   - **Corrección.** Decir que el vocabulario de la #14 ya lo da como decisión del humano. La nota
     pendiente de alinear es la de su `design.md` §3.1. Su T8 sigue dependiendo de que el nulo
     sea huérfano, ahora con apoyo en la decisión.
   - **Qué no tocar.** Ni H1, ni ningún R, ni ninguna T.

Aviso para la #14, que no se arregla aquí: su `requirements.md` (vocabulario) y su `design.md`
§3.1 se contradicen sobre si el nulo es decisión del humano o una derivación. Lo tiene que alinear
su spec_author.

### Decisiones del humano abiertas (no las resuelve este spec)

- Reenvío de mensajes del cliente al Telegram de un asesor retirado mientras el huérfano no se
  cierra (Ley 1581; sería un cambio de S13/#15). `design.md` §7, duda 1.
- Cuándo deja de estar un asesor en `ADVISOR_CHAT_IDS`: se ve tras reiniciar handover, y si se
  vuelve a añadir, el caso deja de ser huérfano. Es lo que se deriva hoy; no está en S12. Duda 2.
- `closed_by` al cerrar un huérfano (se deriva que es quien cierra; la #14 R47 lo concreta).
  Duda 3.
- Detalles del recuento al arrancar (evento, nivel, si se registra con 0, si se repite). La #14
  los propone en R49-R51 con [REVISAR: D12/D13]. Duda 4.
- Aviso al cliente o al asesor al cerrar un huérfano (A12 de la #16). Duda 5.
- Caso `assigned` de un asesor activo que nunca lo cierra (opción F). Duda 6.

## Tercera vuelta (2026-10-31)

**Veredicto:** SPEC_APPROVED

Modo nocturno: esta revisión hace de puerta de aprobación del spec en lugar del humano.

### Verificaciones hechas (con evidencia)

- **Cambio 3 resuelto.**
  - `design.md` §1.1, «Decisión: `advisor_id` nulo», segundo párrafo (l.72-77): ahora dice que el
    vocabulario «Caso huérfano» de la #14 «ya lo recoge como decidido por el humano (2026-10-31),
    con la regla publicada por esta feature». Remite el razonamiento técnico a §3.1 de su
    `design.md`. Ya no habla de «derivación propia» ni pide cambiar la nota.
  - `design.md` §6, primera viñeta (l.215-219): «incluye el `advisor_id` nulo como decisión del
    humano (2026-10-31), publicada por esta feature … Ya está alineado».
  - Las dos frases coinciden con el texto actual de `specs/autorizacion_asesores/requirements.md`
    (Vocabulario, **Caso huérfano**, l.33-35): «Decidido por el humano (2026-10-31), regla
    publicada por la #17, incluido el caso con `advisor_id` nulo (también decidido por el humano
    el 2026-10-31)».
- **Sin otros restos.** Busqué `deriva|derivación` en `specs/contrato_cierre_casos_huerfanos/`.
  Solo aparece en §7, dudas 2 y 3 (l.269, l.273), que tratan otros temas y son correctas. §7
  (l.284-285) deja claro que el nulo no es una duda abierta.
- **«Antes» = S12 actual.** La l.35 de `design.md` y la única fila `| S12 |` de
  `contracts/CONTRATOS.md` son iguales al comparar las cadenas exactas. `CONTRATOS.md` tiene 0 CR.
- **«Antes» → «después» (l.41).** `difflib`, carácter a carácter: 3 operaciones `insert`, ningún
  `delete` ni `replace`. Número de `|`: 4 y 4. La «después» incluye:
  - la regla del nulo («cuyo `advisor_id` es nulo o ya no está en `ADVISOR_CHAT_IDS`»);
  - el cierre por cualquier asesor registrado (`close` → `closed`; `authorize(close)` →
    `200 allowed=true`; «cerrarlo no es reasignarlo»);
  - la prohibición de reply/assign (`reply`/`authorize(reply)`/`assign` → `403 forbidden`);
  - la salvedad en la precedencia y el procedimiento A.
- **Tests existentes de S12.** Copié `contracts/`, `conftest.py` y `pytest.ini` al scratchpad,
  sustituí S12 por la «después» y ejecuté `contracts/tests/test_contratos_doc.py` con el `.venv`:
  **113 passed**.
- **Fragmentos de los tests nuevos.** Los 14 fragmentos distintos de T3-T13 (`tasks.md` l.24-34)
  están literalmente en la «después».

### Checklist

- [x] Cambio 3 resuelto y coherente con el vocabulario actual de la #14.
- [x] No quedan descripciones caducadas ni números de línea de otros specs.
- [x] «Antes» idéntica, carácter a carácter, a la S12 publicada. «Después» con la regla del nulo,
  el cierre por cualquier asesor registrado y sin reply/assign.
- [x] Los tests existentes de S12 siguen encontrando sus fragmentos (113 passed).
- [x] EARS: 15 R, un `DEBE`/`NO DEBE` cada uno, sin verbos blandos. No hay cambios desde la
  segunda vuelta.
- [x] Trazabilidad: R1-R11 → T3-T13; R12 → T14; R13 y R14 → T15; R15 → T16. Los 5 criterios del
  acceptance están cubiertos.
- [x] Ids estables: R1-R15 y T1-T17 sin renumerar. Todas las tasks siguen en `[ ]` y en orden.
- [x] Nada inventado. Las dudas 1-6 de `design.md` §7 siguen abiertas, documentadas y sin
  resolver en S12 (no bloquea).
- [x] Nada peligroso: solo `contracts/`, sin red, sin borrar datos.

### Cambios requeridos

Ninguno.

Aviso para la #14, que no se arregla aquí: `specs/autorizacion_asesores/design.md` §3.1
(l.162-164) sigue diciendo «Se deriva de la regla decidida, no es una decisión nueva». Su
`requirements.md` ya lo da como decisión del humano, así que su spec_author tiene que alinear esa
nota. La #17 no depende de ello.
