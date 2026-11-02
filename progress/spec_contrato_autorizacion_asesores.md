# spec_author — contrato_autorizacion_asesores (#13), corrección 2026-10-31

Decisiones del humano (2026-10-31) incorporadas. Estado en `feature_list.json` sin tocar
(`blocked`). Sin código ni tests escritos; suite no ejecutada por mí.

## Archivos

- `specs/contrato_autorizacion_asesores/requirements.md`
- `specs/contrato_autorizacion_asesores/design.md` (reescrito entero; secciones nuevas §1.1, §4.5, §5.1, §9)
- `specs/contrato_autorizacion_asesores/tasks.md`

## Requirements

- Reescritas: R18 (excepción: «Dónde» de la fila común 409, R49), R41 (excepción: S11, R50),
  R46 (C5: reply sobre `closed` → `409 case_closed`, sin enviar nada; antes `403 forbidden`).
- Sin cambios de texto: R43, R44, R45, R47 (C1, C2, C3, C6 aceptadas tal cual), R26.
- Nuevas: R48 (fila `409 case_closed` en la tabla de reply), R49 (fila común 409: «Dónde»
  cita assign y reply), R50 (S11: otro asesor → `403 forbidden`), R51 (S12 documenta que
  cambia el `200` sin cambios de S11 de la #9), R52 (el diff de `CONTRATOS.md` solo elimina
  las dos líneas «antes» de E1/E2), R53 (línea `Llama` de `authorize` con `/cerrar` y
  `POST /cases/{id}/close`).
- Cabecera y sección G sin marca REVISAR («Decidido por el humano (2026-10-31)»); D1-D6;
  sección «Historial de cambios» nueva.

## Tasks

- Reescritas: T4 (+R53), T5, T7 (+R51), T44 (`test_assumptions_s12_reply_on_closed_is_case_closed`),
  T39 (diff con E1/E2 literales, R52), T40 (trazabilidad R1-R53).
- Nuevas: T46 (fila 409 en reply), T47 (E1), T48 (E2), T49
  `test_reply_errors_table_has_case_closed`, T50 `test_common_rules_case_closed_row_cites_reply`,
  T51 `test_assumptions_s11_other_advisor_gets_forbidden`, T52
  `test_assumptions_s12_documents_s11_change`, T53 `test_authorize_route_caller_mentions_cerrar_command`.

## Excepciones al principio aditivo (lista cerrada, design §1.1)

- E1: fila común `409 | case_closed`, solo «Dónde»: `` `/cases/{id}/assign` `` →
  `` `/cases/{id}/assign`, `/cases/{id}/reply` ``. R49; T50 + T39.
- E2: fila `S11`: «sin cambiar el asesor asignado;» → «… cuando quien asigna es el asesor
  asignado; si es otro asesor, responde `403` con `error` = `forbidden` sin cambiar el caso
  (S12, cambio de la #13);». R50; T51 + T39.
- C5 en reply no exige editar ninguna línea publicada: la fila `409` de reply es nueva (R48).

## Tests de contrato existentes afectados (design §5.1)

Ninguno cambia de código ni pierde aserciones. Leen líneas editadas y siguen verdes porque las
líneas «después» conservan sus fragmentos: `test_assumptions_include_assign_idempotency` (S11),
`test_common_rules_case_closed_row_cites_assign` y `test_common_rules_document_error_shape_and_codes`
(fila 409), `test_errors_table_has_route_specific_rows[reply]` y `test_errors_table_has_common_rows[reply]`
(tabla de reply). `test_assign_section_documents_s11` no se ve afectado (la prosa de assign no se edita).

## Desalineaciones con #14/#16 (design §9; no editadas)

- #14: D5 y la nota de alineación (design §8), flujo §4.2 (`case_closed` → `AdvisorForbidden 403`),
  R26 (debe ser `409`), R29/R30/T44 (evento con `code:case_closed`), T41 (espera `403`).
- #16: R14 (D5 de la #14), design l.35, Rec. 2 y D6, tasks T24 y T33. D4 (opción a) queda alineada.

## Duda que sigue abierta (design §7; no bloquea, valor por defecto: no se edita)

La prosa de `### POST /cases/{id}/assign` («Asignar un caso ya `assigned` responde igual, `200` …»)
y el «Cuándo» «(S11)» de la fila común 409 quedan imprecisos tras E1/E2, pero no están en la lista
de líneas que el humano autorizó editar. Si quiere corregirlos, hay que añadir E3/E4 con su R
antes de implementar.
