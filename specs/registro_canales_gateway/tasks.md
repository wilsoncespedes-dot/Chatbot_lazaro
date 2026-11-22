# Tasks — #61 `registro_canales_gateway`

Orden pensado para que la batería quede verde al final de cada paso. Rutas del
gateway relativas a `services/telegram_gateway/`. Los cuatro tests de
`design.md` §7 se sustituyen en el mismo paso que cambia su comportamiento; no
se toca ningún otro test existente. Ejecuta `python -m pytest contracts/tests` y
`python -m pytest services/telegram_gateway` al cerrar cada paso.

- [x] T1 — **Contratos primero.** `contracts/lazaro_contracts/channels.py`: extraer
  `check_json_object(value, max_bytes, max_depth)` y usarla en `metadata` sin
  cambiar su comportamiento. Crear `contracts/lazaro_contracts/channel_registry.py`
  con las constantes y los siete modelos de design §3 y exportarlos en
  `__init__.py`. `CONTRATOS.md`: sección «Canales (registro del gateway)» con las
  seis rutas en el formato estándar, ejemplo JSON por ruta y la equivalencia con
  las columnas; actualizar «Variante canónica de POST /send», la fila 422 y las
  nuevas filas de errores de `POST /send`, una subsección «Degradación por
  capacidades», la fila de `ImageBlock`, «Salud» (Redis y PostgreSQL en
  `telegram_gateway`), la tabla común de errores (`channel_exists`,
  `channel_managed_by_environment`, `channel_inactive`,
  `channel_secrets_unavailable`, `channel_store_unavailable`) y S17. Crear
  `contracts/tests/test_registro_canales_contrato.py` (exports, `extra="forbid"`,
  límites parametrizados, formato de cada sección, ejemplos que validan, texto de
  `/send`, degradación y salud). Sustituir la parte de `/send` de
  `test_canal_abierto_doc.py::test_send_and_messages_document_temporary_rejections`
  conservando literal la de `POST /messages`. Cubre: R1, R2, R3, R4, R55.

- [x] T2 — **Configuración y dependencias.** `requirements.txt`: añadir
  `pg8000>=1.31,<2` y `cryptography>=44,<48`. `config.py`: `database_url: str = ""`
  y `channel_secrets_key: SecretStr = SecretStr("")`, sin validación de formato ni
  cambios en `REQUIRED_IN_PRODUCTION`. `.env.example`: en el bloque
  `# telegram_gateway`, `CHANNEL_SECRETS_KEY=` vacía con comentario y el comando de
  `Fernet.generate_key()`. Sustituir
  `test_telegram_gateway_app.py::test_requirements_txt_matches_design` por la
  lista de 8. Crear `tests/test_canales_despliegue.py` con las pruebas de R52 y R53
  (incluida `Settings` de producción válida sin clave). Cubre: R52, R53, R34, R55.

- [x] T3 — **Dominio y degradación.** `domain.py`: excepciones de design §3/§4
  (`ChannelInactive`, `ChannelNotFound`, `ChannelAlreadyExists`,
  `ChannelManagedByEnvironment`, `ChannelSecretsUnavailable`,
  `ChannelStoreUnavailable`), `ChannelRecord`, `ChannelSecrets`, `ChannelSeed`,
  `BUILTIN_CHANNEL_SEEDS`, `degrade_blocks`, `prepare_blocks`,
  `send_through_channel`; `send_response` usa `prepare_blocks` (deja de lanzar
  `UnsupportedBlock`, que se conserva); campos `channels` y `channel_registry` al
  final de `Adapters`. `adapters/telegram.py` y `whatsapp_cloud.py`
  (`whatsapp_capabilities`): capacidades nuevas explícitas. Sustituir los dos
  tests de imagen de `test_canal_abierto.py` (design §7). Crear
  `tests/test_degradacion.py`: cada regla, límite de 4096 en enlaces, pureza
  (entrada intacta, mismo resultado) y matriz de capacidades; `send_response`
  degrada antes de la ventana. Cubre: R11, R16, R17, R18, R19, R20, R21, R55.

- [x] T4 — **Puerto, registry y adaptadores.** Crear `ports/__init__.py`,
  `ports/canal.py`, `registry.py` (`ChannelContext`, `ChannelFactory`,
  `DuplicateAdapterType`, `UnknownAdapterType`, `ChannelRegistry`,
  `CHANNEL_REGISTRY`) y `adapters/channels/{__init__,telegram,whatsapp_cloud}.py`
  con `TelegramChannel` y `WhatsAppCloudChannel` registrados por decorador. Crear
  `tests/test_registro_canales.py`: `isinstance(…, Canal)`, alta, duplicado
  (conserva la original), desconocido, tipo no slug, contenido exacto del registry
  por defecto, `copy()` aislado, `recibir_mensaje` igual a la normalización del
  webhook (texto, no texto, callback con prueba, WhatsApp texto/botón/no
  soportado, payload inválido → `None`), `identificar_usuario` y `enviar_mensaje`
  con `FakeTelegramClient` y `FakeWhatsAppAdapter`, capacidades de R11 a través
  del puerto. Cubre: R5, R6, R7, R8, R9, R11, R12, R13, R14.

- [x] T5 — **Cifrado.** Crear `secret_cipher.py` (`SecretCipher` con Fernet,
  `status` `ok`/`missing`/`invalid`, `repr` sin clave). Crear
  `tests/test_canales_secretos.py` con clave generada en la prueba: ida y vuelta,
  el token no contiene el texto plano, sin clave/clave inválida/otra clave →
  `ChannelSecretsUnavailable`, `repr` de `SecretCipher` y `ChannelSecrets` sin
  valores. Cubre: R33, R35, R37.

- [x] T6 — **Repositorio.** Crear `adapters/channel_repository.py`
  (`ChannelChanges`, `ChannelRepository`, `PostgresChannelRepository`,
  `FakeChannelRepository`) replicando el patrón de handover (design §3, §5). Crear
  `tests/test_canales_repositorio.py` con conexión falsa que registra SQL y
  parámetros: esquema `CREATE`/`ALTER … IF NOT EXISTS` en la primera conexión,
  solo parámetros `%s`, listado y `get` sin `config_secreta`, siembra con
  `ON CONFLICT DO NOTHING` + `UPDATE … activo_segun_entorno`, reconexión tras error
  de conexión y tras sondeo fallido, `health_check` con timeout en conexión
  aparte; y la misma semántica de siembra en `FakeChannelRepository` (crea
  faltantes, resincroniza con la marca, respeta filas sin marca, no duplica).
  Cubre: R27, R28, R29, R30, R31.

- [x] T7 — **Servicio.** Crear `channel_service.py` (`ChannelService`, design §3 y
  §4). Pruebas unitarias en `tests/test_canales_secretos.py` y
  `tests/test_canales_rutas.py` según corresponda: siembra con WhatsApp
  disponible/no disponible, `resolve` (desconocido, tipo no registrado, no
  disponible antes que inactivo, inactivo, con secretos sin clave), crear (secreto
  de 43 caracteres distinto en cada alta, credenciales cifradas, 409, 422, 503
  sin persistir), editar (solo campos enviados, sin clave si no hay
  `credentials`), activar (quita la marca), regenerar (invalida el anterior,
  conserva credenciales), revelar, 409 de canal gestionado por el entorno, 404 y
  logs de auditoría sin valor. Cubre: R29, R30, R33, R35, R40, R41, R42, R43, R44,
  R45, R46, R47, R48, R49.

- [x] T8 — **HTTP.** `main.py`: importar `adapters.channels`; `build_default_adapters`
  con `PostgresChannelRepository(settings.database_url)`; en `create_app`, servicio,
  WARNING de clave, siembra en `lifespan` tolerante a fallos, Postgres en `/health`,
  `POST /send` por el registry (`LEGACY_SEND_CHANNEL`, sin ramas por canal) y las
  seis rutas `/channels…`. Completar `tests/test_canales_rutas.py`: 401 en cada
  ruta, listado sin secretos ni token y con `adapter_types`, alta/edición/activación/
  secretos por HTTP con un tipo falso en `CHANNEL_REGISTRY.copy()`, `/send` (422
  desconocido, 502 no disponible, 422 `channel_inactive`, 503 almacén con mensaje
  genérico, imagen degradada), siembra visible tras `with TestClient(...)`,
  arranque con almacén caído y siembra diferida, webhooks de Telegram y WhatsApp
  con almacén caído, servicio completo sin clave y con clave inválida, WARNING
  `missing`/`invalid`, logs capturados sin secretos, `/health` con Postgres caído
  (solo y junto a Redis) sin DSN, y la prueba que busca comparaciones con nombres
  de canal en `main.py`, `registry.py` y `channel_service.py`. Cubre: R10, R15, R22,
  R23, R24, R25, R26, R32, R34, R36, R37, R38, R39, R40, R41, R42, R43, R44, R45,
  R46, R47, R48, R49, R50.

- [x] T9 — **Despliegue.** `docker-compose.yml`: `telegram_gateway.depends_on.postgres`
  con `condition: service_healthy` (conserva `redis`). `render.yaml`: en
  `telegram-gateway`, `DATABASE_URL` con `fromDatabase` (`lazaro-postgres`,
  `connectionString`) y `CHANNEL_SECRETS_KEY` con `sync: false`. Añadir sus pruebas a
  `tests/test_canales_despliegue.py`. Cubre: R51, R54.

- [x] T10 — **Cierre.** Ejecutar `./init.sh` (verde) y escribir
  `progress/impl_registro_canales_gateway.md` con el mapa R → test, los cuatro tests
  sustituidos y su motivo (design §7) y la nota para el dueño de design §11.
  Cubre: R55.
