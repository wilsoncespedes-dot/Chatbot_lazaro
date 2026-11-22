# Spec review — #72 consentimiento_unico_por_cliente

**Veredicto:** SPEC_APPROVED

- Cobertura: los 8 criterios de `acceptance` están cubiertos por R1-R27 (tabla de trazabilidad en requirements.md).
- EARS: cada R usa un patrón válido con un solo DEBE o NO DEBE. Cada uno se puede verificar con un test concreto (T2, T12-T26, T27).
- Diseño: respeta las 3 capas y no añade dependencias. Incluye una alternativa descartada y la sección «Supuestos a confirmar» (legal, reasignación de identidad, `ok_no_access`). Las claves de retención son configurables y su valor por defecto es seguro (vacío, sin caducidad). Si falla la vinculación, el sistema vuelve a pedir el aviso (R17).
- Tasks: T1-T29 están en `[ ]`, en orden, y cada una cita sus R. Entre todas cubren R1-R27.
- Nada peligroso: no hay red ni archivos fuera del repo. El borrado solo ocurre en la supresión de un cliente o en la purga por plazo configurado.

Observaciones no bloqueantes:
- T10 menciona R2, pero el test que lo verifica es T12.
- El implementador debe mantener `tests/fakes.py` alineado con `FakeRepository`.
