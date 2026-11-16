# Review — feature 58 `correcciones_sonar`

**Veredicto:** APPROVED

## Verificación ejecutada por el reviewer

- `./init.sh` no se volvió a ejecutar (indicación del leader): el informe
  `progress/impl_correcciones_sonar.md` registra el intento 2 en verde
  (`3624 passed, 1 skipped`, salida `0`). Ese informe (18:45) es posterior a la
  última modificación de cualquier archivo del diff (el más reciente,
  `services/orchestrator/tests/test_admin.py`, 18:37), así que el verde
  corresponde al estado revisado.
- Tests de los archivos tocados, ejecutados ahora:
  - `services/orchestrator/tests/test_memory.py` + `test_admin.py`: 99 passed.
  - `services/rag/tests/test_adapters.py` + `test_production_config.py`: 22 passed.
  - `scripts/tests/test_configurar_webhook.py` + `test_sonar_markers.py`: 29 passed.
- Equivalencia con las regex anteriores: comparación aleatoria de 400000
  cadenas (alfabeto con `@`, `.`, letras, dígitos y espacios ASCII y Unicode,
  incluidos `\x1c`, `\x1f`, `\x85`, ` `, ` `, `​`) entre
  `_contains_email` y `[^\s@]+@[^\s@]+\.[^\s@]+` con `search`, y entre
  `_redact_emails` y `[^\s@]+@[^\s@]+` con `sub`: 0 diferencias.
- Tiempo lineal: medido con 100000, 400000 y 1600000 caracteres sobre las
  cuatro entradas adversarias y dos más (`"a.@"` repetido y muchas palabras). El
  tiempo crece en proporción al tamaño (peor caso, `"@" * 1600000` en
  `_redact_emails`: 1,36 s; con 100000: 0,09 s). Sin crecimiento cuadrático.

## Trazabilidad requirements ↔ tests

- R1: [x] `services/orchestrator/tests/test_memory.py::test_email_detection_matches_previous_regex` (11 casos)
- R2: [x] `services/orchestrator/tests/test_admin.py::test_redact_reason_matches_previous_email_regex` (10 casos)
- R3: [x] `test_memory.py::test_email_detection_is_linear_on_adversarial_input` y `test_admin.py::test_redact_reason_is_linear_on_adversarial_input` (las cuatro entradas del spec, umbral 2 s)
- R4: [x] `test_memory.py::test_memory_has_no_email_regex`, `test_admin.py::test_admin_has_no_email_regex`
- R5: [x] `services/rag/tests/test_production_config.py::test_database_url_defaults_to_empty`
- R6: [x] `test_production_config.py::test_create_app_without_database_url_does_not_connect`
- R7: [x] `test_production_config.py::test_production_without_database_url_is_rejected` y el existente `::test_development_database_credentials_are_rejected` (sin editar)
- R8: [x] `scripts/tests/test_configurar_webhook.py::test_error_helpers_return_none`
- R9: [x] `test_configurar_webhook.py::test_http_error_exits_with_one`, `::test_network_error_exits_with_one`
- R10: [x] `test_configurar_webhook.py::test_config_errors_exit_with_two` (3 casos, cero llamadas)
- R11: [x] `services/rag/tests/test_adapters.py::test_fake_embeddings_is_deterministic`
- R12: [x] `scripts/tests/test_sonar_markers.py::test_false_positives_are_marked_nosonar` (5 líneas)

## Tasks completas

- T1–T13: [x]
- T14: [x] alcance del diff comprobado de nuevo (ver abajo)
- T15: [x] `./init.sh` verde registrado en el informe

## Comprobaciones pedidas

- **Correos (memory.py L78-84, admin.py L172-189):** lineales y equivalentes
  (ver verificación). `_EMAIL` y `_EMAIL_RE` ya no existen; `_digits_pattern`,
  `_LONG_DIGITS_RE` y `_LONG_TOKEN_RE` intactos; el orden de pasos de
  `redact_reason` no cambia. `re.split(r"(\s+)", ...)` en admin.py es un
  separador lineal, permitido por `design.md`; R4 prohíbe la regex para
  detectar correos, no para separar espacios.
- **`database_url` de rag (config.py L25):** queda `""`. El diff de `config.py`
  es solo esa línea: `REQUIRED_IN_PRODUCTION` y el validador no se tocan, y
  producción sigue rechazando tanto el valor vacío como `lazaro:lazaro@`.
- **`scripts/configurar_webhook.py`:** los dos helpers devuelven `None`; los
  cuatro puntos de llamada pasan a llamada + `return 1`. Textos de los mensajes
  sin cambios; códigos `0`/`1`/`2` iguales.
- **`# NOSONAR`:** las cinco líneas llevan justificación tras `# NOSONAR:`; solo
  se añadió el comentario, sin cambiar nombre ni valor.
- **Contratos, rutas, modelos, variables de entorno, dependencias:** sin
  cambios. `contracts/CONTRATOS.md`, `.env.example`, `docker-compose.yml`,
  `render.yaml` y los `requirements.txt` no aparecen en el diff; el cambio en
  `contracts/lazaro_contracts/production.py` es un comentario.
- **Tests existentes:** `git diff --numstat` da 0 líneas borradas en
  `test_memory.py`, `test_admin.py`, `test_production_config.py` y
  `test_configurar_webhook.py`. `test_adapters.py` (+4/−1) es la excepción T9 y
  refuerza la aserción (`assert first and first[0]`).
- **Alcance:** 7 archivos de aplicación, 5 de test existentes, el nuevo
  `scripts/tests/test_sonar_markers.py`, y `specs/`, `progress/`,
  `feature_list.json`. `test_advisor_commands.py` no se tocó.

## Checkpoints

- C1: [x] (verde de `./init.sh` según el informe, no reejecutado)
- C2: [x] solo la #58 en `in_progress`
- C3: [x]
- C4: [x]
- C5: [x] sin archivos sospechosos sin trackear; la entrada de
  `progress/history.md` corresponde al cierre de sesión, que aún no ha ocurrido
- C6: [x]

## Observaciones no bloqueantes

1. `progress/current.md` dice «R1–R14» en la línea del spec; el spec final tiene
   R1–R12. Es una nota de sesión del leader, conviene corregirla al cerrar.
2. `eval/scoring.py` L30 conserva la misma regex de correo. Está fuera del
   alcance por `design.md`; queda pendiente de decisión del leader.
3. `test_production_without_database_url_is_rejected` espera `ValidationError`
   (que envuelve a `ProductionConfigError`) y comprueba el texto
   `Configuración de producción inválida: DATABASE_URL`; es el mismo patrón que
   usan los tests existentes de ese archivo.

## Cambios requeridos

Ninguno.
