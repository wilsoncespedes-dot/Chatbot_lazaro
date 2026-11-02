# Design — validacion_config_asesores

Solo toca `services/handover/` (y un comentario en `.env.example`). Sin cambios en `contracts/`,
en otros servicios ni en `docker-compose.yml`. **Sin dependencias nuevas**: se usa
`pydantic`/`pydantic-settings`, ya en `services/handover/requirements.txt` (`pydantic>=2.12`;
`hide_input_in_errors` existe en `ConfigDict` de esas versiones).

## Archivos

### `services/handover/handover/config.py` (modificar)

- Nueva función pública pura:

  ```python
  def parse_advisor_chat_ids(raw: str) -> list[int]:
      """Ids de ADVISOR_CHAT_IDS en orden; lanza ValueError si una entrada no es válida."""
  ```

  Un solo recorrido de izquierda a derecha sobre `raw.split(",")` con `enumerate(..., start=1)`:
  1. `entry = item.strip()`; si `entry == ""`, se ignora (R1, R2).
  2. Si `entry` no casa con `^-?[0-9]+$` → `ValueError` con posición y valor (R3, R4, S2).
  3. `value = int(entry)`; si ya se vio, `ValueError` con las dos posiciones (R5, R6, S3, S4).
  4. Se añade a la lista y se recuerda `value → posición`.
  Se informa del **primer** problema que aparezca en ese recorrido (sea no numérico o
  duplicado).

- Mensajes (texto en español, formato fijado para que los tests lo comprueben):
  - No numérico: `ADVISOR_CHAT_IDS: la entrada {pos} ('{entry}') no es un entero`
  - Duplicado: `ADVISOR_CHAT_IDS: la entrada {pos} repite el id de la entrada {first_pos}`

- `Settings`:
  - `model_config = SettingsConfigDict(extra="ignore", hide_input_in_errors=True)` (R8).
  - `@field_validator("advisor_chat_ids")` (modo `after`) que llama a
    `parse_advisor_chat_ids(value)` y devuelve `value` sin cambios. Los mensajes de error solo
  incluyen la entrada no válida (no numérico) o posiciones (duplicado), nunca otras entradas
  de la lista (R8). Pydantic convierte el
    `ValueError` en `pydantic.ValidationError` (R3, R5). Se aplica igual cuando el valor llega
    por variable de entorno o por argumento (`Settings(advisor_chat_ids=...)`, como hace
    `tests/conftest.py`).
  - La propiedad `advisor_ids -> list[int]` se conserva con la misma firma y devuelve
    `parse_advisor_chat_ids(self.advisor_chat_ids)`; ya no puede fallar porque el valor se
    validó al construir. Su docstring deja de decir «no numéricas se descartan».
  - El campo sigue siendo `advisor_chat_ids: str = ""`.

### `services/handover/handover/main.py` (modificar)

En `create_app`, justo después de `settings = settings or Settings()` (que ya propaga el
`ValidationError`, R9: nada cambia en esa línea) y antes de crear `FastAPI`:

```python
advisor_count = len(settings.advisor_ids)
logger.info("advisors_configured count=%d", advisor_count)           # R10
if advisor_count == 0:
    logger.warning("no_advisors_configured")                         # R11
```

No se registra ningún id (R13). Con la lista vacía `create_app` sigue igual y devuelve la app
(R12). `app = create_app()` a nivel de módulo hace que, con una configuración inválida,
`uvicorn handover.main:app` falle al importar y el servicio no arranque.

#### Logging del servicio (R15)

Problema (spec review, cambio 2): el `Dockerfile` arranca con `uvicorn handover.main:app` y
nadie configura el logging raíz. El `LOGGING_CONFIG` de uvicorn solo configura `uvicorn`,
`uvicorn.error` y `uvicorn.access`; la raíz queda sin handlers y en `WARNING`, así que el
`INFO` `advisors_configured` de R10 se descartaría y A4 solo se cumpliría bajo `caplog`.

Patrón existente en el repo: ninguno. Todos los servicios solo hacen
`logger = logging.getLogger(__name__)` (`docs/conventions.md`, «Estructura de cada módulo») y
no hay `basicConfig`, `dictConfig` ni `--log-config` en `services/`, Dockerfiles ni
`docker-compose.yml`. Nada lo contradice, así que se aplica la opción (a) del reviewer,
acotada al paquete `handover`:

```python
LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"

def configure_logging() -> None:
    """Hace visibles en stderr los registros INFO o superiores del paquete handover."""
    package_logger = logging.getLogger("handover")
    package_logger.setLevel(logging.INFO)
    if not package_logger.handlers and not logging.getLogger().handlers:
        handler = logging.StreamHandler()          # sys.stderr
        handler.setFormatter(logging.Formatter(LOG_FORMAT))
        package_logger.addHandler(handler)
```

Y al final de `main.py`:

```python
configure_logging()
app = create_app()
```

- Se llama a nivel de módulo, **antes** de `create_app()`, para que el registro de R10 del
  arranque real ya salga por stderr (R15).
- `setLevel(INFO)` en el logger `handover` es lo imprescindible: sin él el nivel efectivo es
  el `WARNING` de la raíz y el registro se descarta antes de llegar a ningún handler.
- Solo se añade un handler propio si ni `handover` ni la raíz tienen ya uno (idempotente: no
  duplica líneas si se importa dos veces ni si alguien configura la raíz, p. ej. pytest o un
  futuro `--log-config`). `propagate` queda en `True`, así que `caplog` sigue viendo los
  registros en los tests de R10-R13.
- No toca la raíz ni otros loggers: no se vuelven visibles los `INFO` de `httpx` u otras
  librerías. Hoy el paquete `handover` no emite ningún otro `INFO` (sus registros existentes
  son `error`/`warning`/`exception`), así que lo único nuevo en la salida es R10.
- No va dentro de `create_app` para no alterar el logging de quien construye la app en tests
  con `create_app(settings, adapters)`.

Prueba (R15): test con `subprocess.run([sys.executable, "-c", "import handover.main"], ...)`,
con `ADVISOR_CHAT_IDS="987654321,-1001234567890"`, `PYTHONPATH` igual al `sys.path` del test
(para que encuentre `handover` y `lazaro_contracts`) y el resto de variables vacías (todas
tienen valor por defecto y `build_default_adapters` no abre conexiones). Comprueba que el
proceso termina con código 0, que `stderr` contiene `advisors_configured count=2` y que no
contiene `987654321` ni `1001234567890` (ids largos para que no coincidan por azar con la
marca de tiempo del formato). Un proceso aparte es la única
forma fiable de probar «sin configuración previa»: dentro de pytest la raíz ya tiene handlers.

### `services/handover/handover/domain.py`

Sin cambios. `open_case` sigue recorriendo `settings.advisor_ids`; con lista vacía responde
`no_advisors` (R14, R8 de la #7).

### Tests

- `services/handover/tests/test_config.py` — cambio del test de R23 (ver abajo) y tests nuevos de
  R1-R8.
- `services/handover/tests/test_startup.py` (nuevo) — R9-R14 (`create_app` + `caplog`, con
  `FakeCaseRepository` y `FakeGatewayClient`, sin red) y R15 (subproceso local que importa
  `handover.main`, sin red).

### `.env.example` (modificar, solo comentario)

Encima de `ADVISOR_CHAT_IDS=` añadir un comentario: «enteros separados por comas, sin repetir;
negativos para grupos o canales; si hay un valor no válido o repetido, handover no arranca».
El valor por defecto sigue vacío.

## Cambio sobre R23 de la #7 (aceptado por el humano el 2026-10-31)

Test afectado: `services/handover/tests/test_config.py::test_advisor_ids_discards_blank_and_non_numeric`.

Hoy:

```python
clean_env.setenv("ADVISOR_CHAT_IDS", " 111, ,abc,222,,-1003, 4x ")
assert Settings().advisor_ids == [111, 222, -1003]
```

Mezcla dos expectativas. Cambio exacto:

1. **Se conserva** la expectativa de entradas vacías (y con ella la de espacios alrededor,
   negativo válido y orden). El test pasa a llamarse
   `test_advisor_ids_discards_blank_entries` y quita de la entrada solo los dos valores no
   numéricos (`abc`, `4x`), sin tocar nada más:

   ```python
   clean_env.setenv("ADVISOR_CHAT_IDS", " 111, ,222,,-1003, ")
   assert Settings().advisor_ids == [111, 222, -1003]
   ```

   La aserción es literalmente la misma (`== [111, 222, -1003]`). Docstring: R2 (este spec).
2. **Cambia** la expectativa de no numéricos: de «se descartan» a «error». Pasa a
   `test_advisor_ids_rejects_non_numeric_entry`, que usa la cadena original
   `" 111, ,abc,222,,-1003, 4x "` y espera `pytest.raises(ValidationError)` con
   `la entrada 3 ('abc')` en el mensaje (R3, R4).

Ninguna otra aserción existente se elimina ni se debilita: `test_advisor_ids_empty_by_default`,
`test_timeout_defaults_to_300`, `test_settings_read_from_env` y
`test_timeout_below_one_is_rejected` quedan como están, y también todos los tests de
`test_handover.py`, `test_cases.py`, `test_timeouts.py`, `test_security.py`,
`test_repository.py` y `test_handover_app.py` (ADVISORS `[111, 222, 333]` y la lista vacía son
configuraciones válidas). El `implementer` lo deja demostrado en `progress/impl_validacion_config_asesores.md`
con el diff de `test_config.py`.

El texto de R23 en `specs/traspaso_asesor/requirements.md` no lo edita esta feature (queda fuera
de `services/handover/`); la nota de que R23 queda modificada por la #10 la añade el leader si
lo considera oportuno.

## Excepciones

No se añaden excepciones de dominio. El fallo de configuración es `pydantic.ValidationError`
(lo que ya lanza hoy `Settings()` con `HANDOVER_TIMEOUT_SECONDS=0`), originado por un
`ValueError` dentro del validador. No pasa por los exception handlers HTTP porque ocurre antes
de que exista la app.

## Alternativas descartadas

1. **Declarar `advisor_chat_ids: list[int]`** y dejar que pydantic-settings lo convierta.
   Descartada: pydantic-settings interpreta los campos complejos leídos del entorno como JSON,
   así que `111,222` fallaría con un error de JSON opaco, sin posición ni valor (incumple R4), y
   rompería la sintaxis actual de `.env.example` y de Render. Tampoco detecta duplicados.
2. **Registrar el número de asesores en un `lifespan`/evento de arranque** en lugar de en
   `create_app`. Descartada: los tests existentes usan `TestClient(create_app(...))` sin
   contexto, así que el `lifespan` no se ejecuta en ellos y probar R10-R13 exigiría cambiar
   cómo se crean los clientes; además el criterio pide fallar al construir, que ya ocurre en
   `create_app`. Registrar en `create_app` es síncrono y se prueba con `caplog` directamente.
3. **Validar en `create_app`** (y no en `Settings`). Descartada: el acceptance pide que
   `Settings()` lance el error, y así cualquier otro uso de `Settings` (scripts, tests) queda
   protegido.
4. **Descartar los duplicados con un aviso** en lugar de fallar. Descartada por decisión del
   humano (2026-10-31): un id repetido es una configuración incorrecta y el servicio no arranca.
5. **Subir `advisors_configured` a `WARNING`** (opción (b) del spec review) para que se vea sin
   configurar logging. Descartada: un arranque normal no es un aviso, y cambiaría S6, que el
   humano decidió mantener (2026-10-31).
6. **`logging.basicConfig(level=logging.INFO)` en la raíz.** Descartada: haría visibles los
   `INFO` de todas las librerías (p. ej. cada petición de `httpx`), no solo los de handover.
7. **`--log-config` en el `CMD` del `Dockerfile`.** Descartada: añade un archivo de
   configuración y depende de cómo se lance el proceso (Render, ejecución local); configurar
   en `main.py` cubre cualquier `uvicorn handover.main:app`.

## Supuestos a confirmar (no decididos por el humano)

Las «Decisiones para el humano» de `progress/specreview_validacion_config_asesores.md`
quedaron decididas por el humano el 2026-10-31, todas según la recomendación del spec.
La nota de R23 modificado en `specs/traspaso_asesor/requirements.md` se añade al cerrar
la feature (aprobada por el humano).

- **Decidido por el humano (2026-10-31) — S1 — Posición.** Se cuenta desde 1 sobre todos los trozos separados por comas, incluidos
  los vacíos. En `" 111, ,abc"`, `abc` es la entrada 3. Alternativa: contar solo las no vacías.
- **Decidido por el humano (2026-10-31) — S2 — Qué es un entero.** Solo `-?[0-9]+` (dígitos ASCII, signo menos opcional). Se
  rechazan `+5`, `1_000`, `1.0`, `1e3` y dígitos no ASCII, aunque `int()` de Python acepte
  algunos. `0` y los ceros a la izquierda se aceptan (no hay regla de negocio que los
  excluya).
- **S3 — Duplicado.** Se compara por valor entero: `7` y `007` son el mismo id; `-7` y `7` no.
- **Decidido por el humano (2026-10-31) — S4 — Mensaje de duplicado sin el id.** El mensaje da las
  dos posiciones pero no el id repetido, para que ningún id de asesor acabe en los logs del
  arranque fallido. El mensaje de no numérico sí incluye el valor (lo pide el criterio 1; un
  valor no numérico no es un id).
- **Decidido por el humano (2026-10-31) — Valor inválido en el mensaje (criterio 1, R4).** Si la
  errata es un id casi correcto (`12345678x`), el mensaje del arranque fallido lo mostrará casi
  entero. Es lo que pide el criterio 1 y lo que permite R8; se recomienda aceptarlo.
- **Decidido por el humano (2026-10-31) — S5 — `hide_input_in_errors=True` (R8).** Sin él, `str(ValidationError)` incluye
  `input_value='<ADVISOR_CHAT_IDS completo>'` y la traza del arranque fallido mostraría todos
  los ids. Se aplica a todo `Settings`, así que tampoco se repite el valor de otros campos
  inválidos (p. ej. `HANDOVER_TIMEOUT_SECONDS`); el mensaje sigue diciendo qué campo y por
  qué. Si el humano no lo quiere, se retira R8 y su test.
- **Decidido por el humano (2026-10-31) — S6 — Niveles de log.** `advisors_configured` a `INFO`;
  `no_advisors_configured` a `WARNING`. (La visibilidad del `INFO` en el arranque real la
  resuelve R15 sin cambiar estos niveles.)
- **Decidido por el humano (2026-10-31) — S7 — Primer error.** Con varias entradas inválidas solo se informa de la primera en orden
  de lectura.
