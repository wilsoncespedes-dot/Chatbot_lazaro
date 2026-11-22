# Tasks — #63 `canal_simulado`

Orden pensado para que la batería quede verde al final de cada paso. Rutas del
gateway relativas a `services/telegram_gateway/`, del orquestador a
`services/orchestrator/`. Los tests de `design.md` §7 se sustituyen en el mismo
paso que registra el tipo `simulado` en `channels/__init__.py` (T3). Ejecuta `python -m pytest contracts/tests`,
`python -m pytest services/telegram_gateway`, `python -m pytest services/orchestrator`
y `python -m pytest scripts/tests` al cerrar cada paso que los toque.

- [x] T1 — **Contratos primero.** Crear `contracts/lazaro_contracts/channel_simulator.py`
  con `MailboxEntry`, `MailboxResponse`, `SimulatedInboundRequest` y
  `SimulatedInboundResponse` (design §3), exportarlos en `__init__.py` y añadir a
  `CONTRATOS.md` la sección «Canal simulado» con las dos rutas, ejemplos JSON,
  errores, `config.capabilities`, ajustes y la nota del rechazo hasta #65. Crear
  `contracts/tests/test_canal_simulado_contrato.py` (exports, `extra="forbid"`,
  límites, ejemplos del documento que validan contra los modelos, presencia de
  los ajustes y de la nota). Cubre: R1, R2.

- [x] T2 — **Configuración y buzón.** `config.py`: los dos ajustes con rangos.
  `.env.example`: las dos variables con el comentario. Crear `adapters/mailbox.py`
  (`MailboxRepository`, `FakeMailboxRepository`, `PostgresMailboxRepository`) y
  `domain.py`: `Adapters.mailbox` al final con `None`. Crear
  `tests/test_buzon_simulado.py`: orden por id, `after`, filtro por `destination`,
  retención con reloj controlado (3600 s vs 3601 s), tope por canal, aislamiento
  entre canales, esquema `CREATE … IF NOT EXISTS`, solo parámetros `%s`,
  reconexión tras error de conexión con conexión falsa que registra SQL, rangos
  de `Settings` e igualdad de comportamiento entre falso y Postgres falso.
  Cubre: R12, R13, R14, R15, R17, R18, R39.

- [x] T3 — **Adaptador.** Crear `adapters/channels/simulado.py` (`SimuladoChannel`,
  docstring con `SIMULADO`, `has_mailbox = True`, `validate_config`, `build`,
  capacidades desde `config.capabilities`, `enviar_mensaje` al buzón por trozos,
  hooks `registrar_entrada`/`registrar_rechazo`) e importarlo en
  `adapters/channels/__init__.py`. Esto registra el tipo real `simulado`, así que
  en este mismo paso se sustituyen los tests de `design.md` §7 de gateway (tipo de
  prueba `tipo_prueba`, listas de tipos esperadas y contenido del registry; el
  ajuste de la nav de `/admin` queda en T7). Crear `tests/test_canal_simulado.py`:
  `isinstance(…, Canal)`, nombre de clase y docstring con SIMULADO, capacidades por
  defecto y personalizadas (dos canales distintos), `validate_config` (claves
  extra, tipos, valores inválidos, config vacío), `build` sin buzón →
  `ChannelNotConfigured`, `recibir_mensaje` e `identificar_usuario` (válido,
  inválido, saliente), envío: trozos ≤ 4096 en orden, `sent`, **sin sockets**
  (`socket.socket` parcheado para fallar) y `FakeCallbackClient.requests == []`,
  fallo del buzón → `failed` con solo el tipo en el log. Cubre: R3 (registry), R4,
  R5, R6, R8, R9, R10, R11, R40.

- [x] T4 — **Rutas de canal.** (Los tests de §7 ya se sustituyeron en T3.) En
  `main.py`: `build_default_adapters` y `create_app` (repositorio del buzón),
  `POST /channels` con `simulado` → `201`. Ampliar `tests/test_canal_simulado.py`
  con las pruebas de `POST /channels`, `PATCH` con config inválida → `422` sin
  persistir y la degradación de `ImageBlock` por `POST /send` hacia el buzón
  (R7). Cubre: R3, R6, R7, R16.

- [x] T5 — **Entrega compartida y rutas internas.** `webhook_service.py`: extraer
  `_deliver`, añadir `DeliveryResult`, `inject`, hooks opcionales con `getattr` y
  captura de excepciones (ERROR con el tipo); `receive` conserva el orden de #62.
  `channel_service.py`: `mailbox_channel` y `active_mailbox_channel`
  (404 uniforme, `ChannelInactive`). `main.py`: `GET /channels/{id}/mailbox` y
  `POST /channels/{id}/simulate`. Crear `tests/test_canal_simulado_rutas.py`:
  buzón con `client` y `rejected` cuando `FakeOrchestratorClient(fail=True)`
  (webhook firmado devuelve `200 accepted`, `/simulate` devuelve `forwarded=false`
  con motivo), entrada aceptada (`forwarded=true`), duplicado sin entradas
  nuevas, `401` sin token, `404` uniforme (canal inexistente / `webhook_generico`
  / `telegram`), `422 channel_inactive`, lectura de canal inactivo, `limit`
  fuera de rango, canal sin hooks (webhook genérico) igual que en #62, fallo del
  buzón sin cambiar la respuesta, dos canales simulados creados por
  `POST /channels` funcionando de punta a punta (firmar, recibir, enviar, leer),
  y la prueba arquitectónica de que `webhook_service.py`, `channel_service.py`
  y `main.py` no comparan con nombres de canal. Cubre: R19, R20, R21, R22, R23,
  R24, R25, R26, R27.

- [x] T6 — **Cliente del orquestador.** Crear `orchestrator/adapters/simulator.py`
  (`SimulatorClient`, `HttpSimulatorClient`, `FakeSimulatorClient`,
  `SimulatorUnavailable`) y `Adapters.simulator` (default `None`; falso en las
  pruebas). Crear `orchestrator/tests/test_simulator_client.py` con `httpx`
  simulado (`MockTransport`): encabezado `X-Service-Token`, solo las tres rutas,
  filtro `adapter_type == "simulado"`, errores 5xx/transporte →
  `SimulatorUnavailable`, sin secretos en la respuesta modelada. Cubre: R34 (parte),
  R35.

- [x] T7 — **Página del panel.** Crear `orchestrator/simulator_page.py`
  (`simulated_label`, `render_simulator`) y `orchestrator/simulator_routes.py`
  (rutas admin y supervisor, CSRF, validación de canal/id/texto, `303`, aviso
  `503`), registrarlo en `main.py`, añadir «Simulador» a `ADMIN_NAV_LINKS` y
  ajustar los tests de navegación (anotar en el reporte). Crear
  `orchestrator/tests/test_simulator_page.py`: admin y supervisor `200`; asesor,
  responsable de datos, cliente y anónimo rechazados sin llamar al gateway (GET y
  POST); SIMULADO en título, encabezado y etiqueta (aun si el nombre no lo
  incluye); aviso sin formulario sin canales simulados; canales no simulados
  ausentes; CSRF faltante/incorrecto; canal fuera de la lista, id y texto
  inválidos sin llamada; `303` con el canal y el id; conversación en orden con
  `client`, `reply` y `rejected` y la nota de #65; escape de `<script>`; gateway
  caído → `503` sin el token. Cubre: R28, R29, R30, R31, R32, R33, R34, R35, R40.

- [x] T8 — **Script.** Crear `scripts/simular_canal.py` (`build_body`, `sign`, `send`,
  `main` con `post` y reloj inyectables, `--url`, `--canal`, `--usuario`, `--texto`,
  `--id-mensaje`, `--secreto-env`) y `scripts/tests/test_simular_canal.py`: cuerpo
  y firma verificados por `verify_signature` del gateway y por el ejemplo de
  `CONTRATOS.md`, bytes firmados = bytes enviados, `0`/`1` según HTTP, secreto
  ausente → `2` sin imprimirlo, el secreto no se acepta por argumento ni aparece
  en la salida, fallo de red → `2` sin traza, reenviar el mismo `--id-mensaje`
  repite el cuerpo, `--help` y docstring con `SIMULADO`. Cubre: R36, R37, R38, R40.

- [x] T9 — **Guarda temporal intacta y cierre.** En
  `orchestrator/tests/test_simulator_guard.py`, afirmar que `ATTENDED_CHANNELS ==
  {"telegram", "whatsapp"}` y que `POST /messages` con un canal `simulado` sigue
  respondiendo `422`. Ejecutar `./init.sh` una vez (el leader lo hace tras el
  writer) y registrar en `progress/impl_canal_simulado.md` los tests sustituidos
  de `design.md` §7. Cubre: R41, R42.
