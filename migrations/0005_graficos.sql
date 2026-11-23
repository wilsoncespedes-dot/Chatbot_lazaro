-- Fase 5: gráficos PNG temporales que el bot envía como imagen o enlace firmado.
-- Cada fila vence en `expires_at`; el orquestador borra las vencidas al guardar
-- un gráfico nuevo y la ruta pública nunca sirve una vencida.

-- ── orchestrator: gráficos temporales
CREATE TABLE IF NOT EXISTS chart_images (
    id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL REFERENCES contacts(id) ON DELETE CASCADE,
    png BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS chart_images_expires_idx ON chart_images (expires_at);
CREATE INDEX IF NOT EXISTS chart_images_contact_idx ON chart_images (contact_id);
