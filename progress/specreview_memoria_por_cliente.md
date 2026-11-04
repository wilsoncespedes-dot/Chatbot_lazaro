# Spec review — feature #40 memoria_por_cliente

**Veredicto:** APPROVED (modo nocturno)

## Comprobaciones
- Cobertura: A1–A5 del acceptance mapeados a R1–R56 (tabla en requirements.md).
- Diseño: todo en orchestrator, sin cambios en `contracts/` ni dependencias nuevas;
  esquema aditivo/idempotente; alternativas descartadas y «Supuestos a confirmar» presentes.
- Referencias al código verificadas: `end_client_session(..., notify)` y
  `repository.end_client_session` -> bool (domain.py:658), `_handover` -> bool
  y `link_case` (domain.py:1127,1151), `_tool_escalate` ramas repeated_failure
  (domain.py:1350), `active_client_id`, `_raise_authorization_error`,
  `handover.authorize(..., "reply")` (`CaseAuthorizeAction = reply|close`),
  `get_active_session_by_profile`, `add_identity_audit`, índice
  `suppression_requests_one_pending`, rutas/plantillas de `advisor_routes.py`/`advisor_panel.py`.
- Tasks T0–T16 en `[ ]`, ordenadas, y entre todas cubren todos los R<n>.
- Nada peligroso: el borrado solo ocurre en `execute_suppression`, con rol
  ejecutor validado (default `admin`), sin ruta HTTP ni herramienta IA que lo invoque;
  retención no toca `client_memory`. `MEMORY_ENABLED=false` por defecto es un
  default seguro y configurable respaldado por docs/proyecto.md (validación legal pendiente).

## Observaciones no bloqueantes
- R32 contiene dos verbos (`DEBE indicar` y `NO DEBE mostrar`); aceptable como un único comportamiento.
- R48–R51 son requisitos sobre pruebas; verificables por existencia del test.
- La ejecución de supresión por persona queda sin UI/ruta hasta #41 (S5); A4 se
  verifica a nivel de dominio.
