# Review — feature 23 (bootstrap_administrador)

**Veredicto:** APPROVED

`./init.sh` → exit 0, 1416 passed (re-ejecutado por el reviewer).

## Trazabilidad requirements ↔ tests
(todos en `services/orchestrator/tests/test_bootstrap_admin.py`)
- R1: [x] `test_bootstrap_creates_single_admin_with_hashed_password` (código 0, un perfil, `role="admin"`)
- R2: [x] mismo test: prefijo `pbkdf2_sha256$100000$`, `verify_password` True, hash ≠ clave
- R3: [x] `test_password_is_read_twice_with_getpass_by_default` (dos prompts; default `getpass.getpass`)
- R4: [x] `test_password_option_is_rejected_without_creating_or_leaking` (código 2, sin perfiles, sin prompt) y `test_environment_variable_is_never_used_as_password`
- R5: [x] `test_success_does_not_expose_password_in_out_err_or_logs`, `test_mismatch_and_short_password_do_not_expose_password`, `test_repository_error_does_not_expose_password` (la excepción lleva la clave en su mensaje y no se filtra), más asserts en R4/R6
- R6: [x] `test_existing_admin_exits_without_prompting_or_changing_data` (código 1, prompt no llamado, `profiles` idéntico vía deepcopy)
- R7: [x] `test_invalid_username_exits_without_profiles` (5 casos), `test_short_password_exits_without_profiles`, `test_mismatched_passwords_exit_without_profiles`
- R8: [x] `test_username_taken_leaves_existing_profile_intact` (asesor intacto, hash y rol sin cambios)
- R9: [x] `test_missing_database_url_exits_without_connecting` (monkeypatch de `PostgresRepository` que falla si se instancia)
- R10: [x] `test_app_exposes_no_bootstrap_route`

## Tasks completas
- T1–T9: [x] (todas marcadas en `specs/bootstrap_administrador/tasks.md`; verificadas en código/tests/README)
- T9: `README.md:60-71` sección «Primer administrador» con `docker compose exec orchestrator python -m orchestrator.bootstrap_admin --username <nombre>`.

## Seguridad contraseña / comando
- Solo `--username` en argparse (`bootstrap_admin.py:37`); `_BootstrapParser.error` (`:29-32`) no imprime el mensaje de argparse, así que `--password <valor>` o posicionales extra no se reflejan en stderr; se imprime `MSG_USAGE` fijo.
- No hay lectura de `os.environ` para la clave; no hay `logging` en el módulo.
- Comprobación de admin (`:79`) antes de pedir la clave (`:84`), conforme a R6.
- `EOFError`/`KeyboardInterrupt` en getpass → mensaje fijo, código 2 (`:86-87`).
- Errores de repositorio exponen solo `type(exc).__name__` (`:77`, `:99`); nunca mensaje ni URL.
- Éxito imprime solo `id` y `username` (`:101`).
- Sin ruta HTTP nueva ni credenciales por defecto; sin cambios en `.env.example`, contratos ni dependencias.

## Observaciones no bloqueantes
1. `-h/--help` lo gestiona argparse: imprime en `sys.stdout` (no en `out`) y devuelve 0 sin crear nada. Inocuo.
2. `PostgresRepository(...)` (`:72`) queda fuera del `try`; hoy es inocuo porque la conexión es perezosa (`repository.py:366`) y los fallos de conexión ocurren dentro de `list_profiles`, que sí está protegido.
3. Ventana check-then-insert aceptada explícitamente en design.md (alternativa descartada); el impl lo documenta.

## Checkpoints
- C1: [x] archivos base y docs presentes; `./init.sh` exit 0.
- C2: [x] una sola feature `in_progress` (#23); estado coherente.
- C3: [x] código dentro de `services/orchestrator/orchestrator/`; sin imports entre servicios; sin rutas nuevas; sin dependencias nuevas (stdlib); `.env` no trackeado; el único `print` es salida del CLI, no debug; sin SQL nuevo.
- C4: [x] tests con `FakeRepository`/prompt falso, sin DB real; suite verde.
- C5: [x] (a cerrar por el leader en `progress/history.md` al marcar done).
- C6: [x] specs completos, EARS, tasks `[x]`, R1–R10 cubiertos.
