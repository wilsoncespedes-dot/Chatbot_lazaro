# Design — #70 aviso_intencion_compra

Todo en `services/orchestrator`. Sin cambios en `contracts/` ni en handover.

## Archivos a tocar

- `orchestrator/purchase_intent.py` (nuevo, puro, sin IO): detección, validación de frases, anti-repetición y marca.
- `orchestrator/config.py`: `purchase_intent_enabled=True`, `purchase_intent_phrases="me interesa,quiero reservar,quiero comprar"`, `purchase_intent_interval_minutes=60` (1..1440), `purchase_intent_create_case=False`, `purchase_intent_mark_hours=72` (1..720); validación de las frases con `validate_phrases`.
- `orchestrator/administration.py`: `SettingSpec.kind` admite `"phrases"`; cuatro `SettingSpec` nuevos (`purchase_intent.phrases|enabled|interval_minutes|create_case`); prefijo `purchase_intent.` en `OPERATIONAL_PREFIXES`; campos en `OperationalSettings` (`purchase_intent_phrases: tuple[str, ...]`, `purchase_intent_enabled`, `purchase_intent_interval_minutes`, `purchase_intent_create_case`); `_valid_value`/`_normalized_value` para `phrases`.
- `orchestrator/admin_routes.py`: prefijo en `get_app_settings(...)`, rama de valor efectivo y `_setting_range` para `phrases` (el formulario de ajustes ya es genérico y escapa HTML).
- `orchestrator/harness.py`: `parse_router_answer` acepta `{"motivo": "purchase_intent"}` solo en `buscar_base_conocimiento`; `RouterDecision` gana `purchase_intent: bool = False` y `args` ya sin `motivo`; descripción en `_TOOL_DESCRIPTIONS`.
- `orchestrator/domain.py`: `_resolve_and_run` integra la detección; `_notify_purchase_intent`; `ConversationRow.purchase_intent`; orden en `panel_conversations`; `ConversationRef.last_purchase_intent_at`.
- `orchestrator/adapters/repository.py`: Protocol, Fake y Postgres: `last_event_at(contact_id, type) -> datetime | None` y subconsulta `last_purchase_intent_at` en `list_conversations`/`conversation_ref` (como ya hace `case_closed`).
- `orchestrator/panel_live.py` y `panel_live_js.py`: `PanelEventKind` incluye `"purchase_intent"`; `relevant()` lo acepta.
- `orchestrator/advisor_panel.py`: insignia «Interés de compra» (texto + clase CSS, sin depender del color) en la fila de la bandeja.
- `.env.example`, `render.yaml`: cinco variables nuevas.
- Tests: `tests/test_purchase_intent_pure.py`, `tests/test_purchase_intent_flow.py`, `tests/test_purchase_intent_panel.py`, `tests/test_purchase_intent_settings.py`; ajustes en `tests/fakes.py`.

## Firmas nuevas

```python
# purchase_intent.py
MAX_PHRASES = 30; MIN_PHRASE_CHARS = 3; MAX_PHRASE_CHARS = 80
def parse_phrases(raw: str) -> tuple[str, ...]: ...          # split por coma, strip, sin vacías
def phrases_valid(raw: str) -> bool: ...                     # R2/R3
def matches_purchase_phrase(text: str, phrases: Sequence[str]) -> bool: ...  # normalize_text + subcadena
def within_interval(last: datetime | None, now: datetime, minutes: int) -> bool: ...  # R19/R20
def has_purchase_interest(last_intent: datetime | None, last_closed: datetime | None,
                          status: str, now: datetime, mark_hours: int) -> bool: ...  # R13

# domain.py
def _notify_purchase_intent(contact: Contact, origin: Literal["phrase", "router"],
                            operational: OperationalSettings, settings: Settings,
                            adapters: Adapters) -> bool: ...   # True si registró una detección nueva
```

## Flujo

En `_resolve_and_run`, tras las ramas de supresión, traspaso humano (R10: gana siempre y retorna) y frustración, y antes del router:

1. Si `enabled` y `matches_purchase_phrase(text, phrases)` → `_notify_purchase_intent(..., "phrase")` (se ejecuta aunque `injection` sea verdadero: es comparación local, R23; el router sigue omitido si hay injection).
2. Si el router devuelve `purchase_intent` y no hubo detección por frase → `_notify_purchase_intent(..., "router")`; se ejecuta `buscar_base_conocimiento` con `args={}`.
3. `_notify_purchase_intent`: si `enabled` y no `within_interval(repo.last_event_at(contact.id, "purchase_intent"), now, minutes)` → `repo.add_event(contact.id, "purchase_intent", origin, now)` y `publish_case_event(key, "purchase_intent", adapters)` con `key = get_contact_last_case(contact.id) or contact.id`. Todo en `try/except` con `logger.error("purchase_intent_failed")` sin texto (R21).
4. El flujo normal responde (R12). Solo si hubo detección nueva y `create_case`, al terminar la herramienta se relee el estado: si sigue `active`/`no_access` y no hay caso abierto, `_handover(contact, "user_request", settings, adapters, ack=False)` (R17). Esto obliga a que `_resolve_and_run` conserve un único punto de salida tras ejecutar la herramienta (envoltorio `_run_with_intent`).

Marca (R13): `panel_conversations` calcula `has_purchase_interest(ref.last_purchase_intent_at, ref.last_closed_at, derived, now, settings.purchase_intent_mark_hours)`. Orden (R14): clave `(status != "pendiente", not row.purchase_intent, -last_activity)`.

Las anti-carreras entre dos mensajes simultáneos del mismo contacto no se tratan con candado: la cola de entrada (#64) serializa por `conversation_key`.

## Excepciones

Se reutilizan `SettingsFormInvalid` y `RouterInvalid`. No se añaden excepciones nuevas; los fallos de detección se capturan y se registran.

## Alternativa descartada

Modelar la intención como un motivo de `escalar_a_asesor` (`motivo=purchase_intent`): obligaría a tocar el contrato de handover (`reason`), cambiaría el estado a `with_advisor` y silenciaría al bot, contra el acceptance «el bot sigue respondiendo». También se descartó una tabla propia de frases: `app_settings` ya es editable desde el panel y se resuelve en cada mensaje (efecto inmediato).

## Dependencias nuevas

Ninguna.

## Supuestos a confirmar (valores por defecto configurables)

- Intervalo anti-repetición: 60 min (`PURCHASE_INTENT_INTERVAL_MINUTES`).
- Duración de la marca en bandeja: 72 h o hasta `case_closed` (`PURCHASE_INTENT_MARK_HOURS`); no se borra al tomar el asesor la conversación.
- Crear caso automáticamente: apagado (`PURCHASE_INTENT_CREATE_CASE=false`). Al activarlo, tras responder el bot pasa la conversación a asesor, como cualquier traspaso; el caso usa motivo `user_request` y el evento `purchase_intent` distingue el origen.
- Las frases no pueden contener comas (separador); la coincidencia es por subcadena normalizada, igual que `HANDOVER_KEYWORDS`.
- El evento guarda solo el origen (`phrase`/`router`), nunca la frase ni el texto, por privacidad.
- La clave de evento en vivo usa `contact_id` cuando no hay caso (`panel_events.case_id` es `TEXT` sin FK); la bandeja (sin filtro de caso) la recibe y el chat de un caso concreto la ignora.
