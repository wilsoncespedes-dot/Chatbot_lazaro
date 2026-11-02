# Design — edicion_fragmentos

## Decisión

Añadir `PATCH /chunks/{id}` al servicio `rag`. La ruta es una interfaz interna para el futuro panel; usa el middleware existente `X-Service-Token`. El request solo contiene `text`. El response devuelve `chunk_id`, `manual_id`, `manual`, `order`, `text` y `active`.

## Cambios

- `contracts/`: modelo, exports, ejemplos, tests y sección de ruta en `CONTRATOS.md`.
- `services/rag/`: operación de edición en dominio/repositorio y endpoint; actualizar fakes y tests.
- No se crea interfaz web ni se cambia la ingesta o la búsqueda.

## Persistencia y errores

Calcular el embedding antes de escribir. Persistir texto y vector juntos en una operación parametrizada; si el proveedor o la escritura falla, mantener la versión anterior. El repositorio devuelve `not_found` cuando no existe el id. No normalizar texto no vacío.

## Reutilización

La operación puede reutilizar `EmbeddingsClient`, `ChunkRepository`, `Chunk` y el middleware existentes. No se requiere código externo ni dependencia nueva; las referencias solo se consultan si hay una pieza directa para esta ruta.

## Alternativa descartada

No se añade una ruta separada por cada campo: el único editable es el texto, así que `PATCH /chunks/{id}` expresa el reemplazo completo y evita una interfaz más amplia.

## Supuestos a confirmar

- `PATCH` reemplaza el texto completo y conserva los metadatos del fragmento.
- Al volver a cargar un manual se crea otro manual, como hace hoy `POST /manuals`; no se modifica el anterior.
