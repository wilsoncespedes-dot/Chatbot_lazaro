# #23 bootstrap_administrador — Tasks

- [x] T1 — Crear `services/orchestrator/orchestrator/bootstrap_admin.py` con `run(...)` y `main()` según design (argparse solo `--username`, validación, comprobación de admin antes de pedir clave, doble `getpass`, `hash_password`, `create_profile`, códigos 0/1/2, mensajes fijos). Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9.
- [x] T2 — `tests/test_bootstrap_admin.py`: instalación vacía con `FakeRepository` → código 0, un perfil `admin`, hash `pbkdf2_sha256$<PASSWORD_HASH_ITERATIONS>$…` y `verify_password` True. Cubre: R1, R2.
- [x] T3 — Test: `prompt_password` falso registra dos llamadas; `--password x` → código 2 y sin perfiles; una variable de entorno con la clave no se usa (monkeypatch env + prompt distinto → hash verifica la del prompt). Cubre: R3, R4.
- [x] T4 — Test: la contraseña no aparece en `out`, `err` ni `caplog` en éxito, mismatch, clave corta y error del repositorio. Cubre: R5.
- [x] T5 — Test: con un admin previo → código 1, `prompt_password` no llamado, `profiles` idéntico antes/después (incluido el hash). Cubre: R6.
- [x] T6 — Tests: username inválido, clave corta, claves distintas → código 2 sin perfiles; username ya usado por un `asesor` → código 2 y perfil intacto. Cubre: R7, R8.
- [x] T7 — Test: `repository=None` y `DATABASE_URL` vacía → código 2 sin construir `PostgresRepository` (monkeypatch que falla si se instancia). Cubre: R9.
- [x] T8 — Test: ninguna ruta de `create_app(...)` contiene `bootstrap`. Cubre: R10.
- [x] T9 — Añadir sección "Primer administrador" en `README.md` con el comando `docker compose exec orchestrator python -m orchestrator.bootstrap_admin --username <nombre>`. Cubre: R1.
