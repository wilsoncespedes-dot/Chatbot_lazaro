# Design — #76 `fuente_clientes_y_futuro_lazaro`

## 1. Resumen

El acceso a clientes (`find_client_by_public_id`, `list_client_credentials`,
`create_client_credential`, `get/renew/revoke_client_credential`) hoy lo llama
el dominio directamente sobre `Repository`. Se introduce un puerto fino
`FuenteDeClientes` y su implementación local que delega en el repositorio. No
cambian esquema, rutas ni contratos HTTP. No se crea ningún adaptador de Lázaro.

```
admin_routes / main / advisor_routes -> domain (create_client, list_clients_admin, ...)
                                          -> FuenteDeClientes (puerto)
                                               -> FuenteClientesLocal -> Repository
```

## 2. Archivos

| Archivo | Cambio |
|---|---|
| `services/orchestrator/orchestrator/client_source.py` (nuevo) | Puerto y `FuenteClientesLocal` (R1-R11). |
| `services/orchestrator/orchestrator/domain.py` | Campo `Adapters.client_source: "FuenteDeClientes | None" = None`; helper `client_source_of(adapters)`; `create_client`, `renew_credential`, `revoke_credential`, `list_clients_admin`, `search_client_by_public_id` usan el helper (R12-R17). |
| `services/orchestrator/orchestrator/admin.py` | `render_clients` añade la tarjeta (R18-R20). |
| `docs/architecture.md` | Sección «Fuente de clientes y adaptador LazaroClientSource (solo a futuro)» (R23-R25). |
| `services/orchestrator/tests/test_client_source.py` (nuevo) | Contrato del puerto y regresiones. |

`admin_routes.py` y `main.py` no cambian: ya llaman a las funciones de dominio
(`create_client`, `list_clients_admin`), que pasan a usar el puerto (R13, R17).

## 3. Firmas

```python
# client_source.py
class FuenteDeClientes(Protocol):
    def buscar_por_id(self, public_id: str) -> ClientSearchResult | None
    def listar(self) -> list[ClientCredentialRow]
    def crear(self, username: str, password_hash: str, valid_from: datetime,
              valid_until: datetime, now: datetime, public_id: str) -> Profile
    def actualizar(self, profile_id: str, now: datetime, *,
                   valid_until: datetime | None = None,
                   revocar: bool = False) -> bool
    def obtener_credencial(self, profile_id: str) -> ClientCredential | None

class FuenteClientesLocal:
    def __init__(self, repository: Repository) -> None
```

- `buscar_por_id` -> `repository.find_client_by_public_id`.
- `listar` -> `repository.list_client_credentials`.
- `crear` -> `repository.create_client_credential(..., public_id=public_id)`.
- `actualizar`: con `revocar=True` -> `revoke_client_credential`; con `valid_until`
  -> `renew_client_credential`; si no se indica ninguno, `False`. Si ambos,
  `ValueError`.
- `obtener_credencial` -> `get_client_credential` (necesario para renovar/revocar
  y devolver `ClientNotFound`/`CredentialRevoked`, R15). Es una operación de
  lectura adicional a las cuatro del acceptance; se documenta como parte de «buscar».

```python
# domain.py
def client_source_of(adapters: Adapters) -> FuenteDeClientes:
    return adapters.client_source or FuenteClientesLocal(adapters.repository)
```

El helper crea la fuente local si no hay una inyectada, por lo que ningún test ni
constructor existente de `Adapters` se rompe (R12, R26).

## 4. Excepciones

Se reutilizan `UsernameTaken`, `PublicIdTaken`, `ClientNotFound`,
`CredentialRevoked` (ya definidas en `domain.py` / repositorio). La fuente local no
las captura: propaga lo que lanza el repositorio (R7, R8). Para evitar importación
circular, `client_source.py` solo importa tipos bajo `TYPE_CHECKING`.

## 5. Tarjeta (admin.py)

`render_clients` inserta, antes del formulario de búsqueda, un
`<section class="card" id="futuro-lazaro"><p>…</p></section>` con el texto
literal del acceptance (R18), escapado con `_esc` (no contiene caracteres
especiales). Se renderiza siempre, también en las respuestas de error (R19).
Sin `<form>`, `<button>`, `<a>` ni `<input>` dentro (R20). Usa clases existentes;
sin CSS inline (CSP).

## 6. No hay conexión simulada (R21, R22)

No se añade variable de entorno, ajuste en `config.py`, ruta, ni clase. Un test
recorre los `.py` de `services/`, `contracts/` y `scripts/` y falla si aparece
`LazaroClientSource` o `lazaro_client` (R21); la documentación es el único lugar
donde el nombre existe. Otro test comprueba que el HTML de `/admin/clientes`
solo contiene «Lazaro» dentro de la tarjeta (R22).

## 7. Documentación (R23-R25)

Sección en `docs/architecture.md`, encabezada «Posibilidad a futuro, no
implementada»:

- `LazaroClientSource` implementaría `FuenteDeClientes`: `buscar_por_id` consulta
  a la API de Lázaro por el ID de cliente; `listar` pagina clientes; sincronizar
  copiaría altas y bajas a la base local.
- Duplicados: la clave de cruce sería el ID de cliente de Lázaro; si ya existe
  localmente se actualiza, nunca se crea otro; conflicto de usuario -> se reporta.
- Borrados: un cliente que desaparece en Lázaro se marcaría como revocado
  (no se borra el historial); uno borrado solo en local se reportaría, no se
  eliminaría en Lázaro.
- Aviso explícito: no hay acceso a la API, no se simula y no es un compromiso.

## 8. Alternativas descartadas

1. **Mover las tablas o crear una tabla `clientes` propia:** el puerto envuelve lo
   existente; migrar datos no aporta y arriesga regresión.
2. **Hacer `client_source` obligatorio en `Adapters`:** obligaría a editar todos
   los constructores de tests y de `build_default_adapters`; el default perezoso
   es equivalente y más seguro.
3. **Esqueleto de `LazaroClientSource` que lanza `NotImplementedError`:** violaría
   que no exista clase que sugiera la conexión (acceptance 4).

## 9. Dependencias nuevas

Ninguna.

## 10. Supuestos (defaults seguros)

- S1 `actualizar` agrupa renovar y revocar en una sola operación del puerto;
  los efectos de dominio (auditoría, sesión, avisos) permanecen en `domain.py`.
- S2 El texto de la tarjeta conserva «Lazaro» sin tilde, como en el acceptance.
- S3 Sin variables de entorno nuevas; `.env.example` no cambia.
