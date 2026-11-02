# Spec review — #22 panel_fragmentos

**Veredicto:** APPROVED

Sin bloqueos materiales.

## Puntos validados
- **python-multipart:** se necesita. El panel de #21 parsea formularios con
  `parse_qs` (`services/orchestrator/orchestrator/admin_routes.py:47-50`), que no
  sirve para multipart, y `services/orchestrator/requirements.txt` no la declara.
  Ya está instalada en `.venv` (0.0.32) y el RAG usa la misma versión acotada
  (`services/rag/requirements.txt:9`). T7 la añade a requirements. Licencia
  Apache-2.0, compatible.
- **Límite 20 MiB:** solo aplica al panel (`ADMIN_MANUAL_MAX_BYTES`, configurable,
  rango acotado). El RAG no tiene límite propio y `POST /manuals` no cambia, así
  que no hay conflicto con el contrato. Los errores que devuelve hoy el RAG
  (415 `unsupported_format`, 422 `empty_document`) quedan cubiertos por R17.
- **Contratos:** los cambios son solo aditivos (3 rutas nuevas). `ChunkUpdateRequest/Response`
  y `ManualUpload*` no se tocan. `ChunkItem` repite los campos de `ChunkUpdateResponse`
  y `RootModel` sigue el patrón de `SearchResponse`. T2 comprueba que las filas
  publicadas no cambian.
- **EARS/cobertura:** R1–R22 tienen un solo `DEBE`/`NO DEBE` cada uno y patrones
  válidos. Los 3 criterios de acceptance están mapeados. Cada R tiene un test
  concreto en T2/T5/T6/T9, y las tasks están en `[ ]` y cubren R1–R22.

## Notas no bloqueantes (para la implementación)
- `await request.form()` de Starlette guarda el archivo completo en un temporal
  antes de que se pueda comprobar `UploadFile.size`. Por eso el límite de 413 no
  limita la lectura del cuerpo. El riesgo es acotado porque la sesión se valida
  antes de parsear (orden de diseño) y solo un admin llega ahí. Si se quiere un
  límite real, rechazar antes por `Content-Length`.
