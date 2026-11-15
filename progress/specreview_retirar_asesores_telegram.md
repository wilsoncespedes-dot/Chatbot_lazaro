# Revisión final de spec — feature #48 `retirar_asesores_telegram`

**Veredicto:** SPEC_APPROVED

## Comprobaciones

- Cobertura de acceptance: [x] Los ocho criterios actuales de la feature_list están cubiertos por R1–R52, incluida la ruta de sincronización que se agregó en el criterio de contratos.
- EARS: [x] Cada requisito usa una forma verificable y contiene una sola obligación normativa.
- Contrato del roster: [x] `POST /advisors/sync` exige `X-Service-Token`; requirements especifican 401, 422 y 500; design/tasks incluyen modelos, ejemplos válidos, validación de cuerpos y pruebas de token ausente e inválido.
- Multi-instancia: [x] El estado `pending|synced` y la generación se guardan en una fila compartida de PostgreSQL junto con la actualización del perfil. Las instancias leen ese estado; handover compara la generación de cada operación con su roster durable y falla cerrado si no coincide. No depende de una bandera local.
- Migración: [x] La migración de asignaciones por Telegram a `profile_id` es transaccional e idempotente; los casos sin perfil vinculado quedan huérfanos sin perder su historial.
- Diseño: [x] Respeta las fronteras HTTP entre servicios, define errores, alternativa descartada y no añade dependencias.
- Tasks: [x] T1–T12 están sin marcar y en orden; cubren los requisitos.
- Decisiones: [x] La elegibilidad por rol `asesor` y los casos huérfanos están respaldados por el acceptance existente y la decisión #48; no se introduce un estado de habilitación adicional.

## Resultado

El spec está listo para pasar a `in_progress` e implementación.
