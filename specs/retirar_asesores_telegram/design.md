# Design — retirar_asesores_telegram

## Objetivo

Eliminar Telegram como interfaz de asesores y usar siempre el perfil autenticado del panel como identidad. Los canales de cliente y `/consultar` permanecen sin cambios. Se conservan los estados y la matriz de autorización S12/S14; el roster persistido en handover sustituye a `ADVISOR_CHAT_IDS`.

## Archivos a modificar

### `contracts/`

- `contracts/CONTRATOS.md`: actualizar S6, S12, S13, S14 y secciones de rutas existentes. Definir `advisor_id` como `profile_id`; especificar `POST /advisors/sync` con token, request/response, errores `401/422/500`, y header de generación; definir respuesta de `POST /handover` (`queued | no_advisors`), respuesta de `/client-message` (`available_in_panel | not_assigned`), política de casos huérfanos, migración y fallos cerrados.
- `contracts/lazaro_contracts/cases.py`, `__init__.py`: modelos `AdvisorRosterSyncRequest`/`AdvisorRosterSyncResponse` para el nuevo endpoint interno, así como las literales actualizadas en `HandoverResponse` y `CaseClientMessageResponse`.
- `contracts/examples/`: ejemplos request/response para sincronización, handover con asesores y sin asesores, y mensaje de cliente disponible en panel.
- `contracts/tests/`: validar ejemplos y rechazar identidad o estados de respuesta inválidos; comprobar documentación/modelos de errores y la autenticación de la nueva ruta en pruebas del servicio.

### `services/handover/`

- `handover/config.py`: retirar `advisor_chat_ids` y su validador.
- `handover/main.py`: añadir `POST /advisors/sync` protegido por `X-Service-Token`; adaptar endpoints de caso para aceptar el header interno `X-Advisor-Roster-Generation`, comparar su valor con la generación sincronizada y devolver `503 roster_out_of_sync` ante discrepancia.
- `handover/domain.py`: roster persistido, decisión `no_advisors`, lista y autorizaciones por profile id; quitar envío/registro de avisos Telegram nuevos; preservar cierre idempotente, asignación condicional, transferencias y orden S12.
- `handover/adapters/repository.py`: protocolo, fake y Postgres para leer/reemplazar roster transaccionalmente, mapear asignaciones antiguas y mantener huérfanos; aplicar migración idempotente al inicializar.
- `handover/adapters/gateway.py`: eliminar dependencias de notificación a asesores en Telegram; conservar envío de mensajes de cliente y avisos de vencimiento al cliente.
- Pruebas afectadas: `test_handover.py`, `test_authorization.py`, `test_list_cases.py`, `test_transfer.py`, `test_assign_close_races.py`, `test_client_message.py`, `test_config.py`, `test_startup.py`, `test_security.py`, `test_repository.py`, `test_handover_app.py`, y nuevas pruebas de sincronización/migración si hace falta. No eliminar aserciones de autorización; adaptar sus identidades.

### `services/orchestrator/`

- `orchestrator/domain.py`: retirar reconocimiento y ejecución de `/responder` y `/cerrar`; mantener el comportamiento ordinario del mensaje y `/consultar`. Cambiar respuesta de `client-message` para reflejar disponibilidad en el panel, no reenvío Telegram.
- `orchestrator/config.py`: retirar configuración/textos exclusivos de comandos de asesor.
- `orchestrator/advisor_routes.py`: `_advisor_id` toma `session.profile.id`, no `telegram_user_id`; no rechaza asesor sin enlace Telegram.
- `orchestrator/admin_routes.py` y `orchestrator/admin.py`: después de alta/cambio de rol de perfil, incrementar generación y marcar sincronización `pending` en la base compartida del orchestrator en la misma transacción que el cambio; intentar publicar roster completo y marcar `synced` solo si la generación no cambió entretanto.
- `orchestrator/adapters/repository.py`: añadir tabla compartida `advisor_roster_sync(singleton_id, generation, status)` y operaciones transaccionales para leer estado, incrementar generación/poner `pending` y confirmar `synced` solo para la generación esperada. Todas las instancias consultan esta fila persistida en cada operación dependiente; no se usa un flag local.
- Pruebas afectadas: `test_advisor_commands.py`, `test_advisor_panel.py`, `test_case_reply.py`, `test_client_forward.py`, `test_authorization.py`, `test_config.py`, `test_admin.py`, `test_accounts.py`, pruebas de adaptadores y seguridad; probar que el comando Telegram nunca llama a reply/close/send para el caso.

### Configuración, despliegue y documentación

- `.env.example`, `docker-compose.yml`, `render.yaml`: quitar `ADVISOR_CHAT_IDS` y descripciones de comandos de asesor; la URL interna y `SERVICE_TOKEN` existentes protegen sincronización.
- `docs/proyecto.md`, `docs/architecture.md`, `docs/especificacion.md`, `docs/conventions.md` y cualquier guía de operación que describa comandos o IDs Telegram como interfaz de asesores: describir panel, roster y migración. Mantener contexto histórico solo donde se identifique expresamente como histórico.
- `progress/current.md` y `progress/impl_retirar_asesores_telegram.md`: documentar implementación y trazabilidad al cerrar la feature.

## Contratos y firmas

```python
class AdvisorRosterEntry(ContractModel):
    profile_id: Identifier
    role: Literal["asesor", "otro"]
    telegram_user_id: Identifier | None = None  # solo para migrar asignaciones anteriores

class AdvisorRosterSyncRequest(ContractModel):
    generation: int
    profiles: list[AdvisorRosterEntry]

class AdvisorRosterSyncResponse(ContractModel):
    status: Literal["synced"]
    generation: int
    advisors: int
    orphaned_cases: int

def sync_advisor_roster(req: AdvisorRosterSyncRequest, settings, adapters) -> AdvisorRosterSyncResponse
```

`POST /advisors/sync` es interno y exige `X-Service-Token`: `401 unauthorized` sin token válido, `422 validation_error` si request/generación no valida, `500 internal_error` ante fallo de persistencia. Responde `200` con `status=synced`, generación aplicada, conteo de asesores y huérfanos. `role == "asesor"` define habilitación: el esquema vigente de perfiles no tiene campo separado `enabled`. Orchestrator envía la lista completa al arrancar y después de cada cambio de rol o perfil pertinente; handover reemplaza su snapshot dentro de una transacción. Handover no consulta directamente la base de orchestrator.

Se conservan los campos `advisor_id` de contratos de casos por compatibilidad estructural; desde este cambio su valor es `profile_id`. `HandoverResponse.status` pasa de `notified | no_advisors` a `queued | no_advisors`. `CaseClientMessageResponse.status` pasa de `forwarded | not_assigned` a `available_in_panel | not_assigned`, porque el mensaje queda consultable en la conversación del panel y no se envía a una cuenta Telegram.

## Migración de datos

1. Crear tabla `handover_advisors(profile_id TEXT PRIMARY KEY, telegram_user_id TEXT NULL)` con índice único parcial sobre `telegram_user_id` no nulo. No se conserva un estado `enabled` adicional; pertenencia al snapshot completo y rol asesor representa habilitación.
2. Añadir versión de esquema/migración transaccional idempotente. Al recibir el roster nuevo, antes de exponerlo a acciones, transformar cada `handover_cases.advisor_id` que coincide con un `telegram_user_id` del snapshot en su `profile_id`.
3. Todo caso `assigned` cuyo antiguo ID no tenga perfil vinculado queda con `advisor_id = NULL` y se considera huérfano conforme a S12/S14. No cambia su estado a `open` ni se borra su caso.
4. Reemplazar snapshot y migrar casos en la misma transacción. Conservar casos, mensajes, notificaciones/auditoría ya existentes y sus timestamps; no crear avisos nuevos. Una repetición no vuelve a interpretar IDs ya migrados como Telegram.
5. Orchestrator mantiene la generación y estado `pending|synced` en una fila singleton de su base compartida. Cada cambio del perfil incrementa la generación y fija `pending` en la misma transacción; todas las instancias consultan esa fila desde Postgres antes de permitir handover o acción de asesor. Mientras sea `pending`, responden fail-closed sin llamar a handover. Una instancia publica la generación completa a handover; handover actualiza roster, migración y generación en la misma transacción. Orchestrator marca `synced` solo si la generación compartida aún coincide con la sincronizada. Si hay una actualización concurrente o fallo, queda `pending`; cualquier otra instancia puede reintentar sincronización. Cada llamada dependiente envía `X-Advisor-Roster-Generation`; handover exige igualdad exacta con su generación durable y devuelve `503 roster_out_of_sync` si la petición va atrasada o adelantada. Al arrancar, ninguna instancia procesa tráfico dependiente antes de completar la reconciliación inicial.

No se requiere alterar el tipo de `handover_cases.advisor_id` (ya es `TEXT`). La tabla de notificaciones históricas puede seguir almacenando sus filas antiguas; no se insertan filas en ella para avisos de nuevos casos. El header `X-Advisor-Roster-Generation` se exige en `POST /handover` y operaciones de asesor (`authorize`, `reply`, `assign`, `transfer`, `close`, `GET /cases`); no se exige en mensajes de cliente.

## Comportamiento y errores

- `/responder` y `/cerrar` ya no se parsean como acciones. El texto entra por las compuertas actuales como entrada ordinaria. Se conserva el parser y flujo de `/consultar`.
- Los adaptadores de panel operan con el ID de perfil de la sesión. La protección entre servicios sigue siendo `X-Service-Token`; la autorización por caso sigue en handover. Operaciones dependientes incluyen `X-Advisor-Roster-Generation` y rechazan versiones distintas con `503 roster_out_of_sync`.
- Para `open` y `timed_out`: asesores del roster pueden responder, asignar o cerrar; una respuesta primera asigna al actor.
- Para `assigned`: solo el dueño responde/transfiere/cierra. Un asignado cuyo ID está nulo o ausente del roster es huérfano; otros asesores solo pueden cerrarlo. No se agrega reasignación.
- Se conservan precedencia S12, cierre repetido S8, asignación S11, lista S14 y fail-closed del orquestador cuando handover falla.
- Un caso nuevo sin perfiles asesor habilitados responde `no_advisors`; Orchestrator envía el `NO_ADVISORS_REPLY` vigente. No se llaman `POST /send` para avisar asesores.
- Mensajes del cliente de casos asignados quedan en el historial que alimenta el panel, sin envío Telegram a personal.

## Alternativa descartada

Mantener IDs Telegram como claves internas o agregar una segunda lista `ADVISOR_PROFILE_IDS` duplicaría las fuentes de verdad y mantendría el enlace de Telegram como requisito operativo. El perfil del panel ya autentica la identidad y es la fuente de roles; handover mantiene una instantánea de esa fuente para decidir autorizaciones y huérfanos sin cruzar bases de datos.

## Excepciones y dependencias

Se reutilizan los errores actuales `forbidden`, `not_found`, `case_closed`, `validation_error`, `upstream_error` y los errores HTTP definidos por ruta. La sincronización inválida responde `422`; token inválido `401`; fallo de persistencia `500`; generación distinta responde `503 roster_out_of_sync`. No se añade dependencia externa. Los fakes de repositorio y cliente deben simular roster, generaciones y fallos de sincronización.

## Supuestos cerrados por aceptación

- Un perfil se considera habilitado para atender cuando su rol es `asesor`; no se inventa otro estado de cuenta.
- El identificador antiguo se puede migrar solo cuando coincide exactamente con `telegram_user_id` de un perfil. Sin coincidencia, se conserva el caso como huérfano.
- No hay aviso Telegram para nuevos casos ni reenvío Telegram de mensajes de clientes a asesores; el panel consulta los registros persistidos.
- No se amplía el alcance a supervisor, reasignación general, cambios de flujo de clientes ni retiro de `/consultar`.
