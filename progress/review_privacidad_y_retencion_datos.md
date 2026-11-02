# Review — feature #27 privacidad_y_retencion_datos

**Veredicto:** APPROVED (con requisitos pre-lanzamiento que **no** cubre el alcance de #27; ver «Riesgos pre-lanzamiento»)

Evidencia: `./init.sh` → 1854 passed, 1 warning (deprecación Starlette/httpx), según el leader. No se repitió la suite.

## Foco revisado

- **Consent gate** — `services/orchestrator/orchestrator/domain.py:802-824, 840-875`: la puerta corre
  **antes** de `get_or_create_contact`/`add_message` en la ruta de cliente. Si falta configuración,
  registra un log `privacy_not_configured` sin datos y no guarda nada. La aceptación se compara por
  igualdad normalizada (`privacy.py:17-21`); una frase vacía nunca cuenta como aceptación. El aviso
  sale por `_notify_sender`, que no guarda historial. Las rutas de personal no pasan por la puerta (R19).
- **R17/R18 síncrono** — `main.py:196-199`: `privacy_acceptance_pending` procesa la aceptación dentro
  de la petición. Si `add_privacy_consent` falla, la excepción sube antes de enviar la confirmación y
  el manejador global responde `500`. Las demás rutas siguen en BackgroundTask como antes.
- **Autorización** — los dos `POST /privacy/purge` (`orchestrator/main.py:202`, `handover/main.py:165`)
  quedan detrás del middleware `X-Service-Token`, que usa `hmac.compare_digest` y rechaza un token
  esperado vacío. No se añadieron rutas públicas. Está cubierto por `test_purge_requires_service_token`
  en los dos servicios.
- **Transacciones** — orchestrator `repository.py:1024-1078` y handover `repository.py:547-606`:
  una sola conexión bajo `threading.Lock`, todo dentro de un único `commit` y `rollback` ante
  cualquier excepción. Handover sigue el orden del design §3: `FOR UPDATE` → requests de expirados →
  casos expirados → cerrados → requests por corte → `privacy_purge_runs`. El SQL va siempre
  parametrizado (`ANY(%s)`). No hay FKs entre tablas de handover (`repository.py:260-282`), así que el
  borrado no puede fallar por integridad referencial. El rollback está probado
  (`test_postgres_purge_rolls_back_when_a_step_fails`).
- **Orden del worker** — `scripts/purgar_datos.py:83-94`: llama primero a handover y solo llama al
  orchestrator si handover devuelve `200`. Un error HTTP o de conexión → `False` → no se llama al
  orchestrator. En bucle, las excepciones no matan el proceso. Comprueba la longitud mínima del token
  en producción.
- **Borrado** — los contactos inactivos se calculan con `created_at < corte`, sin mensajes ni
  `case_links` recientes, y se borran junto con sus `case_links`. `privacy_consents`, `profiles`, la
  auditoría, `handover_notifications` y `handover_denials` no se tocan.
- **Configuración** — R1/R29 están en `REQUIRED_IN_PRODUCTION`. R2/R30 aceptan solo enteros ≥ 1.
  R3 exige la frase dentro del aviso. R31 exige `active < retention` estricto (`handover/config.py:88-97`).

## Trazabilidad requirements ↔ tests
- R1–R52: [x] mapa completo en `progress/impl_privacidad_y_retencion_datos.md`. Comprobé al azar que
  los tests nombrados existen: `test_privacy.py` (10), `test_privacy_purge.py` orch (8) y handover (8),
  `test_purgar_datos.py` (8), `test_worker_compose.py` (8), `contracts/tests/test_privacy.py` (10) y
  los `test_production_config.py` parametrizados con las variables `PRIVACY_*`.

## Tasks completas
- T1–T35: [x]
- T36: [ ] con justificación documentada en `progress/impl_privacidad_y_retencion_datos.md`. El leader
  ya ejecutó `./init.sh` en verde; el leader puede marcarla.

## Checkpoints
- C1: [x] (init.sh verde según el leader)
- C2: [x] solo #27 en `in_progress`
- C3: [x] sin dependencias nuevas; ruta documentada en `CONTRATOS.md`; SQL parametrizado; variables en `.env.example`
- C4: [x] fakes/InMemory y SQL helper; 401 probado
- C5: n/a (cierre de sesión pendiente del leader)
- C6: [x]

## Hallazgos (no bloqueantes, por prioridad)

1. **Media — TOCTOU entre la purga y un mensaje en curso** (`orchestrator/domain.py:872-875` frente a
   `repository.py:1037-1052`). Escenario: el contacto lleva más de R días inactivo y escribe justo
   mientras corre la purga. `get_or_create_contact` devuelve el contacto existente, la purga lo borra y
   después `add_message` (o `_handover` → `case_link`) escribe con un `contact_id` que ya no existe. El
   mensaje queda huérfano; si se creó un `case_link`, `reply_to_case` daría `CaseNotFound` aunque el
   caso siga vivo en handover. Es poco probable (ventana de milisegundos, una vez al día) y los huérfanos
   caen en la siguiente purga por antigüedad. Seguimiento sugerido: `ON DELETE`/FK o recrear el contacto
   en `add_message`.
2. **Baja — el update queda marcado antes de guardar el consentimiento** (`main.py:194-197`). Si el
   `INSERT` en `privacy_consents` falla, el `update_id` ya está en `processed_updates`, así que un
   reintento del gateway sale como `duplicate` y el cliente tiene que reenviar la frase. No contradice
   R17/R18; conviene documentarlo.
3. **Baja — `has_privacy_consent` corre ahora en la ruta síncrona** (`domain.py:795`). Con la privacidad
   configurada, una caída de BD convierte el `202` de cualquier mensaje de cliente en `500`. Antes el
   fallo quedaba en el BackgroundTask. Es aceptable, pero el gateway debería tolerar esos `500`.
4. **Informativa — las rutas de personal crean `contacts` sin consentimiento** (`domain.py:845-866`).
   Cualquier usuario de Telegram que escriba `/consultar`, `/responder`, `/cerrar` o `/start <token>`
   deja una fila con `telegram_user_id`/`chat_id`. Es exactamente lo que pide R19 y la purga lo borra
   por inactividad, pero queda como dato personal fuera del consentimiento y debe constar en el aviso
   (S1).

## Riesgos pre-lanzamiento (datos personales / configuración requerida)

**Bloqueantes para producción, fuera del alcance de la spec #27 (R47 solo cubre compose):**

A. **`render.yaml` no tiene worker de retención.** Solo existe `timeouts-worker` (`render.yaml:126-139`).
   En Render nadie llama nunca a `/privacy/purge`, así que **la retención no se aplica** aunque el dueño
   configure los plazos. Hay que añadir un `worker` `retention-worker` con
   `dockerCommand: python purgar_datos.py --intervalo`, la imagen de handover, `HANDOVER_URL` y
   `ORCHESTRATOR_URL` (hostport) y el grupo compartido. `test_render_blueprint.py` no lo detecta.
B. **`render.yaml` no declara las variables `PRIVACY_*`.** Con `APP_ENV=production`, orchestrator
   (5 variables) y handover (2) lanzan `ProductionConfigError` y **no arrancan**. Es el fallo cerrado
   buscado, pero el blueprint de #24 queda sin poder desplegarse tal cual. Recomendación: declarar
   `PRIVACY_RETENTION_DAYS` en el grupo `lazaro-compartido` (la prueba del design §2.1 exige el **mismo**
   valor en orchestrator y handover, y ningún código comprueba esa coherencia entre servicios). El resto
   va con `sync: false` en su servicio.
C. **`docs/despliegue.md` no menciona las variables `PRIVACY_*` ni el worker de retención.**

**Decisiones del dueño pendientes (S1–S6, sin ellas el sistema falla cerrado):** texto del aviso con
finalidades, responsable y canal de derechos; versión; frase de aceptación y respuesta; plazo de
retención; vida máxima de casos activos (debe ser < retención y cierra casos **sin aviso** al cliente
ni al asesor); conservación de `privacy_consents`. La interpretación de la Ley 1581 **no está revisada
por un abogado** (design §6).

**Fuera de alcance que sigue reteniendo datos personales:** logs de plataforma (stdout de Render),
copias de seguridad de Postgres en Render, `events` huérfanos hasta su corte, y solicitudes
individuales de supresión o revocación (no implementadas).

Recomendación al leader: abrir una feature de seguimiento (`despliegue_retencion` o ampliar #24) para
A–C antes de cualquier despliegue en producción.
