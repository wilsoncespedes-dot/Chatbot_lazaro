# Design — retencion_evidencia_y_privacidad_inicial (feature #57)

## 1. Alcance

- **orchestrator**: `FakeRepository` y `PostgresRepository` — `execute_suppression` y
  `purge_personal_data` incluyen `privacy_consents`. Sin cambios de firma ni de esquema
  (`privacy_consents` ya tiene `channel`, `external_user_id`, `occurred_at`, `accepted_at`).
- **render.yaml, `.env.example`, `docs/despliegue.md`, `contracts/CONTRATOS.md`**: valores
  aprobados y política. `docs/proyecto.md`/`docs/especificacion.md`: solo nota breve de que los
  valores son decisión del dueño (sin afirmar validación legal).
- **Sin cambios**: `handover` (código), `telegram_gateway`, `rag`, `contracts/lazaro_contracts`
  (`PrivacyPurgeResponse.deleted` ya es `dict[str, int]`; `removed_counts` es `dict[str, int]`).
- Sin dependencias nuevas.

## 2. Política aprobada por el dueño (no es revisión legal)

Los valores de la tabla de `requirements.md` son input aprobado el 2026-11-14 y no se
alteran. No se añaden razón social, NIT, correo ni canal distinto del chat. La política queda
registrada como decisión del dueño; no hay revisión legal externa (`docs/proyecto.md` §11) y los
textos no afirman lo contrario.

### Textos (default configurable derivado de lo aprobado)

El dueño aprobó forma y contenido (aviso corto, responsable Lázaro Software, solicitudes por el
mismo chat) pero no dictó la redacción literal. Se propone, editable por variable de entorno:

- `PRIVACY_NOTICE_TEXT`: «Lázaro Software es responsable de tus datos personales. Los usamos
  para atender tu consulta y, si lo necesitas, pasarte con un asesor. Conservamos tus mensajes
  30 días y, hasta que pidas su supresión, la memoria de temas pendientes y acuerdos. Puedes
  pedir esa supresión o ejercer tus derechos por este mismo chat. Para continuar, responde
  ACEPTO.»
- `PRIVACY_ACCEPTED_REPLY`: «Gracias, registramos tu aceptación. ¿En qué te ayudo?»
- `PRIVACY_TEXT_CONSENT_INSTRUCTION` no cambia (ya contiene `{accept}` y `{reject}`).

Si la redacción literal cambia, solo cambia el `value` (el test de R2 comprueba propiedades, no
la cadena exacta). La versión sigue `1.0` mientras el dueño no apruebe otra.

## 3. Archivos a tocar

| Archivo | Cambio |
|---|---|
| `services/orchestrator/orchestrator/adapters/repository.py` | borrado de evidencia en `execute_suppression` y `purge_personal_data` (Fake y Postgres) |
| `render.yaml` | `value` en variables de privacidad y `MEMORY_ENABLED`; comentario de memoria |
| `.env.example` | mismos valores; `MEMORY_ENABLED=true` |
| `docs/despliegue.md` | §2.1: política aprobada, memoria, evidencia 30 días; quitar `privacy_consents` de la lista de no cubiertos |
| `contracts/CONTRATOS.md` | `POST /privacy/purge` y supresión: nuevas claves `privacy_consents` |
| `scripts/tests/test_render_retencion.py` | actualizar R10, R11, R14, R22, R23 de #28 (ver §6) |
| tests de orquestador (ver `tasks.md`) | nuevos tests de R9–R23 |

## 4. Firmas y SQL

No hay firmas públicas nuevas. `execute_suppression(request_id, executed_by, idle_minutes, now)
-> dict[str, int] | None` y `purge_personal_data(cutoff, ran_at) -> dict[str, int]` añaden la
clave `"privacy_consents"` (siempre presente, `0` si nada).

### Fake `execute_suppression`
Dentro del `with self._identity_lock` ya existente, tras calcular `sessions` y antes de mutar
nada (para que un fallo no deje estado parcial): construir `identities = {(c.channel,
c.external_user_id or str(c.telegram_user_id))}` buscando en `self.contacts.values()` los
contactos cuyo `id` está en `session_contact_ids`. Luego filtrar `self.privacy_consents`
quitando los que cumplan `(consent.channel, consent.external_user_id) in identities`; contar
los eliminados. Para R16 en Fake: el borrado de evidencia se aplica **al final**, justo antes
de marcar `executed`, y se calcula la nueva lista antes de asignar; un fallo inyectado
(`fail_privacy_consent_delete: bool`, atributo de test del Fake, análogo a
`fail_privacy_consent`) se evalúa **antes** de cualquier mutación y lanza `RuntimeError`.

### Postgres `execute_suppression` (misma transacción, tras borrar `client_memory`)
```sql
DELETE FROM privacy_consents p USING contacts c
WHERE c.id = ANY(%s)
  AND p.channel = c.channel
  AND p.external_user_id = COALESCE(c.external_user_id, CAST(c.telegram_user_id AS TEXT))
RETURNING p.id
```
parámetro: `session_contact_ids` (omitido si la lista está vacía → 0). `counts` añade
`"privacy_consents": len(rows)`. El `except Exception: conn.rollback(); raise` existente cubre
R16.

### Fake `purge_personal_data`
`kept = [c for c in self.privacy_consents if (c.occurred_at or c.accepted_at) is None or
(c.occurred_at or c.accepted_at) >= cutoff]`; `deleted = len(self.privacy_consents) -
len(kept)`; `counts["privacy_consents"] = deleted`. (Fila con ambas fechas nulas: se conserva;
no puede crearse por el código actual.)

### Postgres `purge_personal_data` (misma transacción, antes del `INSERT` en
`privacy_purge_runs`)
```sql
DELETE FROM privacy_consents
WHERE COALESCE(occurred_at, accepted_at) < %s RETURNING id
```
parámetro: `(cutoff,)`. `counts["privacy_consents"] = len(rows)`. La migración existente ya
rellena `occurred_at` desde `accepted_at`; el `COALESCE` es defensa para filas legadas (R22).

### Memoria (R9, R10)
No se añade código: `purge_personal_data` no toca `client_memory` y `execute_suppression` ya lo
borra. Se añaden tests de regresión.

## 5. Excepciones

Se reutiliza `Exception` genérica del manejador existente (500 `internal_error`) y el `rollback`
de Postgres. Sin excepciones nuevas.

## 6. Tests existentes que cambian

`scripts/tests/test_render_retencion.py` (#28):
- R10, R11, R14 afirmaban `sync: false` y ausencia de `value` para estas variables. Se
  sustituyen por la nueva política: `value` presentes con los valores aprobados;
  `PRIVACY_NOTICE_TEXT` y `PRIVACY_ACCEPTED_REPLY` pueden ser `value`.
- R22 prohibía un ejemplo numérico de plazo en docs: se retira, la política ahora cita 30 y 15.
- R23 exigía que `privacy_consents` figure como no cubierto: se invierte.
- R12–R13 (fuente única de `PRIVACY_RETENTION_DAYS` en handover) NO cambian, pero
  `sync is False` se cambia por `value == "30"` en R13.
Cada ajuste referencia el `R<n>` de #57 que lo sustituye en el docstring.

## 7. Alternativas descartadas

- **Borrar evidencia por `contact_id`** (añadir columna a `privacy_consents`): requiere migración
  y reescritura de la evidencia ya registrada; el mapa por `(channel, external_user_id)` ya
  existe y soporta varios canales.
- **Conservar la evidencia sin plazo como prueba de autorización** (S5 de #27): contradice la
  decisión del dueño (30 días y supresión).
- **Purgar `client_memory` por retención**: contradice «memoria hasta supresión».
- **Borrar evidencia por la antigüedad de la sesión/contacto**: la decisión es por `occurred_at`
  de cada fila; usar el contacto dejaría evidencia vieja de contactos activos.
- **Dejar los textos en `sync: false`**: el acceptance exige que el Blueprint refleje los
  valores; pedirlos en el panel dejaría la configuración sin versionar.

## 8. Supuestos a confirmar (valores por defecto configurables)

| Id | Supuesto | Variable |
|---|---|---|
| S1 | Redacción literal del aviso y de la respuesta (§2); versión fija `1.0` | `PRIVACY_NOTICE_TEXT`, `PRIVACY_ACCEPTED_REPLY` |
| S2 | Tras supresión no se borra el contacto: solo la evidencia; el cliente vuelve a ver el aviso (R17) | — |
| S3 | `occurred_at` nulo cae en `accepted_at` (R22) | — |
| S4 | Revisión legal externa pendiente (no afirmada) | — |

## 9. Trazabilidad diseño → requirements

| Pieza | R |
|---|---|
| `render.yaml`, `.env.example` | R1–R7 |
| `docs/despliegue.md`, `CONTRATOS.md` | R8, R24, R25 |
| memoria (sin código + tests) | R9, R10 |
| `execute_suppression` Fake/Postgres | R11–R17 |
| `purge_personal_data` Fake/Postgres | R18–R22 |
| tests de paridad | R23 |
| `./init.sh` | R26 |
