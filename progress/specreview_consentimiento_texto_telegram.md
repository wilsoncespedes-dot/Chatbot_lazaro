# Spec review — feature #46 `consentimiento_texto_telegram`

**Veredicto:** APPROVED

## Resumen
- Cobertura: los 7 criterios de `acceptance` están mapeados a R1–R32 (tabla
  final de `requirements.md`); R31 (frase de rechazo no agrupada) está
  justificado por la paridad con la frase de aceptación existente en el gateway.
- Verificable: cada R<n> tiene test nombrado en `tasks.md` (T2–T22); todas las
  tasks están en `[ ]`, en orden, y juntas cubren R1–R32.
- Diseño coherente con el código actual: reutiliza `ConsentChallengeStore`
  (`privacy.py:149`, consumo atómico bajo candado) con un nuevo `consume_text`
  que liga versión/hash/chat; `has_channel_privacy_consent`
  (`repository.py:1382`, `:3452`) se amplía a `('button','text')` sin
  migración; no hay dependencias ni contratos nuevos; 3 capas respetadas.
  Hay 4 alternativas descartadas, y las decisiones/supuestos tienen defaults
  configurables (`PRIVACY_REJECT_PHRASE`, `PRIVACY_TEXT_CONSENT_INSTRUCTION`,
  `MESSAGE_GROUPING_REJECT_PHRASE`).
- Seguridad/#35: la gate sigue antes de `get_or_create_contact` (R24); el
  rechazo guarda solo la fila mínima de `privacy_consents`, ya permitida por
  #35/#37; si el desafío se pierde al reiniciar, la frase solo vuelve a mostrar
  el aviso (falla seguro). No toca la red ni archivos fuera del repo.

## Observaciones no bloqueantes (para el implementer)
1. R23 y R30 tienen dos modales (`NO DEBE … y DEBE …`). Son verificables con un
   solo test cada uno, así que no bloquea; si se reabre el spec, conviene
   partirlos.
2. R8 cambia el texto del aviso de WhatsApp: quita los sufijos
   `(privacy.accept)`/`(privacy.reject)` que hoy añade `domain.py:2248-2249`.
   El `OptionsBlock` no cambia (R28), y quitar IDs internos del texto visible es
   seguro, pero el implementer debe dejarlo anotado en
   `progress/impl_consentimiento_texto_telegram.md` como el único cambio
   visible en WhatsApp.
3. Normalización: `normalize_privacy_text` también junta los espacios
   internos repetidos en uno, algo más que el «trim + mayúsculas/minúsculas»
   del acceptance. Está documentado en el design y debe quedar también en
   `docs/proyecto.md` (T23).
