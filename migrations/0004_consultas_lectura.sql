-- Fase 4: consultas de datos de solo lectura listas para producción.
--
-- Roles (son del clúster: se crean una sola vez y sin LOGIN; el runner les da
-- LOGIN con la clave de BOT_LECTURA_PASSWORD / BOT_CONSULTAS_PASSWORD):
--   bot_vistas     NOLOGIN. Dueño de todas las vistas. Sin BYPASSRLS: cuando una
--                  vista lee una tabla con RLS, las políticas se aplican a este rol.
--   bot_lectura    CLIENT_DATA_DATABASE_URL (herramienta consultar_mis_datos). Solo
--                  SELECT sobre las vistas de mis_datos, filtradas por lazaro.cliente_id.
--   bot_consultas  DB_QUERY_DATABASE_URL (/consultar del personal). Solo SELECT sobre
--                  las vistas agregadas de consultas, sin datos personales.
-- Ninguno puede leer ni escribir tablas: solo las vistas que se le conceden.

-- ── orchestrator: roles de solo lectura
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bot_vistas') THEN
    CREATE ROLE bot_vistas NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bot_lectura') THEN
    CREATE ROLE bot_lectura NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bot_consultas') THEN
    CREATE ROLE bot_consultas NOLOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
  EXECUTE format('GRANT CONNECT ON DATABASE %I TO bot_lectura, bot_consultas', current_database());
END $$;
ALTER ROLE bot_vistas NOSUPERUSER NOBYPASSRLS;
ALTER ROLE bot_lectura NOSUPERUSER NOBYPASSRLS;
ALTER ROLE bot_consultas NOSUPERUSER NOBYPASSRLS;
-- Defensa extra: el adaptador ya abre READ ONLY y fija su propio timeout.
ALTER ROLE bot_lectura SET default_transaction_read_only = on;
ALTER ROLE bot_lectura SET statement_timeout = '5s';
ALTER ROLE bot_consultas SET default_transaction_read_only = on;
ALTER ROLE bot_consultas SET statement_timeout = '5s';

CREATE SCHEMA IF NOT EXISTS mis_datos;
CREATE SCHEMA IF NOT EXISTS consultas;
-- CREATE solo hace falta si quien migra no es superusuario (cambio de dueño).
GRANT USAGE, CREATE ON SCHEMA mis_datos, consultas TO bot_vistas;
GRANT USAGE ON SCHEMA mis_datos TO bot_lectura;
GRANT USAGE ON SCHEMA consultas TO bot_consultas;
GRANT SELECT ON profiles, client_credentials, client_sessions, case_links, identidades_cliente, handover_cases, contacts, messages, demo_ofertas TO bot_vistas;

-- ── orchestrator: RLS por lazaro.cliente_id
-- FORCE para que ni el dueño de la tabla se salte la política; el dueño (el
-- usuario que migra y usan los servicios) conserva todo con app_acceso_total.
-- Un superusuario no se ve afectado por la RLS.
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE profiles FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_acceso_total ON profiles;
CREATE POLICY app_acceso_total ON profiles FOR ALL TO CURRENT_USER USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bot_solo_su_cliente ON profiles;
CREATE POLICY bot_solo_su_cliente ON profiles FOR SELECT TO bot_vistas USING (id = current_setting('lazaro.cliente_id', true));

ALTER TABLE client_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE client_credentials FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_acceso_total ON client_credentials;
CREATE POLICY app_acceso_total ON client_credentials FOR ALL TO CURRENT_USER USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bot_solo_su_cliente ON client_credentials;
CREATE POLICY bot_solo_su_cliente ON client_credentials FOR SELECT TO bot_vistas USING (profile_id = current_setting('lazaro.cliente_id', true));

ALTER TABLE client_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE client_sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_acceso_total ON client_sessions;
CREATE POLICY app_acceso_total ON client_sessions FOR ALL TO CURRENT_USER USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bot_solo_su_cliente ON client_sessions;
CREATE POLICY bot_solo_su_cliente ON client_sessions FOR SELECT TO bot_vistas USING (profile_id = current_setting('lazaro.cliente_id', true));

ALTER TABLE case_links ENABLE ROW LEVEL SECURITY;
ALTER TABLE case_links FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_acceso_total ON case_links;
CREATE POLICY app_acceso_total ON case_links FOR ALL TO CURRENT_USER USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bot_solo_su_cliente ON case_links;
CREATE POLICY bot_solo_su_cliente ON case_links FOR SELECT TO bot_vistas USING (profile_id = current_setting('lazaro.cliente_id', true));

ALTER TABLE identidades_cliente ENABLE ROW LEVEL SECURITY;
ALTER TABLE identidades_cliente FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_acceso_total ON identidades_cliente;
CREATE POLICY app_acceso_total ON identidades_cliente FOR ALL TO CURRENT_USER USING (true) WITH CHECK (true);
DROP POLICY IF EXISTS bot_solo_su_cliente ON identidades_cliente;
CREATE POLICY bot_solo_su_cliente ON identidades_cliente FOR SELECT TO bot_vistas USING (cliente_id = current_setting('lazaro.cliente_id', true));

-- ── orchestrator: vistas de mis_datos (cliente autenticado)
-- Cada vista parte de una tabla con RLS: sin lazaro.cliente_id no devuelve nada.
CREATE OR REPLACE VIEW mis_datos.v_mi_cuenta AS SELECT p.public_id AS id_cliente, p.username AS usuario, p.email AS correo, p.phone AS telefono, c.valid_from AS acceso_desde, c.valid_until AS acceso_hasta FROM profiles p LEFT JOIN client_credentials c ON c.profile_id = p.id WHERE p.role = 'cliente';
CREATE OR REPLACE VIEW mis_datos.v_mis_casos AS SELECT h.case_id AS caso, h.status AS estado, h.reason AS motivo, h.created_at AS creado, h.closed_at AS cerrado FROM case_links l JOIN handover_cases h ON h.case_id = l.case_id;
CREATE OR REPLACE VIEW mis_datos.v_mis_sesiones AS SELECT c.channel AS canal, s.started_at AS inicio, s.ended_at AS fin FROM client_sessions s JOIN contacts c ON c.id = s.contact_id;
ALTER VIEW mis_datos.v_mi_cuenta OWNER TO bot_vistas;
ALTER VIEW mis_datos.v_mis_casos OWNER TO bot_vistas;
ALTER VIEW mis_datos.v_mis_sesiones OWNER TO bot_vistas;
GRANT SELECT ON mis_datos.v_mi_cuenta, mis_datos.v_mis_casos, mis_datos.v_mis_sesiones TO bot_lectura;

-- ── orchestrator: vistas de consultas (personal, sin datos personales)
CREATE OR REPLACE VIEW consultas.v_casos AS SELECT h.case_id AS caso, h.status AS estado, h.reason AS motivo, c.channel AS canal, h.created_at AS creado, h.assigned_at AS asignado, h.closed_at AS cerrado FROM handover_cases h LEFT JOIN contacts c ON c.id = h.contact_id;
CREATE OR REPLACE VIEW consultas.v_mensajes_diarios AS SELECT CAST(date_trunc('day', m.at) AS DATE) AS dia, c.channel AS canal, m.role AS rol, count(*) AS mensajes FROM messages m LEFT JOIN contacts c ON c.id = m.contact_id GROUP BY 1, 2, 3;
CREATE OR REPLACE VIEW consultas.v_ofertas AS SELECT id, destino, titulo, precio_cop, valido_desde, valido_hasta, etiqueta FROM demo_ofertas;
ALTER VIEW consultas.v_casos OWNER TO bot_vistas;
ALTER VIEW consultas.v_mensajes_diarios OWNER TO bot_vistas;
ALTER VIEW consultas.v_ofertas OWNER TO bot_vistas;
GRANT SELECT ON consultas.v_casos, consultas.v_mensajes_diarios, consultas.v_ofertas TO bot_consultas;
