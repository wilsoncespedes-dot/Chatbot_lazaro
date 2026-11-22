# Implementación #61 `registro_canales_gateway`

Estado: T1–T10 hechas. Feature sin marcar `done` (pendiente de revisión).

## Resultado de `./init.sh`

Verde: `3879 passed, 1 skipped, 2 warnings` (156 s). Los avisos son de
deprecación de `httpx`/Starlette y de Pydantic en tests del orquestador, ajenos
a #61.

## Mapa R → test

Rutas relativas a `services/telegram_gateway/tests/` (gateway) y
`contracts/tests/` (contratos). La asignación sigue el campo «Cubre» de cada
task en `specs/registro_canales_gateway/tasks.md`.

| Requisito | Archivo de test | Task |
|---|---|---|
| R1, R2, R3, R4 | `contracts/tests/test_registro_canales_contrato.py`, `contracts/tests/test_canal_abierto_doc.py` | T1 |
| R5–R9, R11–R14 | `test_registro_canales.py` | T4 |
| R10, R15 | `test_canales_rutas.py` (búsqueda de nombres de canal en `main.py`, `registry.py`, `channel_service.py`; webhooks con almacén caído) | T8 |
| R16–R21 | `test_degradacion.py`, `test_canal_abierto.py` | T3 |
| R22–R26 | `test_canales_rutas.py` (`/send`: 422, 502, `channel_inactive`, 503) | T8 |
| R27, R28, R30, R31 | `test_canales_repositorio.py` | T6 |
| R29 | `test_canales_repositorio.py`, `test_canales_secretos.py`, `test_canales_rutas.py` | T6/T7/T8 |
| R32 | `test_canales_rutas.py` (arranque con almacén caído, siembra diferida) | T8 |
| R33, R35 | `test_canales_secretos.py` | T5/T7 |
| R34 | `test_canales_despliegue.py` (`Settings` de producción válida sin clave) | T2 |
| R36, R37 | `test_canales_rutas.py`, `test_canales_secretos.py` (WARNING `missing`/`invalid`, logs sin secretos) | T8/T5 |
| R38, R39 | `test_canales_rutas.py` (401 en cada ruta, listado sin secretos) | T8 |
| R40–R47 | `test_canales_secretos.py` (servicio), `test_canales_rutas.py` (HTTP) | T7/T8 |
| R48, R49 | `test_canales_secretos.py` (auditoría sin valor, 404), `test_canales_rutas.py` | T7/T8 |
| R50 | `test_canales_rutas.py`, `test_health_dependencies.py` (`/health` con Postgres caído) | T8 |
| R51, R54 | `test_canales_despliegue.py` (compose y `render.yaml`) | T9 |
| R52, R53 | `test_canales_despliegue.py`, `test_telegram_gateway_app.py::test_requirements_txt_matches_design` | T2 |
| R55 | Batería completa de `contracts/tests` y `services/telegram_gateway` en verde, más el resto del repositorio vía `init.sh` | T1–T10 |

## Tests existentes sustituidos (design §7)

Se sustituyen, no se debilitan; ningún otro test existente se tocó.

1. `test_canal_abierto.py::test_send_image_block_is_rejected_on_current_channels`.
   Motivo: R40 de #60 era temporal («hasta que #61 la degrade»). Sustituto:
   `test_send_image_block_is_degraded_on_current_channels` (200 y el enlace llega
   al canal).
2. `test_canal_abierto.py::test_send_response_rejects_image_without_capability`.
   Motivo: idem. Sustituto:
   `test_send_response_degrades_image_without_capability` (`send_response`
   entrega un `LinkBlock`).
3. `test_telegram_gateway_app.py::test_requirements_txt_matches_design`. Motivo:
   la lista exacta era de 6 dependencias y el dueño decidió añadir `pg8000` y
   `cryptography`. Sustituto: el mismo test con la lista de 8 (R52).
4. `contracts/tests/test_canal_abierto_doc.py::test_send_and_messages_document_temporary_rejections`.
   Motivo: exigía el texto temporal de `/send` (rechazo de `image` y canales que
   no son `telegram` ni `whatsapp`). Sustituto:
   `test_send_and_messages_document_channel_registry_behaviors`: la parte de
   `/send` comprueba el texto de R4; la de `POST /messages` se conserva literal
   (la guarda sigue hasta #65).

`UnsupportedBlock` se conserva en `domain.py` (ya no se lanza) para no romper
imports.

## Nota para el dueño (design §11)

Acción opcional en el servidor: añadir al `.env`
`CHANNEL_SECRETS_KEY=<python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">`.

Sin esa clave, Telegram y WhatsApp funcionan igual. El arranque registra
`channel_secrets_key_unavailable reason=missing`, y solo crear canales o
ver/regenerar secretos responde 503. `DATABASE_URL` ya está en el `.env`
compartido; con `depends_on` el gateway espera a que `postgres` esté sano.
Cambiar la clave más adelante deja ilegibles los secretos ya guardados (S6).
