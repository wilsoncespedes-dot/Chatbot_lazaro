# Spec review — feature #43 proveedor_whatsapp_real (segunda revisión)

**Veredicto:** APPROVED

Proveedor: Meta Cloud API, según la decisión del dueño del 2026-11-03.
Esto satisface el criterio 1 del acceptance. Los criterios 2–4 están
cubiertos por R1–R62, según la matriz de `requirements.md`.

## Bloqueante previo — resuelto

Los requirements que tenían varios `DEBE` se partieron en ids nuevos, sin
renumerar los existentes:

- R15 → R15 + R51
- R21 → R21 + R52
- R23 → R23 + R53
- R37 → R37 + R54 + R55
- R40 → R40 + R56
- R41 → R41 + R57 + R58
- R46 → R46 + R59
- R50 → R50 + R60
- R31 → R31 + R61
- R32 → R32 + R62

Ahora cada `R<n>` lleva un único `DEBE`/`NO DEBE`.

En R26, R42 y R47 queda un solo `DEBE` que rige dos verbos coordinados de la
misma acción. No es bloqueante.

## Tasks

- T1–T22 siguen en `[ ]` y en orden.
- Comprobé de forma mecánica que cada R1–R62 aparece en al menos una línea
  «Cubre:».
- Los ids nuevos están asignados a tests concretos: R51 en T14, R52 en T15,
  R53 en T16, R54–R58 y R62 en T18, R59 en T19, R60 en T22 y R61 en T17.

## No bloqueante previo — resuelto

`design.md` §`adapters/whatsapp_window.py` ahora indica que `record_inbound`
sobrescribe siempre el valor con `SET ... EX`. La contradicción anterior ha
desaparecido.

Diseño, dependencias, contratos y seguridad: siguen sin cambios respecto a
la revisión anterior y sin observaciones.
