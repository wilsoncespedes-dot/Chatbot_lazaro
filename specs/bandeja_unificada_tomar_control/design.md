# Design — #68

Explora `services/orchestrator/orchestrator/domain.py` (assign_case, listado de bandeja, repositorio y fakes en `tests/fakes.py`), `advisor_routes.py`, `advisor_panel.py`, `panel_live_routes.py`, y reutiliza lo existente:
- Estado derivado por función pura `conversation_status(...)` en un módulo nuevo `orchestrator/conversation_status.py`.
- Repositorio: método nuevo `list_conversations(...)` y `take_conversation(conversation_key, advisor_id)` atómico (bajo el candado/transacción que ya usa `assign_case`); en `tests/fakes.py` implementar el equivalente con lock.
- Rutas nuevas en `advisor_routes.py`: `GET /asesor/conversaciones` (lista), `GET /asesor/conversaciones/{id}` (lectura + auditoría), `POST /asesor/conversaciones/{id}/tomar`. «Devolver al bot» reutiliza la ruta existente.
- Etiqueta de canal: reutiliza `channel_label.py` (#67). Escapar todo HTML.
- Sin cambios de esquema salvo lo mínimo necesario; si hace falta una tabla, añadirla a la migración existente del repositorio.
