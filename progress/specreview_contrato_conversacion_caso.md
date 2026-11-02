# Spec review — contrato_conversacion_caso (feature #15)

**Veredicto:** SPEC_APPROVED

Revisado el 2026-11-01 (modo nocturno, tercera vuelta) contra
`specs/contrato_conversacion_caso/{requirements,design,tasks}.md`, el acceptance de la #15,
los criterios «Decidido por el humano (2026-10-31)» de la #16, `progress/propuesta_etapa2.md` §6
y el estado actual de `contracts/CONTRATOS.md`. No se ejecutan tests (revisión de spec).

## Cambios pedidos en vueltas anteriores
- [x] Cambio 1 (S13 incompleto): R36 + T31; criterio de qué entra en S13 en design §1 l.43-53.
- [x] Cambio 2 (identidad S6 ↔ S13): R37 + T33, R39 + T34; encaje con S6 en design §4.3 l.197-204.
- [x] Cambio 3 (enlace a S12): R38 + T32.
- [x] Cambio 4 (coherencia): R34 permite ampliar la docstring de `cases.py` (T29 lo comprueba);
  design §1 l.23 y T0 coinciden: sin la #13 no se empieza.
- [x] Novedad de esta vuelta: R37/R39 pasan de «REVISAR, pendiente del humano» a supuesto
  conservador adoptado en modo nocturno (requirements l.28-33, design §7 l.267, T0). Es el default
  más restrictivo (el remitente, nunca el chat de grupo), coincide con la decisión del humano «el
  `advisor_id` es el id del remitente del webhook» (#16), no cambia la #10 y documenta la
  alternativa (ids positivos: sustituir R39 y T34). Aceptable según la regla de default seguro.

## Cobertura del acceptance de la #15
- [x] A1 ruta, modelos, `200 forwarded|not_assigned`, errores 401/422/404/502/500 → R1-R12, R19, R24.
- [x] A2 línea `Llama` de close con `orchestrator` → R14 (T17 conserva el texto previo, que coincide
  con `CONTRATOS.md` l.278).
- [x] A3 S13 con el funcionamiento de la #16 → R15-R18, R36-R39.
- [x] A4 modelos exportados, ejemplos, rechazos (`text`, `at` sin zona, `status`) → R20, R22, R25, R28-R32.
- [x] A5 comandos por `POST /messages` sin cambios → R17, R33.
- [x] A6 aditivo y tests previos verdes → R34, R35.

## Fidelidad a la #16 y propuesta §6
- [x] Solo `assigned` se reenvía; `open` → flujo con RAG (R15). Comandos `/responder` y `/cerrar` (R17).
  Asesor que no manda comando → flujo actual (R36). Fallo `502` → texto fijo sin RAG (R16).
  `advisor_id` = remitente validado con `TELEGRAM_WEBHOOK_SECRET` (R18). Autorización con S12 (R38).
- Confirmaciones y aviso al cerrar quedan en la #16 con un criterio explícito (design §1). Correcto.

## Comprobaciones puntuales
- [x] Precondición de T0 cumplida en el estado actual: fila `S12` (l.436), fila común
  `403 | forbidden` (l.42) y `### POST /cases/{id}/authorize` (l.379) al final de `## Rutas`.
- [x] Todos los fragmentos que buscan T14, T15, T18-T21 y T31-T34 figuran en el texto de design §4.1/§4.3.
- [x] EARS: un `DEBE`/`NO DEBE` por R; R36-R39 con la forma «La fila `S13` … DEBE …» ya aceptada.
- [x] Tasks T0-T34 en `[ ]`, en orden, cada una con sus R; entre todas cubren R1-R39.
- [x] Diseño: solo `contracts/`, sin dependencias ni variables nuevas, 5 alternativas descartadas,
  «Supuestos a confirmar» presente.
- [x] Nada peligroso: no borra datos, no usa la red, no sale del repo.

## Notas no bloqueantes
- Si el humano elige más tarde la alternativa de ids positivos, se sustituyen R39 y T34 (design §7).
- `closed` → `200 not_assigned` sigue como derivado del acceptance (sin `409` en la lista), no como
  decisión nueva.
