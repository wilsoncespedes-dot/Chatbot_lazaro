# Tasks — estados_y_consentimiento (feature #37)

- [x] T1 — Añadir `ConversationState`, `ConversationEvent` y el reductor puro
  `transition_state`; cubrir estados y transiciones sin dependencias externas.
  Cubre: R1, R8, R10, R11, R12, R13, R14, R15, R16, R17, R18.
- [x] T2 — Integrar el estado con el mensaje canónico por identidad/contacto de
  #36; derivar espera/rechazo antes del consentimiento en memoria y persistir
  estado únicamente tras consentimiento vigente. Cubre: R2, R7, R8, R22, R23,
  R35, R36.
- [x] T3 — Implementar botones normalizados `privacy.accept` y `privacy.reject`;
  guardar resultado, canal/ID, versión, hash, mensaje/botón y timestamp antes de
  cualquier confirmación; texto afirmativo solo solicita pulsar botón y una
  aceptación pasa a `esperando_inicio_sesion`. Cubre: R3–R6, R20, R24, R26,
  R36.
- [x] T4 — Migrar `privacy_consents` de forma aditiva para evidencia nueva,
  preservar aceptación legacy y requerir prueba de botón para que una decisión
  habilite el flujo nuevo; añadir tests de versión nueva, prueba faltante y
  rechazo. Cubre: R4, R5, R7, R20, R24, R34.
- [x] T5 — Añadir almacenamiento de `conversation_states` por contacto
  consentido y migración idempotente; probar reinicio tras rechazo sin guardar
  estado/contacto antes de aceptar. Cubre: R1, R8, R22, R23.
- [x] T6 — Enrutar `esperando_inicio_sesion`, `con_asesor` y `sin_acceso` a sus
  respuestas/flujos fijos sin LLM; conectar eventos fake de #38 y transiciones
  de cierre/inactividad, solicitud de asesor/supresión y handover/resolución
  existentes. Cubre: R9, R10, R11, R12, R13, R14, R16, R17, R18, R21, R27,
  R28.
- [x] T7 — Manejar audio/imagen/documento/sticker con la respuesta fija
  administrada, sin mutar estado ni persistir payload. Cubre: R15, R19, R21, R30.
- [x] T8 — Extender el panel admin existente para ver/editar textos fijos y
  versión legal con protección de rol/CSRF; persistir en `app_settings` y leer
  cambios sin reinicio. Cubre: R19, R20, R21, R25, R32, R33.
- [x] T9 — Implementar respuestas estáticas para política/preguntas, cierre,
  recordatorio, suspensión y contenido no textual; cerrar flujo si faltan textos
  legales requeridos; comprobar que el LLM no se llama. Cubre: R2–R3, R5–R6,
  R9, R14–R15, R21, R25, R30, R32, R33.
- [x] T10 — Añadir tests con fakes para transiciones, entrada/salida por estado,
  botón requerido, registro de rechazo/aceptación, cambio de versión, texto
  multimedia, borrado por rechazo, permisos/CSRF de textos y errores de
  persistencia; cada test identifica los requirements que cubre. Cubre: R1, R2,
  R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15, R16, R17, R18,
  R19, R20, R21, R22, R23, R24, R25, R26, R27, R28, R29, R30, R31, R32, R33,
  R34, R35, R36.
- [x] T11 — Ejecutar `./init.sh`, confirmar no regresión de #35/#36 y registrar
  trazabilidad `R<n> → test` en `progress/impl_estados_y_consentimiento.md`.
  Cubre: R1, R2, R3, R4, R5, R6, R7, R8, R9, R10, R11, R12, R13, R14, R15,
  R16, R17, R18, R19, R20, R21, R22, R23, R24, R25, R26, R27, R28, R29, R30,
  R31, R32, R33, R34, R35, R36.
  Resultado: 2,278 passed, 1 skipped; `./init.sh` exit code 0.
- [x] T12 — Enviar los botones canónicos como teclado interactivo de Telegram,
  recibir `callback_query` y normalizarlo al evento `button`; probar desde el
  webhook hasta la persistencia de la decisión. Cubre R2, R4, R5, R38.
- [x] T13 — Autenticar y vincular cada callback a la huella de versión/hash del
  aviso presentado; descartar callbacks viejos o manipulados sin consentimiento
  ni transición de estado; probar publicación de una política nueva entre
  presentación y clic. Cubre R4, R7, R20, R24, R37, R38.
- [x] T14 — Emitir un desafío aleatorio único por presentación en memoria,
  consumirlo atómicamente al primer clic válido y exigir que la identidad no
  tenga consentimiento vigente; probar rechazo repetido tras aceptación y
  aceptación repetida tras rechazo sin borrar/recrear datos. Cubre R4, R5, R29,
  R37, R39.
- [x] T15 — Vincular el desafío y su HMAC al `external_chat_id`; callback del
  mismo usuario desde otro chat no consume ni registra decisión. Añadir test de
  callback webhook desde chat distinto. Cubre R38, R40.
- [x] T16 — Repetir `./init.sh` tras T12–T15, actualizar la trazabilidad R1–R40
  y obtener la revisión final enfocada en los hallazgos anteriores.
  Resultado: 2,298 passed, 1 skipped, 2 warnings; `./init.sh` exit code 0.
  Trazabilidad R1–R40 actualizada en `progress/impl_estados_y_consentimiento.md`;
  revisión final `APPROVED` en `progress/review_estados_y_consentimiento.md`.
