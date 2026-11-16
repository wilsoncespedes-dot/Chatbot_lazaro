# Implementación — #58 `correcciones_sonar`

## Resumen

- `orchestrator/memory.py`: eliminada `_EMAIL`; nueva `_contains_email` lineal usada
  por `is_sensitive` y `_is_sensitive_with` (R1, R4).
- `orchestrator/admin.py`: eliminada `_EMAIL_RE`; nueva `_redact_emails` lineal usada
  como primer paso de `redact_reason` (R2, R4).
- `rag/config.py`: `database_url` por defecto `""`; no se tocaron
  `REQUIRED_IN_PRODUCTION` ni el validador (R5, R7).
- `scripts/configurar_webhook.py`: `_network_error` y `_http_error` devuelven `None`;
  `main` conserva los códigos 0/1/2 y los mensajes (R8, R9, R10).
- `rag/tests/test_adapters.py`: `test_fake_embeddings_is_deterministic` usa dos
  variables de dos instancias distintas (R11).
- Marcas `# NOSONAR` justificadas en `accounts.py`, `bootstrap_admin.py` (×3) y
  `contracts/lazaro_contracts/production.py` (R12).
- El hallazgo S5863 de `services/orchestrator/tests/test_advisor_commands.py` L99 no
  se toca: es obsoleto (el archivo tiene 88 líneas), documentado en `design.md`.

## Trazabilidad

- R1 → `services/orchestrator/tests/test_memory.py::test_email_detection_matches_previous_regex`
- R2 → `services/orchestrator/tests/test_admin.py::test_redact_reason_matches_previous_email_regex`
- R3 → `services/orchestrator/tests/test_memory.py::test_email_detection_is_linear_on_adversarial_input`,
  `services/orchestrator/tests/test_admin.py::test_redact_reason_is_linear_on_adversarial_input`
- R4 → `services/orchestrator/tests/test_memory.py::test_memory_has_no_email_regex`,
  `services/orchestrator/tests/test_admin.py::test_admin_has_no_email_regex`
- R5 → `services/rag/tests/test_production_config.py::test_database_url_defaults_to_empty`
- R6 → `services/rag/tests/test_production_config.py::test_create_app_without_database_url_does_not_connect`
- R7 → `services/rag/tests/test_production_config.py::test_production_without_database_url_is_rejected`
  y el existente `::test_development_database_credentials_are_rejected`
- R8 → `scripts/tests/test_configurar_webhook.py::test_error_helpers_return_none`
- R9 → `scripts/tests/test_configurar_webhook.py::test_http_error_exits_with_one`,
  `scripts/tests/test_configurar_webhook.py::test_network_error_exits_with_one`
- R10 → `scripts/tests/test_configurar_webhook.py::test_config_errors_exit_with_two`
- R11 → `services/rag/tests/test_adapters.py::test_fake_embeddings_is_deterministic`
- R12 → `scripts/tests/test_sonar_markers.py::test_false_positives_are_marked_nosonar`

## Cierre pendiente para Claude (no lo ejecuta el writer)

- T14: comprobar la lista de `git diff --name-only` respecto al commit base de la
  feature (solo archivos de aplicación, tests, `specs/`, `progress/` y
  `feature_list.json`).
- T15: ejecutar `./init.sh` y dejarlo verde. Tests que cubren el código de salida
  `0` del webhook y que no se editan:
  `test_configurar_webhook.py::test_r23_set_webhook_uses_public_url_and_secret`,
  `::test_solo_consultar_only_calls_get_webhook_info`.

## Intento 1 de `./init.sh` — FALLA (corrección pedida al writer)

Resultado: `3616 passed, 1 skipped, 2 warnings, 16 errors in 319.72s`, salida `1`.

Los 16 errores son de setup/teardown (no de aserción) y vienen solo de dos tests
nuevos, 4 parámetros × 2 fases cada uno:

- `services/orchestrator/tests/test_memory.py::test_email_detection_is_linear_on_adversarial_input`
- `services/orchestrator/tests/test_admin.py::test_redact_reason_is_linear_on_adversarial_input`

Error:

```text
.venv\Lib\site-packages\_pytest\runner.py:209: in _update_current_test_var
    os.environ[var_name] = value
E   ValueError: the environment variable is longer than 32767 characters
```

Causa: `pytest.mark.parametrize` usa la cadena adversaria de 100000 caracteres
como id del test; pytest escribe ese id en `PYTEST_CURRENT_TEST` y Windows no
admite variables de entorno de más de 32767 caracteres.

Corrección pedida (solo en esos dos tests, sin tocar código de aplicación ni
ningún otro test):

- Dar ids cortos y explícitos a los cuatro parámetros en ambos tests, por
  ejemplo `ids=["solo_a", "a_arroba_b", "solo_arrobas", "a_arroba_repetido"]`
  (o `pytest.param(..., id=...)`).
- Las cuatro entradas siguen siendo exactamente `"a" * 100000`,
  `"a@" + "b" * 100000`, `"@" * 100000`, `"a@" * 50000`; el umbral de 2 s y las
  aserciones no cambian.
- Revisar que ningún otro `parametrize` nuevo de esta feature genere ids de
  longitud excesiva.

## Corrección aplicada (intento 2)

- `services/orchestrator/tests/test_memory.py::test_email_detection_is_linear_on_adversarial_input`
  y `services/orchestrator/tests/test_admin.py::test_redact_reason_is_linear_on_adversarial_input`
  reciben `ids=["solo_a", "a_arroba_b", "solo_arrobas", "a_arroba_repetido"]`.
  Las cuatro entradas, el umbral de 2 s y las aserciones no cambiaron.
- Revisados los demás `parametrize` nuevos de la feature: sus parámetros son
  cadenas cortas, así que no generan ids por encima del límite de Windows.
- Sin cambios en código de aplicación ni en ningún otro test.

## Resultado final de `./init.sh` (intento 2) — VERDE

`3624 passed, 1 skipped, 2 warnings in 314.69s`, salida `0` («Todos los tests
pasan»). Un solo ciclo de corrección (ids de `parametrize`).

## T14 — alcance del diff (base `70bd93b`)

`git status --short` lista únicamente:

- Aplicación (7): `services/orchestrator/orchestrator/memory.py`, `admin.py`,
  `accounts.py`, `bootstrap_admin.py`, `services/rag/rag/config.py`,
  `scripts/configurar_webhook.py`, `contracts/lazaro_contracts/production.py`.
- Tests existentes (5): `services/orchestrator/tests/test_memory.py` (+42/−0),
  `test_admin.py` (+41/−0), `services/rag/tests/test_production_config.py`
  (+34/−0), `scripts/tests/test_configurar_webhook.py` (+65/−0),
  `services/rag/tests/test_adapters.py` (+4/−1, la excepción de T9).
- Nuevo: `scripts/tests/test_sonar_markers.py`.
- Arnés: `specs/`, `progress/`, `feature_list.json` (#58 sigue `in_progress`;
  el writer no lo tocó).

No aparecen `services/orchestrator/tests/test_advisor_commands.py`,
`contracts/CONTRATOS.md`, `.env.example`, `docker-compose.yml` ni `render.yaml`.
Ningún test existente se eliminó ni se debilitó.

## T15 — trazabilidad

El mapa R1–R12 → test de la sección «Trazabilidad» queda confirmado: todos los
tests citados existen y pasan. El código de salida `0` del webhook lo cubren los
tests existentes, sin editar, `test_r23_set_webhook_uses_public_url_and_secret`
y `test_solo_consultar_only_calls_get_webhook_info`.

Tasks T1–T15 en `[x]`. Pendiente: revisión de código. La feature no se marca
`done` en esta fase.
