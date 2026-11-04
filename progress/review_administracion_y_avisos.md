# Review — feature 42 `administracion_y_avisos`

**Veredicto:** APPROVED

`./init.sh` (ejecutado por el reviewer): EXIT=0, 2951 passed, 1 skipped, 2 warnings (deprecaciones de Pydantic en `test_conversation_states.py`, no relacionadas con esta feature). Modo nocturno.

## Trazabilidad requirements ↔ tests
Se comprobó con grep que existe cada función `def test_*` citada en `progress/impl_administracion_y_avisos.md` §Trazabilidad (son 89 nombres, ninguno falta).
- R1–R11: [x] `services/orchestrator/tests/test_admin_clients.py` (tabla con estado, días, sesión y aviso; cálculo sin contador; crear con y sin fechas; 422 sin eco de la contraseña; 409; renovar; renovar revocada 409; revocar; cerrar sesión; 404)
- R12–R14: [x] `tests/test_admin_permissions.py`: parametrizado sobre las 5 rutas GET y las 8 POST nuevas (sin sesión, sesión de asesor, sesión vencida, CSRF ausente o incorrecto), además de `test_expiry_notices_without_service_token_returns_401`
- R15–R24: [x] `tests/test_admin_texts_versions.py`
- R25–R35, R72, R73: [x] `tests/test_admin_templates.py`, `tests/test_administration_pure.py::test_effective_templates_registered_then_approved_only_and_expiry_no_fallback`
- R36–R40, R74: [x] `tests/test_admin_settings.py`, `tests/test_administration_pure.py`, `tests/test_admin_clients.py::test_create_without_dates_uses_configured_validity_days`
- R41: [x] `test_administration_pure.py::test_within_business_hours_boundaries_days_offset_and_midnight`
- R42, R43: [x] `tests/test_business_hours.py` (3 tests)
- R44: [x] un test de auditoría por área (clients, texts, templates, settings, metrics)
- R45–R59: [x] `tests/test_expiry_notices.py`. Las partes dobles de R47, R48 y R53 tienen tests separados, y R54 se prueba con hilos concurrentes
- R60, R61: [x] `scripts/tests/test_avisar_vencimientos.py`, `scripts/tests/test_render_blueprint.py::test_expiry_notice_worker_uses_handover_image_and_loop`
- R62–R68: [x] `tests/test_admin_metrics.py`
- R69: [x] `tests/test_config.py::test_admin_settings_defaults_and_env_example`, `::test_admin_settings_reject_invalid_values`
- R70: [x] `tests/test_admin.py::test_navigation_links_to_new_admin_sections`
- R71: [x] `./init.sh` verde con los defaults

## Tasks completas
- T0–T44: [x] (todas en `[x]` en `specs/administracion_y_avisos/tasks.md`)

## Verificación puntual del código
- El reclamo atómico en Postgres (`services/orchestrator/orchestrator/adapters/repository.py:4460-4481`) usa `INSERT ... ON CONFLICT DO UPDATE ... WHERE status='failed' AND attempts < max ... RETURNING`. Así no se reenvía si el estado es `sent` o `sending`, ni si es `failed` con el máximo de intentos (R53, R54). El Fake usa un lock (`:2169`).
- `send_expiry_notices` (`domain.py:3826`): sigue el orden del spec (desactivado → fuera de horario → no_chat → no_text/no_template → reclamar → enviar). No escribe en `messages` ni hace `touch` (R59). El fallo marca `failed` y la pasada sigue (R58).
- El ajuste inválido registra un warning solo con la clave (`administration.py:207`, R39).
- Las variables nuevas están en `.env.example:158-170`. El worker está en `docker-compose.yml:58`, `render.yaml:222` y `services/handover/Dockerfile:11`. La ruta está documentada en `contracts/CONTRATOS.md:714`.
- No hay `print`, `eval`/`exec` ni TODOs en `administration.py`, `admin.py`, `admin_routes.py` ni `scripts/avisar_vencimientos.py`.

## Checkpoints
- C1: [x] (archivos base y docs presentes; `./init.sh` con exit 0)
- C2: [x] (una sola feature `in_progress`, la #42; `progress/current.md` describe la sesión activa)
- C3: [x] (sin servicios nuevos; lo compartido está en `contracts/lazaro_contracts/credentials.py`; ruta en CONTRATOS.md; sin dependencias nuevas; `.env` sin trackear)
- C4: [x] (tests con fakes y reloj inyectado; suite verde; las pruebas de permisos y CSRF existen)
- C5: [x] (sin `*.tmp` ni `.env` sin trackear. La entrada de #42 en `progress/history.md` la añade el leader al cerrar)
- C6: [x] (los 3 archivos del spec; spec review aprobado; tasks en `[x]`; todos los R<n> cubiertos)

## Observaciones no bloqueantes
1. Una fila de aviso en estado `sending` huérfana (el proceso cae entre el reclamo y el envío) no se reintenta nunca. Es el comportamiento elegido en el spec (S2): se ve en `/admin/clientes`, pero no hay forma de reiniciarla desde el panel. Conviene considerarlo en una feature futura.
2. Hay funciones de test con el mismo nombre en `tests/test_admin.py` y `tests/test_admin_permissions.py` (`test_post_without_or_with_wrong_csrf_is_forbidden`, `test_post_without_session_redirects_before_csrf`). La trazabilidad de R12 y R13 apunta correctamente a `test_admin_permissions.py`.
