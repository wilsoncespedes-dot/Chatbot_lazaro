# #23 bootstrap_administrador — Design

## Archivos
- **Nuevo** `services/orchestrator/orchestrator/bootstrap_admin.py` — comando.
  Va dentro del paquete para que la imagen Docker ya lo incluya:
  `docker compose exec orchestrator python -m orchestrator.bootstrap_admin --username admin`.
- **Nuevo** `services/orchestrator/tests/test_bootstrap_admin.py`.
- **Modificar** `README.md` — sección breve "Primer administrador" con el uso.
- Sin cambios en `Repository`, esquema, `config.py`, `.env.example`,
  `contracts/` ni rutas HTTP.

## Firmas
```python
EXIT_OK, EXIT_ADMIN_EXISTS, EXIT_INVALID = 0, 1, 2

def run(
    argv: list[str],
    *,
    settings: Settings,
    repository: Repository | None = None,          # None → PostgresRepository(settings.database_url)
    prompt_password: Callable[[str], str] = getpass.getpass,
    out: TextIO = sys.stdout,
    err: TextIO = sys.stderr,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> int: ...

def main() -> None:  # sys.exit(run(sys.argv[1:], settings=Settings()))
```

## Flujo de `run`
1. `argparse` con un único argumento requerido `--username`; argumentos
   desconocidos (incl. `--password`) → `parser.error` → código 2 (R4). Se
   captura `SystemExit` para devolver el código en vez de salir.
2. Validar `username.lower()` con `USERNAME_PATTERN` → 2 (R7).
3. Si `repository is None` y `settings.database_url == ""` → 2 (R9); si no,
   construir `PostgresRepository`.
4. `any(p.role == "admin" for p in repository.list_profiles())` → mensaje
   fijo en `err`, código 1, sin llamar a `prompt_password` (R6).
5. `prompt_password("Contraseña: ")` y `prompt_password("Repite la contraseña: ")`;
   distinta o `len < profile_password_min_length` → 2 (R7).
6. `repository.create_profile(username.lower(), "admin",
   hash_password(password, settings.password_hash_iterations), clock())` —
   misma lógica que `domain.create_profile`, sin construir `Adapters`
   completos (exige clientes RAG/LLM/gateway innecesarios aquí) (R1, R2).
7. `UsernameTaken` → mensaje fijo, código 2 (R8).
8. Éxito: imprimir en `out` solo `id` y `username`; código 0.
- Cualquier otra excepción del repositorio: mensaje fijo con
  `type(exc).__name__`, código 2; nunca se formatea la contraseña ni la URL (R5).
- La contraseña solo vive en variables locales; nunca se pasa a `logging`,
  `print` ni mensajes de excepción (R5).

## Excepciones
Reutiliza `UsernameTaken` de `domain.py`. No se añaden nuevas.

## Alternativas descartadas
- **Endpoint `POST /bootstrap`** o credenciales por defecto: superficie
  pública explotable en instalaciones recién desplegadas (R10).
- **Contraseña por argumento o variable de entorno**: queda en historial de
  shell, `ps` y entorno del contenedor (R3, R4).
- **Comprobación + inserción atómica en SQL** (`INSERT … WHERE NOT EXISTS
  admin`): exige método/esquema nuevo en `Repository`. Se acepta la ventana
  check-then-insert porque el comando es manual, de un solo uso y lo ejecuta
  un operador con acceso a la base.

## Dependencias
Ninguna nueva (`argparse`, `getpass` de la stdlib).

## Supuestos
- No toca dudas abiertas de `docs/proyecto.md` §12; sin variables nuevas.
