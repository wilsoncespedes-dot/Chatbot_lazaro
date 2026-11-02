# #29 panel_asesores — Tasks

- [x] T1 — `get_session_for_role` en Protocol, Fake y Postgres de `adapters/repository.py`; `get_session` delega con `"admin"`. Cubre: R4, R5.
- [x] T2 — `authenticate_profile` en `domain.py`; `authenticate_admin` delega sin cambiar comportamiento (tests de #21 siguen verdes sin tocarlos). Cubre: R1, R2, R3.
- [x] T3 — `try_assign` en Protocol, `HttpHandoverClient` y `FakeHandoverClient` de `adapters/handover.py`; `assign` sin cambios. Cubre: R11, R14.
- [x] T4 — `assign_case` y `close_case` en `domain.py` con `_record_forbidden` en `403`; `_command_close` usa `close_case` (tests de #16 siguen verdes sin tocarlos). Cubre: R11, R12, R14, R15.
- [x] T5 — `advisor_panel.py`: plantillas de login, home con formularios por `case_id`, error con mensaje fijo por código. Cubre: R7, R8, R14.
- [x] T6 — `advisor_routes.py`: login/logout, home, `reply`/`assign`/`close` con orden sesión → CSRF → vínculo → validación → dominio. Cubre: R1, R2, R4, R6, R9, R10, R11, R12, R14.
- [x] T7 — `main.py`: incluir router, exención de `X-Service-Token` para `/asesor`, redirección de `LoginRequired` según path y respuesta `403` de `CsrfInvalid`. Cubre: R4, R6.
- [x] T8 — `tests/test_advisor_panel.py`: login correcto; 401 idéntico para inexistente/contraseña/`admin`/`cliente`; 429 compartido con `/admin/login`; sin sesión/expirada/logout/rol cambiado → 303; sesión asesor en `/admin` y admin en `/asesor` → 303; CSRF ausente/erróneo → 403 sin llamadas; cabeceras CSP y sin orígenes externos; sin `SERVICE_TOKEN` ni hashes en respuestas; perfil sin vínculo → 403 sin llamadas; reply/assign/close correctos con `advisor_id` de la sesión (un `advisor_id` en el formulario se ignora); aislamiento: caso `assigned` de otro asesor → 403 + `advisor_forbidden`; huérfano: close OK y reply/assign 403 (respuestas de Fake handover); 404/409/422/502 con mensaje fijo sin `message` de handover. Cubre: R1–R12, R14, R15.
- [x] T9 — (depende de #33, ver design Dependencia #33) `list_cases(advisor_id)` en el cliente de handover y `GET /asesor/cases`. Cubre: R13.
- [x] T10 — (depende de #33, igual que T9) Tests de listado: solo se pide con el `advisor_id` de la sesión, un parámetro `advisor_id` en la query se ignora, sin `contact_id`/`chat_id` en el HTML, error de handover → 502. Cubre: R13.
- [x] T11 — `./init.sh` verde y `progress/impl_panel_asesores.md` con trazabilidad R→test. Cubre: R1–R15.
