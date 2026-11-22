# Spec review — #70 aviso_intencion_compra

**Veredicto:** SPEC_APPROVED

- Cobertura: los 5 criterios de `acceptance` están cubiertos por R1-R25 (frases configurables y motivo del router: R1-R8; aviso, prioridad, evento en vivo y caso opcional: R13-R18; traspaso humano intacto: R10; eventos y anti-repetición: R11, R19, R20; texto como dato: R22-R23).
- Diseño: respeta la arquitectura. No cambia `contracts/` ni handover, no añade dependencias y describe una alternativa descartada y los supuestos configurables. Las funciones que reutiliza existen en el código (`publish_case_event`, `add_event`, `get_contact_last_case`, `_handover`, `_resolve_and_run`).
- Tasks: todas están en `[ ]`, en orden, y juntas cubren R1-R25. T15 cierra con `init.sh` y el mapa R→test.
- Seguridad: no exige borrar datos ni usar la red. El evento no guarda texto del cliente.

Observaciones no bloqueantes (el implementador puede ignorarlas):
- R6 y R24 enlazan dos acciones en un solo requisito. Se pueden dividir si se quiere un EARS más estricto.
- T8 (repositorio) no tiene tests propios. Quedan cubiertos de forma indirecta por T11 y T14.
