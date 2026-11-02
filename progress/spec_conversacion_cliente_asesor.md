# Spec #16 conversacion_cliente_asesor — corrección nocturna (2026-11-01)

Estado: `spec_ready` (sin cambios en `feature_list.json`). Solo se tocaron
`specs/conversacion_cliente_asesor/{requirements,design,tasks}.md`.

## 1. Alineación con C5 de la #13 y el código real de la #14
- Comprobado en `services/orchestrator/orchestrator/domain.py`: `reply_to_case` lanza
  `AdvisorForbidden` (403, con `_record_forbidden`), `CaseClosed` (409 `case_closed`, sin
  `advisor_forbidden`), `CaseNotFound` y `UpstreamError`. El D5 anterior («409 → 403») ya no existe.
- R14 ya solo trata `403`. Se añadieron:
  - R60: `/responder` con `CaseClosed` → texto `ADVISOR_COMMAND_CASE_CLOSED_REPLY`.
  - R61: `/cerrar` con `case_closed` → mismo texto, sin aviso al cliente.
  - R62: un `409` no genera `advisor_forbidden`.
- R21 y R24 solo cubren `forbidden` y `sender_not_user`.
- Variable nueva `ADVISOR_COMMAND_CASE_CLOSED_REPLY`; ahora hay ocho textos (R44, §6, T5, T53,
  T54).
- Design §3.3: flujo, divergencia documentada con S8 y excepciones no previstas (suben a
  `_process`). §5 añade `CaseClosed`.
- Tasks:
  - T24, T30 y T33 sin `case_closed`;
  - T71-T73 nuevos;
  - T0 comprueba `CaseClosed` y el candado de la #18.

## 2. Cambios del informe `progress/specreview_conversacion_cliente_asesor.md`
1. Fake del gateway con `fail_for` (§3.7, T4b, T25): ya estaba; verificado contra el código
   actual.
2. A12: D9 resuelta. El aviso solo sale con `/cerrar` (R59). Se añade el test T74, que faltaba
   para R59.
3. D4 opción (a), decidida por el humano y publicada en la línea `Llama` de `authorize`. Caso
   `closed` con la opción (c), alineada con C5 y con D7 de la #14.
4. Las dudas de `docs/proyecto.md` §12 se listan en design §11: bot único y Ley 1581, con la
   ampliación del tratamiento de datos.
5. C1-C4 documentadas en §7 y §9.2. Lo que antes era B1 queda resuelto por D10 de la #14
   (asignación y cierre condicionales) y por la #18 (candado); el riesgo residual es el aceptado
   en D10. Lo que antes era B2 queda resuelto por la #17 y D11 de la #14 (opción C +
   procedimiento A). Se documentan el riesgo residual de reenvío a un asesor retirado y los
   tests de la #14 que lo cubren.
6. Las marcas de D1 en R1-R4 están resueltas.
7. T65 es incondicional: `requests == []`, `denials == []` y `notifications` sin cambios.

## 3. Marcas de revisión
- No queda ninguna marca de revisión ni decisión bloqueante.
- §9 se reescribió en dos partes:
  - 9.1, decididas o publicadas:
    - la identidad por `telegram_user_id` (S13);
    - C5;
    - `closed` → `not_assigned`;
    - D4 (a);
    - huérfanos;
    - carreras.
  - 9.2, supuestos D1-D9 y C1-C4, cada uno con su justificación de opción más conservadora.
- Se añadieron tres alternativas descartadas a §10:
  - `closed` como no autorizado;
  - reutilizar el texto de fallo;
  - la opción B de huérfanos.
- La descripción de la #16 en `feature_list.json` aún dice «PENDIENTE … alinear con C5».
  Ya está hecho, pero no se edita (solo se permite tocar `status`): el leader puede limpiarla.
