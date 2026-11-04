# Spec review — feature #42 administracion_y_avisos

**Veredicto:** APPROVED

## Resumen
- Cobertura: los 5 criterios de acceptance están mapeados (tabla en
  requirements.md, l.46-52) y cada R tiene al menos una task (T0-T44).
- Coherencia con el código: verifiqué que existen las piezas que se reutilizan
  (`create_client`/`renew_credential`/`revoke_credential`/`close_client_session`/
  `_client_status` en domain.py l.978-1096, `credential_status`/`days_remaining`/
  `_POLICY_FIELDS`/`resolve_identity_policy` en identity.py, `channel_window` en
  panel.py, `advisor_send_template` l.2706 con `advisor_whatsapp_template_list`,
  `suppression_result_template` l.3284, `_handover` l.1436 con la rama `notified`,
  eventos `advisor_reply` con motivo `advisor:<id>` y mensajes `role="advisor"`).
  Los días se siguen calculando desde fechas (R2), sin contador.
- Diseño: respeta las 3 capas (`administration.py` puro, repositorio, rutas), no
  añade dependencias, los contratos son aditivos, incluye alternativas
  descartadas y Supuestos S1-S9 con defaults seguros (horario desactivado por
  defecto, aviso de WhatsApp fuera de ventana solo con plantilla aprobada, sin
  respaldo de entorno).
- Riesgo: la idempotencia del aviso se garantiza en BD con un `INSERT ... ON
  CONFLICT ... WHERE` atómico (R53/R54) y el aviso no genera escrituras
  conversacionales (R59). No se borran datos ni se accede a nada fuera del repo.
- Tasks: todas en `[ ]` y en orden.

## Observaciones no bloqueantes (el implementer puede tenerlas en cuenta)
1. EARS: R47, R48, R53 y R69 tienen dos `DEBE`/`NO DEBE` cada uno, y R42
   combina MIENTRAS con CUANDO. Se pueden verificar tal como están; al hacer la
   trazabilidad, cubrir con un test cada una de las dos partes.
2. R22 usa como sujeto «el siguiente mensaje» en lugar de «el sistema». Es
   verificable igualmente (T36).
3. S2: una fila `sending` que quede huérfana no se reintenta nunca. Es una
   elección conservadora y está documentada; conviene mostrarla como `sending`
   en `/admin/clientes` (R1 ya lo contempla).
