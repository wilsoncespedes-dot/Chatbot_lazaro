-- 0001_esquema_inicial: esquema vigente antes del runner de migraciones.
-- Extraído de los CREATE TABLE IF NOT EXISTS que cada servicio ejecutaba al
-- arrancar. Todo es idempotente: aplicarlo sobre una base que ya existe no
-- cambia nada. {{EMBEDDINGS_DIM}} lo sustituye el runner (por defecto 1536).

CREATE EXTENSION IF NOT EXISTS vector;

-- ── orchestrator: tablas ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS contacts (id TEXT PRIMARY KEY, channel TEXT NOT NULL, external_user_id TEXT, external_chat_id TEXT, telegram_user_id BIGINT UNIQUE, chat_id BIGINT, created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS messages (id BIGSERIAL PRIMARY KEY, contact_id TEXT NOT NULL, role TEXT NOT NULL, text TEXT NOT NULL, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS events (id BIGSERIAL PRIMARY KEY, contact_id TEXT NOT NULL, type TEXT NOT NULL, reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS tool_calls (id BIGSERIAL PRIMARY KEY, contact_id TEXT NOT NULL, profile_id TEXT, state TEXT NOT NULL, tool TEXT NOT NULL, origin TEXT NOT NULL, decision TEXT NOT NULL, result TEXT NOT NULL, args_sha256 TEXT NOT NULL, detail TEXT NOT NULL, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS suppression_requests (id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, contact_id TEXT NOT NULL, channel TEXT NOT NULL, status TEXT NOT NULL, case_id TEXT, created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS processed_messages (channel TEXT NOT NULL, external_message_id TEXT NOT NULL, PRIMARY KEY (channel, external_message_id));
CREATE TABLE IF NOT EXISTS processed_updates (update_id BIGINT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS case_links (case_id TEXT PRIMARY KEY, contact_id TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS auto_handover_outcomes (contact_id TEXT NOT NULL, update_id BIGINT NOT NULL, outcome TEXT NOT NULL, at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (contact_id, update_id));
CREATE TABLE IF NOT EXISTS auto_handover_streaks (contact_id TEXT PRIMARY KEY, failure_count INTEGER NOT NULL, state TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS profiles (id TEXT PRIMARY KEY, username TEXT UNIQUE NOT NULL, role TEXT NOT NULL, password_hash TEXT NOT NULL, telegram_user_id BIGINT UNIQUE, created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS link_tokens (token_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id), expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS admin_sessions (token_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id), csrf_token TEXT NOT NULL, expires_at TIMESTAMPTZ NOT NULL, enroll_only BOOLEAN NOT NULL DEFAULT FALSE);
CREATE TABLE IF NOT EXISTS staff_two_factor (profile_id TEXT PRIMARY KEY REFERENCES profiles(id), secret_ciphertext TEXT NOT NULL, enabled_at TIMESTAMPTZ, last_used_step BIGINT NOT NULL DEFAULT 0, created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS staff_recovery_codes (code_hash TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id), created_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS admin_login_attempts (id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL, ip TEXT NOT NULL, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS query_categories (id TEXT PRIMARY KEY, code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, keywords TEXT NOT NULL, active BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS app_settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS db_query_audit (id BIGSERIAL PRIMARY KEY, profile_id TEXT, telegram_user_id BIGINT NOT NULL, status TEXT NOT NULL, views TEXT NOT NULL, row_count INTEGER NOT NULL, sql_sha256 TEXT NOT NULL, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS privacy_consents (id BIGSERIAL PRIMARY KEY, channel TEXT NOT NULL, external_user_id TEXT, telegram_user_id BIGINT, notice_version TEXT NOT NULL, notice_sha256 TEXT NOT NULL, accepted_at TIMESTAMPTZ, result TEXT, evidence_type TEXT, external_message_id TEXT, button_id TEXT, occurred_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS conversation_states (contact_id TEXT PRIMARY KEY, state TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS privacy_purge_runs (id BIGSERIAL PRIMARY KEY, ran_at TIMESTAMPTZ NOT NULL, cutoff TIMESTAMPTZ NOT NULL, counts JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS client_credentials (profile_id TEXT PRIMARY KEY REFERENCES profiles(id), valid_from TIMESTAMPTZ NOT NULL, valid_until TIMESTAMPTZ NOT NULL, revoked_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS login_links (token_hash TEXT PRIMARY KEY, contact_id TEXT NOT NULL, channel TEXT NOT NULL, external_chat_id TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS client_sessions (id TEXT PRIMARY KEY, profile_id TEXT NOT NULL REFERENCES profiles(id), contact_id TEXT NOT NULL, started_at TIMESTAMPTZ NOT NULL, last_activity_at TIMESTAMPTZ NOT NULL, ended_at TIMESTAMPTZ, end_reason TEXT);
CREATE TABLE IF NOT EXISTS identity_login_attempts (id BIGSERIAL PRIMARY KEY, username TEXT NOT NULL, ip TEXT NOT NULL, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS identity_audit (id BIGSERIAL PRIMARY KEY, profile_id TEXT, contact_id TEXT, action TEXT NOT NULL, reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS client_memory (profile_id TEXT PRIMARY KEY, items JSONB NOT NULL, source_session_id TEXT, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS conversation_summaries (session_id TEXT PRIMARY KEY, profile_id TEXT NOT NULL, contact_id TEXT NOT NULL, channel TEXT NOT NULL, summary TEXT NOT NULL, trigger TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS advisor_presence (profile_id TEXT PRIMARY KEY, status TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL, last_seen_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS panel_audit (id BIGSERIAL PRIMARY KEY, actor_profile_id TEXT NOT NULL, actor_role TEXT NOT NULL, action TEXT NOT NULL, case_id TEXT, request_id TEXT, target TEXT, result TEXT NOT NULL, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS text_versions (id BIGSERIAL PRIMARY KEY, field TEXT NOT NULL, version INTEGER NOT NULL, value TEXT NOT NULL, created_by TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL, UNIQUE (field, version));
CREATE TABLE IF NOT EXISTS whatsapp_templates (name TEXT PRIMARY KEY, purpose TEXT NOT NULL, language TEXT NOT NULL, variables INTEGER NOT NULL, body TEXT NOT NULL, status TEXT NOT NULL, approved_by TEXT, approved_at TIMESTAMPTZ, updated_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS credential_expiry_notices (profile_id TEXT NOT NULL, valid_until TIMESTAMPTZ NOT NULL, status TEXT NOT NULL, method TEXT, attempts INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (profile_id, valid_until));
CREATE TABLE IF NOT EXISTS advisor_roster_sync (singleton_id INTEGER PRIMARY KEY, generation INTEGER NOT NULL, status TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS case_notes (id TEXT PRIMARY KEY, case_id TEXT NOT NULL, contact_id TEXT NOT NULL, author_profile_id TEXT NOT NULL, body TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS case_tags (id TEXT PRIMARY KEY, name TEXT NOT NULL, name_key TEXT NOT NULL UNIQUE, active BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS case_tag_assignments (case_id TEXT NOT NULL, tag_id TEXT NOT NULL, contact_id TEXT NOT NULL, assigned_by TEXT NOT NULL, assigned_at TIMESTAMPTZ NOT NULL, PRIMARY KEY (case_id, tag_id));
CREATE TABLE IF NOT EXISTS saved_replies (id TEXT PRIMARY KEY, title TEXT NOT NULL, body TEXT NOT NULL, active BOOLEAN NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS quick_replies (id TEXT PRIMARY KEY, name TEXT NOT NULL, triggers JSONB NOT NULL, blocks JSONB NOT NULL, image_id TEXT, active BOOLEAN NOT NULL, priority INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS quick_reply_images (id TEXT PRIMARY KEY, content_type TEXT NOT NULL, data BYTEA NOT NULL, size INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS panel_events (id BIGSERIAL PRIMARY KEY, case_id TEXT NOT NULL, kind TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS inbox (id BIGSERIAL PRIMARY KEY, conversation_key TEXT NOT NULL, channel TEXT NOT NULL, external_user_id TEXT NOT NULL, payload_kind TEXT NOT NULL, payload JSONB NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TIMESTAMPTZ NOT NULL, locked_until TIMESTAMPTZ NULL, last_error TEXT NULL, created_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ NULL);
CREATE TABLE IF NOT EXISTS outbox (id BIGSERIAL PRIMARY KEY, contact_id TEXT NULL, destination_key TEXT NOT NULL, channel TEXT NOT NULL, destination TEXT NOT NULL, kind TEXT NOT NULL, blocks JSONB NOT NULL, status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, next_attempt_at TIMESTAMPTZ NOT NULL, locked_until TIMESTAMPTZ NULL, last_error TEXT NULL, created_at TIMESTAMPTZ NOT NULL, finished_at TIMESTAMPTZ NULL);
CREATE TABLE IF NOT EXISTS identidades_cliente (cliente_id TEXT NOT NULL, canal_id TEXT NOT NULL, id_externo TEXT NOT NULL, vinculado_en TIMESTAMPTZ NOT NULL, PRIMARY KEY (canal_id, id_externo));
CREATE TABLE IF NOT EXISTS consentimientos_cliente (cliente_id TEXT NOT NULL, notice_version TEXT NOT NULL, notice_sha256 TEXT NOT NULL, aceptado_en TIMESTAMPTZ NOT NULL, canal_id TEXT NOT NULL, PRIMARY KEY (cliente_id, notice_version));

-- ── orchestrator: índices ───────────────────────────────────────
CREATE INDEX IF NOT EXISTS admin_login_attempts_user_at ON admin_login_attempts (username, at);
CREATE INDEX IF NOT EXISTS admin_login_attempts_ip_at ON admin_login_attempts (ip, at);
CREATE INDEX IF NOT EXISTS privacy_consents_user_version ON privacy_consents (telegram_user_id, notice_version);
CREATE UNIQUE INDEX IF NOT EXISTS client_sessions_one_active_profile ON client_sessions (profile_id) WHERE ended_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS client_sessions_one_active_contact ON client_sessions (contact_id) WHERE ended_at IS NULL;
CREATE INDEX IF NOT EXISTS login_links_contact ON login_links (contact_id);
CREATE INDEX IF NOT EXISTS identity_login_attempts_user_at ON identity_login_attempts (username, at);
CREATE INDEX IF NOT EXISTS identity_login_attempts_ip_at ON identity_login_attempts (ip, at);
CREATE INDEX IF NOT EXISTS tool_calls_at_idx ON tool_calls (at);
CREATE INDEX IF NOT EXISTS tool_calls_contact_idx ON tool_calls (contact_id);
CREATE INDEX IF NOT EXISTS conversation_summaries_profile ON conversation_summaries (profile_id, updated_at);
CREATE INDEX IF NOT EXISTS conversation_summaries_updated ON conversation_summaries (updated_at);
CREATE INDEX IF NOT EXISTS client_sessions_profile ON client_sessions (profile_id);
CREATE INDEX IF NOT EXISTS panel_audit_at ON panel_audit (at);
CREATE INDEX IF NOT EXISTS suppression_requests_status_created ON suppression_requests (status, created_at);
CREATE INDEX IF NOT EXISTS whatsapp_templates_purpose ON whatsapp_templates (purpose, status);
CREATE INDEX IF NOT EXISTS events_type_at ON events (type, at);
CREATE INDEX IF NOT EXISTS case_links_created ON case_links (created_at);
CREATE INDEX IF NOT EXISTS case_notes_case ON case_notes (case_id, created_at);
CREATE INDEX IF NOT EXISTS case_notes_contact ON case_notes (contact_id);
CREATE INDEX IF NOT EXISTS case_tag_assignments_tag ON case_tag_assignments (tag_id);
CREATE INDEX IF NOT EXISTS case_tag_assignments_contact ON case_tag_assignments (contact_id);
CREATE INDEX IF NOT EXISTS panel_events_created ON panel_events (created_at);
CREATE INDEX IF NOT EXISTS staff_recovery_codes_profile ON staff_recovery_codes (profile_id);
CREATE INDEX IF NOT EXISTS inbox_conversation ON inbox (conversation_key, id);
CREATE INDEX IF NOT EXISTS inbox_created ON inbox (created_at);
CREATE INDEX IF NOT EXISTS outbox_destination ON outbox (destination_key, id);
CREATE INDEX IF NOT EXISTS outbox_status ON outbox (status, created_at);
CREATE INDEX IF NOT EXISTS identidades_cliente_cliente ON identidades_cliente (cliente_id);

-- ── orchestrator: migraciones aditivas previas ──────────────────
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS channel TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS external_user_id TEXT;
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS external_chat_id TEXT;
ALTER TABLE contacts ALTER COLUMN telegram_user_id DROP NOT NULL;
ALTER TABLE contacts ALTER COLUMN chat_id DROP NOT NULL;
UPDATE contacts SET channel = 'telegram' WHERE channel IS NULL;
UPDATE contacts SET external_user_id = CAST(telegram_user_id AS TEXT) WHERE external_user_id IS NULL AND telegram_user_id IS NOT NULL;
UPDATE contacts SET external_chat_id = CAST(chat_id AS TEXT) WHERE external_chat_id IS NULL AND chat_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS contacts_channel_external_user ON contacts (channel, external_user_id);
ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS channel TEXT;
ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS external_user_id TEXT;
ALTER TABLE privacy_consents ALTER COLUMN telegram_user_id DROP NOT NULL;
UPDATE privacy_consents SET channel = 'telegram' WHERE channel IS NULL;
UPDATE privacy_consents SET external_user_id = CAST(telegram_user_id AS TEXT) WHERE external_user_id IS NULL AND telegram_user_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS privacy_consents_channel_user_version ON privacy_consents (channel, external_user_id, notice_version);
ALTER TABLE privacy_consents ALTER COLUMN accepted_at DROP NOT NULL;
ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS result TEXT;
ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS evidence_type TEXT;
ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS external_message_id TEXT;
ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS button_id TEXT;
ALTER TABLE privacy_consents ADD COLUMN IF NOT EXISTS occurred_at TIMESTAMPTZ;
UPDATE privacy_consents SET result = 'accepted' WHERE result IS NULL;
UPDATE privacy_consents SET evidence_type = 'legacy' WHERE evidence_type IS NULL;
UPDATE privacy_consents SET occurred_at = accepted_at WHERE occurred_at IS NULL AND accepted_at IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS suppression_requests_one_pending ON suppression_requests (profile_id) WHERE status = 'pending';
ALTER TABLE case_links ADD COLUMN IF NOT EXISTS profile_id TEXT;
ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS executed_at TIMESTAMPTZ;
ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS executed_by TEXT;
ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS removed_counts JSONB;
ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS result_note TEXT;
ALTER TABLE suppression_requests ADD COLUMN IF NOT EXISTS notification_result TEXT;
ALTER TABLE admin_sessions ADD COLUMN IF NOT EXISTS enroll_only BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS public_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS profiles_public_id_key ON profiles (public_id);
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS email TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS phone TEXT;
ALTER TABLE profiles ADD COLUMN IF NOT EXISTS contact_updated_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS profiles_email ON profiles (email);
CREATE INDEX IF NOT EXISTS profiles_phone ON profiles (phone);
ALTER TABLE contacts ADD COLUMN IF NOT EXISTS canal_id TEXT;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS canal_id TEXT;
UPDATE contacts SET canal_id = channel WHERE canal_id IS NULL;
UPDATE messages SET canal_id = c.channel FROM contacts c WHERE messages.contact_id = c.id AND messages.canal_id IS NULL;
CREATE INDEX IF NOT EXISTS messages_canal_id ON messages (canal_id);

-- ── handover ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS handover_cases (case_id TEXT PRIMARY KEY, contact_id TEXT NOT NULL, chat_id BIGINT NOT NULL, reason TEXT NOT NULL, status TEXT NOT NULL, advisor_id TEXT NULL, last_messages JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL, assigned_at TIMESTAMPTZ NULL, closed_at TIMESTAMPTZ NULL, closed_by TEXT NULL);
CREATE TABLE IF NOT EXISTS handover_notifications (id BIGSERIAL PRIMARY KEY, case_id TEXT NOT NULL, advisor_id TEXT NOT NULL, reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL, delivered BOOLEAN NOT NULL);
CREATE TABLE IF NOT EXISTS handover_denials (id BIGSERIAL PRIMARY KEY, case_id TEXT NOT NULL, advisor_id TEXT NOT NULL, action TEXT NOT NULL, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS handover_auto_assignments (id BIGSERIAL PRIMARY KEY, case_id TEXT NOT NULL, advisor_id TEXT NOT NULL, reason TEXT NOT NULL, at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS handover_assignment_pointer (strategy TEXT PRIMARY KEY, last_advisor_id TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS handover_requests (id BIGSERIAL PRIMARY KEY, requested_case_id TEXT NOT NULL, case_id TEXT NULL, contact_id TEXT NOT NULL, reason TEXT NOT NULL, received_at TIMESTAMPTZ NOT NULL, result TEXT NOT NULL, advisors_configured INTEGER NOT NULL, notices_delivered INTEGER NOT NULL, messages_count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS privacy_purge_runs (id BIGSERIAL PRIMARY KEY, ran_at TIMESTAMPTZ NOT NULL, cutoff TIMESTAMPTZ NOT NULL, counts JSONB NOT NULL);
CREATE TABLE IF NOT EXISTS handover_advisors (profile_id TEXT PRIMARY KEY, telegram_user_id TEXT NULL, role TEXT NOT NULL DEFAULT 'asesor');
CREATE UNIQUE INDEX IF NOT EXISTS handover_advisors_telegram ON handover_advisors (telegram_user_id) WHERE telegram_user_id IS NOT NULL;
CREATE TABLE IF NOT EXISTS handover_roster_state (singleton_id INTEGER PRIMARY KEY, generation INTEGER NOT NULL);
INSERT INTO handover_roster_state (singleton_id, generation) VALUES (1, 0) ON CONFLICT (singleton_id) DO NOTHING;
ALTER TABLE handover_cases ADD COLUMN IF NOT EXISTS timeout_claimed_at TIMESTAMPTZ NULL;
ALTER TABLE handover_advisors ADD COLUMN IF NOT EXISTS role TEXT NOT NULL DEFAULT 'asesor';

-- ── telegram_gateway: canales ───────────────────────────────────
CREATE TABLE IF NOT EXISTS canales (id TEXT PRIMARY KEY, nombre TEXT NOT NULL, tipo_adaptador TEXT NOT NULL, icono TEXT NOT NULL, color TEXT NOT NULL, config JSONB NOT NULL DEFAULT '{}'::jsonb, activo BOOLEAN NOT NULL DEFAULT TRUE, creado_en TIMESTAMPTZ NOT NULL DEFAULT now());
ALTER TABLE canales ADD COLUMN IF NOT EXISTS config_secreta TEXT NULL;
ALTER TABLE canales ADD COLUMN IF NOT EXISTS activo_segun_entorno BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE canales ADD COLUMN IF NOT EXISTS pistas_credenciales JSONB NOT NULL DEFAULT '{}'::jsonb;

-- ── telegram_gateway: buzón simulado ────────────────────────────
CREATE TABLE IF NOT EXISTS buzon_simulado (id BIGSERIAL PRIMARY KEY, canal_id TEXT NOT NULL, destino TEXT NOT NULL, tipo TEXT NOT NULL, texto TEXT NOT NULL, creado_en TIMESTAMPTZ NOT NULL);
CREATE INDEX IF NOT EXISTS buzon_simulado_canal_id ON buzon_simulado (canal_id, id);

-- ── rag ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS manuals (manual_id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE IF NOT EXISTS chunks (chunk_id TEXT PRIMARY KEY, manual_id TEXT REFERENCES manuals(manual_id), ord INT, text TEXT, embedding vector({{EMBEDDINGS_DIM}}), active BOOLEAN DEFAULT TRUE);
CREATE INDEX IF NOT EXISTS chunks_text_spanish_gin ON chunks USING GIN (to_tsvector('spanish', text)) WHERE active;

-- ── mcp_lectura ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS demo_ofertas (
        id TEXT PRIMARY KEY,
        destino TEXT NOT NULL,
        titulo TEXT NOT NULL,
        precio_cop INTEGER NOT NULL,
        valido_desde DATE NOT NULL,
        valido_hasta DATE NOT NULL,
        es_demo BOOLEAN NOT NULL DEFAULT TRUE CHECK (es_demo),
        etiqueta TEXT NOT NULL DEFAULT 'DEMOSTRACIÓN'
    );
CREATE TABLE IF NOT EXISTS mcp_auditoria (
        id BIGSERIAL PRIMARY KEY,
        herramienta TEXT NOT NULL,
        args_sha256 TEXT NOT NULL,
        filas INTEGER NOT NULL,
        estado TEXT NOT NULL,
        cliente_sha256 TEXT NOT NULL,
        creado_en TIMESTAMPTZ NOT NULL
    );
