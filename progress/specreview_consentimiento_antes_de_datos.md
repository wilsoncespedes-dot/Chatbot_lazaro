# Spec review — feature #35 consentimiento_antes_de_datos

**Veredicto:** APPROVED (modo nocturno: el reviewer aprueba en lugar del humano)

## Comprobaciones clave (contra `services/orchestrator/orchestrator/domain.py`)
- **Rutas antes de la compuerta:** hoy `process_message` (domain.py:872-896) llama a
  `get_or_create_contact` en `/start`, `/consultar` y comandos de asesor antes de
  `_privacy_gate` (domain.py:898). El nuevo orden de design §3 pone todas las lecturas
  (`get_profile_by_telegram_user_id`, `get_link_token_role`, `has_privacy_consent`) antes de la
  primera escritura, y la única escritura antes de pasar la compuerta es `add_privacy_consent`.
  Cubiertas todas las rutas: texto libre, `/consultar` (bien y mal formado), `/responder`,
  `/cerrar`, comando de asesor mal formado y `/start` con token de cliente/inválido (S1).
- **Detección de personal de solo lectura:** `_is_linked_staff` solo lee y descarta uid <= 0
  sin llamar al repo (R2). `get_link_token_role` es un único `SELECT` (R5, T7). El orden
  lectura→escritura se verifica con un repo que registra las llamadas (T12).
- **Prueba de seguridad por ruta:** T9/T10/T11 parametrizadas por las 7 rutas, con
  `_linked_rows` y una comprobación absoluta de tablas vacías (R18-R20).
- **No regresión:** personal sin consentimiento y sin configuración (T14, T22), cliente con
  consentimiento (T19), cambio de versión (T20), autorización existente sin cambios (T18).
- **Contratos:** design §2 y §7 excluyen `contracts/`; ningún contrato nuevo.
- Cobertura acceptance→R completa (tabla en requirements.md). Cada R está en alguna task.
  Alternativas descartadas presentes; riesgo residual S6 documentado y aceptable.
- Nada peligroso: no borra datos ni usa red.

## Observaciones no bloqueantes
1. R4 tiene dos `DEBE` («DEBE devolver el rol… en otro caso DEBE devolver `None`»); se acepta como
   una única regla de retorno.
2. `processed_updates` lo escribe `main.py:211` (`mark_update_if_new`) antes de
   `process_message`; T10 debe ejercitarlo vía `env.post` (no llamando a `process_message`
   directamente) para que R20 quede probado de verdad.
3. En T22, al vincular el perfil `asesor` a 111, conviene que la aserción de `/start
   token-invalido` compruebe `link_failed_reply` (S2/R9) y no solo la ausencia de aviso.
