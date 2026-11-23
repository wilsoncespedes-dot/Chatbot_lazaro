-- Fase 2: entrada unificada de canales sin pérdidas ni respuestas duplicadas.

-- ── orchestrator: inbox idempotente
-- Un mismo mensaje externo de un canal solo entra una vez en la cola, aunque
-- Redis falle y el gateway lo reenvíe. Las filas antiguas quedan en NULL y no
-- chocan entre sí (NULL es distinto de NULL en un índice único).
ALTER TABLE inbox ADD COLUMN IF NOT EXISTS external_message_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS inbox_channel_external_message_uidx ON inbox (channel, external_message_id);

-- ── telegram_gateway: reintentos hacia el orquestador
-- Mensajes ya aceptados por el canal que el orquestador no pudo recibir; el
-- gateway los reenvía con espera creciente y borra la fila al entregarlos.
CREATE TABLE IF NOT EXISTS gateway_entrantes_pendientes (id BIGSERIAL PRIMARY KEY, canal TEXT NOT NULL, id_mensaje_externo TEXT NOT NULL, mensaje JSONB NOT NULL, intentos INTEGER NOT NULL DEFAULT 0, proximo_intento TIMESTAMPTZ NOT NULL, bloqueado_hasta TIMESTAMPTZ, ultimo_error TEXT, creado_en TIMESTAMPTZ NOT NULL, UNIQUE (canal, id_mensaje_externo));
CREATE INDEX IF NOT EXISTS gateway_entrantes_pendientes_proximo_idx ON gateway_entrantes_pendientes (proximo_intento);
