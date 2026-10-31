# Requirements — esqueleto_servicios (feature #2)

> Feature: «Esqueleto de servicios con Docker». Crea los 4 servicios vacíos con
> FastAPI y la forma de `docs/architecture.md` §1, Postgres con pgvector y Redis
> en Docker Compose, y la CI. Ningún servicio implementa todavía rutas de negocio.
>
> Notación EARS estricta (`docs/specs.md`): un solo `DEBE`/`NO DEBE` por
> requirement y solo los 5 patrones. Los supuestos `S<n>` citados están en
> `design.md` §9. Ids estables: no se renumeran.
>
> **Revisión 2** (respuesta a `progress/specreview_esqueleto_servicios.md`):
> R7 queda **retirado** (no se deduce del acceptance; el usuario no root del
> Dockerfile pasa a ser una decisión de `design.md` §5 sin requirement) y su id
> no se reutiliza. R3, R19 y R39 se parten; las partes nuevas son R41, R42 y R43.
> R30, R31, R32 y R37 se reescriben con la plantilla ubicua. Ya no existe
> `tests/infra/`: todos los tests viven en `services/<svc>/tests/`.

**«Los 4 servicios»** son, con el puerto publicado que les asigna esta feature
(`design.md` §5):

| Servicio (`<svc>`)  | Paquete Python      | Puerto publicado |
|---------------------|---------------------|------------------|
| `telegram_gateway`  | `telegram_gateway`  | `8001`           |
| `orchestrator`      | `orchestrator`      | `8002`           |
| `rag`               | `rag`               | `8003`           |
| `handover`          | `handover`          | `8004`           |

**Dónde se cumple y se prueba cada requirement:**

- Secciones A–D, R24, R26, R27, R30, R38, R41 y R42: se cumplen **en cada uno
  de los 4 servicios** y se prueban en `services/<svc>/tests/test_<svc>_app.py`
  de ese servicio.
- Resto de las secciones E–H (artefactos globales del repositorio: compose,
  SQL, `.env.example`, CI, `requirements-dev.txt`): se prueban en
  `services/orchestrator/tests/test_orchestrator_infra.py` (`design.md` §7, S5).
- Sección I: ejecución de `python -m pytest` y `./init.sh` desde la raíz.

«Ruta protegida» = toda ruta HTTP del servicio salvo `GET /health`
(incluidas rutas que no existen).

---

## A. Forma de cada servicio (acceptance 1)

## R1
El sistema DEBE tener, para cada uno de los 4 servicios, la carpeta
`services/<svc>/` con el paquete Python `services/<svc>/<svc>/` (con
`__init__.py`), los módulos `<svc>/main.py`, `<svc>/config.py` y
`<svc>/domain.py`, el paquete `<svc>/adapters/` (con `__init__.py`), los
archivos `services/<svc>/requirements.txt` y `services/<svc>/Dockerfile`, y la
carpeta `services/<svc>/tests/`.

## R2
El sistema DEBE exponer en el módulo `<svc>.main` de cada servicio una función
`create_app(settings: Settings | None = None) -> FastAPI` que devuelve una
instancia de `fastapi.FastAPI`.

## R3
El sistema DEBE exponer en el módulo `<svc>.main` de cada servicio una variable
de módulo `app` que es una instancia de `fastapi.FastAPI` creada con
`create_app()`.

## R4
El sistema DEBE exponer en el módulo `<svc>.config` de cada servicio una clase
`Settings` (Pydantic Settings) con el campo `service_token: str` que se lee de
la variable de entorno `SERVICE_TOKEN`.

## R5
El sistema DEBE declarar en `services/<svc>/requirements.txt` de cada servicio
exactamente las dependencias de ejecución listadas en `design.md` §8.1, cada
una con versión acotada por arriba y por abajo.

## R6
El sistema DEBE incluir en cada servicio un `Dockerfile` que construye la
imagen desde `python:3.12-slim`, copia `contracts/lazaro_contracts` y el
paquete `<svc>`, instala `services/<svc>/requirements.txt` y arranca con
`uvicorn <svc>.main:app --host 0.0.0.0 --port 8000`.

## R7
*Retirado en la revisión 2 (no está en el acceptance). Ver `design.md` §5.*

---

## B. Salud (acceptance 2)

## R8
CUANDO un servicio recibe `GET /health` sin encabezado `X-Service-Token`, el
sistema DEBE responder `200` con el cuerpo exacto
`{"status": "ok", "service": "<svc>"}`, donde `<svc>` es el nombre del servicio.

## R9
CUANDO un servicio recibe `GET /health`, el sistema DEBE devolver un cuerpo que
valida contra el modelo `lazaro_contracts.HealthResponse`.

## R10
CUANDO un servicio recibe `GET /health` con un `X-Service-Token` incorrecto, el
sistema DEBE responder `200` con `{"status": "ok", "service": "<svc>"}`.

---

## C. Autenticación entre servicios (acceptance 3 — prueba de seguridad obligatoria)

## R11
SI un servicio recibe una petición a una ruta protegida sin el encabezado
`X-Service-Token` ENTONCES el sistema DEBE responder `401` con un cuerpo que
valida contra `lazaro_contracts.ErrorResponse` y tiene `error` = `unauthorized`.

## R12
SI un servicio recibe una petición a una ruta protegida con un `X-Service-Token`
distinto de `SERVICE_TOKEN` ENTONCES el sistema DEBE responder `401` con
`error` = `unauthorized`.

## R13
SI un servicio recibe una petición sin token a una ruta que no existe
ENTONCES el sistema DEBE responder `401` con `error` = `unauthorized` (en lugar
de `404`), para no revelar qué rutas existen.

## R14
SI un servicio recibe una petición sin token con un método distinto de `GET`
(p. ej. `POST`) a una ruta protegida ENTONCES el sistema DEBE responder `401`
con `error` = `unauthorized`.

## R15
MIENTRAS `SERVICE_TOKEN` está vacío, el sistema DEBE responder `401` con
`error` = `unauthorized` a toda petición a una ruta protegida, incluida una que
envía `X-Service-Token` vacío (falla cerrado; supuesto S1).

## R16
CUANDO un servicio recibe una petición a una ruta protegida con
`X-Service-Token` igual a `SERVICE_TOKEN`, el sistema NO DEBE responder `401`
(la petición llega al enrutado de FastAPI).

---

## D. Forma de los errores (`contracts/CONTRATOS.md` §Reglas comunes)

## R17
CUANDO un servicio recibe con token válido una petición a una ruta que no
existe, el sistema DEBE responder `404` con un cuerpo que valida contra
`ErrorResponse` y tiene `error` = `not_found`.

## R18
SI una ruta del servicio recibe un cuerpo que no valida contra su modelo
ENTONCES el sistema DEBE responder `422` con un cuerpo que valida contra
`ErrorResponse` y tiene `error` = `validation_error`.

## R19
SI una ruta del servicio lanza una excepción no controlada ENTONCES el sistema
DEBE responder `500` con un cuerpo que valida contra `ErrorResponse` y tiene
`error` = `internal_error`.

## R20
SI una ruta del servicio lanza una subclase de `DomainError` (de `<svc>.domain`)
ENTONCES el sistema DEBE responder con el `status_code` de esa clase y un
cuerpo `{"error": <code de la clase>, "message": <texto de la excepción>}`.

---

## E. Docker Compose (acceptance 4)

## R21
El sistema DEBE incluir en la raíz un `docker-compose.yml` que define los
servicios `postgres`, `redis`, `telegram_gateway`, `orchestrator`, `rag` y
`handover`.

## R22
El sistema DEBE configurar el servicio `postgres` de `docker-compose.yml` con
una imagen cuyo nombre contiene `pgvector` (`pgvector/pgvector:pg16`,
`design.md` §5).

## R23
El sistema DEBE configurar el servicio `redis` de `docker-compose.yml` con la
imagen `redis:7.2-alpine` (última rama con licencia BSD; supuesto S4).

## R24
El sistema DEBE declarar, para cada uno de los 4 servicios en
`docker-compose.yml`, un `env_file` que incluye `.env`.

## R25
El sistema DEBE declarar en el servicio `postgres` de `docker-compose.yml` un
`env_file` que incluye `.env`.

## R26
El sistema DEBE publicar, para cada uno de los 4 servicios en
`docker-compose.yml`, el puerto interno `8000` en el puerto del host de la tabla
de arriba (`"8001:8000"` para `telegram_gateway`, `"8002:8000"` para
`orchestrator`, `"8003:8000"` para `rag`, `"8004:8000"` para `handover`).

## R27
El sistema DEBE construir cada uno de los 4 servicios de `docker-compose.yml`
con contexto la raíz del repositorio (`.`) y `dockerfile` =
`services/<svc>/Dockerfile`.

---

## F. Inicialización de la base de datos (acceptance 5)

## R28
El sistema DEBE incluir el script `scripts/db/init/01_extensions.sql` que
contiene la sentencia `CREATE EXTENSION IF NOT EXISTS vector;`.

## R29
El sistema DEBE montar en el servicio `postgres` de `docker-compose.yml` la
carpeta `./scripts/db/init` en `/docker-entrypoint-initdb.d`.

---

## G. Variables de entorno (acceptance 6)

## R30
El sistema DEBE incluir en `.env.example` una línea `<NOMBRE>=...` por cada
campo de `Settings` de cada uno de los 4 servicios, donde `<NOMBRE>` es el
nombre del campo en mayúsculas.

## R31
El sistema DEBE incluir en `.env.example` una línea `VAR=...` por cada variable
`${VAR}` o `${VAR:-...}` interpolada en `docker-compose.yml`.

## R32
El sistema DEBE incluir en `.env.example` las variables `POSTGRES_USER`,
`POSTGRES_PASSWORD` y `POSTGRES_DB` que usa el servicio `postgres`.

---

## H. Integración continua (acceptance 7)

## R33
El sistema DEBE incluir `.github/workflows/ci.yml` que se dispara en `push` y
en `pull_request`.

## R34
El sistema DEBE incluir en `.github/workflows/ci.yml` un paso que instala
dependencias con `pip install -r requirements-dev.txt`.

## R35
El sistema DEBE incluir en `.github/workflows/ci.yml` un paso que ejecuta
`python -m pytest`.

## R36
El sistema DEBE fijar en `.github/workflows/ci.yml` la versión de Python `3.12`
con `actions/setup-python`.

## R37
El sistema DEBE incluir en `requirements-dev.txt` una línea `-r` con el
`requirements.txt` de cada uno de los 4 servicios, para que una sola
instalación deje listos los tests de todos.

---

## I. Tests y verde global (acceptance 8)

## R38
El sistema DEBE tener en `services/<svc>/tests/` de cada uno de los 4 servicios
al menos un test de `GET /health` (R8) y al menos un test de token ausente (R11).

## R39
CUANDO se ejecuta `python -m pytest` desde la raíz del repositorio, el sistema
DEBE recoger los tests de `services/<svc>/tests/` de los 4 servicios y de
`contracts/tests/` sin errores de colección.

## R40
CUANDO se ejecuta `./init.sh` tras implementar la feature, el sistema DEBE
terminar con código de salida `0` y el bloque de tests en `[OK]` (no `[WARN]`
de «aún no hay tests»).

---

## Requirements añadidos en la revisión 2

## R41
MIENTRAS la variable `SERVICE_TOKEN` no está definida en el entorno, el sistema
DEBE permitir importar `<svc>.main` de cada servicio sin lanzar ninguna
excepción.

## R42
SI una ruta del servicio lanza una excepción no controlada ENTONCES el sistema
NO DEBE incluir el texto de la excepción original en el `message` de la
respuesta.

## R43
CUANDO se ejecuta `python -m pytest` desde la raíz del repositorio, el sistema
DEBE terminar con código de salida `0` (todos los tests recogidos pasan).
