# Spec review — #52 asignacion_automatica_carga

**Veredicto:** APPROVED

## Cola sin asesores (supuesto a confirmar)
Resuelta de forma segura. `design.md` S1 y R23 fijan que un caso en cola no se asigna solo cuando un asesor vuelve a estar disponible. Esto sigue el supuesto del acceptance y no añade barrido ni proceso de fondo. R10 y R12 mantienen el flujo actual de espera y vencimiento. No hay base para bloquear.

El comportamiento no tiene variable de entorno propia. Es el default conservador del acceptance y queda listado como supuesto. Si más adelante se quiere reparto de la cola, será otra feature.

## Comprobaciones
- Cobertura: los 7 criterios de acceptance están cubiertos (R1–R4 modo; R6–R12 reparto y cola; R13–R15 atomicidad; R16–R17 exclusiones; R19–R22 registro y bandeja; R23 supuesto; R26 pruebas).
- EARS: cada R<n> tiene un solo DEBE y es verificable. Hay reservas menores no bloqueantes: R23 mezcla «NO DEBE» y «DEBEN», y R26 es meta-requisito.
- Diseño: respeta la separación presencia (orchestrator) / carga (handover). No añade dependencias. Incluye 3 alternativas descartadas y la sección de supuestos S1–S5. El `ASSIGNMENT_MODE` va a `.env.example`. La atomicidad usa advisory lock más UPDATE condicional, así que nunca pisa una acción humana.
- Tasks: las 20 están en `[ ]`, en orden, con R<n>, y cubren R1–R26.
- Nada peligroso: no borra datos ni usa la red fuera de los servicios internos.

## Notas para el implementer (no bloqueantes)
- R18: el caso reutilizado ya asignado debe resolverse como `skipped` o `queued` en handover. Cubrirlo con `test_reescalation_does_not_reassign`.
