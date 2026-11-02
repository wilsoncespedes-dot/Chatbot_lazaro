# Spec review — validacion_config_asesores (feature #10)

**Veredicto:** SPEC_CHANGES_REQUESTED

Revisión pedida por el leader con la feature en `blocked` (decisión del humano). No se toca
`feature_list.json` ni `specs/`.

## Cobertura del acceptance
- [x] A1 (no entero → error con posición y valor; `create_app()` no crea la app) → R1, R3, R4, R9.
- [x] A2 (vacías ignoradas) → R2.
- [x] A3 (lista vacía: arranca, `no_advisors_configured`, `no_advisors` sin cambios) → R11, R12, R14.
- [x] A4 (log de arranque con el número, sin ids) → R10, R13 (R8 para la traza del arranque fallido). Ver cambio 2: el registro `INFO` no llega a verse con el arranque real.
- [x] A5 (humano: duplicado → error, no arranca) → R5, R6, R9.
- [x] A6 (humano: negativos válidos) → R7.
- [x] A7 (humano: cambio de R23 de la #7) → R2, R3 + design «Cambio sobre R23 de la #7».
- [x] A8 (fuera de alcance: comprobar escritura a cada chat) → requirements «Fuera de alcance».
- [x] A9 (tests listados) → T4 (no numérico), T8 (duplicado), T7 (solo comas), T15 (lista vacía con aviso), T10 (negativos), T6 (espacios), T13 (`create_app` falla), T17 (log sin ids).

## Fidelidad a las decisiones del humano (2026-10-31)
- [x] No numérico y duplicado impiden el arranque; negativos válidos; vacías ignoradas; lista vacía arranca con aviso. Coincide con `progress/propuesta_etapa2.md` §6.
- [x] Ninguna decisión de negocio tomada en silencio: S1-S7 de `design.md` (líneas 142-162) están marcadas «no decididos por el humano».

## Contradicción A1 («indica la posición y el valor inválido») frente a S5/R8 (`hide_input_in_errors`)
- [x] **No hay contradicción real en el diseño.** Lo he comprobado con el `.venv` (pydantic 2.14.2): con `hide_input_in_errors=True` y un `ValueError` lanzado en el `field_validator`, `str(ValidationError)` queda en
  `Value error, ADVISOR_CHAT_IDS: la entrada 2 ('abc') no es un entero [type=value_error]`.
  Es decir, el mensaje propio del validador (design.md línea 28) conserva la posición y el valor inválido (A1, R4), y lo único que se oculta es el `input_value=` con la lista completa (R8). Es la resolución que pedía el leader: posición + valor inválido, sin volcar la lista.
- [ ] **Pero la redacción de R8 es ambigua e incompatible en un caso límite** (`requirements.md` líneas 48-51): «NO DEBE contener el valor completo de `ADVISOR_CHAT_IDS` (es decir, los ids válidos de la lista)» mezcla dos cosas. Con `ADVISOR_CHAT_IDS="987654321,987654321x"`, R4 obliga a mostrar `'987654321x'`, que contiene el id válido `987654321`: R4 y la lectura «los ids válidos» de R8 chocan. Ver cambio 1.

## Cambio de R23 de la #7
- [x] Limitado a lo aceptado. Verificado contra `services/handover/tests/test_config.py` líneas 26-29: la entrada pasa de `" 111, ,abc,222,,-1003, 4x "` a `" 111, ,222,,-1003, "` (solo se quitan `abc` y `4x`; el `, ` final sigue siendo una entrada vacía) y la aserción `== [111, 222, -1003]` es literalmente la misma. La cadena original sigue probada en T4/T5, ahora esperando el error.
- [x] No elimina ni debilita otras aserciones: `test_advisor_ids_empty_by_default`, `test_timeout_defaults_to_300`, `test_settings_read_from_env` y `test_timeout_below_one_is_rejected` quedan intactos; `tests/conftest.py::make_env` (línea 85) solo genera listas válidas (`111,222,333` o vacía), así que ningún otro test de handover cambia. Ningún otro archivo del repo (fuera de `specs/`) depende del descarte de no numéricos (búsqueda de `ADVISOR_CHAT_IDS|advisor_ids`).
- Nota (no bloquea): `progress/impl_traspaso_asesor.md` línea 114 mapea R23 de la #7 a `test_advisor_ids_discards_blank_and_non_numeric`; tras el cambio ese nombre deja de existir. Conviene que T20 lo anote y que el docstring del test renombrado cite «R23 (#7), modificado por R2 (#10)».

## EARS estricto
- [x] Un solo `DEBE`/`NO DEBE` por requirement, sin verbos blandos. R13 ubicuo; R1, R2, R7, R10, R11 evento; R12, R14 estado; R3-R6, R8, R9 no deseado.

## Verificable
- [x] Cada R1-R14 tiene test nombrado en `tasks.md` (T3-T11, T13-T18).

## Sin invenciones
- [x] R8 y S4 (mensaje de duplicado sin el id) se derivan de A4 («no sus ids») y están marcados como supuestos.

## Diseño
- [x] Solo `services/handover/` + comentario en `.env.example`; sin contratos, sin dependencias nuevas, sin variables nuevas.
- [x] Capas: la validación es pura (`config.py`); `create_app` solo registra el log. Sin IO nuevo.
- [x] 4 alternativas descartadas con motivo (design líneas 125-140).
- [x] «Supuestos a confirmar» presente (S1-S7).
- [ ] **El registro `INFO` de R10 no se ve en el arranque real.** `services/handover/Dockerfile` arranca con `uvicorn handover.main:app` y nadie configura el logging raíz: comprobado en el `.venv`, el `LOGGING_CONFIG` de uvicorn solo configura los loggers `uvicorn`, `uvicorn.error` y `uvicorn.access` (`root` = `None`), y no hay `basicConfig` en ningún servicio. El logger `handover.main` propaga a una raíz sin handlers en nivel `WARNING`, así que `advisors_configured count=N` (INFO) se descarta y solo se vería el `WARNING` `no_advisors_configured`. Los tests con `caplog` pasarían, pero A4 («Al iniciar, handover registra en el log cuántos asesores hay») no se cumpliría en Compose ni en Render. Ver cambio 2.

## Tasks
- [x] T1-T20 en `[ ]`, en orden (config → test de R23 → tests de config → arranque → docs/cierre), cada una con sus `R<n>`; entre todas cubren R1-R14.

## Nada peligroso
- [x] No borra datos, no usa la red, no toca archivos fuera del repo.

## Cambios requeridos
1. **Reescribir R8** para que no choque con R4 y diga exactamente lo que comprueba T11. Propuesta:
   «SI `Settings()` lanza un error de validación por `ADVISOR_CHAT_IDS` ENTONCES el texto del error NO DEBE contener ninguna entrada de la lista distinta de la entrada no válida que informa R4.»
   Mantener T11 (con entradas que no se solapen) y añadir a T5 la comprobación de que `111` y `-1003` no aparecen en el mensaje del caso `" 111, ,abc,222,,-1003, 4x "`.
2. **Hacer visible el log de arranque de R10** o declararlo. Una de dos, documentada en `design.md`:
   (a) configurar el logging del servicio para que los `INFO` de `handover` lleguen a la salida (p. ej. `logging.basicConfig(level=logging.INFO)` en `main.py` antes de `create_app`, o `--log-config`), con un test que lo compruebe; o
   (b) registrar `advisors_configured` a `WARNING` (cambiando S6) y explicar por qué.
   Lo que no vale es que A4 solo se cumpla bajo `caplog`.

## Decisiones para el humano
- **S1 (posición):** se cuenta incluyendo las entradas vacías (`" 111, ,abc"` → `abc` es la 3). Alternativa: contar solo las no vacías.
- **S2 (qué es un entero):** solo `-?[0-9]+`; se rechazan `+5`, `1_000`, `1.0`; se aceptan `0` y ceros a la izquierda (`007` = `7`, que con S3 cuenta como duplicado).
- **S4:** el error de duplicado da las dos posiciones pero no el id. A5 solo pide que «lo indique».
- **S5:** `hide_input_in_errors=True` se aplica a **todo** `Settings`, no solo a `ADVISOR_CHAT_IDS`: tampoco se mostrará el valor de `HANDOVER_TIMEOUT_SECONDS`, `SERVICE_TOKEN`, etc. si son inválidos (lo considero una mejora de seguridad, pero cambia los mensajes actuales).
- **Valor inválido en el mensaje (A1):** si la errata es un id casi correcto (`12345678x`), el mensaje del arranque fallido lo mostrará casi entero. Es lo que pide A1; confirmar que se acepta.
- **S6/S7:** niveles de log y «solo el primer error».
- **Nota en `specs/traspaso_asesor/requirements.md`** (R23 modificado por la #10): la deja el design a criterio del leader; recomiendo añadirla para que la #7 no quede contradictoria.

## Segunda vuelta (2026-10-31)

**Veredicto:** SPEC_APPROVED (solo quedan decisiones del humano)

### Cambios requeridos de la primera vuelta
- [x] **Cambio 1 (R8).** `requirements.md` l.48-52 reescrito con la redacción propuesta («ninguna entrada de la lista distinta de la entrada no válida que informa R4») y el ejemplo `'987654321x'`. T5 (l.18) ya comprueba que `111`, `-1003` y `222` no aparecen; T11 (l.27) usa entradas que no se solapan con la inválida.
- [x] **Cambio 2 (log visible).** Opción (a): R15 nueva (l.81-86), design «Logging del servicio» (l.61-115) con `configure_logging()` acotado al logger `handover` (no toca la raíz, idempotente, `propagate` intacto, fuera de `create_app`), T21 (implementación) y T22 (subproceso `import handover.main` que lee `stderr`, sin red). La opción (b), `basicConfig` en la raíz y `--log-config` quedan como alternativas descartadas 5-7 con motivo. S6 no cambia.
- [x] Nota no bloqueante de la primera vuelta (renombrado del test de R23 de la #7) recogida en T3 (docstring) y T20.

### Decisiones del humano no tomadas en silencio
- [x] S1, S2, S4, «valor inválido en el mensaje», S5, S6 y S7 marcados «REVISAR (pendiente del humano)» (design l.214-237), con la misma recomendación de la primera vuelta. S3 no estaba entre las decisiones abiertas (es consecuencia de S2) y no lleva la marca: correcto.
- [x] La nota en `specs/traspaso_asesor/requirements.md` sigue a criterio del leader (design l.173-175).

### Nada inventado, sin conflictos
- [x] R15 es la forma verificable del criterio 4 en el arranque real (lo pidió el cambio 2); no añade comportamiento de negocio.
- [x] Con la #11 y la #12: la #11 no toca `main.py` ni `config.py`; sus logs nuevos son `ERROR` y `configure_logging()` no los afecta (el logger `handover` queda en `INFO`). La #12 no importa `handover.config`. `test_startup.py` no colisiona con ningún archivo de test de la #11/#12.
- [x] Con la #14 (`specs/autorizacion_asesores/`): la comparación exacta de `advisor_id` con los ids de `ADVISOR_CHAT_IDS` (design #14 §3.1) es compatible con la lista que deja esta feature.

### EARS, trazabilidad y tasks
- [x] R1-R15: un solo `DEBE`/`NO DEBE`, patrones válidos (R15 es de evento).
- [x] Cada R con test nombrado (R15 → T22; R13 también T22). T1-T22 en `[ ]`; el orden T21-T22 antes de T19 está explicado en `tasks.md` l.6-7. T20 mapea R1-R15.

### Notas para el implementer (no bloquean)
- T22 en Windows: construir el `env=` del subproceso partiendo de `os.environ` (o al menos con `SYSTEMROOT`); con un entorno vacío el intérprete hijo puede fallar al arrancar.

### Decisiones para el humano (siguen abiertas)
1. S1 — posición contando las entradas vacías.
2. S2 — qué es un entero (`-?[0-9]+`; `007` = `7` y cuenta como duplicado).
3. S4 — mensaje de duplicado con posiciones y sin el id.
4. Valor inválido en el mensaje: un id casi correcto (`12345678x`) se verá casi entero.
5. S5 — `hide_input_in_errors=True` para todo `Settings`.
6. S6/S7 — niveles de log (`INFO`/`WARNING`) y «solo el primer error».
7. (Leader) Nota de R23 modificado en `specs/traspaso_asesor/requirements.md`.
