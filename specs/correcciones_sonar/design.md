# Design — #58 `correcciones_sonar`

Feature de mantenimiento: cambios locales, sin contratos, rutas, modelos,
variables de entorno ni dependencias nuevas. No se reutiliza código externo.

## Triaje de los 12 hallazgos

| Hallazgo | Ubicación | Veredicto | Acción |
|---|---|---|---|
| S8786 | `orchestrator/memory.py` L78 (`_EMAIL`, usos L90 y L109) | Real | Detección lineal sin regex |
| S8786 | `orchestrator/admin.py` L38 (`_EMAIL_RE`, uso L175) | Real | Redacción lineal sin regex |
| secrets:S6698 | `rag/config.py` L25 | Real | Valor por defecto `""` |
| S3516 | `scripts/configurar_webhook.py` `_network_error`, `_http_error` | Real | Devuelven `None` |
| S5863 | `rag/tests/test_adapters.py` L14 | Real | Dos variables |
| S2068 | `orchestrator/accounts.py` L9 | Falso positivo | `# NOSONAR` |
| S2068 | `orchestrator/bootstrap_admin.py` L20-22 | Falso positivo | `# NOSONAR` |
| S5332 | `contracts/lazaro_contracts/production.py` L40 | Falso positivo (#24) | `# NOSONAR` |
| S5863 | `orchestrator/tests/test_advisor_commands.py` L99 | Obsoleto | Ninguna: el archivo tiene 88 líneas |

Por qué las regex son un hallazgo real: con `search`/`sub`, `[^\s@]+@` reintenta
desde cada posición de un tramo largo sin `@`, lo que es cuadrático
(100000 caracteres ≈ 5·10⁹ pasos).

## Archivos a modificar

### `services/orchestrator/orchestrator/memory.py`

- Eliminar `_EMAIL`.
- Añadir la función pura:

  ```python
  def _contains_email(text: str) -> bool:
  ```

  Algoritmo (lineal): para cada palabra de `text.split()`, `parts =
  palabra.split("@")`; devuelve `True` si existe `k` con `parts[k]` no vacío y
  `"." in parts[k + 1][1:-1]`. En otro caso `False`.
- `is_sensitive` y `_is_sensitive_with` terminan con `return _contains_email(text)`.
- No se toca `_digits_pattern` (no está en el reporte). `import re` se conserva
  porque `_digits_pattern` lo usa.

### `services/orchestrator/orchestrator/admin.py`

- Eliminar `_EMAIL_RE`.
- Añadir la función pura:

  ```python
  def _redact_emails(text: str) -> str:
  ```

  Algoritmo (lineal): recorrer el texto separando palabras y espacios de modo
  que los espacios se copien tal cual (un recorrido carácter a carácter con
  `str.isspace()`, o `re.split(r"(\s+)", text)`, que es lineal). Por cada
  palabra, `parts = palabra.split("@")` e índice `i = 0`:
  - si `parts[i]` y `parts[i + 1]` existen y no son vacíos: emitir `REDACTED`
    y avanzar `i += 2`;
  - si no: emitir `parts[i]` y avanzar `i += 1`;
  - tras cada emisión, si quedan partes, emitir `"@"`.

  Ejemplos: `a@b@c` → `[redactado]@c`; `a@b@c@d` → `[redactado]@[redactado]`;
  `@b`, `a@`, `a@@b` no cambian.
- `redact_reason` usa `_redact_emails(reason)` como primer paso; el orden con
  `_LONG_DIGITS_RE` y `_LONG_TOKEN_RE` no cambia.

### `services/rag/rag/config.py`

- `database_url: str = ""` (igual que handover L32 y orchestrator L97).
- `REQUIRED_IN_PRODUCTION` y `_validate_production` no se tocan:
  `production_problems` ya rechaza el valor vacío y el marcador
  `lazaro:lazaro@`.

### `scripts/configurar_webhook.py`

- `_network_error(exc) -> None` y `_http_error(action, response) -> None`: solo
  imprimen en `stderr`, sin `return 1`.
- Los cuatro puntos de llamada en `main` pasan a ser dos sentencias: llamar a la
  función y después `return 1`. Los mensajes y los códigos `0`/`1`/`2` no
  cambian.

### `services/rag/tests/test_adapters.py`

- `test_fake_embeddings_is_deterministic`: `first = FakeEmbeddings().embed(["hola mundo"])`,
  `second = FakeEmbeddings().embed(["hola mundo"])`, `assert first == second`.
  Se puede añadir `assert first and first[0]`; no se quita nada.

### Marcas `# NOSONAR` (solo se añade el comentario al final de la línea)

| Archivo | Línea | Comentario sugerido |
|---|---|---|
| `orchestrator/accounts.py` | `PASSWORD_SCHEME = "pbkdf2_sha256"` | `# NOSONAR: nombre de algoritmo, no credencial` |
| `orchestrator/bootstrap_admin.py` | `MSG_PASSWORD_READ_FAILED`, `MSG_PASSWORD_SHORT`, `MSG_PASSWORD_MISMATCH` | `# NOSONAR: mensaje al usuario, no credencial` |
| `contracts/lazaro_contracts/production.py` | `return f"http://{text}"` | `# NOSONAR: red privada entre servicios (#24)` |

`contracts/CONTRATOS.md` no se toca: el cambio en `production.py` es un
comentario.

## Tests existentes afectados (comprobado en el código)

**Regex de correo.** Solo tres tests ejercitan hoy la detección, todos con
`ana@example.com`, y deben seguir pasando sin editarse:

- `services/orchestrator/tests/test_memory.py::test_r15_r16_sensitive_detection_covers_keywords_digits_and_email`
  (caso `"escribe a ana@example.com"`).
- `services/orchestrator/tests/test_admin.py::test_events_are_recent_first_short_and_redacted`.
- `services/orchestrator/tests/test_admin.py::test_redact_reason_and_short_id_are_pure`
  (exige exactamente 3 `[redactado]`).

Ningún test importa `_EMAIL` ni `_EMAIL_RE`.

**`database_url` por defecto de rag.** Ningún test depende del valor por defecto:

- `services/rag/tests/conftest.py::build_env`, `test_search.py` y
  `test_search_hybrid.py` inyectan `FakeChunkRepository`; el DSN no se usa.
- `test_rag_app.py::test_create_app_returns_fastapi`,
  `::test_module_exposes_fastapi_app` y
  `::test_empty_configured_token_rejects_everything` construyen
  `PgVectorChunkRepository` real, pero es perezoso (conecta en el primer uso) y
  esos tests no llegan a usarlo.
- `test_search_hybrid.py::test_default_flag_is_off_and_candidate_limit_is_50` y
  `test_rag_app.py::test_settings_reads_service_token_from_env` llaman a
  `Settings()` y solo miran otros campos.
- `test_production_config.py` pasa siempre `database_url` explícito.

Desarrollo local: `.env.example` L19 ya define
`DATABASE_URL=postgresql://lazaro:lazaro@postgres:5432/lazaro` y
`docker-compose.yml` carga `.env` en todos los servicios, así que el arranque no
cambia. Sin `.env`, rag arranca igual y la conexión falla en el primer uso por
las rutas de error existentes (antes fallaba igual salvo que hubiera un host
`postgres`).

**`configurar_webhook.py`.** `scripts/tests/test_configurar_webhook.py` solo
afirma `== 0` o `!= 0` y no llama a `_network_error` ni `_http_error`
directamente; sigue pasando sin editarse.

## Tests nuevos

Se añaden al final de archivos existentes, salvo el de marcas:

- `services/orchestrator/tests/test_memory.py` — equivalencia y tiempo (R1, R3, R4).
- `services/orchestrator/tests/test_admin.py` — equivalencia y tiempo (R2, R3, R4).
- `services/rag/tests/test_production_config.py` — valor por defecto y producción (R5, R6, R7).
- `scripts/tests/test_configurar_webhook.py` — `None` y códigos exactos (R8, R9, R10).
- `scripts/tests/test_sonar_markers.py` (nuevo) — lee los tres archivos fuente
  por ruta desde la raíz, como hace `test_configurar_webhook.py`, y comprueba la
  marca (R12).

La medición de R3 usa `time.perf_counter()` con umbral de 2 s: la versión lineal
tarda milisegundos y la cuadrática decenas de segundos, así que el margen evita
falsos fallos en CI.

El hallazgo obsoleto de `test_advisor_commands.py` no es un requirement: queda
documentado en la tabla de triaje de arriba y el archivo no se modifica. La no
regresión (sin cambios de contrato, tests existentes intactos, `./init.sh` en
verde) tampoco es un requirement: es la regla de cierre de `tasks.md` (T14 y
T15). Los requirements de la feature son R1–R12 y todos tienen test.

## Excepciones

No se añade ninguna. Se reutiliza `ProductionConfigError` sin cambios.

## Alternativas descartadas

- **Mantener regex con anclaje `(?<![^\s@])`** (empezar solo al inicio de un
  tramo). Es lineal y equivalente, pero conserva cuantificadores adyacentes
  sobre la misma clase de caracteres, el analizador puede volver a marcarla y es
  más difícil de razonar que dos `split`. El acceptance pide «sin
  cuantificadores solapados».
- **Acotar longitudes (`{1,64}`) o truncar la entrada.** Cambia los resultados
  actuales en textos largos; el acceptance exige conservarlos.
- **Renombrar `PASSWORD_SCHEME` / `MSG_PASSWORD_*`.** Prohibido por el
  acceptance; además los tests importan esos nombres.
- **Hacer que `_network_error` devuelva códigos distintos según el error.**
  Cambiaría los códigos de salida observables.

## Fuera de alcance

- `eval/scoring.py` L30 tiene la misma regex de correo, pero no figura en el
  reporte ni en el acceptance. No se toca; queda anotado para el leader.
- `_digits_pattern`, `_LONG_DIGITS_RE` y `_LONG_TOKEN_RE` no están en el reporte.

## Dependencias nuevas

Ninguna.

## Supuestos a confirmar

Ninguno: la feature no toca dudas abiertas de `docs/proyecto.md` §12 ni añade
variables de entorno. El umbral de 2 s de R3 es una constante del test.
