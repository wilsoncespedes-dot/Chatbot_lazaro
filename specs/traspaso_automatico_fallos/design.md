# Design — traspaso automático tras fallos (#32)

## Reutilización existente

- `process_message` ya distingue `no_relevant_chunks`, `invalid_answer`, errores de infraestructura y respuestas válidas.
- `_handover` ya registra eventos, construye `HandoverRequest`, enlaza el caso efectivo y maneja `notified`, `no_advisors` y fallos del servicio. Handover ya reutiliza el caso `open` o `assigned` del contacto.
- Reutilizar `NO_ADVISORS_REPLY` y `HANDOVER_ACK_REPLY`; no añadir rutas ni modelos de contrato.
- No copiar código de terceros: reutilizar funciones y adaptadores locales. Si se consulta `referencias/`, verificar archivo, commit y licencia; solo copiar MIT/Apache y registrar el aviso exigido.

## Cambios previstos

- `services/orchestrator/orchestrator/config.py`, `.env.example`: `AUTO_HANDOVER_FAILURE_THRESHOLD` (entero ≥ 1, default 3) y `AUTO_HANDOVER_FAILURE_REASONS` (allowlist de `no_relevant_chunks,invalid_answer`, default ambos; permite al dueño ajustar qué cuenta como fallo). Validar y fallar al inicio ante valores fuera de la allowlist.
- `orchestrator/domain.py`: sustituir la derivación inmediata de resultados elegibles por el registro de racha; al cruzar el umbral invocar `_handover` una sola vez. Respuesta válida pone la racha a cero. Si handover falla, conserva estado reintentable. Las peticiones explícitas `user_request` mantienen el flujo actual y limpian la racha.
- `orchestrator/adapters/repository.py`: extender `Repository`, `FakeRepository` y `PostgresRepository` con operaciones atómicas para registrar outcome idempotente por `update_id`, leer/actualizar racha y completar o dejar reintentable un traspaso. Tabla propia por `contact_id`; almacenar conteo, estado (`pending`/`handed_over`) y actualización. SQL parametrizado y cambios bajo el lock existente de la conexión.
- Tests nuevos en `services/orchestrator/tests/test_auto_handover.py`; ampliar tests de config/repository solo donde haga falta.
- `progress/impl_traspaso_automatico_fallos.md`: mapa R1–R14 y resultados de verificación.

## Estado de racha

La transición del resultado y su deduplicación se persisten atómicamente por conversación. Los motivos habilitados en `AUTO_HANDOVER_FAILURE_REASONS` suman uno; el default es `no_relevant_chunks,invalid_answer`. `invalid_answer` solo se incluye cuando la opción actual `INVALID_ANSWER_HANDOVER` está activa. Respuesta RAG válida pone el contador a cero y libera la siguiente racha. Fallos de RAG/LLM no se consideran una respuesta fallida del bot y no crean una derivación automática. Al alcanzar el umbral se intenta `POST /handover`; `notified` y `no_advisors` cierran la derivación de esa racha. Si el servicio falla, se deja reintentar en la siguiente consulta elegible; `/handover` conserva su semántica de reutilizar casos activos. No se reintenta tras `notified` ni `no_advisors` hasta que una respuesta válida abra una nueva racha. Las solicitudes duplicadas con el mismo `update_id` no alteran el estado.

## Firmas internas previstas

- `Repository.record_rag_outcome(contact_id, update_id, outcome, threshold, failure_reasons) -> bool` — registro idempotente; indica si debe intentar derivar.
- `Repository.reset_rag_streak(contact_id) -> None`.
- `Repository.finish_auto_handover(contact_id, success) -> None`.

`outcome` queda limitado a los dos motivos permitidos y `rag_answer`; no se aceptan textos libres ni se guardan textos del cliente en esta tabla.

## Alternativa descartada

Derivar tras cada fallo (el comportamiento previo para algunos resultados) se descarta porque no satisface el umbral ni evita avisos repetidos. Un contador solo en memoria se descarta porque pierde rachas al reiniciar y no protege reintentos.

## Sin cambios

No se modifican `contracts/`, APIs, autorización, respuestas de comandos, formato del webhook ni el contrato de `/handover`. Sin dependencias nuevas. Errores de proveedor no cuentan como “no respuesta confiable” para el umbral y siguen el mensaje de error existente.
