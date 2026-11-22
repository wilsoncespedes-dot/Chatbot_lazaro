# Design — #77 `importacion_clientes`

## 1. Resumen

Importación en dos pasos (vista previa y confirmación) sobre `/admin/clientes`.
La lógica vive en un módulo nuevo `client_import.py`; las escrituras pasan por el
puerto `FuenteDeClientes` de #76 (ampliado). El archivo se lee en memoria, nunca
se persiste; entre los dos pasos solo se guardan en memoria las filas ya
normalizadas, con TTL y de un solo uso.

```
POST .../importar/vista-previa (multipart, CSRF) -> parse + validar + duplicados
     -> ImportStaging.put(session_id, plan) -> HTML vista previa (+ token)
POST .../importar/confirmar (token, politica, CSRF) -> ImportStaging.pop
     -> ejecutar_importacion -> FuenteDeClientes -> resumen (HTML)
GET  .../importar/resumen/{token}.csv -> CSV con celdas protegidas
```

## 2. Archivos

| Archivo | Cambio |
|---|---|
| `services/orchestrator/orchestrator/client_import.py` (nuevo) | Parseo, validación, duplicados, ejecución, resumen, `ImportStaging`, CSV seguro (R4-R38). |
| `services/orchestrator/orchestrator/client_source.py` | Puerto: `buscar_por_correo`, `buscar_por_telefono`, `actualizar_contacto`; `crear` gana `correo`/`telefono` opcionales (R36, R39). |
| `services/orchestrator/orchestrator/adapters/repository.py` | Protocol, `InMemoryRepository` y `PostgresRepository`: `find_client_id_by_email/phone`, `update_client_contact`, `create_client_credential(..., email, phone)`; sentencias de esquema; limpieza en supresión y purga (R39-R41). |
| `services/orchestrator/orchestrator/domain.py` | `Profile` gana `email`/`phone` opcionales (default `None`). |
| `services/orchestrator/orchestrator/admin_routes.py` | Rutas de §4; reutiliza `_require_session`, `_require_csrf_audited`, `_audit`, límite de tamaño de multipart (R1-R3, R42). |
| `services/orchestrator/orchestrator/admin.py` | `render_clients` añade el enlace; `render_import_form`, `render_import_preview`, `render_import_summary`. |
| `services/orchestrator/orchestrator/config.py`, `.env.example` | `CLIENT_IMPORT_MAX_BYTES`, `CLIENT_IMPORT_MAX_ROWS`, `CLIENT_IMPORT_PREVIEW_TTL_SECONDS`. |
| `services/orchestrator/tests/test_client_import.py` (nuevo) | Pruebas unitarias y de rutas. |
| `docs/architecture.md` | Párrafo breve con formato del CSV y límites. |

## 3. Firmas

```python
# client_import.py
CAMPOS = ("id", "usuario", "correo", "telefono")

class ImportFileError(Exception):
    code: str  # archivo_no_utf8 | encabezado_invalido | archivo_demasiado_grande | demasiadas_filas

@dataclass(frozen=True)
class FieldError: field: str; code: str

@dataclass(frozen=True)
class ImportRow:
    number: int                      # fila de datos, base 1
    id: str | None; usuario: str; correo: str | None; telefono: str | None
    errors: tuple[FieldError, ...]
    status: Literal["nueva", "duplicado_base", "duplicado_archivo", "conflicto", "invalida"]
    reason: str | None               # id|correo|telefono|usuario|fila origen
    existing_profile_id: str | None

@dataclass(frozen=True)
class ImportPlan: rows: tuple[ImportRow, ...]

@dataclass(frozen=True)
class ImportSummary:
    created: int; updated: int; skipped: int; failed: int
    details: tuple[tuple[int, str, str], ...]   # fila, estado, motivo (sin PII)

def parse_csv(data: bytes, *, max_bytes: int, max_rows: int) -> list[dict[str, str]]
def build_plan(rows, source: FuenteDeClientes) -> ImportPlan
def run_import(plan: ImportPlan, policy: Literal["actualizar", "saltar"],
               source: FuenteDeClientes, now: datetime) -> ImportSummary
def summary_to_csv(summary: ImportSummary) -> str
def csv_safe(cell: str) -> str

class ImportStaging:                  # en memoria, thread-safe
    def __init__(self, ttl_seconds: int, clock: Callable[[], datetime]) -> None
    def put(self, session_id: str, plan: ImportPlan) -> str       # token urlsafe
    def pop(self, session_id: str, token: str) -> ImportPlan | None
    def put_summary / get_summary                                  # mismo TTL, para el CSV
```

Puerto (`client_source.py`), todos opcionales para no romper llamadores:

```python
def buscar_por_correo(self, correo: str) -> str | None   # profile_id
def buscar_por_telefono(self, telefono: str) -> str | None
def actualizar_contacto(self, profile_id: str, now: datetime, *,
                        correo: str | None = None, telefono: str | None = None) -> bool
def crear(..., public_id: str, correo: str | None = None, telefono: str | None = None) -> Profile
```

El cruce por `id` usa `buscar_por_id` ya existente. Prioridad del cruce: id, correo,
teléfono; si dos claves apuntan a perfiles distintos, estado `conflicto` (R23).

## 4. Rutas (admin_routes.py)

| Método y ruta | Resultado |
|---|---|
| `GET /admin/clientes/importar` | Formulario `multipart/form-data` con `csrf_token` y documentación de columnas. |
| `POST /admin/clientes/importar/vista-previa` | Parsea, construye plan, guarda en `ImportStaging`, muestra vista previa con selector de política y `token` oculto. |
| `POST /admin/clientes/importar/confirmar` | Ejecuta; muestra resumen; `409 vista_previa_expirada` si el token no existe. |
| `GET /admin/clientes/importar/resumen/{token}` | `text/csv`, `Content-Disposition: attachment`; solo mismo `session_id`. |

Los errores de archivo devuelven `422` con el código. El límite de bytes se aplica
leyendo el `UploadFile` en bloques y abortando al superar el máximo (R8), antes de
decodificar. Las rutas de importación se registran junto a las demás de
`/admin/clientes`, por lo que heredan la exigencia de rol admin (R2).

## 5. Reglas de validación y normalización

- `usuario`: minúsculas, `USERNAME_PATTERN` (reutilizado de `admin_routes`).
- `id`: `normalize_public_id`; `None` si vacío (se genera con `generate_public_id`).
- `correo`: regex simple `^[^@\s]+@[^@\s]+\.[^@\s]+$`, ≤254, minúsculas.
- `telefono`: se quitan espacios, guiones y paréntesis; válido con 7-15 dígitos y
  `+` inicial opcional.
- Se rechazan caracteres de control en cualquier campo. Separador: se cuenta `;` vs
  `,` en la línea de encabezado (gana el mayor; empate = coma); se usa `csv.reader`
  de la biblioteca estándar con `utf-8-sig`.
- Una fila duplicada en archivo se evalúa solo contra filas previas **válidas**.

## 6. Credencial inactiva (R37, R38)

El cliente importado se crea con `password_hash = "importado$deshabilitado"` (sin
prefijo `scrypt`/`pbkdf2`, así `verify_password` devuelve siempre `False`),
`valid_from = now - 1 día` y `valid_until = now`, es decir, vencida según
`credential_status`. Nunca se llama `hash_password_scrypt` con un valor del archivo.

## 7. Esquema y privacidad (R39-R41)

Sentencias añadidas a la lista de esquema: `ALTER TABLE profiles ADD COLUMN IF NOT
EXISTS email TEXT`, `... phone TEXT`, `... contact_updated_at TIMESTAMPTZ` e índices
no únicos sobre `email` y `phone` (la unicidad se decide en la aplicación, no en la
base, para poder informar duplicados). `update_client_contact` y la creación fijan
`contact_updated_at`. La supresión existente (`execute suppression`) pone `email`,
`phone` y `contact_updated_at` en nulo; `purge_personal_data(cutoff, ...)` lo hace
para los perfiles con `contact_updated_at < cutoff`. Se hace en ambos repositorios
(memoria y Postgres) con la misma semántica.

## 8. Auditoría y registro (R35, R42)

`client_import_preview` y `client_import` con `target=None` y `detail` solo con
totales y códigos. Ningún evento ni CSV contiene correo ni teléfono; en la vista
HTML el contenido se escapa con `_esc`.

## 9. Alternativas descartadas

1. **Guardar el archivo (disco o tabla) entre vista previa y confirmación:** viola
   «el archivo no se guarda»; se prefiere staging en memoria con TTL y un uso.
2. **Re-subir el archivo en la confirmación:** el admin podría confirmar un archivo
   distinto al previsualizado y se duplica el parseo; se descartó.
3. **Campos ocultos con todas las filas en la confirmación:** 1000 filas en HTML,
   manipulables por el cliente; el estado de confianza queda en el servidor.
4. **Excel `.xlsx`:** soportado desde 2026-11-22 con `openpyxl` (MIT), aprobado por el dueño; primera hoja, solo valores, mismos límites.

## 10. Dependencias nuevas

`openpyxl` (MIT) para `.xlsx`, aprobada por el dueño el 2026-11-22; el resto es biblioteca estándar.

## 11. Supuestos (defaults seguros, configurables donde aplica)

- S1 «nombre» del acceptance = `usuario`; el cliente no tiene otro campo de
  nombre y no se amplía el esquema más allá de correo y teléfono.
- S2 Política de duplicados única para todo el archivo; «Saltar» por defecto.
- S3 Actualizar solo toca `correo` y `telefono`; nunca `usuario`, credencial ni
  `id`. Una fila vacía en esos campos no borra el dato existente.
- S4 Límites: 1 MiB, 1000 filas, TTL 900 s (variables en `.env.example`).
- S5 El staging es en memoria de un proceso; con varios workers la confirmación
  puede dar `vista_previa_expirada` y se repite la vista previa (el despliegue
  actual es de un proceso).
- S6 «Habilitar con el flujo actual»: el flujo existente solo permite renovar la
  vigencia; no existe hoy un flujo para fijar la contraseña de un cliente ya
  creado. Esta feature no lo añade. El cliente importado queda sin acceso hasta
  que exista ese flujo (o se cree uno nuevo con «Nuevo cliente»). Se reporta como
  limitación, no como bloqueo.
- S7 Retención de correo/teléfono: se reutiliza `PRIVACY_RETENTION_DAYS`, sin
  variable nueva.
