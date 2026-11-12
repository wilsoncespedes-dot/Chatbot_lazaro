# Design — #46 `consentimiento_texto_telegram`

## Resumen

Se añade una rama de **consentimiento por texto** solo para el canal
`telegram` dentro de la compuerta preconsentimiento existente
(`_handle_pre_consent_text`). La prueba de "aviso vigente mostrado" reutiliza
`ConsentChallengeStore` (#37): el aviso de texto registra un desafío ligado a
canal/usuario/chat/versión/hash, y la frase exacta lo consume de forma atómica
antes de registrar la decisión con `evidence_type="text"`. WhatsApp sigue en
la rama de botones sin cambios. Sin contratos nuevos ni dependencias nuevas.

## Archivos a modificar

### `services/orchestrator/orchestrator/config.py`
- Campos nuevos:
  - `privacy_reject_phrase: str = ""` (env `PRIVACY_REJECT_PHRASE`).
  - `privacy_text_consent_instruction: str =
    "Para aceptar, escribe exactamente: {accept}\nSi no aceptas, escribe exactamente: {reject}"`
    (env `PRIVACY_TEXT_CONSENT_INSTRUCTION`).
- Propiedades nuevas:
  - `consent_accept_phrase -> str`: `privacy_accept_phrase.strip() or "ACEPTO"` (R1).
  - `consent_reject_phrase -> str`: `privacy_reject_phrase.strip() or "NO ACEPTO"` (R2).
- `model_validator` nuevo `_validate_text_consent_phrases`: `ValueError` si
  las frases efectivas normalizadas coinciden (R3) o si la instrucción no
  contiene `{accept}` y `{reject}` (R4).
- **No** se cambia el default de `privacy_accept_phrase` (sigue `""`) para no
  activar `_validate_notice_phrase` ni alterar `privacy_configured`.

### `services/orchestrator/orchestrator/privacy.py`
- `TEXT_CONSENT_CHANNELS: frozenset[str] = frozenset({"telegram"})`.
- `def matches_consent_phrase(text: str, phrase: str) -> bool` — alias
  documentado de `is_acceptance` (igualdad tras `normalize_privacy_text`) (R5).
- `def text_consent_instruction(template: str, accept: str, reject: str) -> str`
  — sustitución con `str.replace` (no `str.format`, para tolerar llaves en el
  texto) (R7).
- `ConsentChallengeStore.consume_text(channel, external_user_id,
  external_chat_id, *, notice_version, notice_sha) -> bool`: bajo el candado,
  comprueba que exista desafío con misma versión/hash/chat y lo elimina;
  devuelve `False` en otro caso (R11, R14).

### `services/orchestrator/orchestrator/domain.py`
- `_consent_prompt(texts, include_greeting, channel, settings)`:
  - `telegram`: `greeting? + notice_text + "\n\n" + instrucción` (R7).
  - otros canales: `greeting? + notice_text + "\n\nAcepto\nNo acepto"` — se
    eliminan los sufijos `(privacy.accept)` / `(privacy.reject)` (R8). El
    `OptionsBlock` de WhatsApp no cambia (R28).
- `_notify_consent_prompt`:
  - Si `channel in TEXT_CONSENT_CHANNELS`: registra desafío siempre (R9) y
    envía solo `TextBlock` por `send_channel_blocks`, o `_notify_channel` si
    el gateway no tiene bloques (R6). Sin `OptionsBlock` ni pruebas.
  - Otros canales: comportamiento actual.
- `_handle_pre_consent_text`: para `telegram`, nuevo orden:
  1. `CLOSED` → `RESTART_MESSAGE`, se descarta `consent_shown` **y** el desafío
     (`consent_challenges.discard`) (R20).
  2. Si el texto coincide con frase de aceptación o rechazo efectiva:
     `consume_text(...)` con versión/hash vigentes; si `True` →
     `_record_text_consent_decision(...)`; si `False` → mostrar aviso
     (saludo incluido si es primera presentación) y salir (R14, R15).
  3. Si no se ha mostrado → aviso con saludo (comportamiento actual).
  4. Resto (incluye afirmaciones parecidas) → reenviar aviso con instrucción;
     **no** se usa `confirm_button_reply` (R21, R23).
  - Para canales no-texto (WhatsApp) la función conserva su lógica actual
    (R30).
- `_handle_pre_consent_text` recibe además `external_message_id: str` y
  `received_at: datetime`. Llamadores:
  - `_legacy_consent_gate`: `str(request.update_id)`, `request.received_at`.
  - `process_channel_message`: `message.external_message_id`,
    `message.received_at`.
- Nueva `_finish_acceptance(channel, external_user_id, destination, texts,
  settings, adapters)` extraída de `_handle_consent_button` (crear contacto,
  `AWAITING_LOGIN`, `issue_login_link`, `_send_identity_blocks`) y usada por
  botón y texto (R12).
- Nueva `_record_text_consent_decision(channel, external_user_id, destination,
  result, external_message_id, received_at, texts, settings, adapters)`:
  - `repo.add_privacy_decision(..., result, external_message_id, "",
    received_at, evidence_type="text")` (R10, R18).
  - `consent_shown.discard`.
  - `accepted` → `repo.mark_message_if_new(channel, external_message_id)`
    (R17) y `_finish_acceptance` (R12).
  - `rejected` → `repo.delete_contact_content(...)` y `rejected_reply` por
    `_notify_channel` (R18, R19).
- `_handle_consent_button`: tras el chequeo "ya consentido → ignorar" (R27),
  si `channel in TEXT_CONSENT_CHANNELS`: log
  `consent_button_ignored channel=telegram reason=text_consent_channel`, no
  consume desafío ni registra; llama `_notify_consent_prompt` (texto) (R25, R26).
- Nueva `consent_text_pending(message: NormalizedMessage, settings) -> bool`:
  `channel in TEXT_CONSENT_CHANNELS`, `kind == "text"` y el texto coincide con
  alguna frase efectiva (R16).
- Orden de las rutas de #35 en `process_message` intacto: la compuerta sigue
  antes de `get_or_create_contact` (R24).

### `services/orchestrator/orchestrator/main.py`
- `pending = consent_button_pending(body) or (not consent_ready and
  consent_text_pending(body, settings))` (calculado después de
  `consent_ready`) para que la frase se procese en la petición (R16). La
  rama `MessageRequest` histórica también evalúa
  `consent_text_pending(normalize_legacy_message(body), settings)` cuando no
  hay consentimiento vigente.

### `services/orchestrator/orchestrator/adapters/repository.py`
- `has_channel_privacy_consent` (memoria y Postgres): `evidence_type IN
  ('button', 'text')` (R13). `legacy` sigue excluido. Sin migración: la
  columna es `TEXT` sin `CHECK`.

### `services/telegram_gateway/telegram_gateway/config.py` / `domain.py` / `grouping.py`
- `message_grouping_reject_phrase: str = ""` (env
  `MESSAGE_GROUPING_REJECT_PHRASE`; vacío = desactivado, mismo patrón que la
  de aceptación).
- `is_immediate(text, accept_phrase, reject_phrase="")` trata ambas frases
  como inmediatas (R31). `grouping.py` pasa la nueva frase.
- `TelegramChannelAdapter.send` y `build_inline_keyboard` no cambian: sin
  `OptionsBlock` ya devuelven `reply_markup=None` (R32, solo test).

### Configuración y docs (no código de aplicación, los toca el implementer)
- `.env.example`: `PRIVACY_REJECT_PHRASE=`, `PRIVACY_TEXT_CONSENT_INSTRUCTION=`
  (comentario con el default), `MESSAGE_GROUPING_REJECT_PHRASE=`.
- `render.yaml`: `MESSAGE_GROUPING_REJECT_PHRASE` heredado de
  `PRIVACY_REJECT_PHRASE` del orchestrator, como la de aceptación.
- `docs/proyecto.md`: sección de consentimiento — Telegram por frase de texto,
  WhatsApp por botones, normalización y evidencia `text`.

## Firmas nuevas

```python
# privacy.py
TEXT_CONSENT_CHANNELS: frozenset[str]
def matches_consent_phrase(text: str, phrase: str) -> bool
def text_consent_instruction(template: str, accept: str, reject: str) -> str
class ConsentChallengeStore:
    def consume_text(self, channel: str, external_user_id: str,
                     external_chat_id: str, *, notice_version: str,
                     notice_sha: str) -> bool

# config.py
class Settings:
    privacy_reject_phrase: str
    privacy_text_consent_instruction: str
    @property
    def consent_accept_phrase(self) -> str
    @property
    def consent_reject_phrase(self) -> str

# domain.py
def consent_text_pending(message: NormalizedMessage, settings: Settings) -> bool
def _finish_acceptance(...) -> None
def _record_text_consent_decision(...) -> None

# telegram_gateway/domain.py
def is_immediate(text: str, accept_phrase: str, reject_phrase: str = "") -> bool
```

## Excepciones

- No se añaden excepciones de dominio. `ValueError` de pydantic en `Settings`
  para R3/R4.
- Un fallo de `add_privacy_decision` propaga como hoy; al procesarse en la
  petición (R16) el handler genérico responde `500`.

## Decisiones y supuestos (defaults configurables)

- **Frase de aceptación por defecto `ACEPTO`**, rechazo `NO ACEPTO`, vía
  propiedades efectivas (no cambia el default del campo para no romper
  validadores existentes).
- **Instrucción** operativa, no legal: configurable por
  `PRIVACY_TEXT_CONSENT_INSTRUCTION`; el aviso legal sigue saliendo del panel.
- **Normalización**: `normalize_privacy_text` existente (trim + espacios
  internos colapsados + `casefold`). Es la "normalización mínima" del
  acceptance; colapsar espacios internos se documenta aquí y en
  `docs/proyecto.md`.
- **Canales de consentimiento por texto**: constante `{"telegram"}` (decisión
  explícita del dueño; no se expone como variable para no abrir la vía de
  texto en WhatsApp por error).
- **Rechazo**: se guarda la misma fila mínima de decisión que el botón de #37
  (`privacy_consents`, permitida expresamente por #35) para poder cerrar y
  reiniciar desde `Nuevo`; no se guarda contenido del mensaje.
- **Evidencia `external_message_id` en Telegram**: el id externo canónico de
  Telegram en este sistema es el `update_id` (es el que usa
  `_legacy_from_normalized`), así que la ruta histórica guarda
  `str(update_id)`.
- **Desafío en memoria**: igual que #37; un reinicio del orquestador entre el
  aviso y la frase hace que la frase muestre otra vez el aviso (falla seguro).

## Alternativas descartadas

1. **Usar `consent_shown` (set en memoria) como prueba del aviso mostrado.**
   Descartada: no liga versión, hash ni chat; tras un cambio de
   `notice_version` una frase aceptaría un aviso no mostrado. El desafío de
   `ConsentChallengeStore` ya liga esos campos y se consume atómicamente.
2. **Mantener los botones inline y aceptar también texto en Telegram.**
   Descartada: contradice la decisión del dueño (quitar botones) y duplica
   caminos de evidencia.
3. **Variable `PRIVACY_TEXT_CONSENT_CHANNELS`.** Descartada: el dueño fijó
   Telegram; configurarlo abre un riesgo de cambiar WhatsApp sin spec.
4. **Persistir el desafío en BD.** Descartada: escribiría datos ligados al
   remitente antes del consentimiento (#35).

## Dependencias nuevas

Ninguna. No hay reutilización de código externo.

## Impacto en tests existentes

Los tests de `services/orchestrator/tests/test_conversation_states.py` que
ejercitan botones con el `channel="telegram"` por defecto (aceptar/rechazar
con botón, prueba firmada, desafío por presentación, chat ajeno, repetidos)
pasan a `channel="whatsapp"` para conservar la cobertura de #37 sobre el canal
que mantiene botones. Los tests de `test_consent_before_data.py` que aceptan
en Telegram por botón pasan a aceptar por frase de texto tras el aviso. El
test `test_text_affirmation_asks_for_the_button_and_keeps_awaiting` se limita
a WhatsApp (R30).
