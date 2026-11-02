# Propuesta — etapa 2 (features #10 a #16)

Fecha: 2026-10-31. Estado: **pendiente de revisión humana**. Las 7 features están en
`feature_list.json` con `"status": "blocked"` para que `./nocturno.sh` no las tome (en modo
nocturno el `reviewer` aprobaría los supuestos de negocio en lugar del humano). Al aprobarlas,
el leader las pasa a `pending` y sigue el flujo SDD normal (spec → revisión → ⏸ → implementación).

Base: features #1-#9 `done`, 674 tests.

## 1. Lo que ya existe (para no duplicar)

| Necesidad | Ya cubierto | Hueco real |
|---|---|---|
| Vencimiento | `POST /cases/check-timeouts` (handover); `CONTRATOS.md` ya dice «Llama: worker o cron» | Nadie la llama. Además `update_case` reescribe todos los campos: un vencimiento o una reutilización simultáneos con una asignación la deshacen (la carrera dura lo que tarde el envío al gateway, hasta `HTTP_TIMEOUT_SECONDS=10`) |
| Registro de traspasos | Orquestador: evento `handover` por solicitud + historial completo. Handover: una notificación por aviso a asesor | Handover no guarda nada de la solicitud si no hay asesores; al reutilizar un caso, `last_messages` se reemplaza |
| Asesores | `ADVISOR_CHAT_IDS` solo en handover; entradas no numéricas se descartan en silencio (R23 de la #7) | Una errata deja el sistema en `no_advisors` sin aviso |
| Autorización | `X-Service-Token` en todas las rutas internas | `advisor_id` es lo que declare quien llama; nadie comprueba que sea asesor ni que el caso sea suyo |
| Conversación | `POST /cases/{id}/reply` (asesor → cliente, por HTTP) | Los mensajes del cliente siguen yendo al RAG aunque el caso esté asignado; el asesor no puede responder desde Telegram |

## 2. Features propuestas

| # | name | Servicios | Contrato | Depende de |
|---|---|---|---|---|
| 10 | `validacion_config_asesores` | handover | no | — |
| 11 | `registro_solicitudes_traspaso` | handover | no | — |
| 12 | `vencimiento_automatico` | scripts, compose, handover | no (la ruta ya existe) | — |
| 13 | `contrato_autorizacion_asesores` | contracts | **sí** | — |
| 14 | `autorizacion_asesores` | handover, orchestrator | consume #13 | #13; recomendada tras #10 |
| 15 | `contrato_conversacion_caso` | contracts | **sí** | — |
| 16 | `conversacion_cliente_asesor` | orchestrator, handover | consume #15 | #15, #14; recomendada tras #10 |

```
#10 ─┬──────────────► #14 ──► #16
#13 ─┘                 ▲       ▲
#15 ───────────────────┼───────┘
#11  (independiente)   │
#12  (independiente)   └─ #16 necesita #14: sin autorización, cualquiera podría usar /responder
```

Los ids siguen el orden de ejecución recomendado (`nocturno.sh` las procesa por id).

Criterios de diseño aplicados:
- **Handover es el único dueño** de los casos y de la lista de asesores. El orquestador nunca lee
  `ADVISOR_CHAT_IDS` ni la base de handover: pregunta por HTTP (principio 1).
- **Contratos primero**: las dos rutas nuevas van en features de contrato propias (#13, #15),
  como se hizo con la #9 (principio 2).
- **Sin servicios HTTP nuevos.** El único proceso nuevo es `timeouts_worker` (#12), que ejecuta
  un script; su `design.md` deberá justificarlo (§1 de `docs/architecture.md`).

## 3. Decisiones que necesito del humano

Ninguna se ha tomado. Cada una figura como «Supuesto (requiere aprobación)» en el acceptance.

| # | Decisión | Propuesta | Alternativa |
|---|---|---|---|
| 10 | Cambiar R23 de la #7: no numérico → el servicio no arranca (modifica la expectativa de un test existente) | Sí | Mantener el descarte silencioso y solo avisar en el log |
| 10 | Id repetido | Error de arranque | Eliminarlo y avisar en el log |
| 10 | Ids negativos (grupos) | Válidos, como hoy | Rechazarlos |
| 11 | Copia de `last_messages` por solicitud (Ley 1581) | No copiar; guardar solo cuántos mensajes llegaron (el historial ya está en el orquestador) | Copiar para auditar lo que vio el asesor |
| 12 | Intervalo | 60 s (aviso al cliente entre 300 y 360 s) | Otro valor |
| 12 | Quién lo ejecuta en Render | Decidir aparte; la feature entrega script y servicio de compose | Render Cron Job / worker (de pago) / GitHub Actions `schedule` (≥ 5 min, con retrasos) |
| 14 | Quién es asesor | `ADVISOR_CHAT_IDS` hasta que existan el panel y la verificación | — |
| 14 | Reglas | `open`/`timed_out`: cualquier asesor registrado responde y la 1.ª respuesta asigna; `assigned`: solo el asignado responde y cierra; sin reasignación ni supervisor | Permitir reasignar o un rol supervisor |
| 14 | Cerrar un caso sin asignar | Cualquier asesor registrado | Solo tras asignar |
| 14 | Handover caído al autorizar | Falla cerrado: no se envía, `502` | Enviar igualmente |
| 16 | Qué casos reenvían mensajes del cliente | Solo `assigned`; con `open` sigue el RAG | Reenviar también con `open` a todos los asesores avisados |
| 16 | Cómo responde el asesor | Comandos `/responder <case_id> <texto>` y `/cerrar <case_id>` | Contestar al aviso (exige `message_id` en `POST /send`: otro contrato) |
| 16 | Mensaje de un asesor que no es comando | Se trata como el de un cliente (como hoy) | Ruta nueva para que handover diga si un chat es de un asesor |
| 16 | Falla el envío al asesor | Texto fijo al cliente + evento `forward_failed` | Volver al RAG |
| 16 | Confirmaciones | Confirmación fija al asesor y aviso fijo al cliente al cerrar | Sin mensajes |

## 4. Limitación que hay que aceptar o resolver

Por HTTP, quien llama se autentica con `SERVICE_TOKEN` y declara el `advisor_id`. La #14 impide
que un asesor no registrado o ajeno al caso responda, pero no que alguien con el token se haga
pasar por un asesor registrado. La identidad real por persona llega con la identidad de Telegram
(#16, garantizada por `TELEGRAM_WEBHOOK_SECRET`) o con el panel y la verificación de cuentas
(lista `later`).

## 6. Decisiones del humano (2026-10-31)

Incorporadas al acceptance de cada feature como «Decidido por el humano (2026-10-31)».
Las siete features siguen `blocked` hasta que el humano revise sus specs.

- **#10:** una entrada no numérica o un id duplicado impiden el arranque; los negativos son
  válidos; las vacías se ignoran; con la lista vacía arranca y deja un aviso en el log. Se acepta
  cambiar R23 de la #7 y su test.
- **#11:** registrar cada solicitud (también sin asesores o al reutilizar un caso). Sin copia de
  `last_messages`: solo el conteo y los demás datos de auditoría propuestos.
- **#12:** intervalo inicial de 60 s; script y servicio de Compose. Queda pendiente cómo se
  ejecuta en Render hasta revisar costes y límites.
- **#13 y #15:** contratos según la propuesta.
- **#14:** `ADVISOR_CHAT_IDS` define quién es asesor. Con `open`/`timed_out` responde cualquier
  asesor registrado y la primera respuesta asigna; con `assigned` solo responde el asignado. Sin
  reasignación ni supervisor. Cualquier asesor registrado cierra un caso sin asignar. Si handover
  no está disponible, falla cerrado y no envía. (Cerrar un caso `assigned`: solo el asignado,
  según la propuesta, que el humano no cambió.)
- **#16:** reenviar al asesor mientras el caso esté `assigned`; con `open`, flujo actual con RAG.
  Comandos `/responder` y `/cerrar`. Los mensajes de asesores que no son comandos siguen el flujo
  actual. Si falla el reenvío: texto fijo y evento `forward_failed`, sin volver al RAG.
  Confirmación al asesor y aviso al cliente al cerrar.
- **Identidad:** documentar que la autorización por HTTP con `SERVICE_TOKEN` no impide que un
  proceso que ya tenga ese token suplante el `advisor_id`. En Telegram, el `advisor_id` es el id
  del remitente del webhook validado, nunca un id escrito en el mensaje.

## 5. Siguiente paso

1. El humano aprueba o cambia las decisiones de §3 (y la limitación de §4).
2. El leader traslada las decisiones al acceptance de cada feature, las pasa a `pending` y lanza
   `spec_author` una a una. En modo supervisado cada spec se para en `spec_ready` para su aprobación.
