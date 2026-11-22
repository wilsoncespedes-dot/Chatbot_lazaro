# Spec review — #69 estrategias_asignacion

**Veredicto:** SPEC_APPROVED

- Cobertura: los 5 criterios de `acceptance` están cubiertos (R1-R3 y R4 para la interfaz y el registro, R15-R19 para el ajuste y el modo, R10-R14 para las reglas de #52, R21 para las pruebas).
- Verificable: T10 y T12 nombran tests concretos para cada grupo de R.
- Diseño: respeta las 3 capas. No hay dependencias nuevas. Describe una alternativa descartada y la sección de supuestos. Las estrategias válidas viven en `contracts`, así que orchestrator no importa handover.
- Tasks: todas están en `[ ]`, en orden y con sus R. Entre todas cubren R1-R21.
- Sin riesgos de seguridad ni de datos.

Observaciones no bloqueantes:
- R3, R7 y R12 usan "y" o "o" en la condición. Se pueden probar tal como están y no justifican rechazar.
- Para tolerar a un asesor que sale del roster, el puntero se compara por orden lexicográfico y no por pertenencia (ver «Supuestos»). Conviene dejar un test que lo cubra.
