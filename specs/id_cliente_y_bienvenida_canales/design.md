# Design — id_cliente_y_bienvenida_canales (#73)

Todo en `services/orchestrator`. No cambia `contracts/` ni otros servicios. El login
sigue obligatorio y no se añade ningún mecanismo alternativo de identificación.

## Archivos

Nuevos:
- `orchestrator/client_id.py` (puro): `ALPHABET`, `ID_PATTERN`, `generate_public_id() -> str`
  (sin argumentos, `secrets.choice`, 8 chars, `XXXX-XXXX`), `normalize_public_id(raw) -> str | None`
  (mayúsculas, quita espacios y guiones, valida 8 chars del alfabeto, devuelve formateado o `None`),
  `class PublicIdGenerationError(RuntimeError)`, `class PublicIdTaken(Exception)`.
- `orchestrator/welcome.py` (puro): `channels_welcome_block(policies, intro, include_simulated) -> str`.
  Filtra activo + público (+ no simulado salvo ajuste), ordena por nombre, tope `MAX_WELCOME_CHANNELS = 10`,
  usa `icon_glyph` de `admin_channels`, texto plano del chat, enlace solo si `https://` y <= 200 caracteres.
- `orchestrator/copy_button.py` (puro): `copy_button(public_id) -> str` (HTML escapado,
  `<button type="button" class="copy-btn" data-copy="..." aria-label="Copiar ID">Copiar</button>`)
  y `COPY_JS` (JS propio). Ruta `GET /panel/copiar.js` en `panel_live_routes.py`, con el mismo
  mecanismo y cabeceras que `PANEL_LIVE_JS`; `advisor_panel._page` y `admin.render_page` incluyen
  `<script src="/panel/copiar.js" defer>` (la CSP actual ya permite `'self'`).
- Tests: `tests/test_id_cliente.py`, `test_id_cliente_chat.py`, `test_id_cliente_panel.py`,
  `test_bienvenida_canales.py`, `test_docs_login_configurable.py`.

Modificados:
- `adapters/repository.py`: protocolo, `InMemoryRepository` y `PostgresRepository`.
  - Esquema: `ALTER TABLE profiles ADD COLUMN IF NOT EXISTS public_id TEXT` y
    `CREATE UNIQUE INDEX IF NOT EXISTS profiles_public_id_key ON profiles (public_id)` (NULL permitido para staff).
  - `create_client_credential(..., public_id: str)` guarda el ID; si viola unicidad lanza `PublicIdTaken`
    (en Postgres, `UniqueViolation` del constraint `profiles_public_id_key`; un `username` repetido conserva su error actual).
  - `ensure_public_ids(generate: Callable[[], str]) -> int`: asigna ID a clientes sin él (R7), idempotente, reintenta colisiones; se llama tras crear el esquema en el arranque.
  - `find_client_by_public_id(public_id: str) -> ClientSearchResult | None` (solo lo usan rutas de panel; nunca el flujo de chat).
  - Los modelos de lectura de cliente (`ClientCredential`/fila de `list_clients`, vista de caso `client`, filas de bandeja y conversaciones) ganan `public_id: str | None`.
- `domain.py`: `create_client(...)` genera con reintento (`for _ in range(5)`) y lanza `PublicIdGenerationError` al agotar;
  `login_client` envía tras la bienvenida o suspensión el mensaje solo-ID; rama del comando de ID junto a la de logout (~línea 3269):
  `is_client_id_command(text, settings.identity_client_id_command_list)` solo con sesión activa;
  `_consent_prompt`/`_notify_consent_prompt` anexan el bloque de canales cuando `include_greeting` (usa `adapters.channels.list_policies()` dentro de `try/except` -> sin bloque).
- `identity.py`: `is_client_id_command` (misma lógica que `is_logout_command`).
- `channels.py`: `ChannelPolicy` gana `public: bool = False`, `contact_url: str = ""`, `simulated: bool = False`; `policy_from_info` los lee de `config` y de `adapter_type == SIMULATED_ADAPTER_TYPE` (mover la constante a `channels.py` o a un módulo común si hay import circular con `adapters/simulator.py`).
- `admin_channels.py`: `channel_form` acepta `public` (checkbox `si`) y `contact_url` (R35); `admin.py` renderiza los campos.
- `config.py` y `.env.example`: `IDENTITY_CLIENT_ID_COMMANDS="/id,mi id,mi id de cliente"`,
  `CHANNELS_WELCOME_INCLUDE_SIMULATED=false`, `CONVERSATION_CLIENT_ID_INTRO`, `CONVERSATION_CHANNELS_INTRO`.
- `advisor_panel.py`, `admin.py`, `advisor_routes.py`, `admin_routes.py`: ID + botón en `_client_section`,
  `render_inbox_table`, `render_conversations_table`, `render_conversation_read`, `render_advisor_case`, `render_clients`;
  ruta `GET /asesor/clientes` (asesor y supervisor) con `render_client_search`, y parámetro `q` en `GET /admin/clientes`.
- `docs/especificacion.md`: subsección «Login configurable (posibilidad, no implementada)» + ID de cliente + bienvenida con canales.
- `tests/fakes.py` y `conftest.py`: soporte de `public_id` y de canales públicos.

## Decisiones y firmas clave

- Formato: 8 caracteres de un alfabeto de 30 = ~6,5e11 combinaciones; `XXXX-XXXX` se lee y copia fácil. La búsqueda es tolerante (R21) pero no mapea caracteres ambiguos (no están en el alfabeto, así que `0`/`O` dan «ID no válido»).
- El flujo de chat nunca resuelve un ID (R13/R14): `find_client_by_public_id` solo se invoca desde rutas del panel con sesión. Un test hace que el repositorio de pruebas lance si se llama desde `process_message`.
- Mensaje solo-ID: dos `_send`, el segundo con el ID exacto, para copiarlo con una pulsación.
- Canales públicos: se guarda en `canales.config` (`public`, `contact_url`); sin columna ni migración. Por defecto ningún canal es público hasta que el admin lo marque.
- Backfill idempotente en el arranque en vez de migración manual.
- Logs: la búsqueda registra solo `client_search found=true/false`, nunca el ID.

## Excepciones

Nuevas: `PublicIdGenerationError`, `PublicIdTaken`. Se reutiliza `ChannelFormError` (R35).

## Alternativa descartada

Derivar el ID de un hash del `profile_id` (determinista, sin columna): descartado porque el ID quedaría
ligado a datos internos, no se podría rotar si se filtra y la unicidad dependería de truncar el hash. Un ID aleatorio con índice único es más simple y cumple «no revela datos».
También descartado: botón copiar con `onclick` en línea; rompería `script-src 'self'`.

## Dependencias nuevas

Ninguna.

## Supuestos a confirmar (valores por defecto configurables)

- Comandos para pedir el ID: `/id,mi id,mi id de cliente` (`IDENTITY_CLIENT_ID_COMMANDS`).
- Los canales simulados no aparecen en la bienvenida (`CHANNELS_WELCOME_INCLUDE_SIMULATED=false`).
- Ningún canal existente es público tras desplegar; el admin los marca.
- El ID se conserva mientras exista el cliente y se borra con su supresión (coherente con #72).
- Máximo 10 canales en la bienvenida (constante).
- Login configurable por empresa: solo documentado, no implementado.
