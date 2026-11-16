# Requirements — #58 `correcciones_sonar`

Corrige los hallazgos reales del reporte de Sonar del 2026-11-15 y deja
justificados los falsos positivos. No cambia contratos, rutas, modelos ni
variables de entorno. El triaje del `acceptance` es vinculante.

Definiciones usadas abajo:

- **Espacio**: carácter para el que `str.isspace()` es verdadero (lo mismo que
  `\s` en las regex actuales).
- **Tramo**: secuencia máxima de caracteres que no son espacio ni `@`.
- **Entrada adversaria**: cada una de estas cadenas de 100000 caracteres o más:
  `"a" * 100000`, `"a@" + "b" * 100000`, `"@" * 100000`, `"a@" * 50000`.

## Orquestador — detección de correos (S8786)

### R1
CUANDO `is_sensitive` o `clean_memory_items` (`orchestrator/memory.py`) evalúan
un texto, el orquestador DEBE tratarlo como correo exactamente en los mismos
casos que la regex actual `[^\s@]+@[^\s@]+\.[^\s@]+` con `search`: existe un
`@` precedido por un tramo no vacío y seguido por un tramo que contiene un `.`
que no es ni su primer ni su último carácter.

### R2
CUANDO `redact_reason` (`orchestrator/admin.py`) recibe un texto, el
orquestador DEBE devolver el mismo resultado que la sustitución actual de
`[^\s@]+@[^\s@]+` por `[redactado]`: de izquierda a derecha y sin solapes, cada
secuencia `tramo@tramo` (ambos tramos completos y no vacíos) se reemplaza por
`[redactado]`, y el resto del texto, incluidos los espacios, se conserva.

### R3
SI `is_sensitive` o `redact_reason` reciben una entrada adversaria ENTONCES el
orquestador DEBE completar cada llamada en menos de 2 segundos.

### R4
El orquestador NO DEBE detectar correos en `memory.py` ni en `admin.py` con una
expresión regular: los nombres `_EMAIL` y `_EMAIL_RE` dejan de existir en esos
módulos.

## Rag — DSN por defecto (secrets:S6698)

### R5
MIENTRAS la variable de entorno `DATABASE_URL` no está definida, `Settings` del
servicio rag DEBE exponer `database_url == ""`.

### R6
MIENTRAS `DATABASE_URL` no está definida y `APP_ENV` es `development`, el
servicio rag DEBE construir la aplicación con `create_app()` sin abrir ninguna
conexión a la base de datos.

### R7
SI `APP_ENV` es `production` y `database_url` queda vacío o contiene
`lazaro:lazaro@` ENTONCES el servicio rag DEBE lanzar `ProductionConfigError`
nombrando `DATABASE_URL`.

## Script `scripts/configurar_webhook.py` (S3516)

### R8
Las funciones `_network_error` y `_http_error` DEBEN limitarse a escribir su
mensaje en `stderr` y devolver `None`.

### R9
SI Telegram responde sin éxito o la llamada falla por red ENTONCES `main` DEBE
devolver `1` y escribir en `stderr` el mismo mensaje que hoy
(`<acción> falló: Telegram respondió con código <status>` o
`Error de red al llamar a Telegram: <NombreDeExcepción>`).

### R10
SI falta una variable obligatoria, `PUBLIC_BASE_URL` no empieza por `https://` o
`TELEGRAM_WEBHOOK_SECRET` no cumple el formato ENTONCES `main` DEBE devolver `2`
sin llamar a Telegram.

## Tests de rag (S5863)

### R11
El test `test_fake_embeddings_is_deterministic`
(`services/rag/tests/test_adapters.py`) DEBE guardar en dos variables distintas
los vectores de dos instancias distintas de `FakeEmbeddings` para el mismo texto
y afirmar su igualdad.

## Falsos positivos (S2068, S5332)

### R12
Las líneas que definen `PASSWORD_SCHEME` (`orchestrator/accounts.py`),
`MSG_PASSWORD_READ_FAILED`, `MSG_PASSWORD_SHORT` y `MSG_PASSWORD_MISMATCH`
(`orchestrator/bootstrap_admin.py`) y la línea `return f"http://{text}"` de
`normalize_service_url` (`contracts/lazaro_contracts/production.py`) DEBEN
terminar con un comentario `# NOSONAR` seguido de una justificación breve, sin
cambiar el nombre ni el valor.

## Hallazgo obsoleto y no regresión (sin requirement)

Estos dos criterios del acceptance no describen un comportamiento del sistema,
así que no llevan `R<n>`:

- El hallazgo S5863 de `services/orchestrator/tests/test_advisor_commands.py`
  L99 es obsoleto (el archivo tiene 88 líneas desde la #48). Queda documentado
  en la tabla de triaje de `design.md`; el archivo no se modifica.
- La no regresión (sin cambios de contrato, tests existentes intactos,
  `./init.sh` en verde) es una regla de cierre de `tasks.md` (T14 y T15).

## Cobertura del acceptance

| Criterio del acceptance | Cobertura |
|---|---|
| S8786 regex de correo | R1, R2, R3, R4 |
| secrets:S6698 DSN por defecto de rag | R5, R6, R7 |
| S3516 `configurar_webhook.py` | R8, R9, R10 (código `0`: tests existentes, que no se editan) |
| S5863 `test_adapters.py` | R11 |
| Falsos positivos S2068 / S5332 | R12 |
| S5863 obsoleto en `test_advisor_commands.py` | Sin `R<n>`: tabla de triaje de `design.md` |
| Sin cambios de contrato; tests intactos; `./init.sh` verde | Sin `R<n>`: regla de cierre en `tasks.md` (T14, T15) |

## Test que verifica cada requirement

| Requirement | Test (archivo → task) |
|---|---|
| R1 | `services/orchestrator/tests/test_memory.py::test_email_detection_matches_previous_regex` (T2) |
| R2 | `services/orchestrator/tests/test_admin.py::test_redact_reason_matches_previous_email_regex` (T5) |
| R3 | `test_memory.py::test_email_detection_is_linear_on_adversarial_input` (T3), `test_admin.py::test_redact_reason_is_linear_on_adversarial_input` (T6) |
| R4 | `test_memory.py::test_memory_has_no_email_regex` (T3), `test_admin.py::test_admin_has_no_email_regex` (T6) |
| R5 | `services/rag/tests/test_production_config.py::test_database_url_defaults_to_empty` (T8) |
| R6 | `test_production_config.py::test_create_app_without_database_url_does_not_connect` (T8) |
| R7 | `test_production_config.py::test_production_without_database_url_is_rejected` (T8) y el existente `test_development_database_credentials_are_rejected` |
| R8 | `scripts/tests/test_configurar_webhook.py::test_error_helpers_return_none` (T11) |
| R9 | `test_configurar_webhook.py::test_http_error_exits_with_one`, `::test_network_error_exits_with_one` (T11) |
| R10 | `test_configurar_webhook.py::test_config_errors_exit_with_two` (T11) |
| R11 | `services/rag/tests/test_adapters.py::test_fake_embeddings_is_deterministic` (T9) |
| R12 | `scripts/tests/test_sonar_markers.py::test_false_positives_are_marked_nosonar` (T13) |
