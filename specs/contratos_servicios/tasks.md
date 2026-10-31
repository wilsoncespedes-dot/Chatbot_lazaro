# Tasks — contratos_servicios (feature #1)

> Orden pensado para que cada paso sea verificable. Python del proyecto:
> `.venv/Scripts/python.exe`. Solo se tocan `contracts/` y `requirements-dev.txt`
> (ver `design.md` §1). Cada test lleva en su docstring el `R<n>` que cubre.
> `contracts/.gitkeep` no se toca (`design.md` §8).

## Dependencias

- [x] T1 — Crear `contracts/requirements.txt` con la única línea `pydantic>=2.12,<3`. Cubre: R50.
- [x] T2 — Añadir la línea `-r contracts/requirements.txt` a `requirements-dev.txt`, conservando sin cambios las líneas existentes (`pytest>=8,<9` y `httpx>=0.27,<1`). Cubre: R51.
- [x] T3 — Instalar en el `.venv`: `.venv/Scripts/python.exe -m pip install -r contracts/requirements.txt` (único paquete autorizado por `design.md` §8) y comprobar `python -c "import pydantic; print(pydantic.VERSION)"` → `2.x`. Si la instalación se deniega por permisos o falla, la feature queda `blocked` con el error (`.claude/nocturno.md` §Dependencias); no buscar vías alternativas. Cubre: R17, R50.

## Paquete `lazaro_contracts`

- [x] T4 — Crear `contracts/lazaro_contracts/common.py`: constantes, `Identifier`, `MessageText`, `ContractModel` (`extra="forbid"`), `ErrorResponse`, `HealthResponse` según `design.md` §3. Cubre: R18, R22, R43, R44, R45.
- [x] T5 — Crear `contracts/lazaro_contracts/messages.py` con `MessageRequest`, `MessageResponse`, `SendRequest`, `SendResponse`. Cubre: R20, R21, R23, R24, R25, R26.
- [x] T6 — Crear `contracts/lazaro_contracts/search.py` con `SearchRequest`, `SearchResult`, `SearchResponse` (`RootModel`). Cubre: R27, R28, R29, R30, R52.
- [x] T7 — Crear `contracts/lazaro_contracts/manuals.py` con `ManualUploadRequest`, `ManualUploadResponse`. Cubre: R37, R38.
- [x] T8 — Crear `contracts/lazaro_contracts/cases.py` con `HandoverReason`, `LastMessage`, `HandoverRequest`, `HandoverResponse`, `CaseReplyRequest`, `CaseReplyResponse`, `CaseCloseRequest`, `CaseCloseResponse`, `CheckTimeoutsRequest`, `CheckTimeoutsResponse`. Cubre: R20, R21, R22, R26, R31, R32, R33, R34, R35, R36, R39, R40, R41, R42.
- [x] T9 — Crear `contracts/lazaro_contracts/__init__.py` que reexporta los 20 modelos de R16 y las 6 constantes de R45 y define `__all__`. Imports solo de stdlib, pydantic y el propio paquete. Cubre: R16, R45, R46.

## Ejemplos

- [x] T10 — Crear los 21 archivos JSON de `contracts/examples/` de `design.md` §6 (datos ficticios, UTF-8, 2 espacios). Cubre: R47, R48.

## Documento

- [x] T11 — Crear `contracts/CONTRATOS.md` con la estructura de `design.md` §5: `## Reglas comunes` (autenticación, errores con la tabla de §4, mensajes repetidos, salud), `## Rutas` con una sección `### POST …` por cada una de las 8 rutas (líneas `Expone`, `Llama`, `Modelos`; subsecciones `#### Request`, `#### Respuesta`, `#### Errores`), y `## Supuestos a confirmar` con S1–S10 de `design.md` §9. Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15.

## Tests

- [x] T12 — Crear `contracts/tests/test_examples.py` con el mapa `EXAMPLES` y: `test_every_example_validates_against_its_model` (parametrizado), `test_every_example_file_is_mapped`, `test_every_model_has_an_example`. Cubre: R47, R48, R49.
- [x] T13 — Crear `contracts/tests/test_models.py`, parte 1 (genérica, derivada de los ejemplos): `test_missing_required_field_is_rejected` (parametrizado por modelo y campo obligatorio; en `SearchResponse` quitando el campo de un elemento) y `test_unexpected_field_is_rejected` (todos los modelos salvo `SearchResponse`; para `SearchResult` dentro del arreglo). Cubre: R18, R19.
- [x] T14 — En `contracts/tests/test_models.py`, parte 2 (tipos y límites comunes): fechas sin zona en `received_at` y `at` (R20); `text` vacío y de 4097 caracteres en los 4 modelos (R21); identificadores vacíos y de 65 caracteres en cada campo de R22 (R22). Cubre: R20, R21, R22.
- [x] T15 — En `contracts/tests/test_models.py`, parte 3 (por modelo): `MessageRequest` (campos y `update_id` negativo rechazado, R23); `MessageResponse.status` inválido (R24); `SendRequest` (R25); `sent: false` en `SendResponse` y `CaseReplyResponse` (R26); `SearchRequest` (R27) con `top_k` 0 y 21 (R28) y sin `category` → `None` (R52); `SearchResponse` con `[]` y con resultados (R29); `score` -1.01 y 1.01 (R30); `HandoverRequest` (R31), `reason` inválido (R32), 11 `last_messages` rechazados y 10 aceptados (R33), `role` inválido (R34); `HandoverResponse` (R35); `CaseReplyRequest` (R36); `name` vacío y de 201 caracteres (R37); `chunks: 0` (R38); `CaseCloseRequest` (R39); `CaseCloseResponse.status` inválido (R40); `{}` en `CheckTimeoutsRequest` (R41); `timed_out_cases: []` aceptado (R42); `ErrorResponse` con `error` `"Not Found"` y `message` vacío (R43); `HealthResponse` con `status` `"down"` y `service` vacío (R44). Cubre: R23–R44, R52.
- [x] T16 — Crear `contracts/tests/test_contratos_doc.py`: secciones de las 8 rutas (R1), `Expone` con el servicio correcto (R2), `Llama` no vacío (R3), `Modelos` en `__all__` (R4), campos del modelo de request en la tabla `#### Request` (R5), código de éxito y campos de response en `#### Respuesta` (R6), filas 401/422 en cada `#### Errores` (R7), errores propios (R8), reglas comunes (R9, R10, R11, R12), supuestos S1, S2 y S1–S10 (R13, R14, R15). Cubre: R1–R15.
- [x] T17 — Crear `contracts/tests/test_packaging.py`: línea de `contracts/requirements.txt` (R50), línea de `requirements-dev.txt` (R51), valores de las constantes (R45), `pydantic.VERSION` 2.x y subclases de `BaseModel` (R17), exportación de los 20 modelos (R16), imports permitidos recorriendo con `ast` los módulos (R46). Cubre: R16, R17, R45, R46, R50, R51.

## Cierre

- [x] T18 — Ejecutar `.venv/Scripts/python.exe -m pytest contracts` y después `./init.sh`; ambos en verde. Cubre: R1–R52.
- [x] T19 — Escribir el mapa de trazabilidad `R<n> → test` en `progress/impl_contratos_servicios.md` (todas las R1–R52). Cubre: R1–R52.
