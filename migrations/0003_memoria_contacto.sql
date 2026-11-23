-- Fase 3: memoria por contacto sin login.
-- El contacto (canal + id externo) recuerda hechos útiles y un resumen corto
-- aunque no inicie sesión. Al iniciar sesión se fusionan con client_memory.

-- ── orchestrator: memoria por contacto
-- Un valor por clave y contacto; la lista de claves es cerrada.
-- fuente_mensaje_id apunta a messages.id solo como trazabilidad (sin FK: la
-- retención borra mensajes por antigüedad y el hecho sigue siendo válido).
CREATE TABLE IF NOT EXISTS contact_facts (contact_id TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE, clave TEXT NOT NULL CHECK (clave IN ('nombre', 'empresa', 'producto_interes', 'pedido_caso', 'preferencia_contacto')), valor TEXT NOT NULL, fuente_mensaje_id BIGINT, actualizado TIMESTAMPTZ NOT NULL, PRIMARY KEY (contact_id, clave));
-- Resumen del contacto y mensajes pendientes de revisar por el extractor.
CREATE TABLE IF NOT EXISTS contact_memory (contact_id TEXT PRIMARY KEY REFERENCES contacts(id) ON DELETE CASCADE, resumen TEXT NOT NULL DEFAULT '', mensajes_pendientes INTEGER NOT NULL DEFAULT 0, actualizado TIMESTAMPTZ NOT NULL);
