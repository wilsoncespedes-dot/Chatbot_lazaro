# Requirements — edicion_fragmentos

Alcance: API del servicio RAG para editar un fragmento; el panel queda fuera.

## R1 — Contrato
El contrato DEBE documentar `PATCH /chunks/{id}`, los modelos request/response y sus errores `401`, `404`, `422` y `500`.

## R2 — Texto inválido
SI `text` está vacío o contiene solo espacios ENTONCES RAG DEBE responder `422 validation_error`.

## R3 — Preservar texto
CUANDO `text` contiene caracteres no blancos, RAG DEBE conservar exactamente el valor recibido.

## R4 — Autorización
SI falta `X-Service-Token` o no coincide con `SERVICE_TOKEN` ENTONCES RAG DEBE responder `401 unauthorized` sin modificar datos.

## R5 — Recalcular embedding
CUANDO recibe una edición válida, RAG DEBE recalcular el embedding con el proveedor configurado antes de persistir.

## R6 — Guardar edición
CUANDO el embedding se calcula correctamente, RAG DEBE guardar el texto y el embedding nuevos.

## R7 — Conservar metadatos
CUANDO edita un fragmento, RAG DEBE conservar `chunk_id`, `manual_id`, manual, orden y estado activo.

## R8 — Respuesta exitosa
CUANDO una edición termina correctamente, RAG DEBE responder `200` con los datos actualizados del fragmento.

## R9 — Fragmento inexistente
CUANDO `{id}` no existe ENTONCES RAG DEBE responder `404 not_found` sin crear datos.

## R10 — Fallo de embeddings
SI falla el cálculo del embedding ENTONCES RAG DEBE responder `500 internal_error` y conservar el texto y embedding anteriores.

## Trazabilidad
R1 → tests de contrato. R2–R10 → tests del endpoint y repositorios.
