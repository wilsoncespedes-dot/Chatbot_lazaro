# Spec review — feature 2 `esqueleto_servicios`

**Veredicto (vuelta 2, vigente):** SPEC_APPROVED

**Veredicto vuelta 1:** SPEC_CHANGES_REQUESTED

Revisado: `specs/esqueleto_servicios/{requirements,design,tasks}.md` contra
`feature_list.json` (acceptance de #2), `docs/specs.md`, `docs/architecture.md`,
`docs/conventions.md`, `contracts/CONTRATOS.md`, `.claude/nocturno.md`,
`.claude/settings.json`, `pytest.ini`, `conftest.py`, `init.sh`.

## Checklist

- [x] **Cobertura de acceptance.** Los 8 criterios tienen R: (1) R1–R7, (2) R8–R10,
  (3) R11–R16, (4) R21–R27, (5) R28–R29, (6) R30–R32, (7) R33–R37, (8) R38–R40.
- [ ] **EARS estricto.** Hay R con dos obligaciones y R fuera de los 5 patrones (ver B1).
- [x] **Verificable.** Cada R tiene un test concreto en la tabla de `design.md` §7
  (R39/R40 se verifican con la salida de pytest/init.sh, aceptable).
- [ ] **Sin invenciones.** R7 (usuario no root) no está en acceptance ni se deduce de él (ver B2).
- [ ] **Diseño / arquitectura.** 3 capas, sin GPL/AGPL, deps con versión y licencia,
  contratos respetados, alternativas descartadas y supuestos: correcto. **Pero** el
  plan depende de editar `pytest.ini` y `docs/`, que están bloqueados (ver A1, A2), y
  crea una carpeta de primer nivel `tests/` fuera de las rutas trazables (A2).
- [ ] **Plan de tests compatible con `./init.sh`.** Con el `pytest.ini` actual
  (`testpaths = services contracts eval scripts`) `tests/infra/` no se recoge y no se puede
  cambiar (A1). Además los tests de infra dependen de `pyyaml`, cuya instalación choca con
  la regla de dependencias del modo nocturno (A3).
- [x] **Tasks.** Todas en `[ ]`, ordenadas, cada una con sus R; entre todas cubren R1–R40.
- [x] **Nada peligroso.** No borra datos del usuario ni toca nada fuera del repo; la red
  solo se usa para `pip install` (permitido en modo nocturno).

## Bloqueantes (el implementer no podría terminar)

### A1. `pytest.ini` no se puede editar → `tests/infra/` nunca se ejecuta
- `.claude/settings.json:41` deniega `Edit(/pytest.ini)`; `.claude/nocturno.md:114-118`
  prohíbe tocar configuración para desbloquearse.
- `design.md` §2 («Se modifican», fila `pytest.ini`) y `tasks.md` T15 lo exigen.
- Sin ese cambio, `python -m pytest` desde la raíz usa `testpaths = services contracts eval scripts`
  (`pytest.ini:4`) y **no recoge** `tests/infra/test_infra.py`: R21–R29 y R31–R37 quedarían
  sin test ejecutado por `./init.sh`/CI, y R39 («recoger ... `tests/infra/`») sería falso.

### A2. `docs/` no se puede editar y `tests/` no es una carpeta trazable
- `.claude/settings.json:33` deniega `Edit(/docs/**)`; `nocturno.md:116` lo prohíbe.
  `design.md` §2 (filas `docs/architecture.md` y `docs/specs.md`) y T17 lo exigen.
- `docs/specs.md` §Trazabilidad solo admite tests en `services/*/tests/`, `contracts/tests/`
  o `eval/`. Los 16 tests de `tests/infra/` no serían trazables según la regla vigente, y el
  reviewer de código tendría que rechazar.
- `docs/architecture.md` §1: «No se añaden ... carpetas de primer nivel ... sin que una
  feature lo pida». El acceptance de #2 no pide `tests/`.

### A3. Instalación de `pyyaml` incompatible con la regla nocturna
- `nocturno.md:90-94`: solo se instala con `-m pip install -r services/<servicio>/requirements.txt`
  y solo paquetes de ese `requirements.txt`. `pyyaml` no está en ningún `requirements.txt` de
  servicio (`design.md` §8.2) y T3 usa `pip install -r requirements-dev.txt`, que no es la forma
  permitida. En el `.venv` actual no están ni `fastapi`, ni `uvicorn`, ni `pydantic-settings`, ni `pyyaml`.
- `design.md` §8 dice «solo se pueden instalar las de esta sección ... con
  `python -m pip install -r requirements-dev.txt`», lo que contradice `nocturno.md`.

## Otros cambios requeridos

### B1. EARS: un solo `DEBE` por requirement y solo los 5 patrones (`docs/specs.md` §requirements)
- **R3**: «DEBE exponer ... `app` ... y su importación NO DEBE fallar ...» → dos obligaciones. Partir en dos R.
- **R19**: «DEBE responder `500` ... y cuyo `message` NO DEBE contener ...» → partir.
- **R39**: «DEBE recoger ... y todos DEBEN pasar» → partir.
- **R30, R31**: empiezan por «Para cada ...», que no es ninguno de los 5 patrones. Reescribir como
  ubicuo («El sistema DEBE incluir en `.env.example` una línea `NOMBRE=` por cada campo de `Settings`...»).
- (Menor) R32, R37: sujeto `.env.example`/`requirements-dev.txt` en lugar de «el sistema»; alinear
  con la plantilla ubicua. Como los ids son estables, añadir R nuevos al final en vez de renumerar.

### B2. R7 (usuario no root en el Dockerfile) es una invención
No aparece en el acceptance ni en `docs/architecture.md`. Opciones: quitar R7 y dejar el `USER app`
como decisión de `design.md` §5 sin requirement, o justificar explícitamente de qué regla se deduce.

### B3. (Menor) `design.md` §7 regla 3
Dice «aunque `importlib` tolere duplicados». En pytest 8.x, para archivos de test sin
`__init__.py`, `--import-mode=importlib` intenta primero importar por el nombre del módulo
(`stem`) y reutiliza `sys.modules[stem]` si ya existe. Dos archivos con el mismo nombre pueden
cargar el módulo equivocado sin avisar. La regla de nombres únicos es **obligatoria**, no
opcional: corregir la redacción para que el implementer no la relaje.

## Cómo resolver A1–A3 (para el `spec_author`)

Elegir una de estas dos vías y reflejarla en los 3 archivos:

1. **Sin tocar `pytest.ini` ni `docs/` (recomendada).** Quitar `tests/infra/`. Repartir los
   tests de infraestructura dentro de `services/<svc>/tests/` (rutas ya trazables y recogidas):
   cada servicio prueba su propia entrada del compose (R24, R26, R27) y los globales (R21–R23,
   R25, R28, R29, R31–R37) van en un archivo con nombre único en un servicio elegido y
   justificado en `design.md` (revisar la alternativa B descartada, ahora forzada por las
   restricciones). Quitar T15 y T17, y reescribir R39 sin `tests/infra/`. Para no depender de
   `pyyaml`, leer `docker-compose.yml` y `ci.yml` como texto (búsquedas y regex acotadas). Si
   se mantiene un parser YAML, justificar cómo se instala cumpliendo `nocturno.md:90-94`.
   Alinear T3 y `design.md` §8 con la forma permitida: `-m pip install -r services/<svc>/requirements.txt`
   para cada servicio. `pytest`/`httpx` ya están instalados.
2. **Mantener `tests/infra/`.** Declarar en `design.md` y en `tasks.md` que los cambios a
   `pytest.ini`, `docs/architecture.md` §1 y `docs/specs.md` §Trazabilidad, y la instalación
   de `pyyaml`, son **requisitos previos humanos**. En modo nocturno esto deja la feature
   `blocked` hasta que el humano los haga.

Lo demás está bien: alcance, firmas de `create_app`/`Settings`/`DomainError`, middleware de
token (cubre rutas inexistentes y cualquier método, falla cerrado con S1), handlers de error
conformes a `ErrorResponse`/`HealthResponse`, Docker/compose (pgvector, `redis:7.2-alpine` por
licencia), CI, supuestos S1–S5 y alternativas A, C, D y E.

---

# Vuelta 2

**Veredicto:** SPEC_APPROVED

Revisado de nuevo: `specs/esqueleto_servicios/{requirements,design,tasks}.md` (revisión 2)
contra el acceptance de #2 en `feature_list.json`, `docs/specs.md`, `docs/architecture.md`,
`docs/conventions.md`, `contracts/CONTRATOS.md`, `contracts/lazaro_contracts/common.py`,
`pytest.ini`, `conftest.py`, `requirements-dev.txt`, `.env.example`, `.claude/settings.json`
y `.claude/nocturno.md`.

## Puntos de la vuelta 1

- [x] **A1 (`pytest.ini`).** Resuelto con la vía 1: ya no existe `tests/infra/`
  (`design.md` §2 y §10.B). Todos los tests viven en `services/<svc>/tests/`, que
  `testpaths = services ...` (`pytest.ini:4`) ya recoge. `pytest.ini` aparece en
  «No se modifican» (`design.md` §2) y en la cabecera de `tasks.md`.
- [x] **A2 (`docs/` y carpeta trazable).** No se edita `docs/`; tests en rutas trazables de
  `docs/specs.md`. Ninguna carpeta de primer nivel nueva (`scripts/db/init/` cuelga de
  `scripts/`; `.github/` la pide el acceptance 7). Los tests globales van a
  `services/orchestrator/tests/test_orchestrator_infra.py`, justificado en S5 y §10.B.
- [x] **A3 (PyYAML / instalación).** Sin parser YAML (alternativa F descartada, §10); lectura
  como texto con helper `_block` y formato de compose/CI fijado (§5, §6, §7.2). T3 y §8 usan
  solo `-m pip install -r services/<svc>/requirements.txt`, conforme a `nocturno.md`
  §Dependencias; `requirements-dev.txt` no gana paquetes (§8.2), solo líneas `-r`.
- [x] **B1 (EARS).** R3, R19 y R39 tienen ahora un solo `DEBE`; las partes separadas son R41
  (importar sin `SERVICE_TOKEN`), R42 (no filtrar el texto de la excepción) y R43 (pytest sale
  con 0), añadidos al final sin renumerar. R30, R31, R32 y R37 usan la plantilla ubicua
  «El sistema DEBE…». Revisados los 42 R vigentes: todos en uno de los 5 patrones y un solo
  `DEBE`/`NO DEBE`.
- [x] **B2 (R7 inventado).** R7 retirado con id reservado (`requirements.md:79-80`); el usuario
  no root queda como decisión de `design.md` §5 sin requirement ni test.
- [x] **B3 (nombres de test).** `design.md` §7.1 regla 3 declara la unicidad «OBLIGATORIA, no
  relajable» con la explicación correcta de `importlib`, y fija los 5 nombres; ninguno choca
  con `contracts/tests/` (`test_contratos_doc.py`, `test_examples.py`, `test_models.py`,
  `test_packaging.py`).

## Checklist completo (vuelta 2)

- [x] **Cobertura de acceptance:** (1) R1–R6; (2) R8–R10; (3) R11–R16; (4) R21–R27;
  (5) R28–R29; (6) R30–R32; (7) R33–R36 (+R37 para que la instalación de CI sirva);
  (8) R38, R39, R40, R43.
- [x] **EARS estricto.**
- [x] **Verificable:** tabla de §7.3 con un test por R (25 en cada `test_<svc>_app.py`, 13 en
  `test_orchestrator_infra.py`); R39/R40/R43 por ejecución, con salida pegada en
  `progress/impl_esqueleto_servicios.md`.
- [x] **Sin invenciones:** R17–R20, R41, R42 se deducen de `contracts/CONTRATOS.md` §Reglas
  comunes (forma `{error, message}`) y de que el `app` de módulo debe importarse en tests/CI;
  R37 se deduce del acceptance 7 (la CI debe poder instalar las dependencias de los servicios).
- [x] **Diseño / arquitectura:** 3 capas (`main`/`domain`/`adapters`), servicios sin importarse
  entre sí, `contracts/` sin cambios, dependencias con versión y licencia (MIT/BSD), Redis
  7.2 BSD (evita RSAL/SSPL/AGPL), alternativas A–F descartadas, supuestos S1–S5.
  `SERVICE_TOKEN_HEADER`, `HealthResponse` y `ErrorResponse` existen en `lazaro_contracts`.
- [x] **Plan compatible con `./init.sh` y permisos:** no toca archivos denegados en
  `.claude/settings.json`; `conftest.py` raíz ya añade `services/<svc>/` a `sys.path`.
- [x] **Tasks:** T1–T19 en `[ ]`, ordenadas, cada una con sus R; entre todas cubren R1–R6 y
  R8–R43.
- [x] **Nada peligroso:** no borra datos del usuario (solo `services/.gitkeep`, exigido por el
  spec), no lee `.env` (`Settings` sin `env_file`; `.dockerignore` excluye `.env`), red solo
  para `pip install` permitido.

## Observaciones no bloqueantes (para el implementer)

1. `ErrorResponse.message` exige `min_length=1` (`contracts/lazaro_contracts/common.py:32`).
   En el handler de `DomainError` (§3.4) y de `HTTPException`, si `str(exc)`/`detail` sale vacío,
   usar un texto fijo en español para no producir un cuerpo fuera de contrato.
2. R19/R42 con `TestClient(app, raise_server_exceptions=False)`: es la forma correcta, porque
   `ServerErrorMiddleware` re-lanza tras usar el handler de `Exception`.
3. T8: los tests de compose (R24, R26, R27) fallarán hasta T11; el hook PostToolUse ejecuta
   los tests tras cada edición, así que conviene no dejar la sesión parada entre T8 y T11.
