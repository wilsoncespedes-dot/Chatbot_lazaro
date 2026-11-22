# Design — #72 consentimiento_unico_por_cliente

## Estado actual (revisado)

- `domain._has_current_consent(channel, external_user_id, settings, adapters)` y
  `main.py` (cálculo de `consent_ready`) llaman a
  `repository.has_channel_privacy_consent(channel, id, version)`, que mira solo
  `privacy_consents` por `(channel, external_user_id)` (#35/#37/#46).
- La aceptación (botón en `_handle_consent_button`, frase en
  `_record_text_consent_decision`) escribe `add_privacy_decision(... "accepted")` y
  ambos terminan en `_finish_acceptance` (contacto, estado `AWAITING_LOGIN`, enlace).
- `login_client` (domain.py) verifica credenciales y llama
  `repo.start_client_session(token_hash, profile_id, session_id, now)`; `"ok"` es el
  punto de login verificado. `link.contact_id` identifica el contacto (canal + id).
- `execute_suppression` borra `privacy_consents` solo de los contactos de las
  sesiones del perfil; `purge_personal_data` borra `privacy_consents` por plazo.
- Existen `Repository` (Protocol), `FakeRepository` y `PostgresRepository` en
  `adapters/repository.py`; el esquema vive en la lista de `CREATE TABLE IF NOT EXISTS`
  del mismo archivo.

## Archivos a modificar

- `services/orchestrator/orchestrator/adapters/repository.py`: Protocol, fake y
  Postgres; DDL de las dos tablas; supresión y purga.
- `services/orchestrator/orchestrator/domain.py`: `has_current_consent` público,
  llamadas en `login_client` y `_finish_acceptance`, `client_history`.
- `services/orchestrator/orchestrator/main.py`: `consent_ready` usa el helper de dominio.
- `services/orchestrator/orchestrator/config.py` y `.env.example`:
  `CLIENT_CONSENT_RETENTION_DAYS`.
- `contracts/CONTRATOS.md`: documentación (R27).
- Tests nuevos (ver tasks.md). `FakeRepository` también está en
  `services/orchestrator/tests/fakes.py` si allí se extiende.

## Esquema nuevo

```sql
CREATE TABLE IF NOT EXISTS identidades_cliente (
  cliente_id TEXT NOT NULL,
  canal_id TEXT NOT NULL,
  id_externo TEXT NOT NULL,
  vinculado_en TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (canal_id, id_externo)
);
CREATE INDEX IF NOT EXISTS identidades_cliente_cliente ON identidades_cliente (cliente_id);

CREATE TABLE IF NOT EXISTS consentimientos_cliente (
  cliente_id TEXT NOT NULL,
  notice_version TEXT NOT NULL,
  notice_sha256 TEXT NOT NULL,
  aceptado_en TIMESTAMPTZ NOT NULL,
  canal_id TEXT NOT NULL,
  PRIMARY KEY (cliente_id, notice_version)
);
```

Sin claves foráneas a `contacts` (la purga por inactividad borra contactos; la
vinculación del cliente debe sobrevivir). `cliente_id` es `profiles.id` lógico,
igual que `client_sessions.profile_id`.

## Firmas nuevas

Repository (Protocol + fake + Postgres):

```python
def has_client_consent_for_identity(
    self, channel: str, external_user_id: str, notice_version: str,
    not_before: datetime | None,
) -> bool: ...
# join identidades_cliente -> consentimientos_cliente; not_before filtra aceptado_en.

def register_client_login(
    self, cliente_id: str, channel: str, external_user_id: str,
    notice_version: str, now: datetime,
) -> None: ...
# Una transacción: upsert identidad (reasigna cliente_id y vinculado_en, R15) y, si no
# existe fila (cliente_id, version), copia sha/fecha/canal de la última privacy_consents
# 'accepted' button|text de esa identidad y versión (si no hay evidencia, no inserta).

def register_client_acceptance_if_linked(
    self, channel: str, external_user_id: str, notice_version: str,
    notice_sha256: str, accepted_at: datetime,
) -> None: ...
# Si la identidad está vinculada: INSERT ... ON CONFLICT DO NOTHING en consentimientos_cliente.

def client_history(self, cliente_id: str, limit: int) -> list[ClientHistoryMessage]: ...
# messages JOIN contacts por (channel, external_user_id) de identidades_cliente.
```

Dominio:

```python
def has_current_consent(channel, external_user_id, settings, adapters) -> bool
# evidencia por canal O cobertura por cliente (con not_before de la retención).
# _has_current_consent permanece como alias para no romper tests existentes.

def client_history(profile_id, limit, adapters) -> list[ClientHistoryMessage]

@dataclass(frozen=True)
class ClientHistoryMessage: channel: str; role: str; text: str; at: datetime
```

Config: `client_consent_retention_days: str = ""`, validador análogo a
`privacy_retention_days` (vacío o entero >= 1), propiedad `client_consent_not_before(now)`.

## Flujo

1. Texto entrante: `process_channel_message`/`_legacy_consent_gate` llaman
   `has_current_consent`. Con cobertura por cliente se enruta como consentido
   (R4, R5); sin ella, `_handle_pre_consent_text` (R10, R7).
2. Aceptación (botón o texto): tras `add_privacy_decision("accepted")`,
   `_finish_acceptance` llama `register_client_acceptance_if_linked` (R8, R9). Ese es
   el único punto compartido por #37 y #46; no se duplica lógica.
3. Login: tras `start_client_session` con `"ok"`, `register_client_login` dentro de
   `try/except Exception` que registra `logger.warning("client_consent_link_failed")`
   sin identificadores (R17). Falla en dirección segura: se vuelve a pedir el aviso.
4. Supresión: se añaden al bloque de `execute_suppression` el borrado de
   `consentimientos_cliente` e `identidades_cliente` por `profile_id` y el borrado de
   `privacy_consents` por las identidades vinculadas (antes de borrar `identidades_cliente`).
   Mismo trabajo en el fake. Claves nuevas en `removed_counts`.
5. Purga: `consentimientos_cliente` se borra solo si
   `client_consent_retention_days` está configurado; `identidades_cliente` nunca por plazo.

## Excepciones

No se añaden excepciones. Las rutas existentes no cambian de códigos. Errores de BD
en la vinculación se absorben con log (R17); en `has_current_consent` se propagan
(falla cerrada, como hoy).

## Alternativa descartada

Hacer que el login copie una fila `accepted` a `privacy_consents` por cada canal
vinculado: duplica evidencia, falsea el canal donde se aceptó, rompe «evidencia por
canal» y la supresión/purga por canal se vuelve ambigua. Se descarta; la cobertura se
resuelve por consulta (identidad -> cliente -> versión).

## Dependencias nuevas

Ninguna.

## Supuestos (confirmados por el dueño el 2026-11-22)

- **Legal (aceptado por el dueño):** la aceptación por cliente se conserva hasta la supresión. Por defecto
  `CLIENT_CONSENT_RETENTION_DAYS=` (vacío = sin caducidad); configurable en `.env.example`.
- Una identidad pertenece a un solo cliente; un login posterior de otro cliente
  reasigna la identidad (R15) y la cobertura sigue al nuevo cliente. Default seguro:
  si ese cliente no aceptó la versión vigente, se vuelve a pedir.
- El historial se expone como función de dominio/repositorio; no se crea ruta nueva.
- Un login con credencial vencida (`ok_no_access`) también vincula, pues la identidad
  ya fue verificada.
