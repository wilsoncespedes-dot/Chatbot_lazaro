-- Canal gmail_api (integrado desde la rama principal): cursor persistente de Gmail
-- History por canal. Antes lo creaba el gateway al conectar; desde la fase 1 todo el
-- esquema vive en migraciones y los servicios no ejecutan DDL.

-- ── telegram_gateway: cursor de Gmail History
CREATE TABLE IF NOT EXISTS gmail_history_state (
    canal_id TEXT PRIMARY KEY,
    history_id TEXT NOT NULL,
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT now()
);
