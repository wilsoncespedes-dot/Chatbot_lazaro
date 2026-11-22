# Design — #66 `panel_administracion_canales`

## 1. Resumen

```
navegador admin ──/admin/canales──▶ orchestrator (admin_routes + admin_channels)
                                       │ HttpChannelAdminClient (X-Service-Token)
                                       ▼
                                    gateway /channels… (#61)  ── canales (Postgres)
```

El orquestador no guarda nada de canales: renderiza, valida el formulario y
delega en el gateway. Tras cada cambio invalida su `ChannelDirectory` (#65).

## 2. Contrato

- `ChannelInfo.credential_hints: dict[CredentialName, str] = {}` (R1).
- `credential_hint(value) -> str`: `"…" + value[-4:]` si `len(value) >= 8`, si no `"…"`.
- `CHANNEL_ICONS: dict[str, str]` (R2): `chat 💬, telegram ✈️, whatsapp 🟢, web 🌐,
  correo ✉️, telefono 📞, sms 📨, instagram 📷, facebook 👥, tienda 🛒, bot 🤖,
  soporte 🛟`. Vive en `lazaro_contracts.channel_registry` para que el núcleo del
  orquestador no contenga nombres de canal (#65 R36).
- No se valida el ícono en los modelos de petición: un ícono ya guardado fuera de
  la lista se muestra como `💬`. La lista cerrada la aplica el panel (R15).

## 3. Gateway

- Columna `pistas_credenciales JSONB NOT NULL DEFAULT '{}'` (migración
  `ADD COLUMN IF NOT EXISTS`); `ChannelRecord.credential_hints`,
  `ChannelChanges.credential_hints`. Create y update con `credentials` calculan
  las pistas con `credential_hint` (R3, R4). Fake y Postgres igual.
- `_info` copia `record.credential_hints` (R1).
- `simulado.validate_config` acepta `consent_mode` (R5); la validación del valor
  ya la hace el contrato (#65 R5).
- R27 ya lo cumplen `resolve_for_webhook` (404) y `resolve` (`channel_inactive`);
  se cubre con un test de regresión.

## 4. Orquestador

### Cliente

`adapters/channel_admin.py`:

```python
class ChannelAdminError(Exception): status: int; code: str
class ChannelAdminUnavailable(ServiceUnavailable): ...
class ChannelAdminClient(Protocol):
    def list(self) -> ChannelListResponse
    def create(self, req: ChannelCreateRequest) -> ChannelCreateResponse
    def update(self, channel_id, req: ChannelUpdateRequest) -> ChannelInfo
    def set_active(self, channel_id, active: bool) -> ChannelInfo
    def reveal_secret(self, channel_id) -> ChannelSecretResponse
    def regenerate_secret(self, channel_id) -> ChannelSecretResponse
class HttpChannelAdminClient  # httpx, timeout, transport inyectable
class FakeChannelAdminClient  # en memoria; registra llamadas
```

`4xx` (salvo 401) → `ChannelAdminError(status, code)` con el `error` del cuerpo;
red, `401`, `5xx` o cuerpo inválido → `ChannelAdminUnavailable` (R18, R19).
`Adapters.channel_admin` (por defecto `FakeChannelAdminClient()` vacío;
`build_default_adapters` usa `HttpChannelAdminClient(telegram_gateway_url, …)`).
`ChannelDirectory.invalidate()` en `HttpChannelDirectory` y `FakeChannelDirectory` (R29).

### Dominio puro (`admin_channels.py`)

- `contrast_ratio(hex, "#FFFFFF")` WCAG 2.x; `valid_color(hex) -> bool` exige
  `#RRGGBB` y ratio ≥ 4.5 (R16).
- `parse_credentials(text) -> dict[str, str]`: líneas `nombre=valor`, ignora
  vacías, nombre con `CREDENTIAL_NAME_PATTERN`, valor no vacío, sin duplicados,
  máximo 20 (R17); `ValueError` si no cumple.
- `channel_form(form, *, creating) -> ChannelForm` valida id (solo al crear),
  nombre, ícono (R15), color, `consent_mode`, `callback_url` (opcional, solo se
  incluye si no está vacío) y credenciales.
- `webhook_url(base, channel_id)` (R20).

### Rutas (`admin_routes.py`)

| Ruta | Acción |
|---|---|
| `GET /admin/canales` | listado + formulario de alta |
| `POST /admin/canales` | alta; muestra secreto una vez (R12) |
| `POST /admin/canales/{id}` | edición (R13, R14) |
| `POST /admin/canales/{id}/activo` | `active=true|false` (R26) |
| `POST /admin/canales/{id}/secreto` | ver secreto (R22) |
| `POST /admin/canales/{id}/secreto/regenerar` | regenerar (R23); exige `confirmar=si` |
| `GET /admin/static/canales.js` | script del botón copiar (R30) |

Sesión con `_require_session` (solo admin, R7); CSRF con `_require_csrf_audited`
(R8). Auditoría con `_audit(actor, action, result, target=channel_id)`; nunca se
pasa el secreto (R24). Todas las páginas usan `security_headers()` (ya
`no-store`, R25).

### Vista (`admin.py::render_channels`)

Tabla de canales: etiqueta con el emoji y el nombre en blanco sobre el color
del canal (R31). La CSP actual (`default-src 'self'`) bloquea los atributos
`style`, así que la etiqueta es un `<svg>` inline con `<rect fill="#RRGGBB">` y
`<text fill="#FFFFFF">`: los atributos de presentación SVG no son estilos inline
y la CSP los permite. El color llega ya validado por el contrato (`#RRGGBB`).

Botón copiar: `<button type="button" data-copy="#id-del-input">Copiar</button>`
junto a un `<input readonly>`; `canales.js` (`defer`, mismo origen) usa
`navigator.clipboard.writeText` y, si falla, selecciona el texto. Sin JS el
campo sigue seleccionable.

Formulario de edición por canal: nombre, ícono (select de `CHANNEL_ICONS`),
color, modo de consentimiento, URL de callback (opcional) y credenciales
(textarea vacío = no cambiar; muestra las pistas). Los canales gestionados por
el entorno solo muestran nombre, ícono, color, consentimiento y activo (R14).

### Configuración

`GATEWAY_PUBLIC_BASE_URL` (opcional, `https://`, sin barra final) en `config.py`
y `.env.example`.

## 5. Bandeja (R28)

No cambia: `advisor_inbox` no filtra por `active` y `list_policies` incluye los
canales inactivos (#65). Test de regresión.

## 6. Alternativas descartadas

1. Guardar las pistas en el orquestador: el orquestador no posee canales.
2. Descifrar credenciales al listar: el listado fallaría sin clave y expondría
   más superficie; se guardan solo las pistas.
3. Script inline o `style` inline: exigiría cambiar la CSP.

## 7. Supuestos (defaults seguros)

- S1 Pista con 4 caracteres solo si la credencial mide ≥ 8.
- S2 Contraste contra blanco ≥ 4.5:1 (WCAG AA texto normal).
- S3 Regenerar pide confirmación con un checkbox `confirmar=si`.
- S4 Sin `GATEWAY_PUBLIC_BASE_URL` se muestra la ruta relativa con aviso.
