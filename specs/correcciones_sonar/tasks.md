# Tasks — #58 `correcciones_sonar`

Reglas para todas las tasks: no se edita ni se borra ningún test existente
(única excepción: T9); los tests nuevos se añaden al final del archivo indicado
y llevan en su docstring el `R<n>` que cubren.

## Orquestador — correos

- [x] T1 — En `services/orchestrator/orchestrator/memory.py`: eliminar `_EMAIL`, añadir `_contains_email(text: str) -> bool` según `design.md` y usarla en `is_sensitive` y `_is_sensitive_with`. Cubre: R1, R4.
- [x] T2 — En `services/orchestrator/tests/test_memory.py`: añadir `test_email_detection_matches_previous_regex`, parametrizado. Sensibles: `"ana@example.com"`, `"x a@b.c y"`, `"ana@mail.example.com"`, `"a@b@c.d"`. No sensibles: `"ana@example"`, `"@example.com"`, `"ana@.com"`, `"ana@example."`, `"ana @example.com"`, `"ana@ example.com"`, `"sin arroba.com"`. Usar `is_sensitive(text, (), 6)`. Cubre: R1.
- [x] T3 — En el mismo archivo: añadir `test_email_detection_is_linear_on_adversarial_input`, parametrizado con `"a" * 100000`, `"a@" + "b" * 100000`, `"@" * 100000`, `"a@" * 50000`; cada llamada a `is_sensitive(text, (), 6)` termina en menos de 2 s (`time.perf_counter`) y devuelve `False`. Añadir `test_memory_has_no_email_regex`: `orchestrator.memory` no tiene el atributo `_EMAIL`. Cubre: R3, R4.
- [x] T4 — En `services/orchestrator/orchestrator/admin.py`: eliminar `_EMAIL_RE`, añadir `_redact_emails(text: str) -> str` según `design.md` y usarla como primer paso de `redact_reason`. Cubre: R2, R4.
- [x] T5 — En `services/orchestrator/tests/test_admin.py`: añadir `test_redact_reason_matches_previous_email_regex`, parametrizado (entrada → salida): `"ana@example.com"` → `"[redactado]"`; `"a@b@c"` → `"[redactado]@c"`; `"a@b@c@d"` → `"[redactado]@[redactado]"`; `"x a@b y c@d"` → `"x [redactado] y [redactado]"`; `"a@b\t c@d\n"` → `"[redactado]\t [redactado]\n"`; sin cambios: `"@b"`, `"a@"`, `"a@@b"`, `"a @ b"`, `""`. Cubre: R2.
- [x] T6 — En el mismo archivo: añadir `test_redact_reason_is_linear_on_adversarial_input` con las cuatro entradas de T3 (cada llamada en menos de 2 s) y `test_admin_has_no_email_regex`: `orchestrator.admin` no tiene el atributo `_EMAIL_RE`. Cubre: R3, R4.

## Rag — DSN por defecto

- [x] T7 — En `services/rag/rag/config.py`: cambiar el valor por defecto a `database_url: str = ""`. No tocar `REQUIRED_IN_PRODUCTION` ni el validador. Cubre: R5, R7.
- [x] T8 — En `services/rag/tests/test_production_config.py`: añadir (a) `test_database_url_defaults_to_empty`: con `monkeypatch.delenv("DATABASE_URL", raising=False)`, `Settings().database_url == ""`, y el texto de `rag/config.py` no contiene `lazaro:lazaro@`; (b) `test_create_app_without_database_url_does_not_connect`: sin `DATABASE_URL` ni `APP_ENV`, parchear `rag.adapters.repository._pg_connect` para que falle si se llama, y `create_app()` devuelve un `FastAPI`; (c) `test_production_without_database_url_is_rejected`: `Settings(**{**VALID_sin_database_url})` con `DATABASE_URL` sin definir lanza `ProductionConfigError` cuyo texto contiene `DATABASE_URL`. El test existente `test_development_database_credentials_are_rejected` se conserva sin cambios. Cubre: R5, R6, R7.

## Tests de rag

- [x] T9 — En `services/rag/tests/test_adapters.py`: reescribir el cuerpo de `test_fake_embeddings_is_deterministic` con dos variables (`first`, `second`) de dos instancias distintas y `assert first == second`; conservar nombre y docstring. Cubre: R11.

## Script del webhook

- [x] T10 — En `scripts/configurar_webhook.py`: `_network_error` y `_http_error` pasan a `-> None` sin `return 1`; en `main`, cada uno de los cuatro usos queda como llamada seguida de `return 1`. Mensajes intactos. Cubre: R8, R9.
- [x] T11 — En `scripts/tests/test_configurar_webhook.py`: añadir (a) `test_error_helpers_return_none`: `webhook._network_error(RuntimeError("x")) is None` y `webhook._http_error("setWebhook", httpx.Response(500)) is None`, con el mensaje en `stderr`; (b) `test_http_error_exits_with_one`: respuesta 500 → `main` devuelve exactamente `1` y `stderr` contiene `setWebhook falló: Telegram respondió con código 500`; el mismo caso con `--solo-consultar` contiene `getWebhookInfo falló`; (c) `test_network_error_exits_with_one`: `httpx.ConnectError` → `1` y `stderr` contiene `Error de red al llamar a Telegram: ConnectError`; (d) `test_config_errors_exit_with_two`: variable ausente, `PUBLIC_BASE_URL` con `http://` y secreto inválido → exactamente `2` y cero llamadas. Cubre: R8, R9, R10.

## Falsos positivos

- [x] T12 — Añadir el comentario `# NOSONAR: <justificación>` al final de las cinco líneas indicadas en `design.md` (`accounts.py`, `bootstrap_admin.py` ×3, `contracts/lazaro_contracts/production.py`), sin cambiar nombre ni valor. Cubre: R12.
- [x] T13 — Crear `scripts/tests/test_sonar_markers.py` con `test_false_positives_are_marked_nosonar`: lee los tres archivos (UTF-8) desde la raíz del repo y, para cada línea que empieza por `PASSWORD_SCHEME = "pbkdf2_sha256"`, `MSG_PASSWORD_READ_FAILED = "No se pudo leer la contraseña."`, `MSG_PASSWORD_SHORT = "La contraseña no cumple la longitud mínima."`, `MSG_PASSWORD_MISMATCH = "Las contraseñas no coinciden."` o (tras `strip`) por `return f"http://{text}"`, comprueba que existe exactamente una y que contiene `# NOSONAR` seguido de texto no vacío. Cubre: R12.

## Cierre

- [x] T14 — Comprobar que `git diff --name-only` respecto al commit base de la feature solo lista: los siete archivos de aplicación de T1, T4, T7, T10 y T12; los cinco archivos de test de T2/T3, T5/T6, T8, T9, T11; el nuevo `scripts/tests/test_sonar_markers.py`; `specs/`, `progress/` y `feature_list.json`. En particular no aparecen `services/orchestrator/tests/test_advisor_commands.py`, `contracts/CONTRATOS.md`, `.env.example`, `docker-compose.yml` ni `render.yaml`, y el diff de los archivos de test existentes solo tiene líneas añadidas (salvo T9). Anotar el resultado en `progress/impl_correcciones_sonar.md`. Comprobación de cierre (no regresión); no cubre ningún `R<n>`.
- [x] T15 — Ejecutar `./init.sh` y dejarlo en verde; registrar el mapa de trazabilidad R1–R12 (tabla «Test que verifica cada requirement» de `requirements.md`) en `progress/impl_correcciones_sonar.md`, incluyendo los tests existentes que cubren el código de salida `0` (`test_r23_set_webhook_uses_public_url_and_secret`, `test_solo_consultar_only_calls_get_webhook_info`). Comprobación de cierre (no regresión); no cubre ningún `R<n>`.
